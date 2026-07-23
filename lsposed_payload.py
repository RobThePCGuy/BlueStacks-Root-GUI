"""Acquire the pinned LSPosed (Zygisk) module.

LSPosed is the Xposed framework as a Zygisk module: it lets Xposed modules hook
into apps on a rooted device. It needs a working Zygisk -- on BlueStacks that's
ReZygisk (see ``rezygisk_payload``) -- and is a normal Magisk module, so it
flashes with the same ``magisk --install-module`` path as any other module
(``adb_handler.install_module``). After a reboot, modules are managed from the
LSPosed app.

This is NOT an integrity tool: it adds the Xposed hooking framework, nothing
more. BlueStacks doesn't pass Play Integrity regardless of modules.

Like the other payloads, the module is **downloaded on demand, not vendored**:
fetched from LSPosed's own GitHub release, SHA-256-verified, and cached. We pin
the **zygisk** variant (the riru variant is for the older Riru loader we don't
use). Bumping the version is a one-line change: update ``MODULE_URL`` +
``MODULE_SHA256`` (+ ``MODULE_SIZE``) together.

Credit: LSPosed (c) LSPosed Developers, GPLv3.
"""
from __future__ import annotations

import os

import payload_fetch

# --- Pinned module (official release, hash-locked) -------------------------
# One-line version bump: change URL + SHA256 (+ SIZE) together. Use the *zygisk*
# asset, not the riru one.
MODULE_NAME = "LSPosed-v1.9.2-7024-zygisk-release.zip"
MODULE_URL = (
    "https://github.com/LSPosed/LSPosed/releases/download/v1.9.2/"
    "LSPosed-v1.9.2-7024-zygisk-release.zip"
)
MODULE_SHA256 = "0ebc6bcb465d1c4b44b7220ab5f0252e6b4eb7fe43da74650476d2798bb29622"
MODULE_SIZE = 2462055
MODULE_VERSION = "v1.9.2 (7024)"  # human-readable; move in lockstep with the pin


def fetch_module(cache_dir: str, progress=None) -> str:
    """Return a path to the verified pinned LSPosed zip, downloading + caching if
    needed.

    Re-verifies SHA-256 on every call; a cached file with the wrong hash is
    re-downloaded.  Raises ``RuntimeError`` on a hash mismatch after download.
    Hand the returned path to ``adb_handler.install_module``.
    """
    os.makedirs(cache_dir, exist_ok=True)
    dest = os.path.join(cache_dir, MODULE_NAME)
    return payload_fetch.fetch_verified(
        MODULE_URL, dest, MODULE_SHA256, label="LSPosed module", progress=progress)
