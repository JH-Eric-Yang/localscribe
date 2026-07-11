# LocalScribe Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A git-cloneable folder that lets a non-technical researcher double-click one launcher, get a local web page, pick a folder, choose Verbatim/Non-verbatim, and batch-transcribe every audio/video file to .srt/.vtt/.csv/.json — on Windows and macOS, CPU-only, no Python/ffmpeg/admin rights required.

**Architecture:** Two double-click launchers self-bootstrap uv → pinned CPython 3.12 → locked deps into a gitignored `.managed/` dir, then run a NiceGUI single-page app on 127.0.0.1. One worker thread drives faster-whisper (sequential API only) with per-file failure isolation and a per-folder resume manifest; all output writes are atomic. Spec: `docs/superpowers/specs/2026-07-11-localscribe-design.md`.

**Tech Stack:** Python 3.12 (uv-managed), faster-whisper==1.2.1, nicegui>=3.14,<4, huggingface_hub (transitive), pytest (dev). No other runtime deps — everything else is stdlib.

## Global Constraints

- Dependencies: exactly `faster-whisper==1.2.1` and `nicegui>=3.14,<4`; dev-only `pytest>=8`. Never add torch, whisperx, ffmpeg packages, or tqdm (tqdm arrives transitively via faster-whisper).
- Python pinned `>=3.12,<3.13`; `.python-version` contains `3.12`.
- Transcription uses **only** the sequential `WhisperModel.transcribe()` API — never `BatchedInferencePipeline` (it silently drops the temperature-fallback ladder).
- Both modes keep the guard set: `beam_size=5`, `temperature=[0.0,0.2,0.4,0.6,0.8,1.0]`, `condition_on_previous_text=False`, `no_speech_threshold=0.6`, `log_prob_threshold=-1.0`, `compression_ratio_threshold=2.4`, `word_timestamps=True`.
- Models only from ungated `Systran/faster-whisper-*` HuggingFace repos; no tokens/accounts ever; UI offers base/small/medium, default small; engine also supports tiny (tests only).
- All user-facing copy is plain language (no jargon); every failure path ends in a friendly message + log pointer, never a vanished window.
- Outputs go to `<chosen>/transcripts/` named `<original name with extension>.<fmt>` (e.g. `interview.mp3.srt`); every file write is `.partial` + `os.replace`.
- All runtime state/caches live in gitignored `.managed/` (uv, python, uv-cache, hf-cache, logs, app.lock); per-folder state only in `<chosen>/transcripts/.localscribe/state.json`.
- App binds `127.0.0.1` only; default port 8377, probe upward if taken.
- uv version pinned to 0.11.28 in both launchers (installer URL and release zip URL).
- Commit after every task with the `Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>` trailer.

## File Structure

```
Auto_Transcription/
├── Start Transcriber.command   # Task 12 — macOS launcher (mode 100755, LF)
├── Start Transcriber.bat       # Task 12 — Windows launcher (CRLF)
├── pyproject.toml              # Task 1
├── uv.lock                     # Task 1 (generated)
├── .python-version             # Task 1
├── .gitignore                  # Task 1
├── .gitattributes              # Task 1
├── conftest.py                 # Task 1 (empty; puts repo root on sys.path for pytest)
├── README.md                   # Task 14
├── docs/TROUBLESHOOTING.md     # Task 14
├── app/
│   ├── __init__.py             # Task 1 — APP_VERSION
│   ├── writers.py              # Task 2 — srt/vtt/csv/json + atomic writes
│   ├── discovery.py            # Task 3 — whitelist scan + PyAV probe
│   ├── state.py                # Task 4 — JobState (in-memory) + Manifest (state.json)
│   ├── diagnostics.py          # Task 5 — logging + error categorization
│   ├── engine.py               # Task 6 — mode presets, model download, transcribe wrapper
│   ├── awake.py                # Task 7 — keep-awake context manager (small deviation from
│   │                           #   spec layout: spec put this in ui.py; own file = testable)
│   ├── worker.py               # Task 8 — job thread, per-file isolation, disk-full pause
│   ├── folder_picker.py        # Task 9 — vendored directory-picker dialog
│   ├── ui.py                   # Task 10 — page, JobState rendering, ETA, tab title
│   └── main.py                 # Task 11 — single-instance, port probe, ui.run
└── tests/
    ├── test_writers.py         # Task 2
    ├── test_discovery.py       # Task 3
    ├── test_state.py           # Task 4
    ├── test_diagnostics.py     # Task 5
    ├── test_engine.py          # Task 6
    ├── test_awake.py           # Task 7
    ├── test_worker.py          # Task 8
    ├── test_folder_picker.py   # Task 9
    ├── test_ui.py              # Task 10 (eta_text only)
    ├── test_main.py            # Task 11
    └── test_integration.py     # Task 13 (marked slow; excluded by default)
```

---

### Task 1: Project scaffolding and locked environment

**Files:**
- Create: `pyproject.toml`, `.python-version`, `.gitignore`, `.gitattributes`, `conftest.py`, `app/__init__.py`, `uv.lock` (generated)

**Interfaces:**
- Produces: `app.APP_VERSION: str` (used by worker/ui); a synced `.venv` so `uv run pytest` works for all later tasks.

- [ ] **Step 1: Ensure uv exists on this dev machine**

Run: `command -v uv || curl -LsSf https://astral.sh/uv/install.sh | sh`
Expected: a path to `uv`, or a successful install (then restart shell or use `~/.local/bin/uv`).

- [ ] **Step 2: Write project files**

`pyproject.toml`:
```toml
[project]
name = "localscribe"
version = "1.0.0"
description = "Double-click local batch transcription for researchers"
requires-python = ">=3.12,<3.13"
dependencies = [
    "faster-whisper==1.2.1",
    "nicegui>=3.14,<4",
]

[dependency-groups]
dev = ["pytest>=8"]

[tool.uv]
package = false

[tool.pytest.ini_options]
testpaths = ["tests"]
addopts = "-m 'not slow'"
markers = ["slow: integration tests that download real models"]
```

`.python-version`:
```
3.12
```

`.gitignore`:
```
.managed/
.venv/
__pycache__/
*.pyc
```

`.gitattributes`:
```
*.bat text eol=crlf
*.command text eol=lf
```

`conftest.py` (empty file — its presence makes pytest put the repo root on `sys.path` so `import app.writers` works):
```python
```

`app/__init__.py`:
```python
APP_VERSION = "1.0.0"
```

- [ ] **Step 3: Generate the lockfile and sync**

Run: `uv lock && uv sync`
Expected: `uv.lock` created; `.venv` populated. If resolution fails on a wheel for your platform, STOP and report — the spec requires verified wheels for win_amd64/macosx_arm64/macosx_x86_64.

- [ ] **Step 4: Verify imports and pytest**

Run: `uv run python -c "import faster_whisper, nicegui; print('ok')" && uv run pytest --collect-only -q`
Expected: `ok`, then `no tests ran` (exit code 5 from pytest is fine at this stage).

- [ ] **Step 5: Commit**

```bash
git add pyproject.toml uv.lock .python-version .gitignore .gitattributes conftest.py app/__init__.py
git commit -m "feat: project scaffolding with locked uv environment

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 2: Output writers (srt/vtt/csv/json, atomic)

**Files:**
- Create: `app/writers.py`
- Test: `tests/test_writers.py`

**Interfaces:**
- Consumes: nothing (stdlib only). Segments are plain dicts: `{"id": int, "start": float, "end": float, "text": str, "words": [{"word": str, "start": float, "end": float, "probability": float}]}`.
- Produces: `format_timestamp(seconds: float, sep: str) -> str`; `write_outputs(out_dir: Path, source_name: str, segments: list[dict], meta: dict) -> list[Path]` (writes `<source_name>.srt/.vtt/.csv/.json`, returns the 4 paths); `atomic_write(path: Path, content: str, encoding: str) -> None`.

- [ ] **Step 1: Write the failing tests**

`tests/test_writers.py`:
```python
import json
from pathlib import Path

from app.writers import atomic_write, format_timestamp, to_csv, to_srt, to_vtt, write_outputs

SEGMENTS = [
    {"id": 1, "start": 0.0, "end": 2.5, "text": " Hello there.", "words": []},
    {"id": 2, "start": 3661.5, "end": 3663.0, "text": " Um, yes.",
     "words": [{"word": " Um,", "start": 3661.5, "end": 3661.9, "probability": 0.9}]},
]
META = {"source_file": "a.mp3", "duration_seconds": 3663.0, "language": "en",
        "language_probability": 0.98, "mode": "verbatim", "model_size": "small",
        "app_version": "1.0.0", "created_utc": "2026-07-11T00:00:00+00:00"}


def test_format_timestamp():
    assert format_timestamp(0.0, ",") == "00:00:00,000"
    assert format_timestamp(3661.5, ",") == "01:01:01,500"
    assert format_timestamp(3661.5, ".") == "01:01:01.500"
    assert format_timestamp(-1.0, ",") == "00:00:00,000"


def test_to_srt():
    assert to_srt(SEGMENTS) == (
        "1\n00:00:00,000 --> 00:00:02,500\nHello there.\n"
        "\n2\n01:01:01,500 --> 01:01:03,000\nUm, yes.\n"
    )


