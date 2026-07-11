"""Single page: setup card -> progress -> completion, all rendered from JobState."""
import logging
import subprocess
import sys
import threading
from pathlib import Path

from nicegui import app as nicegui_app
from nicegui import ui

from app import worker
from app.awake import keep_awake
from app.discovery import ScanResult, scan_folder
from app.folder_picker import FolderPicker
from app.state import FileStatus, JobState, Manifest

logger = logging.getLogger("localscribe")

job = JobState()
current_scan: ScanResult | None = None
manifest: Manifest | None = None

MODE_OPTIONS = {
    "non_verbatim": "Non-verbatim — cleaned-up, easier to read (recommended)",
    "verbatim": "Verbatim — keeps um, uh, repetitions and false starts",
}
MODEL_OPTIONS = {
    "base": "Faster — less accurate",
    "small": "Standard — recommended",
    "medium": "Most accurate — much slower (1.5 GB download)",
}
STATUS_ICONS = {"queued": "radio_button_unchecked", "running": "autorenew",
                "done": "check_circle", "skipped": "remove_circle_outline",
                "failed": "error"}
STATUS_COLORS = {"queued": "grey", "running": "primary", "done": "positive",
                 "skipped": "warning", "failed": "negative"}


def eta_text(media_done: float, wall_elapsed: float, media_total: float) -> str | None:
    if wall_elapsed < 30 or media_done <= 0:
        return None
    rate = media_done / wall_elapsed
    remaining_min = max(1, round((media_total - media_done) / rate / 60))
    return f"about {remaining_min} minute{'s' if remaining_min != 1 else ''} left"


def _media_progress() -> tuple[float, float]:
    done = total = 0.0
    for fs in job.files:
        d = fs.task.duration or 0.0
        if fs.status == "skipped":
            continue
        total += d
        done += d if fs.status in ("done", "failed") else d * fs.progress
    return done, total


def open_folder(path: Path) -> None:
    if sys.platform == "darwin":
        subprocess.Popen(["open", str(path)])
    elif sys.platform == "win32":
        subprocess.Popen(["explorer", str(path)])
    else:
        subprocess.Popen(["xdg-open", str(path)])


def start_job() -> None:
    job.files = []
    for task in current_scan.tasks:
        skipped = (not job_redo_flag["redo"]
                   and manifest.should_skip(task, job.mode, job.model))
        job.files.append(FileStatus(task=task,
                                    status="skipped" if skipped else "queued"))
    job.cancel_requested = False
    job.error_message = None
    job.message = ""
    job.phase = "downloading"
    threading.Thread(target=_job_thread, daemon=True).start()


def retry_job() -> None:
    """After a job-level failure (e.g. model download): re-run pending files."""
    for fs in job.files:
        if fs.status in ("failed", "running"):
            fs.status = "queued"
            fs.progress = 0.0
            fs.error = None
    job.cancel_requested = False
    job.error_message = None
    job.phase = "downloading"
    threading.Thread(target=_job_thread, daemon=True).start()


def _job_thread() -> None:
    with keep_awake():  # entered on the worker thread: required on Windows
        worker.run_job(job, manifest)


def request_cancel() -> None:
    """Stop after the current file. Also wakes a disk-full pause so cancel
    takes effect immediately instead of waiting for the user to press Resume."""
    job.cancel_requested = True
    job.resume_event.set()


def reset_to_setup() -> None:
    global current_scan, manifest
    job.phase = "idle"
    job.files = []
    job.folder = None
    current_scan = None
    manifest = None


job_redo_flag = {"redo": False}


