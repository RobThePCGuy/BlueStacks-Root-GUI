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

**Offline first.** The network is only a fallback: if a Kyubi APK is present
locally -- ``KYUBI_PAYLOAD_APK`` if set, else ``magisk_assets/kyubi/`` next to
this app (or next to the exe / inside the PyInstaller bundle) -- it is used
verbatim and no request is made at all.  That is the default path, because the
GitHub REST API is capped at 60 unauthenticated requests per hour per source IP
and rate-limits (HTTP 403 "rate limit exceeded") routinely, which used to fail
an otherwise perfectly offline install.  A locally supplied APK can be pinned
with a sibling ``app-release.apk.sha256`` file (or ``KYUBI_PAYLOAD_SHA256``);
without one it is trusted as-is but still shape-checked, and a wrong/changed
file fails closed.  Nothing here vendors Kyubi: the drop-in file is the user's
own and is git-ignored, so this project still redistributes none of it.

Credit: Magisk (c) topjohnwu; Magisk Delta (c) HuskyDG; Kitsune build by
1q23lyc45; Kyubi build by RobThePCGuy.  All GPLv3.
"""
from __future__ import annotations

import json
import logging
import os
import shutil
import sys
import urllib.error
import urllib.request
import zipfile

import payload_fetch

logger = logging.getLogger(__name__)

# --- Auto-latest payload (GitHub release, hash-verified) -------------------
# No per-release SHA to bump: fetch_apk() resolves the newest Kyubi release from
# the GitHub API and verifies the APK against that asset's own published digest.
# "Newest" includes prereleases: every Kyubi build is published as a prerelease,
# and /releases/latest skips those, which left the GUI on an old promoted build.
# Kyubi = RobThePCGuy's stripped, emulator-only Magisk (Kitsune lineage): x86 only,
# no magiskboot / boot-image path, system-mode install.
PAYLOAD_REPO = "RobThePCGuy/Kyubi"
PAYLOAD_ASSET_NAME = "app-release.apk"       # the release asset we install
PAYLOAD_NAME = "Kyubi-app-release.apk"       # cache filename on disk
_API = "https://api.github.com/repos/%s/releases" % PAYLOAD_REPO
RELEASES_API = _API + "?per_page=30"         # newest first, prereleases included
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

# --- Offline payload: the default source whenever a local APK exists ---------
# Drop a Kyubi APK at <app dir>/magisk_assets/kyubi/app-release.apk (the asset
# name the GitHub release uses) and every install/update/manager step runs with
# no network access at all. This is the default path on purpose: the GitHub API
# rate-limits unauthenticated callers (HTTP 403 "rate limit exceeded") often
# enough that the download was the one flaky step left in an otherwise fully
# offline tool. The file is user-supplied and git-ignored -- Kyubi is GPLv3 and
# this project redistributes none of it -- so a release build only carries one
# if whoever built it chose to put it there.
BUNDLED_DIR = os.path.join("magisk_assets", "kyubi")
BUNDLED_APK_NAME = "app-release.apk"        # same name as the release asset
SHA_SIDECAR_SUFFIX = ".sha256"              # optional "<hex>" pin next to the APK
LOCAL_VERSION_LABEL = "local (Kyubi)"       # manifest version for a local payload
CACHED_VERSION_LABEL = "cached (Kyubi)"     # ...for a cached earlier download

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

# BlueStacks Air (Apple Silicon) runs a 64-bit-only arm64 guest: no 32-bit ABI,
# so no magisk32. Needs a Kyubi release built with arm64-v8a.
_ARM64 = "arm64-v8a"
_TOOLS_ARM64 = {
    "busybox": (_ARM64, "libbusybox.so"),
    "magisk64": (_ARM64, "libmagisk64.so"),
    "magiskinit": (_ARM64, "libmagiskinit.so"),
    "magiskpolicy": (_ARM64, "libmagiskpolicy.so"),
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


def _app_roots() -> list[str]:
    """Directories that may hold ``magisk_assets/kyubi``, most specific first.

    Frozen (PyInstaller) build: the bundle's ``sys._MEIPASS`` and the folder the
    exe itself lives in, so a payload can be dropped next to a downloaded exe
    without rebuilding it. Running from source: this module's directory.
    """
    roots: list[str] = []
    if getattr(sys, "frozen", False):
        meipass = getattr(sys, "_MEIPASS", "")
        if meipass:
            roots.append(meipass)
        exe_dir = os.path.dirname(os.path.abspath(sys.executable))
        if exe_dir not in roots:
            roots.append(exe_dir)
    else:
        roots.append(os.path.dirname(os.path.abspath(__file__)))
    return roots


def bundled_apk_path() -> str:
    """The offline payload the app would use *now*: an existing drop-in APK, or
    -- when there is none -- the canonical path to put one at, so callers can
    quote it in messages and docs."""
    roots = _app_roots()
    for root in roots:
        candidate = os.path.join(root, BUNDLED_DIR, BUNDLED_APK_NAME)
        if os.path.isfile(candidate):
            return candidate
    return os.path.join(roots[0], BUNDLED_DIR, BUNDLED_APK_NAME)


def _declared_sha256(apk_path: str) -> str:
    """The SHA-256 a local APK is *supposed* to have: the ``<apk>.sha256``
    sidecar (``"<hex>"`` or ``"<hex>  filename"``), else ``KYUBI_PAYLOAD_SHA256``,
    else ``""`` meaning "unpinned, trust the file as-is"."""
    side = apk_path + SHA_SIDECAR_SUFFIX
    if os.path.isfile(side):
        try:
            with open(side, encoding="utf-8", errors="replace") as f:
                fields = f.read().split()
        except OSError:
            return ""
        return fields[0].strip().lower() if fields else ""
    return (os.environ.get(LOCAL_SHA_ENV) or "").strip().lower()


def _local_sha256(apk_path: str) -> str:
    """SHA-256 of a local payload, fail-closed against a declared pin."""
    got = payload_fetch.sha256_file(apk_path)
    want = _declared_sha256(apk_path)
    if want and got != want:
        raise RuntimeError(
            "Kyubi payload SHA-256 mismatch for %s: got %s, expected %s."
            % (apk_path, got, want))
    return got


def _check_payload_shape(apk_path: str) -> None:
    """Refuse a local file that is not a usable Kyubi payload, before any disk is
    touched.

    A hand-downloaded APK is the likeliest thing to be wrong (an HTML error page
    saved as .apk, a truncated download, the wrong repo's release), and the
    symptom would otherwise surface much later as "payload is missing lib/x86/
    libmagisk32.so" from the extractors. A payload qualifies when it carries the
    Magisk binaries for at least one ABI -- x86/x86_64 for BlueStacks for
    Windows, arm64-v8a for BlueStacks Air -- plus the DATABIN extras, so a
    Windows-only and an Air-only Kyubi build both pass.
    """
    try:
        with zipfile.ZipFile(apk_path) as z:
            members = set(z.namelist())
    except (zipfile.BadZipFile, OSError) as exc:
        raise RuntimeError(
            "%s is not a usable Kyubi APK (%s). Download %s from "
            "https://github.com/%s/releases and put it back there."
            % (apk_path, exc, BUNDLED_APK_NAME, PAYLOAD_REPO)) from exc

    missing_extras = [m for m in _DATABIN_EXTRAS.values() if m not in members]
    families = {"x86/x86_64": _TOOLS, "arm64-v8a": _TOOLS_ARM64}
    if not missing_extras and any(
            all("lib/%s/%s" % (abi, soname) in members for abi, soname in tools.values())
            for tools in families.values()):
        return
    missing_bins = ["lib/%s/%s" % (abi, soname) for abi, soname in _TOOLS.values()
                    if "lib/%s/%s" % (abi, soname) not in members]
    raise RuntimeError(
        "%s is not a usable Kyubi APK: no complete ABI set inside it (missing %s) "
        "and/or missing %s. Download %s from https://github.com/%s/releases."
        % (apk_path, ", ".join(missing_bins) or "(all x86 files present)",
           ", ".join(missing_extras) or "(no extras missing)",
           BUNDLED_APK_NAME, PAYLOAD_REPO))


def local_payload() -> tuple[str, str] | None:
    """``(path, source_label)`` of the local Kyubi APK to install offline, or
    ``None`` when there is none and the release has to be fetched.

    ``KYUBI_PAYLOAD_APK`` wins when set -- and pointing it at a missing file is
    an error rather than a silent fall-back to the network, because whoever set
    it explicitly asked for offline. Otherwise the bundled drop-in is used.
    """
    explicit = (os.environ.get(LOCAL_PAYLOAD_ENV) or "").strip()
    if explicit:
        if not os.path.isfile(explicit):
            raise RuntimeError(
                "%s points at %s, which does not exist." % (LOCAL_PAYLOAD_ENV, explicit))
        return explicit, "explicit"
    bundled = bundled_apk_path()
    if os.path.isfile(bundled):
        return bundled, "bundled"
    return None


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
                "GitHub rate-limited this request, try again later. To skip the "
                "network entirely, download %s from "
                "https://github.com/%s/releases and save it as %s."
                % (BUNDLED_APK_NAME, PAYLOAD_REPO, bundled_apk_path())) from exc
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

    Uses the newest published release (prereleases included) that carries the
    APK, unless ``KYUBI_PAYLOAD_TAG`` pins one.  The expected
    hash comes from the release asset's own ``digest`` (``sha256:...``); if GitHub
    hasn't populated it, a sibling ``<asset>.sha256`` release asset is read as a
    fallback.  ``expected_sha256`` is ``""`` when neither is available -- the
    caller fails closed rather than install something unverified.
    """
    tag_pin = os.environ.get(PIN_TAG_ENV)
    if tag_pin:
        rel = _api_get(TAG_API % tag_pin)
    else:
        releases = sorted(_api_get(RELEASES_API),
                          key=lambda r: r.get("published_at") or "", reverse=True)
        rel = next((r for r in releases
                    if not r.get("draft")
                    and any(a.get("name") == PAYLOAD_ASSET_NAME
                            for a in r.get("assets", []))), None)
        if rel is None:
            raise RuntimeError(
                "No Kyubi release with %s was found." % PAYLOAD_ASSET_NAME)
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
    """Return a path to a usable, verified Kyubi APK -- offline when possible.

    Order of preference:
      1. ``KYUBI_PAYLOAD_APK`` (explicit path; an error if it is missing);
      2. the drop-in ``magisk_assets/kyubi/app-release.apk``;
      3. otherwise resolve the newest release (or ``KYUBI_PAYLOAD_TAG``),
         verify it against that release's published SHA-256, and cache it;
      4. if step 3 fails and an earlier verified copy is cached, reuse it.

    Steps 1-2 make no request at all, so the default install works with no
    network. Fails closed either way: no resolvable digest, a hash mismatch, or
    a file that is not a Kyubi payload raises ``RuntimeError`` rather than
    installing something unverified.
    """
    def _p(msg: str) -> None:
        logger.info(msg)
        if progress:
            progress(msg)

    os.makedirs(cache_dir, exist_ok=True)
    dest = os.path.join(cache_dir, PAYLOAD_NAME)

    # Offline payload first: no request at all when a local APK is available.
    local = local_payload()
    if local:
        path, source = local
        _check_payload_shape(path)          # refuse a wrong/truncated download early
        sha = _local_sha256(path)           # honours a sidecar/env pin, fail-closed
        _record(sha, LOCAL_VERSION_LABEL)
        _p("Using the %s Kyubi payload at %s%s."
           % (source, path, " (SHA-256 verified)" if _declared_sha256(path) else ""))
        return path

    try:
        _p("Resolving latest Kyubi release...")
        tag, url, expected = _resolve_release()
        if not expected:
            raise RuntimeError(
                "Kyubi release %s exposes no SHA-256 digest (nor a %s.sha256 asset); "
                "refusing to install unverified. Pin a known build with %s, or put "
                "an APK at %s to install offline."
                % (tag, PAYLOAD_ASSET_NAME, PIN_TAG_ENV, bundled_apk_path()))

        payload_fetch.fetch_verified(url, dest, expected, label="Kyubi %s" % tag,
                                     progress=progress)
    except Exception as exc:
        # Offline, rate-limited, or the release moved: a copy this app verified on
        # an earlier run beats failing an install that needs no network anyway.
        if not os.path.isfile(dest):
            raise
        _check_payload_shape(dest)
        sha = payload_fetch.sha256_file(dest)
        _record(sha, CACHED_VERSION_LABEL)
        _p("Could not fetch a fresh Kyubi release (%s); using the payload cached at "
           "%s from an earlier verified download." % (exc, dest))
        return dest

    _record(expected, "%s (Kyubi)" % tag)
    return dest


def latest_identity(progress=None) -> tuple[str, str]:
    """The version label and SHA-256 of the payload that would install *now*,
    resolved WITHOUT downloading it.

    Mirrors ``fetch_apk``'s source selection so the answer matches what an
    install would actually use: a local payload (``KYUBI_PAYLOAD_APK``, else the
    drop-in APK) wins and returns that file's hash -- no network; only with
    neither present is the newest Kyubi release resolved and its published
    digest returned. Used by the "Update Magisk" check to compare against the
    installed manifest's ``payload_sha256`` before doing any work.

    Returns ``(version_label, sha256)``. Raises ``RuntimeError`` if no digest is
    resolvable (the same fail-closed rule ``fetch_apk`` uses), so an update check
    never silently reports "up to date" on a lookup it couldn't complete.
    """
    def _p(msg: str) -> None:
        logger.info(msg)
        if progress:
            progress(msg)

    local = local_payload()
    if local:
        path, source = local
        _p("Checking the %s Kyubi payload at %s..." % (source, path))
        return LOCAL_VERSION_LABEL, _local_sha256(path)

    _p("Checking the latest Kyubi release...")
    tag, _url, expected = _resolve_release()
    if not expected:
        raise RuntimeError(
            "Kyubi release %s exposes no SHA-256 digest, so an update can't be "
            "checked. Pin a known build with %s, or put an APK at %s."
            % (tag, PIN_TAG_ENV, bundled_apk_path()))
    return "%s (Kyubi)" % tag, expected.lower()


def extract_tools(apk_path: str, dest_dir: str, progress=None, *,
                  arm64: bool = False) -> dict[str, str]:
    """Extract the Magisk native tools from the APK into ``dest_dir``.

    Returns ``{tool_name: path}``.  Files are written under their plain names
    (busybox, magisk64, ...) -- the form Magisk's daemon expects in
    ``/data/adb/magisk`` -- not the ``lib*.so`` wrapper.  ``arm64`` selects the
    BlueStacks Air set instead of the x86 one.
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
            for tool, (abi, soname) in (_TOOLS_ARM64 if arm64 else _TOOLS).items():
                member = "lib/%s/%s" % (abi, soname)
                if member not in members:
                    if arm64:
                        raise RuntimeError(
                            "This Kyubi build has no Apple Silicon (arm64) files "
                            "yet, so it cannot be installed on BlueStacks Air.")
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