def test_to_vtt():
    out = to_vtt(SEGMENTS)
    assert out.startswith("WEBVTT\n\n")
    assert "00:00:00.000 --> 00:00:02.500\nHello there." in out


def test_to_csv_header_and_rows():
    lines = to_csv(SEGMENTS).splitlines()
    assert lines[0] == "segment,start_seconds,end_seconds,start_timecode,end_timecode,text"
    assert lines[1] == "1,0.000,2.500,00:00:00.000,00:00:02.500,Hello there."


def test_atomic_write_leaves_no_partial(tmp_path):
    target = tmp_path / "x.srt"
    atomic_write(target, "content", "utf-8")
    assert target.read_text(encoding="utf-8") == "content"
    assert list(tmp_path.glob("*.partial")) == []


def test_write_outputs(tmp_path):
    paths = write_outputs(tmp_path / "transcripts", "a.mp3", SEGMENTS, META)
    names = sorted(p.name for p in paths)
    assert names == ["a.mp3.csv", "a.mp3.json", "a.mp3.srt", "a.mp3.vtt"]
    csv_bytes = (tmp_path / "transcripts" / "a.mp3.csv").read_bytes()
    assert csv_bytes.startswith(b"\xef\xbb\xbf")  # UTF-8 BOM for Excel
    data = json.loads((tmp_path / "transcripts" / "a.mp3.json").read_text(encoding="utf-8"))
    assert data["mode"] == "verbatim"
    assert data["segments"][1]["words"][0]["word"] == " Um,"
    assert list(Path(tmp_path / "transcripts").glob("*.partial")) == []
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_writers.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.writers'`

- [ ] **Step 3: Implement**

`app/writers.py`:
```python
"""Serialize transcript segments to .srt/.vtt/.csv/.json with atomic writes."""
import csv
import io
import json
import os
from pathlib import Path


def format_timestamp(seconds: float, sep: str = ",") -> str:
    ms = max(0, round(seconds * 1000))
    h, ms = divmod(ms, 3_600_000)
    m, ms = divmod(ms, 60_000)
    s, ms = divmod(ms, 1000)
    return f"{h:02d}:{m:02d}:{s:02d}{sep}{ms:03d}"


def to_srt(segments: list[dict]) -> str:
    blocks = []
    for i, seg in enumerate(segments, start=1):
        blocks.append(
            f"{i}\n{format_timestamp(seg['start'], ',')} --> "
            f"{format_timestamp(seg['end'], ',')}\n{seg['text'].strip()}\n"
        )
    return "\n".join(blocks)


def to_vtt(segments: list[dict]) -> str:
    lines = ["WEBVTT", ""]
    for seg in segments:
        lines.append(
            f"{format_timestamp(seg['start'], '.')} --> {format_timestamp(seg['end'], '.')}"
        )
        lines.append(seg["text"].strip())
        lines.append("")
    return "\n".join(lines)


def to_csv(segments: list[dict]) -> str:
    buf = io.StringIO()
    writer = csv.writer(buf, lineterminator="\r\n")
    writer.writerow(["segment", "start_seconds", "end_seconds",
                     "start_timecode", "end_timecode", "text"])
    for i, seg in enumerate(segments, start=1):
        writer.writerow([
            i, f"{seg['start']:.3f}", f"{seg['end']:.3f}",
            format_timestamp(seg["start"], "."), format_timestamp(seg["end"], "."),
            seg["text"].strip(),
        ])
    return buf.getvalue()


def to_json(segments: list[dict], meta: dict) -> str:
    return json.dumps({**meta, "segments": segments}, ensure_ascii=False, indent=2)


def atomic_write(path: Path, content: str, encoding: str = "utf-8") -> None:
    partial = path.with_name(path.name + ".partial")
    partial.write_text(content, encoding=encoding, newline="")
    os.replace(partial, path)


def write_outputs(out_dir: Path, source_name: str, segments: list[dict], meta: dict) -> list[Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    written = []
    for suffix, content, encoding in [
        (".srt", to_srt(segments), "utf-8"),
        (".vtt", to_vtt(segments), "utf-8"),
        (".csv", to_csv(segments), "utf-8-sig"),
        (".json", to_json(segments, meta), "utf-8"),
    ]:
        path = out_dir / (source_name + suffix)
        atomic_write(path, content, encoding)
        written.append(path)
    return written
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_writers.py -v`
Expected: 6 passed

- [ ] **Step 5: Commit**

```bash
git add app/writers.py tests/test_writers.py
git commit -m "feat: atomic srt/vtt/csv/json transcript writers

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 3: File discovery with PyAV probe

**Files:**
- Create: `app/discovery.py`
- Test: `tests/test_discovery.py`

**Interfaces:**
- Consumes: nothing from other tasks.
- Produces: `MEDIA_EXTENSIONS: set[str]`; `@dataclass FileTask(path: Path, size: int, mtime: float, duration: float | None)`; `@dataclass ScanResult(tasks: list[FileTask], damaged: list[Path], ignored: list[Path])`; `scan_folder(folder: Path, probe=probe_duration) -> ScanResult`; `probe_duration(path: Path) -> float` (raises on unreadable media).

- [ ] **Step 1: Write the failing tests**

`tests/test_discovery.py`:
```python
import pytest

from app.discovery import MEDIA_EXTENSIONS, FileTask, scan_folder


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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_discovery.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.discovery'`

- [ ] **Step 3: Implement**

`app/discovery.py`:
```python
"""Non-recursive media discovery with a cheap PyAV readability probe."""
from dataclasses import dataclass
from pathlib import Path

MEDIA_EXTENSIONS = {
    ".mp3", ".wav", ".m4a", ".aac", ".flac", ".ogg", ".oga", ".opus", ".wma",
    ".aiff", ".aif", ".mpga",
    ".mp4", ".mov", ".m4v", ".avi", ".mkv", ".webm", ".wmv", ".mpg", ".mpeg", ".3gp",
}


@dataclass
class FileTask:
    path: Path
    size: int
    mtime: float
    duration: float | None


@dataclass
class ScanResult:
    tasks: list
    damaged: list
    ignored: list


def probe_duration(path: Path) -> float:
    import av  # imported lazily: keeps module import light for tests

    with av.open(str(path)) as container:
        if container.duration is None:
            raise ValueError(f"no duration in {path.name}")
        return container.duration / av.time_base


def scan_folder(folder: Path, probe=probe_duration) -> ScanResult:
    tasks, damaged, ignored = [], [], []
    for entry in sorted(folder.iterdir(), key=lambda p: p.name.lower()):
        if entry.name.startswith(".") or entry.is_dir():
            continue
        if entry.suffix.lower() not in MEDIA_EXTENSIONS:
            ignored.append(entry)
            continue
        stat = entry.stat()
        if stat.st_size == 0:
            damaged.append(entry)
            continue
        try:
            duration = probe(entry)
        except Exception:
            damaged.append(entry)
            continue
        tasks.append(FileTask(path=entry, size=stat.st_size,
                              mtime=stat.st_mtime, duration=duration))
    return ScanResult(tasks=tasks, damaged=damaged, ignored=ignored)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_discovery.py -v`
Expected: 2 passed

- [ ] **Step 5: Commit**

```bash
git add app/discovery.py tests/test_discovery.py
git commit -m "feat: media file discovery with readability probe

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 4: Job state and resume manifest

**Files:**
- Create: `app/state.py`
- Test: `tests/test_state.py`

**Interfaces:**
- Consumes: `FileTask` from `app.discovery`.
- Produces: `@dataclass FileStatus(task: FileTask, status: str = "queued", progress: float = 0.0, error: str | None = None, elapsed: float | None = None)` — status values: `queued|running|done|skipped|failed`; `class JobState` with attributes `phase` (`idle|downloading|transcribing|paused_disk_full|done`), `folder: Path | None`, `mode: str` (`non_verbatim|verbatim`), `model: str`, `files: list[FileStatus]`, `current_index: int`, `download_done: int`, `download_total: int`, `cancel_requested: bool`, `resume_event: threading.Event`, `started_at: float | None`, `message: str`, `error_message: str | None`; `class Manifest(folder: Path)` with `.should_skip(task, mode, model) -> bool`, `.mark_done(task, mode, model, outputs: list[Path])`, `.mark_failed(task, mode, model, error: str)`, `.save()` (atomic).

- [ ] **Step 1: Write the failing tests**

`tests/test_state.py`:
```python
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


def test_jobstate_defaults():
    job = JobState()
    assert job.phase == "idle"
    assert job.files == [] and job.cancel_requested is False
    assert not job.resume_event.is_set()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_state.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.state'`

- [ ] **Step 3: Implement**

