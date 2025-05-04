# config_handler.py
import os
import logging
import re
from typing import Dict, Optional


import constants

logger = logging.getLogger(__name__)


def modify_config_file(config_path: str, setting: str, new_value: str) -> bool:
    """
    Modifies a specific setting in the bluestacks.conf file.

    If the setting exists, its value is updated. If it doesn't exist,
    it's appended to the end of the file. Handles values enclosed
    in double quotes. Ensures the file is only written if changes are made.

    Args:
        config_path: Absolute path to the bluestacks.conf file.
        setting: The configuration key to modify (e.g., "bst.instance.Nougat64.enable_root_access").
        new_value: The desired string value for the setting (e.g., "1", "0").

    Returns:
        True if the file was modified, False otherwise.

    Raises:
        FileNotFoundError: If config_path does not point to an existing file.
        IOError: If there are problems reading or writing the file (caught as Exception).
        Exception: For other unexpected file I/O errors.
    """
    if not os.path.isfile(config_path):
        logger.error(f"Config file not found: {config_path}")
        raise FileNotFoundError(f"Config file not found: {config_path}")

    logger.debug(
        f"Attempting to modify setting '{setting}' to '{new_value}' in {config_path}"
    )

    new_line_content = f'{setting}="{new_value}"'

    lines = []
    try:

        with open(config_path, "r", encoding="utf-8") as file:
            lines = file.readlines()
    except Exception as e:
        logger.exception(f"Error reading configuration file {config_path}")
        raise IOError(f"Error reading configuration file {config_path}: {e}") from e

    updated_lines = []
    setting_found_and_updated = False
    changed = False

    setting_pattern = re.compile(r"^\s*" + re.escape(setting) + r"\s*=")

    for line in lines:
        stripped_line = line.strip()

        if setting_pattern.match(stripped_line):

            if stripped_line != new_line_content:
                logger.info(
                    f"Updating setting '{setting}'. Old line: '{stripped_line}', New line: '{new_line_content}'"
                )
                updated_lines.append(new_line_content + "\n")
                changed = True
            else:
                logger.debug(
                    f"Setting '{setting}' already has the desired value '{new_value}'. No change needed."
                )
                updated_lines.append(line)
            setting_found_and_updated = True
        else:
            updated_lines.append(line)

    if not setting_found_and_updated:
        logger.info(
            f"Setting '{setting}' not found. Appending with value '{new_value}'."
        )

        if updated_lines and not updated_lines[-1].endswith("\n"):
            updated_lines[-1] += "\n"
        updated_lines.append(new_line_content + "\n")
        changed = True

    if changed:
        try:
            with open(config_path, "w", encoding="utf-8") as file:
                file.writelines(updated_lines)
            logger.debug(f"Successfully wrote changes to {config_path}")
        except Exception as e:
            logger.exception(f"Error writing updated configuration file {config_path}")
            raise IOError(
                f"Error writing updated configuration file {config_path}: {e}"
            ) from e
    else:
        logger.debug(f"No changes were made to {config_path}.")

    return changed


def get_all_instance_root_statuses(config_path: str) -> Dict[str, bool]:
    """
    Reads the config file and returns a dictionary of instance names
    and their root status (True if enabled, False otherwise).

    Args:
        config_path: Path to the bluestacks.conf file.

    Returns:
        A dictionary mapping instance name (str) to root status (bool).
        Returns an empty dictionary if the file is not found or an error occurs during reading.
    """
    statuses: Dict[str, bool] = {}
    if not os.path.isfile(config_path):
        logger.warning(
            f"Config file not found for reading root statuses: {config_path}"
        )
        return statuses

    instance_pattern = re.compile(
        r"^"
        + re.escape(constants.INSTANCE_PREFIX)
        + r"([^.]+)"
        + re.escape(constants.ENABLE_ROOT_KEY)
        + r'\s*=\s*"([^"]*)"',
        re.IGNORECASE,
    )

    try:
        with open(config_path, "r", encoding="utf-8") as file:
            for line in file:
                match = instance_pattern.match(line.strip())
                if match:
                    instance_name = match.group(1)
                    value = match.group(2)
                    is_enabled = value == "1"
                    statuses[instance_name] = is_enabled
                    logger.debug(
                        f"Found root status for instance '{instance_name}': {'Enabled' if is_enabled else 'Disabled'}"
                    )
    except Exception:
        logger.exception(f"Error reading config file {config_path} for root statuses.")
        return {}

    if not statuses:
        logger.info(f"No instance root status settings found in {config_path}.")

    return statuses


def is_root_enabled(config_path: str, instance_name: str) -> Optional[bool]:
    """
    Checks if root access is enabled for a *single* given instance.

    Less efficient than get_all_instance_root_statuses if checking multiple instances.

    Args:
        config_path: Path to the configuration file.
        instance_name: The name of the instance.

    Returns:
        True if root is enabled ('="1"'), False if disabled ('="0"' or setting not found),
        None if the file cannot be read or another error occurs.
    """
    if not os.path.isfile(config_path):
        logger.warning(f"Config file not found for checking root status: {config_path}")
        return None

    setting_key = (
        f"{constants.INSTANCE_PREFIX}{instance_name}{constants.ENABLE_ROOT_KEY}"
    )

    enabled_pattern = re.compile(
        r"^" + re.escape(setting_key) + r'\s*=\s*"1"\s*$', re.IGNORECASE
    )

    setting_exists_pattern = re.compile(
        r"^" + re.escape(setting_key) + r'\s*=\s*"[^"]*"\s*$', re.IGNORECASE
    )

    setting_found = False
    try:
        with open(config_path, "r", encoding="utf-8") as file:
            for line in file:
                stripped_line = line.strip()
                if enabled_pattern.match(stripped_line):
                    logger.debug(
                        f"Root access for instance '{instance_name}' is explicitly enabled ('= \"1\"')."
                    )
                    return True
                if setting_exists_pattern.match(stripped_line):

                    setting_found = True

                    logger.debug(
                        f"Found root access setting for '{instance_name}', but value is not '1'."
                    )
                    break

        if setting_found:
            logger.debug(
                f"Root access for instance '{instance_name}' is disabled (setting found but not '= \"1\"')."
            )
            return False
        else:

            logger.debug(
                f"Root access setting key '{setting_key}' not found in {config_path}."
            )
            return False

    except Exception:
        logger.exception(
            f"Error reading config file {config_path} while checking root for {instance_name}."
        )
        return None
