"""Tests for telemetry_block's pure/state logic.

The offline disk write itself is validated live (it needs an attached Root.vhd
+ Administrator). Here we lock in the marked-block generation, idempotent
strip/re-apply, and the state sidecar.
"""
import telemetry_block as tb


def test_blocklist_is_nonempty_lowercase_domains():
    assert tb.BLOCKLIST
    for d in tb.BLOCKLIST:
        assert d == d.lower() and " " not in d and "/" not in d
    # the ad exchange caught in the live capture is in the list
    assert "rtbhouse.net" in tb.BLOCKLIST


def test_block_text_markers_and_null_routes():
    text = tb._block_text()
    assert tb._BLOCK_BEGIN in text and tb._BLOCK_END in text
    for d in tb.BLOCKLIST:
        assert "0.0.0.0 %s" % d in text
        assert "0.0.0.0 www.%s" % d in text  # www alias too
    assert tb.has_block(text) is True


def test_strip_block_removes_only_the_marked_section():
    original = "127.0.0.1\tlocalhost\n::1\t\tlocalhost\n"
    blocked = original + tb._block_text()
    assert tb.has_block(blocked) is True
    stripped = tb._strip_block(blocked)
    assert tb.has_block(stripped) is False
    # the user's real hosts entries survive
    assert "127.0.0.1\tlocalhost" in stripped
    assert "rtbhouse.net" not in stripped


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
    assert st["domains"] == len(tb.BLOCKLIST)
    tb._write_state(str(tmp_path), False)
    assert tb.status(str(tmp_path)) is None
