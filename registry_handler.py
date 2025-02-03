import winreg
import logging

# Initialize logger for registry_handler module
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO) # Or desired level, if not set at root logger


def get_bluestacks_path(key_name="DataDir"):
    """Retrieves a registry value from HKEY_LOCAL_MACHINE\SOFTWARE\BlueStacks_nxt.

    Args:
        key_name (str): The name of the registry value to retrieve (default: "DataDir").

    Returns:
        str: The registry value if found, None otherwise.
    """
    reg_path = r"SOFTWARE\\BlueStacks_nxt"
    try:
        logger.debug(f"Attempting to read registry key '{key_name}' from path: HKLM\\{reg_path}")
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, reg_path) as key:
            value, _ = winreg.QueryValueEx(key, key_name)
            logger.debug(f"Registry key '{key_name}' found with value: {value}")
            return value
    except FileNotFoundError:
        error_msg = f"Registry key '{key_name}' not found under HKLM\\{reg_path}"
        logger.warning(error_msg) # Use warning as it's not necessarily critical error
        print(error_msg) # Keep print for immediate user feedback if needed
        return None
    except Exception as e:
        error_msg = f"Error accessing registry path HKLM\\{reg_path}: {e}"
        logger.exception(error_msg)
        print(error_msg)
        return None