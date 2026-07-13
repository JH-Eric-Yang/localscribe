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
