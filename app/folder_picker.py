"""Directory-only picker dialog, adapted from NiceGUI's local_file_picker example."""
import os
from pathlib import Path

from nicegui import events, ui


def list_subdirectories(path: Path) -> list[Path]:
    try:
        return sorted(
            (p for p in path.iterdir() if p.is_dir() and not p.name.startswith(".")),
            key=lambda p: p.name.lower(),
        )
    except PermissionError:
        return []


def default_directory() -> Path:
    """Where Browse… starts: the LocalScribe folder itself — users tend to
    keep their recordings next to the app, not in the home directory."""
    return Path(__file__).resolve().parent.parent


def list_drives() -> list[Path]:
    """All drive roots (C:\\, D:\\, mapped network drives). os.listdrives
    exists only on Windows (3.12+), so this is [] on macOS/Linux."""
    lister = getattr(os, "listdrives", None)
    if lister is None:
        return []
    try:
        return [Path(d) for d in lister()]
    except OSError:
        return []


def picker_rows(current: Path) -> list[dict]:
    rows = []
    if current.parent != current:
        rows.append({"name": "⬆ ..", "path": str(current.parent)})
    else:
        # A drive root has no ".." (C:\ is its own parent), and on Windows
        # each drive is a separate root — without these rows the picker
        # would trap users on the drive they started on.
        rows += [{"name": f"💽 {d}", "path": str(d)}
                 for d in list_drives() if d != current]
    rows += [{"name": f"\U0001f4c1 {p.name}", "path": str(p)}
             for p in list_subdirectories(current)]
    return rows


class FolderPicker(ui.dialog):
    def __init__(self, directory: str | None = None) -> None:
        super().__init__()
        self.current = (Path(directory).expanduser().resolve() if directory
                        else default_directory())
        with self, ui.card().classes("w-[28rem]"):
            ui.label("Double-click a folder to open it").classes("text-sm text-gray-500")
            self.path_label = ui.label(str(self.current)).classes("font-mono text-xs")
            self.grid = ui.aggrid({
                "columnDefs": [{"field": "name", "headerName": "Folder"}],
                "rowSelection": "single",
            }).classes("w-full h-64").on("cellDoubleClicked", self._descend)
            with ui.row().classes("w-full justify-end"):
                ui.button("Cancel", on_click=lambda: self.submit(None)).props("flat")
                ui.button("Choose this folder",
                          on_click=lambda: self.submit(str(self.current)))
        self._refresh()

    def _refresh(self) -> None:
        self.path_label.text = str(self.current)
        self.grid.options["rowData"] = picker_rows(self.current)
        self.grid.update()

    def _descend(self, e: events.GenericEventArguments) -> None:
        self.current = Path(e.args["data"]["path"])
        self._refresh()
