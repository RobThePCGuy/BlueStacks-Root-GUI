"""Locate a BlueStacks Air install -- the macOS counterpart to ``registry_handler``.

macOS has no registry, and Air does not need one: every path this tool wants is
either fixed by the installer or recorded in a small plist. Detection therefore
reads the filesystem directly and returns the *same* installation dict shape
``registry_handler.get_all_bluestacks_installations()`` produces, so the UI and
``update_instance_data()`` do not care which backend found the install.

Layout (BlueStacks Air 5.21.782, Apple Silicon)
-----------------------------------------------
``/Applications/BlueStacks.app/Contents/``
    ``MacOS/``      the player, plus the tools this project reuses: ``hd-adb``
                    (guest ADB) and ``qemu-img`` (qcow2 conversion).
    ``img/``        ``Root.qcow2`` (the shared, read-only Android system image),
                    ``data-org.qcow2`` (pristine userdata template), and the
                    guest ``kernel_hvf`` / ``initrd_hvf.img``.
``/Users/Shared/Library/Application Support/BlueStacks/``
    ``bluestacks.conf``   the same key/value file Windows uses, same keys.
    ``Engine/<Name>/``    one directory per instance, holding that instance's
                          ``data.qcow2``. Note there is **no** per-instance
                          ``Root.qcow2``: every instance boots the one image in
                          the app bundle, which is why rooting on Air is
                          install-wide rather than per-instance.

Two Windows concepts have no analogue here and are reported as such:

* **The engine patch.** That patches ``HD-Player.exe``'s disk-integrity check,
  introduced in 5.22.150.1014. Air is 5.21.x, has no such check, and has no
  ``.exe`` to patch -- so ``patch_mode`` is always False.
* **R/W mode.** On Windows each instance owns ``Root.vhd``/``fastboot.vdi`` and
  a ``.bstk`` file whose ``Type="Readonly"`` this tool flips. Air ships no
  ``.bstk`` files at all and mounts the shared image read-only regardless, so
  there is nothing to toggle.
"""
from __future__ import annotations

import logging
import os
import plistlib
import struct
from typing import Any

import constants

logger = logging.getLogger(__name__)

Installation = dict[str, Any]

# The installer hard-codes both of these; ``setting.plist`` records the app
# location too, and is preferred when present so a relocated bundle still works.
DEFAULT_APP_PATH = "/Applications/BlueStacks.app"
DATA_DIR = "/Users/Shared/Library/Application Support/BlueStacks"

SETTING_PLIST = os.path.join(DATA_DIR, "setting.plist")
SETTING_PATH_KEY = "BlueStacks Air.path"          # -> <bundle>/Contents/MacOS

ENGINE_DIRNAME = "Engine"
IMG_DIRNAME = "img"
ROOT_IMAGE_NAME = "Root.qcow2"

PLAYER_NAME = "BlueStacks"          # Contents/MacOS/BlueStacks

# Mach-O header constants, used to tell the Apple Silicon build apart from an
# Intel one. Only the byte patterns are needed, so these are matched directly
# rather than unpacked into ints of ambiguous endianness.
_MACHO_64_LE = b"\xcf\xfa\xed\xfe"   # MH_MAGIC_64 on a little-endian host
_MACHO_64_BE = b"\xfe\xed\xfa\xcf"
_FAT_MAGIC = b"\xca\xfe\xba\xbe"     # universal binary (big-endian header)
_FAT_MAGIC_LE = b"\xbe\xba\xfe\xca"

ARCH_ARM64 = "arm64"
ARCH_X86_64 = "x86_64"
_CPU_TYPES = {0x0100000C: ARCH_ARM64, 0x01000007: ARCH_X86_64,
              0x0000000C: "arm", 0x00000007: "i386"}

# A universal binary with a silly arch count is corrupt, not something to walk.
_MAX_FAT_ARCHES = 16

# Bundled tools we reuse rather than requiring the user to install.
ADB_NAME = "hd-adb"
QEMU_IMG_NAME = "qemu-img"

# Directories under Engine/ that are not instances.
_NON_INSTANCE_DIRS = frozenset({"UserData"})


def _app_path_from_plist() -> str | None:
    """Bundle path recorded in ``setting.plist``, or None if unusable."""
    try:
        with open(SETTING_PLIST, "rb") as fh:
            data = plistlib.load(fh)
    except (OSError, plistlib.InvalidFileException):
        logger.debug("could not read %s", SETTING_PLIST, exc_info=True)
        return None

    macos_dir = data.get(SETTING_PATH_KEY)
    if not macos_dir:
        return None
    # The key points at <bundle>/Contents/MacOS; walk back up to the bundle.
    bundle = os.path.dirname(os.path.dirname(str(macos_dir)))
    return bundle if bundle.endswith(".app") else None


def find_app_path() -> str | None:
    """Path to ``BlueStacks.app``, or None when Air is not installed."""
    for candidate in (_app_path_from_plist(), DEFAULT_APP_PATH):
        if candidate and os.path.isdir(os.path.join(candidate, "Contents", "MacOS")):
            return candidate
    return None


