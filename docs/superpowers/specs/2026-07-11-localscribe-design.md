# LocalScribe — Design Spec

**Date:** 2026-07-11
**Status:** Approved by user (engine choice, model selector, and overall design confirmed)

## What this is

A git-cloneable folder that lets a non-technical university researcher batch-transcribe every audio/video file in a folder of their choosing, locally and offline (after first run), on Windows 10/11 and macOS (Intel + Apple Silicon), with a choice of **Verbatim** (keeps um/uh, repetitions, false starts) or **Non-verbatim** (clean, default) transcription. Setup is: clone → double-click one file → browser page opens.

## Decisions made with the user

| Decision | Choice | Why |
|---|---|---|
| Engine | **faster-whisper 1.2.1**, not the `whisperx` package | `whisperx` 3.8.6 hard-requires an ffmpeg executable on PATH *and* FFmpeg shared libs (torchcodec), plus ~3 GB of torch/pyannote — irreconcilable with "no ffmpeg, no admin rights". faster-whisper is WhisperX's internal engine (identical models/quality), ~300 MB, decodes audio *and* video via PyAV's bundled FFmpeg. Loses only wav2vec2 forced alignment; native `word_timestamps=True` is adequate for srt/vtt/csv. |
| Model choice | **Selector: base / small / medium**, default **small** (int8) | User explicitly chose flexibility over a fixed model. UI labels: "Faster – less accurate" / "Standard – recommended" / "Most accurate – much slower (1.5 GB download)". |
| Interface | Local web page (NiceGUI) at `http://127.0.0.1:8377` | Chosen by user over a native window. |
| Outputs | `.srt`, `.vtt`, `.csv`, `.json` per input file | Chosen by user (no .txt/.docx). |
| Diarization | None | No HuggingFace account/token ever required. |
| Hardware target | Ordinary laptops, CPU-only | ctranslate2 int8 on AVX/oneDNN (x86) and NEON/Accelerate (Apple Silicon). No CUDA/MPS path. |

## Stack

- **faster-whisper==1.2.1** (Python >=3.9; deps: ctranslate2<5, tokenizers<1, onnxruntime<2, av>=11 — verified wheels for win_amd64, macosx_arm64, macosx_x86_64 on Python 3.12). PyAV bundles FFmpeg: zero system ffmpeg, video containers supported.
- **CPython 3.12**, pinned in `.python-version`, auto-downloaded by uv.
- **uv 0.11.28** (version-pinned installer URL), installed into repo-local `.managed/uv` via `UV_UNMANAGED_INSTALL` — no admin, no PATH edits. `uv run --frozen` syncs `uv.lock` and launches.
- **nicegui>=3.14,<4** for the UI (single pure-Python wheel; auto-opens browser; websocket updates). Folder picking via a vendored, directories-only adaptation of NiceGUI's `local_file_picker` example. Gradio rejected (heavy pinned deps, buggy FileExplorer); tkinter dialogs rejected (crashes off-main-thread on macOS).
- **huggingface_hub.snapshot_download** (already a dep) for model downloads from ungated `Systran/faster-whisper-*` repos — resume-capable, no token.
- Everything else is stdlib: `threading`, `json`, `csv`, `logging`, `pathlib`, `os.replace`.

## Setup flow

### macOS — `Start Transcriber.command` (committed with mode 100755)
1. `cd` to its own directory; `mkdir -p .managed/logs` **before** `exec > >(tee -a .managed/logs/bootstrap.log) 2>&1` (tee target must exist on first run).
2. Export self-containment vars: `UV_PYTHON_INSTALL_DIR=$DIR/.managed/python`, `UV_CACHE_DIR=$DIR/.managed/uv-cache`, `HF_HOME=$DIR/.managed/hf-cache`.
3. Health-check uv: if `.managed/uv/uv --version` fails (missing/corrupt/AV-mangled), `rm -rf` it and reinstall from the **version-pinned** URL `https://astral.sh/uv/0.11.28/install.sh` with `UV_UNMANAGED_INSTALL` + `INSTALLER_NO_MODIFY_PATH=1`. On failure: plain-language message naming internet/proxy as likely cause, `read -p` pause so the window never vanishes.
4. `uv run --project "$DIR" --frozen python -m app.main`.
5. Never `set -e` without a friendly trap: every failure path prints a message pointing at `bootstrap.log` and pauses.

