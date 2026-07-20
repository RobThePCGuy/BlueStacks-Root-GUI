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

import hashlib
import logging
import os
import urllib.request

logger = logging.getLogger(__name__)

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


def _sha256(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def fetch_module(cache_dir: str, progress=None) -> str:
    """Return a path to the verified pinned LSPosed zip, downloading + caching if
    needed.

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
                _p("LSPosed module present and verified (cached).")
                return dest
        except OSError:  # unreadable/locked cache -> fall through to re-download
            pass

    _p("Downloading LSPosed (%s)..." % MODULE_NAME)
    tmp = dest + ".part"
    try:
        urllib.request.urlretrieve(MODULE_URL, tmp)  # pinned URL, hash-checked below
        got = _sha256(tmp)
        if got != MODULE_SHA256:
            raise RuntimeError(
                "LSPosed module SHA-256 mismatch: got %s, expected %s"
                % (got, MODULE_SHA256))
        os.replace(tmp, dest)
    finally:
        if os.path.isfile(tmp):
            os.unlink(tmp)
    _p("LSPosed module verified.")
    return dest
