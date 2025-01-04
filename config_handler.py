def modify_config_file(config_path, setting, new_value):
    """Modifies a setting in the BlueStacks configuration file.

    Args:
        config_path: The full path to the bluestacks.conf file.
        setting: The name of the setting to modify (e.g., "bst.feature.rooting").
        new_value: The new value for the setting (e.g., "1" or "0").
    """
    try:
        with open(config_path, "r") as f:
            lines = f.readlines()

        with open(config_path, "w") as f:
            for line in lines:
                if line.startswith(setting + "="):
                    f.write(f"{setting}=\"{new_value}\"\n")
                else:
                    f.write(line)
    except FileNotFoundError:
        print(f"Error: Configuration file not found at {config_path}")
    except Exception as e:
        print(f"Error modifying configuration file: {e}")

def is_root_enabled(config_path, instance_name):
    """Checks if root access is enabled for a specific instance in the configuration file."""
    try:
        with open(config_path, "r") as f:
            for line in f:
                if line.startswith(f"bst.instance.{instance_name}.enable_root_access="):
                    return line.strip().endswith("=\"1\"")
        return False  # Default to False if the setting is not found
    except FileNotFoundError:
        print(f"Error: Configuration file not found at {config_path}")
        return False
    except Exception as e:
        print(f"Error reading configuration file: {e}")
        return False