`app/state.py`:
```python
"""In-memory job state shared with the UI, and the per-folder resume manifest."""
import json
import os
import threading
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from app.discovery import FileTask


@dataclass
class FileStatus:
    task: FileTask
    status: str = "queued"  # queued|running|done|skipped|failed
    progress: float = 0.0
    error: str | None = None
    elapsed: float | None = None


class JobState:
    def __init__(self):
        self.phase = "idle"  # idle|downloading|transcribing|paused_disk_full|done
        self.folder: Path | None = None
        self.mode = "non_verbatim"
        self.model = "small"
        self.files: list[FileStatus] = []
        self.current_index = -1
        self.download_done = 0
        self.download_total = 0
        self.cancel_requested = False
        self.resume_event = threading.Event()
        self.started_at: float | None = None
        self.message = ""
        self.error_message: str | None = None


class Manifest:
    """Maps input filename -> completion record in <folder>/transcripts/.localscribe/state.json."""

    def __init__(self, folder: Path):
        self.path = folder / "transcripts" / ".localscribe" / "state.json"
        self.data: dict = {}
        if self.path.exists():
            try:
                self.data = json.loads(self.path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                self.data = {}

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        partial = self.path.with_name(self.path.name + ".partial")
        partial.write_text(json.dumps(self.data, indent=2), encoding="utf-8")
        os.replace(partial, self.path)

    def should_skip(self, task: FileTask, mode: str, model: str) -> bool:
        entry = self.data.get(task.path.name)
        if not entry or entry.get("status") != "done":
            return False
        if entry.get("size") != task.size or entry.get("mtime") != task.mtime:
            return False
        if entry.get("mode") != mode or entry.get("model") != model:
            return False
        return all(Path(p).exists() for p in entry.get("outputs", []))

    def _record(self, task: FileTask, mode: str, model: str, **extra) -> None:
        self.data[task.path.name] = {
            "size": task.size, "mtime": task.mtime, "mode": mode, "model": model,
            "finished_at": datetime.now(timezone.utc).isoformat(), **extra,
        }
        self.save()

    def mark_done(self, task: FileTask, mode: str, model: str, outputs: list[Path]) -> None:
        self._record(task, mode, model, status="done",
                     outputs=[str(p) for p in outputs], error=None)

    def mark_failed(self, task: FileTask, mode: str, model: str, error: str) -> None:
        self._record(task, mode, model, status="failed", outputs=[], error=error)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_state.py -v`
Expected: 8 passed

- [ ] **Step 5: Commit**

```bash
git add app/state.py tests/test_state.py
git commit -m "feat: job state and atomic resume manifest

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 5: Diagnostics — logging and plain-language error categorization

**Files:**
- Create: `app/diagnostics.py`
- Test: `tests/test_diagnostics.py`

**Interfaces:**
- Consumes: nothing from other tasks.
- Produces: `setup_logging(managed_dir: Path) -> logging.Logger` (logger name `"localscribe"`, RotatingFileHandler at `managed_dir/logs/app.log`); `log_run_header(logger, settings: dict) -> None`; `categorize_error(exc: Exception) -> str` (plain-language message; damaged-file wording contains `"damaged"`, memory wording contains `"memory"`).

- [ ] **Step 1: Write the failing tests**

`tests/test_diagnostics.py`:
```python
import errno
import logging

from app.diagnostics import categorize_error, log_run_header, setup_logging


def test_categorize_memory():
    assert "memory" in categorize_error(MemoryError()).lower()


def test_categorize_damaged_by_message():
    exc = ValueError("Invalid data found when processing input")
    assert "damaged" in categorize_error(exc).lower()


def test_categorize_damaged_by_av_module():
    class FakeAvError(Exception):
        pass
    FakeAvError.__module__ = "av.error"
    assert "damaged" in categorize_error(FakeAvError("whatever")).lower()


def test_categorize_generic_points_to_log():
    assert "log" in categorize_error(RuntimeError("boom")).lower()


def test_setup_logging_and_header(tmp_path):
    logger = setup_logging(tmp_path)
    log_run_header(logger, {"mode": "verbatim", "model": "small"})
    logger.info("hello")
    for h in logger.handlers:
        h.flush()
    text = (tmp_path / "logs" / "app.log").read_text(encoding="utf-8")
    assert "hello" in text and "mode" in text
    assert isinstance(logger, logging.Logger)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_diagnostics.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.diagnostics'`

- [ ] **Step 3: Implement**

`app/diagnostics.py`:
```python
"""Logging setup and translation of exceptions into plain-language messages."""
import logging
import platform
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path


def setup_logging(managed_dir: Path) -> logging.Logger:
    logger = logging.getLogger("localscribe")
    logger.setLevel(logging.INFO)
    if not logger.handlers:
        log_dir = managed_dir / "logs"
        log_dir.mkdir(parents=True, exist_ok=True)
        handler = RotatingFileHandler(log_dir / "app.log", maxBytes=2_000_000,
                                      backupCount=3, encoding="utf-8")
        handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
        logger.addHandler(handler)
    return logger


def log_run_header(logger: logging.Logger, settings: dict) -> None:
    logger.info("run header: os=%s arch=%s python=%s settings=%s",
                platform.platform(), platform.machine(), sys.version.split()[0], settings)


def categorize_error(exc: Exception) -> str:
    if isinstance(exc, MemoryError):
        return "This file is too large for this computer's memory."
    text = str(exc).lower()
    root_module = exc.__class__.__module__.split(".")[0]
    if root_module == "av" or "invalid data" in text or "moov atom" in text:
        return "This file appears to be damaged or in an unsupported format."
    return "Something went wrong with this file — see the log for details."
```

(Disk-full is deliberately NOT handled here: the worker in Task 8 catches `OSError` with `errno.ENOSPC` *before* calling `categorize_error` and pauses the whole job instead of failing the file.)

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_diagnostics.py -v`
Expected: 5 passed

- [ ] **Step 5: Commit**

```bash
git add app/diagnostics.py tests/test_diagnostics.py
git commit -m "feat: logging setup and plain-language error categorization

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 6: Engine — mode presets, model download, transcribe wrapper

**Files:**
- Create: `app/engine.py`
- Test: `tests/test_engine.py`

**Interfaces:**
- Consumes: nothing from other tasks.
- Produces: `VERBATIM_PROMPT: str`; `MODEL_REPOS: dict[str, str]` (keys: tiny/base/small/medium); `transcribe_kwargs(mode: str) -> dict`; `ensure_model(size: str, progress_cb=None, retries=3, download=None, sleep=time.sleep) -> str` (returns local snapshot path; raises `ModelDownloadError` after retries); `load_model(model_path: str)` (returns `WhisperModel`); `transcribe_file(model, path: Path, mode: str) -> (segment_iterator, info)`; `segment_to_dict(seg) -> dict` (the dict shape Task 2 consumes); `effective_compute_type(model) -> str`; `hotwords_injected_per_window() -> bool` (build-time source check).

- [ ] **Step 1: Write the failing tests**

`tests/test_engine.py`:
```python
import pytest

from app.engine import (MODEL_REPOS, VERBATIM_PROMPT, ModelDownloadError,
                        ensure_model, hotwords_injected_per_window,
                        segment_to_dict, transcribe_kwargs)


def test_verbatim_prompt_shape():
    assert VERBATIM_PROMPT == VERBATIM_PROMPT.strip()  # leading spaces skew timestamps
    assert "um" in VERBATIM_PROMPT.lower() and "uh" in VERBATIM_PROMPT.lower()


def test_shared_guards_in_both_modes():
    for mode in ("verbatim", "non_verbatim"):
        kw = transcribe_kwargs(mode)
        assert kw["beam_size"] == 5
        assert kw["temperature"] == [0.0, 0.2, 0.4, 0.6, 0.8, 1.0]
        assert kw["condition_on_previous_text"] is False
        assert kw["no_speech_threshold"] == 0.6
        assert kw["log_prob_threshold"] == -1.0
        assert kw["compression_ratio_threshold"] == 2.4
        assert kw["word_timestamps"] is True
        assert kw["vad_filter"] is True


def test_verbatim_mode_specifics():
    kw = transcribe_kwargs("verbatim")
    assert kw["initial_prompt"] == VERBATIM_PROMPT
    assert kw["hotwords"] == VERBATIM_PROMPT  # injected into EVERY 30-s window
    assert kw["vad_parameters"] == {"min_silence_duration_ms": 2000, "speech_pad_ms": 400}


def test_non_verbatim_mode_specifics():
    kw = transcribe_kwargs("non_verbatim")
    assert kw["initial_prompt"] is None
    assert kw.get("hotwords") is None
    assert kw["vad_parameters"] == {"min_silence_duration_ms": 500}


def test_unknown_mode_rejected():
    with pytest.raises(ValueError):
        transcribe_kwargs("clean")


def test_model_repos_ungated_systran():
    assert MODEL_REPOS["small"] == "Systran/faster-whisper-small"
    assert set(MODEL_REPOS) == {"tiny", "base", "small", "medium"}


def test_hotwords_injected_per_window():
    assert hotwords_injected_per_window(), (
        "Installed faster-whisper no longer injects hotwords into every window when "
        "there is no previous-text conditioning — Verbatim mode is broken. Spec fallback: "
        "condition_on_previous_text=True + hallucination_silence_threshold."
    )


def test_ensure_model_retries_then_succeeds():
    calls = []
    def flaky_download(repo, tqdm_class=None):
        calls.append(repo)
        if len(calls) < 3:
            raise ConnectionError("network blip")
        return "/fake/path"
    path = ensure_model("small", download=flaky_download, sleep=lambda s: None)
    assert path == "/fake/path"
    assert calls == ["Systran/faster-whisper-small"] * 3


def test_ensure_model_gives_up():
    def always_fails(repo, tqdm_class=None):
        raise ConnectionError("blocked")
    with pytest.raises(ModelDownloadError) as exc_info:
        ensure_model("small", download=always_fails, sleep=lambda s: None)
    assert "internet" in str(exc_info.value).lower()


def test_segment_to_dict():
    class W:
        word, start, end, probability = " um,", 1.0, 1.2, 0.9
    class S:
        id, start, end, text, words = 1, 0.0, 2.0, " Hello", [W()]
    d = segment_to_dict(S())
    assert d == {"id": 1, "start": 0.0, "end": 2.0, "text": " Hello",
                 "words": [{"word": " um,", "start": 1.0, "end": 1.2, "probability": 0.9}]}
    S.words = None
    assert segment_to_dict(S())["words"] == []
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_engine.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.engine'`

