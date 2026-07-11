"""The job loop: one worker thread, per-file isolation, disk-full pause, manifest updates."""
import errno
import logging
import os
import time
from datetime import datetime, timezone

from app import APP_VERSION
from app import engine as default_engine
from app.diagnostics import categorize_error, log_run_header
from app.state import FileStatus, JobState, Manifest
from app.writers import write_outputs

logger = logging.getLogger("localscribe")


def run_job(job: JobState, manifest: Manifest, eng=default_engine) -> None:
    try:
        _run(job, manifest, eng)
    except Exception as exc:  # job-level failure (model download, model load)
        logger.exception("job failed before/outside per-file processing")
        job.error_message = str(exc)
    finally:
        job.phase = "done"


def _run(job: JobState, manifest: Manifest, eng) -> None:
    log_run_header(logger, {
        "mode": job.mode, "model": job.model, "folder": str(job.folder),
        "file_count": len(job.files), "cpu_threads": os.cpu_count(),
    })
    job.phase = "downloading"

    def dl_progress(done: int, total: int) -> None:
        job.download_done, job.download_total = done, total

    model_path = eng.ensure_model(job.model, progress_cb=dl_progress)
    model = eng.load_model(model_path)
    logger.info("effective compute type: %s", eng.effective_compute_type(model))

    job.started_at = time.monotonic()
    job.phase = "transcribing"
    out_dir = job.folder / "transcripts"
    for i, fs in enumerate(job.files):
        if job.cancel_requested:
            for rest in job.files[i:]:
                if rest.status == "queued":
                    rest.status = "skipped"
            job.message = "Stopped by user."
            break
        if fs.status == "skipped":
            continue
        job.current_index = i
        fs.status = "running"
        started = time.monotonic()
        _process_with_disk_full_pause(job, fs, model, out_dir, manifest, eng)
        fs.elapsed = time.monotonic() - started


def _process_with_disk_full_pause(job, fs: FileStatus, model, out_dir, manifest, eng):
    while True:
        try:
            _process_file(job, fs, model, out_dir, manifest, eng)
            fs.status = "done"
            fs.progress = 1.0
            return
        except OSError as exc:
            if getattr(exc, "errno", None) == errno.ENOSPC:
                logger.warning("disk full — pausing job")
                job.resume_event.clear()
                job.phase = "paused_disk_full"
                job.resume_event.wait()
                job.phase = "transcribing"
                if job.cancel_requested:
                    fs.status = "skipped"
                    return
                continue  # retry the same file
            _fail(job, fs, manifest, exc)
            return
        except Exception as exc:
            _fail(job, fs, manifest, exc)
            return


def _fail(job, fs: FileStatus, manifest: Manifest, exc: Exception) -> None:
    logger.exception("file failed: %s", fs.task.path)
    fs.status = "failed"
    fs.error = categorize_error(exc)
    manifest.mark_failed(fs.task, job.mode, job.model, fs.error)


def _process_file(job, fs: FileStatus, model, out_dir, manifest, eng) -> None:
    seg_iter, info = eng.transcribe_file(model, fs.task.path, job.mode)
    duration = fs.task.duration or getattr(info, "duration", 0) or 0
    segments = []
    for seg in seg_iter:
        segments.append(eng.segment_to_dict(seg))
        if duration:
            fs.progress = min(0.99, seg.end / duration)
    meta = {
        "source_file": fs.task.path.name,
        "duration_seconds": duration,
        "language": getattr(info, "language", None),
        "language_probability": getattr(info, "language_probability", None),
        "mode": job.mode,
        "model_size": job.model,
        "app_version": APP_VERSION,
        "created_utc": datetime.now(timezone.utc).isoformat(),
    }
    outputs = write_outputs(out_dir, fs.task.path.name, segments, meta)
    manifest.mark_done(fs.task, job.mode, job.model, outputs)
