# instance_handler.py
import os
import glob
import logging
import psutil
from typing import List, Optional


import constants

logger = logging.getLogger(__name__)


def modify_instance_files(instance_path: str, new_mode: str) -> None:
    """
    Modifies the 'Type' attribute in .bstk files within an instance
    directory to toggle R/W status for specific virtual disk files.

    Args:
        instance_path: Path to the BlueStacks instance directory
                       (e.g., "C:\\ProgramData\\BlueStacks_nxt\\Nougat64_1").
        new_mode: The new mode string (constants.MODE_READWRITE or constants.MODE_READONLY).

    Raises:
        FileNotFoundError: If the instance path or essential .bstk files are missing.
        ValueError: If new_mode is not a valid mode constant.
        IOError: If there are problems reading or writing files.
        Exception: For other unexpected errors.
    """
    logger.info(f"Modifying R/W mode to '{new_mode}' for instance at: {instance_path}")

    if new_mode not in [constants.MODE_READONLY, constants.MODE_READWRITE]:
        raise ValueError(
            f"Invalid new_mode specified: {new_mode}. Must be '{constants.MODE_READONLY}' or '{constants.MODE_READWRITE}'."
        )

    if not os.path.isdir(instance_path):
        raise FileNotFoundError(f"Instance directory not found: {instance_path}")

    bstk_files_to_process: List[str] = []
    android_bstk_in_path = os.path.join(instance_path, constants.ANDROID_BSTK_IN_FILE)

    if os.path.exists(android_bstk_in_path):
        bstk_files_to_process.append(android_bstk_in_path)
    else:

        logger.warning(
            f"'{constants.ANDROID_BSTK_IN_FILE}' not found in {instance_path}. R/W toggle might be incomplete."
        )

    try:
        instance_bstk_files = glob.glob(
            os.path.join(instance_path, constants.BSTK_FILE_PATTERN)
        )

        instance_bstk_files = [
            f
            for f in instance_bstk_files
            if os.path.basename(f) != constants.ANDROID_BSTK_IN_FILE
        ]
        bstk_files_to_process.extend(instance_bstk_files)
    except Exception as e:
        logger.error(f"Error finding .bstk files in {instance_path}: {e}")

        raise IOError(f"Error finding .bstk files in {instance_path}") from e

    if not bstk_files_to_process:

        if not os.path.exists(android_bstk_in_path):
            raise FileNotFoundError(
                f"No .bstk files (including {constants.ANDROID_BSTK_IN_FILE}) found to modify in {instance_path}"
            )
        else:

            logger.warning(
                f"Only {constants.ANDROID_BSTK_IN_FILE} found in {instance_path}. Proceeding with modification."
            )

    logger.debug(f"Found .bstk files to process: {bstk_files_to_process}")

    type_pattern = constants.REGEX_BSTK_TYPE_PATTERN

    for bstk_file_path in bstk_files_to_process:
        logger.debug(f"Processing file: {bstk_file_path}")
        try:

            with open(bstk_file_path, "r", encoding="utf-8") as f:
                content = f.readlines()

            updated_content = []
            file_changed = False
            for line in content:
                modified_line = line

                if any(
                    target_file in line for target_file in constants.FILES_TO_MODIFY_RW
                ):

                    match = type_pattern.search(line)
                    if match:
                        old_mode = match.group(2)

                        if old_mode.lower() != new_mode.lower():

                            modified_line = type_pattern.sub(
                                r"\1" + new_mode + r"\3", line
                            )
                            logger.info(
                                f"  In '{os.path.basename(bstk_file_path)}': Changed mode from '{old_mode}' to '{new_mode}' for line containing target file."
                            )
                            file_changed = True
                        else:
                            logger.debug(
                                f"  In '{os.path.basename(bstk_file_path)}': Mode already '{new_mode}' for line containing target file. No change needed."
                            )
                    else:

                        logger.warning(
                            f"  In '{os.path.basename(bstk_file_path)}': Line contains target file but no standard 'Type=\"{constants.MODE_READONLY}|{constants.MODE_READWRITE}\"' attribute found. Line: {line.strip()}"
                        )

                updated_content.append(modified_line)

            if file_changed:
                logger.debug(f"Writing changes back to {bstk_file_path}")
                with open(bstk_file_path, "w", encoding="utf-8") as f:
                    f.writelines(updated_content)
            else:
                logger.debug(f"No changes needed for {bstk_file_path}")

        except FileNotFoundError:

            logger.error(f"File disappeared during processing: {bstk_file_path}")
            raise
        except IOError:
            logger.exception(f"I/O error processing file {bstk_file_path}")
            raise
        except Exception:
            logger.exception(f"Unexpected error processing file {bstk_file_path}")
            raise