- [ ] **Step 3: Implement**

`app/engine.py`:
```python
"""faster-whisper wrapper: mode presets, model download, sequential transcription.

Sequential API only — BatchedInferencePipeline silently drops the temperature
fallback ladder (verified against faster-whisper source during design review).
"""
import time
from pathlib import Path

MODEL_REPOS = {
    "tiny": "Systran/faster-whisper-tiny",  # not offered in the UI; used by tests
    "base": "Systran/faster-whisper-base",
    "small": "Systran/faster-whisper-small",
    "medium": "Systran/faster-whisper-medium",
}

# Filler-dense, <224 tokens, stripped (leading spaces skew timestamps).
VERBATIM_PROMPT = (
    "Mm-hmm. Uh, yeah, so, um, I was- I was thinking, like, you know, it's... "
    "it's kind of, uh, hard to say. Umm, let me think like, hmm... Okay, here's "
    "what I'm, like, thinking. So, so um, uh, and um, like um, er, ah, uh-huh, "
    "you know what I mean, sort of, I mean, right?"
).strip()

_GUARDS = {
    "beam_size": 5,
    "temperature": [0.0, 0.2, 0.4, 0.6, 0.8, 1.0],
    "condition_on_previous_text": False,
    "no_speech_threshold": 0.6,
    "log_prob_threshold": -1.0,
    "compression_ratio_threshold": 2.4,
    "word_timestamps": True,
    "vad_filter": True,
}


class ModelDownloadError(Exception):
    pass


def transcribe_kwargs(mode: str) -> dict:
    if mode == "verbatim":
        # hotwords ride into EVERY 30-s window when condition_on_previous_text=False;
        # initial_prompt covers window 1. VAD loosened (not off) to keep hesitation
        # pauses without opening the long-silence hallucination surface.
        return {**_GUARDS,
                "initial_prompt": VERBATIM_PROMPT, "hotwords": VERBATIM_PROMPT,
                "vad_parameters": {"min_silence_duration_ms": 2000, "speech_pad_ms": 400}}
    if mode == "non_verbatim":
        return {**_GUARDS,
                "initial_prompt": None,
                "vad_parameters": {"min_silence_duration_ms": 500}}
    raise ValueError(f"unknown mode: {mode!r}")


def hotwords_injected_per_window() -> bool:
    """Build-time check that the installed faster-whisper still injects hotwords
    into each window's prompt when there is no prefix — the load-bearing verbatim
    mechanic. Guards against a silent behavior change on dependency upgrade."""
    import inspect

    import faster_whisper.transcribe as fwt
    src = " ".join(inspect.getsource(fwt.WhisperModel.get_prompt).split())
    return "if hotwords and not prefix" in src


def _progress_tqdm(progress_cb):
    from tqdm.auto import tqdm as base_tqdm

    class UITqdm(base_tqdm):
        def update(self, n=1):
            super().update(n)
            if progress_cb and self.total:
                progress_cb(self.n, self.total)
    return UITqdm


def ensure_model(size: str, progress_cb=None, retries: int = 3,
                 download=None, sleep=time.sleep) -> str:
    if download is None:
        from huggingface_hub import snapshot_download
        download = snapshot_download
    last_exc = None
    for attempt in range(retries):
        try:
            return download(MODEL_REPOS[size], tqdm_class=_progress_tqdm(progress_cb))
        except Exception as exc:  # snapshot_download resumes partial downloads on retry
            last_exc = exc
            sleep(2 ** attempt)
    raise ModelDownloadError(
        "Could not download the speech model — you need internet the first time. "
        "If you are on a university network, a proxy may be blocking huggingface.co."
    ) from last_exc


def load_model(model_path: str):
    import os

    from faster_whisper import WhisperModel
    cpu_threads = max(1, (os.cpu_count() or 4) - 1)
    return WhisperModel(model_path, device="cpu", compute_type="int8",
                        cpu_threads=cpu_threads)


def effective_compute_type(model) -> str:
    # ctranslate2 silently falls back when int8 is unsupported — log the truth.
    return str(getattr(getattr(model, "model", None), "compute_type", "unknown"))


def transcribe_file(model, path: Path, mode: str):
    return model.transcribe(str(path), task="transcribe", **transcribe_kwargs(mode))


def segment_to_dict(seg) -> dict:
    return {
        "id": seg.id, "start": seg.start, "end": seg.end, "text": seg.text,
        "words": [{"word": w.word, "start": w.start, "end": w.end,
                   "probability": w.probability} for w in (seg.words or [])],
    }
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_engine.py -v`
Expected: 10 passed. If `test_hotwords_injected_per_window` FAILS, STOP — do not weaken the test; report it and apply the spec's fallback plan instead.

- [ ] **Step 5: Commit**

```bash
git add app/engine.py tests/test_engine.py
git commit -m "feat: engine presets, verified verbatim mechanics, model download

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 7: Keep-awake context manager

**Files:**
- Create: `app/awake.py`
- Test: `tests/test_awake.py`

**Interfaces:**
- Consumes: nothing from other tasks.
- Produces: `keep_awake()` context manager. On macOS spawns `caffeinate -i -w <pid>`; on Windows calls `SetThreadExecutionState(ES_CONTINUOUS | ES_SYSTEM_REQUIRED)` **on the calling thread** (so the worker thread must enter it, which Task 10's job thread does); elsewhere no-op.

- [ ] **Step 1: Write the failing tests**

`tests/test_awake.py`:
```python
import subprocess
import sys

import app.awake as awake


def test_darwin_spawns_and_terminates_caffeinate(monkeypatch):
    events = []

    class FakeProc:
        def terminate(self):
            events.append("terminated")

    def fake_popen(cmd, **kwargs):
        events.append(cmd[:2])
        return FakeProc()

    monkeypatch.setattr(awake.sys, "platform", "darwin")
    monkeypatch.setattr(subprocess, "Popen", fake_popen)
    with awake.keep_awake():
        pass
    assert events[0] == ["caffeinate", "-i"]
    assert events[-1] == "terminated"


def test_other_platform_is_noop(monkeypatch):
    monkeypatch.setattr(awake.sys, "platform", "linux")
    with awake.keep_awake():
        pass  # must not raise
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_awake.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.awake'`

- [ ] **Step 3: Implement**

`app/awake.py`:
```python
"""Prevent system sleep while a job runs. Enter from the WORKER thread on
Windows — SetThreadExecutionState applies to the calling thread."""
import contextlib
import os
import subprocess
import sys

ES_CONTINUOUS = 0x80000000
ES_SYSTEM_REQUIRED = 0x00000001


@contextlib.contextmanager
def keep_awake():
    proc = None
    windows = sys.platform == "win32"
    try:
        if sys.platform == "darwin":
            # -w: caffeinate exits by itself if our process dies
            proc = subprocess.Popen(["caffeinate", "-i", "-w", str(os.getpid())])
        elif windows:
            import ctypes
            ctypes.windll.kernel32.SetThreadExecutionState(
                ES_CONTINUOUS | ES_SYSTEM_REQUIRED)
        yield
    finally:
        if proc is not None:
            proc.terminate()
        elif windows:
            import ctypes
            ctypes.windll.kernel32.SetThreadExecutionState(ES_CONTINUOUS)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_awake.py -v`
Expected: 2 passed

- [ ] **Step 5: Commit**

```bash
git add app/awake.py tests/test_awake.py
git commit -m "feat: keep-awake context manager for long batch jobs

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 8: Worker — job loop with per-file isolation and disk-full pause

**Files:**
- Create: `app/worker.py`
- Test: `tests/test_worker.py`

**Interfaces:**
- Consumes: `JobState`, `FileStatus`, `Manifest` (Task 4); `write_outputs` (Task 2); `categorize_error` (Task 5); the engine module surface (Task 6) — injected as `eng` for tests.
- Produces: `run_job(job: JobState, manifest: Manifest, eng=app.engine) -> None` — blocking; meant to run in a daemon thread. Contract: sets `job.phase` through `downloading → transcribing → done` (or `paused_disk_full` awaiting `job.resume_event`); never raises; per-file failures set `FileStatus.status="failed"` + plain-language `.error` and the batch continues; `job.cancel_requested` stops after the current file; pre-marked `status="skipped"` files are not touched; job-level failures (e.g. model download) set `job.error_message`.

- [ ] **Step 1: Write the failing tests**

`tests/test_worker.py`:
```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_worker.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.worker'`

- [ ] **Step 3: Implement**

