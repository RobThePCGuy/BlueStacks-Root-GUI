"""Acquire the pinned Kyubi payload and extract the native tools needed for
offline system-mode installation.

Kyubi is RobThePCGuy's stripped, emulator-only Magisk (Kitsune lineage): x86 /
x86_64 only, no magiskboot / boot-image path, system-mode install. The APK is
**downloaded on demand, not vendored** -- it is GPLv3, so this project
redistributes none of it; instead it resolves the **latest** Kyubi release from
the GitHub API, verifies the downloaded APK against that release asset's own
published SHA-256 digest, and caches it.  The native tools ship inside the APK at
``lib/<abi>/lib*.so``; we extract the ``x86_64`` set (BlueStacks guests are
x86_64) plus the 32-bit ``magisk32`` so 32-bit guest apps get root too, renaming
``lib*.so`` to the plain names the daemon expects in ``/data/adb/magisk``.

**Auto-latest, still hash-verified.** There is no per-release SHA to bump: every
cut of a new Kyubi release is picked up automatically, and integrity is kept by
verifying the bytes against the digest GitHub publishes for that same asset (a
sibling ``<asset>.sha256`` file is used as a fallback if the API digest is
absent). It fails closed -- if no digest can be resolved, nothing is installed.
Pin a specific build with the ``KYUBI_PAYLOAD_TAG`` env var if ever needed.

Credit: Magisk (c) topjohnwu; Magisk Delta (c) HuskyDG; Kitsune build by
1q23lyc45; Kyubi build by RobThePCGuy.  All GPLv3.
"""
from __future__ import annotations

import json
import logging
import os
import shutil
import urllib.error
import urllib.request
import zipfile

import payload_fetch

logger = logging.getLogger(__name__)

# --- Auto-latest payload (GitHub release, hash-verified) -------------------
# No per-release SHA to bump: fetch_apk() resolves the latest Kyubi release from
# the GitHub API and verifies the APK against that asset's own published digest.
# Kyubi = RobThePCGuy's stripped, emulator-only Magisk (Kitsune lineage): x86 only,
# no magiskboot / boot-image path, system-mode install.
PAYLOAD_REPO = "RobThePCGuy/Kyubi"
PAYLOAD_ASSET_NAME = "app-release.apk"       # the release asset we install
PAYLOAD_NAME = "Kyubi-app-release.apk"       # cache filename on disk
_API = "https://api.github.com/repos/%s/releases" % PAYLOAD_REPO
LATEST_API = _API + "/latest"
TAG_API = _API + "/tags/%s"                  # used when KYUBI_PAYLOAD_TAG pins a build

# Resolved at fetch time (updated by fetch_apk); read by magisk_system for the
# install manifest. Defaults describe the "not yet fetched" state.
PAYLOAD_SHA256 = ""
PAYLOAD_VERSION = "latest (Kyubi)"

# Pin a specific release tag instead of "latest" (escape hatch), e.g.
# KYUBI_PAYLOAD_TAG=v31.0-72524ff2. Normally unset -> newest release wins.
PIN_TAG_ENV = "KYUBI_PAYLOAD_TAG"

# Local-payload override for offline validation: KYUBI_PAYLOAD_APK points at an
# APK used verbatim (no download). If KYUBI_PAYLOAD_SHA256 is also set, the file
# is checked against it; otherwise it is trusted as-is (dev/offline only).
LOCAL_PAYLOAD_ENV = "KYUBI_PAYLOAD_APK"
LOCAL_SHA_ENV = "KYUBI_PAYLOAD_SHA256"

# lib/<abi>/lib<tool>.so  ->  DATABIN tool name.  magisk64 + the x86_64 tools
# come from lib/x86_64; magisk32 from lib/x86 so 32-bit guest apps get root.
_X64 = "x86_64"
_X86 = "x86"
_TOOLS = {
    "busybox": (_X64, "libbusybox.so"),      # the daemon's environment gate
    "magisk64": (_X64, "libmagisk64.so"),    # magiskd / su (64-bit)
    "magiskinit": (_X64, "libmagiskinit.so"),
    "magiskpolicy": (_X64, "libmagiskpolicy.so"),
    # Kyubi ships no magiskboot (system-mode install never patches a boot image).
    "magisk32": (_X86, "libmagisk32.so"),    # 32-bit app root
}

