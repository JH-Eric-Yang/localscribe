"""End-to-end pipeline with the real tiny model (~75 MB download on first run).
Run explicitly: uv run pytest -m slow -v
Uses a synthesized tone WAV: transcript may be empty, but decode -> transcribe ->
write-outputs -> manifest must all succeed."""
import math
import struct
import wave

import pytest

from app.discovery import scan_folder
from app.state import FileStatus, JobState, Manifest
from app.worker import run_job

pytestmark = pytest.mark.slow


def write_tone_wav(path, seconds=3, rate=16000):
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        frames = b"".join(
            struct.pack("<h", int(12000 * math.sin(2 * math.pi * 440 * i / rate)))
            for i in range(rate * seconds))
        w.writeframes(frames)


@pytest.mark.parametrize("mode", ["non_verbatim", "verbatim"])
def test_real_pipeline(tmp_path, mode):
    write_tone_wav(tmp_path / "tone.wav")
    scan = scan_folder(tmp_path)
    assert [t.path.name for t in scan.tasks] == ["tone.wav"]

    job = JobState()
    job.folder = tmp_path
    job.mode = mode
    job.model = "tiny"
    job.files = [FileStatus(task=t) for t in scan.tasks]
    manifest = Manifest(tmp_path)

    run_job(job, manifest)

    assert job.phase == "done", job.error_message
    assert job.error_message is None
    assert job.files[0].status == "done"
    tag = "verbatim" if mode == "verbatim" else "clean"
    for ext in (".srt", ".vtt", ".csv", ".json"):
        assert (tmp_path / "transcripts" / f"tone.{tag}{ext}").exists()
    assert manifest.should_skip(scan.tasks[0], mode, "tiny")