`app/worker.py`:
```python
"""The job loop: one worker thread, per-file isolation, disk-full pause, manifest updates."""
import errno
import logging
import time
from datetime import datetime, timezone

from app import APP_VERSION
from app import engine as default_engine
from app.diagnostics import categorize_error
from app.state import FileStatus, JobState, Manifest
from app.writers import write_outputs

logger = logging.getLogger("localscribe")


def run_job(job: JobState, manifest: Manifest, eng=default_engine) -> None:
    try:
        _run(job, manifest, eng)
    except Exception as exc:  # job-level failure (model download, model load)
        logger.exception("job failed before/outside per-file processing")
        job.error_message = str(exc)
    finally:
        job.phase = "done"


def _run(job: JobState, manifest: Manifest, eng) -> None:
    job.started_at = time.monotonic()
    job.phase = "downloading"

    def dl_progress(done: int, total: int) -> None:
        job.download_done, job.download_total = done, total

    model_path = eng.ensure_model(job.model, progress_cb=dl_progress)
    model = eng.load_model(model_path)
    logger.info("effective compute type: %s", eng.effective_compute_type(model))

    job.phase = "transcribing"
    out_dir = job.folder / "transcripts"
    for i, fs in enumerate(job.files):
        if job.cancel_requested:
            for rest in job.files[i:]:
                if rest.status == "queued":
                    rest.status = "skipped"
            job.message = "Stopped by user."
            break
        if fs.status == "skipped":
            continue
        job.current_index = i
        fs.status = "running"
        started = time.monotonic()
        _process_with_disk_full_pause(job, fs, model, out_dir, manifest, eng)
        fs.elapsed = time.monotonic() - started


def _process_with_disk_full_pause(job, fs: FileStatus, model, out_dir, manifest, eng):
    while True:
        try:
            _process_file(job, fs, model, out_dir, manifest, eng)
            fs.status = "done"
            fs.progress = 1.0
            return
        except OSError as exc:
            if getattr(exc, "errno", None) == errno.ENOSPC:
                logger.warning("disk full — pausing job")
                job.resume_event.clear()
                job.phase = "paused_disk_full"
                job.resume_event.wait()
                job.phase = "transcribing"
                continue  # retry the same file
            _fail(job, fs, manifest, exc)
            return
        except Exception as exc:
            _fail(job, fs, manifest, exc)
            return


def _fail(job, fs: FileStatus, manifest: Manifest, exc: Exception) -> None:
    logger.exception("file failed: %s", fs.task.path)
    fs.status = "failed"
    fs.error = categorize_error(exc)
    manifest.mark_failed(fs.task, job.mode, job.model, fs.error)


def _process_file(job, fs: FileStatus, model, out_dir, manifest, eng) -> None:
    seg_iter, info = eng.transcribe_file(model, fs.task.path, job.mode)
    duration = fs.task.duration or getattr(info, "duration", 0) or 0
    segments = []
    for seg in seg_iter:
        segments.append(eng.segment_to_dict(seg))
        if duration:
            fs.progress = min(0.99, seg.end / duration)
    meta = {
        "source_file": fs.task.path.name,
        "duration_seconds": duration,
        "language": getattr(info, "language", None),
        "language_probability": getattr(info, "language_probability", None),
        "mode": job.mode,
        "model_size": job.model,
        "app_version": APP_VERSION,
        "created_utc": datetime.now(timezone.utc).isoformat(),
    }
    outputs = write_outputs(out_dir, fs.task.path.name, segments, meta)
    manifest.mark_done(fs.task, job.mode, job.model, outputs)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_worker.py -v`
Expected: 6 passed

- [ ] **Step 5: Commit**

```bash
git add app/worker.py tests/test_worker.py
git commit -m "feat: worker job loop with failure isolation and disk-full pause

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 9: Folder picker dialog (vendored)

**Files:**
- Create: `app/folder_picker.py`
- Test: `tests/test_folder_picker.py`

**Interfaces:**
- Consumes: nicegui.
- Produces: `list_subdirectories(path: Path) -> list[Path]` (sorted case-insensitively, no hidden dirs, `[]` on PermissionError); `class FolderPicker(ui.dialog)` — usage from an async handler: `result = await FolderPicker(start)` → chosen folder path as `str`, or `None` on cancel. Adapted from NiceGUI's `local_file_picker` example, directories only.

- [ ] **Step 1: Write the failing test (pure helper only — the dialog itself is exercised manually in Task 10's smoke test)**

`tests/test_folder_picker.py`:
```python
from app.folder_picker import list_subdirectories


def test_list_subdirectories(tmp_path):
    (tmp_path / "b_data").mkdir()
    (tmp_path / "Alpha").mkdir()
    (tmp_path / ".hidden").mkdir()
    (tmp_path / "file.txt").write_text("x")
    names = [p.name for p in list_subdirectories(tmp_path)]
    assert names == ["Alpha", "b_data"]


def test_list_subdirectories_permission_error(tmp_path, monkeypatch):
    def boom(self):
        raise PermissionError()
    monkeypatch.setattr(type(tmp_path), "iterdir", boom)
    assert list_subdirectories(tmp_path) == []
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_folder_picker.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.folder_picker'`

- [ ] **Step 3: Implement**

`app/folder_picker.py`:
```python
"""Directory-only picker dialog, adapted from NiceGUI's local_file_picker example."""
from pathlib import Path

from nicegui import events, ui


def list_subdirectories(path: Path) -> list[Path]:
    try:
        return sorted(
            (p for p in path.iterdir() if p.is_dir() and not p.name.startswith(".")),
            key=lambda p: p.name.lower(),
        )
    except PermissionError:
        return []


class FolderPicker(ui.dialog):
    def __init__(self, directory: str = "~") -> None:
        super().__init__()
        self.current = Path(directory).expanduser().resolve()
        with self, ui.card().classes("w-[28rem]"):
            ui.label("Double-click a folder to open it").classes("text-sm text-gray-500")
            self.path_label = ui.label(str(self.current)).classes("font-mono text-xs")
            self.grid = ui.aggrid({
                "columnDefs": [{"field": "name", "headerName": "Folder"}],
                "rowSelection": "single",
            }).classes("w-full h-64").on("cellDoubleClicked", self._descend)
            with ui.row().classes("w-full justify-end"):
                ui.button("Cancel", on_click=lambda: self.submit(None)).props("flat")
                ui.button("Choose this folder",
                          on_click=lambda: self.submit(str(self.current)))
        self._refresh()

    def _refresh(self) -> None:
        rows = []
        if self.current.parent != self.current:
            rows.append({"name": "⬆ ..", "path": str(self.current.parent)})
        rows += [{"name": f"\U0001f4c1 {p.name}", "path": str(p)}
                 for p in list_subdirectories(self.current)]
        self.path_label.text = str(self.current)
        self.grid.options["rowData"] = rows
        self.grid.update()

    def _descend(self, e: events.GenericEventArguments) -> None:
        self.current = Path(e.args["data"]["path"])
        self._refresh()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_folder_picker.py -v`
Expected: 2 passed

- [ ] **Step 5: Commit**

```bash
git add app/folder_picker.py tests/test_folder_picker.py
git commit -m "feat: vendored directory-only folder picker dialog

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 10: The web UI

**Files:**
- Create: `app/ui.py`
- Test: `tests/test_ui.py`

**Interfaces:**
- Consumes: everything from Tasks 3–9: `scan_folder`, `JobState`/`FileStatus`/`Manifest`, `run_job`, `keep_awake`, `FolderPicker`.
- Produces: importing `app.ui` registers the `/` page on nicegui; `eta_text(media_done: float, wall_elapsed: float, media_total: float) -> str | None` (None during the first 30 s calibration); module-level shared `job: JobState`.

- [ ] **Step 1: Write the failing test for the ETA helper**

`tests/test_ui.py`:
```python
from app.ui import eta_text


def test_eta_none_during_calibration():
    assert eta_text(media_done=10.0, wall_elapsed=10.0, media_total=100.0) is None
    assert eta_text(media_done=0.0, wall_elapsed=60.0, media_total=100.0) is None


def test_eta_phrasing():
    # 60 media-s in 60 wall-s -> 1x realtime -> 540 media-s left -> "about 9 minutes left"
    assert eta_text(media_done=60.0, wall_elapsed=60.0, media_total=600.0) == "about 9 minutes left"
    assert eta_text(media_done=590.0, wall_elapsed=60.0, media_total=600.0) == "about 1 minute left"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_ui.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.ui'`

- [ ] **Step 3: Implement**

