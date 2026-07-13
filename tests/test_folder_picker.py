import os
from pathlib import Path

from app import folder_picker
from app.folder_picker import list_drives, list_subdirectories, picker_rows


def test_list_subdirectories(tmp_path):
    (tmp_path / "b_data").mkdir()
    (tmp_path / "Alpha").mkdir()
    (tmp_path / ".hidden").mkdir()
    (tmp_path / "file.txt").write_text("x")
    names = [p.name for p in list_subdirectories(tmp_path)]
    assert names == ["Alpha", "b_data"]


def test_list_subdirectories_permission_error(tmp_path, monkeypatch):
    def boom(self):
        raise PermissionError()
    monkeypatch.setattr(type(tmp_path), "iterdir", boom)
    assert list_subdirectories(tmp_path) == []


def test_list_drives_empty_without_os_support():
    # os.listdrives exists only on Windows (Python 3.12+); everywhere else
    # the picker must behave exactly as before this feature existed.
    assert not hasattr(os, "listdrives")  # precondition on the dev machine
    assert list_drives() == []


def test_list_drives_windows(monkeypatch):
    monkeypatch.setattr(os, "listdrives", lambda: ["C:\\", "D:\\"], raising=False)
    assert list_drives() == [Path("C:\\"), Path("D:\\")]


def test_list_drives_swallows_os_error(monkeypatch):
    def boom():
        raise OSError("drive enumeration failed")
    monkeypatch.setattr(os, "listdrives", boom, raising=False)
    assert list_drives() == []


def test_picker_rows_lists_parent_then_subdirs(tmp_path):
    (tmp_path / "b_data").mkdir()
    (tmp_path / "Alpha").mkdir()
    rows = picker_rows(tmp_path)
    assert rows[0] == {"name": "⬆ ..", "path": str(tmp_path.parent)}
    assert [r["name"] for r in rows[1:]] == ["📁 Alpha", "📁 b_data"]


def test_picker_rows_at_drive_root_offers_other_drives(monkeypatch):
    # At a filesystem root (parent == self, e.g. C:\ on Windows) there is no
    # "..", so the other drives must be reachable or the picker is trapped
    # on one drive. The current drive itself is not repeated.
    monkeypatch.setattr(folder_picker, "list_drives",
                        lambda: [Path("/"), Path("D:\\")])
    monkeypatch.setattr(folder_picker, "list_subdirectories", lambda p: [])
    rows = picker_rows(Path("/"))
    assert rows == [{"name": "💽 D:\\", "path": "D:\\"}]


def test_picker_rows_at_root_without_drives(monkeypatch):
    # macOS/Linux: at "/" there are no drives and no ".." — just subfolders.
    monkeypatch.setattr(folder_picker, "list_subdirectories",
                        lambda p: [Path("/Users")])
    rows = picker_rows(Path("/"))
    assert rows == [{"name": "📁 Users", "path": "/Users"}]
