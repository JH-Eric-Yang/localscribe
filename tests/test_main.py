import socket

from app.main import existing_instance_port, find_free_port


def test_find_free_port_skips_occupied():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        s.listen(1)
        occupied = s.getsockname()[1]
        assert find_free_port(start=occupied) == occupied + 1


def test_existing_instance_detected(tmp_path):
    lock = tmp_path / "app.lock"
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        s.listen(1)
        port = s.getsockname()[1]
        lock.write_text(str(port))
        assert existing_instance_port(lock) == port
    # socket closed -> stale lock -> no instance
    assert existing_instance_port(lock) is None


def test_existing_instance_bad_lockfile(tmp_path):
    lock = tmp_path / "app.lock"
    assert existing_instance_port(lock) is None      # missing file
    lock.write_text("not-a-port")
    assert existing_instance_port(lock) is None      # garbage content