`app/ui.py`:
```python
"""Single page: setup card -> progress -> completion, all rendered from JobState."""
import logging
import subprocess
import sys
import threading
from pathlib import Path

from nicegui import app as nicegui_app
from nicegui import ui

from app import worker
from app.awake import keep_awake
from app.discovery import ScanResult, scan_folder
from app.folder_picker import FolderPicker
from app.state import FileStatus, JobState, Manifest

logger = logging.getLogger("localscribe")

job = JobState()
current_scan: ScanResult | None = None
manifest: Manifest | None = None

MODE_OPTIONS = {
    "non_verbatim": "Non-verbatim — cleaned-up, easier to read (recommended)",
    "verbatim": "Verbatim — keeps um, uh, repetitions and false starts",
}
MODEL_OPTIONS = {
    "base": "Faster — less accurate",
    "small": "Standard — recommended",
    "medium": "Most accurate — much slower (1.5 GB download)",
}
STATUS_ICONS = {"queued": "radio_button_unchecked", "running": "autorenew",
                "done": "check_circle", "skipped": "remove_circle_outline",
                "failed": "error"}
STATUS_COLORS = {"queued": "grey", "running": "primary", "done": "positive",
                 "skipped": "warning", "failed": "negative"}


def eta_text(media_done: float, wall_elapsed: float, media_total: float) -> str | None:
    if wall_elapsed < 30 or media_done <= 0:
        return None
    rate = media_done / wall_elapsed
    remaining_min = max(1, round((media_total - media_done) / rate / 60))
    return f"about {remaining_min} minute{'s' if remaining_min != 1 else ''} left"


def _media_progress() -> tuple[float, float]:
    done = total = 0.0
    for fs in job.files:
        d = fs.task.duration or 0.0
        if fs.status == "skipped":
            continue
        total += d
        done += d if fs.status in ("done", "failed") else d * fs.progress
    return done, total


def open_folder(path: Path) -> None:
    if sys.platform == "darwin":
        subprocess.Popen(["open", str(path)])
    elif sys.platform == "win32":
        subprocess.Popen(["explorer", str(path)])
    else:
        subprocess.Popen(["xdg-open", str(path)])


def start_job() -> None:
    job.files = []
    for task in current_scan.tasks:
        skipped = (not job_redo_flag["redo"]
                   and manifest.should_skip(task, job.mode, job.model))
        job.files.append(FileStatus(task=task,
                                    status="skipped" if skipped else "queued"))
    job.cancel_requested = False
    job.error_message = None
    job.message = ""
    job.phase = "downloading"
    threading.Thread(target=_job_thread, daemon=True).start()


def retry_job() -> None:
    """After a job-level failure (e.g. model download): re-run pending files."""
    for fs in job.files:
        if fs.status in ("failed", "running"):
            fs.status = "queued"
            fs.progress = 0.0
            fs.error = None
    job.cancel_requested = False
    job.error_message = None
    job.phase = "downloading"
    threading.Thread(target=_job_thread, daemon=True).start()


def _job_thread() -> None:
    with keep_awake():  # entered on the worker thread: required on Windows
        worker.run_job(job, manifest)


def reset_to_setup() -> None:
    global current_scan, manifest
    job.phase = "idle"
    job.files = []
    job.folder = None
    current_scan = None
    manifest = None


job_redo_flag = {"redo": False}


@ui.page("/")
def index() -> None:
    async def pick_folder() -> None:
        result = await FolderPicker("~")
        if result:
            choose_folder(result)

    def choose_folder(path_str: str) -> None:
        global current_scan, manifest
        folder = Path(path_str).expanduser()
        if not folder.is_dir():
            ui.notify("That folder does not exist — check the path.", type="warning")
            return
        job.folder = folder
        manifest = Manifest(folder)
        current_scan = scan_folder(folder)
        folder_input.value = str(folder)
        update_scan_summary()

    def update_scan_summary() -> None:
        if current_scan is None:
            return
        n_skip = sum(1 for t in current_scan.tasks
                     if manifest.should_skip(t, job.mode, job.model))
        parts = [f"Found {len(current_scan.tasks)} audio/video files"]
        if n_skip and not job_redo_flag["redo"]:
            parts.append(f"{n_skip} already transcribed — will be skipped")
        if n_skip and job_redo_flag["redo"]:
            parts.append(f"existing transcripts for {n_skip} files will be replaced")
        if current_scan.damaged:
            parts.append(f"{len(current_scan.damaged)} unreadable or damaged — skipped")
        if current_scan.ignored:
            parts.append(f"{len(current_scan.ignored)} other files ignored")
        scan_label.text = ", ".join(parts) + "."
        pending = len(current_scan.tasks) - (0 if job_redo_flag["redo"] else n_skip)
        start_btn.set_enabled(pending > 0)
        start_btn.text = ("Start transcription" if pending
                          else "Nothing to do — all files already transcribed")

    def on_start() -> None:
        start_job()
        body.refresh()

    with ui.column().classes("w-full max-w-3xl mx-auto p-4 gap-4"):
        ui.label("LocalScribe").classes("text-2xl font-bold")
        ui.label("Transcribe every audio/video file in a folder — on this computer, "
                 "nothing is uploaded anywhere.").classes("text-sm text-gray-500")

        with ui.card().classes("w-full").bind_visibility_from(
                job, "phase", backward=lambda p: p == "idle"):
            ui.label("1. Choose the folder with your recordings").classes("text-lg")
            with ui.row().classes("w-full items-center"):
                folder_input = ui.input("Folder to transcribe").props("readonly") \
                    .classes("grow")
                ui.button("Browse…", on_click=pick_folder)
            with ui.expansion("Or type/paste a folder path (e.g. a network drive)"):
                typed = ui.input("Full folder path").classes("w-full")
                ui.button("Use this path", on_click=lambda: choose_folder(typed.value))
            scan_label = ui.label("").classes("text-sm text-gray-600")
            ui.checkbox("Re-do already transcribed files",
                        on_change=lambda e: (job_redo_flag.__setitem__("redo", e.value),
                                             update_scan_summary()))

            ui.label("2. How should it transcribe?").classes("text-lg mt-2")
            ui.radio(MODE_OPTIONS, value=job.mode,
                     on_change=lambda e: (setattr(job, "mode", e.value),
                                          update_scan_summary()))
            ui.label("Verbatim keeps many more hesitations, but no software can "
                     "capture every single one.").classes("text-xs text-gray-500")
            ui.select(MODEL_OPTIONS, value=job.model, label="Accuracy vs speed",
                      on_change=lambda e: (setattr(job, "model", e.value),
                                           update_scan_summary())).classes("w-72")
            ui.label("The first run downloads a speech model (about 0.5 GB for "
                     "Standard, one time only). Keep the laptop plugged in with the "
                     "lid open during transcription.").classes("text-xs text-gray-500")
            start_btn = ui.button("Start transcription", on_click=on_start) \
                .props("size=lg color=primary")
            start_btn.disable()

        @ui.refreshable
        def body() -> None:
            if job.phase == "idle":
                ui.page_title("LocalScribe")
                return
            done, total = _media_progress()
            pct = int(done / total * 100) if total else 0
            if job.phase == "done":
                render_completion()
                ui.page_title("Done — LocalScribe")
            else:
                render_progress(done, total, pct)
                ui.page_title(f"{pct}% — Transcribing…")

        def render_progress(done: float, total: float, pct: int) -> None:
            with ui.card().classes("w-full"):
                if job.phase == "downloading":
                    mb_done = job.download_done // 1_000_000
                    mb_total = job.download_total // 1_000_000
                    ui.label(f"Downloading speech model — {mb_done} MB of "
                             f"{mb_total} MB (one time only)…")
                    ui.linear_progress(
                        value=(job.download_done / job.download_total)
                        if job.download_total else 0, show_value=False)
                elif job.phase == "paused_disk_full":
                    ui.label("Your disk is full — free some space, then press "
                             "Resume.").classes("text-negative text-lg")
                    ui.button("Resume", on_click=job.resume_event.set) \
                        .props("color=primary")
                else:
                    running = [fs for fs in job.files if fs.status == "running"]
                    name = running[0].task.path.name if running else ""
                    n_active = sum(1 for fs in job.files if fs.status != "skipped")
                    n_done = sum(1 for fs in job.files
                                 if fs.status in ("done", "failed"))
                    ui.label(f"File {min(n_done + 1, n_active)} of {n_active} — {name}")
                    ui.linear_progress(value=done / total if total else 0,
                                       show_value=False)
                    import time as _time
                    eta = eta_text(done, _time.monotonic() - (job.started_at or 0),
                                   total) if job.started_at else None
                    ui.label(eta or "Estimating time remaining…") \
                        .classes("text-sm text-gray-500")
                    ui.button("Stop after current file",
                              on_click=lambda: setattr(job, "cancel_requested", True)) \
                        .props("flat color=negative")
                render_file_rows()

        def render_file_rows() -> None:
            for fs in job.files:
                with ui.row().classes("w-full items-center gap-2"):
                    ui.icon(STATUS_ICONS[fs.status],
                            color=STATUS_COLORS[fs.status])
                    ui.label(fs.task.path.name).classes("grow font-mono text-sm")
                    if fs.status == "running":
                        ui.linear_progress(value=fs.progress, show_value=False) \
                            .classes("w-32")
                    elif fs.status == "done" and fs.elapsed:
                        ui.label(f"{fs.elapsed:.0f}s").classes("text-xs text-gray-500")
                    elif fs.status == "failed":
                        ui.label(fs.error or "failed") \
                            .classes("text-xs text-negative")

        def render_completion() -> None:
            n_done = sum(1 for fs in job.files if fs.status == "done")
            n_failed = sum(1 for fs in job.files if fs.status == "failed")
            n_skipped = sum(1 for fs in job.files if fs.status == "skipped")
            with ui.card().classes("w-full"):
                if job.error_message:
                    ui.label("Could not start the transcription.") \
                        .classes("text-lg text-negative")
                    ui.label(job.error_message).classes("text-sm")
                    ui.button("Retry", on_click=lambda: (retry_job(), body.refresh())) \
                        .props("color=primary")
                else:
                    color = "text-positive" if n_failed == 0 else "text-warning"
                    summary = f"{n_done} of {n_done + n_failed} files transcribed."
                    if n_failed:
                        summary += f" {n_failed} failed."
                    if n_skipped:
                        summary += f" {n_skipped} skipped (already done)."
                    if job.message:
                        summary += f" {job.message}"
                    ui.label(summary).classes(f"text-lg {color}")
                render_file_rows()
                with ui.row():
                    if job.folder:
                        ui.button("Open output folder",
                                  on_click=lambda: open_folder(job.folder / "transcripts"))
                    ui.button("Transcribe another folder",
                              on_click=lambda: (reset_to_setup(), body.refresh())) \
                        .props("flat")

        body()
        ui.timer(0.5, body.refresh)

        with ui.row().classes("w-full justify-between text-xs text-gray-400 mt-8"):
            managed = Path(__file__).resolve().parent.parent / ".managed"
            ui.label(f"Problems? Send us the log file: {managed / 'logs' / 'app.log'}")
            ui.button("Quit LocalScribe", on_click=nicegui_app.shutdown).props("flat dense")
```

