"""Tests for magisk_payload: payload verification and tool extraction.

Network-free: extraction runs against a synthetic APK zip, and the download
path is exercised with a monkeypatched urlretrieve, so nothing here touches the
real release or the wire.
"""
import hashlib
import os
import urllib.error
import zipfile

import pytest

import magisk_payload as mp
import payload_fetch


@pytest.fixture(autouse=True)
def _clear_kyubi_env(monkeypatch):
    """Keep fetch_apk tests hermetic: a KYUBI_PAYLOAD_APK set in the real shell
    (offline-validation override) would otherwise short-circuit the resolve path."""
    for var in (mp.LOCAL_PAYLOAD_ENV, mp.LOCAL_SHA_ENV, mp.PIN_TAG_ENV):
        monkeypatch.delenv(var, raising=False)


def _make_synthetic_apk(path):
    """Build a zip shaped like the real APK's lib/<abi>/lib*.so + assets/ layout,
    with each member's bytes tagged so extraction can be checked."""
    with zipfile.ZipFile(path, "w") as z:
        for _tool, (abi, soname) in mp._TOOLS.items():
            z.writestr("lib/%s/%s" % (abi, soname), b"ELF:" + abi.encode() + b"/" + soname.encode())
        # decoys that must NOT be extracted (wrong abi for a given tool)
        z.writestr("lib/arm64-v8a/libmagisk64.so", b"WRONG-ABI")
        # DATABIN extras (util scripts, chromeos keys, stub) + a decoy asset
        for _rel, member in mp._DATABIN_EXTRAS.items():
            z.writestr(member, b"ASSET:" + member.encode())
        z.writestr("assets/uninstaller.sh", b"# not a DATABIN extra")


def test_extract_tools_writes_every_tool_unwrapped(tmp_path):
    apk = tmp_path / "synthetic.apk"
    _make_synthetic_apk(apk)
    out = tmp_path / "tools"

    tools = mp.extract_tools(str(apk), str(out))

    assert set(tools) == set(mp._TOOLS)
    for tool, (abi, soname) in mp._TOOLS.items():
        # extracted under the plain name, not lib*.so
        assert (out / tool).is_file()
        assert not (out / soname).exists()
        # the right abi's member landed in the right tool file
        assert (out / tool).read_bytes() == b"ELF:" + abi.encode() + b"/" + soname.encode()


def test_extract_pulls_magisk64_from_x64_and_magisk32_from_x86(tmp_path):
    apk = tmp_path / "synthetic.apk"
    _make_synthetic_apk(apk)
    out = tmp_path / "tools"

    mp.extract_tools(str(apk), str(out))

    assert (out / "magisk64").read_bytes() == b"ELF:x86_64/libmagisk64.so"
    assert (out / "magisk32").read_bytes() == b"ELF:x86/libmagisk32.so"


def test_extract_databin_extras_pulls_declared_scripts(tmp_path):
    apk = tmp_path / "synthetic.apk"
    _make_synthetic_apk(apk)
    out = tmp_path / "databin"

    extras = mp.extract_databin_extras(str(apk), str(out))

    # every declared extra came out, keyed by its DATABIN-relative path
    assert set(extras) == set(mp._DATABIN_EXTRAS)
    # util_functions.sh -- the module-install gate -- must be present, content matches
    assert "util_functions.sh" in extras
    uf = out / "util_functions.sh"
    assert uf.is_file()
    assert uf.read_bytes() == b"ASSET:assets/util_functions.sh"
    assert extras["util_functions.sh"] == str(uf)
    # Kyubi is system-mode only: no chromeos signing tools ship
    assert not (out / "chromeos").exists()


def test_extract_databin_extras_missing_member_raises_and_cleans_partial(tmp_path):
    apk = tmp_path / "bad.apk"
    rels = list(mp._DATABIN_EXTRAS.items())
    with zipfile.ZipFile(apk, "w") as z:  # write all extras EXCEPT the last
        for _rel, member in rels[:-1]:
            z.writestr(member, b"x")
    out = tmp_path / "databin"

    with pytest.raises(RuntimeError, match="missing"):
        mp.extract_databin_extras(str(apk), str(out))

    # no half-populated dir left behind (walk: only empty dirs, no files)
    assert not any(p.is_file() for p in out.rglob("*"))


