"""Tests for magisk_payload: payload verification and tool extraction.

Network-free: extraction runs against a synthetic APK zip, and the download
path is exercised with a monkeypatched urlretrieve, so nothing here touches the
real release or the wire.
"""
import hashlib
import os
import sys
import urllib.error
import zipfile

import pytest

import magisk_payload as mp
import payload_fetch

# The real resolver, captured before the autouse fixture below replaces it with a
# stub; the frozen-layout tests re-patch to this to exercise the genuine logic.
_REAL_APP_ROOTS = mp._app_roots


@pytest.fixture(autouse=True)
def _no_ambient_payload(monkeypatch, tmp_path_factory):
    """Keep every test hermetic about *which* payload source wins.

    A KYUBI_PAYLOAD_APK set in the real shell or (more insidiously) a real drop-in
    APK sitting at the repo's ``magisk_assets/kyubi/app-release.apk`` would
    otherwise short-circuit the release-resolution path, so the download tests
    would pass for the wrong reason on a machine that happens to have one.
    Tests that exercise a local payload point ``_app_roots``/the env var at their
    own files.
    """
    for var in (mp.LOCAL_PAYLOAD_ENV, mp.LOCAL_SHA_ENV, mp.PIN_TAG_ENV):
        monkeypatch.delenv(var, raising=False)
    empty = tmp_path_factory.mktemp("no-payload")
    monkeypatch.setattr(mp, "_app_roots", lambda: [str(empty)])


def _make_synthetic_apk(path):
    """Build a zip shaped like the real APK's lib/<abi>/lib*.so + assets/ layout,
    with each member's bytes tagged so extraction can be checked."""
    path = str(path)
    with zipfile.ZipFile(path, "w") as z:
        for _tool, (abi, soname) in mp._TOOLS.items():
            z.writestr("lib/%s/%s" % (abi, soname), b"ELF:" + abi.encode() + b"/" + soname.encode())
        # decoys that must NOT be extracted (wrong abi for a given tool)
        z.writestr("lib/arm64-v8a/libmagisk64.so", b"WRONG-ABI")
        # DATABIN extras (util scripts, chromeos keys, stub) + a decoy asset
        for _rel, member in mp._DATABIN_EXTRAS.items():
            z.writestr(member, b"ASSET:" + member.encode())
        z.writestr("assets/uninstaller.sh", b"# not a DATABIN extra")


def _drop_in_apk(tmp_path, monkeypatch, sidecar=None):
    """Lay a synthetic APK out at the documented drop-in path and aim the app at it.

    Returns the APK path. ``sidecar``, when given, is written next to it as the
    optional ``.sha256`` pin.
    """
    root = tmp_path / "app"
    (root / mp.BUNDLED_DIR).mkdir(parents=True)
    apk = root / mp.BUNDLED_DIR / mp.BUNDLED_APK_NAME
    _make_synthetic_apk(apk)
    if sidecar is not None:
        (root / mp.BUNDLED_DIR /
         (mp.BUNDLED_APK_NAME + mp.SHA_SIDECAR_SUFFIX)).write_text(sidecar)
    monkeypatch.setattr(mp, "_app_roots", lambda: [str(root)])
    return apk


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
    src = tmp_path / "local.apk"
    _make_synthetic_apk(src)
    digest = hashlib.sha256(src.read_bytes()).hexdigest()
    monkeypatch.setenv(mp.LOCAL_PAYLOAD_ENV, str(src))
    monkeypatch.setenv(mp.LOCAL_SHA_ENV, digest)

    # a valid local override must never hit the release API
    def _no_net():
        raise AssertionError("resolved the release despite a local override")
    monkeypatch.setattr(mp, "_resolve_release", _no_net)

    dest = mp.fetch_apk(str(tmp_path / "cache"))
    assert os.path.isfile(dest)
    assert open(dest, "rb").read() == src.read_bytes()
    assert mp.PAYLOAD_SHA256 == digest

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


