"""Tests for magisk_payload: payload verification and tool extraction.

Network-free: extraction runs against a synthetic APK zip, and the download
path is exercised with a monkeypatched urlretrieve, so nothing here touches the
real release or the wire.
"""
import hashlib
import zipfile

import pytest

import magisk_payload as mp


def _make_synthetic_apk(path):
    """Build a zip shaped like the real APK's lib/<abi>/lib*.so layout, with each
    member's bytes tagged by its abi+soname so extraction can be checked."""
    with zipfile.ZipFile(path, "w") as z:
        for _tool, (abi, soname) in mp._TOOLS.items():
            z.writestr("lib/%s/%s" % (abi, soname), b"ELF:" + abi.encode() + b"/" + soname.encode())
        # decoys that must NOT be extracted (wrong abi for a given tool)
        z.writestr("lib/arm64-v8a/libmagisk64.so", b"WRONG-ABI")
        z.writestr("assets/util_functions.sh", b"# not a tool")


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


def test_fetch_apk_returns_cached_when_hash_matches(tmp_path, monkeypatch):
    payload = b"pretend-apk-bytes"
    digest = hashlib.sha256(payload).hexdigest()
    monkeypatch.setattr(mp, "PAYLOAD_SHA256", digest)
    cached = tmp_path / mp.PAYLOAD_NAME
    cached.write_bytes(payload)

    # any download attempt would be a bug -> make it explode
    def _boom(*a, **k):
        raise AssertionError("fetch_apk downloaded despite a valid cached file")
    monkeypatch.setattr(mp.urllib.request, "urlretrieve", _boom)

    assert mp.fetch_apk(str(tmp_path)) == str(cached)


def test_fetch_apk_rejects_bad_hash_and_cleans_up(tmp_path, monkeypatch):
    monkeypatch.setattr(mp, "PAYLOAD_SHA256", "0" * 64)

    def _fake_download(url, dest):
        with open(dest, "wb") as f:
            f.write(b"corrupted-or-tampered")
    monkeypatch.setattr(mp.urllib.request, "urlretrieve", _fake_download)

    with pytest.raises(RuntimeError, match="SHA-256 mismatch"):
        mp.fetch_apk(str(tmp_path))

    # nothing left behind: no .part, no accepted payload
    assert not (tmp_path / (mp.PAYLOAD_NAME + ".part")).exists()
    assert not (tmp_path / mp.PAYLOAD_NAME).exists()
