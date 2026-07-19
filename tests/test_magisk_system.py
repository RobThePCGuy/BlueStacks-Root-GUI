"""Tests for magisk_system's pure/parsing logic.

The offline disk staging itself is validated live (it needs an attached VHDX +
Administrator).  Here we lock in the debugfs quirks and safety logic: `write`
links its dest as a bare filename in the CWD (so cd first, bare names), source
paths are quoted for spaces, cleanup enumerates the dir's real contents, and
verification checks every tool's mode + ownership.
"""
import os
from types import SimpleNamespace

import pytest

import magisk_system as ms


def test_write_commands_cd_precedes_bare_quoted_writes():
    tools = {"busybox": r"C:\tools\busybox", "magisk64": r"C:\tools\magisk64"}
    cmds = ms._write_commands(tools)

    cd_i = cmds.index("cd %s" % ms._DATABIN)
    write_is = [i for i, c in enumerate(cmds) if c.startswith("write ")]

    assert write_is and min(write_is) > cd_i, "a write happens before cd"
    assert cmds.index("mkdir %s" % ms._DATABIN) < cd_i, "mkdir before cd"
    for i in write_is:
        assert cmds[i].count('"') == 2, "write source must be quoted: %r" % cmds[i]
        dest = cmds[i].split()[-1]
        assert "/" not in dest, "write dest must be a bare name: %r" % dest


def test_write_commands_make_tools_exec_root_owned():
    cmds = ms._write_commands({"busybox": r"C:\t\busybox"})
    bb = "%s/busybox" % ms._DATABIN
    assert "sif %s mode 0100755" % bb in cmds
    assert "sif %s uid 0" % bb in cmds
    assert "sif %s gid 0" % bb in cmds
    assert "sif %s mode 040700" % ms._DATABIN in cmds


def test_dq_quotes_paths_with_spaces():
    assert ms._dq("/cygdrive/c/Users/John Doe/x") == '"/cygdrive/c/Users/John Doe/x"'


@pytest.mark.skipif(os.name != "nt", reason="Windows path semantics")
def test_cygpath_converts_drive_and_separators():
    assert ms._cygpath(r"C:\Users\Rob\x\busybox") == "/cygdrive/c/Users/Rob/x/busybox"


def _fake_run(stdout):
    return lambda *a, **k: SimpleNamespace(stdout=stdout, stderr="", returncode=0)


def test_list_databin_parses_names_skipping_dots_and_symlink_targets(monkeypatch):
    sample = "\n".join([
        " 3801090   40700 (2)   0   0   4096 19-Jul-2026 12:38 .",
        " 3801089   40700 (2)   0   0   4096 19-Jul-2026 12:06 ..",
        " 3801091  100755 (1)   0   0   2260144 19-Jul-2026 12:38 busybox",
        " 3801092  120777 (7)   0   0   9 19-Jul-2026 12:38 sulink -> busybox",
    ])
    monkeypatch.setattr(ms._es, "_run", _fake_run(sample))
    assert ms._list_databin("dev", {}) == ["busybox", "sulink"]


def test_clean_commands_removes_actual_contents_then_rmdir(monkeypatch):
    monkeypatch.setattr(ms._es, "_run", _fake_run(
        " 1 100755 (1) 0 0 5 d t foo\n 2 100755 (1) 0 0 5 d t bar\n"))
    assert ms._clean_commands("dev", {}) == [
        "rm %s/foo" % ms._DATABIN, "rm %s/bar" % ms._DATABIN, "rmdir %s" % ms._DATABIN]


def test_verify_staged_flags_wrong_mode_and_owner(monkeypatch):
    stats = {
        "busybox": "Inode: 5   Type: regular   Mode:  0755\nUser:     0   Group:     0",
        "magisk64": "Inode: 6   Type: regular   Mode:  0644\nUser:     0   Group:     0",  # wrong mode
        "magiskinit": "Inode: 7   Type: regular   Mode:  0755\nUser:  1000   Group:     0",  # wrong owner
    }
    monkeypatch.setattr(ms._es, "_stat_path",
                        lambda dev, path, env: stats[path.rsplit("/", 1)[-1]])
    bad = ms._verify_staged("dev", {"busybox": "", "magisk64": "", "magiskinit": ""}, {})
    assert sorted(bad) == ["magisk64", "magiskinit"]


def test_errtail_surfaces_debugfs_error_lines():
    out = "debugfs: write x y\nAllocated inode: 39\n/adb/magisk/foo: File not found by ext2_lookup"
    assert "File not found" in ms._errtail(out)
