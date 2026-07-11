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
