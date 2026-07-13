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

# Restart state lives here, NOT in app/main.py. app/main.py runs as module
# __main__ (launched via `python -m app.main`) AND gets imported a second
# time as canonical `app.main` (by app/ui.py's `from app import main`) —
# two separate module objects, two separate globals. A flag set on one is
# invisible to the other, so main()'s exit-code check would always see the
# untouched copy. app/gpu.py is only ever imported canonically, so state
# set here is visible everywhere.
_restart_requested = False


def request_restart() -> None:
    """First GPU enable: exit code 42 tells the launcher loop to re-run
    uv (now with --extra cuda), which downloads the wheels and restarts."""
    global _restart_requested
    _restart_requested = True
    from nicegui import app as nicegui_app
    nicegui_app.shutdown()


def exit_code() -> int:
    return 42 if _restart_requested else 0


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


_dll_dirs_registered = False


def _add_dll_dirs() -> None:
    """Register the nvidia wheels' DLL directories. ctranslate2 loads
    cuBLAS/cuDNN lazily via LoadLibrary, which honours add_dll_directory
    and PATH — set both (belt and braces).

    Guarded by a module-level flag: cuda_usable() runs once per job, and
    without the guard every job would prepend the same directories to PATH
    again, growing it without bound over a long-running process. The flag
    is only set on success, so a failed probe (wheels not yet installed)
    doesn't block a later successful registration once they are."""
    global _dll_dirs_registered
    if _dll_dirs_registered:
        return
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
    _dll_dirs_registered = True


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
