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


def _dir_listing_run(listings):
    """Fake ``_es._run`` that answers each ``ls -l <dir>`` from ``listings``
    (a ``{ext4_dir: output}`` map) -- so recursion into subdirs can be tested."""
    def run(cmd, env=None, **k):
        arg = next((c for c in cmd if isinstance(c, str) and c.startswith("ls -l ")), "")
        return SimpleNamespace(stdout=listings.get(arg[len("ls -l "):], ""),
                               stderr="", returncode=0)
    return run


def test_list_databin_parses_names_skipping_dots_and_symlink_targets(monkeypatch):
    sample = "\n".join([
        " 3801090   40700 (2)   0   0   4096 19-Jul-2026 12:38 .",
        " 3801089   40700 (2)   0   0   4096 19-Jul-2026 12:06 ..",
        " 3801091  100755 (1)   0   0   2260144 19-Jul-2026 12:38 busybox",
        " 3801092  120777 (7)   0   0   9 19-Jul-2026 12:38 sulink -> busybox",
    ])
    monkeypatch.setattr(ms._es, "_run", _fake_run(sample))
    assert ms._list_dir("dev", ms._DATABIN, {}) == ["busybox", "sulink"]


def test_clean_dir_commands_removes_actual_contents_then_rmdir(monkeypatch):
    monkeypatch.setattr(ms._es, "_run", _fake_run(
        " 1 100755 (1) 0 0 5 d t foo\n 2 100755 (1) 0 0 5 d t bar\n"))
    assert ms._clean_dir_commands("dev", "/x/y", {}) == [
        "rm /x/y/foo", "rm /x/y/bar", "rmdir /x/y"]


def test_list_dir_typed_flags_directories_not_files_or_symlinks(monkeypatch):
    sample = "\n".join([
        " 1  40755 (2)   0   0   4096 19-Jul-2026 12:38 chromeos",   # dir
        " 2 100755 (1)   0   0   5    19-Jul-2026 12:38 busybox",    # file
        " 3 120777 (7)   0   0   9    19-Jul-2026 12:38 s -> busybox",  # symlink
    ])
    monkeypatch.setattr(ms._es, "_run", _fake_run(sample))
    assert ms._list_dir_typed("dev", "/x", {}) == [
        ("chromeos", True), ("busybox", False), ("s", False)]


def test_clean_dir_commands_recurses_subdir_before_parent_rmdir(monkeypatch):
    listings = {
        "/adb/magisk": "\n".join([
            " 1 100755 (1) 0 0 5 d t busybox",
            " 2 100755 (1) 0 0 5 d t util_functions.sh",
            " 3  40755 (2) 0 0 4096 d t chromeos",
        ]),
        "/adb/magisk/chromeos": "\n".join([
            " 4 100755 (1) 0 0 5 d t futility",
            " 5 100644 (1) 0 0 5 d t kernel.keyblock",
        ]),
    }
    monkeypatch.setattr(ms._es, "_run", _dir_listing_run(listings))
    # subdir is emptied + rmdir'd before the parent rmdir (rm won't remove a dir)
    assert ms._clean_dir_commands("dev", "/adb/magisk", {}) == [
        "rm /adb/magisk/busybox",
        "rm /adb/magisk/util_functions.sh",
        "rm /adb/magisk/chromeos/futility",
        "rm /adb/magisk/chromeos/kernel.keyblock",
        "rmdir /adb/magisk/chromeos",
        "rmdir /adb/magisk",
    ]