def test_resolve_release_picks_newest_published_prerelease(monkeypatch):
    """Kyubi publishes every build as a prerelease; /releases/latest would skip
    them all. The resolver must take the newest published release that carries
    the APK, ignoring drafts and asset-less releases."""
    def _rel(tag, published, draft=False, prerelease=True, apk=True):
        assets = [{"name": mp.PAYLOAD_ASSET_NAME,
                   "browser_download_url": "https://x/%s.apk" % tag,
                   "digest": "sha256:" + tag[-1] * 64}] if apk else []
        return {"tag_name": tag, "published_at": published, "draft": draft,
                "prerelease": prerelease, "assets": assets}
    listing = [
        _rel("v-stable1", "2026-09-22T00:00:00Z", prerelease=False),
        _rel("v-draft2", None, draft=True),
        _rel("v-noapk3", "2026-10-30T05:00:00Z", apk=False),
        _rel("v-pre4", "2026-10-30T04:00:00Z"),
        _rel("v-pre5", "2026-10-06T00:00:00Z"),
    ]
    monkeypatch.delenv(mp.PIN_TAG_ENV, raising=False)
    monkeypatch.setattr(mp, "_api_get", lambda url: listing)
    tag, url, sha = mp._resolve_release()
    assert (tag, url, sha) == ("v-pre4", "https://x/v-pre4.apk", "4" * 64)


# --------------------------------------------------------------------------
# Offline payload: the drop-in APK is the DEFAULT source, ahead of the network.
# --------------------------------------------------------------------------

def test_bundled_payload_is_used_by_default_without_network(tmp_path, monkeypatch):
    """The reported bug: a rate-limited API turned an offline-capable install into
    a hard failure. With the APK dropped in place, nothing may even be resolved."""
    apk = _drop_in_apk(tmp_path, monkeypatch)

    def _no_net(*a, **k):
        raise AssertionError("network used despite a bundled offline payload")
    monkeypatch.setattr(mp, "_resolve_release", _no_net)
    monkeypatch.setattr(payload_fetch.urllib.request, "urlretrieve", _no_net)

    out = mp.fetch_apk(str(tmp_path / "cache"))

    assert out == str(apk)                                    # used verbatim, no copy
    assert mp.PAYLOAD_SHA256 == hashlib.sha256(apk.read_bytes()).hexdigest()
    assert mp.PAYLOAD_VERSION == mp.LOCAL_VERSION_LABEL        # what the manifest stamps


def test_env_override_still_beats_the_bundled_payload(tmp_path, monkeypatch):
    _drop_in_apk(tmp_path, monkeypatch)                       # would otherwise win
    override = tmp_path / "elsewhere.apk"
    _make_synthetic_apk(override)
    monkeypatch.setenv(mp.LOCAL_PAYLOAD_ENV, str(override))

    assert mp.fetch_apk(str(tmp_path / "cache")) == str(override)


def test_missing_explicit_override_errors_instead_of_downloading(tmp_path, monkeypatch):
    """Whoever set the env var asked for offline: falling back to the wire would
    hide the typo and re-introduce the exact failure they were avoiding."""
    monkeypatch.setenv(mp.LOCAL_PAYLOAD_ENV, str(tmp_path / "gone.apk"))

    def _no_net(*a, **k):
        raise AssertionError("fell back to the network")
    monkeypatch.setattr(mp, "_resolve_release", _no_net)

    with pytest.raises(RuntimeError, match="does not exist"):
        mp.fetch_apk(str(tmp_path / "cache"))


def test_bundled_file_that_is_not_an_apk_is_rejected_early(tmp_path, monkeypatch):
    """A saved HTML error page / truncated download must fail with a message that
    names the file, not later as "payload is missing lib/x86/libmagisk32.so"."""
    root = tmp_path / "app"
    (root / mp.BUNDLED_DIR).mkdir(parents=True)
    (root / mp.BUNDLED_DIR / mp.BUNDLED_APK_NAME).write_text("<html>404</html>")
    monkeypatch.setattr(mp, "_app_roots", lambda: [str(root)])

    with pytest.raises(RuntimeError, match="not a usable Kyubi APK"):
        mp.fetch_apk(str(tmp_path / "cache"))


def test_bundled_zip_without_the_binaries_is_rejected(tmp_path, monkeypatch):
    root = tmp_path / "app"
    (root / mp.BUNDLED_DIR).mkdir(parents=True)
    apk = root / mp.BUNDLED_DIR / mp.BUNDLED_APK_NAME
    with zipfile.ZipFile(apk, "w") as z:                      # a zip, but not Kyubi
        z.writestr("AndroidManifest.xml", b"not kyubi")
    monkeypatch.setattr(mp, "_app_roots", lambda: [str(root)])

    with pytest.raises(RuntimeError, match="not a usable Kyubi APK"):
        mp.fetch_apk(str(tmp_path / "cache"))


