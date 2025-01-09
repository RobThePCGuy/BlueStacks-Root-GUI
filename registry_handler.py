import winreg

def get_bluestacks_path(key_name="DataDir"):
    """Retrieves a registry value from HKEY_LOCAL_MACHINE\SOFTWARE\BlueStacks_nxt."""
    try:
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\BlueStacks_nxt") as key:
            value, _ = winreg.QueryValueEx(key, key_name)
            return value
    except FileNotFoundError:
        return None