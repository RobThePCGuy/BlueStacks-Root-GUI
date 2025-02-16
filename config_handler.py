import os
import glob
import logging

# Initialize logger for config_handler module
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)  # Or desired level, if not set at root logger


def modify_config_file(config_path, setting, new_value):
    """Modifies a setting in bluestacks.conf.

    Args:
        config_path (str): Path to the bluestacks.conf file.
        setting (str): The setting to modify (e.g., "bst.feature.rooting").
        new_value (str): The new value for the setting.
    """
    changed = False
    try:
        logger.debug(f"Attempting to modify setting '{setting}' to '{new_value}' in config file: {config_path}")
        # Open with encoding='utf-8' for reading
        with open(config_path, "r", encoding='utf-8') as f:
            lines = f.readlines()

        updated_lines = []
        setting_found = False # Flag to check if setting was found
        for line in lines:
            if line.startswith(f"{setting}="):
                logger.debug(f"Found setting '{setting}', replacing value. Original line: '{line.strip()}'")
                updated_lines.append(f"{setting}=\"{new_value}\"\n")
                changed = True
                setting_found = True
                logger.info(f"Setting '{setting}' updated to '{new_value}' in {config_path}") # Info level for successful modification
            else:
                updated_lines.append(line)

        if not setting_found: # Setting not found, append it to the end
            updated_lines.append(f"{setting}=\"{new_value}\"\n")
            changed = True
            logger.info(f"Setting '{setting}' not found, appending to {config_path} with value '{new_value}'.")


        # Open with encoding='utf-8' for writing
        with open(config_path, "w", encoding='utf-8') as f:
            f.writelines(updated_lines)


    except FileNotFoundError:
        error_msg = f"Config file not found at {config_path}"
        logger.error(error_msg)
        print(error_msg)  # Keep print for user feedback if needed in CLI context, but logging is primary
        logger.debug("Full exception details:", exc_info=True)
    except Exception as e:
        error_msg = f"Error modifying configuration file {config_path}: {e}"
        logger.exception(error_msg)  # Log full exception traceback
        print(error_msg)  # Keep print for user feedback
        logger.debug("Full exception details:", exc_info=True)



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
        logger.debug(f"Checking root status for instance '{instance_name}' in {config_path}, setting key: '{setting_key}'")
        # Open with encoding='utf-8' for reading
        with open(config_path, "r", encoding='utf-8') as f:
            for line in f:
                if line.startswith(setting_key):
                    is_enabled = line.strip().endswith("=\"1\"")
                    logger.info(f"Root status for instance '{instance_name}': {'Enabled' if is_enabled else 'Disabled'} in {config_path}") # Info level for root status
                    return is_enabled
        logger.info(f"Root setting '{setting_key}' not found for instance '{instance_name}' in {config_path}. Assuming root is disabled.") # Info level for not found, but assuming disabled is important info
        return False  # Setting not found, assume root is disabled
    except FileNotFoundError:
        error_msg = f"Config file not found at {config_path}"
        logger.error(error_msg)
        print(error_msg)
        logger.debug("Full exception details:", exc_info=True)
        return False
    except Exception as e:
        error_msg = f"Error reading configuration file {config_path}: {e}"
        logger.exception(error_msg)
        print(error_msg)
        logger.debug("Full exception details:", exc_info=True)
        return False