### Windows — `Start Transcriber.bat`
Same sequence in cmd. Specifics:
- `.bat` is not subject to PowerShell execution policy. uv install first tries `powershell -NoProfile -ExecutionPolicy Bypass -Command "irm .../0.11.28/install.ps1 | iex"`; if PowerShell is GPO-blocked, **pure-cmd fallback**: `curl.exe` + `tar` (both ship with Win10 1803+) fetching the uv release zip, selecting `aarch64` vs `x86_64` from `%PROCESSOR_ARCHITECTURE%`, with `mkdir` of the target dir **before** `tar -xf ... -C`.
- On any non-zero exit: `echo` plain-language message + `pause`.

### Both platforms
- App probes port 8377 (increments if taken), writes `.managed/app.lock` (PID+port); a second double-click detects the live instance and just reopens the browser to it. Binds `127.0.0.1` only (no firewall prompt). `ui.run(reload=False, show=True)`.
- Model download does **not** block startup — it runs in the worker with visible progress on first Start.
- `.gitattributes` pins `*.bat text eol=crlf` and `*.command text eol=lf` (a CRLF shebang = "bad interpreter" is the most opaque possible first-run failure).
- Idempotency is the universal recovery: **"delete `.managed` and double-click again"** is the documented factory reset, echoed in launcher failure messages.
- README documents the one scary OS prompt per platform with screenshots: Gatekeeper "Open Anyway" (+ drag-into-Terminal fallback) on macOS; MOTW "More info → Run anyway" / Properties→Unblock on Windows.

## UI flow

Single page, three states, all rendered from a **server-side `JobState`** polled by `ui.timer(0.5)` — closing/refreshing the tab or laptop sleep loses nothing; reopening the URL shows current truth.

1. **Setup card:** folder Browse… (vendored directory picker; expandable "type/paste a path" input for network drives) → scan summary ("Found 14 audio/video files, 3 already transcribed — will be skipped, 2 other files ignored") with a "Re-do already transcribed files" checkbox (default off; when on, warn "Existing transcripts for 3 files will be replaced") → mode radio (Non-verbatim recommended / Verbatim, one-line captions; Verbatim caption: "keeps many more hesitations, but no software can capture every single one") → model select (base/small/medium, default small, helper text about the one-time download size) → Start (disabled until ≥1 pending file).
2. **Progress:** overall bar + "File 3 of 14 — interview_02.mp3"; honest ETA from rolling measured realtime factor (shown only after ~30 s calibration, phrased "about N minutes left"); progress mirrored in the browser tab title ("37% – Transcribing…"); model-download row with byte progress and an explicit **Retry** button on failure (message names university Wi-Fi/proxies); per-file rows (queued/spinner/done/skip/error icons, per-file progress = last segment end ÷ PyAV duration, plain-language failure reason with log-excerpt expansion). Cancel button is honest: "Stop after current file". Footer: log-file path + Quit button (`app.shutdown()`).
3. **Completion card:** "13 of 14 files transcribed, 1 failed, 3 skipped." Buttons: Open output folder (`open`/`explorer`), Transcribe another folder, Open log file (on failure). Persists in JobState for overnight users.

**Keep-awake during jobs:** `caffeinate -i -w <pid>` subprocess on macOS; `ctypes` `SetThreadExecutionState(ES_CONTINUOUS | ES_SYSTEM_REQUIRED)` on Windows. Complements (not replaces) the resume manifest. Helper text: "keep the laptop plugged in and the lid open".

