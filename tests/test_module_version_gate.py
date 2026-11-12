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


def _runner(version_out, version_rc=0, version_err=""):
    """Fake adb: resolves a serial, answers `magisk -V`, succeeds otherwise."""
    calls = []

    def runner(cmd):
        calls.append(cmd)
        joined = " ".join(str(c) for c in cmd)
        if "magisk -V" in joined:
            return _cp(stdout=version_out, stderr=version_err, rc=version_rc)
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


# --------------------------------------------------------------------------
# Reading the code, not a number that happens to be nearby.
#
# Field report: flashing ReZygisk was refused with "this instance is running
# 5555". 5555 was the instance's ADB port, never a version: the tcp transport had
# been dropped by an adb server restart, so the query failed with
# "error: device '127.0.0.1:5555' not found" -- and the old parse took "the first
# 4-6 digit number in stdout+stderr" out of that sentence.
# --------------------------------------------------------------------------

def test_a_failed_transport_is_never_read_as_a_version():
    assert magisk_version_code(
        "adb", "127.0.0.1:5555",
        _runner("", version_rc=1,
                version_err="error: device '127.0.0.1:5555' not found")) is None


def test_a_nonzero_exit_yields_no_version_even_when_digits_appear():
    assert magisk_version_code("adb", "s", _runner("31000\n", version_rc=1)) is None


def test_adb_server_chatter_around_the_code_is_ignored():
    # A mismatched adb server prints this to *stdout*, right where the code lands:
    # "* daemon starting now at tcp:5037" would otherwise offer 5037 as a version.
    out = ("adb server version (41) doesn't match this client (36); killing...\n"
           "* daemon started successfully *\n"
           "31000\n")
    assert magisk_version_code("adb", "s", _runner(out)) == 31000


def test_a_port_on_its_own_line_is_not_a_version():
    assert magisk_version_code(
        "adb", "s", _runner("* daemon not running; starting now at tcp:5037\n")) is None


def test_install_module_proceeds_when_only_a_transport_error_mentions_the_port(zip_path):
    """End to end for the reported failure: the version query fails with the
    serial in the message, which must mean "couldn't tell" (proceed) and not
    "running 5555" (refuse)."""
    runner = _runner("", version_rc=1,
                     version_err="error: device '127.0.0.1:5555' not found")
    install_module("adb", 5555, zip_path, runner=runner, min_magisk_ver_code=26402)
    assert any("--install-module" in " ".join(str(c) for c in cmd)
               for cmd in runner.calls)
