"""Application constants."""
from __future__ import annotations

import re

INSTANCE_PREFIX = "bst.instance."
ENABLE_ROOT_KEY = ".enable_root_access"
DISPLAY_NAME_KEY = ".display_name"
FEATURE_ROOTING_KEY = "bst.feature.rooting"
BLUESTACKS_CONF_FILENAME = "bluestacks.conf"


REGISTRY_BASE_PATH = r"SOFTWARE\BlueStacks_nxt"
REGISTRY_MSI_BASE_PATH = r"SOFTWARE\BlueStacks_msi5"
REGISTRY_CN_BASE_PATH = r"SOFTWARE\BlueStacks_nxt_cn"
REGISTRY_DATA_DIR_KEY = "DataDir"
REGISTRY_USER_DIR_KEY = "UserDefinedDir"
# Program-files directory that holds HD-Player.exe etc. (for the integrity patch)
REGISTRY_INSTALL_DIR_KEY = "InstallDir"
REGISTRY_VERSION_KEY = "Version"

# Builds at/after this introduced the disk-integrity check and the signed-whitelist
# guest su, which require the binary + offline-su patches. Older builds use the
# classic conf-based rooting (enable_root_access keys) and hide the patch buttons.
PATCH_MIN_VERSION = (5, 22, 150, 1014)


def parse_version(s):
    """'5.22.166.1003' -> (5, 22, 166, 1003); None on failure."""
    try:
        return tuple(int(x) for x in str(s).strip().split("."))
    except Exception:
        return None

# FIX: Add constants to identify the source application
APP_SOURCE_NXT = "NXT"
APP_SOURCE_MSI = "MSI"
APP_SOURCE_NXT_CN = "CN"


MODE_READWRITE = "Normal"
MODE_READONLY = "Readonly"
MODE_UNKNOWN = "Unknown"


FASTBOOT_VDI = "fastboot.vdi"
ROOT_VHD = "Root.vhd"
DATA_VHDX = "Data.vhdx"

# Disks whose Type= the R/W *toggle* flips. Only the system disks -- never
# Data.vhdx (userdata), which must stay writable or the instance won't boot.
FILES_TO_MODIFY_RW = [FASTBOOT_VDI, ROOT_VHD]

# Disks read when *detecting* an instance's R/W state. Newer BlueStacks
# instances (created/cloned) ship a single Data.vhdx and no fastboot.vdi/
# Root.vhd, so their .bstk only references Data.vhdx. We include it here so
# such instances are recognized (and listed) instead of coming back "Unknown".
RW_DETECT_FILES = [FASTBOOT_VDI, ROOT_VHD, DATA_VHDX]


ANDROID_BSTK_IN_FILE = "Android.bstk.in"
BSTK_FILE_PATTERN = "*.bstk"


REGEX_BSTK_TYPE_PATTERN = re.compile(
    r'(Type\s*=\s*")' + f"({MODE_READONLY}|{MODE_READWRITE})" + r'(")', re.IGNORECASE
)

REGEX_BSTK_READONLY_PATTERN = re.compile(
    r'Type\s*=\s*"' + MODE_READONLY + r'"', re.IGNORECASE
)


BLUESTACKS_PROCESS_NAMES = [
    "HD-Player.exe",
    # Must be terminated before patching: the engine patch rewrites
    # HD-MultiInstanceManager.exe, and Windows denies the write while the
    # Manager window is open (its .exe is locked).
    "HD-MultiInstanceManager.exe",
    "BlueStacks.exe",
    "HD-Agent.exe",
    "BstkSVC.exe",
    "HD-Frontend.exe",
    "HD-LogRotatorService.exe",
    "BlueStacksWebHelper.exe",
]


REFRESH_INTERVAL_MS = 5000
PROCESS_TERMINATION_WAIT_MS = 1500
PROCESS_KILL_TIMEOUT_S = 5
PROCESS_POST_KILL_WAIT_S = 2


APP_VERSION = "3.0.0"
APP_ID = f"RobThePCGuy.BlueStacksRootGUI.{APP_VERSION}"
APP_NAME = "BlueStacks Root GUI"
ICON_FILENAME = "favicon.ico"
