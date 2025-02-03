import os
import glob
import logging

# Initialize logger for instance_handler module
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO) # Or desired level, if not set at root logger


def modify_instance_files(instance_path, file_names, new_type):
    """Modifies file types in .bstk files to toggle R/W status, and logs changes in detail.

    Args:
        instance_path (str): Path to the BlueStacks instance directory.
        file_names (list): List of file names to modify within the .bstk files.
        new_type (str): The new file type to set ("Normal" or "Readonly").
    """
    bstk_files = ["Android.bstk.in"]
    instance_bstk_files = glob.glob(os.path.join(instance_path, "*.bstk"))

    if not instance_bstk_files:
        error_msg = f"Error: No .bstk file found in instance path: {instance_path}"
        logger.error(error_msg)
        print(error_msg)
        return

    bstk_files.append(os.path.basename(instance_bstk_files[0])) # Take the first one found

    logger.debug(f"Modifying instance files in path: {instance_path}, BSTK files: {bstk_files}, Target files: {file_names}, New type: {new_type}")

    for bstk_file in bstk_files:
        bstk_path = os.path.join(instance_path, bstk_file)
        changed_entries = []  # Store (filename, old_value, new_value)

        try:
            logger.debug(f"Processing BSTK file: {bstk_path}")
            with open(bstk_path, "r") as f:
                content = f.readlines()

            with open(bstk_path, "w") as f:
                for line in content:
                    # Check if any target file_name is mentioned in this line
                    matched_file_name = next((fn for fn in file_names if fn in line), None)
                    if matched_file_name:
                        if "Readonly" in line:
                            old_value = "Readonly"
                            line = line.replace("Readonly", new_type)
                            changed_entries.append((matched_file_name, old_value, new_type))
                            logger.debug(f"Modified line for file '{matched_file_name}': from 'Readonly' to '{new_type}'")
                        elif "Normal" in line:
                            old_value = "Normal"
                            line = line.replace("Normal", new_type)
                            changed_entries.append((matched_file_name, old_value, new_type))
                            logger.debug(f"Modified line for file '{matched_file_name}': from 'Normal' to '{new_type}'")
                    f.write(line)

            if changed_entries:
                for (file_name, old_val, new_val) in changed_entries:
                    logger.info(f"Successfully updated file type for '{file_name}' in {bstk_path}: from '{old_val}' to '{new_val}'")
            else:
                logger.info(f"No target file types ('Readonly' or 'Normal' with filenames {file_names}) found to modify in {bstk_path}.")

        except FileNotFoundError:
            error_msg = f"BSTK file not found at {bstk_path}"
            logger.error(error_msg)
            print(error_msg)
        except Exception as e:
            error_msg = f"Error modifying BSTK file {bstk_path}: {e}"
            logger.exception(error_msg)
            print(error_msg)


def is_instance_readonly(instance_path):
    """Checks if instance files are set to 'Readonly'.

    Args:
        instance_path (str): Path to the BlueStacks instance directory.

    Returns:
        bool: True if 'Readonly' is found in any checked .bstk file, False otherwise.
    """
    bstk_files_to_check = ["Android.bstk.in"] # Define filenames to check directly
    instance_bstk_files = glob.glob(os.path.join(instance_path, "*.bstk"))
    if instance_bstk_files: # Only add if found, avoid index error if glob returns empty list
        bstk_files_to_check.append(os.path.basename(instance_bstk_files[0]))

    logger.debug(f"Checking readonly status for instance path: {instance_path}, BSTK files to check: {bstk_files_to_check}")

    for bstk_file in bstk_files_to_check:
        bstk_path = os.path.join(instance_path, bstk_file)
        try:
            with open(bstk_path, "r") as f:
                for line in f:
                    if "Readonly" in line:
                        logger.debug(f"'Readonly' found in {bstk_path}")
                        return True
            logger.debug(f"'Readonly' not found in {bstk_path}") # Log even when not found to confirm check
        except FileNotFoundError:
            error_msg = f"BSTK file not found at {bstk_path}"
            logger.error(error_msg)
            print(error_msg)
            return False # If one file not found, consider it not readonly for safety (or adjust logic)
        except Exception as e:
            error_msg = f"Error reading BSTK file {bstk_path}: {e}"
            logger.exception(error_msg)
            print(error_msg)
            return False
    return False # Readonly not found in any checked files