@ui.page("/")
def index() -> None:
    async def pick_folder() -> None:
        result = await FolderPicker("~")
        if result:
            choose_folder(result)

    def choose_folder(path_str: str) -> None:
        global current_scan, manifest
        folder = Path(path_str).expanduser()
        if not folder.is_dir():
            ui.notify("That folder does not exist — check the path.", type="warning")
            return
        job.folder = folder
        manifest = Manifest(folder)
        current_scan = scan_folder(folder)
        folder_input.value = str(folder)
        update_scan_summary()

    def update_scan_summary() -> None:
        if current_scan is None:
            return
        n_skip = sum(1 for t in current_scan.tasks
                     if manifest.should_skip(t, job.mode, job.model))
        parts = [f"Found {len(current_scan.tasks)} audio/video files"]
        if n_skip and not job_redo_flag["redo"]:
            parts.append(f"{n_skip} already transcribed — will be skipped")
        if n_skip and job_redo_flag["redo"]:
            parts.append(f"existing transcripts for {n_skip} files will be replaced")
        if current_scan.damaged:
            parts.append(f"{len(current_scan.damaged)} unreadable or damaged — skipped")
        if current_scan.ignored:
            parts.append(f"{len(current_scan.ignored)} other files ignored")
        scan_label.text = ", ".join(parts) + "."
        pending = len(current_scan.tasks) - (0 if job_redo_flag["redo"] else n_skip)
        start_btn.set_enabled(pending > 0)
        if pending:
            start_btn.text = "Start transcription"
        elif not current_scan.tasks:
            start_btn.text = "No audio/video files found in this folder"
        else:
            start_btn.text = "Nothing to do — all files already transcribed"

    def on_start() -> None:
        start_job()
        body.refresh()

    def on_reset() -> None:
        """Back to a pristine setup card: clear shared state AND this page's widgets."""
        reset_to_setup()
        folder_input.value = ""
        scan_label.text = ""
        start_btn.text = "Start transcription"
        start_btn.disable()
        body.refresh()

    with ui.column().classes("w-full max-w-3xl mx-auto p-4 gap-4"):
        ui.label("LocalScribe").classes("text-2xl font-bold")
        ui.label("Transcribe every audio/video file in a folder — on this computer, "
                 "nothing is uploaded anywhere.").classes("text-sm text-gray-500")

        with ui.card().classes("w-full").bind_visibility_from(
                job, "phase", backward=lambda p: p == "idle"):
            ui.label("1. Choose the folder with your recordings").classes("text-lg")
            with ui.row().classes("w-full items-center"):
                folder_input = ui.input("Folder to transcribe").props("readonly") \
                    .classes("grow")
                ui.button("Browse…", on_click=pick_folder)
            with ui.expansion("Or type/paste a folder path (e.g. a network drive)"):
                typed = ui.input("Full folder path").classes("w-full")
                ui.button("Use this path", on_click=lambda: choose_folder(typed.value))
            scan_label = ui.label("").classes("text-sm text-gray-600")
            ui.checkbox("Re-do already transcribed files",
                        on_change=lambda e: (job_redo_flag.__setitem__("redo", e.value),
                                             update_scan_summary()))

            ui.label("2. How should it transcribe?").classes("text-lg mt-2")
            ui.radio(MODE_OPTIONS, value=job.mode,
                     on_change=lambda e: (setattr(job, "mode", e.value),
                                          update_scan_summary()))
            ui.label("Verbatim keeps many more hesitations, but no software can "
                     "capture every single one.").classes("text-xs text-gray-500")
            ui.select(MODEL_OPTIONS, value=job.model, label="Accuracy vs speed",
                      on_change=lambda e: (setattr(job, "model", e.value),
                                           update_scan_summary())).classes("w-72")
            ui.label("The first run downloads a speech model (about 0.5 GB for "
                     "Standard, one time only). Keep the laptop plugged in with the "
                     "lid open during transcription.").classes("text-xs text-gray-500")
            start_btn = ui.button("Start transcription", on_click=on_start) \
                .props("size=lg color=primary")
            start_btn.disable()

        @ui.refreshable
        def body() -> None:
            if job.phase == "idle":
                ui.page_title("LocalScribe")
                return
            done, total = _media_progress()
            pct = int(done / total * 100) if total else 0
            if job.phase == "done":
                render_completion()
                ui.page_title("Done — LocalScribe")
            else:
                render_progress(done, total, pct)
                ui.page_title(f"{pct}% — Transcribing…")

        def render_progress(done: float, total: float, pct: int) -> None:
            with ui.card().classes("w-full"):
                if job.phase == "downloading":
                    mb_done = job.download_done // 1_000_000
                    mb_total = job.download_total // 1_000_000
                    ui.label(f"Downloading speech model — {mb_done} MB of "
                             f"{mb_total} MB (one time only)…")
                    ui.linear_progress(
                        value=(job.download_done / job.download_total)
                        if job.download_total else 0, show_value=False)
                elif job.phase == "paused_disk_full":
                    ui.label("Your disk is full — free some space, then press "
                             "Resume.").classes("text-negative text-lg")
                    with ui.row():
                        ui.button("Resume", on_click=job.resume_event.set) \
                            .props("color=primary")
                        ui.button("Stop transcription", on_click=request_cancel) \
                            .props("flat color=negative")
                else:
                    running = [fs for fs in job.files if fs.status == "running"]
                    name = running[0].task.path.name if running else ""
                    n_active = sum(1 for fs in job.files if fs.status != "skipped")
                    n_done = sum(1 for fs in job.files
                                 if fs.status in ("done", "failed"))
                    ui.label(f"File {min(n_done + 1, n_active)} of {n_active} — {name}")
                    ui.linear_progress(value=done / total if total else 0,
                                       show_value=False)
                    import time as _time
                    eta = eta_text(done, _time.monotonic() - (job.started_at or 0),
                                   total) if job.started_at else None
                    ui.label(eta or "Estimating time remaining…") \
                        .classes("text-sm text-gray-500")
                    ui.button("Stop after current file", on_click=request_cancel) \
                        .props("flat color=negative")
                render_file_rows()

        def render_file_rows() -> None:
            for fs in job.files:
                with ui.row().classes("w-full items-center gap-2"):
                    ui.icon(STATUS_ICONS[fs.status],
                            color=STATUS_COLORS[fs.status])
                    ui.label(fs.task.path.name).classes("grow font-mono text-sm")
                    if fs.status == "running":
                        ui.linear_progress(value=fs.progress, show_value=False) \
                            .classes("w-32")
                    elif fs.status == "done" and fs.elapsed:
                        ui.label(f"{fs.elapsed:.0f}s").classes("text-xs text-gray-500")
                    elif fs.status == "failed":
                        ui.label(fs.error or "failed") \
                            .classes("text-xs text-negative")

        def render_completion() -> None:
            n_done = sum(1 for fs in job.files if fs.status == "done")
            n_failed = sum(1 for fs in job.files if fs.status == "failed")
            n_skipped = sum(1 for fs in job.files if fs.status == "skipped")
            with ui.card().classes("w-full"):
                if job.error_message:
                    ui.label("Could not start the transcription.") \
                        .classes("text-lg text-negative")
                    ui.label(job.error_message).classes("text-sm")
                    ui.button("Retry", on_click=lambda: (retry_job(), body.refresh())) \
                        .props("color=primary")
                else:
                    color = "text-positive" if n_failed == 0 else "text-warning"
                    summary = f"{n_done} of {n_done + n_failed} files transcribed."
                    if n_failed:
                        summary += f" {n_failed} failed."
                    if n_skipped:
                        summary += f" {n_skipped} skipped (already done)."
                    if job.message:
                        summary += f" {job.message}"
                    ui.label(summary).classes(f"text-lg {color}")
                render_file_rows()
                with ui.row():
                    if job.folder:
                        ui.button("Open output folder",
                                  on_click=lambda: open_folder(job.folder / "transcripts"))
                    ui.button("Transcribe another folder", on_click=on_reset) \
                        .props("flat")

        body()
        ui.timer(0.5, body.refresh)

        with ui.row().classes("w-full justify-between text-xs text-gray-400 mt-8"):
            managed = Path(__file__).resolve().parent.parent / ".managed"
            ui.label(f"Problems? Send us the log file: {managed / 'logs' / 'app.log'}")
            ui.button("Quit LocalScribe", on_click=nicegui_app.shutdown).props("flat dense")