## Transcription pipeline

- **Discovery:** non-recursive scan of chosen folder; extension whitelist (mp3 wav m4a aac flac ogg oga opus wma aiff aif mpga mp4 mov m4v avi mkv webm wmv mpg mpeg 3gp); skip hidden/zero-byte files and the `transcripts/` dir; cheap `av.open()` probe flags unreadable files at scan time ("unsupported or damaged — skipped") instead of mid-batch.
- **Resume manifest:** `<chosen>/transcripts/.localscribe/state.json` maps input → {size, mtime, mode, model, status, outputs, error, finished_at}. Skip iff done + size/mtime match + mode/model match + all four outputs exist. Rewritten atomically after every file → a crash costs at most the in-flight file. Mode or model changed → those files re-run by design.
- **Worker:** one `threading.Thread` (ctranslate2 releases the GIL; multiprocessing deliberately avoided). Ensure model via `snapshot_download` (custom tqdm → UI progress; 3 retries with backoff; resumes partial downloads). Load `WhisperModel(size, device='cpu', compute_type='int8', cpu_threads=cpu_count-1)`; log the *effective* compute type (ctranslate2 falls back silently). Per-file try/except isolation: decode error → "file appears damaged or unsupported"; `OSError` errno 28 → **pause the whole job** with "Your disk is full — free some space, then press Resume"; `MemoryError` → "file too large for this computer's memory"; else generic + log pointer. Batch always continues past a failed file.
- **Engine parameters** (sequential API only — the batched pipeline runs only `temperatures[0]` with no fallback ladder, verified in source; both modes keep the full anti-hallucination guards):
  - **Non-verbatim (default):** `beam_size=5, temperature=[0.0,0.2,0.4,0.6,0.8,1.0], initial_prompt=None, condition_on_previous_text=False, vad_filter=True, vad_parameters={'min_silence_duration_ms': 500}, no_speech_threshold=0.6, log_prob_threshold=-1.0, compression_ratio_threshold=2.4, word_timestamps=True`. **No filler post-filter** — two judges flagged post-filtering as a content-altering liability in the default path; Whisper's trained-in cleaning suffices.
  - **Verbatim:** `VERBATIM_PROMPT` = filler-dense text ("Mm-hmm. Uh, yeah, so, um, I was- I was thinking, like, you know, it's... it's kind of, uh, hard to say. …", <224 tokens, `.strip()`ed) passed as **both `initial_prompt` and `hotwords`**. With `condition_on_previous_text=False`, faster-whisper injects `hotwords` into *every* 30-s window (source-verified: `if hotwords and not prefix` in `get_prompt`), so the verbatim bias never fades on long recordings. `vad_filter=True` but **loosened** (`min_silence_duration_ms=2000, speech_pad_ms=400`) to keep hesitation pauses without the open hallucination surface of VAD-off. Same guard ladder as non-verbatim. `suppress_tokens` stays `[-1]` (emptying it unlocks symbol noise, not fillers).
  - Both modes stream the segment generator, updating per-file progress per segment.
  - **Build-time verification step:** confirm the hotwords-per-window behavior against the installed faster-whisper `transcribe.py` before relying on it; fallback if ineffective: `condition_on_previous_text=True` + `hallucination_silence_threshold`.

## Outputs

To `<chosen>/transcripts/`, named `<original name with extension>.<fmt>` (`interview.mp3.srt` — collision-proof vs `interview.mp4`). Every file written to `<name>.partial` then `os.replace()` (atomic on both OSes).

- `.srt` — standard, `HH:MM:SS,mmm`, UTF-8.
- `.vtt` — `WEBVTT` header, `HH:MM:SS.mmm`.
- `.csv` — UTF-8 **with BOM** (Excel-friendly): `segment,start_seconds,end_seconds,start_timecode,end_timecode,text`.
- `.json` — {source_file, duration_seconds, language, language_probability, mode, model_size, app_version, created_utc, segments:[{id,start,end,text,words:[{word,start,end,probability}]}]}.

