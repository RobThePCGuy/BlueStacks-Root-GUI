import winreg

def get_bluestacks_path(key_name="DataDir"):
    """Retrieves the value of a registry key under HKEY_LOCAL_MACHINE\SOFTWARE\BlueStacks_nxt\.

    Args:
        key_name: The name of the registry key to retrieve.

    Returns:
        The value of the registry key (e.g., the installation path) or None if not found.
    """
    try:
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\BlueStacks_nxt") as key:
            value, _ = winreg.QueryValueEx(key, key_name)
            return value
    except FileNotFoundError:
        return None