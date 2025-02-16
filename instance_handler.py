import os
import glob
import logging
import psutil  # Import psutil for process termination

# Initialize logger for instance_handler module
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)  # Or desired level, if not set at root logger


def modify_instance_files(engine_path, instance_path, file_names, new_mode):
    """Modifies file types in .bstk files to toggle R/W status.

    Operates on Android.bstk.in in the engine_path and instance .bstk files in instance_path.

    Args:
        engine_path (str): Path to the BlueStacks Engine directory (e.g., C:\ProgramData\BlueStacks_nxt\Engine\Rvc64_4).
        instance_path (str): Path to the BlueStacks instance directory (e.g., ...\instance_0).
                                 This might be the same as engine_path for the master instance.
        file_names (list): List of file names to modify within the .bstk files (e.g., [FASTBOOT_VDI, ROOT_VHD]).
        new_mode (str): The new file type to set ("Normal" or "Readonly").
    """
    android_bstk_in_path = os.path.join(engine_path, "Android.bstk.in") # Android.bstk.in is always in engine_path
    instance_bstk_files_glob = os.path.join(instance_path, "*.bstk") # Instance .bstk files are in instance_path
    instance_bstk_files = glob.glob(instance_bstk_files_glob)

    bstk_files = []
    if os.path.exists(android_bstk_in_path):
        bstk_files.append("Android.bstk.in") # Add master Android.bstk.in if it exists
    else:
        error_msg = f"Error: Android.bstk.in not found in engine path: {engine_path}"
        logger.error(error_msg)
        print(error_msg)  # Keep print for immediate feedback
        return

    if instance_bstk_files:
        bstk_files.extend([os.path.basename(f) for f in instance_bstk_files]) # Add instance specific .bstk files

    logger.debug(f"Modifying instance files in engine path: {engine_path}, instance path: {instance_path}, BSTK files: {bstk_files}, Target files: {file_names}, New mode: {new_mode}")

    for bstk_file in bstk_files:
        if bstk_file == "Android.bstk.in":
            current_bstk_path = os.path.join(engine_path, bstk_file) # Path for master Android.bstk.in
        else:
            current_bstk_path = os.path.join(instance_path, bstk_file) # Path for instance .bstk files

        changed_entries = []

        try:
            logger.debug(f"Processing BSTK file: {current_bstk_path}")
            with open(current_bstk_path, "r") as f:
                content = f.readlines()

            updated_content = []
            file_found_in_bstk = False # Flag to track if any target file is found in current bstk
            for line in content:
                modified_line = line
                for target_file_name in file_names:
                    if target_file_name in line:
                        file_found_in_bstk = True
                        if "Readonly" in line or "Normal" in line: # Existing type found, replace
                            old_mode = "Readonly" if "Readonly" in line else "Normal"
                            modified_line = line.replace(old_mode, new_mode)
                            if old_mode != new_mode:
                                changed_entries.append((target_file_name, old_mode, new_mode))
                                logger.debug(f"Modified line for file '{target_file_name}': from '{old_mode}' to '{new_mode}' in {bstk_file}")
                        else: # No type specified, append the type
                            modified_line = line.rstrip() + f" Type=\"{new_mode}\"\n" # Append type
                            changed_entries.append((target_file_name, "None", new_mode)) # Old mode as None to indicate appended
                            logger.debug(f"Appended type '{new_mode}' for file '{target_file_name}' in {bstk_file}")
                        break # Move to next line after processing a target file

                updated_content.append(modified_line)


            if file_found_in_bstk: # Only rewrite if file was found in bstk, to avoid unnecessary writes
                with open(current_bstk_path, "w") as f:
                    f.writelines(updated_content)

            if changed_entries:
                for (file_name, old_val, new_val) in changed_entries:
                    logger.info(f"Successfully updated file type for '{file_name}' in {current_bstk_path}: from '{old_val}' to '{new_val}'")
            else:
                if file_found_in_bstk:
                    logger.info(f"Target file types already set to '{new_mode}' or no change needed in {current_bstk_path} for files: {file_names}.")
                else:
                    logger.info(f"No target files {file_names} found to modify in {current_bstk_path}.")


        except FileNotFoundError:
            error_msg = f"BSTK file not found at {current_bstk_path}"
            logger.error(error_msg)
            print(error_msg)
        except Exception as e:
            error_msg = f"Error modifying BSTK file {current_bstk_path}: {e}"
            logger.exception(error_msg)
            print(error_msg)


