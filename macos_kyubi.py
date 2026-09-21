"""Kyubi (Magisk-managed root) for BlueStacks Air -- the macOS ``magisk_system``.

What it installs
----------------
The same system-mode footprint the Windows installer writes, in Air's one shared
system image (``Root.qcow2``, edited through ``macos_root.open_image``):

* ``/system/etc/init/magisk/`` -- ``magisk64``, ``magiskinit``, ``magiskpolicy``,
  ``busybox``, ``stub.apk``, ``util_functions.sh``, ``config``, plus the two
  small scripts below. Root-owned, 0700.
* ``/system/etc/init/bootanim.rc`` -- the stock file with Magisk's boot hooks
  appended; the stock file is kept gzipped beside it as ``bootanim.rc.gz``.

Two deliberate differences from Windows, both forced by Air:

* **arm64 only, no magisk32.** Air's guest is 64-bit ARM with no 32-bit ABI.
* **``/debug_ramdisk`` instead of ``/sbin``.** Air's ramdisk has no ``/sbin``;
  ``/debug_ramdisk`` exists and is the first place Magisk looks for its tmpfs.

And one simplification: **the DATABIN is staged by the guest itself.** On
Windows ``/data/adb/magisk`` is written offline into ``Data.vhdx``. On Air every
instance has its own multi-GB ``data.qcow2``, and converting that on each
install would be slow and would touch user data. Instead the boot hook runs a
small script before Magisk starts that copies the binaries from the system
image into ``/data/adb/magisk`` whenever they differ (compared by a stamp), so
every instance picks Kyubi up on its next boot, and an update to the system
image refreshes them automatically.

Root is install-wide on Air, so this sits beside ``macos_root``'s plain ``su``
in the shared modification record, as the ``kyubi`` entry. The two conflict (both
provide ``su``): installing Kyubi removes the plain ``su`` in the same pass.
"""
from __future__ import annotations

import gzip
import hashlib
import logging
import os
import tempfile

import macos_locator
import macos_root
import magisk_payload

logger = logging.getLogger(__name__)

INIT_DIR = "/android/system/etc/init"
MAGISK_DIR = INIT_DIR + "/magisk"
BOOTANIM = INIT_DIR + "/bootanim.rc"
BOOTANIM_GZ = INIT_DIR + "/bootanim.rc.gz"
GUEST_MAGISK_DIR = "/system/etc/init/magisk"

STAGE_SCRIPT = "kyubi-stage.sh"
ADB_GRANT_SCRIPT = "00-bsrgui-adbgrant.sh"
STAMP = "stamp"

CONFIG = "SYSTEMMODE=true\nRECOVERYMODE=false\n"

# Appended to the stock bootanim.rc. Same sequence Magisk's own install-to-system
# writes (see magisk_assets/*/bootanim.rc), with the tmpfs at /debug_ramdisk and
# the DATABIN staging step in front of --post-fs-data.
BOOT_HOOK = """on post-fs-data
    start logd
    mkdir /data/adb 0700 root root
    exec u:r:su:s0 root root -- {d}/busybox sh {d}/{stage}
    exec u:r:su:s0 root root -- {d}/magiskpolicy --live --magisk
    exec u:r:magisk:s0 root root -- {d}/magiskpolicy --live --magisk
    exec u:r:update_engine:s0 root root -- {d}/magiskpolicy --live --magisk
    exec u:r:su:s0 root root -- {d}/magisk64 --auto-selinux --setup-sbin {d} /debug_ramdisk
    exec u:r:su:s0 root root -- /debug_ramdisk/magisk --auto-selinux --post-fs-data
on nonencrypted
    exec u:r:su:s0 root root -- /debug_ramdisk/magisk --auto-selinux --service
on property:vold.decrypt=trigger_restart_framework
    exec u:r:su:s0 root root -- /debug_ramdisk/magisk --auto-selinux --service
on property:sys.boot_completed=1
    mkdir /data/adb/magisk 755
    exec u:r:su:s0 root root -- /debug_ramdisk/magisk --auto-selinux --boot-complete
on property:init.svc.zygote=restarting
    exec u:r:su:s0 root root -- /debug_ramdisk/magisk --auto-selinux --zygote-restart
on property:init.svc.zygote=stopped
    exec u:r:su:s0 root root -- /debug_ramdisk/magisk --auto-selinux --zygote-restart
""".format(d=GUEST_MAGISK_DIR, stage=STAGE_SCRIPT)

# Files the stage script copies into /data/adb/magisk. util_functions.sh is the
# module-install gate ("Incomplete Magisk install" without it).
DATABIN_FILES = ("busybox", "magisk64", "magiskinit", "magiskpolicy",
                 "stub.apk", "util_functions.sh")

