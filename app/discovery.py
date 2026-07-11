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
