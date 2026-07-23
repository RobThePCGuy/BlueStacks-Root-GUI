"""Configuration file handling utilities."""
from __future__ import annotations

import os
import logging
import re
from typing import Any


import constants
import root_persistence
import win_retry

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
        with open(config_path, encoding="utf-8") as file:
            lines = file.readlines()
    except Exception as e:
        logger.exception(f"Error reading configuration file {config_path}")
        raise OSError(f"Error reading configuration file {config_path}: {e}") from e

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
            # The persistence bypass may have set bluestacks.conf read-only to
            # stop BlueStacks reverting the root keys. Temporarily clear that
            # attribute for the write and restore it afterwards, so legitimate
            # edits keep working without losing the lock.
            with root_persistence.unlocked(config_path):
                # bluestacks.conf is BlueStacks' one shared, global config --
                # every instance's settings live in this single file. Write to
                # a temp file first and os.replace() it into place, so the
                # real path only ever resolves to the complete old file or the
                # complete new one -- never a truncated one, even if this
                # process dies mid-write. os.replace() on Windows can still
                # raise PermissionError if something else (AV, the Search
                # indexer, BlueStacks itself) briefly holds the destination
                # open, so that specific case is retried rather than failed
                # outright.
                tmp_path = config_path + ".tmp"
                try:
                    with open(tmp_path, "w", encoding="utf-8") as file:
                        file.writelines(updated_lines)
                    win_retry.retry_on_sharing_violation(
                        lambda: os.replace(tmp_path, config_path),
                        label="bluestacks.conf write")
                finally:
                    if os.path.isfile(tmp_path):
                        os.unlink(tmp_path)
            logger.debug(f"Successfully wrote changes to {config_path}")
        except Exception as e:
            logger.exception(f"Error writing updated configuration file {config_path}")
            raise OSError(
                f"Error writing updated configuration file {config_path}: {e}"
            ) from e

    return changed


def get_complete_root_statuses(config_path: str) -> dict[str, Any]:
    """
    Reads a config file and returns all instance root statuses AND the global rooting feature status.

    Args:
        config_path: Path to the bluestacks.conf file.

    Returns:
        A dictionary like:
        {'global_status': bool, 'instance_statuses': {name: bool}, 'display_names': {name: str}}
    """
    instance_statuses: dict[str, bool] = {}
    display_names: dict[str, str] = {}
    global_status: bool = False
    empty_result = {"global_status": False, "instance_statuses": {}, "display_names": {}}

    if not os.path.isfile(config_path):
        logger.warning(
            f"Config file not found for reading root statuses: {config_path}"
        )
        return empty_result

    # FIX: Regex for both instance-specific and global root keys
    instance_pattern = re.compile(
        r"^"
        + re.escape(constants.INSTANCE_PREFIX)
        + r"([^.]+)"
        + re.escape(constants.ENABLE_ROOT_KEY)
        + r'\s*=\s*"([^"]*)"',
        re.IGNORECASE,
    )
    display_name_pattern = re.compile(
        r"^"
        + re.escape(constants.INSTANCE_PREFIX)
        + r"([^.]+)"
        + re.escape(constants.DISPLAY_NAME_KEY)
        + r'\s*=\s*"([^"]*)"',
        re.IGNORECASE,
    )
    global_pattern = re.compile(
        r"^" + re.escape(constants.FEATURE_ROOTING_KEY) + r'\s*=\s*"1"', re.IGNORECASE
    )

    try:
        with open(config_path, encoding="utf-8") as file:
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

                # Check for instance display-name key
                name_match = display_name_pattern.match(stripped_line)
                if name_match:
                    instance_name, value = name_match.group(1), name_match.group(2)
                    display_names[instance_name] = value
    except Exception:
        logger.exception(f"Error reading config file {config_path} for root statuses.")
        return empty_result

    return {
        "global_status": global_status,
        "instance_statuses": instance_statuses,
        "display_names": display_names,
    }
