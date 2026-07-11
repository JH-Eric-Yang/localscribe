from app.folder_picker import list_subdirectories


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
