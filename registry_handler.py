# registry_handler.py
import winreg
import logging
from typing import Optional


import constants

logger = logging.getLogger(__name__)


def get_bluestacks_path(
    key_name: str = constants.REGISTRY_DATA_DIR_KEY,
) -> Optional[str]:
    r"""
    Retrieves a specific registry string value from the BlueStacks or MSI App
    Player registry keys.

    Checks ``HKEY_LOCAL_MACHINE\SOFTWARE\BlueStacks_nxt`` first and then
    ``HKEY_LOCAL_MACHINE\SOFTWARE\BlueStacks_msi5`` if not found.

    Args:
        key_name: The registry value name to retrieve (e.g., ``DataDir`` or
            ``UserDefinedDir``). Defaults to
            ``constants.REGISTRY_DATA_DIR_KEY``.

    Returns:
        The string value of the registry key if found and of type ``REG_SZ``.
        ``None`` if the key or value is missing, access is denied, the value is
        not a string, or any other error occurs.
    """

    value: Optional[str] = None
    for reg_path in (constants.REGISTRY_BASE_PATH, constants.REGISTRY_MSI_BASE_PATH):
        full_reg_path_log = f"HKEY_LOCAL_MACHINE\\{reg_path}"
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
                    logger.info(
                        f"Found registry key '{key_name}' with value: {value}"
                    )
                    return value
                else:
                    logger.warning(
                        f"Registry key '{key_name}' found but is not a string (Type: {reg_type}). Value: {reg_value}"
                    )
        except FileNotFoundError:
            logger.debug(
                f"Registry path {full_reg_path_log} or value '{key_name}' not found."
            )
            continue
        except PermissionError:
            logger.error(
                f"Permission denied accessing registry value '{key_name}' at {full_reg_path_log}. Try running as administrator."
            )
            return None
        except OSError as e:
            if e.winerror == 5:
                logger.error(
                    f"Permission denied accessing registry value '{key_name}' at {full_reg_path_log} (OSError: {e}). Try running as administrator."
                )
            elif e.winerror == 2:
                logger.debug(
                    f"Registry path {full_reg_path_log} or value name '{key_name}' not found (OSError: {e})."
                )
                continue
            else:
                logger.error(
                    f"OS error accessing registry value '{key_name}' at {full_reg_path_log}: {e}"
                )
            return None
        except Exception as e:
            logger.exception(
                f"An unexpected error occurred accessing registry value '{key_name}' at {full_reg_path_log}: {e}"
            )
            return None

    return value