## Diagnostics

All logs in **one place**: `.managed/logs/` (`bootstrap.log`, `app.log` with rotation) — "send me the log file" needs no explanation of which one. Run header logs OS, arch, Python, package versions, effective compute type, cpu_threads, chosen settings. UI error rows link to the exact path. (The per-folder `.localscribe/` dir holds only `state.json`, not logs.)

## Repo layout

```
Auto_Transcription/
├── Start Transcriber.command   # macOS launcher, mode 100755
├── Start Transcriber.bat       # Windows launcher
├── pyproject.toml              # faster-whisper==1.2.1, nicegui>=3.14,<4
├── uv.lock                     # fully pinned resolution
├── .python-version             # 3.12
├── .gitattributes              # *.bat crlf, *.command lf
├── .gitignore                  # .managed/, __pycache__
├── README.md                   # plain-language 3-step guide per OS, screenshots
├── docs/
│   ├── screenshots/
│   ├── TROUBLESHOOTING.md      # proxy, antivirus, "nothing opened", factory reset
│   └── superpowers/specs/      # this spec
└── app/
    ├── main.py                 # single-instance lock, port probe, ui.run
    ├── ui.py                   # page + JobState rendering + keep-awake
    ├── folder_picker.py        # vendored directory picker
    ├── discovery.py            # whitelist scan + PyAV probe
    ├── engine.py               # WhisperModel wrapper, mode presets, model download
    ├── worker.py               # worker thread, per-file isolation, cancel flag
    ├── state.py                # JobState + state.json manifest
    ├── writers.py              # srt/vtt/csv/json, atomic writes
    └── diagnostics.py          # logging, env report, error categorization
```

## Error handling summary

Per-file isolation (batch survives bad files); job-level pause on disk-full; retries+resume on all downloads; self-healing uv bootstrap; single-instance guard; atomic writes everywhere (outputs + manifest); every failure path ends in a plain-language message plus a pause or a log pointer — never a vanished window.

## Testing

- **Unit tests** (run via `uv run pytest`): writers (srt/vtt/csv/json golden files, atomicity), discovery (whitelist, hidden/zero-byte/probe-fail cases), state manifest skip logic (size/mtime/mode/model/outputs-exist matrix), error categorization.
- **Engine smoke test** with a tiny committed fixture (~10 s WAV): both modes produce four outputs; verbatim vs non-verbatim parameters actually differ in the call.
- **Build-time source check:** assert the installed faster-whisper injects hotwords per-window (grep/inspect `get_prompt`), so a future upgrade can't silently break Verbatim.
- **Manual platform pass** (documented checklist): fresh clone on a clean Mac and Windows machine — double-click, first-run download, batch run, sleep/resume, re-run skip, factory reset.
- CI check (if/when CI exists): `git ls-files --stage` asserts the `.command` mode bit is 100755.

## Out of scope (deliberate)

Speaker diarization, wav2vec2 forced alignment, recursive folder scan, mid-file cancel, parallel file processing, batched inference pipeline (legitimate future opt-in "faster" mode — but it drops the temperature-fallback ladder, so sequential stays the default), CrisperWhisper verbatim model (HF-gated + CC-BY-NC → violates no-token requirement), .txt/.docx outputs, translation, GPU support.

## Known risks (accepted)

- Verbatim is probabilistic — prompting biases but cannot guarantee filler retention; set expectations in README.
- First run needs internet (uv, Python, deps, model); hard-blocking proxies are unfixable — README suggests first launch from home Wi-Fi.
- Aggressive AV/AppLocker can still block unsigned scripts; TROUBLESHOOTING.md covers quarantine restore; AppLocker needs IT.
- ~1–2 GB in `.managed/` inside the repo folder; README warns against cloning into OneDrive-synced locations.
- Intel-Mac and Windows-on-ARM wheel coverage must be re-verified at every dependency bump.
