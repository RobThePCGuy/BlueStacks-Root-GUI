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
    # (registry value name, parser for a REG_SZ value) -- read and logged the
    # same way for every key; only the parser differs (Version needs
    # constants.parse_version, the rest are plain strings).
    value_specs = (
        (constants.REGISTRY_USER_DIR_KEY, str),
        (constants.REGISTRY_DATA_DIR_KEY, str),
        (constants.REGISTRY_INSTALL_DIR_KEY, str),
        (constants.REGISTRY_VERSION_KEY, constants.parse_version),
    )

    for source_name, reg_path in reg_sources.items():
        full_reg_path_log = f"HKEY_LOCAL_MACHINE\\{reg_path}"
        values: dict[str, Any] = {}
        try:
            with winreg.OpenKey(
                winreg.HKEY_LOCAL_MACHINE, reg_path, 0, winreg.KEY_READ
            ) as key:
                logger.debug(f"Successfully opened registry key: {full_reg_path_log} for {source_name}")
                for key_name, parse in value_specs:
                    try:
                        reg_value, reg_type = winreg.QueryValueEx(key, key_name)
                        if reg_type == winreg.REG_SZ:
                            values[key_name] = parse(reg_value)
                            logger.info(f"Found '{key_name}' for {source_name}: {values[key_name]}")
                    except FileNotFoundError:
                        logger.debug(f"'{key_name}' not found for {source_name}.")
                    except Exception as e:
                        logger.error(f"Error reading '{key_name}' for {source_name}: {e}")

            user_dir = values.get(constants.REGISTRY_USER_DIR_KEY)
            data_dir = values.get(constants.REGISTRY_DATA_DIR_KEY)
            install_dir = values.get(constants.REGISTRY_INSTALL_DIR_KEY)
            version = values.get(constants.REGISTRY_VERSION_KEY)
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
