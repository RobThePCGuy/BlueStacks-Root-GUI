"""Serial resolution: a `connect` that says "connected" is not proof the transport
survives to the next adb call.

Field report: flashing a module was refused with "this instance is running 5555".
5555 was never a version -- it was the instance's ADB port. The guest's tcp
transport had been dropped (a second adb of a different version kills the shared
server on sight: "adb server version (41) doesn't match this client (36);
killing..."), so every later `-s 127.0.0.1:5555` failed with "device not found"
while the emulator transport was still perfectly usable.

These pin the fix: confirm the serial is actually attached before handing it to
the rest of the app, and fall back to the sole attached device when it isn't.
"""
from types import SimpleNamespace

import pytest

from adb_handler import _resolve_serial


def _cp(stdout="", stderr="", rc=0):
    return SimpleNamespace(stdout=stdout, stderr=stderr, returncode=rc)


def _runner(connect_out, devices_out):
    calls = []

    def runner(cmd):
        calls.append(cmd)
        joined = " %s " % " ".join(str(c) for c in cmd)
        if " connect " in joined:
            return _cp(stdout=connect_out)
        if " devices " in joined:
            return _cp(stdout=devices_out)
        return _cp()

    runner.calls = calls
    return runner


def test_uses_the_port_serial_when_it_is_really_attached():
    runner = _runner("connected to 127.0.0.1:5555",
                     "List of devices attached\n127.0.0.1:5555\tdevice\n")
    assert _resolve_serial("adb", 5555, runner) == "127.0.0.1:5555"


def test_falls_back_to_the_attached_device_when_the_transport_vanished():
    # The reported case: connect replies "connected", the server restart leaves
    # only the emulator transport behind.
    runner = _runner("connected to 127.0.0.1:5555",
                     "List of devices attached\nemulator-5554\tdevice\n")
    assert _resolve_serial("adb", 5555, runner) == "emulator-5554"


def test_raises_when_the_connect_was_the_only_thing_that_succeeded():
    runner = _runner("connected to 127.0.0.1:5555", "List of devices attached\n")
    with pytest.raises(RuntimeError, match="No running BlueStacks instance"):
        _resolve_serial("adb", 5555, runner)


def test_no_port_uses_the_sole_attached_device_without_connecting():
    runner = _runner("", "List of devices attached\nemulator-5554\tdevice\n")
    assert _resolve_serial("adb", None, runner) == "emulator-5554"
    assert not any("connect" in " ".join(str(c) for c in cmd) for cmd in runner.calls)
