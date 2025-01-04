import os
import glob  # Import the glob module

def modify_instance_files(instance_path, file_names, new_type):
    """Modifies the type of specified files within an instance's .bstk files.

    Directly replaces "Readonly" and "Normal" strings to toggle R/W status.

    Args:
        instance_path: The path to the instance directory (e.g., ...\Engine\Rvc64).
        file_names: A list of file names to modify (e.g., ["fastboot.vdi", "Root.vhd"]).
        new_type: The new type to set (e.g., "Normal" or "Readonly").
    """
    bstk_files = ["Android.bstk.in"]

    # Find the instance-specific .bstk file
    instance_bstk_files = glob.glob(os.path.join(instance_path, "*.bstk"))
    if instance_bstk_files:
        bstk_files.append(os.path.basename(instance_bstk_files[0]))
    else:
        print(f"Error: No instance-specific .bstk file found in {instance_path}")
        return

    for bstk_file_name in bstk_files:
        bstk_file_path = os.path.join(instance_path, bstk_file_name)

        try:
            with open(bstk_file_path, "r") as file:
                content = file.readlines()

            modified = False
            with open(bstk_file_path, "w") as file:
                for line in content:
                    # Check if any of the file_names are in the current line
                    if any(file_name in line for file_name in file_names):
                        # Replace "Readonly" or "Normal" with the new_type
                        if "Readonly" in line:
                            line = line.replace("Readonly", new_type)
                            modified = True
                        elif "Normal" in line:
                            line = line.replace("Normal", new_type)
                            modified = True
                    file.write(line)

            if modified:
                print(f"Modified file: {bstk_file_path}")
            else:
                print(f"No changes made to file: {bstk_file_path}")

        except FileNotFoundError:
            print(f"Error: Instance file not found at {bstk_file_path}")
        except Exception as e:
            print(f"Error modifying instance file: {e}")
            
def is_instance_readonly(instance_path):
    """Checks if the instance files are set to Readonly.

    Args:
        instance_path: The path to the instance directory.

    Returns:
        True if any line in the instance files contains "Readonly", False otherwise.
    """
    for bstk_file_name in ["Android.bstk.in", f"{os.path.basename(instance_path)}.bstk"]:
        bstk_file_path = os.path.join(instance_path, bstk_file_name)

        try:
            with open(bstk_file_path, "r") as file:
                for line in file:
                    if "Readonly" in line:
                        return True  # Found "Readonly" in a line
            return False  # Did not find "Readonly" in any line
        except FileNotFoundError:
            print(f"Error: Instance file not found at {bstk_file_path}")
            return False
        except Exception as e:
            print(f"Error reading instance file: {e}")
            return False