"""Application constants."""
import re

INSTANCE_PREFIX = "bst.instance."
ENABLE_ROOT_KEY = ".enable_root_access"
FEATURE_ROOTING_KEY = "bst.feature.rooting"
BLUESTACKS_CONF_FILENAME = "bluestacks.conf"


REGISTRY_BASE_PATH = r"SOFTWARE\BlueStacks_nxt"
REGISTRY_MSI_BASE_PATH = r"SOFTWARE\BlueStacks_msi5"
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


MODE_READWRITE = "Normal"
MODE_READONLY = "Readonly"
MODE_UNKNOWN = "Unknown"


FASTBOOT_VDI = "fastboot.vdi"
ROOT_VHD = "Root.vhd"

FILES_TO_MODIFY_RW = [FASTBOOT_VDI, ROOT_VHD]


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


APP_ID = "RobThePCGuy.BlueStacksRootGUI.2.6"
APP_NAME = "BlueStacks Root GUI"
ICON_FILENAME = "favicon.ico"