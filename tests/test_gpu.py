from app import gpu


def test_flag_round_trip(tmp_path):
    flag = tmp_path / "gpu-enabled"
    assert gpu.enabled(flag) is False
    gpu.set_enabled(True, flag)
    assert flag.exists()
    assert gpu.enabled(flag) is True
    gpu.set_enabled(True, flag)   # idempotent
    gpu.set_enabled(False, flag)
    assert gpu.enabled(flag) is False
    gpu.set_enabled(False, flag)  # idempotent when already off


def test_flag_lives_in_managed_dir():
    # The launcher checks this exact path; .managed is the gitignored
    # self-bootstrap dir whose deletion is the universal recovery story.
    assert gpu.FLAG_PATH.name == "gpu-enabled"
    assert gpu.FLAG_PATH.parent.name == ".managed"


def test_driver_detection_requires_windows_and_nvidia_smi(monkeypatch):
    monkeypatch.setattr(gpu.sys, "platform", "win32")
    monkeypatch.setattr(gpu.shutil, "which",
                        lambda name: "C:/Windows/System32/nvidia-smi.exe")
    assert gpu.nvidia_driver_present() is True

    monkeypatch.setattr(gpu.shutil, "which", lambda name: None)
    assert gpu.nvidia_driver_present() is False

    monkeypatch.setattr(gpu.sys, "platform", "darwin")
    monkeypatch.setattr(gpu.shutil, "which",
                        lambda name: "/usr/bin/nvidia-smi")  # hypothetical
    assert gpu.nvidia_driver_present() is False


def test_cuda_deps_not_installed_by_default():
    # Dev machines never have the cuda extra installed.
    assert gpu.cuda_deps_installed() is False


def test_cuda_usable_swallows_probe_failures(monkeypatch):
    def boom():
        raise ImportError("no nvidia wheels here")
    monkeypatch.setattr(gpu, "_add_dll_dirs", boom)
    assert gpu.cuda_usable() is False


def test_cuda_usable_false_on_this_machine():
    # No NVIDIA hardware in dev; must return False, never raise.
    assert gpu.cuda_usable() is False


def test_add_dll_dirs_guard_not_set_on_failed_probe(monkeypatch):
    # This machine has no nvidia wheels installed, so the real _add_dll_dirs
    # raises ImportError. The guard must stay False on failure — otherwise a
    # later run (after the wheels get installed) would short-circuit and
    # never register the DLL directories at all.
    monkeypatch.setattr(gpu, "_dll_dirs_registered", False)
    try:
        gpu._add_dll_dirs()
    except ImportError:
        pass
    assert gpu._dll_dirs_registered is False


def test_add_dll_dirs_short_circuits_when_already_registered(monkeypatch):
    # Once registered, a second call must return immediately without
    # attempting the nvidia import again — otherwise PATH grows on every
    # job. Simulate "already registered" and confirm no ImportError escapes
    # even though the nvidia wheels aren't installed on this machine.
    monkeypatch.setattr(gpu, "_dll_dirs_registered", True)
    gpu._add_dll_dirs()  # would raise ImportError if it attempted the import


def test_exit_code_default_zero(monkeypatch):
    monkeypatch.setattr(gpu, "_restart_requested", False)
    assert gpu.exit_code() == 0


def test_request_restart_yields_exit_code_42(monkeypatch):
    monkeypatch.setattr(gpu, "_restart_requested", False)
    shutdowns = []
    import nicegui
    monkeypatch.setattr(nicegui.app, "shutdown", lambda: shutdowns.append(1))
    gpu.request_restart()
    assert gpu.exit_code() == 42           # launcher loop re-runs uv on 42
    assert shutdowns == [1]                 # the app actually closes
    gpu._restart_requested = False          # don't leak state to other tests
