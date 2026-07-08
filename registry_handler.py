from __future__ import annotations

import winreg
import logging
import os
from typing import Any

import constants

logger = logging.getLogger(__name__)

Installation = dict[str, Any]

def get_all_bluestacks_installations() -> list[Installation]:
    installations: list[Installation] = []
    reg_sources = {
        constants.APP_SOURCE_NXT: constants.REGISTRY_BASE_PATH,
        constants.APP_SOURCE_NXT_CN: constants.REGISTRY_CN_BASE_PATH,
        constants.APP_SOURCE_MSI: constants.REGISTRY_MSI_BASE_PATH,
    }

    for source_name, reg_path in reg_sources.items():
        full_reg_path_log = f"HKEY_LOCAL_MACHINE\\{reg_path}"
        user_dir = None
        data_dir = None
        install_dir = None
        version = None
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

                try:
                    reg_value, reg_type = winreg.QueryValueEx(key, constants.REGISTRY_INSTALL_DIR_KEY)
                    if reg_type == winreg.REG_SZ:
                        install_dir = str(reg_value)
                        logger.info(f"Found '{constants.REGISTRY_INSTALL_DIR_KEY}' for {source_name}: {install_dir}")
                except FileNotFoundError:
                    logger.debug(f"'{constants.REGISTRY_INSTALL_DIR_KEY}' not found for {source_name}.")
                except Exception as e:
                    logger.error(f"Error reading '{constants.REGISTRY_INSTALL_DIR_KEY}' for {source_name}: {e}")

                try:
                    reg_value, reg_type = winreg.QueryValueEx(key, constants.REGISTRY_VERSION_KEY)
                    if reg_type == winreg.REG_SZ:
                        version = constants.parse_version(reg_value)
                        logger.info(f"Found '{constants.REGISTRY_VERSION_KEY}' for {source_name}: {reg_value} -> {version}")
                except FileNotFoundError:
                    logger.debug(f"'{constants.REGISTRY_VERSION_KEY}' not found for {source_name}.")
                except Exception as e:
                    logger.error(f"Error reading '{constants.REGISTRY_VERSION_KEY}' for {source_name}: {e}")

            if user_dir and data_dir:
                config_path = os.path.join(user_dir, constants.BLUESTACKS_CONF_FILENAME)
                installations.append({
                    "source": source_name,
                    "user_path": user_dir,
                    "data_path": data_dir,
                    "install_path": install_dir,
                    "config_path": config_path,
                    "version": version,
                    "patch_mode": bool(version and version >= constants.PATCH_MIN_VERSION),
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
