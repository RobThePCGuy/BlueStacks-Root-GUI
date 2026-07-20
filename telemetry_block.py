"""Offline ad/telemetry blocking for a BlueStacks instance's guest hosts file.

Why this exists
---------------
BlueStacks and the apps inside it phone home to ad networks and analytics
endpoints -- and the in-app "disable ads" toggle only covers a fraction of it
(a live capture still shows the player reaching an ad-exchange like rtbhouse
with that toggle off).  The surgical, emulator-only fix is the classic Android
ad-block approach: null-route the ad/tracker domains in the guest's
``/system/etc/hosts``.  This affects **only the emulator's guest**, never the
user's Windows machine (unlike a system-wide hosts edit), and it's fully
reversible.

How it works
------------
``/system/etc/hosts`` lives in the guest system tree inside ``Root.vhd`` (mounted
read-only by the hypervisor at runtime), so it's edited **offline** while the
instance is shut down -- the same ``diskpart``-attach + bundled ``debugfs`` path
the Magisk install uses.  ``apply`` backs up the current hosts (host-side
sidecar), then writes ``<original, minus any prior block> + a marked block`` of
``0.0.0.0 <domain>`` lines.  ``remove`` restores the backup.  Because the block
lives between explicit markers, re-applying is idempotent and removal is exact.

The block list is intentionally conservative: clear third-party ad/analytics
networks plus the ad exchange seen in a live capture -- nothing that Google Play,
GMS, or an app's own servers need.  It's meant to be extended from a live capture
of a given build (``README`` in this module explains the capture step).

Note: ``Root.vhd`` is shared across all instances of one Android version, so the
block applies to every instance of that version -- which is what you want for a
telemetry block.

Requirements: Windows, Administrator (raw-disk access + diskpart), instance shut
down.
"""
from __future__ import annotations

import datetime
import json
import logging
import os
import tempfile

import ext4_symlink as _es
import magisk_system as _ms

logger = logging.getLogger(__name__)

_BLOCK_BEGIN = "# >>> BlueStacksRootGUI ad/telemetry block >>>"
_BLOCK_END = "# <<< BlueStacksRootGUI ad/telemetry block <<<"
_BACKUP_NAME = ".hosts_prelock.bak"       # host-side: original hosts before first block
_STATE_NAME = ".telemetry_block.json"     # host-side: applied? + provenance

# Null-routed domains. Conservative on purpose -- clear third-party ad networks,
# mobile-attribution SDKs, and the ad exchange caught in a live capture. NOT
# Google Play / GMS infrastructure, NOT an app's own backend. Extend from a live
# capture of the target build (see module docstring).
BLOCKLIST = (
    # ad exchange seen phoning home from the player itself (live capture)
    "rtbhouse.net",
    # generic ad serving
    "doubleclick.net",
    "googlesyndication.com",
    "googleadservices.com",
    # third-party mobile ad networks
    "applovin.com",
    "applvn.com",
    "adcolony.com",
    "chartboost.com",
    "inmobi.com",
    "vungle.com",
    "tapjoy.com",
    "mopub.com",
    "supersonicads.com",
    "ironsrc.com",
    "unityads.unity3d.com",
    "flurry.com",
    "adtilt.com",
    # mobile attribution / tracking SDKs
    "appsflyer.com",
    "adjust.com",
    "kochava.com",
)


def _instance_paths(instance_dir: str) -> tuple[str, str]:
    return (os.path.join(instance_dir, _BACKUP_NAME),
            os.path.join(instance_dir, _STATE_NAME))


def _block_text() -> str:
    """The marked block of ``0.0.0.0 <domain>`` lines (both the bare domain and
    its ``www.`` alias)."""
    lines = [_BLOCK_BEGIN]
    for d in BLOCKLIST:
        lines.append("0.0.0.0 %s" % d)
        lines.append("0.0.0.0 www.%s" % d)
    lines.append(_BLOCK_END)
    return "\n".join(lines) + "\n"


def _strip_block(text: str) -> str:
    """``text`` with any existing marked block removed (idempotent re-apply)."""
    out: list[str] = []
    skipping = False
    for line in text.splitlines():
        s = line.strip()
        if s == _BLOCK_BEGIN:
            skipping = True
            continue
        if s == _BLOCK_END:
            skipping = False
            continue
        if not skipping:
            out.append(line)
    body = "\n".join(out).rstrip("\n")
    return (body + "\n") if body else ""


def has_block(text: str) -> bool:
    return _BLOCK_BEGIN in text


def _hosts_ext4(sysroot: str) -> str:
    return "%s/etc/hosts" % sysroot


def _dump_hosts(device: str, sysroot: str, env: dict) -> str:
    """Return the current guest hosts content (empty string if absent)."""
    fd, tmp = tempfile.mkstemp(suffix="-hosts")
    os.close(fd)
    try:
        _es._run([_es._debugfs(), "-R",
                  "dump %s %s" % (_hosts_ext4(sysroot), _ms._cygpath(tmp)), device],
                 env=env)
        try:
            with open(tmp, encoding="utf-8", errors="replace") as f:
                return f.read()
        except OSError:
            return ""
    finally:
        try:
            os.unlink(tmp)
        except OSError:
            pass


