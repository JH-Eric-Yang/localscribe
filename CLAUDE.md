# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Purpose

LocalScribe: a simple, easy-to-set-up local web app for batch audio/video transcription, aimed at **non-technical users** on both **Windows and macOS**. Users pick a folder, choose Verbatim or Non-verbatim mode, and every media file in the folder is transcribed to .srt/.vtt/.csv/.json.

The full approved design is in `docs/superpowers/specs/2026-07-11-localscribe-design.md` — read it before making architectural changes. (The `docs/` folder is git-ignored and exists only on the original development machine; it is not in the public repository.)

## Current State

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

## Design Constraints

- **Audience is non-technical**: everyday use must not require the command line, Python knowledge, or manual dependency management. Setup is: `git clone` → double-click `Start Transcriber.command`/`.bat` → browser opens. The launchers self-bootstrap uv, a pinned CPython 3.12, and locked dependencies into a gitignored `.managed/` directory — no Python, no ffmpeg, no admin rights assumed on the user's machine.
- **Cross-platform**: everything must work on Windows 10/11 and macOS (Intel + Apple Silicon), CPU-only.
- **Engine is faster-whisper, NOT the `whisperx` package** (decided with the user 2026-07-11): whisperx requires system ffmpeg twice over (CLI + shared libs for torchcodec) and ~3 GB of torch/pyannote — incompatible with the no-admin setup. faster-whisper is whisperx's internal engine (identical quality) and decodes media via PyAV's bundled FFmpeg.
- **Verbatim mode is load-bearing**: it relies on passing a filler-dense prompt as both `initial_prompt` and `hotwords` with `condition_on_previous_text=False` so faster-whisper injects it into every 30-s window. Both modes must use the sequential API — the batched pipeline silently drops the temperature-fallback ladder.
- **No accounts/tokens ever**: models come from ungated Systran HuggingFace repos; no diarization.