- [ ] **Step 4: Run tests — the ETA helper and that the module imports cleanly**

Run: `uv run pytest tests/test_ui.py -v && uv run python -c "import app.ui; print('imports ok')"`
Expected: 2 passed, then `imports ok`

- [ ] **Step 5: Commit**

```bash
git add app/ui.py tests/test_ui.py
git commit -m "feat: single-page web UI with setup, progress, and completion states

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 11: Entrypoint — single instance, port probe, ui.run

**Files:**
- Create: `app/main.py`
- Test: `tests/test_main.py`

**Interfaces:**
- Consumes: `setup_logging` (Task 5); importing `app.ui` (Task 10) registers the page.
- Produces: `python -m app.main` starts the app. `find_free_port(start=8377) -> int`; `existing_instance_port(lock_path: Path) -> int | None` (reads port from lock file, returns it only if something is listening — i.e. a live instance); `main()`.

- [ ] **Step 1: Write the failing tests**

`tests/test_main.py`:
```python
import socket

from app.main import existing_instance_port, find_free_port


def test_find_free_port_skips_occupied():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        s.listen(1)
        occupied = s.getsockname()[1]
        assert find_free_port(start=occupied) == occupied + 1


def test_existing_instance_detected(tmp_path):
    lock = tmp_path / "app.lock"
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        s.listen(1)
        port = s.getsockname()[1]
        lock.write_text(str(port))
        assert existing_instance_port(lock) == port
    # socket closed -> stale lock -> no instance
    assert existing_instance_port(lock) is None


def test_existing_instance_bad_lockfile(tmp_path):
    lock = tmp_path / "app.lock"
    assert existing_instance_port(lock) is None      # missing file
    lock.write_text("not-a-port")
    assert existing_instance_port(lock) is None      # garbage content
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_main.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.main'`

- [ ] **Step 3: Implement**

`app/main.py`:
```python
"""Entrypoint: single-instance guard, port probing, logging, ui.run."""
import socket
import webbrowser
from pathlib import Path

MANAGED_DIR = Path(__file__).resolve().parent.parent / ".managed"
LOCK_PATH = MANAGED_DIR / "app.lock"


def _port_in_use(port: int) -> bool:
    with socket.socket() as s:
        s.settimeout(0.5)
        return s.connect_ex(("127.0.0.1", port)) == 0


def find_free_port(start: int = 8377) -> int:
    port = start
    while _port_in_use(port):
        port += 1
    return port


def existing_instance_port(lock_path: Path = LOCK_PATH) -> int | None:
    if not lock_path.exists():
        return None
    try:
        port = int(lock_path.read_text(encoding="utf-8").strip())
    except (ValueError, OSError):
        return None
    return port if _port_in_use(port) else None


def main() -> None:
    existing = existing_instance_port()
    if existing is not None:
        # Second double-click: just reopen the running app's page.
        webbrowser.open(f"http://127.0.0.1:{existing}")
        return

    from app.diagnostics import setup_logging
    logger = setup_logging(MANAGED_DIR)

    port = find_free_port()
    LOCK_PATH.parent.mkdir(parents=True, exist_ok=True)
    LOCK_PATH.write_text(str(port), encoding="utf-8")
    logger.info("starting on 127.0.0.1:%s", port)

    import app.ui  # noqa: F401  (registers the / page)
    from nicegui import ui
    ui.run(host="127.0.0.1", port=port, reload=False, show=True,
           title="LocalScribe", favicon="🎙️")


if __name__ in {"__main__", "__mp_main__"}:
    main()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_main.py -v`
Expected: 3 passed

- [ ] **Step 5: Manual smoke test (dev machine)**

Run: `uv run python -m app.main`
Expected: browser opens `http://127.0.0.1:8377` showing the setup card. Browse to a folder — scan summary appears. Press Quit — app exits. Run again while one instance is open (second terminal): the second process just reopens the browser tab and exits.

- [ ] **Step 6: Commit**

```bash
git add app/main.py tests/test_main.py
git commit -m "feat: entrypoint with single-instance guard and port probing

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 12: Double-click launchers

**Files:**
- Create: `Start Transcriber.command` (LF line endings, git mode 100755), `Start Transcriber.bat` (CRLF line endings)

**Interfaces:**
- Consumes: `pyproject.toml`/`uv.lock` (Task 1), `app/main.py` (Task 11).
- Produces: the two user-facing entrypoints. Contract: idempotent; every failure prints a plain-language message naming `bootstrap.log` and the "delete .managed" factory reset, and pauses so the window never vanishes.

- [ ] **Step 1: Write the macOS launcher**

`Start Transcriber.command`:
```bash
#!/bin/bash
# LocalScribe launcher — double-click me. Everything installs into ./.managed
cd "$(dirname "$0")" || exit 1
DIR="$(pwd)"

mkdir -p "$DIR/.managed/logs"   # must exist BEFORE the tee below
exec > >(tee -a "$DIR/.managed/logs/bootstrap.log") 2>&1

echo "Starting LocalScribe — leave this window open while you transcribe."

export UV_PYTHON_INSTALL_DIR="$DIR/.managed/python"
export UV_CACHE_DIR="$DIR/.managed/uv-cache"
export HF_HOME="$DIR/.managed/hf-cache"

UV="$DIR/.managed/uv/uv"

fail() {
    echo ""
    echo "$1"
    echo "The universal fix: delete the .managed folder inside this folder, then double-click again."
    echo "(Technical details were saved to .managed/logs/bootstrap.log)"
    read -r -p "Press Return to close this window."
    exit 1
}

if ! "$UV" --version >/dev/null 2>&1; then
    rm -rf "$DIR/.managed/uv"
    echo "One-time setup: downloading the setup tool..."
    curl -LsSf https://astral.sh/uv/0.11.28/install.sh \
        | env UV_UNMANAGED_INSTALL="$DIR/.managed/uv" INSTALLER_NO_MODIFY_PATH=1 sh \
        || fail "Could not download the setup tool — check your internet connection (a university proxy may be blocking astral.sh), then double-click again."
    "$UV" --version >/dev/null 2>&1 \
        || fail "The setup tool did not install correctly — check your internet connection, then double-click again."
fi

"$UV" run --project "$DIR" --frozen python -m app.main \
    || fail "LocalScribe could not start."
```

- [ ] **Step 2: Write the Windows launcher**

`Start Transcriber.bat`:
```bat
@echo off
setlocal
rem LocalScribe launcher - double-click me. Everything installs into .managed
cd /d "%~dp0"
set "DIR=%~dp0"

if not exist "%DIR%.managed\logs" mkdir "%DIR%.managed\logs"

echo Starting LocalScribe - leave this window open while you transcribe.

set "UV_PYTHON_INSTALL_DIR=%DIR%.managed\python"
set "UV_CACHE_DIR=%DIR%.managed\uv-cache"
set "HF_HOME=%DIR%.managed\hf-cache"
set "UV=%DIR%.managed\uv\uv.exe"

"%UV%" --version >nul 2>&1
if not errorlevel 1 goto run

if exist "%DIR%.managed\uv" rmdir /s /q "%DIR%.managed\uv"
echo One-time setup: downloading the setup tool...
powershell -NoProfile -ExecutionPolicy Bypass -Command "$env:UV_UNMANAGED_INSTALL='%DIR%.managed\uv'; irm https://astral.sh/uv/0.11.28/install.ps1 | iex" >>"%DIR%.managed\logs\bootstrap.log" 2>&1
"%UV%" --version >nul 2>&1
if not errorlevel 1 goto run

echo The usual route failed - trying the built-in downloader...
set "UVARCH=x86_64"
if /i "%PROCESSOR_ARCHITECTURE%"=="ARM64" set "UVARCH=aarch64"
if not exist "%DIR%.managed\uv" mkdir "%DIR%.managed\uv"
curl.exe -L -o "%TEMP%\uv.zip" "https://github.com/astral-sh/uv/releases/download/0.11.28/uv-%UVARCH%-pc-windows-msvc.zip" >>"%DIR%.managed\logs\bootstrap.log" 2>&1
tar -xf "%TEMP%\uv.zip" -C "%DIR%.managed\uv" >>"%DIR%.managed\logs\bootstrap.log" 2>&1
"%UV%" --version >nul 2>&1
if errorlevel 1 goto fail

