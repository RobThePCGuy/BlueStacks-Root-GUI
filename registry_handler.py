# registry_handler.py
import winreg
import logging
from typing import Optional


import constants

logger = logging.getLogger(__name__)


def get_bluestacks_path(
    key_name: str = constants.REGISTRY_DATA_DIR_KEY,
) -> Optional[str]:
    """
    Retrieves a specific registry string value from the BlueStacks registry key.

    Looks under HKEY_LOCAL_MACHINE\\SOFTWARE\\BlueStacks_nxt.

    Args:
        key_name: The registry value name to retrieve (e.g., "DataDir", "UserDefinedDir").
                  Defaults to constants.REGISTRY_DATA_DIR_KEY.

    Returns:
        The string value of the registry key if found and is of type REG_SZ.
        None if the path/key is not found, access is denied, the key is not
        a string, or any other error occurs.
    """

    reg_path = constants.REGISTRY_BASE_PATH
    full_reg_path_log = f"HKEY_LOCAL_MACHINE\\{reg_path}"
    value: Optional[str] = None

    try:
        logger.debug(f"Attempting to open registry key: {full_reg_path_log}")

        with winreg.OpenKey(
            winreg.HKEY_LOCAL_MACHINE, reg_path, 0, winreg.KEY_READ
        ) as key:
            logger.debug(
                f"Successfully opened registry key. Querying value for '{key_name}'."
            )

            reg_value, reg_type = winreg.QueryValueEx(key, key_name)

            if reg_type == winreg.REG_SZ:
                value = str(reg_value)
                logger.info(f"Found registry key '{key_name}' with value: {value}")
            else:
                logger.warning(
                    f"Registry key '{key_name}' found but is not a string (Type: {reg_type}). Value: {reg_value}"
                )
                value = None

    except FileNotFoundError:
        logger.warning(
            f"Registry path {full_reg_path_log} or value name '{key_name}' not found."
        )
        value = None
    except PermissionError:

        logger.error(
            f"Permission denied accessing registry value '{key_name}' at {full_reg_path_log}. Try running as administrator."
        )
        value = None
    except OSError as e:

        if e.winerror == 5:
            logger.error(
                f"Permission denied accessing registry value '{key_name}' at {full_reg_path_log} (OSError: {e}). Try running as administrator."
            )
        elif e.winerror == 2:
            logger.warning(
                f"Registry path {full_reg_path_log} or value name '{key_name}' not found (OSError: {e})."
            )
        else:
            logger.error(
                f"OS error accessing registry value '{key_name}' at {full_reg_path_log}: {e}"
            )
        value = None
    except Exception as e:
        logger.exception(
            f"An unexpected error occurred accessing registry value '{key_name}' at {full_reg_path_log}: {e}"
        )
        value = None

    return value
