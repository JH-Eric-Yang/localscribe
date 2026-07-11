import subprocess
import sys

import app.awake as awake


def test_darwin_spawns_and_terminates_caffeinate(monkeypatch):
    events = []

    class FakeProc:
        def terminate(self):
            events.append("terminated")

    def fake_popen(cmd, **kwargs):
        events.append(cmd[:2])
        return FakeProc()

    monkeypatch.setattr(awake.sys, "platform", "darwin")
    monkeypatch.setattr(subprocess, "Popen", fake_popen)
    with awake.keep_awake():
        pass
    assert events[0] == ["caffeinate", "-i"]
    assert events[-1] == "terminated"


def test_other_platform_is_noop(monkeypatch):
    monkeypatch.setattr(awake.sys, "platform", "linux")
    with awake.keep_awake():
        pass  # must not raise
