import errno
import threading
import time
from types import SimpleNamespace

import pytest

from app.discovery import FileTask
from app.state import FileStatus, JobState, Manifest
from app.worker import run_job


class FakeEngine:
    """Mirrors app.engine's surface (ensure_model/load_model/transcribe_file/
    segment_to_dict/effective_compute_type) without any model download."""

    def __init__(self, fail_names=(), enospc_names=()):
        self.fail_names = set(fail_names)
        self.enospc_names = set(enospc_names)
        self.enospc_thrown = set()
        self.transcribe_calls = []

    def ensure_model(self, size, progress_cb=None):
        if progress_cb:
            progress_cb(484, 484)
        return "/fake/model"

    def load_model(self, path, use_gpu=False):
        self.load_calls = getattr(self, "load_calls", [])
        self.load_calls.append(use_gpu)
        return object(), ("cuda" if use_gpu and getattr(self, "has_gpu", False)
                          else "cpu")

    def effective_compute_type(self, model):
        return "int8"

    def transcribe_file(self, model, path, mode):
        self.transcribe_calls.append(path.name)
        if path.name in self.fail_names:
            raise ValueError("Invalid data found when processing input")
        if path.name in self.enospc_names and path.name not in self.enospc_thrown:
            self.enospc_thrown.add(path.name)  # fail once, succeed on retry
            raise OSError(errno.ENOSPC, "No space left on device")
        seg = SimpleNamespace(id=1, start=0.0, end=1.0, text=" hello", words=None)
        info = SimpleNamespace(duration=1.0, language="en", language_probability=0.99)
        return iter([seg]), info

    def segment_to_dict(self, seg):
        return {"id": seg.id, "start": seg.start, "end": seg.end,
                "text": seg.text, "words": []}


def make_job(tmp_path, names, statuses=None):
    job = JobState()
    job.folder = tmp_path
    for i, name in enumerate(names):
        f = tmp_path / name
        f.write_bytes(b"x" * 10)
        st = f.stat()
        task = FileTask(path=f, size=st.st_size, mtime=st.st_mtime, duration=1.0)
        job.files.append(FileStatus(task=task,
                                    status=(statuses or {}).get(name, "queued")))
    return job


def test_happy_path_writes_outputs_and_manifest(tmp_path):
    job = make_job(tmp_path, ["a.mp3", "b.mp3"])
    manifest = Manifest(tmp_path)
    run_job(job, manifest, eng=FakeEngine())
    assert job.phase == "done" and job.error_message is None
    assert [fs.status for fs in job.files] == ["done", "done"]
    assert (tmp_path / "transcripts" / "a.clean.srt").exists()
    assert (tmp_path / "transcripts" / "b.clean.json").exists()
    assert manifest.should_skip(job.files[0].task, "non_verbatim", "small")


def test_failure_is_isolated(tmp_path):
    job = make_job(tmp_path, ["a.mp3", "bad.mp3", "c.mp3"])
    run_job(job, Manifest(tmp_path), eng=FakeEngine(fail_names={"bad.mp3"}))
    assert [fs.status for fs in job.files] == ["done", "failed", "done"]
    assert "damaged" in job.files[1].error.lower()
    assert (tmp_path / "transcripts" / "c.clean.srt").exists()


def test_premarked_skips_are_untouched(tmp_path):
    job = make_job(tmp_path, ["a.mp3", "b.mp3"], statuses={"a.mp3": "skipped"})
    run_job(job, Manifest(tmp_path), eng=FakeEngine())
    assert [fs.status for fs in job.files] == ["skipped", "done"]
    assert not list((tmp_path / "transcripts").glob("a.*")) if (tmp_path / "transcripts").exists() else True


def test_cancel_before_start_skips_everything(tmp_path):
    job = make_job(tmp_path, ["a.mp3", "b.mp3"])
    job.cancel_requested = True
    run_job(job, Manifest(tmp_path), eng=FakeEngine())
    assert job.phase == "done"
    assert [fs.status for fs in job.files] == ["skipped", "skipped"]


def test_download_failure_sets_job_error(tmp_path):
    class BrokenEngine(FakeEngine):
        def ensure_model(self, size, progress_cb=None):
            raise ConnectionError("blocked by proxy")
    job = make_job(tmp_path, ["a.mp3"])
    run_job(job, Manifest(tmp_path), eng=BrokenEngine())
    assert job.phase == "done" and "proxy" in job.error_message


