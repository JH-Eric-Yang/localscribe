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
        self.device_notice: str | None = None


class Manifest:
    """Maps input filename -> completion record in <folder>/transcripts/.localscribe/state.json."""

    def __init__(self, folder: Path):
        self.path = folder / "transcripts" / ".localscribe" / "state.json"
        self.data: dict = {}
        if self.path.exists():
            try:
                loaded = json.loads(self.path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                loaded = {}
            self.data = loaded if isinstance(loaded, dict) else {}

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
        outputs = entry.get("outputs") or []
        transcripts_dir = self.path.parent.parent
        return bool(outputs) and all((transcripts_dir / name).exists() for name in outputs)

    def _record(self, task: FileTask, mode: str, model: str, **extra) -> None:
        self.data[task.path.name] = {
            "size": task.size, "mtime": task.mtime, "mode": mode, "model": model,
            "finished_at": datetime.now(timezone.utc).isoformat(), **extra,
        }
        self.save()

    def mark_done(self, task: FileTask, mode: str, model: str, outputs: list[Path]) -> None:
        # Store filenames only (resolved against transcripts/ at read time) so
        # moving or renaming the parent folder doesn't void resume state.
        self._record(task, mode, model, status="done",
                     outputs=[p.name for p in outputs], error=None)

    def mark_failed(self, task: FileTask, mode: str, model: str, error: str) -> None:
        self._record(task, mode, model, status="failed", outputs=[], error=error)