STAGE_BODY = """#!/system/bin/sh
# Kyubi on BlueStacks Air: copy the binaries from the system image into the
# DATABIN before Magisk starts, whenever they differ. Run by init as root.
S={s}
D=/data/adb/magisk
BB=$S/busybox
if ! $BB cmp -s $S/{stamp} $D/.kyubi_stamp; then
  $BB rm -rf $D
  $BB mkdir -p $D
  for f in {files}; do $BB cp -f $S/$f $D/$f; done
  $BB chmod 0755 $D/*
  $BB chmod 0644 $D/stub.apk
  $BB cp -f $S/{stamp} $D/.kyubi_stamp
fi
$BB mkdir -p /data/adb/service.d
$BB cp -f $S/{grant} /data/adb/service.d/{grant}
$BB chmod 0755 /data/adb/service.d/{grant}
""".format(s=GUEST_MAGISK_DIR, stamp=STAMP, grant=ADB_GRANT_SCRIPT,
           files=" ".join(DATABIN_FILES))

# Same auto-grant as the Windows install (magisk_system._ADB_GRANT_BODY): lets
# the ADB shell use su so module flashes over ADB are never silently denied.
ADB_GRANT_BODY = (
    "#!/system/bin/sh\n"
    "# BlueStacks-Root-GUI: force-allow the ADB shell (uid 2000) at boot so\n"
    "# module flashes over ADB are never auto-denied. Runs as root via Magisk\n"
    "# service.d; scoped to the shell uid only.\n"
    "for i in 1 2 3 4 5 6 7 8 9 10; do\n"
    '  magisk --sqlite "REPLACE INTO policies (uid,policy,until,logging,notification) VALUES(2000,2,0,0,0)" && break\n'
    "  sleep 2\n"
    "done\n"
)


def status(app_path: str, data_dir: str = macos_locator.DATA_DIR) -> dict | None:
    """Recorded Kyubi install, or None. Shaped like ``magisk_system.magisk_status``."""
    return macos_root.read_modstate(app_path, data_dir).get("kyubi")


def _cache_dir() -> str:
    return os.path.join(tempfile.gettempdir(), "BlueStacksRootGUI-magisk", "cache")