def test_fetch_apk_returns_cached_when_hash_matches(tmp_path, monkeypatch):
    payload = b"pretend-apk-bytes"
    digest = hashlib.sha256(payload).hexdigest()
    monkeypatch.setattr(mp, "_resolve_release",
                        lambda: ("v9.9", "http://x/app-release.apk", digest))
    cached = tmp_path / mp.PAYLOAD_NAME
    cached.write_bytes(payload)

    # any download attempt would be a bug -> make it explode
    def _boom(*a, **k):
        raise AssertionError("fetch_apk downloaded despite a valid cached file")
    monkeypatch.setattr(payload_fetch.urllib.request, "urlretrieve", _boom)

    assert mp.fetch_apk(str(tmp_path)) == str(cached)
    # the resolved release is recorded for the install manifest
    assert mp.PAYLOAD_SHA256 == digest
    assert "v9.9" in mp.PAYLOAD_VERSION


def test_extract_tools_missing_member_raises_and_cleans_partial(tmp_path):
    apk = tmp_path / "bad.apk"
    items = list(mp._TOOLS.items())
    with zipfile.ZipFile(apk, "w") as z:  # write all tools EXCEPT the last one
        for _tool, (abi, soname) in items[:-1]:
            z.writestr("lib/%s/%s" % (abi, soname), b"x")
    out = tmp_path / "tools"

    with pytest.raises(RuntimeError, match="missing"):
        mp.extract_tools(str(apk), str(out))

    # no half-populated tool dir left behind
    assert list(out.glob("*")) == []


def test_fetch_apk_redownloads_when_cache_unreadable(tmp_path, monkeypatch):
    good = b"good-apk-bytes"
    monkeypatch.setattr(mp, "_resolve_release",
                        lambda: ("v9.9", "http://x/app-release.apk",
                                 hashlib.sha256(good).hexdigest()))
    cached = tmp_path / mp.PAYLOAD_NAME
    cached.write_bytes(b"placeholder-that-cannot-be-read")

    real_sha = payload_fetch.sha256_file

    def flaky_sha(path):
        if os.path.abspath(path) == os.path.abspath(str(cached)):
            raise OSError("locked")   # cached file unreadable
        return real_sha(path)         # the fresh .part hashes fine
    monkeypatch.setattr(payload_fetch, "sha256_file", flaky_sha)

    def fake_dl(url, dest):
        with open(dest, "wb") as f:
            f.write(good)
    monkeypatch.setattr(payload_fetch.urllib.request, "urlretrieve", fake_dl)

    assert mp.fetch_apk(str(tmp_path)) == str(cached)
    assert cached.read_bytes() == good   # re-downloaded over the bad cache


def test_fetch_apk_rejects_bad_hash_and_cleans_up(tmp_path, monkeypatch):
    monkeypatch.setattr(mp, "_resolve_release",
                        lambda: ("v9.9", "http://x/app-release.apk", "0" * 64))

    def _fake_download(url, dest):
        with open(dest, "wb") as f:
            f.write(b"corrupted-or-tampered")
    monkeypatch.setattr(payload_fetch.urllib.request, "urlretrieve", _fake_download)

    with pytest.raises(RuntimeError, match="SHA-256 mismatch"):
        mp.fetch_apk(str(tmp_path))

    # nothing left behind: no .part, no accepted payload
    assert not (tmp_path / (mp.PAYLOAD_NAME + ".part")).exists()
    assert not (tmp_path / mp.PAYLOAD_NAME).exists()


def test_fetch_apk_fails_closed_when_no_digest(tmp_path, monkeypatch):
    # A release that exposes no sha256 (API digest empty, no .sha256 sibling) must
    # NOT be installed -- auto-latest never trades away hash verification.
    monkeypatch.setattr(mp, "_resolve_release",
                        lambda: ("v9.9", "http://x/app-release.apk", ""))

    def _boom(*a, **k):
        raise AssertionError("downloaded despite having no digest to verify")
    monkeypatch.setattr(payload_fetch.urllib.request, "urlretrieve", _boom)

    with pytest.raises(RuntimeError, match="refusing to install unverified"):
        mp.fetch_apk(str(tmp_path))


