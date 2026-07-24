"""Offline ad/telemetry blocking for a BlueStacks instance's guest hosts file.

Why this exists, and what it does NOT do
----------------------------------------
Apps running inside the emulator phone home to ad networks and analytics
endpoints.  The surgical, emulator-only fix is the classic Android ad-block
approach: null-route the ad/tracker domains in the guest's
``/system/etc/hosts``.  This affects **only the emulator's guest**, never the
user's Windows machine (unlike a system-wide hosts edit), and it's fully
reversible.

**It cannot block BlueStacks' own ads.**  Those are served by ``HD-Player.exe``
on Windows, not by the guest -- proven by a live capture in which the player kept
open connections to googlesyndication, inmobi, rubiconproject and adnxs while the
Android guest was **completely powered off**.  Applying this block changed the
player's ad endpoints not at all (40 before, 40 after, on 5.22.250.1015).  For
those use :mod:`ad_settings`, which turns off BlueStacks' own config switches and
measured 40 -> 0 on the same rig.  This module is for in-guest app traffic; the
two are complementary, not alternatives.

A hosts file also has **no wildcard support**: an entry for ``doubleclick.net``
does nothing for ``cm.g.doubleclick.net`` or ``pagead2.googlesyndication.com``.
Real ad traffic is overwhelmingly subdomains, so the observed ones are enumerated
explicitly in ``HOST_BLOCKLIST``.

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
down, **and a patched engine**.  This edits the guest system image, and BlueStacks
shuts down an instance whose system image was modified ("...illegally
tampered...") unless ``integrity_patch`` has been applied -- root is not required
to trip that check, any modification does it.
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
# mobile-attribution SDKs, and the exchanges caught in a live capture. NOT
# Google Play / GMS infrastructure, NOT an app's own backend. Extend from a live
# capture of the target build (see module docstring).
#
# These are apex domains; each also gets a "www." alias. A hosts file has NO
# wildcard support, so an apex entry does not cover subdomains -- and real
# ad traffic is almost entirely subdomains. The observed ones therefore have to
# be listed explicitly in HOST_BLOCKLIST below.
BLOCKLIST = (
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
    # ad exchange (the earlier list had "rtbhouse.net", which does not resolve --
    # the real endpoint seen in a capture is esp.rtbhouse.com, below)
    "rtbhouse.com",
)

# Fully-qualified hostnames, listed individually because a hosts file cannot
# wildcard a domain. Every one of these was observed live on 5.22.250.1015 while
# an apex-only blocklist was already applied -- i.e. these are exactly the
# endpoints that the apex entries above silently fail to cover.
HOST_BLOCKLIST = (
    # google ad serving (subdomains of already-listed apexes)
    "ad.doubleclick.net",
    "cm.g.doubleclick.net",
    "static.doubleclick.net",
    "googleads.g.doubleclick.net",
    "securepubads.g.doubleclick.net",
    "pagead2.googlesyndication.com",
    "tpc.googlesyndication.com",
    "ep1.adtrafficquality.google",
    "ep2.adtrafficquality.google",
    # inmobi
    "w.inmobi.com",
    "api.w.inmobi.com",
    "sync.inmobi.com",
    # exchanges / RTB / cookie-sync seen in the live capture
    "esp.rtbhouse.com",
    "ib.adnxs.com",
    "secure.adnxs.com",
    "fastlane.rubiconproject.com",
    "pixel-us-east.rubiconproject.com",
    "token.rubiconproject.com",
    "rtb.openx.net",
    "us-u.openx.net",
    "eu-u.openx.net",
    "google-bidout-d.openx.net",
    "oa.openxcdn.net",
    "hbopenbid.pubmatic.com",
    "ssum-sec.casalemedia.com",
    "js-sec.indexww.com",
    "direct.adsrvr.org",
    "btlr.sharethrough.com",
    "ads.betweendigital.com",
)


def _instance_paths(instance_dir: str) -> tuple[str, str]:
    return (os.path.join(instance_dir, _BACKUP_NAME),
            os.path.join(instance_dir, _STATE_NAME))


def blocked_hosts() -> tuple[str, ...]:
    """Every hostname the block null-routes, de-duplicated and ordered.

    Apex domains contribute their ``www.`` alias; ``HOST_BLOCKLIST`` entries are
    used verbatim, since they are the subdomains an apex entry cannot cover.
    """
    seen: dict[str, None] = {}
    for d in BLOCKLIST:
        seen.setdefault(d, None)
        seen.setdefault("www.%s" % d, None)
    for h in HOST_BLOCKLIST:
        seen.setdefault(h, None)
    return tuple(seen)


def _block_text() -> str:
    """The marked block of ``0.0.0.0 <host>`` lines."""
    lines = [_BLOCK_BEGIN]
    for host in blocked_hosts():
        lines.append("0.0.0.0 %s" % host)
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
            "domains": len(blocked_hosts()),
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
    with _es._Attached(root_vhd, progress=_p) as att:
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
        _p("Writing %d blocked hostnames into guest hosts..." % len(blocked_hosts()))
        out = _write_hosts(dev, sysroot, new, env)
        written = _dump_hosts(dev, sysroot, env)
        if not has_block(written):
            raise RuntimeError("hosts block not written (debugfs: %s)" % _ms._errtail(out))
        _p("Verifying filesystem (e2fsck)...")
        if not _es._fsck_ok(dev, env):
            raise RuntimeError("e2fsck reported errors after writing hosts")
    _write_state(instance_dir, True)
    return ["Blocked %d ad/tracker hostnames in the guest hosts file."
            % len(blocked_hosts())]


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
    with _es._Attached(root_vhd, progress=_p) as att:
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
