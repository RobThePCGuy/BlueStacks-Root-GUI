import winreg
import logging
import os
from typing import Optional, List, Dict, Any

import constants

logger = logging.getLogger(__name__)

Installation = Dict[str, Any]

def get_all_bluestacks_installations() -> List[Installation]:
    installations: List[Installation] = []
    reg_sources = {
        constants.APP_SOURCE_NXT: constants.REGISTRY_BASE_PATH,
        constants.APP_SOURCE_MSI: constants.REGISTRY_MSI_BASE_PATH,
    }

    for source_name, reg_path in reg_sources.items():
        full_reg_path_log = f"HKEY_LOCAL_MACHINE\\{reg_path}"
        user_dir = None
        data_dir = None
        try:
            with winreg.OpenKey(
                winreg.HKEY_LOCAL_MACHINE, reg_path, 0, winreg.KEY_READ
            ) as key:
                logger.debug(f"Successfully opened registry key: {full_reg_path_log} for {source_name}")
                try:
                    reg_value, reg_type = winreg.QueryValueEx(key, constants.REGISTRY_USER_DIR_KEY)
                    if reg_type == winreg.REG_SZ:
                        user_dir = str(reg_value)
                        logger.info(f"Found '{constants.REGISTRY_USER_DIR_KEY}' for {source_name}: {user_dir}")
                except FileNotFoundError:
                    logger.debug(f"'{constants.REGISTRY_USER_DIR_KEY}' not found for {source_name}.")
                except Exception as e:
                    logger.error(f"Error reading '{constants.REGISTRY_USER_DIR_KEY}' for {source_name}: {e}")

                try:
                    reg_value, reg_type = winreg.QueryValueEx(key, constants.REGISTRY_DATA_DIR_KEY)
                    if reg_type == winreg.REG_SZ:
                        data_dir = str(reg_value)
                        logger.info(f"Found '{constants.REGISTRY_DATA_DIR_KEY}' for {source_name}: {data_dir}")
                except FileNotFoundError:
                    logger.debug(f"'{constants.REGISTRY_DATA_DIR_KEY}' not found for {source_name}.")
                except Exception as e:
                    logger.error(f"Error reading '{constants.REGISTRY_DATA_DIR_KEY}' for {source_name}: {e}")

            if user_dir and data_dir:
                config_path = os.path.join(user_dir, constants.BLUESTACKS_CONF_FILENAME)
                installations.append({
                    "source": source_name,
                    "user_path": user_dir,
                    "data_path": data_dir,
                    "config_path": config_path,
                })

        except FileNotFoundError:
            logger.debug(f"Registry path not found for {source_name}: {full_reg_path_log}")
            continue
        except PermissionError:
            logger.error(f"Permission denied accessing registry for {source_name} at {full_reg_path_log}. Try running as administrator.")
            continue
        except Exception as e:
            logger.exception(f"An unexpected error occurred accessing registry for {source_name} at {full_reg_path_log}: {e}")
            continue

    return installations