def _write_hosts(device: str, sysroot: str, content: str, env: dict) -> str:
    """Write ``content`` to the guest hosts (0644 root:root). Returns debugfs
    output. Rewrites in place: rm then write a bare name in the CWD (debugfs
    quirk), matching magisk_system's writer."""
    fd, tmp = tempfile.mkstemp(suffix="-hosts")
    with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as f:
        f.write(content)
    try:
        etcdir = "%s/etc" % sysroot
        hosts = _hosts_ext4(sysroot)
        cmds = ["cd %s" % etcdir, "rm hosts",
                "write %s hosts" % _ms._dq(_ms._cygpath(tmp)),
                "sif %s mode 0100644" % hosts,
                "sif %s uid 0" % hosts, "sif %s gid 0" % hosts]
        return _es._run_script(device, cmds, env)
    finally:
        try:
            os.unlink(tmp)
        except OSError:
            pass


def _write_state(instance_dir: str, applied: bool) -> None:
    _, state = _instance_paths(instance_dir)
    if not applied:
        try:
            os.unlink(state)
        except OSError:
            pass
        return
    data = {"telemetry_block": True,
            "domains": len(BLOCKLIST),
            "applied_at": datetime.datetime.now().isoformat(timespec="seconds")}
    try:
        with open(state, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
    except OSError as exc:
        logger.warning("could not write telemetry-block state: %s", exc)


def status(instance_dir: str) -> dict | None:
    """The block state sidecar, or None if not applied. For the GUI."""
    _, state = _instance_paths(instance_dir)
    try:
        with open(state, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def apply(instance_dir: str, progress=None) -> list[str]:
    """Null-route the ad/telemetry domains in the instance's guest hosts.
    Backs up the original once, is idempotent, and verifies the filesystem."""
    def _p(msg: str) -> None:
        logger.info(msg)
        if progress:
            progress(msg)

    if not _es.tools_available():
        raise RuntimeError("bundled e2fsprogs (debugfs) not found")
    root_vhd = _ms._resolve_root_vhd(instance_dir)
    backup, _ = _instance_paths(instance_dir)
    env = _es._tool_env()

    _p("Attaching Root.vhd (blocking ad/telemetry hosts)...")
    with _es._Attached(root_vhd) as att:
        dev = att.device
        sysroot = _ms._find_system_root(dev, env)
        current = _dump_hosts(dev, sysroot, env)
        base = _strip_block(current)
        # Preserve the pre-block original once, so remove() restores it exactly.
        if not os.path.isfile(backup):
            try:
                with open(backup, "w", encoding="utf-8", newline="\n") as f:
                    f.write(base)
            except OSError as exc:
                logger.warning("could not save hosts backup: %s", exc)
        new = base + _block_text()
        _p("Writing %d blocked domains into guest hosts..." % len(BLOCKLIST))
        out = _write_hosts(dev, sysroot, new, env)
        written = _dump_hosts(dev, sysroot, env)
        if not has_block(written):
            raise RuntimeError("hosts block not written (debugfs: %s)" % _ms._errtail(out))
        _p("Verifying filesystem (e2fsck)...")
        if not _es._fsck_ok(dev, env):
            raise RuntimeError("e2fsck reported errors after writing hosts")
    _write_state(instance_dir, True)
    return ["Blocked %d ad/telemetry domains in the guest hosts file." % len(BLOCKLIST)]


def remove(instance_dir: str, progress=None) -> list[str]:
    """Restore the guest hosts to its pre-block state."""
    def _p(msg: str) -> None:
        logger.info(msg)
        if progress:
            progress(msg)

    if not _es.tools_available():
        return ["e2fsprogs unavailable -- nothing to remove"]
    try:
        root_vhd = _ms._resolve_root_vhd(instance_dir)
    except RuntimeError:
        return ["Root.vhd not found -- nothing to remove"]
    backup, _ = _instance_paths(instance_dir)
    env = _es._tool_env()

    _p("Attaching Root.vhd (restoring guest hosts)...")
    with _es._Attached(root_vhd) as att:
        dev = att.device
        sysroot = _ms._find_system_root(dev, env)
        if os.path.isfile(backup):
            with open(backup, encoding="utf-8", errors="replace") as f:
                base = f.read()
        else:  # no backup: just strip our block from whatever is there
            base = _strip_block(_dump_hosts(dev, sysroot, env))
        if not base.strip():
            base = "127.0.0.1\tlocalhost\n::1\t\tlocalhost\n"  # stock fallback
        _write_hosts(dev, sysroot, base, env)
        if not _es._fsck_ok(dev, env):
            raise RuntimeError("e2fsck reported errors after restoring hosts")
    _write_state(instance_dir, False)
    try:
        os.unlink(backup)
    except OSError:
        pass
    return ["Restored the guest hosts file (ad/telemetry block removed)."]
