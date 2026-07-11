"""Prevent system sleep while a job runs. Enter from the WORKER thread on
Windows — SetThreadExecutionState applies to the calling thread."""
import contextlib
import os
import subprocess
import sys

ES_CONTINUOUS = 0x80000000
ES_SYSTEM_REQUIRED = 0x00000001


@contextlib.contextmanager
def keep_awake():
    proc = None
    windows = sys.platform == "win32"
    try:
        if sys.platform == "darwin":
            # -w: caffeinate exits by itself if our process dies
            proc = subprocess.Popen(["caffeinate", "-i", "-w", str(os.getpid())])
        elif windows:
            import ctypes
            ctypes.windll.kernel32.SetThreadExecutionState(
                ES_CONTINUOUS | ES_SYSTEM_REQUIRED)
        yield
    finally:
        if proc is not None:
            proc.terminate()
        elif windows:
            import ctypes
            ctypes.windll.kernel32.SetThreadExecutionState(ES_CONTINUOUS)
