"""Directory-only picker dialog, adapted from NiceGUI's local_file_picker example."""
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


class FolderPicker(ui.dialog):
    def __init__(self, directory: str = "~") -> None:
        super().__init__()
        self.current = Path(directory).expanduser().resolve()
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
        rows = []
        if self.current.parent != self.current:
            rows.append({"name": "⬆ ..", "path": str(self.current.parent)})
        rows += [{"name": f"\U0001f4c1 {p.name}", "path": str(p)}
                 for p in list_subdirectories(self.current)]
        self.path_label.text = str(self.current)
        self.grid.options["rowData"] = rows
        self.grid.update()

    def _descend(self, e: events.GenericEventArguments) -> None:
        self.current = Path(e.args["data"]["path"])
        self._refresh()
