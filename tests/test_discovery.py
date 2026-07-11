from pathlib import Path

import pytest

from app.discovery import MEDIA_EXTENSIONS, FileTask, probe_duration, scan_folder


def fake_probe(path):
    if path.name == "broken.mp3":
        raise ValueError("Invalid data found when processing input")
    return 60.0


@pytest.fixture
def folder(tmp_path):
    (tmp_path / "b_interview.mp3").write_bytes(b"x" * 10)
    (tmp_path / "A_video.MP4").write_bytes(b"x" * 10)  # uppercase ext must match
    (tmp_path / "broken.mp3").write_bytes(b"x" * 10)
    (tmp_path / "empty.wav").write_bytes(b"")           # zero-byte -> damaged
    (tmp_path / "notes.docx").write_bytes(b"x")         # non-media -> ignored
    (tmp_path / ".hidden.mp3").write_bytes(b"x")        # hidden -> silently skipped
    (tmp_path / "transcripts").mkdir()                  # output dir -> skipped
    return tmp_path


def test_scan_folder(folder):
    result = scan_folder(folder, probe=fake_probe)
    assert [t.path.name for t in result.tasks] == ["A_video.MP4", "b_interview.mp3"]
    assert all(isinstance(t, FileTask) and t.duration == 60.0 for t in result.tasks)
    assert sorted(p.name for p in result.damaged) == ["broken.mp3", "empty.wav"]
    assert [p.name for p in result.ignored] == ["notes.docx"]


def test_whitelist_covers_spec():
    for ext in [".mp3", ".wav", ".m4a", ".mp4", ".mov", ".mkv", ".webm", ".opus"]:
        assert ext in MEDIA_EXTENSIONS


class _FakeContainer:
    def __init__(self, duration):
        self.duration = duration

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


def test_probe_duration_converts_time_base(monkeypatch):
    import av

    monkeypatch.setattr(av, "open", lambda p: _FakeContainer(5 * av.time_base))
    assert probe_duration(Path("x.mp3")) == 5.0


def test_probe_duration_rejects_missing_duration(monkeypatch):
    import av

    monkeypatch.setattr(av, "open", lambda p: _FakeContainer(None))
    with pytest.raises(ValueError, match="no duration"):
        probe_duration(Path("x.mp3"))
