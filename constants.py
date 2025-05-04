# constants.py
import re

INSTANCE_PREFIX = "bst.instance."
ENABLE_ROOT_KEY = ".enable_root_access"
FEATURE_ROOTING_KEY = "bst.feature.rooting"
BLUESTACKS_CONF_FILENAME = "bluestacks.conf"


REGISTRY_BASE_PATH = r"SOFTWARE\BlueStacks_nxt"
REGISTRY_DATA_DIR_KEY = "DataDir"
REGISTRY_USER_DIR_KEY = "UserDefinedDir"


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


APP_ID = "RobThePCGuy.BlueStacksRootGUI.2.1"
APP_NAME = "BlueStacks Root GUI"
ICON_FILENAME = "favicon.ico"