# Non-lib member the system-mode install needs (the Magisk manager stub the app
# would otherwise write to /system/etc/init/magisk/stub.apk).
STUB_APK_MEMBER = "assets/stub.apk"

# APK assets/ that complete the DATABIN alongside the native binaries, so
# /data/adb/magisk matches a real Magisk install and `magisk --install-module`
# works.  Magisk aborts "Incomplete Magisk install" without util_functions.sh
# (it defines the install_module function + every helper that calls).  These are
# static build artifacts -- copied verbatim, version baked in (MAGISK_VER lives
# inside util_functions.sh) -- so, like the binaries, they're derived from the
# pinned APK, nothing captured.  Keys: DATABIN-relative path (chromeos/* keeps
# the subdir).  Values: the APK member.
_DATABIN_EXTRAS = {
    "util_functions.sh": "assets/util_functions.sh",  # the module-install gate
    "stub.apk": "assets/stub.apk",
    # Kyubi is system-mode only: no boot_patch.sh, no addon.d.sh, no chromeos
    # signing tools ship in the APK, so none are staged into the DATABIN.
}


def _record(sha256: str, version: str) -> None:
    """Remember what was actually fetched so the install manifest can stamp it."""
    global PAYLOAD_SHA256, PAYLOAD_VERSION
    PAYLOAD_SHA256 = sha256
    PAYLOAD_VERSION = version


def _open_url(req: urllib.request.Request, timeout: int = 30):
    """``urllib.request.urlopen``, but a GitHub rate-limit response (403/429) is
    turned into a clear, actionable ``RuntimeError`` instead of a raw
    ``HTTPError``. GitHub caps unauthenticated REST API requests at 60/hour per
    source IP (tightened further in May 2025), so a shared/CGNAT egress IP or
    rapid retries can trip this -- this is the only network path in the app
    that calls the GitHub API rather than a pinned direct-download URL."""
    try:
        return urllib.request.urlopen(req, timeout=timeout)
    except urllib.error.HTTPError as exc:
        if exc.code in (403, 429):
            raise RuntimeError(
                "GitHub rate-limited this request, try again later.") from exc
        raise


def _api_get(url: str):
    req = urllib.request.Request(url, headers={
        "Accept": "application/vnd.github+json",
        "User-Agent": "BlueStacks-Root-GUI",
        "X-GitHub-Api-Version": "2022-11-28",
    })
    with _open_url(req) as r:
        return json.load(r)


# Trust-model note: unlike rezygisk_payload/lsposed_payload (which pin both the
# download URL and the SHA-256 in source), this resolves the *latest* release
# and verifies against that release's own published digest -- TOFU per
# release, not a pinned hash like the sibling ReZygisk/LSPosed modules. This is
# currently unpinned because Kyubi is the maintainer's own repo; if this
# pattern is ever extended to fetch a genuinely third-party payload, it should
# use the pinned-hash model instead.
def _resolve_release():
    """Resolve the Kyubi release to install -> (tag, apk_url, expected_sha256).

    Uses the newest release unless ``KYUBI_PAYLOAD_TAG`` pins one.  The expected
    hash comes from the release asset's own ``digest`` (``sha256:...``); if GitHub
    hasn't populated it, a sibling ``<asset>.sha256`` release asset is read as a
    fallback.  ``expected_sha256`` is ``""`` when neither is available -- the
    caller fails closed rather than install something unverified.
    """
    tag_pin = os.environ.get(PIN_TAG_ENV)
    rel = _api_get(TAG_API % tag_pin if tag_pin else LATEST_API)
    tag = rel.get("tag_name") or (tag_pin or "?")
    assets = {a.get("name"): a for a in rel.get("assets", []) if a.get("name")}

    apk = assets.get(PAYLOAD_ASSET_NAME)
    if not apk or not apk.get("browser_download_url"):
        raise RuntimeError(
            "Kyubi release %s has no %s asset." % (tag, PAYLOAD_ASSET_NAME))

    sha = ""
    digest = apk.get("digest") or ""            # e.g. "sha256:deadbeef..."
    if digest.lower().startswith("sha256:"):
        sha = digest.split(":", 1)[1].strip().lower()
    else:                                       # fallback: a published checksum asset
        side = assets.get(PAYLOAD_ASSET_NAME + ".sha256")
        if side and side.get("browser_download_url"):
            with _open_url(urllib.request.Request(
                    side["browser_download_url"],
                    headers={"User-Agent": "BlueStacks-Root-GUI"})) as r:
                # accept "<hex>" or "<hex>  filename"
                sha = r.read().decode("utf-8", "replace").split()[0].strip().lower()

    return tag, apk["browser_download_url"], sha


