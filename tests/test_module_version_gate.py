"""The Magisk version gate on install_module.

A module's own customize.sh enforces a MAGISK_VER_CODE minimum and aborts partway
through if it isn't met, leaving a half-written module directory. Checking before
anything is pushed turns that into a clean refusal.

The subtle requirement is the failure direction: an *unreadable* version must let
the flash proceed. A gate that fired on "couldn't tell" would block flashing on a
healthy instance whose shell was momentarily unavailable -- worse than the problem
it prevents. These pin that direction, which is easy to invert in a refactor.
"""
from types import SimpleNamespace

import pytest

from adb_handler import install_module, magisk_version_code


def _cp(stdout="", stderr="", rc=0):
    return SimpleNamespace(stdout=stdout, stderr=stderr, returncode=rc)


def _runner(version_out, version_rc=0):
    """Fake adb: resolves a serial, answers `magisk -V`, succeeds otherwise."""
    calls = []

    def runner(cmd):
        calls.append(cmd)
        joined = " ".join(str(c) for c in cmd)
        if "magisk -V" in joined:
            return _cp(stdout=version_out, rc=version_rc)
        if "connect" in joined:
            return _cp(stdout="connected to 127.0.0.1:5555")
        if "devices" in joined:
            return _cp(stdout="List of devices attached\n127.0.0.1:5555\tdevice\n")
        return _cp()

    runner.calls = calls
    return runner


@pytest.fixture()
def zip_path(tmp_path):
    p = tmp_path / "ReZygisk-v1.0.0-release.zip"
    p.write_bytes(b"PK\x03\x04stub")
    return str(p)


def test_reads_numeric_version_code():
    assert magisk_version_code("adb", "s", _runner("31000\n")) == 31000


def test_unreadable_version_reports_none_not_zero():
    # None means "couldn't tell"; 0 would compare as hopelessly old and block.
    assert magisk_version_code("adb", "s", _runner("su: not found", 127)) is None


def test_refuses_when_daemon_is_older_than_the_module_requires(zip_path):
    runner = _runner("26000\n")
    with pytest.raises(RuntimeError) as exc:
        install_module("adb", 5555, zip_path, runner=runner,
                       min_magisk_ver_code=26402)
    msg = str(exc.value)
    assert "26402" in msg and "26000" in msg
    # Refusal must come BEFORE anything is pushed to the guest.
    assert not any("push" in " ".join(str(c) for c in cmd) for cmd in runner.calls)


def test_proceeds_when_daemon_meets_the_minimum(zip_path):
    runner = _runner("31000\n")
    install_module("adb", 5555, zip_path, runner=runner, min_magisk_ver_code=26402)
    assert any("--install-module" in " ".join(str(c) for c in cmd)
               for cmd in runner.calls)


def test_proceeds_when_version_is_unreadable(zip_path):
    # The important direction: fail open, not closed.
    runner = _runner("su: not found", 127)
    install_module("adb", 5555, zip_path, runner=runner, min_magisk_ver_code=26402)
    assert any("--install-module" in " ".join(str(c) for c in cmd)
               for cmd in runner.calls)


def test_no_minimum_means_no_version_query_at_all(zip_path):
    runner = _runner("31000\n")
    install_module("adb", 5555, zip_path, runner=runner)
    assert not any("magisk -V" in " ".join(str(c) for c in cmd)
                   for cmd in runner.calls)