def test_databin_extra_commands_writes_scripts_and_stub():
    # Kyubi extras: the module-install gate script + the manager stub (no chromeos).
    extras = {
        "util_functions.sh": r"C:\d\util_functions.sh",
        "stub.apk": r"C:\d\stub.apk",
    }
    cmds = ms._databin_extra_commands(extras)
    db = ms._DATABIN

    # top-level files: cd into DATABIN, then quoted-source bare-name writes
    assert "cd %s" % db in cmds
    assert 'write "/cygdrive/c/d/util_functions.sh" util_functions.sh' in cmds
    for c in cmds:
        if c.startswith("write "):
            assert c.count('"') == 2 and "/" not in c.split()[-1]  # quoted src, bare dest
    # scripts are exec (0755), the stub is data (0644)
    assert "sif %s/util_functions.sh mode 0100755" % db in cmds
    assert "sif %s/stub.apk mode 0100644" % db in cmds
    # Kyubi ships no chromeos subdir
    assert not any("chromeos" in c for c in cmds)


def test_service_d_grant_commands_creates_dir_when_absent():
    cmds = ms._service_d_grant_commands(r"C:\w\00-bsrgui-adbgrant.sh", dir_exists=False)
    sd = ms._SERVICE_D
    dst = "%s/%s" % (sd, ms._ADB_GRANT_SCRIPT)
    # fresh instance: service.d is created 0700 root before the script write
    assert "mkdir %s" % sd in cmds
    assert "sif %s mode 040700" % sd in cmds
    assert cmds.index("mkdir %s" % sd) < cmds.index("cd %s" % sd)
    # rm-before-write (write won't overwrite), quoted src + bare dest, 0755 root
    assert cmds.index("rm %s" % ms._ADB_GRANT_SCRIPT) < cmds.index(
        'write "/cygdrive/c/w/00-bsrgui-adbgrant.sh" %s' % ms._ADB_GRANT_SCRIPT)
    assert "sif %s mode 0100755" % dst in cmds
    assert "sif %s uid 0" % dst in cmds and "sif %s gid 0" % dst in cmds
    assert "ea_set %s security.selinux %s" % (dst, ms._SELINUX_CTX) in cmds


def test_service_d_grant_commands_skips_mkdir_when_present():
    cmds = ms._service_d_grant_commands(r"C:\w\00-bsrgui-adbgrant.sh", dir_exists=True)
    # booted-once instance already has service.d: don't recreate it
    assert not any(c.startswith("mkdir ") for c in cmds)
    assert "cd %s" % ms._SERVICE_D in cmds
    assert any(c.startswith("write ") and c.endswith(ms._ADB_GRANT_SCRIPT) for c in cmds)


def test_grant_script_tempfile_is_lf_and_grants_shell():
    path = ms._grant_script_tempfile()
    try:
        raw = open(path, "rb").read()
        assert b"\r\n" not in raw, "guest sh needs LF endings, not CRLF"
        assert raw.startswith(b"#!/system/bin/sh")
        text = raw.decode("utf-8")
        # force-allow (policy 2) the shell uid (2000), forever (until 0)
        assert "REPLACE INTO policies" in text
        assert "VALUES(2000,2,0,0,0)" in text
    finally:
        os.unlink(path)


def test_verify_staged_checks_extras_mode_and_owner(monkeypatch):
    stats = {
        "busybox": "Inode: 5 Type: regular Mode:  0755\nUser:  0 Group:  0",
        "util_functions.sh": "Inode: 6 Type: regular Mode:  0755\nUser:  0 Group:  0",
        "stub.apk": "Inode: 7 Type: regular Mode:  0755\nUser:  0 Group:  0",  # wrong: data=0644
        "futility": "Inode: 8 Type: regular Mode:  0755\nUser:  0 Group:  0",
    }
    monkeypatch.setattr(ms._es, "_stat_path",
                        lambda dev, path, env: stats[path.rsplit("/", 1)[-1]])
    bad = ms._verify_staged("dev", {"busybox": ""}, {},
                            {"util_functions.sh": "", "stub.apk": "", "chromeos/futility": ""})
    assert bad == ["stub.apk"]


