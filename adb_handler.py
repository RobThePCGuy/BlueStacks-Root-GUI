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
    # Decode adb/magisk output as UTF-8 and never crash on odd bytes. A module's
    # install log can contain bytes that Windows' default cp1252 can't decode
    # (e.g. box-drawing/emoji), which would otherwise raise UnicodeDecodeError in
    # subprocess's reader thread and dump a traceback mid-install.
    return subprocess.run(cmd, capture_output=True, text=True, timeout=60,
                          encoding="utf-8", errors="replace",
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


def _resolve_serial(adb_exe: str, port: Optional[int], runner: Runner) -> str:
    """The ADB serial of the target instance, connecting by ``port`` if given,
    else falling back to the sole attached device. Raises with a user-facing
    message when nothing usable is reachable."""
    if port:
        serial = "127.0.0.1:%d" % port
        cp = runner([adb_exe, "connect", serial])
        out = (cp.stdout or "") + (cp.stderr or "")
        if "connected" in out.lower():
            return serial
        logger.debug("adb connect output: %s", out.strip())  # fall through

    cp = runner([adb_exe, "devices"])
    devices = _parse_devices(cp.stdout or "")
    if not devices:
        raise RuntimeError(
            "No running BlueStacks instance was reachable over ADB. Start the "
            "instance, let it reach the home screen, then try again.")
    if len(devices) > 1:
        raise RuntimeError(
            "Multiple instances are running and the target's ADB port could not "
            "be identified. Close the others and retry, or start only the target "
            "instance.")
    return devices[0]


def install_module(adb_exe: str, port: Optional[int], local_zip: str,
                   progress: Optional[Callable[[str], None]] = None,
                   runner: Runner = _run) -> str:
    """Push ``local_zip`` to a running instance and flash it via Magisk directly.

    Runs ``magisk --install-module`` over an ADB root shell (the same command we
    flash by hand). On success the module is installed and only needs a reboot.
    If the root shell / Magisk isn't reachable, the zip is left in the guest's
    Download folder and a RuntimeError explains how to flash it manually.
    """
    def _p(msg):
        logger.info(msg)
        if progress:
            progress(msg)

    if not os.path.isfile(local_zip):
        raise RuntimeError("Module file not found: %s" % local_zip)

    name = os.path.basename(local_zip)
    _p("Connecting to the instance...")
    serial = _resolve_serial(adb_exe, port, runner)

    tmp = "/data/local/tmp/" + name
    _p("Pushing %s..." % name)
    cp = runner([adb_exe, "-s", serial, "push", local_zip, tmp])
    if cp.returncode != 0:
        raise RuntimeError("ADB push failed: %s"
                           % ((cp.stdout or "") + (cp.stderr or "")).strip())

    _p("Installing %s via Magisk..." % name)
    cp = runner([adb_exe, "-s", serial, "shell", "su", "-c",
                 "magisk --install-module '%s'" % tmp])
    out = ((cp.stdout or "") + (cp.stderr or "")).strip()
    runner([adb_exe, "-s", serial, "shell", "rm", "-f", tmp])  # tidy up

    if cp.returncode == 0:
        return "Installed \"%s\". Close and reopen the instance to activate it." % name

    # Couldn't auto-install (no root shell, Magisk not on PATH, module rejected):
    # leave the zip where the user can flash it by hand and say so.
    _p("Direct install failed; copying to Download for manual flashing...")
    runner([adb_exe, "-s", serial, "push", local_zip, "/sdcard/Download/"])
    raise RuntimeError(
        "Couldn't install automatically (%s). If that's a root-permission "
        "rejection, set Magisk/Kitsune -> Settings -> Superuser access -> "
        "\"Apps and ADB\" and try again. The zip was also copied to the "
        "instance's Download folder -- or flash it there: Modules -> Install "
        "from storage -> Download." % (out or "unknown error"))


def list_running_instances(adb_exe: str, instances, runner: Runner = _run) -> dict:
    """Which of ``instances`` are currently reachable over ADB.

    ``instances`` is an iterable of (unique_id, config_path, original_name).
    Returns {unique_id: port} for every instance whose configured ADB port
    is currently connected. Instances with no recorded port (never booted)
    are skipped without spawning a process.
    """
    running = {}
    for unique_id, config_path, name in instances:
        port = instance_adb_port(config_path, name)
        if port is None:
            continue
        cp = runner([adb_exe, "connect", "127.0.0.1:%d" % port])
        out = (cp.stdout or "") + (cp.stderr or "")
        if "connected" in out.lower():
            running[unique_id] = port
    return running
