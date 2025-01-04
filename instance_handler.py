from docx import Document
import os

def modify_instance_files(instance_path, file_names, new_type):
    """Modifies the type of specified files within an instance's .bstk files.

    Args:
        instance_path: The path to the instance directory (e.g., ...\Engine\Rvc64).
        file_names: A list of file names to modify (e.g., ["fastboot.vdi", "Root.vhd"]).
        new_type: The new type to set (e.g., "Normal" or "Readonly").
    """
    for bstk_file_name in ["Android.bstk.in", f"{os.path.basename(instance_path)}.bstk"]:
        bstk_file_path = os.path.join(instance_path, bstk_file_name)

        try:
            with open(bstk_file_path, "r") as file:
                content = file.readlines()

            modified = False
            with open(bstk_file_path, "w") as file:
                for line in content:
                    for file_name in file_names:
                        if file_name in line:
                            line = line.replace("Readonly", new_type).replace("Normal", new_type)
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
        True if the instance files are in Readonly mode, False otherwise.
    """
    for bstk_file_name in ["Android.bstk.in", f"{os.path.basename(instance_path)}.bstk"]:
        bstk_file_path = os.path.join(instance_path, bstk_file_name)

        try:
            with open(bstk_file_path, "r") as file:
                for line in file:
                    if "Readonly" in line:
                        return True
            return False
        except FileNotFoundError:
            print(f"Error: Instance file not found at {bstk_file_path}")
            return False
        except Exception as e:
            print(f"Error reading instance file: {e}")
            return False