@pytest.mark.parametrize("code", [403, 429])
def test_open_url_converts_github_rate_limit_to_clear_message(monkeypatch, code):
    def _raise_rate_limited(req, timeout=30):
        raise urllib.error.HTTPError(
            "https://api.github.com/x", code, "rate limited", {}, None)
    monkeypatch.setattr(mp.urllib.request, "urlopen", _raise_rate_limited)

    with pytest.raises(RuntimeError, match="rate-limited"):
        mp._api_get("https://api.github.com/repos/x/releases/latest")


def test_open_url_reraises_other_http_errors_unconverted(monkeypatch):
    def _raise_not_found(req, timeout=30):
        raise urllib.error.HTTPError(
            "https://api.github.com/x", 404, "not found", {}, None)
    monkeypatch.setattr(mp.urllib.request, "urlopen", _raise_not_found)

    # A non-rate-limit HTTPError must propagate as-is, not be swallowed or
    # relabeled as a rate-limit message.
    with pytest.raises(urllib.error.HTTPError) as exc_info:
        mp._api_get("https://api.github.com/repos/x/releases/latest")
    assert exc_info.value.code == 404


def test_resolve_release_surfaces_rate_limit_message_end_to_end(tmp_path, monkeypatch):
    """The friendly message must reach fetch_apk's caller, not just _api_get's."""
    def _raise_rate_limited(req, timeout=30):
        raise urllib.error.HTTPError(
            "https://api.github.com/x", 403, "rate limited", {}, None)
    monkeypatch.setattr(mp.urllib.request, "urlopen", _raise_rate_limited)

    with pytest.raises(RuntimeError, match="rate-limited"):
        mp.fetch_apk(str(tmp_path))


def test_fetch_apk_local_override_verifies_and_skips_network(tmp_path, monkeypatch):
    payload = b"local-apk-bytes"
    src = tmp_path / "local.apk"
    src.write_bytes(payload)
    monkeypatch.setenv(mp.LOCAL_PAYLOAD_ENV, str(src))
    monkeypatch.setenv(mp.LOCAL_SHA_ENV, hashlib.sha256(payload).hexdigest())

    # a valid local override must never hit the release API
    def _no_net():
        raise AssertionError("resolved the release despite a local override")
    monkeypatch.setattr(mp, "_resolve_release", _no_net)

    dest = mp.fetch_apk(str(tmp_path / "cache"))
    assert os.path.isfile(dest)
    assert open(dest, "rb").read() == payload

    # a wrong declared sha is rejected
    monkeypatch.setenv(mp.LOCAL_SHA_ENV, "0" * 64)
    with pytest.raises(RuntimeError, match="mismatch"):
        mp.fetch_apk(str(tmp_path / "cache2"))


def test_latest_identity_from_release_returns_tag_and_digest(monkeypatch):
    monkeypatch.setattr(mp, "_resolve_release",
                        lambda: ("kyubi-2.0.0", "http://x/app-release.apk", "ABCDEF"))
    version, sha = mp.latest_identity()
    assert version == "kyubi-2.0.0 (Kyubi)"
    assert sha == "abcdef"          # normalised lowercase, matches the manifest


def test_latest_identity_uses_the_local_override_without_network(tmp_path, monkeypatch):
    payload = b"local-apk-bytes"
    src = tmp_path / "local.apk"
    src.write_bytes(payload)
    monkeypatch.setenv(mp.LOCAL_PAYLOAD_ENV, str(src))
    monkeypatch.setattr(mp, "_resolve_release",
                        lambda: (_ for _ in ()).throw(AssertionError("hit the network")))
    version, sha = mp.latest_identity()
    assert version == "local (Kyubi)"
    assert sha == hashlib.sha256(payload).hexdigest()


def test_latest_identity_fails_closed_without_a_digest(monkeypatch):
    monkeypatch.setattr(mp, "_resolve_release",
                        lambda: ("kyubi-2.0.0", "http://x/app-release.apk", ""))
    with pytest.raises(RuntimeError, match="update"):
        mp.latest_identity()