def is_instance_readonly(instance_path: str) -> Optional[bool]:
    """
    Checks if any relevant disk file (.vdi, .vhd) is explicitly set to 'Readonly'
    in the instance's .bstk files.

    Args:
        instance_path: Path to the BlueStacks instance directory.

    Returns:
        True if any relevant file is explicitly marked 'Readonly'.
        False if relevant files are found but none are marked 'Readonly' (implies Writable/Normal).
        None if the path doesn't exist, no relevant .bstk files are found,
              or an error occurs during reading, indicating an indeterminate state.
    """
    logger.debug(f"Checking readonly status for instance at: {instance_path}")
    if not os.path.isdir(instance_path):
        logger.warning(
            f"Instance directory not found for readonly check: {instance_path}"
        )
        return None

    bstk_files_to_check: List[str] = []
    android_bstk_in_path = os.path.join(instance_path, constants.ANDROID_BSTK_IN_FILE)
    if os.path.exists(android_bstk_in_path):
        bstk_files_to_check.append(android_bstk_in_path)

    try:
        instance_bstk_files = glob.glob(
            os.path.join(instance_path, constants.BSTK_FILE_PATTERN)
        )
        instance_bstk_files = [
            f
            for f in instance_bstk_files
            if os.path.basename(f) != constants.ANDROID_BSTK_IN_FILE
        ]
        bstk_files_to_check.extend(instance_bstk_files)
    except Exception as e:
        logger.error(
            f"Error finding .bstk files in {instance_path} for readonly check: {e}"
        )
        return None

    if not bstk_files_to_check:
        logger.warning(
            f"No .bstk files found to check readonly status in {instance_path}"
        )
        return None

    logger.debug(f"Checking readonly status in files: {bstk_files_to_check}")

    readonly_pattern = constants.REGEX_BSTK_READONLY_PATTERN
    found_relevant_line = False

    for file_path in bstk_files_to_check:
        logger.debug(f"Scanning file for readonly check: {file_path}")
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                for line_num, line in enumerate(f, 1):

                    if any(
                        target_file in line
                        for target_file in constants.FILES_TO_MODIFY_RW
                    ):
                        found_relevant_line = True

                        if readonly_pattern.search(line):
                            logger.debug(
                                f"Readonly status found in {os.path.basename(file_path)} (Line {line_num}) for a target disk file."
                            )
                            return True
        except FileNotFoundError:
            logger.warning(
                f"File not found during readonly check (maybe deleted concurrently?): {file_path}. Skipping."
            )
            continue
        except Exception:
            logger.exception(f"Error reading file {file_path} during readonly check.")
            return None

    if found_relevant_line:

        logger.debug(
            f"Relevant disk file lines found in instance {instance_path}, but none were explicitly 'Type=\"{constants.MODE_READONLY}\"'. Assuming Writable."
        )
        return False
    else:

        logger.warning(
            f"No configuration lines found for target disk files ({constants.FILES_TO_MODIFY_RW}) in instance {instance_path}. Cannot determine R/W status."
        )
        return None


def is_bluestacks_running() -> bool:
    """
    Checks if any known BlueStacks processes are running.

    Returns:
        True if at least one known BlueStacks process is found, False otherwise.
    """
    logger.debug("Checking for running BlueStacks processes...")
    for proc in psutil.process_iter(["name"]):
        try:

            proc_name = proc.info["name"]
            if proc_name in constants.BLUESTACKS_PROCESS_NAMES:
                logger.info(
                    f"Detected running BlueStacks process: {proc_name} (PID: {proc.pid})"
                )
                return True
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess) as e:

            logger.debug(f"Skipping process check for PID {proc.pid}: {e}")
            continue
        except Exception as e:

            logger.exception(f"Unexpected error checking process {proc.pid}: {e}")
            continue

    logger.debug("No running BlueStacks processes found matching the known list.")
    return False


