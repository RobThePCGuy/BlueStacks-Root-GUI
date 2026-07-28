"""Acquire the pinned ReZygisk module -- standalone Zygisk for the emulator.

BlueStacks' guest kernel doesn't support Magisk's built-in Zygisk, so Zygisk
(which Zygisk modules like LSPosed depend on) needs ReZygisk, a ptrace-based
standalone Zygisk implementation.  ReZygisk is a normal Magisk module:
once the DATABIN is complete (``util_functions.sh`` present), it flashes with the
same ``magisk --install-module`` path as any other module -- see
``adb_handler.install_module``.

Like the Magisk payload, the module is **downloaded on demand, not vendored**:
this project fetches a specific, hash-pinned release from ReZygisk's own GitHub,
verifies it by SHA-256, and caches it.  Bumping the version is a one-line change:
update ``MODULE_URL`` + ``MODULE_SHA256`` + ``MODULE_VERSION`` together.

Credit: ReZygisk (c) The PerformanC Organization, GPLv3.
"""
from __future__ import annotations

import os

import payload_fetch

# --- Pinned module (official release, hash-locked) -------------------------
# One-line version bump: change URL + SHA256 + VERSION together.
MODULE_NAME = "ReZygisk-v1.0.0-release.zip"
MODULE_URL = (
    "https://github.com/PerformanC/ReZygisk/releases/download/v1.0.0/"
    "ReZygisk-v1.0.0-release.zip"
)
MODULE_SHA256 = "7904649b8dcaf2b060c3432df4fee302aeb1258da199d2b425335e82d49510e6"
MODULE_VERSION = "v1.0.0 (515)"  # shown in progress; move in lockstep with the pin

# ReZygisk's customize.sh requires Magisk >= this (MAGISK_VER_CODE) and aborts
# partway through its own install script otherwise. Enforced before anything is
# pushed -- adb_handler.install_module takes this as min_magisk_ver_code, so a
# payload that ever dips below produces a clear refusal instead of a failed
# flash. The pinned Kyubi payload is 31000, comfortably above it.
MIN_MAGISK_VER_CODE = 26402


def fetch_module(cache_dir: str, progress=None) -> str:
    """Return a path to the verified pinned ReZygisk zip, downloading + caching
    if needed.

    Re-verifies SHA-256 on every call; a cached file with the wrong hash is
    re-downloaded.  Raises ``RuntimeError`` on a hash mismatch after download.
    Hand the returned path to ``adb_handler.install_module``.
    """
    os.makedirs(cache_dir, exist_ok=True)
    dest = os.path.join(cache_dir, MODULE_NAME)
    return payload_fetch.fetch_verified(
        MODULE_URL, dest, MODULE_SHA256,
        label="ReZygisk %s" % MODULE_VERSION, progress=progress)
