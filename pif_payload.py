"""Acquire the pinned Play Integrity Fork (PIFork) module.

Play Integrity's BASIC and DEVICE verdicts gate on the guest looking like a
Play-certified device: a valid build fingerprint and a set of "sensitive"
system props. PIFork (osm0sis, the maintained successor to the abandoned PIF)
spoofs those from a Zygisk module, and its bundled ``autopif`` fetches a fresh,
Play-certified fingerprint so the default one being burned/banned isn't a
problem. It's a Zygisk module, so it needs a working Zygisk -- on BlueStacks
that's ReZygisk (see ``rezygisk_payload``).

STRONG is a separate story: it needs a valid, unrevoked *hardware* keybox, which
this tool neither ships nor can generate -- PIFork alone reaches BASIC + DEVICE.

Like the other payloads, the module is **downloaded on demand, not vendored**:
fetched from PIFork's own GitHub release, SHA-256-verified, and cached. Bumping
the version is a one-line change: update ``MODULE_URL`` + ``MODULE_SHA256``
(+ ``MODULE_SIZE``) together.

Credit: Play Integrity Fork (c) osm0sis & chiteroman @ xda-developers.
"""
from __future__ import annotations

import hashlib
import logging
import os
import urllib.request

logger = logging.getLogger(__name__)

# --- Pinned module (official release, hash-locked) -------------------------
# One-line version bump: change URL + SHA256 (+ SIZE) together.
MODULE_NAME = "PlayIntegrityFork-v17.zip"
MODULE_URL = (
    "https://github.com/osm0sis/PlayIntegrityFork/releases/download/v17/"
    "PlayIntegrityFork-v17.zip"
)
MODULE_SHA256 = "69115acdeba904a3b82882851cf3cb6c27aef5bfb6aa57c1988ab3a4c0bb8c87"
MODULE_SIZE = 285020
MODULE_VERSION = "v17"  # human-readable; move in lockstep with the pin


def _sha256(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def fetch_module(cache_dir: str, progress=None) -> str:
    """Return a path to the verified pinned PIFork zip, downloading + caching if
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
                _p("PIFork module present and verified (cached).")
                return dest
        except OSError:  # unreadable/locked cache -> fall through to re-download
            pass

    _p("Downloading Play Integrity Fork (%s)..." % MODULE_NAME)
    tmp = dest + ".part"
    try:
        urllib.request.urlretrieve(MODULE_URL, tmp)  # pinned URL, hash-checked below
        got = _sha256(tmp)
        if got != MODULE_SHA256:
            raise RuntimeError(
                "PIFork module SHA-256 mismatch: got %s, expected %s"
                % (got, MODULE_SHA256))
        os.replace(tmp, dest)
    finally:
        if os.path.isfile(tmp):
            os.unlink(tmp)
    _p("PIFork module verified.")
    return dest
