"""Tests for the pre-write journal replay in ext4_symlink.

BlueStacks instances are almost never shut down cleanly, so /data routinely
carries an unreplayed journal. `e2fsck -fn` cannot replay one and then reports
phantom errors (orphaned inodes, bitmap differences) that are really the
journal's pending metadata, which used to surface as "e2fsck reported errors"
and refuse an operation over nothing.

Two properties matter most here and both are easy to regress:

* the repair runs on the *partition* device, because via `?offset=` the bundled
  Cygwin e2fsck dies reopening the filesystem after a replay and never commits;
* it is *best-effort and never raises*, because an unreplayed journal is the
  normal resting state of these images, and raising would block the uninstall
  and restore paths that deliberately tolerate a dirty filesystem.
"""
import pytest

import ext4_symlink as es

OFFSET_DEV = "/dev/sdc?offset=1048576"
PART_DEV = "/dev/sdc1"
UUID = "3f2b1a4c-9d8e-4f7a-b6c5-0123456789ab"
OTHER_UUID = "00000000-1111-2222-3333-444444444444"


class _Result:
    def __init__(self, returncode, stdout=""):
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = ""


def _disk(uuids, dirty_until=1):
    """Fake e2fsck/debugfs. `uuids` maps device -> superblock UUID."""
    state = {"preened": 0}

    def handler(cmd):
        dev = cmd[-1]
        if "show_super_stats -h" in cmd:
            uid = uuids.get(dev)
            return _Result(0, "Filesystem UUID:  %s\n" % uid) if uid else _Result(1, "")
        if "-fp" in cmd:
            state["preened"] += 1
            return _Result(1, "recovering journal")
        if "-fn" in cmd:
            return _Result(4 if state["preened"] < dirty_until else 0)
        raise AssertionError("unexpected command: %r" % (cmd,))

    return handler, state


def _install(monkeypatch, handler):
    calls = []

    def run(cmd, env=None, **kw):
        calls.append(cmd)
        return handler(cmd)

    monkeypatch.setattr(es, "_run", run)
    return calls


# --- _fsck_repair -----------------------------------------------------------

def test_clean_image_is_not_touched(monkeypatch):
    calls = _install(monkeypatch, _disk({}, dirty_until=0)[0])
    assert es._fsck_repair(OFFSET_DEV, {}) is None
    assert not any("-fp" in c for c in calls)


def test_repair_runs_on_the_partition_device_not_the_offset_one(monkeypatch):
    """The whole point: via ?offset= the replay never persists."""
    handler, _ = _disk({OFFSET_DEV: UUID, PART_DEV: UUID})
    calls = _install(monkeypatch, handler)
    note = es._fsck_repair(OFFSET_DEV, {})
    assert note and "journal" in note.lower()
    preens = [c for c in calls if "-fp" in c]
    assert len(preens) == 1 and preens[0][-1] == PART_DEV


def test_verdict_comes_from_rechecking_the_original_device(monkeypatch):
    handler, _ = _disk({OFFSET_DEV: UUID, PART_DEV: UUID})
    calls = _install(monkeypatch, handler)
    es._fsck_repair(OFFSET_DEV, {})
    assert calls[-1][-1] == OFFSET_DEV and "-fn" in calls[-1]


@pytest.mark.parametrize("preen_code", [0, 1, 2, 4, 8, 12])
def test_preen_exit_code_does_not_decide_the_outcome(monkeypatch, preen_code):
    """The real build exits 12 after a successful replay and 1 after a real
    repair, so only the recheck may decide."""
    state = {"preened": 0}

    def handler(cmd):
        if "show_super_stats -h" in cmd:
            return _Result(0, "Filesystem UUID:  %s\n" % UUID)
        if "-fp" in cmd:
            state["preened"] += 1
            return _Result(preen_code)
        return _Result(4 if state["preened"] == 0 else 0)

    _install(monkeypatch, handler)
    assert es._fsck_repair(OFFSET_DEV, {}) is not None


def test_partition_is_matched_by_uuid_not_by_size(monkeypatch):
    """Identity guard: a same-size but different filesystem must never be
    preened, and with no match the repair is skipped rather than misapplied."""
    handler, state = _disk({OFFSET_DEV: UUID, PART_DEV: OTHER_UUID})
    calls = _install(monkeypatch, handler)
    assert es._fsck_repair(OFFSET_DEV, {}) is None
    assert state["preened"] == 0
    assert not any("-fp" in c for c in calls)


