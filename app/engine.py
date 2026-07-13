"""faster-whisper wrapper: mode presets, model download, sequential transcription.

Sequential API only — BatchedInferencePipeline silently drops the temperature
fallback ladder (verified against faster-whisper source during design review).
"""
import logging
import os
import threading
import time
from pathlib import Path

# The Xet download backend stalls irrecoverably inside native code on networks
# that throttle long-lived transfers; the classic HTTP path supports byte-range
# resume and its stuck connections can be dropped and retried (see ensure_model's
# stall watchdog). Must be set before huggingface_hub is first imported.
os.environ.setdefault("HF_HUB_DISABLE_XET", "1")

logger = logging.getLogger("localscribe")

# No download progress for this long -> drop the connection and resume. Progress
# arrives in 10 MB chunks (huggingface_hub's DOWNLOAD_CHUNK_SIZE), so a healthy
# but slow link still reports within this window; a throttled-to-a-trickle
# connection is better killed and resumed than left to crawl forever.
DOWNLOAD_STALL_SECONDS = 90

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
            # huggingface_hub drives several tqdm bars during a download: one
            # per file (unit="it", a file count) and byte-unit bars (unit="B")
            # for the actual transfer. Only the byte bars make a sane MB/MB
            # progress readout in the UI.
            if progress_cb and self.total and getattr(self, "unit", "") == "B":
                progress_cb(self.n, self.total)
    return UITqdm


def _abort_stalled_download():
    """Force-close huggingface_hub's shared HTTP client. The blocked body read
    inside the download raises immediately, and the next request transparently
    gets a fresh client — turning a silent hang into a resumable error."""
    try:
        from huggingface_hub.utils import close_session
        close_session()
    except Exception:
        logger.exception("could not close the download session")


def ensure_model(size: str, progress_cb=None, retries: int = 5,
                 download=None, sleep=time.sleep,
                 stall_seconds: float = DOWNLOAD_STALL_SECONDS,
                 abort_stalled=None) -> str:
    if download is None:
        from huggingface_hub import snapshot_download
        download = snapshot_download
    if abort_stalled is None:
        abort_stalled = _abort_stalled_download

    last_progress = [time.monotonic()]

    def on_progress(done, total):
        last_progress[0] = time.monotonic()
        if progress_cb:
            progress_cb(done, total)

    # Watchdog: a throttled connection can trickle bytes forever without ever
    # tripping a socket timeout (observed in the field: downloads freezing
    # mid-file with no exception). If no progress arrives for stall_seconds,
    # drop the connection so the attempt fails fast and the retry below
    # resumes from the bytes already on disk.
    finished = threading.Event()

    def watchdog():
        while not finished.wait(max(stall_seconds / 4, 0.05)):
            if time.monotonic() - last_progress[0] > stall_seconds:
                logger.warning(
                    "model download made no progress for %.0fs — dropping the "
                    "connection to force a resume", stall_seconds)
                last_progress[0] = time.monotonic()
                abort_stalled()

    threading.Thread(target=watchdog, daemon=True).start()
    try:
        last_exc = None
        for attempt in range(retries):
            last_progress[0] = time.monotonic()
            try:
                return download(MODEL_REPOS[size],
                                tqdm_class=_progress_tqdm(on_progress))
            except Exception as exc:  # download resumes partial files on retry
                last_exc = exc
                if attempt < retries - 1:
                    sleep(2 ** min(attempt, 3))
        raise ModelDownloadError(
            "Could not download the speech model — you need internet the first time. "
            "If you are on a university network, a proxy may be blocking huggingface.co."
        ) from last_exc
    finally:
        finished.set()


def load_model(model_path: str, use_gpu: bool = False):
    """Returns (model, device). The CUDA branch can fail for reasons only
    discoverable at load time (driver/library mismatch), so any failure
    falls back to the CPU path — a job never fails because GPU mode is on."""
    from faster_whisper import WhisperModel

    from app import gpu
    if use_gpu and gpu.cuda_usable():
        try:
            return WhisperModel(model_path, device="cuda",
                                compute_type="float16"), "cuda"
        except Exception:
            logger.exception("CUDA model load failed — falling back to CPU")
    cpu_threads = max(1, (os.cpu_count() or 4) - 1)
    return WhisperModel(model_path, device="cpu", compute_type="int8",
                        cpu_threads=cpu_threads), "cpu"


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