def test_system_write_commands_footprint_and_perms():
    srcs = {n: r"C:\a\%s" % n for n in
            ("config", "magisk32", "magisk64", "magiskinit", "magiskpolicy",
             "stub.apk", "bootanim.rc", "bootanim.rc.gz")}
    cmds = ms._system_write_commands("/android/system", srcs)
    md = "/android/system/etc/init/magisk"
    idir = "/android/system/etc/init"

    # magisk dir created 0700 root, cd'd into before its writes
    assert "mkdir %s" % md in cmds
    assert "sif %s mode 040700" % md in cmds
    cd_md = cmds.index("cd %s" % md)
    cd_id = cmds.index("cd %s" % idir)
    assert cd_md < cd_id  # magisk dir written first, then init dir

    # every magisk-dir file: quoted source, bare dest, 0700 root
    assert 'write "/cygdrive/c/a/config" config' in cmds
    assert "sif %s/magisk64 mode 0100700" % md in cmds
    assert "sif %s/stub.apk uid 0" % md in cmds

    # bootanim.rc replaces stock (rm first), 0664 system; .gz backup 0600 root
    assert cmds.index("rm bootanim.rc") > cd_id
    assert "sif %s/bootanim.rc mode 0100664" % idir in cmds
    assert "sif %s/bootanim.rc uid 1000" % idir in cmds
    assert "sif %s/bootanim.rc.gz mode 0100600" % idir in cmds


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


_BSTK = (
    '<HardDisk uuid="{a}" location="fastboot.vdi" format="VDI" type="Readonly"/>\n'
    '<HardDisk uuid="{b}" location="{ROOTLOC}" format="VHD" type="Readonly"/>\n'
    '<HardDisk uuid="{c}" location="Data.vhdx" format="VHDX" type="Normal"/>\n'
)


def test_bstk_vhd_location_picks_the_vhd_not_vdi_or_vhdx(tmp_path):
    p = tmp_path / "x.bstk"
    p.write_text(_BSTK.replace("{ROOTLOC}", "../Master/Root.vhd"))
    assert ms._bstk_vhd_location(str(p)) == "../Master/Root.vhd"


def test_resolve_root_vhd_prefers_own(tmp_path):
    (tmp_path / "Root.vhd").write_bytes(b"x")
    assert ms._resolve_root_vhd(str(tmp_path)) == str(tmp_path / "Root.vhd")


def test_resolve_root_vhd_follows_bstk_to_shared_master(tmp_path):
    master = tmp_path / "Master"
    master.mkdir()
    (master / "Root.vhd").write_bytes(b"x")
    clone = tmp_path / "Clone"
    clone.mkdir()
    (clone / "Clone.bstk").write_text(_BSTK.replace("{ROOTLOC}", "../Master/Root.vhd"))

    resolved = ms._resolve_root_vhd(str(clone))
    assert os.path.normpath(resolved) == os.path.normpath(str(master / "Root.vhd"))


def test_resolve_root_vhd_raises_when_none(tmp_path):
    (tmp_path / "Data.vhdx").write_bytes(b"x")  # data-only, no Root.vhd, no bstk
    with pytest.raises(RuntimeError, match="no Root.vhd"):
        ms._resolve_root_vhd(str(tmp_path))


def test_manifest_roundtrip(tmp_path):
    assert ms.magisk_status(str(tmp_path)) is None
    ms._write_manifest(str(tmp_path), ["system", "databin", "manager"])
    st = ms.magisk_status(str(tmp_path))
    assert st["magisk"] is True
    assert st["components"] == ["databin", "manager", "system"]
    assert st["version"] == ms._mp.PAYLOAD_VERSION
    ms._clear_manifest(str(tmp_path))
    assert ms.magisk_status(str(tmp_path)) is None


def test_add_and_remove_component_update_manifest(tmp_path):
    # offline install stamps system+databin; the manager is added after the
    # adb step, removed if the manager is uninstalled.
    ms._write_manifest(str(tmp_path), ["system", "databin"])
    ms.add_component(str(tmp_path), "manager")
    assert ms.magisk_status(str(tmp_path))["components"] == ["databin", "manager", "system"]
    ms.add_component(str(tmp_path), "manager")  # idempotent
    assert ms.magisk_status(str(tmp_path))["components"] == ["databin", "manager", "system"]
    ms.remove_component(str(tmp_path), "manager")
    assert ms.magisk_status(str(tmp_path))["components"] == ["databin", "system"]


