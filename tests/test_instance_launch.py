import pytest

import instance_handler as ih


def test_launch_instance_starts_hd_player_with_instance(tmp_path, monkeypatch):
    exe = tmp_path / "HD-Player.exe"
    exe.write_bytes(b"x")
    calls = []
    monkeypatch.setattr(ih.subprocess, "Popen", lambda args, **k: calls.append(args))

    ih.launch_instance(str(tmp_path), "Tiramisu64")

    assert calls and calls[0][:3] == [str(exe), "--instance", "Tiramisu64"]


def test_launch_instance_missing_player_raises(tmp_path):
    with pytest.raises(RuntimeError, match="HD-Player"):
        ih.launch_instance(str(tmp_path), "Whatever")


def test_restart_instance_kills_then_relaunches(tmp_path, monkeypatch):
    exe = tmp_path / "HD-Player.exe"
    exe.write_bytes(b"x")
    order = []
    monkeypatch.setattr(ih, "terminate_bluestacks", lambda: order.append("kill"))
    monkeypatch.setattr(ih.time, "sleep", lambda s: order.append("wait"))
    monkeypatch.setattr(ih.subprocess, "Popen", lambda args, **k: order.append("launch"))

    ih.restart_instance(str(tmp_path), "Tiramisu64", wait_ms=10)

    assert order == ["kill", "wait", "launch"]  # kill, settle, then relaunch
