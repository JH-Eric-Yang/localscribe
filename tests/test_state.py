import json

import pytest

from app.discovery import FileTask
from app.state import JobState, Manifest


@pytest.fixture
def task(tmp_path):
    f = tmp_path / "a.mp3"
    f.write_bytes(b"x" * 10)
    stat = f.stat()
    return FileTask(path=f, size=stat.st_size, mtime=stat.st_mtime, duration=60.0)


def make_outputs(tmp_path, name="a.mp3"):
    out = tmp_path / "transcripts"
    out.mkdir(exist_ok=True)
    paths = [out / f"{name}{ext}" for ext in (".srt", ".vtt", ".csv", ".json")]
    for p in paths:
        p.write_text("x", encoding="utf-8")
    return paths


def test_skip_after_done(tmp_path, task):
    m = Manifest(tmp_path)
    m.mark_done(task, "verbatim", "small", make_outputs(tmp_path))
    assert m.should_skip(task, "verbatim", "small") is True


def test_no_skip_when_unknown(tmp_path, task):
    assert Manifest(tmp_path).should_skip(task, "verbatim", "small") is False


def test_no_skip_on_mode_or_model_change(tmp_path, task):
    m = Manifest(tmp_path)
    m.mark_done(task, "verbatim", "small", make_outputs(tmp_path))
    assert m.should_skip(task, "non_verbatim", "small") is False
    assert m.should_skip(task, "verbatim", "medium") is False


def test_no_skip_when_file_changed(tmp_path, task):
    m = Manifest(tmp_path)
    m.mark_done(task, "verbatim", "small", make_outputs(tmp_path))
    changed = FileTask(path=task.path, size=task.size + 1, mtime=task.mtime, duration=60.0)
    assert m.should_skip(changed, "verbatim", "small") is False


def test_no_skip_when_output_missing(tmp_path, task):
    m = Manifest(tmp_path)
    outputs = make_outputs(tmp_path)
    m.mark_done(task, "verbatim", "small", outputs)
    outputs[0].unlink()
    assert m.should_skip(task, "verbatim", "small") is False


def test_no_skip_after_failed(tmp_path, task):
    m = Manifest(tmp_path)
    m.mark_failed(task, "verbatim", "small", "damaged")
    assert m.should_skip(task, "verbatim", "small") is False


def test_persists_and_survives_corruption(tmp_path, task):
    m = Manifest(tmp_path)
    m.mark_done(task, "verbatim", "small", make_outputs(tmp_path))
    reloaded = Manifest(tmp_path)
    assert reloaded.should_skip(task, "verbatim", "small") is True
    manifest_path = tmp_path / "transcripts" / ".localscribe" / "state.json"
    assert json.loads(manifest_path.read_text(encoding="utf-8"))  # valid json on disk
    manifest_path.write_text("{corrupt", encoding="utf-8")
    assert Manifest(tmp_path).should_skip(task, "verbatim", "small") is False  # no crash


@pytest.mark.parametrize("root", ["null", "[]", '"x"'])
def test_no_crash_on_non_dict_manifest_root(tmp_path, task, root):
    manifest_path = tmp_path / "transcripts" / ".localscribe" / "state.json"
    manifest_path.parent.mkdir(parents=True)
    manifest_path.write_text(root, encoding="utf-8")
    assert Manifest(tmp_path).should_skip(task, "verbatim", "small") is False


def test_no_skip_when_done_entry_has_empty_outputs(tmp_path, task):
    manifest_path = tmp_path / "transcripts" / ".localscribe" / "state.json"
    manifest_path.parent.mkdir(parents=True)
    entry = {
        task.path.name: {
            "size": task.size, "mtime": task.mtime,
            "mode": "verbatim", "model": "small",
            "status": "done", "outputs": [], "error": None,
        }
    }
    manifest_path.write_text(json.dumps(entry), encoding="utf-8")
    assert Manifest(tmp_path).should_skip(task, "verbatim", "small") is False


def test_survives_folder_rename(tmp_path, task):
    """Manifest must store output filenames (not absolute paths), so renaming or
    moving the transcribed folder does not void all resume state."""
    m = Manifest(tmp_path)
    m.mark_done(task, "verbatim", "small", make_outputs(tmp_path))
    moved = tmp_path.parent / "moved_folder"
    tmp_path.rename(moved)
    moved_task = FileTask(path=moved / task.path.name, size=task.size,
                          mtime=task.mtime, duration=60.0)
    assert Manifest(moved).should_skip(moved_task, "verbatim", "small") is True


def test_jobstate_defaults():
    job = JobState()
    assert job.phase == "idle"
    assert job.files == [] and job.cancel_requested is False
    assert not job.resume_event.is_set()
