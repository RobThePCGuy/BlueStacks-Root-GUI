"""Tests for pif_payload: pinned-module verification and caching.

Network-free: the download path runs with a monkeypatched urlretrieve, so
nothing here touches the real release or the wire.
"""
import hashlib
import os

import pytest

import pif_payload as pp


def test_fetch_module_returns_cached_when_hash_matches(tmp_path, monkeypatch):
    payload = b"pretend-pifork-zip"
    monkeypatch.setattr(pp, "MODULE_SHA256", hashlib.sha256(payload).hexdigest())
    cached = tmp_path / pp.MODULE_NAME
    cached.write_bytes(payload)

    def _boom(*a, **k):
        raise AssertionError("fetch_module downloaded despite a valid cached file")
    monkeypatch.setattr(pp.urllib.request, "urlretrieve", _boom)

    assert pp.fetch_module(str(tmp_path)) == str(cached)


def test_fetch_module_redownloads_when_cache_unreadable(tmp_path, monkeypatch):
    good = b"good-pifork-zip"
    monkeypatch.setattr(pp, "MODULE_SHA256", hashlib.sha256(good).hexdigest())
    cached = tmp_path / pp.MODULE_NAME
    cached.write_bytes(b"placeholder-that-cannot-be-read")

    real_sha = pp._sha256

    def flaky_sha(path):
        if os.path.abspath(path) == os.path.abspath(str(cached)):
            raise OSError("locked")
        return real_sha(path)
    monkeypatch.setattr(pp, "_sha256", flaky_sha)

    def fake_dl(url, dest):
        with open(dest, "wb") as f:
            f.write(good)
    monkeypatch.setattr(pp.urllib.request, "urlretrieve", fake_dl)

    assert pp.fetch_module(str(tmp_path)) == str(cached)
    assert cached.read_bytes() == good


def test_fetch_module_rejects_bad_hash_and_cleans_up(tmp_path, monkeypatch):
    monkeypatch.setattr(pp, "MODULE_SHA256", "0" * 64)

    def _fake_download(url, dest):
        with open(dest, "wb") as f:
            f.write(b"corrupted-or-tampered")
    monkeypatch.setattr(pp.urllib.request, "urlretrieve", _fake_download)

    with pytest.raises(RuntimeError, match="SHA-256 mismatch"):
        pp.fetch_module(str(tmp_path))

    assert not (tmp_path / (pp.MODULE_NAME + ".part")).exists()
    assert not (tmp_path / pp.MODULE_NAME).exists()
