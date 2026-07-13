from app.ui import eta_text


def test_eta_none_during_calibration():
    assert eta_text(media_done=10.0, wall_elapsed=10.0, media_total=100.0) is None
    assert eta_text(media_done=0.0, wall_elapsed=60.0, media_total=100.0) is None


def test_eta_phrasing():
    # 60 media-s in 60 wall-s -> 1x realtime -> 540 media-s left -> "about 9 minutes left"
    assert eta_text(media_done=60.0, wall_elapsed=60.0, media_total=600.0) == "about 9 minutes left"
    assert eta_text(media_done=590.0, wall_elapsed=60.0, media_total=600.0) == "about 1 minute left"


def test_start_job_resets_device_notice(monkeypatch):
    from types import SimpleNamespace

    from app import ui as ui_mod
    monkeypatch.setattr(ui_mod.worker, "run_job", lambda job, manifest: None)
    monkeypatch.setattr(ui_mod, "current_scan", SimpleNamespace(tasks=[]))
    ui_mod.job.device_notice = "GPU not available — using CPU."
    ui_mod.start_job()
    assert ui_mod.job.device_notice is None
    ui_mod.job.phase = "idle"  # don't leak state to other tests