def test_bundled_payload_sha256_sidecar_is_enforced(tmp_path, monkeypatch):
    apk = _drop_in_apk(tmp_path, monkeypatch, sidecar="0" * 64)

    with pytest.raises(RuntimeError, match="mismatch"):
        mp.fetch_apk(str(tmp_path / "cache"))

    # the correct pin (in `sha256sum` output form: "<hex>  <filename>") is accepted
    (apk.parent / (mp.BUNDLED_APK_NAME + mp.SHA_SIDECAR_SUFFIX)).write_text(
        hashlib.sha256(apk.read_bytes()).hexdigest() + "  " + mp.BUNDLED_APK_NAME + "\n")
    assert mp.fetch_apk(str(tmp_path / "cache")) == str(apk)


def test_latest_identity_prefers_the_bundled_payload(tmp_path, monkeypatch):
    """The "Update Magisk" check must use the same source the install would, so a
    local payload keeps the update path off the network too."""
    apk = _drop_in_apk(tmp_path, monkeypatch)

    def _no_net():
        raise AssertionError("hit the network for the update check")
    monkeypatch.setattr(mp, "_resolve_release", _no_net)

    version, sha = mp.latest_identity()
    assert version == mp.LOCAL_VERSION_LABEL
    assert sha == hashlib.sha256(apk.read_bytes()).hexdigest()


def test_rate_limited_download_falls_back_to_the_cached_copy(tmp_path, monkeypatch):
    """No drop-in APK and the API is rate-limited: an earlier hash-verified
    download is still a valid, installed-before payload -- use it."""
    cache = tmp_path / "cache"
    cache.mkdir()
    cached = cache / mp.PAYLOAD_NAME
    _make_synthetic_apk(cached)

    def _rate_limited():
        raise RuntimeError("GitHub rate-limited this request, try again later.")
    monkeypatch.setattr(mp, "_resolve_release", _rate_limited)

    out = mp.fetch_apk(str(cache))

    assert out == str(cached)
    assert mp.PAYLOAD_VERSION == mp.CACHED_VERSION_LABEL
    assert mp.PAYLOAD_SHA256 == hashlib.sha256(cached.read_bytes()).hexdigest()


def test_rate_limit_still_fails_when_nothing_is_cached(tmp_path, monkeypatch):
    """The cached-copy fallback must not turn a real failure into a silent no-op."""
    def _rate_limited():
        raise RuntimeError("GitHub rate-limited this request, try again later.")
    monkeypatch.setattr(mp, "_resolve_release", _rate_limited)

    with pytest.raises(RuntimeError, match="rate-limited"):
        mp.fetch_apk(str(tmp_path / "cache"))


def test_bundled_apk_path_resolves_inside_the_frozen_bundle(tmp_path, monkeypatch):
    meipass = tmp_path / "meipass"
    (meipass / mp.BUNDLED_DIR).mkdir(parents=True)
    apk = meipass / mp.BUNDLED_DIR / mp.BUNDLED_APK_NAME
    _make_synthetic_apk(apk)
    monkeypatch.setattr(mp, "_app_roots", _REAL_APP_ROOTS)   # exercise the real logic
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "_MEIPASS", str(meipass), raising=False)
    monkeypatch.setattr(sys, "executable", str(tmp_path / "exe" / "BlueStacksRootGUI.exe"),
                        raising=False)

    assert mp.bundled_apk_path() == str(apk)


def test_bundled_apk_path_next_to_a_frozen_exe_is_found(tmp_path, monkeypatch):
    """A user who downloads the exe can drop the APK beside it -- no rebuild."""
    exe_dir = tmp_path / "Downloads"
    (exe_dir / mp.BUNDLED_DIR).mkdir(parents=True)
    apk = exe_dir / mp.BUNDLED_DIR / mp.BUNDLED_APK_NAME
    _make_synthetic_apk(apk)
    monkeypatch.setattr(mp, "_app_roots", _REAL_APP_ROOTS)   # exercise the real logic
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "_MEIPASS", str(tmp_path / "empty-bundle"), raising=False)
    monkeypatch.setattr(sys, "executable", str(exe_dir / "BlueStacksRootGUI.exe"),
                        raising=False)

    assert mp.bundled_apk_path() == str(apk)


def test_bundled_apk_path_reports_the_drop_in_location_when_absent(tmp_path, monkeypatch):
    """With no payload at all, the path is still answerable -- error messages and
    docs quote exactly where to put the file."""
    root = tmp_path / "app"
    monkeypatch.setattr(mp, "_app_roots", lambda: [str(root)])

    assert mp.bundled_apk_path() == str(root / mp.BUNDLED_DIR / mp.BUNDLED_APK_NAME)

