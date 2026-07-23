"""Tests for lsposed_payload: pinned-module verification and caching.

Network-free: the download path runs with a monkeypatched urlretrieve, so
nothing here touches the real release or the wire.
"""
import hashlib
import os

import pytest

import lsposed_payload as lp
import payload_fetch


def test_pins_the_zygisk_variant_not_riru():
    # ReZygisk provides Zygisk; the riru asset is for the old Riru loader.
    assert "zygisk" in lp.MODULE_NAME
    assert "riru" not in lp.MODULE_NAME


def test_fetch_module_returns_cached_when_hash_matches(tmp_path, monkeypatch):
    payload = b"pretend-lsposed-zip"
    monkeypatch.setattr(lp, "MODULE_SHA256", hashlib.sha256(payload).hexdigest())
    cached = tmp_path / lp.MODULE_NAME
    cached.write_bytes(payload)

    def _boom(*a, **k):
        raise AssertionError("fetch_module downloaded despite a valid cached file")
    monkeypatch.setattr(payload_fetch.urllib.request, "urlretrieve", _boom)

    assert lp.fetch_module(str(tmp_path)) == str(cached)


def test_fetch_module_redownloads_when_cache_unreadable(tmp_path, monkeypatch):
    good = b"good-lsposed-zip"
    monkeypatch.setattr(lp, "MODULE_SHA256", hashlib.sha256(good).hexdigest())
    cached = tmp_path / lp.MODULE_NAME
    cached.write_bytes(b"placeholder-that-cannot-be-read")

    real_sha = payload_fetch.sha256_file

    def flaky_sha(path):
        if os.path.abspath(path) == os.path.abspath(str(cached)):
            raise OSError("locked")
        return real_sha(path)
    monkeypatch.setattr(payload_fetch, "sha256_file", flaky_sha)

    def fake_dl(url, dest):
        with open(dest, "wb") as f:
            f.write(good)
    monkeypatch.setattr(payload_fetch.urllib.request, "urlretrieve", fake_dl)

    assert lp.fetch_module(str(tmp_path)) == str(cached)
    assert cached.read_bytes() == good


def test_fetch_module_rejects_bad_hash_and_cleans_up(tmp_path, monkeypatch):
    monkeypatch.setattr(lp, "MODULE_SHA256", "0" * 64)

    def _fake_download(url, dest):
        with open(dest, "wb") as f:
            f.write(b"corrupted-or-tampered")
    monkeypatch.setattr(payload_fetch.urllib.request, "urlretrieve", _fake_download)

    with pytest.raises(RuntimeError, match="SHA-256 mismatch"):
        lp.fetch_module(str(tmp_path))

    assert not (tmp_path / (lp.MODULE_NAME + ".part")).exists()
    assert not (tmp_path / lp.MODULE_NAME).exists()