def fetch_apk(cache_dir: str, progress=None) -> str:
    """Return a path to the verified latest Kyubi APK, downloading + caching.

    Resolves the newest release (or ``KYUBI_PAYLOAD_TAG``), verifies the bytes
    against the release's published SHA-256, and caches.  Fails closed: raises
    ``RuntimeError`` if no digest can be resolved or the hash doesn't match.
    """
    def _p(msg: str) -> None:
        logger.info(msg)
        if progress:
            progress(msg)

    os.makedirs(cache_dir, exist_ok=True)
    dest = os.path.join(cache_dir, PAYLOAD_NAME)

    # Offline override: use a local Kyubi APK verbatim (dev/validation).
    local = os.environ.get(LOCAL_PAYLOAD_ENV)
    if local and os.path.isfile(local):
        got = payload_fetch.sha256_file(local)
        want = (os.environ.get(LOCAL_SHA_ENV) or "").strip().lower()
        if want and got != want:
            raise RuntimeError(
                "%s SHA-256 mismatch: got %s, expected %s"
                % (LOCAL_PAYLOAD_ENV, got, want))
        shutil.copyfile(local, dest)
        _record(got, "local (Kyubi)")
        _p("Kyubi payload sourced from %s%s."
           % (LOCAL_PAYLOAD_ENV, " (verified)" if want else ""))
        return dest

    _p("Resolving latest Kyubi release...")
    tag, url, expected = _resolve_release()
    if not expected:
        raise RuntimeError(
            "Kyubi release %s exposes no SHA-256 digest (nor a %s.sha256 asset); "
            "refusing to install unverified. Pin a known build with %s."
            % (tag, PAYLOAD_ASSET_NAME, PIN_TAG_ENV))

    payload_fetch.fetch_verified(url, dest, expected, label="Kyubi %s" % tag, progress=progress)
    _record(expected, "%s (Kyubi)" % tag)
    return dest


def latest_identity(progress=None) -> tuple[str, str]:
    """The version label and SHA-256 of the payload that would install *now*,
    resolved WITHOUT downloading it.

    Mirrors ``fetch_apk``'s source selection so the answer matches what an
    install would actually use: the ``KYUBI_PAYLOAD_APK`` local override wins and
    returns that file's hash; otherwise the newest Kyubi release is resolved and
    its published digest returned. Used by the "Update Magisk" check to compare
    against the installed manifest's ``payload_sha256`` before doing any work.

    Returns ``(version_label, sha256)``. Raises ``RuntimeError`` if no digest is
    resolvable (the same fail-closed rule ``fetch_apk`` uses), so an update check
    never silently reports "up to date" on a lookup it couldn't complete.
    """
    def _p(msg: str) -> None:
        logger.info(msg)
        if progress:
            progress(msg)

    local = os.environ.get(LOCAL_PAYLOAD_ENV)
    if local and os.path.isfile(local):
        _p("Checking the local Kyubi payload...")
        return "local (Kyubi)", payload_fetch.sha256_file(local)

    _p("Checking the latest Kyubi release...")
    tag, _url, expected = _resolve_release()
    if not expected:
        raise RuntimeError(
            "Kyubi release %s exposes no SHA-256 digest, so an update can't be "
            "checked. Pin a known build with %s." % (tag, PIN_TAG_ENV))
    return "%s (Kyubi)" % tag, expected.lower()


