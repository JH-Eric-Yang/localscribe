"""Opt-in NVIDIA CUDA support: flag file, driver detection, runtime probing.

All GPU knowledge lives here — no other module touches nvidia/ctranslate2
device details. GPU mode is Windows-only: ctranslate2 has no macOS CUDA
backend, and Linux would need LD_LIBRARY_PATH set before process start.
"""
import importlib.util
import logging
import os
import shutil
import sys
from pathlib import Path

logger = logging.getLogger("localscribe")

FLAG_PATH = Path(__file__).resolve().parent.parent / ".managed" / "gpu-enabled"


def nvidia_driver_present() -> bool:
    """Gates showing the GPU checkbox. Every NVIDIA driver install puts
    nvidia-smi on PATH (System32), so its presence == driver installed."""
    return sys.platform == "win32" and shutil.which("nvidia-smi") is not None


def enabled(flag_path: Path = FLAG_PATH) -> bool:
    return flag_path.exists()


def set_enabled(on: bool, flag_path: Path = FLAG_PATH) -> None:
    if on:
        flag_path.parent.mkdir(parents=True, exist_ok=True)
        flag_path.touch()
    else:
        flag_path.unlink(missing_ok=True)


def cuda_deps_installed() -> bool:
    """True when the CUDA runtime wheels are importable — decides
    enable-without-restart vs restart-to-download in the UI."""
    try:
        return importlib.util.find_spec("nvidia.cudnn") is not None
    except (ImportError, ModuleNotFoundError, ValueError):
        return False


def _add_dll_dirs() -> None:
    """Register the nvidia wheels' DLL directories. ctranslate2 loads
    cuBLAS/cuDNN lazily via LoadLibrary, which honours add_dll_directory
    and PATH — set both (belt and braces)."""
    import nvidia.cublas
    import nvidia.cudnn
    for pkg in (nvidia.cublas, nvidia.cudnn):
        root = Path(list(pkg.__path__)[0])
        for sub in ("bin", "lib"):
            d = root / sub
            if d.is_dir():
                if hasattr(os, "add_dll_directory"):  # Windows only
                    os.add_dll_directory(str(d))
                os.environ["PATH"] = str(d) + os.pathsep + os.environ.get("PATH", "")


def cuda_usable() -> bool:
    """Runtime auto-detection; idempotent, safe to call once per job.
    Never raises — any probe failure means 'use the CPU'."""
    try:
        _add_dll_dirs()
        import ctranslate2
        return ctranslate2.get_cuda_device_count() > 0
    except Exception:
        logger.exception("CUDA probe failed — falling back to CPU")
        return False