def _sha256(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _hook_bootanim(stock: str) -> str:
    return stock.rstrip("\n") + "\n" + BOOT_HOOK


def _write_host_file(workdir: str, name: str, data: bytes) -> str:
    path = os.path.join(workdir, name)
    with open(path, "wb") as fh:
        fh.write(data)
    return path


def _put(img: macos_root.ImageSession, host: str, guest: str, *,
         mode: int, uid: int = 0, gid: int = 0) -> None:
    parent, name = guest.rsplit("/", 1)
    img.run("rm {g}\ncd {p}\nwrite {h} {n}\nsif {n} mode 0{m:o}\n"
            "sif {n} uid {u}\nsif {n} gid {gi}\nquit\n"
            .format(g=guest, p=parent, h=host, n=name, m=mode, u=uid, gi=gid))
    if "Inode:" not in img.run("stat %s\nquit\n" % guest):
        raise macos_root.RootError("Could not write %s into the system image." % guest)


def _remove_magisk_dir(img: macos_root.ImageSession) -> None:
    listing = img.run("ls -p %s\nquit\n" % MAGISK_DIR)
    names = [p.split("/")[5] for p in listing.split() if p.count("/") >= 6]
    names = [n for n in names if n not in ("", ".", "..")]
    cmds = "".join("rm %s/%s\n" % (MAGISK_DIR, n) for n in names)
    img.run(cmds + "rmdir %s\nquit\n" % MAGISK_DIR)


def _read_stock_backup(img: macos_root.ImageSession) -> str | None:
    gz = os.path.join(img.workdir, "bootanim.rc.gz")
    if os.path.exists(gz):
        os.unlink(gz)
    img.run("dump %s %s\nquit\n" % (BOOTANIM_GZ, gz))
    if not os.path.isfile(gz):
        return None
    with gzip.open(gz, "rb") as fh:
        return fh.read().decode("utf-8")


def install(app_path: str, progress=None,
            data_dir: str = macos_locator.DATA_DIR) -> list[str]:
    """Install Kyubi into the Air system image. BlueStacks must be closed."""
    def _step(msg: str) -> None:
        logger.info(msg)
        if progress:
            progress(msg)

    _step("Fetching Kyubi...")
    apk = magisk_payload.fetch_apk(_cache_dir(), progress=progress)
    work = tempfile.mkdtemp(prefix="kyubi-air-")
    tools = magisk_payload.extract_tools(apk, os.path.join(work, "tools"),
                                         progress=progress, arm64=True)
    extras = magisk_payload.extract_databin_extras(apk, os.path.join(work, "extras"),
                                                   progress=progress)
    payload_sha = _sha256(apk)

    image = macos_locator.root_image_path(app_path)
    state = macos_root.read_modstate(app_path, data_dir)
    active = macos_root.applied_modifications(state)
    macos_root.ensure_backup(image, data_dir, image_is_pristine=not active, step=_step)

    results: list[str] = []
    with macos_root.open_image(app_path, progress, results=results) as img:
        if state.get("root"):
            _step("Removing the plain su (Kyubi provides its own)...")
            img.run("rm %s\nquit\n" % macos_root.SU_IMAGE_PATH)
            results.append("removed %s" % macos_root.SU_GUEST_PATH)

        _step("Writing Kyubi into the system image...")
        current = img.read_file(BOOTANIM)
        if current is None:
            raise macos_root.RootError("The system image has no %s to hook." % BOOTANIM)
        stock = current
        if "magisk" in current:
            # Reinstall/update over an existing install: the stock file is the
            # gzipped copy the first install kept, not the hooked one in place.
            stock = _read_stock_backup(img)
            if stock is None:
                raise macos_root.RootError(
                    "Kyubi's boot hook is present but the original bootanim.rc "
                    "backup is missing, so it cannot be reinstalled safely.")
        if "Inode:" in img.run("stat %s\nquit\n" % MAGISK_DIR):
            _remove_magisk_dir(img)
        img.run("mkdir %s\nsif %s mode 040700\nsif %s uid 0\nsif %s gid 0\nquit\n"
                % (MAGISK_DIR, MAGISK_DIR, MAGISK_DIR, MAGISK_DIR))

        files = dict(tools)
        files.update(extras)
        files["config"] = _write_host_file(work, "config", CONFIG.encode())
        files[STAGE_SCRIPT] = _write_host_file(work, STAGE_SCRIPT, STAGE_BODY.encode())
        files[ADB_GRANT_SCRIPT] = _write_host_file(work, ADB_GRANT_SCRIPT,
                                                   ADB_GRANT_BODY.encode())
        files[STAMP] = _write_host_file(work, STAMP, (payload_sha + "\n").encode())
        for name, host in sorted(files.items()):
            _put(img, host, "%s/%s" % (MAGISK_DIR, name), mode=0o100700)

        if "magisk" not in current:
            _put(img, _write_host_file(work, "bootanim.rc.gz",
                                       gzip.compress(stock.encode())),
                 BOOTANIM_GZ, mode=0o100600)
        _put(img, _write_host_file(work, "bootanim.rc", _hook_bootanim(stock).encode()),
             BOOTANIM, mode=0o100664, uid=1000, gid=1000)
        results.append("installed Kyubi into %s" % GUEST_MAGISK_DIR)

    state["root"] = False
    state["kyubi"] = {"version": magisk_payload.PAYLOAD_VERSION,
                      "payload_sha256": payload_sha,
                      "components": ["system"]}
    macos_root.write_modstate(app_path, data_dir, state)
    _step("Kyubi installed. Start BlueStacks to finish setup.")
    results.append("Kyubi installed. Start BlueStacks to finish setup.")
    return results


def uninstall(app_path: str, progress=None,
              data_dir: str = macos_locator.DATA_DIR) -> list[str]:
    """Remove Kyubi from the Air system image. BlueStacks must be closed."""
    def _step(msg: str) -> None:
        logger.info(msg)
        if progress:
            progress(msg)

    image = macos_locator.root_image_path(app_path)
    state = macos_root.read_modstate(app_path, data_dir)
    active = macos_root.applied_modifications(state)
    results: list[str] = []

    # Last edit standing: put the untouched image back, byte for byte, which
    # also repairs BlueStacks.app's signature.
    if not (active - {"kyubi"}) and os.path.isfile(macos_root.backup_path(data_dir)):
        results += macos_root.restore_pristine(image, data_dir, _step)
        macos_root.write_modstate(app_path, data_dir, {})
        _step("Kyubi removed. Restart BlueStacks for the change to take effect.")
        return results

    with macos_root.open_image(app_path, progress, results=results) as img:
        _step("Removing Kyubi from the system image...")
        stock = _read_stock_backup(img)
        if stock is not None:
            _put(img, _write_host_file(img.workdir, "bootanim.rc", stock.encode()),
                 BOOTANIM, mode=0o100664, uid=1000, gid=1000)
            img.run("rm %s\nquit\n" % BOOTANIM_GZ)
        if "Inode:" in img.run("stat %s\nquit\n" % MAGISK_DIR):
            _remove_magisk_dir(img)
        results.append("removed Kyubi from %s" % GUEST_MAGISK_DIR)

    state["kyubi"] = None
    macos_root.write_modstate(app_path, data_dir, state)
    _step("Kyubi removed. Restart BlueStacks for the change to take effect.")
    results.append("Kyubi removed. Start BlueStacks to use it without root.")
    return results


def add_component(app_path: str, component: str,
                  data_dir: str = macos_locator.DATA_DIR) -> None:
    state = macos_root.read_modstate(app_path, data_dir)
    kyubi = state.get("kyubi")
    if not kyubi:
        return
    comps = set(kyubi.get("components") or [])
    comps.add(component)
    kyubi["components"] = sorted(comps)
    # Re-stamping is safe here: the image has not changed since read_modstate
    # validated it.
    macos_root.write_modstate(app_path, data_dir, state)


def remove_component(app_path: str, component: str,
                     data_dir: str = macos_locator.DATA_DIR) -> None:
    state = macos_root.read_modstate(app_path, data_dir)
    kyubi = state.get("kyubi")
    if not kyubi:
        return
    kyubi["components"] = sorted(set(kyubi.get("components") or []) - {component})
    macos_root.write_modstate(app_path, data_dir, state)