def extract_tools(apk_path: str, dest_dir: str, progress=None) -> dict[str, str]:
    """Extract the Magisk native tools from the APK into ``dest_dir``.

    Returns ``{tool_name: path}``.  Files are written under their plain names
    (busybox, magisk64, ...) -- the form Magisk's daemon expects in
    ``/data/adb/magisk`` -- not the ``lib*.so`` wrapper.
    """
    def _p(msg: str) -> None:
        logger.info(msg)
        if progress:
            progress(msg)

    os.makedirs(dest_dir, exist_ok=True)
    out: dict[str, str] = {}
    try:
        with zipfile.ZipFile(apk_path) as z:
            members = set(z.namelist())
            for tool, (abi, soname) in _TOOLS.items():
                member = "lib/%s/%s" % (abi, soname)
                if member not in members:
                    raise RuntimeError(
                        "payload is missing %s (expected %s in the APK)" % (tool, member))
                target = os.path.join(dest_dir, tool)
                with z.open(member) as src, open(target, "wb") as dst:
                    shutil.copyfileobj(src, dst)
                out[tool] = target
    except Exception:
        for p in out.values():  # don't leave a half-populated tool dir behind
            try:
                os.unlink(p)
            except OSError:
                pass
        raise
    _p("Extracted %d Magisk tools (%s)." % (len(out), ", ".join(sorted(out))))
    return out


def extract_stub_apk(apk_path: str, dest_dir: str) -> str:
    """Extract the Magisk manager stub (``assets/stub.apk``) from the APK; return
    its path.  Needed by the system-mode install (goes to
    ``/system/etc/init/magisk/stub.apk``)."""
    os.makedirs(dest_dir, exist_ok=True)
    dest = os.path.join(dest_dir, "stub.apk")
    with zipfile.ZipFile(apk_path) as z:
        if STUB_APK_MEMBER not in set(z.namelist()):
            raise RuntimeError("payload is missing %s" % STUB_APK_MEMBER)
        with z.open(STUB_APK_MEMBER) as src, open(dest, "wb") as dst:
            shutil.copyfileobj(src, dst)
    return dest


def extract_databin_extras(apk_path: str, dest_dir: str, progress=None) -> dict[str, str]:
    """Extract the non-binary DATABIN files (util scripts, chromeos signing keys,
    stub) from the APK into ``dest_dir``, preserving the ``chromeos/`` subdir.

    Returns ``{databin_relpath: host_path}`` (e.g. ``"chromeos/futility"``).
    Combined with :func:`extract_tools`' binaries this yields a *complete*
    ``/data/adb/magisk`` -- without ``util_functions.sh`` Magisk aborts
    ``--install-module`` with "Incomplete Magisk install".
    """
    def _p(msg: str) -> None:
        logger.info(msg)
        if progress:
            progress(msg)

    os.makedirs(dest_dir, exist_ok=True)
    out: dict[str, str] = {}
    try:
        with zipfile.ZipFile(apk_path) as z:
            members = set(z.namelist())
            for rel, member in _DATABIN_EXTRAS.items():
                if member not in members:
                    raise RuntimeError(
                        "payload is missing %s (expected %s in the APK)" % (rel, member))
                target = os.path.join(dest_dir, rel.replace("/", os.sep))
                os.makedirs(os.path.dirname(target), exist_ok=True)
                with z.open(member) as src, open(target, "wb") as dst:
                    shutil.copyfileobj(src, dst)
                out[rel] = target
    except Exception:
        for p in out.values():  # don't leave a half-populated dir behind
            try:
                os.unlink(p)
            except OSError:
                pass
        raise
    _p("Extracted %d DATABIN support files (%s)." % (len(out), ", ".join(sorted(out))))
    return out
