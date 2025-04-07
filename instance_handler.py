import os
import glob
import logging
import psutil
import re

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

def modify_instance_files(engine_path: str, instance_path: str, file_names: list, new_mode: str) -> None:
    """
    Modifies file types in .bstk files to toggle R/W status.

    Args:
        engine_path (str): Path to the BlueStacks Engine directory.
        instance_path (str): Path to the BlueStacks instance directory.
        file_names (list): List of file names to modify (e.g., ['fastboot.vdi', 'Root.vhd']).
        new_mode (str): The new mode ("Normal" or "Readonly").
    """
    android_bstk_in = os.path.join(engine_path, "Android.bstk.in")
    instance_bstk_files = glob.glob(os.path.join(instance_path, "*.bstk"))
    bstk_files = []

    if os.path.exists(android_bstk_in):
        bstk_files.append(("Android.bstk.in", engine_path))
    else:
        error_msg = f"Android.bstk.in not found in engine path: {engine_path}"
        logger.error(error_msg)
        return

    for file_path in instance_bstk_files:
        bstk_files.append((os.path.basename(file_path), instance_path))

    logger.debug(f"Modifying files: {bstk_files} for targets: {file_names} with new mode: {new_mode}")

    for bstk_file, base_path in bstk_files:
        current_path = os.path.join(base_path, bstk_file)
        changed_entries = []

        try:
            logger.debug(f"Processing file: {current_path}")
            with open(current_path, "r") as f:
                content = f.readlines()

            updated_content = []
            file_found = False
            for line in content:
                modified_line = line
                for target in file_names:
                    if target in line:
                        file_found = True
                        # Use regex to capture mode words with flexible whitespace handling.
                        pattern = re.compile(r'(Readonly|Normal)')
                        match = pattern.search(line)
                        if match:
                            old_mode = match.group(0)
                            modified_line = pattern.sub(new_mode, line)
                            if old_mode != new_mode:
                                changed_entries.append((target, old_mode, new_mode))
                                logger.debug(f"Modified {target} from {old_mode} to {new_mode} in {bstk_file}")
                        else:
                            modified_line = line.rstrip() + f' Type="{new_mode}"\n'
                            changed_entries.append((target, "None", new_mode))
                            logger.debug(f"Appended type for {target} with mode {new_mode} in {bstk_file}")
                        break
                updated_content.append(modified_line)

            if file_found:
                with open(current_path, "w") as f:
                    f.writelines(updated_content)

            if changed_entries:
                for target, old_mode, new_mode in changed_entries:
                    logger.info(f"Updated {target} in {current_path}: from {old_mode} to {new_mode}")
            else:
                logger.info(f"No changes needed in {current_path} for target files: {file_names}")
        except FileNotFoundError:
            error_msg = f"File not found: {current_path}"
            logger.error(error_msg)
        except Exception as e:
            error_msg = f"Error modifying file {current_path}: {e}"
            logger.exception(error_msg)

def is_instance_readonly(instance_path: str) -> bool:
    """
    Checks if any .bstk file in the instance directory is set to 'Readonly'.

    Args:
        instance_path (str): Path to the BlueStacks instance directory.

    Returns:
        bool: True if any file is marked 'Readonly'; otherwise False.
    """
    engine_path = instance_path
    android_bstk_in = os.path.join(engine_path, "Android.bstk.in")
    instance_files = glob.glob(os.path.join(instance_path, "*.bstk"))
    files_to_check = []

    if os.path.exists(android_bstk_in):
        files_to_check.append(android_bstk_in)
    files_to_check.extend(instance_files)

    logger.debug(f"Checking readonly status for files: {files_to_check}")

    for file_path in files_to_check:
        if not os.path.exists(file_path):
            logger.warning(f"File not found: {file_path}. Skipping readonly check.")
            continue
        try:
            with open(file_path, "r") as f:
                for line in f:
                    if "Readonly" in line:
                        logger.debug(f"Readonly found in {file_path}")
                        return True
        except Exception as e:
            error_msg = f"Error reading file {file_path}: {e}"
            logger.exception(error_msg)
            return False
    return False

def terminate_bluestacks() -> None:
    """
    Terminates BlueStacks-related processes.
    """
    process_names = ["HD-Player.exe", "BlueStacks.exe", "HD-Agent.exe", "BstkSVC.exe", "HD-Frontend.exe"]
    terminated = []
    for proc in psutil.process_iter(['pid', 'name']):
        if proc.info['name'] in process_names:
            try:
                proc.terminate()
                proc.wait(timeout=5)
                terminated.append(proc.info['name'])
                logger.info(f"Terminated {proc.info['name']} (PID: {proc.info['pid']})")
            except psutil.NoSuchProcess:
                logger.debug(f"Process {proc.info['name']} not found.")
            except psutil.TimeoutExpired:
                logger.warning(f"Process {proc.info['name']} did not terminate in time.")
            except Exception as e:
                logger.error(f"Error terminating {proc.info['name']}: {e}")
    if terminated:
        logger.info(f"Terminated processes: {', '.join(terminated)}")
    else:
        logger.info("No BlueStacks processes found to terminate.")
