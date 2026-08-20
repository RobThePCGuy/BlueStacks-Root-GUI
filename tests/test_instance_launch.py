"""Launch/restart coverage for both players.

``launch_instance`` branches on the platform -- ``HD-Player.exe --instance`` on
Windows, the extension-less ``BlueStacks`` binary inside the .app on macOS --
so each test pins the branch it means to exercise instead of inheriting the
host's. That way the Windows path is still covered when the suite runs on a Mac
(and vice versa), which is the whole point of having both.
"""
import pytest

import instance_handler as ih


@pytest.fixture
def windows(monkeypatch):
    monkeypatch.setattr(ih.platform_support, "IS_MACOS", False)
    monkeypatch.setattr(ih.platform_support, "IS_WINDOWS", True)


@pytest.fixture
def macos(monkeypatch):
    monkeypatch.setattr(ih.platform_support, "IS_MACOS", True)
    monkeypatch.setattr(ih.platform_support, "IS_WINDOWS", False)


def test_launch_instance_starts_hd_player_with_instance(tmp_path, monkeypatch, windows):
    exe = tmp_path / "HD-Player.exe"
    exe.write_bytes(b"x")
    calls = []
    monkeypatch.setattr(ih.subprocess, "Popen", lambda args, **k: calls.append(args))

    ih.launch_instance(str(tmp_path), "Tiramisu64")

    assert calls and calls[0][:3] == [str(exe), "--instance", "Tiramisu64"]


def test_launch_instance_missing_player_raises(tmp_path, windows):
    with pytest.raises(RuntimeError, match="HD-Player"):
        ih.launch_instance(str(tmp_path), "Whatever")


def test_restart_instance_kills_then_relaunches(tmp_path, monkeypatch, windows):
    exe = tmp_path / "HD-Player.exe"
    exe.write_bytes(b"x")
    order = []
    monkeypatch.setattr(ih, "terminate_bluestacks", lambda: order.append("kill"))
    monkeypatch.setattr(ih.time, "sleep", lambda s: order.append("wait"))
    monkeypatch.setattr(ih.subprocess, "Popen", lambda args, **k: order.append("launch"))

    ih.restart_instance(str(tmp_path), "Tiramisu64", wait_ms=10)

    assert order == ["kill", "wait", "launch"]  # kill, settle, then relaunch


# --- BlueStacks Air ------------------------------------------------------

def test_launch_instance_macos_runs_bundle_binary(tmp_path, monkeypatch, macos):
    exe = tmp_path / "BlueStacks"
    exe.write_bytes(b"x")
    calls = []
    monkeypatch.setattr(ih.subprocess, "Popen",
                        lambda args, **k: calls.append((args, k)))

    ih.launch_instance(str(tmp_path), "Tiramisu64")

    args, kwargs = calls[0]
    assert args == [str(exe), "--instance", "Tiramisu64"]
    # Detached, so quitting this app never takes the emulator down with it.
    assert kwargs.get("start_new_session") is True


def test_launch_instance_macos_missing_binary_raises(tmp_path, macos):
    # Names the macOS binary, not HD-Player.exe, so the error is actionable.
    with pytest.raises(RuntimeError, match="BlueStacks not found"):
        ih.launch_instance(str(tmp_path), "Whatever")


def test_macos_process_names_are_used_for_termination(macos):
    names = ih.bluestacks_process_names()
    assert "BlueStacks" in names
    # Air's player has no .exe processes at all; picking the Windows list would
    # silently terminate nothing and let a write race against a running VM.
    assert not any(n.endswith(".exe") for n in names)


def test_windows_process_names_are_used_for_termination(windows):
    names = ih.bluestacks_process_names()
    assert "HD-Player.exe" in names
