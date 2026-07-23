"""Shared fetch/verify/cache plumbing for the payload-acquisition modules
(``magisk_payload``, ``rezygisk_payload``, ``lsposed_payload``).

Each of those modules owns its OWN trust model -- what URL, what hash, and
where the hash comes from (ReZygisk/LSPosed pin both URL and SHA-256 in
source; Kyubi resolves GitHub's "latest" release and verifies against that
release's own published digest -- see ``magisk_payload._resolve_release``).
This module only extracts the mechanical part all three used to repeat
verbatim: hash a file, reuse a cache hit, download to a temp file, verify,
atomically replace, and clean up on failure. It does not decide what to
trust -- callers pass in the URL and the hash they've already decided to
trust, so the trust-model differences above are unaffected by this refactor.
"""
from __future__ import annotations

import hashlib
import logging
import os
import urllib.request

logger = logging.getLogger(__name__)


def sha256_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def fetch_verified(url: str, dest: str, expected_sha256: str, *,
                   label: str, progress=None) -> str:
    """Download ``url`` to ``dest``, verified against ``expected_sha256``.

    Reuses ``dest`` as-is if it's already present and matches (no re-download).
    Otherwise downloads to a ``.part`` sibling first and only ``os.replace``s
    it over ``dest`` once the hash checks out, so a failed/interrupted
    download never leaves a corrupt file at the real path; the ``.part`` file
    is removed on any failure. Raises ``RuntimeError`` on a hash mismatch.
    ``label`` is used only in progress/log messages (e.g. "ReZygisk module").
    """
    def _p(msg: str) -> None:
        logger.info(msg)
        if progress:
            progress(msg)

    if os.path.isfile(dest):
        try:
            if sha256_file(dest) == expected_sha256:
                _p("%s present and verified (cached)." % label)
                return dest
        except OSError:  # unreadable/locked cache -> fall through to re-download
            pass

    _p("Downloading %s..." % label)
    tmp = dest + ".part"
    try:
        urllib.request.urlretrieve(url, tmp)  # hash-checked below
        got = sha256_file(tmp)
        if got != expected_sha256:
            raise RuntimeError(
                "%s SHA-256 mismatch: got %s, expected %s" % (label, got, expected_sha256))
        os.replace(tmp, dest)
    finally:
        if os.path.isfile(tmp):
            os.unlink(tmp)
    _p("%s verified." % label)
    return dest