def test_disk_full_pauses_then_resumes(tmp_path):
    job = make_job(tmp_path, ["a.mp3"])
    eng = FakeEngine(enospc_names={"a.mp3"})
    t = threading.Thread(target=run_job, args=(job, Manifest(tmp_path)),
                         kwargs={"eng": eng}, daemon=True)
    t.start()
    deadline = time.monotonic() + 5
    while job.phase != "paused_disk_full":
        assert time.monotonic() < deadline, f"never paused (phase={job.phase})"
        time.sleep(0.01)
    job.resume_event.set()
    t.join(timeout=5)
    assert job.phase == "done"
    assert job.files[0].status == "done"


def test_cancel_during_disk_full_pause_skips_without_retry(tmp_path):
    job = make_job(tmp_path, ["a.mp3"])
    eng = FakeEngine(enospc_names={"a.mp3"})
    t = threading.Thread(target=run_job, args=(job, Manifest(tmp_path)),
                         kwargs={"eng": eng}, daemon=True)
    t.start()
    deadline = time.monotonic() + 5
    while job.phase != "paused_disk_full":
        assert time.monotonic() < deadline, f"never paused (phase={job.phase})"
        time.sleep(0.01)
    job.cancel_requested = True
    job.resume_event.set()
    t.join(timeout=5)
    assert job.phase == "done"
    assert job.files[0].status == "skipped"
    assert eng.transcribe_calls.count("a.mp3") == 1  # not retried
    assert not list((tmp_path / "transcripts").glob("a.*")) if (tmp_path / "transcripts").exists() else True


def test_colliding_stems_keep_full_names(tmp_path):
    """interview.mp3 + interview.mp4 in one folder must not overwrite each
    other's transcripts — colliding stems fall back to the full filename."""
    job = make_job(tmp_path, ["interview.mp3", "interview.mp4", "solo.wav"])
    run_job(job, Manifest(tmp_path), eng=FakeEngine())
    out = tmp_path / "transcripts"
    assert (out / "interview.mp3.clean.srt").exists()
    assert (out / "interview.mp4.clean.srt").exists()
    assert not (out / "interview.clean.srt").exists()
    assert (out / "solo.clean.srt").exists()  # non-colliding file keeps the bare stem


def test_mode_tag_differentiates_transcripts(tmp_path):
    """Verbatim and clean transcripts of the same recording must not
    overwrite each other — the mode is part of the output name."""
    job = make_job(tmp_path, ["a.mp3"])
    job.mode = "verbatim"
    run_job(job, Manifest(tmp_path), eng=FakeEngine())
    assert (tmp_path / "transcripts" / "a.verbatim.srt").exists()

    job2 = make_job(tmp_path, ["b.mp3"])
    run_job(job2, Manifest(tmp_path), eng=FakeEngine())  # default non_verbatim
    assert (tmp_path / "transcripts" / "b.clean.srt").exists()


def test_gpu_enabled_but_unusable_sets_notice(tmp_path, monkeypatch):
    monkeypatch.setattr("app.gpu.enabled", lambda *a, **k: True)
    job = make_job(tmp_path, ["a.mp3"])
    eng = FakeEngine()  # has_gpu unset -> load_model reports "cpu"
    run_job(job, Manifest(tmp_path), eng=eng)
    assert eng.load_calls == [True]
    assert job.device_notice == "GPU not available — using CPU."
    assert job.files[0].status == "done"  # fallback, never a failure


def test_gpu_working_leaves_no_notice(tmp_path, monkeypatch):
    monkeypatch.setattr("app.gpu.enabled", lambda *a, **k: True)
    job = make_job(tmp_path, ["a.mp3"])
    eng = FakeEngine()
    eng.has_gpu = True
    run_job(job, Manifest(tmp_path), eng=eng)
    assert job.device_notice is None


def test_gpu_disabled_leaves_no_notice(tmp_path, monkeypatch):
    monkeypatch.setattr("app.gpu.enabled", lambda *a, **k: False)
    job = make_job(tmp_path, ["a.mp3"])
    eng = FakeEngine()
    run_job(job, Manifest(tmp_path), eng=eng)
    assert eng.load_calls == [False]
    assert job.device_notice is None