def test_component_helpers_noop_when_not_installed(tmp_path):
    ms.add_component(str(tmp_path), "manager")     # no manifest -> nothing happens
    assert ms.magisk_status(str(tmp_path)) is None
    ms.remove_component(str(tmp_path), "manager")  # also a no-op
    assert ms.magisk_status(str(tmp_path)) is None


def _stub_install(monkeypatch):
    """Make install() a no-op that just stamps the system+databin manifest, so
    update() can be tested without touching a real disk."""
    monkeypatch.setattr(ms, "install",
                        lambda instance_dir, work_dir=None, progress=None:
                        (ms._write_manifest(instance_dir, ["system", "databin"]),
                         ["installed"])[1])


def test_update_preserves_the_manager_component(tmp_path, monkeypatch):
    # A prior install with the manager tracked; install() re-stamps only
    # system+databin, so update() must restore the manager record.
    ms._write_manifest(str(tmp_path), ["system", "databin", "manager"])
    _stub_install(monkeypatch)
    ms.update(str(tmp_path))
    assert ms.magisk_status(str(tmp_path))["components"] == \
        ["databin", "manager", "system"]


def test_update_without_a_manager_does_not_invent_one(tmp_path, monkeypatch):
    ms._write_manifest(str(tmp_path), ["system", "databin"])
    _stub_install(monkeypatch)
    ms.update(str(tmp_path))
    assert "manager" not in ms.magisk_status(str(tmp_path))["components"]


def test_update_reports_the_old_and_new_version(tmp_path, monkeypatch):
    ms._write_manifest(str(tmp_path), ["system", "databin"])
    _stub_install(monkeypatch)
    result = ms.update(str(tmp_path))[-1]
    assert "Updated Magisk" in result
    assert "Restart the instance" in result


def test_system_write_commands_rm_gz_before_rewrite():
    # debugfs `write` won't overwrite an existing file, so a reinstall over a
    # leftover bootanim.rc.gz must rm it first.
    srcs = {n: r"C:\a\%s" % n for n in
            ("config", "magisk32", "magisk64", "magiskinit", "magiskpolicy",
             "stub.apk", "bootanim.rc", "bootanim.rc.gz")}
    cmds = ms._system_write_commands("/android/system", srcs)
    rm_i = cmds.index("rm bootanim.rc.gz")
    write_i = next(i for i, c in enumerate(cmds)
                   if c.startswith("write ") and c.endswith(" bootanim.rc.gz"))
    assert rm_i < write_i


def test_install_rolls_back_system_when_databin_fails(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr(ms._mp, "fetch_apk", lambda *a, **k: "apk")
    monkeypatch.setattr(ms._mp, "extract_tools", lambda *a, **k: {"busybox": "b"})
    monkeypatch.setattr(ms._mp, "extract_stub_apk", lambda *a, **k: "stub")
    monkeypatch.setattr(ms._mp, "extract_databin_extras", lambda *a, **k: {})
    monkeypatch.setattr(ms, "install_to_system", lambda *a, **k: calls.append("sys") or ["sys ok"])

    def boom(*a, **k):
        calls.append("databin")
        raise RuntimeError("databin failed")
    monkeypatch.setattr(ms, "stage_databin", boom)
    monkeypatch.setattr(ms, "uninstall_from_system", lambda *a, **k: calls.append("rollback") or [])
    wrote = []
    monkeypatch.setattr(ms, "_write_manifest", lambda *a, **k: wrote.append(a))

    with pytest.raises(RuntimeError, match="databin failed"):
        ms.install(str(tmp_path), work_dir=str(tmp_path / "w"))

    # /system was rolled back, and no manifest was stamped on the failed install
    assert calls == ["sys", "databin", "rollback"]
    assert wrote == []
