import os
import glob

def modify_instance_files(instance_path, file_names, new_type):
    """Modifies file types in .bstk files to toggle R/W status, and logs changes in detail."""
    bstk_files = ["Android.bstk.in"]
    instance_bstk = glob.glob(os.path.join(instance_path, "*.bstk"))

    if not instance_bstk:
        print(f"Error: No .bstk file found in {instance_path}")
        return

    bstk_files.append(os.path.basename(instance_bstk[0]))

    for bstk_file in bstk_files:
        bstk_path = os.path.join(instance_path, bstk_file)
        changed_entries = []  # Store (filename, old_value, new_value)

        try:
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
                        elif "Normal" in line:
                            old_value = "Normal"
                            line = line.replace("Normal", new_type)
                            changed_entries.append((matched_file_name, old_value, new_type))
                    f.write(line)

            if changed_entries:
                for (file_name, old_val, new_val) in changed_entries:
                    print(f"Successfully updated '{file_name}' from '{old_val}' to '{new_val}' in {bstk_path}")
            else:
                print(f"No changes made in {bstk_path}")

        except FileNotFoundError:
            print(f"Error: File not found at {bstk_path}")
        except Exception as e:
            print(f"Error modifying file: {e}")

def is_instance_readonly(instance_path):
    """Checks if instance files are set to 'Readonly'."""
    for bstk_file in ["Android.bstk.in", f"{os.path.basename(instance_path)}.bstk"]:
        bstk_path = os.path.join(instance_path, bstk_file)
        try:
            with open(bstk_path, "r") as f:
                for line in f:
                    if "Readonly" in line:
                        return True
            return False
        except FileNotFoundError:
            print(f"Error: File not found at {bstk_path}")
            return False
        except Exception as e:
            print(f"Error reading file: {e}")
            return False