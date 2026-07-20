"""Acquire the pinned ReZygisk module -- standalone Zygisk for the emulator.

BlueStacks' guest kernel doesn't support Magisk's built-in Zygisk, so Zygisk
(the API modules like Play Integrity Fix depend on) needs ReZygisk, a ptrace-
based standalone Zygisk implementation.  ReZygisk is a normal Magisk module:
once the DATABIN is complete (``util_functions.sh`` present), it flashes with the
same ``magisk --install-module`` path as any other module -- see
``adb_handler.install_module``.

Like the Magisk payload, the module is **downloaded on demand, not vendored**:
this project fetches a specific, hash-pinned release from ReZygisk's own GitHub,
verifies it by SHA-256, and caches it.  Bumping the version is a one-line change:
update ``MODULE_URL`` + ``MODULE_SHA256`` (+ ``MODULE_SIZE``) together.

Credit: ReZygisk (c) The PerformanC Organization, GPLv3.
"""
from __future__ import annotations

import hashlib
import logging
import os
import urllib.request

logger = logging.getLogger(__name__)

# --- Pinned module (official release, hash-locked) -------------------------
# One-line version bump: change URL + SHA256 (+ SIZE) together.
MODULE_NAME = "ReZygisk-v1.0.0-release.zip"
MODULE_URL = (
    "https://github.com/PerformanC/ReZygisk/releases/download/v1.0.0/"
    "ReZygisk-v1.0.0-release.zip"
)
MODULE_SHA256 = "7904649b8dcaf2b060c3432df4fee302aeb1258da199d2b425335e82d49510e6"
MODULE_SIZE = 506334
MODULE_VERSION = "v1.0.0 (515)"  # human-readable; move in lockstep with the pin

# ReZygisk's customize.sh requires Magisk >= this (MAGISK_VER_CODE). The pinned
# Kitsune payload is 27001, comfortably above it; surfaced here so a Magisk
# version bump that dips below is caught rather than failing mid-flash.
MIN_MAGISK_VER_CODE = 26402


def _sha256(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def fetch_module(cache_dir: str, progress=None) -> str:
    """Return a path to the verified pinned ReZygisk zip, downloading + caching
    if needed.

    Re-verifies SHA-256 on every call; a cached file with the wrong hash is
    re-downloaded.  Raises ``RuntimeError`` on a hash mismatch after download.
    Hand the returned path to ``adb_handler.install_module``.
    """
    def _p(msg: str) -> None:
        logger.info(msg)
        if progress:
            progress(msg)

    os.makedirs(cache_dir, exist_ok=True)
    dest = os.path.join(cache_dir, MODULE_NAME)
    if os.path.isfile(dest):
        try:
            if _sha256(dest) == MODULE_SHA256:
                _p("ReZygisk module present and verified (cached).")
                return dest
        except OSError:  # unreadable/locked cache -> fall through to re-download
            pass

    _p("Downloading ReZygisk module (%s)..." % MODULE_NAME)
    tmp = dest + ".part"
    try:
        urllib.request.urlretrieve(MODULE_URL, tmp)  # pinned URL, hash-checked below
        got = _sha256(tmp)
        if got != MODULE_SHA256:
            raise RuntimeError(
                "ReZygisk module SHA-256 mismatch: got %s, expected %s"
                % (got, MODULE_SHA256))
        os.replace(tmp, dest)
    finally:
        if os.path.isfile(tmp):
            os.unlink(tmp)
    _p("ReZygisk module verified.")
    return dest
