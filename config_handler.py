def modify_config_file(config_path, setting, new_value):
    """Modifies a setting in bluestacks.conf."""
    changed = False
    try:
        with open(config_path, "r") as f:
            lines = f.readlines()

        with open(config_path, "w") as f:
            for line in lines:
                if line.startswith(f"{setting}="):
                    f.write(f"{setting}=\"{new_value}\"\n")
                    changed = True
                else:
                    f.write(line)

        if changed:
            print(f"Successfully updated '{setting}' to '{new_value}' in {config_path}")
        else:
            print(f"No changes made for '{setting}' in {config_path}")
    except FileNotFoundError:
        print(f"Error: File not found at {config_path}")
    except Exception as e:
        print(f"Error modifying configuration: {e}")


def is_root_enabled(config_path, instance_name):
    """Checks if root access is enabled for a specific instance."""
    try:
        with open(config_path, "r") as f:
            for line in f:
                if line.startswith(f"bst.instance.{instance_name}.enable_root_access="):
                    return line.strip().endswith("=\"1\"")
        return False
    except FileNotFoundError:
        print(f"Error: File not found at {config_path}")
        return False
    except Exception as e:
        print(f"Error reading configuration: {e}")
        return False