def player_architectures(app_path: str) -> set[str]:
    """CPU architectures the BlueStacks player binary is built for.

    Used to refuse an Intel install rather than silently mistreating it as
    Air. The two macOS BlueStacks products are unrelated inside: the Apple
    Silicon one (Air) runs an **arm64** Android guest from a qcow2, while the
    Intel one is the older VirtualBox-based build with VHDX disks and an x86
    guest. Nothing here fits that -- and the failure would be quiet rather
    than loud, since ``macos_root`` would happily write an *aarch64* ``su``
    into an x86 guest, leaving a modified system image and an ``su`` that
    dies with an exec-format error.

    Returns an empty set if the binary is missing or unreadable.
    """
    path = os.path.join(app_path, "Contents", "MacOS", PLAYER_NAME)
    try:
        with open(path, "rb") as fh:
            head = fh.read(8)
            if len(head) < 8:
                return set()
            magic, rest = head[:4], head[4:8]

            if magic in (_FAT_MAGIC, _FAT_MAGIC_LE):
                # Universal binary: a big-endian count, then 20-byte entries
                # each starting with the cputype.
                count = struct.unpack(">I", rest)[0]
                found = set()
                for _ in range(min(count, _MAX_FAT_ARCHES)):
                    entry = fh.read(20)
                    if len(entry) < 20:
                        break
                    cpu = struct.unpack(">I", entry[:4])[0]
                    found.add(_CPU_TYPES.get(cpu, "cpu:0x%x" % cpu))
                return found

            if magic == _MACHO_64_LE:
                cpu = struct.unpack("<I", rest)[0]
            elif magic == _MACHO_64_BE:
                cpu = struct.unpack(">I", rest)[0]
            else:
                return set()
            return {_CPU_TYPES.get(cpu, "cpu:0x%x" % cpu)}
    except OSError:
        logger.debug("could not read %s", path, exc_info=True)
        return set()


def app_version(app_path: str) -> tuple[int, ...] | None:
    """Version tuple from the bundle's ``Info.plist`` (e.g. (5, 21, 782))."""
    try:
        with open(os.path.join(app_path, "Contents", "Info.plist"), "rb") as fh:
            data = plistlib.load(fh)
    except (OSError, plistlib.InvalidFileException):
        logger.debug("could not read Info.plist under %s", app_path, exc_info=True)
        return None
    return constants.parse_version(data.get("CFBundleShortVersionString", ""))


def root_image_path(app_path: str) -> str:
    """Path to the shared Android system image inside the bundle."""
    return os.path.join(app_path, "Contents", IMG_DIRNAME, ROOT_IMAGE_NAME)


def bundled_tool(app_path: str, name: str) -> str | None:
    """Path to an executable BlueStacks ships in ``Contents/MacOS``."""
    path = os.path.join(app_path, "Contents", "MacOS", name)
    return path if os.access(path, os.X_OK) else None


def engine_dir(data_dir: str = DATA_DIR) -> str:
    """Directory holding one subdirectory per instance."""
    return os.path.join(data_dir, ENGINE_DIRNAME)


def list_instance_dirs(data_dir: str = DATA_DIR) -> list[str]:
    """Instance directory names under ``Engine/`` (``UserData`` excluded)."""
    base = engine_dir(data_dir)
    try:
        return sorted(
            entry for entry in os.listdir(base)
            if entry not in _NON_INSTANCE_DIRS
            and os.path.isdir(os.path.join(base, entry))
        )
    except OSError:
        logger.debug("could not list %s", base, exc_info=True)
        return []


def get_all_bluestacks_installations() -> list[Installation]:
    """Detected Air installs, in ``registry_handler``'s dict shape.

    Returns at most one entry -- unlike Windows, where NXT / MSI / CN can be
    installed side by side, macOS supports a single BlueStacks.app.
    """
    app_path = find_app_path()
    if not app_path:
        logger.debug("No BlueStacks Air installation found.")
        return []

    # Fail closed on anything that is not the Apple Silicon build, including a
    # binary we cannot read: reporting nothing costs an Intel user a confusing
    # "not found", while proceeding would edit their system image with an
    # aarch64 payload it cannot run.
    arches = player_architectures(app_path)
    if ARCH_ARM64 not in arches:
        logger.warning(
            "BlueStacks at %s is not the Apple Silicon (Air) build -- player "
            "architecture %s. Only BlueStacks Air on Apple Silicon is "
            "supported; the Intel/x86 macOS build is a different, "
            "VirtualBox-based product this tool cannot root yet.",
            app_path, ", ".join(sorted(arches)) or "unreadable")
        return []

    config_path = os.path.join(DATA_DIR, constants.BLUESTACKS_CONF_FILENAME)
    if not os.path.isfile(config_path):
        # The bundle exists but BlueStacks has never been run, so there are no
        # instances and no conf. Report nothing rather than a half-install the
        # UI would render as an empty, un-actionable row.
        logger.info("BlueStacks Air found at %s but %s does not exist yet "
                    "(never launched?).", app_path, config_path)
        return []

    version = app_version(app_path)
    logger.info("Found BlueStacks Air %s at %s",
                ".".join(map(str, version)) if version else "?", app_path)

    return [{
        "source": constants.APP_SOURCE_AIR,
        "user_path": DATA_DIR,
        # Instance folders live under Engine/, not the data dir itself.
        "data_path": engine_dir(DATA_DIR),
        "install_path": os.path.join(app_path, "Contents", "MacOS"),
        "config_path": config_path,
        "version": version,
        # Air has neither the 5.22 integrity check nor an .exe to patch.
        "patch_mode": False,
        # Rooting Air means injecting su into the shared system image; the
        # conf-key mechanism that roots Windows BlueStacks does nothing here.
        "air_mode": True,
        "app_path": app_path,
    }]
