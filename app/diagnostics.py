"""Logging setup and translation of exceptions into plain-language messages."""
import logging
import platform
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path


def setup_logging(managed_dir: Path) -> logging.Logger:
    logger = logging.getLogger("localscribe")
    logger.setLevel(logging.INFO)
    if not logger.handlers:
        log_dir = managed_dir / "logs"
        log_dir.mkdir(parents=True, exist_ok=True)
        handler = RotatingFileHandler(log_dir / "app.log", maxBytes=2_000_000,
                                      backupCount=3, encoding="utf-8")
        handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
        logger.addHandler(handler)
    return logger


def log_run_header(logger: logging.Logger, settings: dict) -> None:
    logger.info("run header: os=%s arch=%s python=%s settings=%s",
                platform.platform(), platform.machine(), sys.version.split()[0], settings)


def categorize_error(exc: Exception) -> str:
    if isinstance(exc, MemoryError):
        return "This file is too large for this computer's memory."
    text = str(exc).lower()
    root_module = exc.__class__.__module__.split(".")[0]
    if root_module == "av" or "invalid data" in text or "moov atom" in text:
        return "This file appears to be damaged or in an unsupported format."
    return "Something went wrong with this file — see the log for details."
