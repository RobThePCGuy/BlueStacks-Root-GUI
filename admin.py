"""Windows UAC elevation helpers.

Patching the binaries under ``C:\\Program Files\\BlueStacks_nxt`` and terminating
BlueStacks processes both require administrator rights. These helpers let the
app detect whether it is elevated and, if not, relaunch itself through a UAC
prompt.

Network/shared-drive note
-------------------------
An elevated process runs in a different logon session that does NOT inherit the
user's mapped drive letters (e.g. a VMware shared folder mapped to ``Y:``). If
the app is launched from such a drive, a naive relaunch of ``Y:\\...\\main.py``
fails because ``Y:`` doesn't exist for the elevated process, so it never starts.
We therefore rewrite the relaunch path to its UNC form
(``\\\\vmware-host\\Shared Folders\\...``), which the elevated session can reach.
"""
from __future__ import annotations

import ctypes
import logging
import os
import subprocess
import sys
from ctypes import wintypes

logger = logging.getLogger(__name__)

SW_SHOWNORMAL = 1
ERROR_SUCCESS = 0


def is_admin() -> bool:
    """Return True if the current process is running with administrator rights."""
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:  # noqa: BLE001 - any failure means "assume not admin"
        logger.debug("IsUserAnAdmin() check failed", exc_info=True)
        return False


def _drive_unc_root(drive: str) -> str | None:
    """Return the UNC root for a mapped drive (e.g. 'Y:' -> r'\\\\host\\share'), or None."""
    try:
        mpr = ctypes.WinDLL("mpr", use_last_error=True)
        buf = ctypes.create_unicode_buffer(1024)
        length = wintypes.DWORD(1024)
        rc = mpr.WNetGetConnectionW(drive, buf, ctypes.byref(length))
        if rc == ERROR_SUCCESS and buf.value:
            return buf.value
    except Exception:  # noqa: BLE001
        logger.debug("WNetGetConnectionW failed for %s", drive, exc_info=True)
    return None


def to_accessible_path(path: str) -> str:
    """Rewrite a path on a mapped network drive to its UNC form.

    Elevated processes can't see mapped drive letters but can reach the
    underlying UNC share, so this keeps relaunch-as-admin working when the app
    lives on a VMware shared folder / network drive. Non-network paths are
    returned unchanged.
    """
    abspath = os.path.abspath(path)
    drive, rest = os.path.splitdrive(abspath)
    if len(drive) == 2 and drive[1] == ":":
        try:
            # DriveType 4 == network (DRIVE_REMOTE)
            if ctypes.windll.kernel32.GetDriveTypeW(drive + "\\") == 4:
                unc_root = _drive_unc_root(drive)
                if unc_root:
                    return unc_root + rest
        except Exception:  # noqa: BLE001
            logger.debug("Drive-type check failed for %s", drive, exc_info=True)
    return abspath

def relaunch_as_admin() -> bool:
    """Relaunch the current program elevated via a UAC prompt.

    Works both from source (``python main.py ...``) and as a frozen PyInstaller
    executable, and from a mapped network/shared drive (rewritten to UNC).
    Returns True if an elevated instance was started (caller should then exit),
    or False if elevation was declined or failed.
    """
    if is_admin():
        return False

    if getattr(sys, "frozen", False):
        # Frozen exe: relaunch the exe itself with the same args.
        executable = to_accessible_path(sys.executable)
        params = subprocess.list2cmdline(sys.argv[1:])
        workdir = os.path.dirname(executable)
    else:
        # Running from source: relaunch the interpreter with this script + args.
        # The script path is made UNC-safe; the interpreter itself is local.
        script = to_accessible_path(sys.argv[0])
        executable = sys.executable
        params = subprocess.list2cmdline([script] + sys.argv[1:])
        workdir = os.path.dirname(script)

    # A UNC working directory is unreliable; the script's own directory is added
    # to sys.path[0] from the absolute script path anyway, so cwd isn't needed
    # for imports. Pass None when workdir is UNC to avoid ShellExecute quirks.
    lp_directory = None if workdir.startswith("\\\\") else workdir

    try:
        # ShellExecuteW with the "runas" verb raises the UAC consent dialog.
        rc = ctypes.windll.shell32.ShellExecuteW(
            None, "runas", executable, params, lp_directory, SW_SHOWNORMAL
        )
    except Exception:  # noqa: BLE001
        logger.exception("Failed to request elevation")
        return False

    # ShellExecuteW returns a value > 32 on success.
    if int(rc) > 32:
        logger.info("Relaunched elevated (%s %s); exiting unelevated instance.",
                    executable, params)
        return True
    logger.warning("Elevation request was declined or failed (code %s).", rc)
    return False


def ensure_admin() -> None:
    """Elevate if needed: if not admin, request elevation and exit this process.

    If the user accepts the UAC prompt an elevated copy is launched and this
    (unelevated) process exits. If they decline, this process keeps running so
    the app still opens -- it will simply surface permission errors when it tries
    to patch or kill processes.
    """
    if is_admin():
        return
    if relaunch_as_admin():
        sys.exit(0)
    logger.warning("Continuing without administrator rights.")
