"""Platform detection and the one privileged operation macOS needs.

This project began as Windows-only, and everything that touches the machine --
the registry probe, UAC elevation, ``FILE_ATTRIBUTE_READONLY`` locks, the
bundled e2fsprogs ``.exe``s -- assumed it. BlueStacks Air (macOS/Apple Silicon)
is a different enough product that the honest port is a second backend rather
than a sprinkling of ``if sys.platform`` checks, so this module holds only the
two things every backend genuinely shares: which platform we are on, and how to
run a command with administrator rights.

Elevation differs in kind, not just in API
------------------------------------------
On Windows the app relaunches *itself* elevated through UAC (``admin.py``),
because nearly everything it does -- patching binaries under Program Files,
killing services -- needs admin for the whole session. On macOS almost nothing
does: the config file, the instance disks and the logs all live under
``/Users/Shared`` and are writable by the logged-in user, and even
``Root.qcow2`` inside the app bundle ships mode ``rw-rw-rw-``.

What actually guards that bundle is not permissions but *App Management*: since
Ventura, modifying another application's bundle is refused with ``EPERM``
regardless of POSIX mode, until the user grants the privilege. The crucial
detail is that App Management is granted to an **application**, not to a user --
so a root shell spawned through ``osascript`` does **not** inherit the grant its
parent holds, and escalating can fail precisely where a direct write succeeds.
That was observed on a real install: a plain write permitted while ``cp`` under
``with administrator privileges`` was refused on the same file seconds later.

The consequence for callers is that elevation is a *fallback*, not the first
move (see ``macos_root._install_image``), and the normal macOS flow shows no
password prompt at all. This helper remains for installs whose image genuinely
is not user-writable. Running the whole GUI as root would be worse practice
and, for a Qt app, actively awkward -- it would write root-owned files into the
user's config directory, and it would not help with App Management anyway.
"""
from __future__ import annotations

import logging
import os
import subprocess
import sys
import tempfile

logger = logging.getLogger(__name__)

IS_WINDOWS = sys.platform.startswith("win")
IS_MACOS = sys.platform == "darwin"


class ElevationError(RuntimeError):
    """A privileged command failed, or the user dismissed the auth prompt."""


# AppleScript's own error number for "user cancelled" -- surfaced by osascript
# as ``execution error: User canceled. (-128)``.
_USER_CANCELLED = "-128"


def run_elevated(script: str, *, label: str = "operation", timeout: int = 1800) -> str:
    """Run ``script`` (``/bin/sh`` source) as root, returning its stdout.

    macOS shows one authorization dialog per call, so callers should batch a
    whole operation into a single script rather than elevating step by step --
    a revert that prompted twice would be a bug, not a detail.

    The script is written to a private temp file with mode 0600 and executed by
    path. Passing it inline would mean embedding it in an AppleScript string
    literal, where a quote or backslash in a BlueStacks path could change what
    the elevated shell runs; a file sidesteps the nested quoting entirely.

    Raises :class:`ElevationError` if the user cancels the prompt or the script
    exits non-zero.
    """
    if not IS_MACOS:
        raise ElevationError("run_elevated() is macOS-only")

    # mkdtemp (not just mkstemp) so the *directory* is ours and 0700: a
    # world-writable /tmp entry that root is about to execute would otherwise be
    # a swap-the-file-under-us race.
    tmpdir = tempfile.mkdtemp(prefix="bsrootgui-")
    path = os.path.join(tmpdir, "elevated.sh")
    try:
        with open(path, "w", encoding="utf-8") as fh:
            fh.write("#!/bin/sh\nset -e\n")
            fh.write(script)
        os.chmod(path, 0o700)

        logger.info("Requesting administrator rights for: %s", label)
        applescript = 'do shell script "/bin/sh %s" with administrator privileges' % path
        try:
            proc = subprocess.run(
                ["/usr/bin/osascript", "-e", applescript],
                capture_output=True, text=True, timeout=timeout,
            )
        except subprocess.TimeoutExpired as exc:
            raise ElevationError(
                "%s timed out waiting for the administrator prompt." % label) from exc

        if proc.returncode != 0:
            err = (proc.stderr or "").strip()
            if _USER_CANCELLED in err or "User canceled" in err:
                raise ElevationError(
                    "Administrator access is required to %s, and the prompt was "
                    "dismissed." % label)
            raise ElevationError("%s failed: %s" % (label, err or "unknown error"))

        logger.info("Elevated %s completed.", label)
        return proc.stdout
    finally:
        # Never leave a root-executable script lying around, even on failure.
        try:
            if os.path.isfile(path):
                os.unlink(path)
            os.rmdir(tmpdir)
        except OSError:
            logger.debug("could not clean up %s", tmpdir, exc_info=True)


def shell_quote(path: str) -> str:
    """Quote a path for safe inclusion in the ``/bin/sh`` source above."""
    return "'" + str(path).replace("'", "'\\''") + "'"
