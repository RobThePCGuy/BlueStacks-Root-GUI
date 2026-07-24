"""Tests for the pre-write journal replay in ext4_symlink.

BlueStacks instances are almost never shut down cleanly, so /data routinely
carries an unreplayed journal. `e2fsck -fn` cannot replay one and then reports
phantom errors (orphaned inodes, bitmap differences) that are really just the
journal's pending metadata, which used to surface as "e2fsck reported errors"
and refuse an operation over nothing.

The repair has to run on the partition device: via `?offset=` the bundled Cygwin
e2fsck dies reopening the filesystem after a replay and never commits, so the
journal stays dirty no matter how often it runs. These lock in both that routing
and the identity check that stops a repair landing on another partition.
"""
import pytest

import ext4_symlink as es

OFFSET_DEV = "/dev/sdc?offset=1048576"
PART_DEV = "/dev/sdc1"

# what e2fsck prints; the capacities are the filesystem's fingerprint
SUMMARY = "/dev/sdc1: 4919/8388608 files (4.9%% non-contiguous), %d/33554176 blocks"


class _Result:
    def __init__(self, returncode, stdout=""):
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = ""


def _install(monkeypatch, handler):
    calls = []

    def run(cmd, env=None, **kw):
        calls.append(cmd)
        return handler(cmd)

    monkeypatch.setattr(es, "_run", run)
    return calls


def _healthy_disk(dirty_until=1):
    """A disk where PART_DEV matches OFFSET_DEV and preen cleans it."""
    state = {"preened": 0}

    def handler(cmd):
        dev = cmd[-1]
        if "-fp" in cmd:
            state["preened"] += 1
            return _Result(1, "recovering journal")
        # -fn
        if dev in (OFFSET_DEV, PART_DEV):
            dirty = state["preened"] < dirty_until
            return _Result(4 if dirty else 0, SUMMARY % 1414054)
        return _Result(8, "Possibly non-existent device?")

    return handler, state


def test_clean_image_is_not_touched(monkeypatch):
    calls = _install(monkeypatch, lambda cmd: _Result(0, SUMMARY % 1414054))
    assert es._fsck_repair(OFFSET_DEV, {}) is None
    assert not any("-fp" in c for c in calls)


def test_repair_runs_on_the_partition_device_not_the_offset_one(monkeypatch):
    """The whole point: via ?offset= the replay never persists."""
    handler, _ = _healthy_disk()
    calls = _install(monkeypatch, handler)
    note = es._fsck_repair(OFFSET_DEV, {})
    assert note and "journal" in note.lower()
    preens = [c for c in calls if "-fp" in c]
    assert len(preens) == 1
    assert preens[0][-1] == PART_DEV
    assert OFFSET_DEV not in preens[0]


def test_verdict_comes_from_rechecking_the_original_device(monkeypatch):
    handler, _ = _healthy_disk()
    calls = _install(monkeypatch, handler)
    es._fsck_repair(OFFSET_DEV, {})
    assert calls[-1][-1] == OFFSET_DEV and "-fn" in calls[-1]


@pytest.mark.parametrize("preen_code", [0, 1, 2, 4, 8, 12])
def test_preen_exit_code_does_not_decide_the_outcome(monkeypatch, preen_code):
    """The real build exits 12 after a successful replay, and 1 after a real
    repair, so only the recheck may decide."""
    state = {"preened": 0}

    def handler(cmd):
        if "-fp" in cmd:
            state["preened"] += 1
            return _Result(preen_code)
        dev = cmd[-1]
        if dev in (OFFSET_DEV, PART_DEV):
            return _Result(4 if state["preened"] == 0 else 0, SUMMARY % 1414054)
        return _Result(8)

    _install(monkeypatch, handler)
    assert es._fsck_repair(OFFSET_DEV, {}) is not None


def test_a_partition_of_a_different_size_is_never_repaired(monkeypatch):
    """Identity guard: only a same-size filesystem may be the repair target."""
    def handler(cmd):
        dev = cmd[-1]
        if "-fp" in cmd:
            raise AssertionError("must not preen an unidentified partition")
        if dev == OFFSET_DEV:
            return _Result(4, SUMMARY % 1414054)
        if dev == PART_DEV:
            # same shape, different capacity: a different filesystem
            return _Result(0, "/dev/sdc1: 10/2097152 files, 5/8388608 blocks")
        return _Result(8, "Possibly non-existent device?")

    _install(monkeypatch, handler)
    with pytest.raises(RuntimeError) as exc:
        es._fsck_repair(OFFSET_DEV, {})
    assert "could not be located" in str(exc.value)


def test_still_dirty_after_replay_raises_instead_of_writing(monkeypatch):
    handler, _ = _healthy_disk(dirty_until=99)   # never comes clean
    _install(monkeypatch, handler)
    with pytest.raises(RuntimeError) as exc:
        es._fsck_repair(OFFSET_DEV, {})
    msg = str(exc.value)
    assert "will not write" in msg
    assert "shut it down" in msg


def test_plain_device_needs_no_partition_lookup(monkeypatch):
    calls = _install(monkeypatch, _healthy_disk()[0])
    es._fsck_repair(PART_DEV, {})
    assert [c for c in calls if "-fp" in c][0][-1] == PART_DEV
