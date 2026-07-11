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

    def ensure_model(self, size, progress_cb=None):
        if progress_cb:
            progress_cb(484, 484)
        return "/fake/model"

    def load_model(self, path):
        return object()

    def effective_compute_type(self, model):
        return "int8"

    def transcribe_file(self, model, path, mode):
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
    assert (tmp_path / "transcripts" / "a.mp3.srt").exists()
    assert (tmp_path / "transcripts" / "b.mp3.json").exists()
    assert manifest.should_skip(job.files[0].task, "non_verbatim", "small")


def test_failure_is_isolated(tmp_path):
    job = make_job(tmp_path, ["a.mp3", "bad.mp3", "c.mp3"])
    run_job(job, Manifest(tmp_path), eng=FakeEngine(fail_names={"bad.mp3"}))
    assert [fs.status for fs in job.files] == ["done", "failed", "done"]
    assert "damaged" in job.files[1].error.lower()
    assert (tmp_path / "transcripts" / "c.mp3.srt").exists()


def test_premarked_skips_are_untouched(tmp_path):
    job = make_job(tmp_path, ["a.mp3", "b.mp3"], statuses={"a.mp3": "skipped"})
    run_job(job, Manifest(tmp_path), eng=FakeEngine())
    assert [fs.status for fs in job.files] == ["skipped", "done"]
    assert not (tmp_path / "transcripts" / "a.mp3.srt").exists()


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
