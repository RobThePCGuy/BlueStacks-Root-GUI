"""Acquire the pinned KitsuneMagisk (Magisk Delta) payload and extract the
native tools needed for offline system-mode installation.

The APK is **downloaded on demand, not vendored** -- Magisk/Kitsune is GPLv3, so
this project redistributes none of it; instead it fetches a specific,
hash-pinned build from RobThePCGuy's own release, verifies it by SHA-256, and
caches it.  Magisk's native tools ship inside the APK at ``lib/<abi>/lib*.so``;
we extract the ``x86_64`` set (BlueStacks guests are x86_64) plus the 32-bit
``magisk32`` so 32-bit guest apps get root too, renaming ``lib*.so`` to the plain
names Magisk's daemon expects in ``/data/adb/magisk``.

Bumping the Magisk version is a one-line change: update ``PAYLOAD_URL`` and
``PAYLOAD_SHA256`` together.

Credit: Magisk (c) topjohnwu; Magisk Delta (c) HuskyDG; Kitsune build maintained
by 1q23lyc45.  All GPLv3.
"""
from __future__ import annotations

import hashlib
import logging
import os
import shutil
import urllib.request
import zipfile

logger = logging.getLogger(__name__)

# --- Pinned payload (self-hosted, hash-locked) -----------------------------
# One-line version bump: change URL + SHA256 (+ SIZE) together.
PAYLOAD_NAME = "Magisk-Delta-Kitsune-27.001-Canary.apk"
PAYLOAD_URL = (
    "https://github.com/RobThePCGuy/Root-Bluestacks-with-Kitsune-Mask/"
    "releases/download/magisk-delta-kitsune-27.001/"
    "Magisk-Delta-Kitsune-27.001-Canary.apk"
)
PAYLOAD_SHA256 = "5a3e77d28d4ead274e39b83fa7a4c60d201c43b2d665b30955685179c77d53e7"
PAYLOAD_SIZE = 12880326

# lib/<abi>/lib<tool>.so  ->  DATABIN tool name.  magisk64 + the x86_64 tools
# come from lib/x86_64; magisk32 from lib/x86 so 32-bit guest apps get root.
_X64 = "x86_64"
_X86 = "x86"
_TOOLS = {
    "busybox": (_X64, "libbusybox.so"),      # the daemon's environment gate
    "magisk64": (_X64, "libmagisk64.so"),    # magiskd / su (64-bit)
    "magiskinit": (_X64, "libmagiskinit.so"),
    "magiskpolicy": (_X64, "libmagiskpolicy.so"),
    "magiskboot": (_X64, "libmagiskboot.so"),
    "magisk32": (_X86, "libmagisk32.so"),    # 32-bit app root
}


def _sha256(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def fetch_apk(cache_dir: str, progress=None) -> str:
    """Return a path to the verified pinned APK, downloading + caching if needed.

    Re-verifies SHA-256 on every call; a cached file with the wrong hash is
    re-downloaded.  Raises ``RuntimeError`` on a hash mismatch after download.
    """
    def _p(msg: str) -> None:
        logger.info(msg)
        if progress:
            progress(msg)

    os.makedirs(cache_dir, exist_ok=True)
    dest = os.path.join(cache_dir, PAYLOAD_NAME)
    if os.path.isfile(dest) and _sha256(dest) == PAYLOAD_SHA256:
        _p("Kitsune payload present and verified (cached).")
        return dest

    _p("Downloading Kitsune payload (%s)..." % PAYLOAD_NAME)
    tmp = dest + ".part"
    try:
        urllib.request.urlretrieve(PAYLOAD_URL, tmp)  # pinned URL, hash-checked below
        got = _sha256(tmp)
        if got != PAYLOAD_SHA256:
            raise RuntimeError(
                "Kitsune payload SHA-256 mismatch: got %s, expected %s"
                % (got, PAYLOAD_SHA256))
        os.replace(tmp, dest)
    finally:
        if os.path.isfile(tmp):
            os.unlink(tmp)
    _p("Kitsune payload verified.")
    return dest


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
    with zipfile.ZipFile(apk_path) as z:
        for tool, (abi, soname) in _TOOLS.items():
            member = "lib/%s/%s" % (abi, soname)
            target = os.path.join(dest_dir, tool)
            with z.open(member) as src, open(target, "wb") as dst:
                shutil.copyfileobj(src, dst)
            out[tool] = target
    _p("Extracted %d Magisk tools (%s)." % (len(out), ", ".join(sorted(out))))
    return out