def test_missing_partition_node_is_skipped_not_fatal(monkeypatch):
    """Cygwin may not expose /dev/sdXN at all. That must not block the write:
    an unreplayed journal is the normal state, so raising would break everything.
    """
    handler, _ = _disk({OFFSET_DEV: UUID})     # no partition nodes
    _install(monkeypatch, handler)
    assert es._fsck_repair(OFFSET_DEV, {}) is None      # no exception


def test_still_dirty_after_replay_is_reported_but_not_fatal(monkeypatch):
    """Uninstall and restore paths tolerate a dirty filesystem on purpose, so a
    failed replay must not stop them from running."""
    handler, _ = _disk({OFFSET_DEV: UUID, PART_DEV: UUID}, dirty_until=99)
    _install(monkeypatch, handler)
    assert es._fsck_repair(OFFSET_DEV, {}) is None      # no exception


def test_plain_device_needs_no_partition_lookup(monkeypatch):
    handler, _ = _disk({PART_DEV: UUID})
    calls = _install(monkeypatch, handler)
    es._fsck_repair(PART_DEV, {})
    assert [c for c in calls if "-fp" in c][0][-1] == PART_DEV


# --- _Attached wiring -------------------------------------------------------

@pytest.fixture
def attach_stub(monkeypatch):
    """Stub out diskpart so _Attached can be exercised without a real VHD."""
    events = []
    monkeypatch.setattr(es, "_partition_offset", lambda p: 1048576)
    monkeypatch.setattr(es, "_attach", lambda p: events.append("attach"))
    monkeypatch.setattr(es, "_detach", lambda p: (events.append("detach"), True)[1])
    monkeypatch.setattr(es, "_disk_number", lambda p: 2)
    monkeypatch.setattr(es, "_tool_env", dict)
    monkeypatch.setattr(es.time, "sleep", lambda *_: None)
    return events


def test_clean_image_reports_no_repair(attach_stub, monkeypatch):
    monkeypatch.setattr(es, "_fsck_repair", lambda dev, env: None)
    with es._Attached("R.vhd") as att:
        assert att.repaired is None
        assert att.device == OFFSET_DEV
    assert attach_stub == ["attach", "detach"]


def test_repair_false_skips_it_entirely(attach_stub, monkeypatch):
    def boom(dev, env):
        raise AssertionError("must not repair when repair=False")

    monkeypatch.setattr(es, "_fsck_repair", boom)
    with es._Attached("R.vhd", repair=False) as att:
        assert att.repaired is None


def test_a_repair_reattaches_to_drop_the_stale_partition_cache(attach_stub, monkeypatch):
    """The preen writes through the partition node while debugfs writes through
    the disk node; reattaching removes that cache aliasing."""
    monkeypatch.setattr(es, "_fsck_repair", lambda dev, env: "replayed")
    with es._Attached("R.vhd") as att:
        assert att.repaired == "replayed"
    assert attach_stub == ["attach", "detach", "attach", "detach"]


def test_a_stuck_detach_does_not_trigger_a_double_attach(attach_stub, monkeypatch):
    """If the refresh detach fails, re-attaching an already-attached disk would
    only compound it, so we keep the working device instead."""
    monkeypatch.setattr(es, "_fsck_repair", lambda dev, env: "replayed")
    monkeypatch.setattr(es, "_detach",
                        lambda p: (attach_stub.append("detach-failed"), False)[1])
    with es._Attached("R.vhd") as att:
        assert att.device == OFFSET_DEV          # still usable
    assert attach_stub.count("attach") == 1      # never re-attached


def test_the_repair_note_is_reported_to_the_caller(attach_stub, monkeypatch):
    monkeypatch.setattr(es, "_fsck_repair", lambda dev, env: "replayed the journal")
    seen = []
    with es._Attached("R.vhd", progress=seen.append):
        pass
    assert seen == ["replayed the journal"]


def test_a_failure_inside_enter_detaches_before_propagating(attach_stub, monkeypatch):
    """Otherwise the image stays mounted as a raw disk and the instance will not
    boot until the user detaches it by hand."""
    def boom(dev, env):
        raise RuntimeError("kaboom")

    monkeypatch.setattr(es, "_fsck_repair", boom)
    with pytest.raises(RuntimeError, match="kaboom"):
        with es._Attached("R.vhd"):
            pass
    assert attach_stub == ["attach", "detach"]


def test_an_unlocatable_disk_still_detaches(attach_stub, monkeypatch):
    monkeypatch.setattr(es, "_disk_number", lambda p: None)
    with pytest.raises(RuntimeError, match="could not locate"):
        with es._Attached("R.vhd"):
            pass
    assert attach_stub == ["attach", "detach"]
