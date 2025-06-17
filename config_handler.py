"""Configuration file handling utilities."""
import os
import logging
import re
from typing import Dict, Any, Optional


import constants

logger = logging.getLogger(__name__)


def modify_config_file(config_path: str, setting: str, new_value: str) -> bool:
    """
    Modifies a specific setting in the bluestacks.conf file.
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

    return changed


def get_complete_root_statuses(config_path: str) -> Dict[str, Any]:
    """
    Reads a config file and returns all instance root statuses AND the global rooting feature status.

    Args:
        config_path: Path to the bluestacks.conf file.

    Returns:
        A dictionary like: {'global_status': bool, 'instance_statuses': {name: bool}}
    """
    instance_statuses: Dict[str, bool] = {}
    global_status: bool = False

    if not os.path.isfile(config_path):
        logger.warning(
            f"Config file not found for reading root statuses: {config_path}"
        )
        return {"global_status": False, "instance_statuses": {}}

    # FIX: Regex for both instance-specific and global root keys
    instance_pattern = re.compile(
        r"^"
        + re.escape(constants.INSTANCE_PREFIX)
        + r"([^.]+)"
        + re.escape(constants.ENABLE_ROOT_KEY)
        + r'\s*=\s*"([^"]*)"',
        re.IGNORECASE,
    )
    global_pattern = re.compile(
        r"^" + re.escape(constants.FEATURE_ROOTING_KEY) + r'\s*=\s*"1"', re.IGNORECASE
    )

    try:
        with open(config_path, "r", encoding="utf-8") as file:
            for line in file:
                stripped_line = line.strip()
                
                # Check for global key
                if global_pattern.match(stripped_line):
                    global_status = True
                    logger.debug(f"Found global root status in {config_path}: Enabled")
                
                # Check for instance key
                match = instance_pattern.match(stripped_line)
                if match:
                    instance_name, value = match.group(1), match.group(2)
                    is_enabled = value == "1"
                    instance_statuses[instance_name] = is_enabled
    except Exception:
        logger.exception(f"Error reading config file {config_path} for root statuses.")
        return {"global_status": False, "instance_statuses": {}}

    return {"global_status": global_status, "instance_statuses": instance_statuses}