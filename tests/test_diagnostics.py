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


def test_cuda_oom_gets_friendly_gpu_message():
    exc = RuntimeError(
        "CUDA failed with error out of memory (cudaMalloc returned 2)")
    msg = categorize_error(exc)
    assert "graphics card" in msg
    assert "untick" in msg.lower()
    # a CPU MemoryError must NOT get the GPU message
    assert "graphics card" not in categorize_error(MemoryError())


def test_setup_logging_and_header(tmp_path):
    logger = setup_logging(tmp_path)
    log_run_header(logger, {"mode": "verbatim", "model": "small"})
    logger.info("hello")
    for h in logger.handlers:
        h.flush()
    text = (tmp_path / "logs" / "app.log").read_text(encoding="utf-8")
    assert "hello" in text and "mode" in text
    assert isinstance(logger, logging.Logger)
