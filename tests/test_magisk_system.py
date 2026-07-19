"""Tests for magisk_system's pure command construction.

The offline disk staging itself is validated live (it needs an attached VHDX +
Administrator); here we lock in the debugfs quirks that bit us: `write` links
its dest as a bare filename in the CWD, so the script must `cd` first and write
bare names, and `_cygpath` must feed the Cygwin debugfs a Cygwin source path.
"""
import os

import pytest

import magisk_system as ms


def test_stage_commands_cd_precedes_bare_name_writes():
    tools = {"busybox": r"C:\tools\busybox", "magisk64": r"C:\tools\magisk64"}
    cmds = ms._stage_commands(tools)

    cd_i = cmds.index("cd %s" % ms._DATABIN)
    write_is = [i for i, c in enumerate(cmds) if c.startswith("write ")]

    assert write_is, "no write commands generated"
    assert min(write_is) > cd_i, "a write happens before cd into the DATABIN dir"
    # every write's destination is a BARE filename (no slash) -- debugfs links it
    # into the CWD; a full path would create a literally-slashed filename.
    for i in write_is:
        dest = cmds[i].split()[-1]
        assert "/" not in dest, "write dest %r must be a bare name" % dest


def test_stage_commands_make_tools_executable_root_owned():
    tools = {"busybox": r"C:\t\busybox"}
    cmds = ms._stage_commands(tools)
    bb = "%s/busybox" % ms._DATABIN
    assert "sif %s mode 0100755" % bb in cmds
    assert "sif %s uid 0" % bb in cmds
    assert "sif %s gid 0" % bb in cmds
    # dir itself is 0700 root:root
    assert "sif %s mode 040700" % ms._DATABIN in cmds


def test_stage_commands_clean_then_recreate():
    cmds = ms._stage_commands({"busybox": r"C:\t\busybox"})
    # removes the old file + dir before recreating, so re-staging is deterministic
    assert "rm %s/busybox" % ms._DATABIN in cmds
    assert cmds.index("rmdir %s" % ms._DATABIN) < cmds.index("mkdir %s" % ms._DATABIN)


@pytest.mark.skipif(os.name != "nt", reason="Windows path semantics")
def test_cygpath_converts_drive_and_separators():
    assert ms._cygpath(r"C:\Users\Rob\x\busybox") == "/cygdrive/c/Users/Rob/x/busybox"
