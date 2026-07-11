import csv
import io
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


def test_to_csv_escapes_commas_quotes_and_newlines():
    tricky = [{"id": 1, "start": 0.0, "end": 1.0,
               "text": ' He said, "wait...\nno".', "words": []}]
    out = to_csv(tricky)
    rows = list(csv.reader(io.StringIO(out)))
    assert rows[0] == ["segment", "start_seconds", "end_seconds",
                       "start_timecode", "end_timecode", "text"]
    assert rows[1][5] == 'He said, "wait...\nno".'
    # The tricky field must be quoted with doubled quotes in the raw output.
    assert '"He said, ""wait...\nno""."' in out


def test_empty_segments():
    assert to_srt([]) == ""
    assert to_vtt([]).startswith("WEBVTT")
    csv_lines = to_csv([]).splitlines()
    assert csv_lines == ["segment,start_seconds,end_seconds,start_timecode,end_timecode,text"]


def test_write_outputs_empty_segments(tmp_path):
    paths = write_outputs(tmp_path / "transcripts", "a.mp3", [], META)
    assert sorted(p.name for p in paths) == ["a.mp3.csv", "a.mp3.json", "a.mp3.srt", "a.mp3.vtt"]
    assert all(p.exists() for p in paths)
    data = json.loads((tmp_path / "transcripts" / "a.mp3.json").read_text(encoding="utf-8"))
    assert data["segments"] == []


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
