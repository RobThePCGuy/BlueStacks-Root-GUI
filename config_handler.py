import os
import logging

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

def modify_config_file(config_path: str, setting: str, new_value: str) -> bool:
    """
    Modifies a setting in the bluestacks.conf file.

    Args:
        config_path (str): Path to the configuration file.
        setting (str): The configuration key (e.g., "bst.feature.rooting").
        new_value (str): The new value for the setting.

    Returns:
        bool: True if any change was made; otherwise False.
    """
    changed = False
    try:
        logger.debug(f"Modifying setting '{setting}' to '{new_value}' in {config_path}")
        with open(config_path, "r", encoding="utf-8") as file:
            lines = file.readlines()

        updated_lines = []
        setting_found = False
        for line in lines:
            if line.startswith(f"{setting}="):
                logger.debug(f"Replacing line: {line.strip()}")
                updated_lines.append(f'{setting}="{new_value}"\n')
                changed = True
                setting_found = True
                logger.info(f"Updated setting '{setting}' to '{new_value}' in {config_path}")
            else:
                updated_lines.append(line)

        if not setting_found:
            updated_lines.append(f'{setting}="{new_value}"\n')
            changed = True
            logger.info(f"Appended setting '{setting}' with value '{new_value}' to {config_path}")

        with open(config_path, "w", encoding="utf-8") as file:
            file.writelines(updated_lines)

    except FileNotFoundError:
        error_msg = f"Config file not found: {config_path}"
        logger.error(error_msg, exc_info=True)
    except Exception as e:
        error_msg = f"Error modifying configuration file {config_path}: {e}"
        logger.exception(error_msg)
    return changed

def is_root_enabled(config_path: str, instance_name: str) -> bool:
    """
    Checks if root access is enabled for a given instance.

    Args:
        config_path (str): Path to the configuration file.
        instance_name (str): The name of the instance.

    Returns:
        bool: True if root is enabled; otherwise False.
    """
    try:
        setting_key = f"bst.instance.{instance_name}.enable_root_access="
        logger.debug(f"Checking root access for instance '{instance_name}' with key '{setting_key}' in {config_path}")
        with open(config_path, "r", encoding="utf-8") as file:
            for line in file:
                if line.startswith(setting_key):
                    is_enabled = line.strip().endswith('="1"')
                    logger.info(f"Root access for instance '{instance_name}' is {'enabled' if is_enabled else 'disabled'}")
                    return is_enabled
        logger.info(f"Setting '{setting_key}' not found in {config_path}. Assuming root is disabled.")
    except FileNotFoundError:
        error_msg = f"Config file not found: {config_path}"
        logger.error(error_msg, exc_info=True)
    except Exception as e:
        error_msg = f"Error reading config file {config_path}: {e}"
        logger.exception(error_msg)
    return False
