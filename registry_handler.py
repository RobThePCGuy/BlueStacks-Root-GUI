import winreg
import logging

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

def get_bluestacks_path(key_name: str = "DataDir") -> str:
    """
    Retrieves a registry value from HKEY_LOCAL_MACHINE\SOFTWARE\BlueStacks_nxt.

    Args:
        key_name (str): The registry key name (default "DataDir").

    Returns:
        str: The registry value if found; otherwise, None.
    """
    reg_path = r"SOFTWARE\BlueStacks_nxt"
    full_reg_path = f"HKLM\\{reg_path}"
    try:
        logger.debug(f"Reading registry key '{key_name}' from {full_reg_path}")
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, reg_path) as key:
            value, _ = winreg.QueryValueEx(key, key_name)
            logger.info(f"Found registry key '{key_name}' with value: {value}")
            return value
    except FileNotFoundError:
        error_msg = f"Registry key '{key_name}' not found under {full_reg_path}"
        logger.warning(error_msg, exc_info=True)
    except PermissionError:
        error_msg = f"Permission error accessing registry {full_reg_path}. Run as administrator."
        logger.error(error_msg, exc_info=True)
    except Exception as e:
        error_msg = f"Error accessing registry {full_reg_path}: {e}"
        logger.exception(error_msg)
    return None