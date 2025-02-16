import winreg
import logging

# Initialize logger for registry_handler module
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)  # Or desired level, if not set at root logger


def get_bluestacks_path(key_name="DataDir"):
    """Retrieves a registry value from HKEY_LOCAL_MACHINE\SOFTWARE\BlueStacks_nxt.

    Args:
        key_name (str): The name of the registry value to retrieve (default: "DataDir").

    Returns:
        str: The registry value if found, None otherwise.
    """
    reg_path = r"SOFTWARE\\BlueStacks_nxt"
    full_reg_path = f"HKLM\\{reg_path}" # For clearer log messages

    try:
        logger.debug(f"Attempting to read registry key '{key_name}' from path: {full_reg_path}")
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, reg_path) as key:
            value, _ = winreg.QueryValueEx(key, key_name)
            logger.info(f"Registry key '{key_name}' found at '{full_reg_path}' with value: {value}") # Info level for success
            return value
    except FileNotFoundError:
        error_msg = f"Registry key '{key_name}' not found under {full_reg_path}"
        logger.warning(error_msg)  # Use warning as it's not critical, but important to note
        print(error_msg)  # Keep print for immediate user feedback if needed
        logger.debug("Full exception details:", exc_info=True) # Debug level for exception details
        return None
    except PermissionError:
        error_msg = f"Permission error accessing registry path {full_reg_path}. Please run as administrator."
        logger.error(error_msg) # Error level for permission issues
        print(error_msg)
        logger.debug("Full exception details:", exc_info=True)
        return None
    except Exception as e:
        error_msg = f"Error accessing registry path {full_reg_path}: {e}"
        logger.exception(error_msg) # Exception for unexpected errors
        print(error_msg)
        return None