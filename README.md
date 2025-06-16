# BlueStacks Root GUI

[![GitHub Repo Stars](https://img.shields.io/github/stars/RobThePCGuy/BlueStacks-Root-GUI?style=social)](https://github.com/RobThePCGuy/BlueStacks-Root-GUI) [![YouTube Video Views](https://img.shields.io/youtube/views/zpihBs3FtEc?style=social)](https://youtu.be/zpihBs3FtEc) [![Last Updated](https://img.shields.io/github/last-commit/RobThePCGuy/BlueStacks-Root-GUI)](https://github.com/RobThePCGuy/BlueStacks-Root-GUI/commits/main)

---

![GUI Screenshot](https://github.com/user-attachments/assets/10f965eb-e1cc-4d61-9b6f-0cbb484a4ef0)

BlueStacks Root GUI is a utility designed to easily toggle root access settings and enable read/write (R/W) permissions for your BlueStacks 5 instances (specifically targeting the `BlueStacks_nxt` structure and the MSI App Player's `BlueStacks_msi5`). It aims to simplify the process described in the original guide: **[Root BlueStacks with Kitsune Mask](https://github.com/RobThePCGuy/Root-Bluestacks-with-Kitsune-Mask/)** by providing a graphical interface.

---

## Table of Contents

- [Features](#features)
- [Prerequisites](#prerequisites)
- [Installation & Download](#installation--download)
- [Usage Guide](#usage-guide)
- [Troubleshooting](#troubleshooting)
- [Development](#development)
- [Contributing](#contributing)
- [Changelog](#changelog)
- [License](#license)

---

## Features

- **Auto-Detection:** Discovers BlueStacks installation paths via the Windows Registry (`SOFTWARE\BlueStacks_nxt` or `SOFTWARE\BlueStacks_msi5`).
- **Instance Listing:** Reads `bluestacks.conf` to find and list configured instances.
- **Root Toggle:** Modifies `bst.instance.<name>.enable_root_access` and `bst.feature.rooting` in `bluestacks.conf`.
- **Read/Write Toggle:** Modifies the `Type` attribute (`Normal` vs `Readonly`) for key disk files (`fastboot.vdi`, `Root.vhd`) within instance-specific `.bstk` files.
- **Process Handling:** Detects running BlueStacks processes and attempts graceful termination before applying changes.
- **Status Display:** Shows the current Root and R/W status for each detected instance.
- **Responsive UI:** Uses background threads (`QThread`) for potentially long operations (file I/O, process termination) to keep the GUI responsive.
- **Basic Internationalization:** Includes English and Japanese translations.

## Prerequisites

- **Operating System:** Windows 10 or later (due to registry keys and file paths used).
- **BlueStacks Version:** BlueStacks 5 or MSI App Player (versions using the `BlueStacks_nxt` or `BlueStacks_msi5` registry keys and configuration structure). *Compatibility with other versions is not guaranteed.*
- **Python (for development):** Python 3.7+
- **Administrator Rights:** **Required** to read the HKLM registry and terminate BlueStacks processes effectively. Run the application as an administrator.
- **Dependencies:** Listed in `requirements.txt`. Key dependencies include `PyQt5`, `pywin32`, `psutil`.

## Installation & Download

### For End Users (Executable Download)

1.  **Download the Latest Executable:** Go to the **[Releases](https://github.com/RobThePCGuy/BlueStacks-Root-GUI/releases)** page on GitHub and download the latest `.exe` file.
2.  **Run as Administrator:** Right-click the downloaded `.exe` and select "Run as administrator". This is necessary for registry access and process termination.
3.  **Important Pre-Run Steps:**
    *   **Clean BlueStacks Install Recommended:** If you encounter issues, fully uninstall *all* previous BlueStacks versions using the official **[BlueStacks Cleaner tool](https://support.bluestacks.com/hc/en-us/articles/360057724751-How-to-uninstall-BlueStacks-5-BlueStacks-X-and-BlueStacks-Services-completely-from-your-PC)**.
    *   **Install Latest BlueStacks 5:** Download and install the latest version from the official **[BlueStacks website](https://www.bluestacks.com/)**.

### For Developers (Building from Source)

1.  **Clone the Repository:**
    ```bash
    git clone https://github.com/RobThePCGuy/BlueStacks-Root-GUI.git
    cd BlueStacks-Root-GUI
    ```
2.  **Create a Virtual Environment (Recommended):**
    ```bash
    python -m venv venv
    .\venv\Scripts\activate
    ```
3.  **Install Dependencies:**
    ```bash
    pip install -r requirements.txt
    ```
4.  **Run the Application:**
    ```bash
    python main.py
    ```
    *(Remember to run your terminal/IDE as administrator if running directly)*
5.  **Build the Executable (Optional):**
    ```bash
    pip install pyinstaller
    pyinstaller --onefile --windowed --icon="favicon.ico" --add-data "favicon.ico;." --name BlueStacksRootGUI main.py
    ```
    The executable will be in the `dist/` folder.

## Usage Guide

1.  **Launch as Administrator:** Start the GUI (`.exe` or `python main.py`) with administrator privileges.
2.  **Instance Detection:** The GUI will attempt to find your BlueStacks installation and list the instances found in `bluestacks.conf`. Statuses (Root, R/W) will be displayed.
3.  **Select Instances:** Check the box(es) next to the instance(s) you want to modify.
4.  **Toggle Root:**
    *   Click **"Toggle Root"**. This enables the necessary settings in `bluestacks.conf`.
    *   **Turn this ON only temporarily** while you are installing Kitsune Mask.
5.  **Toggle R/W:**
    *   Click **"Toggle R/W"**. This sets the instance's disk files (`Root.vhd`, `fastboot.vdi`) to `Normal` (Read/Write) mode.
    *   **This needs to be left ON** for the system modifications (like Kitsune Mask) to persist after the instance restarts.
6.  **Install Kitsune Mask:**
    *   Ensure **Root is ON** and **R/W is ON** in the GUI for the target instance.
    *   Download the latest **[Kitsune Mask APK](https://github.com/1q23lyc45/KitsuneMagisk/releases)**.
    *   Launch the modified instance using the BlueStacks Multi-Instance Manager.
    *   Install the downloaded Kitsune Mask APK onto the instance (drag-and-drop usually works).
    *   Open the Kitsune Mask app inside the instance.
    *   Tap **Install**.
    *   Tap **Next**.
    *   Select the option **"Direct Install to /system"**.
        *   *Troubleshooting:* If the "Direct Install" option is missing, fully close and reopen the Kitsune Mask app *inside* BlueStacks. It should then appear.
    *   Let the installation complete and reboot when prompted (the instance will restart).
7.  **Final GUI Step:**
    *   **Crucially:** Once Kitsune Mask is successfully installed to `/system`, return to the BlueStacks Root GUI.
    *   Select the instance again.
    *   Click **"Toggle Root"** to turn the configuration setting **OFF**.
    *   **Leave "Toggle R/W" ON.**
8.  **Verify:** Launch the instance. Open Kitsune Mask; it should show as installed and active. Root applications should now work.
9.  **Close:** Close the BlueStacks Root GUI.

## Troubleshooting

-   **"Path Not Found" / No Instances Listed:**
    *   Ensure you ran the GUI as **administrator**.
     *   Verify BlueStacks 5 or MSI App Player is installed correctly and the registry keys (`HKLM\SOFTWARE\BlueStacks_nxt\UserDefinedDir` and `DataDir` or `HKLM\SOFTWARE\BlueStacks_msi5`) exist.
    *   A clean reinstall of BlueStacks using the official cleaner tool might be necessary.
-   **Permission Errors during Toggle:**
    *   You *must* run the GUI as administrator.
-   **R/W Toggle Doesn't Stick:**
    *   Ensure BlueStacks processes (`HD-Player.exe`, `HD-Agent.exe`, etc.) were fully terminated before toggling. The GUI attempts this, but manual termination via Task Manager might be needed if issues persist.
    *   Ensure you are leaving the **R/W** setting **ON** in the GUI after installing Kitsune Mask.
-   **"Direct Install to /system" Missing in Kitsune Mask:**
    *   Make sure **Root** and **R/W** were both **ON** in the GUI *before* launching the instance and attempting installation.
    *   Try closing and reopening the Kitsune Mask app within the BlueStacks instance.
-   **Errors during Toggle Operations:** Check the status bar in the GUI and the application logs (if run from source/console) for specific error messages.

## Development

Follow the steps in [Installation & Download > For Developers](#for-developers-building-from-source).

Key modules:
- `main.py`: PyQt5 GUI, application logic, threading.
- `config_handler.py`: Reads/writes `bluestacks.conf`.
- `instance_handler.py`: Modifies `.bstk` files, handles processes.
- `registry_handler.py`: Reads BlueStacks paths from Windows Registry.
- `constants.py`: Shared constant values (keys, filenames, modes, etc.).

## Contributing

Contributions are welcome! Please follow these guidelines:

-   Maintain code style and structure.
-   Use the `logging` module appropriately.
-   Add/update docstrings for new/modified code.
-   Ensure UI remains responsive (use background threads for blocking tasks).
-   Update `constants.py` if adding new configurable values.
-   Submit pull requests with clear descriptions of changes.
-   Open an issue to discuss significant changes beforehand.

## Changelog 

> v2.1 vs v2

### Major Changes

*   **Code Modularization:** The entire application has been restructured from a single `main.py` file into multiple focused modules:
    *   `main.py`: Handles the GUI (PyQt5), application logic, and threading.
    *   `config_handler.py`: Dedicated to reading and writing `bluestacks.conf`.
    *   `instance_handler.py`: Manages instance file (`.bstk`) modifications and BlueStacks process handling.
    *   `registry_handler.py`: Specifically handles reading BlueStacks paths from the Windows Registry.
    *   `constants.py`: Centralizes all constants (file names, keys, modes, etc.) for easier maintenance and consistency.
*   **Improved Error Handling & Reporting:**
    *   More specific exceptions are caught and raised throughout the helper modules (`FileNotFoundError`, `IOError`, `ValueError`, etc.).
    *   Worker threads now emit more granular error messages and status updates to the main UI, distinguishing between critical failures and per-instance issues.
    *   Functions now often return `Optional[...]` types (like `Optional[bool]`) to better represent indeterminate states (e.g., when a file is missing or unreadable).

### Improvements

*   **Configuration Handling (`config_handler.py`):**
    *   Uses regular expressions for more reliable parsing of `bluestacks.conf` settings.
    *   `modify_config_file` now correctly handles appending new settings if they don't exist and avoids writing the file if no changes are actually made.
    *   `get_all_instance_root_statuses` provides an efficient way to read all instance statuses at once.
*   **Instance File Handling (`instance_handler.py`):**
    *   `modify_instance_files` uses more robust regex (`REGEX_BSTK_TYPE_PATTERN`) to find and replace the `Type` attribute in `.bstk` files, handling different whitespace and casing.
    *   `is_instance_readonly` now checks specifically for the `Readonly` type associated with target disk files and returns `None` if the status cannot be determined (e.g., file missing, read error), preventing incorrect assumptions.
*   **Process Management (`instance_handler.py`):**
    *   `terminate_bluestacks` implements a more robust termination sequence: attempts graceful `terminate()`, waits (`PROCESS_KILL_TIMEOUT_S`), and then forcefully `kill()` any remaining processes.
    *   Uses a more comprehensive list of `BLUESTACKS_PROCESS_NAMES` from `constants.py`.
    *   `is_bluestacks_running` uses `psutil` for efficient process checking.
*   **Registry Access (`registry_handler.py`):**
    *   More specific error handling for `FileNotFoundError` and `PermissionError` during registry access.
    *   Checks the registry value type (`REG_SZ`) to ensure a string path is returned.
*   **GUI & User Experience (`main.py`):**
    *   Instance list now uses `QGridLayout` for potentially better column alignment.
    *   Path label now displays both the `UserDefinedDir` and `DataDir` paths found.
    *   Language selection ComboBox moved to the top-left for better visibility.
    *   Added tooltips to the "Toggle Root" and "Toggle R/W" buttons explaining their function.
    *   Added a specific, clearer "Kitsune Mask Install Reminder" popup message with updated instructions.
    *   Worker thread emits detailed status messages (`operation_message` signal) during operations (e.g., "Toggling Root for Nougat64...").
    *   Improved cleanup logic for the background thread (`QThread`).
    *   Added Windows AppUserModelID setting for better taskbar integration (pinning, icon grouping).
    *   Icon handling is more robust, checking for file existence.
*   **Logging:**
    *   Standardized logging setup using `logging.basicConfig`.
    *   Modules use `logger = logging.getLogger(__name__)` for better log organization.
    *   Increased logging detail, especially at the DEBUG level.

### Fixes

*   **Potential State Inconsistencies:** Improved logic for reading R/W status (`is_instance_readonly`) reduces the chance of misrepresenting the state if files are unreadable or missing attributes.
*   **Configuration File Writing:** `modify_config_file` now avoids unnecessary file writes if the value is already correct.
*   **Instance File Modification:** More reliable identification and modification of the `Type` attribute in `.bstk` files due to regex usage.

### Code Quality & Refactoring

*   Massive refactoring into separate modules improves readability and maintainability.
*   Introduction of `constants.py` eliminates magic strings and numbers.
*   Increased use of type hinting (`typing` module) enhances code clarity and allows for static analysis.
*   Removed unused dependencies (`lxml`, `pillow`, `python-docx`) from `requirements.txt`.
*   Improved docstrings across functions and classes.

## License

This project is licensed under the MIT License. See the [LICENSE](LICENSE) file (if included, standard MIT otherwise) for details.