def is_instance_readonly(instance_path):
    """Checks if instance files are set to 'Readonly' in Android.bstk.in and instance .bstk files.

    Args:
        instance_path (str): Path to the BlueStacks instance directory (or engine directory for master).

    Returns:
        bool: True if 'Readonly' is found in any checked .bstk file, False otherwise.
    """
    engine_path = instance_path # For master instance, instance_path IS engine_path
    android_bstk_in_path = os.path.join(engine_path, "Android.bstk.in")
    instance_bstk_files_glob = os.path.join(instance_path, "*.bstk") # Instance .bstk still relative to instance_path
    instance_bstk_files = glob.glob(instance_bstk_files_glob)

    bstk_files_to_check = []
    if os.path.exists(android_bstk_in_path):
        bstk_files_to_check.append("Android.bstk.in")
    if instance_bstk_files:
        bstk_files_to_check.extend([os.path.basename(f) for f in instance_bstk_files])

    logger.debug(f"Checking readonly status for instance path: {instance_path}, Engine path: {engine_path}, BSTK files to check: {bstk_files_to_check}")

    for bstk_file in bstk_files_to_check:
        if bstk_file == "Android.bstk.in":
            current_bstk_path = os.path.join(engine_path, bstk_file)
        else:
            current_bstk_path = os.path.join(instance_path, bstk_file)

        if not os.path.exists(current_bstk_path):
            logger.warning(f"BSTK file not found at {current_bstk_path}, skipping readonly check for this file.")
            continue # Skip to next file, don't treat as error for overall readonly status

        try:
            with open(current_bstk_path, "r") as f:
                for line in f:
                    if "Readonly" in line:
                        logger.debug(f"'Readonly' found in {current_bstk_path}")
                        return True
            logger.debug(f"'Readonly' not found in {current_bstk_path}")
        except Exception as e:
            error_msg = f"Error reading BSTK file {current_bstk_path}: {e}"
            logger.exception(error_msg)
            print(error_msg) # Keep print for debugging
            return False # Consider not readonly on read error, or adjust logic
    return False  # Readonly not found in any checked files


def terminate_bluestacks():
    """Terminates BlueStacks processes."""
    processes_to_kill = ["HD-Player.exe", "BlueStacks.exe", "HD-Agent.exe", "BstkSVC.exe", "HD-Frontend.exe"] # Common BlueStacks processes
    killed_processes = []
    for proc_name in processes_to_kill:
        for proc in psutil.process_iter(['pid', 'name']):
            if proc.info['name'] == proc_name:
                try:
                    proc.terminate()
                    proc.wait(timeout=5) # Wait for termination, with timeout
                    killed_processes.append(proc_name)
                    logger.info(f"Terminated process: {proc_name} (PID: {proc.info['pid']})")
                except psutil.NoSuchProcess:
                    logger.debug(f"Process {proc_name} not found during termination attempt.")
                except psutil.TimeoutExpired:
                    logger.warning(f"Process {proc_name} did not terminate in time, may still be running.")
                except Exception as e:
                    logger.error(f"Error terminating process {proc_name}: {e}")
    if killed_processes:
        logger.info(f"Successfully terminated BlueStacks processes: {', '.join(killed_processes)}")
    else:
        logger.info("No BlueStacks processes found to terminate.")