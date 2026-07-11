"""Entrypoint: single-instance guard, port probing, logging, ui.run."""
import socket
import webbrowser
from pathlib import Path

MANAGED_DIR = Path(__file__).resolve().parent.parent / ".managed"
LOCK_PATH = MANAGED_DIR / "app.lock"


def _port_in_use(port: int) -> bool:
    with socket.socket() as s:
        s.settimeout(0.5)
        return s.connect_ex(("127.0.0.1", port)) == 0


def find_free_port(start: int = 8377) -> int:
    port = start
    while _port_in_use(port):
        port += 1
    return port


def existing_instance_port(lock_path: Path = LOCK_PATH) -> int | None:
    if not lock_path.exists():
        return None
    try:
        port = int(lock_path.read_text(encoding="utf-8").strip())
    except (ValueError, OSError):
        return None
    return port if _port_in_use(port) else None


def main() -> None:
    existing = existing_instance_port()
    if existing is not None:
        # Second double-click: just reopen the running app's page.
        webbrowser.open(f"http://127.0.0.1:{existing}")
        return

    from app.diagnostics import setup_logging
    logger = setup_logging(MANAGED_DIR)

    port = find_free_port()
    LOCK_PATH.parent.mkdir(parents=True, exist_ok=True)
    LOCK_PATH.write_text(str(port), encoding="utf-8")
    logger.info("starting on 127.0.0.1:%s", port)

    import app.ui  # noqa: F401  (registers the / page)
    from nicegui import ui
    ui.run(host="127.0.0.1", port=port, reload=False, show=True,
           title="LocalScribe", favicon="🎙️")


if __name__ in {"__main__", "__mp_main__"}:
    main()