def terminate_bluestacks() -> bool:
    """
    Attempts to terminate all known BlueStacks-related processes gracefully,
    then forcefully kills any that remain after a timeout.

    Returns:
        True if termination was attempted (i.e., processes were found), False otherwise.
        Note: This does not guarantee all processes were successfully terminated (e.g., due to permissions).
    """
    terminated_any = False
    logger.info("Attempting to terminate BlueStacks processes...")
    processes_found: List[psutil.Process] = []

    for proc in psutil.process_iter(["pid", "name"]):
        try:
            proc_name = proc.info.get("name")
            if proc_name in constants.BLUESTACKS_PROCESS_NAMES:
                processes_found.append(proc)
                logger.debug(f"Found BlueStacks process: {proc_name} (PID: {proc.pid})")
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            continue
        except Exception as e:
            logger.warning(
                f"Error accessing process info during discovery: {e} (PID: {proc.pid})"
            )

    if not processes_found:
        logger.info("No running BlueStacks processes found to terminate.")
        return False

    terminated_names = []

    logger.info(f"Sending terminate signal to {len(processes_found)} processes...")
    for proc in processes_found:
        try:
            proc_name = proc.name()
            proc_pid = proc.pid
            logger.info(f"Terminating {proc_name} (PID: {proc_pid})...")
            proc.terminate()
            terminated_any = True
            terminated_names.append(f"{proc_name}({proc_pid})")
        except psutil.NoSuchProcess:
            logger.warning(
                f"Process {proc.name() if 'proc' in locals() and proc.is_running() else 'unknown'} (PID: {proc.pid if 'proc' in locals() else 'unknown'}) disappeared before termination signal."
            )
        except psutil.AccessDenied:
            logger.error(
                f"Permission denied trying to terminate {proc.name()} (PID: {proc.pid}). Try running as administrator."
            )

            terminated_any = True
            terminated_names.append(f"{proc.name()}({proc.pid}) - FAILED (Permission)")
        except Exception as e:

            proc_id_str = (
                f"{proc.name()}({proc.pid})"
                if "proc" in locals() and proc.is_running()
                else f"PID {proc.pid if 'proc' in locals() else 'unknown'}"
            )
            logger.exception(f"Error sending terminate signal to {proc_id_str}: {e}")
            terminated_any = True
            terminated_names.append(f"{proc_id_str} - FAILED (Error)")

    if terminated_any:
        logger.info(
            f"Waiting up to {constants.PROCESS_KILL_TIMEOUT_S}s for processes to exit gracefully..."
        )

        try:
            gone, alive = psutil.wait_procs(
                processes_found, timeout=constants.PROCESS_KILL_TIMEOUT_S
            )
        except Exception as e:

            logger.error(f"Error occurred during process wait: {e}")

            alive = processes_found
            gone = []

        for proc in gone:
            try:
                logger.debug(
                    f"Process {proc.name()} (PID: {proc.pid}) terminated successfully."
                )
            except psutil.NoSuchProcess:
                logger.debug(
                    f"Process (PID: {proc.pid}) terminated successfully (already gone)."
                )
            except Exception as e:
                logger.warning(
                    f"Error getting info for terminated process PID {proc.pid}: {e}"
                )

        if alive:
            logger.warning(
                f"{len(alive)} processes did not terminate gracefully. Attempting to kill..."
            )
            for proc in alive:
                try:
                    proc_name = proc.name()
                    proc_pid = proc.pid
                    logger.info(f"Force killing {proc_name} (PID: {proc_pid})...")
                    proc.kill()

                    proc.wait(timeout=constants.PROCESS_POST_KILL_WAIT_S)
                    logger.info(f"Force killed {proc_name} (PID: {proc_pid}).")
                except psutil.NoSuchProcess:

                    logger.info(
                        f"Process {proc.name() if 'proc_name' in locals() else 'unknown'} (PID: {proc.pid if 'proc_pid' in locals() else 'unknown'}) exited after kill signal or before."
                    )
                except psutil.AccessDenied:
                    logger.error(
                        f"Permission denied trying to force kill {proc.name()} (PID: {proc.pid})."
                    )
                except Exception as e:
                    proc_id_str = (
                        f"{proc.name()}({proc.pid})"
                        if "proc" in locals() and proc.is_running()
                        else f"PID {proc.pid if 'proc' in locals() else 'unknown'}"
                    )
                    logger.error(f"Error force killing {proc_id_str}: {e}")

    if terminated_names:
        logger.info(f"Termination attempted for: {', '.join(terminated_names)}")
    elif processes_found:

        logger.warning(
            "Processes were found, but none were marked for termination attempt (internal logic issue?)."
        )

    return bool(processes_found)
