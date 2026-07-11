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
