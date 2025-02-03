import os
import glob
import logging

# Initialize logger for config_handler module
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO) # Or desired level, if not set at root logger

def modify_config_file(config_path, setting, new_value):
    """Modifies a setting in bluestacks.conf.

    Args:
        config_path (str): Path to the bluestacks.conf file.
        setting (str): The setting to modify (e.g., "bst.feature.rooting").
        new_value (str): The new value for the setting.
    """
    changed = False
    try:
        logger.debug(f"Attempting to modify setting '{setting}' in config file: {config_path}")
        # Open with encoding='utf-8' for reading
        with open(config_path, "r", encoding='utf-8') as f:
            lines = f.readlines()

        # Open with encoding='utf-8' for writing
        with open(config_path, "w", encoding='utf-8') as f:
            for line in lines:
                if line.startswith(f"{setting}="):
                    logger.debug(f"Found setting '{setting}', replacing value. Original line: '{line.strip()}'")
                    f.write(f"{setting}=\"{new_value}\"\n")
                    changed = True
                    logger.debug(f"Setting '{setting}' updated to '{new_value}'")
                else:
                    f.write(line)

        if changed:
            logger.info(f"Successfully updated setting '{setting}' to '{new_value}' in {config_path}")
        else:
            logger.info(f"Setting '{setting}' not found in {config_path}, no changes made.")
    except FileNotFoundError:
        error_msg = f"Config file not found at {config_path}"
        logger.error(error_msg)
        print(error_msg) # Keep print for user feedback if needed in CLI context, but logging is primary
    except Exception as e:
        error_msg = f"Error modifying configuration file {config_path}: {e}"
        logger.exception(error_msg) # Log full exception traceback
        print(error_msg) # Keep print for user feedback


def is_root_enabled(config_path, instance_name):
    """Checks if root access is enabled for a specific instance.

    Args:
        config_path (str): Path to the bluestacks.conf file.
        instance_name (str): The name of the BlueStacks instance.

    Returns:
        bool: True if root access is enabled, False otherwise.
    """
    try:
        setting_key = f"bst.instance.{instance_name}.enable_root_access="
        logger.debug(f"Checking root status for instance '{instance_name}' in {config_path}")
        # Open with encoding='utf-8' for reading
        with open(config_path, "r", encoding='utf-8') as f:
            for line in f:
                if line.startswith(setting_key):
                    is_enabled = line.strip().endswith("=\"1\"")
                    logger.debug(f"Root status for instance '{instance_name}': {'Enabled' if is_enabled else 'Disabled'}")
                    return is_enabled
        logger.debug(f"Root setting '{setting_key}' not found for instance '{instance_name}' in {config_path}. Assuming root is disabled.")
        return False # Setting not found, assume root is disabled
    except FileNotFoundError:
        error_msg = f"Config file not found at {config_path}"
        logger.error(error_msg)
        print(error_msg)
        return False
    except Exception as e:
        error_msg = f"Error reading configuration file {config_path}: {e}"
        logger.exception(error_msg)
        print(error_msg)
        return False