:run
"%UV%" run --project "%DIR%." --frozen python -m app.main
if errorlevel 1 goto fail
exit /b 0

:fail
echo.
echo Something went wrong - check your internet connection and try again.
echo The universal fix: delete the .managed folder inside this folder, then double-click again.
echo (Technical details: .managed\logs\bootstrap.log)
pause
exit /b 1
```

- [ ] **Step 3: Set the executable bit and verify both files**

Run:
```bash
chmod +x "Start Transcriber.command"
bash -n "Start Transcriber.command" && echo "bash syntax ok"
git add "Start Transcriber.command" "Start Transcriber.bat"
git ls-files --stage | grep "Start Transcriber"
```
Expected: `bash syntax ok`; the `.command` line shows mode `100755`, the `.bat` shows `100644`.

- [ ] **Step 4: Manual smoke test (dev Mac)**

Run: `rm -rf .managed && open "Start Transcriber.command"` (or double-click it in Finder)
Expected: Terminal window opens, downloads uv + Python + deps on first run (~300 MB), then the browser opens the app. Second double-click while running: browser tab reopens, no second server. `cat .managed/logs/bootstrap.log` shows the captured output.

- [ ] **Step 5: Commit**

```bash
git commit -m "feat: double-click self-bootstrapping launchers for macOS and Windows

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 13: Integration smoke test (slow, real model)

**Files:**
- Test: `tests/test_integration.py`

**Interfaces:**
- Consumes: real `app.engine` + `app.worker` + `app.state` + `app.discovery`.
- Produces: confidence that the real pipeline (PyAV decode → faster-whisper tiny → writers) runs end-to-end. Excluded from default runs by the `slow` marker.

- [ ] **Step 1: Write the test**

`tests/test_integration.py`:
```python
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
    for ext in (".srt", ".vtt", ".csv", ".json"):
        assert (tmp_path / "transcripts" / f"tone.wav{ext}").exists()
    assert manifest.should_skip(scan.tasks[0], mode, "tiny")
```

- [ ] **Step 2: Verify it is excluded by default**

Run: `uv run pytest --collect-only -q | tail -3`
Expected: integration tests listed as deselected (the `-m 'not slow'` addopts).

- [ ] **Step 3: Run it for real (needs internet, ~75 MB one-time download)**

Run: `uv run pytest -m slow -v`
Expected: 2 passed (may take a couple of minutes on first run).

- [ ] **Step 4: Commit**

```bash
git add tests/test_integration.py
git commit -m "test: end-to-end pipeline smoke test with real tiny model

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 14: User docs and final verification

**Files:**
- Create: `README.md`, `docs/TROUBLESHOOTING.md`, `docs/screenshots/` (directory, populated manually later)
- Modify: `CLAUDE.md` (replace the "Current State" section)

**Interfaces:**
- Consumes: everything — this task verifies the whole build.

- [ ] **Step 1: Write README.md**

`README.md`:
```markdown
# LocalScribe — transcribe your recordings on your own computer

LocalScribe turns a folder of audio or video recordings into transcripts
(subtitles and spreadsheets), **entirely on your own computer**. Nothing is
uploaded anywhere. No accounts, no sign-ups.

## What you need

- A Windows 10/11 or Mac computer (no special hardware).
- Internet **for the first run only** (it downloads its own tools, about 1 GB
  total). After that it works offline.
- About 2 GB of free disk space.
- Tip: put this folder somewhere that is **not** synced by OneDrive/Dropbox.

## Setting up (one time, about 5–10 minutes)

1. Download this folder: click the green **Code** button on this page →
   **Download ZIP**, then unzip it. (If you know git: `git clone` works too
   and avoids one security prompt.)
2. Open the unzipped folder.
3. **On a Mac:** double-click **`Start Transcriber.command`**.
   The first time, macOS may say it "cannot verify the developer":
   open **System Settings → Privacy & Security**, scroll down, and click
   **Open Anyway**. (Screenshots in `docs/screenshots/`.)
   **On Windows:** double-click **`Start Transcriber.bat`**.
   If a blue "Windows protected your PC" box appears, click
   **More info → Run anyway**.
4. A black text window opens and sets things up (first time only — a few
   minutes). **Leave that window open.** Your web browser then opens the
   LocalScribe page automatically.

## Using it

1. Click **Browse…** and choose the folder with your recordings.
2. Pick how to transcribe:
   - **Non-verbatim** (recommended): cleaned-up text, easiest to read.
   - **Verbatim**: keeps "um", "uh", repetitions and false starts — useful for
     detailed analysis. (It keeps many more hesitations than normal, but no
     software can capture every single one.)
3. Pick accuracy vs speed (**Standard** is right for almost everyone).
4. Click **Start transcription** and leave the laptop plugged in with the lid
   open. You can close the browser tab and come back — the work continues.

When it finishes, click **Open output folder**. For each recording you get:

| File | What it is |
|---|---|
| `recording.mp3.srt` / `.vtt` | Subtitle files (timestamps + text) |
| `recording.mp3.csv` | Spreadsheet — opens in Excel, one row per sentence with times |
| `recording.mp3.json` | Full detail including word-level timestamps |

Already-transcribed files are skipped automatically if you run the same
folder again — so it is always safe to re-run.

## Something not working?

See [docs/TROUBLESHOOTING.md](docs/TROUBLESHOOTING.md). The universal fix:
**delete the `.managed` folder inside this folder, then double-click the
launcher again.**
```

- [ ] **Step 2: Write docs/TROUBLESHOOTING.md**

`docs/TROUBLESHOOTING.md`:
```markdown
# Troubleshooting

**The universal fix for almost everything:** close the black text window,
delete the `.managed` folder inside the LocalScribe folder, and double-click
the launcher again. Setup re-runs from scratch and resumes any finished work.

## "Nothing happened" when I double-clicked

- A LocalScribe browser tab may already be open — double-clicking again just
  reopens the existing page. Check your browser tabs.
- **Mac:** if you saw a security warning, go to System Settings → Privacy &
  Security → click **Open Anyway**, then double-click again. If that option
  never appears, drag `Start Transcriber.command` onto the Terminal app icon
  and press Return.
- **Windows:** click **More info → Run anyway** on the blue SmartScreen box.
  If nothing appears at all, right-click the `.bat` file → Properties → tick
  **Unblock** → OK, then try again.

## "Could not download the setup tool" / "Could not download the speech model"

The first run needs internet access to `astral.sh`, `github.com`, and
`huggingface.co`. University networks sometimes block these:
- Try again on a different network (home Wi-Fi or a phone hotspot). This is a
  **one-time** download; afterwards LocalScribe works offline.
- Downloads resume where they left off — just double-click again.

## It seems stuck / is it frozen?

Transcription on an ordinary laptop takes roughly as long as the recording
itself (Standard model). Watch the progress bar and the time estimate; the
browser tab title also shows progress. Keep the laptop plugged in with the
lid open.

## One file failed but the others worked

The file is probably damaged or in an unusual format. The page shows a
plain-language reason per file. Everything else still completes.

## My antivirus complained

The setup tool (`uv.exe`) is a well-known open-source program from
astral.sh. If your antivirus quarantined it, restore it or just delete
`.managed` and re-run — setup detects the damage and re-downloads.

## Where are the logs? (for emailing support)

`.managed/logs/bootstrap.log` (setup) and `.managed/logs/app.log` (the app).
The page footer shows the exact path.
```

- [ ] **Step 3: Update CLAUDE.md "Current State" section**

Replace the `## Current State` section body with:
```markdown
Implemented. Common commands:

- Run all tests: `uv run pytest`
- Run one test: `uv run pytest tests/test_worker.py::test_failure_is_isolated -v`
- Slow integration tests (downloads real tiny model): `uv run pytest -m slow`
- Run the app (dev): `uv run python -m app.main`
- End users launch via `Start Transcriber.command` / `Start Transcriber.bat`
- After changing deps in pyproject.toml: `uv lock && uv sync` (never edit uv.lock by hand)

Architecture: launchers bootstrap uv/Python/deps into gitignored `.managed/`;
`app/main.py` (single-instance, port probe) → `app/ui.py` (NiceGUI page, JobState
polling) → `app/worker.py` (one thread, per-file isolation) → `app/engine.py`
(faster-whisper sequential API, verbatim = initial_prompt + hotwords) →
`app/writers.py` (atomic srt/vtt/csv/json). Resume manifest: `app/state.py` →
`<folder>/transcripts/.localscribe/state.json`.
```

- [ ] **Step 4: Full verification**

Run: `uv run pytest -v && bash -n "Start Transcriber.command" && git ls-files --stage | grep command`
Expected: all tests pass (slow ones deselected), bash syntax ok, mode 100755.

Then the manual checklist (record results honestly; screenshots for README go in `docs/screenshots/` as they are taken):
1. Fresh-clone smoke on the dev Mac: clone to a temp dir, double-click launcher, transcribe a folder with 2 real recordings in both modes, verify 4 outputs each, re-run and confirm skip behavior.
2. On a Windows machine (or VM): same pass, plus SmartScreen prompt screenshot.
3. Verify "Stop after current file", Quit button, and second-double-click behavior.

- [ ] **Step 5: Commit**

```bash
git add README.md docs/TROUBLESHOOTING.md CLAUDE.md
git commit -m "docs: plain-language user guide and troubleshooting

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```
