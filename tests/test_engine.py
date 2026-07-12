import io

import pytest

from app.engine import (MODEL_REPOS, VERBATIM_PROMPT, ModelDownloadError,
                        _progress_tqdm, ensure_model,
                        hotwords_injected_per_window, segment_to_dict,
                        transcribe_kwargs)


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


def test_xet_backend_disabled():
    # The Xet download backend stalls irrecoverably inside native code on
    # networks that throttle long-lived transfers (observed in the field);
    # importing app.engine must force the resumable classic HTTP path.
    import os

    import app.engine  # noqa: F401

    assert os.environ.get("HF_HUB_DISABLE_XET") == "1"


def test_ensure_model_recovers_from_stalled_download():
    """A download that goes quiet must be aborted by the stall watchdog and
    retried — the retry resumes and succeeds instead of hanging forever."""
    import threading

    calls = []
    aborts = []
    unblock = threading.Event()

    def abort():
        aborts.append(1)
        unblock.set()  # simulates close_session() making the blocked read raise

    def stalling_download(repo, tqdm_class=None):
        calls.append(repo)
        if len(calls) == 1:
            assert unblock.wait(timeout=10), "watchdog never aborted the stall"
            raise ConnectionError("connection force-closed")
        return "/fake/path"

    path = ensure_model("small", download=stalling_download, sleep=lambda s: None,
                        stall_seconds=0.2, abort_stalled=abort)
    assert path == "/fake/path"
    assert len(calls) == 2
    assert len(aborts) >= 1


def test_progress_callback_only_fires_for_byte_bars():
    """huggingface_hub drives both byte-unit download bars and a file-count
    bar through the same tqdm_class; only the byte bars should reach the UI
    callback, or download progress mixes bytes with a file count."""
    calls = []

    def cb(done, total):
        calls.append((done, total))

    UITqdm = _progress_tqdm(cb)
    quiet = io.StringIO()  # keep tqdm from writing a progress bar to stderr

    byte_bar = UITqdm(total=1000, unit="B", file=quiet)
    byte_bar.update(500)

    file_count_bar = UITqdm(total=3, unit="it", file=quiet)
    file_count_bar.update(1)

    assert calls == [(500, 1000)]


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
