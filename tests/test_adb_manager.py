"""Tests for the manager install/uninstall helpers (adb_handler).

The full Magisk/Kitsune manager can't be placed offline, so it's `adb install`'d
as a user app after first boot. These lock in the command shape and the
user-facing error handling; the real install is validated live against a booted
instance.
"""
from types import SimpleNamespace

import pytest

from adb_handler import MANAGER_PACKAGE, install_manager, uninstall_manager


def _cp(stdout="", stderr="", rc=0):
    return SimpleNamespace(stdout=stdout, stderr=stderr, returncode=rc)


def _runner(handle):
    calls = []

    def runner(cmd):
        calls.append(cmd)
        return handle(cmd)

    runner.calls = calls
    return runner


def _apk(tmp_path):
    p = tmp_path / "Magisk-manager.apk"
    p.write_bytes(b"PK\x03\x04manager")
    return str(p)


def test_install_manager_success_runs_install_against_connected_serial(tmp_path):
    apk = _apk(tmp_path)

    def handle(cmd):
        if cmd[1] == "connect":
            return _cp("connected to 127.0.0.1:5555")
        if "install" in cmd:
            return _cp("Performing Streamed Install\nSuccess")
        return _cp()

    runner = _runner(handle)
    msg = install_manager("adb", 5555, apk, runner=runner)

    assert "Installed the Magisk manager" in msg
    inst = next(c for c in runner.calls if "install" in c)
    assert inst[:3] == ["adb", "-s", "127.0.0.1:5555"]
    assert inst[-3:] == ["install", "-r", apk]


def test_install_manager_missing_apk_raises(tmp_path):
    with pytest.raises(RuntimeError, match="not found"):
        install_manager("adb", 5555, str(tmp_path / "nope.apk"))


def test_install_manager_signature_mismatch_is_actionable(tmp_path):
    apk = _apk(tmp_path)

    def handle(cmd):
        if cmd[1] == "connect":
            return _cp("connected to 127.0.0.1:5555")
        if "install" in cmd:
            return _cp(stderr="Failure [INSTALL_FAILED_UPDATE_INCOMPATIBLE: "
                              "signatures do not match previously installed version]", rc=1)
        return _cp()

    with pytest.raises(RuntimeError, match="different-signed"):
        install_manager("adb", 5555, apk, runner=_runner(handle))


def test_install_manager_generic_failure_surfaces_output(tmp_path):
    apk = _apk(tmp_path)

    def handle(cmd):
        if cmd[1] == "connect":
            return _cp("connected to 127.0.0.1:5555")
        if "install" in cmd:
            return _cp(stderr="Failure [INSTALL_FAILED_INSUFFICIENT_STORAGE]", rc=1)
        return _cp()

    with pytest.raises(RuntimeError, match="INSUFFICIENT_STORAGE"):
        install_manager("adb", 5555, apk, runner=_runner(handle))


def test_uninstall_manager_success(tmp_path):
    def handle(cmd):
        if cmd[1] == "connect":
            return _cp("connected to 127.0.0.1:5555")
        if "uninstall" in cmd:
            assert cmd[-1] == MANAGER_PACKAGE
            return _cp("Success")
        return _cp()

    assert "Removed" in uninstall_manager("adb", 5555, runner=_runner(handle))


def test_uninstall_manager_not_installed_is_success(tmp_path):
    def handle(cmd):
        if cmd[1] == "connect":
            return _cp("connected to 127.0.0.1:5555")
        if "uninstall" in cmd:
            return _cp("Failure [DELETE_FAILED_INTERNAL_ERROR]\n"
                       "Unknown package: %s" % MANAGER_PACKAGE, rc=1)
        return _cp()

    msg = uninstall_manager("adb", 5555, runner=_runner(handle))
    assert "not installed" in msg.lower()
