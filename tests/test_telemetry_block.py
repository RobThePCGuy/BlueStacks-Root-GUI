"""Tests for telemetry_block's pure/state logic.

The offline disk write itself is validated live (it needs an attached Root.vhd
+ Administrator). Here we lock in the marked-block generation, idempotent
strip/re-apply, and the state sidecar.
"""
import telemetry_block as tb


def test_blocklist_is_nonempty_lowercase_domains():
    assert tb.BLOCKLIST
    for d in tb.BLOCKLIST + tb.HOST_BLOCKLIST:
        assert d == d.lower() and " " not in d and "/" not in d


def test_dead_rtbhouse_net_entry_is_gone():
    """It never resolved; the live endpoint is esp.rtbhouse.com.

    Compared by equality rather than ``in``: an entry has to be its own exact
    hostname, so a substring sitting inside some longer domain cannot satisfy
    this. (It also keeps CodeQL's incomplete-URL-sanitization rule quiet, which
    cannot tell tuple membership from a substring check on a URL.)
    """
    assert not any(d == "rtbhouse.net" for d in tb.BLOCKLIST)
    assert any(d == "rtbhouse.com" for d in tb.BLOCKLIST)
    assert any(h == "esp.rtbhouse.com" for h in tb.HOST_BLOCKLIST)


def test_subdomains_are_listed_explicitly_because_hosts_cannot_wildcard():
    """An apex entry does not cover subdomains, and ad traffic is subdomains."""
    hosts = tb.blocked_hosts()
    for fqdn in ("cm.g.doubleclick.net",
                 "pagead2.googlesyndication.com",
                 "api.w.inmobi.com",
                 "esp.rtbhouse.com"):
        assert fqdn in hosts, fqdn


def test_blocked_hosts_has_no_duplicates():
    hosts = tb.blocked_hosts()
    assert len(hosts) == len(set(hosts))


def test_block_text_markers_and_null_routes():
    text = tb._block_text()
    assert tb._BLOCK_BEGIN in text and tb._BLOCK_END in text
    for d in tb.BLOCKLIST:
        assert "0.0.0.0 %s" % d in text
        assert "0.0.0.0 www.%s" % d in text  # www alias too
    for h in tb.HOST_BLOCKLIST:
        assert "0.0.0.0 %s" % h in text
    assert tb.has_block(text) is True


def test_strip_block_removes_only_the_marked_section():
    original = "127.0.0.1\tlocalhost\n::1\t\tlocalhost\n"
    blocked = original + tb._block_text()
    assert tb.has_block(blocked) is True
    stripped = tb._strip_block(blocked)
    assert tb.has_block(stripped) is False
    # the user's real hosts entries survive
    assert "127.0.0.1\tlocalhost" in stripped
    assert "doubleclick.net" not in stripped


def test_apply_is_idempotent_no_double_block():
    original = "127.0.0.1 localhost\n"
    once = tb._strip_block(original) + tb._block_text()
    # re-applying strips the prior block first, so there's exactly one
    twice = tb._strip_block(once) + tb._block_text()
    assert twice.count(tb._BLOCK_BEGIN) == 1
    assert once == twice


def test_has_block_false_on_plain_hosts():
    assert tb.has_block("127.0.0.1 localhost\n") is False


def test_state_sidecar_roundtrip(tmp_path):
    assert tb.status(str(tmp_path)) is None
    tb._write_state(str(tmp_path), True)
    st = tb.status(str(tmp_path))
    assert st["telemetry_block"] is True
    assert st["domains"] == len(tb.blocked_hosts())
    tb._write_state(str(tmp_path), False)
    assert tb.status(str(tmp_path)) is None


def test_status_is_shared_across_instances_of_one_android_version(tmp_path, monkeypatch):
    """The block lives in the shared Root.vhd, so a clone must not report "not
    blocked" while its master (same image) is blocked."""
    master = tmp_path / "Tiramisu64"
    clone = tmp_path / "Tiramisu64_2"
    master.mkdir()
    clone.mkdir()
    root_vhd = master / "Root.vhd"
    root_vhd.write_bytes(b"")

    # Both instances resolve to the master's Root.vhd (the clone has none).
    monkeypatch.setattr(tb._ms, "_resolve_root_vhd", lambda _dir: str(root_vhd))

    # Applying via one instance is visible from the other.
    tb._write_state(str(master), True)
    assert tb.status(str(master))["telemetry_block"] is True
    assert tb.status(str(clone))["telemetry_block"] is True

    tb._write_state(str(master), False)
    assert tb.status(str(clone)) is None


def test_sidecar_falls_back_to_instance_dir_without_a_root_vhd(tmp_path, monkeypatch):
    def _boom(_dir):
        raise RuntimeError("no Root.vhd")

    monkeypatch.setattr(tb._ms, "_resolve_root_vhd", _boom)
    tb._write_state(str(tmp_path), True)               # must not raise
    assert tb.status(str(tmp_path))["telemetry_block"] is True
