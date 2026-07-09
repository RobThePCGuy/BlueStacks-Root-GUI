"""Push files into a running BlueStacks instance via its bundled ADB.

Used by the "Sideload Magisk Module" feature: BlueStacks' in-app file picker
hands Kitsune/Magisk a Windows-style URI that its module installer can't open
("Invalid Uri"). Getting the module .zip into the guest's own storage
(`/sdcard/Download/`) sidesteps that -- the user then flashes it from Magisk's
own picker, which reads guest storage fine.

This is the tool's one *online* operation: the target instance must be RUNNING
so its ADB port is open. Everything else in the app works on shut-down disks.
"""
from __future__ import annotations

import logging
import os
import re
import subprocess
from typing import Callable, Optional

logger = logging.getLogger(__name__)

# BlueStacks ships its own adb as HD-Adb.exe next to HD-Player.exe. Plain adb.exe
# is a fallback for unusual layouts.
_ADB_NAMES = ("HD-Adb.exe", "adb.exe")

# bluestacks.conf: bst.instance.<name>.status.adb_port="5555"
_ADB_PORT_KEY = ".status.adb_port"

# Hide the console window adb would otherwise flash on Windows.
_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)

Runner = Callable[[list], "subprocess.CompletedProcess"]


def _run(cmd: list) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, text=True, timeout=60,
                          creationflags=_NO_WINDOW)


def find_adb(install_dirs) -> Optional[str]:
    """First HD-Adb.exe / adb.exe found in any of ``install_dirs``, else None."""
    for d in install_dirs:
        if not d:
            continue
        for name in _ADB_NAMES:
            cand = os.path.join(d, name)
            if os.path.isfile(cand):
                return cand
    return None


def instance_adb_port(config_path: str, instance_name: str) -> Optional[int]:
    """The ADB port BlueStacks assigned this instance, from bluestacks.conf.

    Returns None if the key isn't present (e.g. the instance has never been
    started, so BlueStacks hasn't recorded a port).
    """
    if not config_path or not os.path.isfile(config_path):
        return None
    key = re.compile(
        r"^bst\.instance\." + re.escape(instance_name) + re.escape(_ADB_PORT_KEY)
        + r'\s*=\s*"(\d+)"', re.IGNORECASE)
    try:
        with open(config_path, encoding="utf-8") as fh:
            for line in fh:
                m = key.match(line.strip())
                if m:
                    return int(m.group(1))
    except OSError:
        logger.debug("Could not read %s for adb port", config_path, exc_info=True)
    return None


def _parse_devices(stdout: str) -> list:
    """Serials from `adb devices` output that are in the 'device' state."""
    serials = []
    for line in stdout.splitlines()[1:]:          # skip "List of devices attached"
        parts = line.split()
        if len(parts) >= 2 and parts[1] == "device":
            serials.append(parts[0])
    return serials


def push_module(adb_exe: str, port: Optional[int], local_zip: str,
                remote_dir: str = "/sdcard/Download/",
                progress: Optional[Callable[[str], None]] = None,
                runner: Runner = _run) -> str:
    """Push ``local_zip`` into a running instance's ``remote_dir``.

    Resolves the target serial from ``port`` (connecting if needed), or falls
    back to the sole attached device. Returns a human-readable status line;
    raises RuntimeError with a user-facing message on failure.
    """
    def _p(msg):
        logger.info(msg)
        if progress:
            progress(msg)

    if not os.path.isfile(local_zip):
        raise RuntimeError("Module file not found: %s" % local_zip)

    serial = None
    if port:
        serial = "127.0.0.1:%d" % port
        _p("Connecting to %s..." % serial)
        cp = runner([adb_exe, "connect", serial])
        out = (cp.stdout or "") + (cp.stderr or "")
        if "connected" not in out.lower():
            # connect didn't take -- fall back to whatever's already attached
            logger.debug("adb connect output: %s", out.strip())
            serial = None

    if serial is None:
        cp = runner([adb_exe, "devices"])
        devices = _parse_devices(cp.stdout or "")
        if not devices:
            raise RuntimeError(
                "No running BlueStacks instance was reachable over ADB. Start the "
                "instance, let it reach the home screen, then try again.")
        if len(devices) > 1:
            raise RuntimeError(
                "Multiple instances are running and the target's ADB port could "
                "not be identified. Close the others and retry, or start only the "
                "target instance.")
        serial = devices[0]

    _p("Pushing %s to %s..." % (os.path.basename(local_zip), remote_dir))
    cp = runner([adb_exe, "-s", serial, "push", local_zip, remote_dir])
    out = (cp.stdout or "") + (cp.stderr or "")
    if cp.returncode != 0:
        raise RuntimeError("ADB push failed: %s" % out.strip())
    dest = remote_dir.rstrip("/") + "/" + os.path.basename(local_zip)
    return "Pushed to %s. In BlueStacks, open Kitsune/Magisk -> Modules -> " \
           "Install from storage -> Download, and pick this file." % dest
