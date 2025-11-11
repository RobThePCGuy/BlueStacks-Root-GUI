# BlueStacks Root GUI

[![GitHub Repo Stars](https://img.shields.io/github/stars/RobThePCGuy/BlueStacks-Root-GUI?style=social)](https://github.com/RobThePCGuy/BlueStacks-Root-GUI)
[![YouTube Video Views](https://img.shields.io/youtube/views/zpihBs3FtEc?style=social)](https://youtu.be/zpihBs3FtEc)
[![Last Updated](https://img.shields.io/github/last-commit/RobThePCGuy/BlueStacks-Root-GUI)](https://github.com/RobThePCGuy/BlueStacks-Root-GUI/commits/main)

---

![GUI Screenshot](https://github.com/user-attachments/assets/10f965eb-e1cc-4d61-9b6f-0cbb484a4ef0)

A utility designed to easily toggle root access and enable read/write (R/W) permissions for BlueStacks 5 instances. Provides a graphical interface for the process described in **[Root BlueStacks with Kitsune Mask](https://github.com/RobThePCGuy/Root-Bluestacks-with-Kitsune-Mask/)**.

> [!WARNING]
> **BlueStacks 5.22+ users:** See [Version Compatibility](#version-compatibility) for known issues with recent updates.

---

## Table of Contents

- [Features](#features)
- [Prerequisites](#prerequisites)
- [Installation](#installation)
- [Usage Guide](#usage-guide)
- [Troubleshooting](#troubleshooting)
- [Development](#development)
- [Contributing](#contributing)

---

## Features

- **Auto-Detection** - Discovers BlueStacks installation paths via Windows Registry
- **Instance Listing** - Reads `bluestacks.conf` to display all configured instances
- **Root Toggle** - Modifies `bst.instance.<name>.enable_root_access` and `bst.feature.rooting`
- **Read/Write Toggle** - Changes disk file attributes (`fastboot.vdi`, `Root.vhd`) between `Normal` and `Readonly`
- **Process Handling** - Detects and gracefully terminates BlueStacks processes before applying changes
- **Status Display** - Shows current Root and R/W status for each instance
- **Responsive UI** - Uses background threads (`QThread`) to keep the interface responsive
- **Internationalization** - Includes English and Japanese translations

## Prerequisites

- **Operating System:** Windows 10 or later
- **BlueStacks Version:** BlueStacks 5 or MSI App Player (5.21 or earlier recommended)
- **Administrator Rights:** Required for registry access and process termination
- **Python (development only):** Python 3.7+

## Installation

### Option 1: Download Executable (Recommended)

1. Download the latest `.exe` from **[Releases](https://github.com/RobThePCGuy/BlueStacks-Root-GUI/releases)**
2. Right-click the executable and select **"Run as administrator"**

**Before first use:**
- Uninstall previous BlueStacks versions using the official **[BlueStacks Cleaner tool](https://support.bluestacks.com/hc/en-us/articles/360057724751-How-to-uninstall-BlueStacks-5-BlueStacks-X-and-BlueStacks-Services-completely-from-your-PC)**
- Install **BlueStacks 5.21 or earlier** (see [Version Compatibility](#version-compatibility))

### Option 2: Run from Source

```bash
git clone https://github.com/RobThePCGuy/BlueStacks-Root-GUI.git
cd BlueStacks-Root-GUI
python -m venv venv
.\venv\Scripts\activate
pip install -r requirements.txt
python main.py
```

**Note:** Run your terminal as administrator.

### Building the Executable

```bash
pip install pyinstaller
pyinstaller --onefile --windowed --icon="favicon.ico" --add-data "favicon.ico;." --name BlueStacksRootGUI main.py
```

Output will be in the `dist/` folder.

## Usage Guide

### Initial Setup

1. Launch the GUI **as administrator**
2. The app will auto-detect your BlueStacks installation and list available instances
3. Select the instance(s) you want to modify

### Installing Kitsune Mask

1. **Enable Root & R/W**
   - Select your target instance
   - Click **"Toggle Root"** (turn ON)
   - Click **"Toggle R/W"** (turn ON)

2. **Install Kitsune Mask**
   - Download **[Kitsune Mask APK](https://github.com/1q23lyc45/KitsuneMagisk/releases)**
   - Launch the instance via BlueStacks Multi-Instance Manager
   - Install the APK (drag-and-drop)
   - Open Kitsune Mask app

3. **Direct Install to System**
   - Tap **Install** -> **Next**
   - Select **"Direct Install to /system"**
   - If this option is missing, close and reopen the Kitsune Mask app
   - Let installation complete and reboot when prompted

4. **Final Configuration**
   - Return to BlueStacks Root GUI
   - Click **"Toggle Root"** to turn it OFF
   - **Leave "Toggle R/W" ON**

5. **Verify**
   - Launch instance and open Kitsune Mask
   - Should show as installed and active

## Troubleshooting

### Version Compatibility

| BlueStacks Version | Root Working? | Notes |
|-------------------|---------------|-------|
| 5.20.x | Yes | Fully compatible |
| 5.21.x | Yes | Last confirmed working version |
| 5.22.0.1102+ | No | Play Integrity enforcement blocks root |

**Issue:** BlueStacks 5.22+ (October 2025) shows *"Android system doesn't meet security"* popup when root/R/W is enabled.

**Cause:** Google replaced SafetyNet with Play Integrity API in January 2025. BlueStacks 5.22 now enforces integrity checks that detect system modifications.

**Solution:** Downgrade to BlueStacks 5.21

<details>
<summary><b>How to Downgrade to 5.21</b></summary>

1. **Backup your data** - Export important app data/saves

2. **Complete uninstall**
   - Download **[BSTCleaner](https://support.bluestacks.com/hc/en-us/articles/360057724751)**
   - Run to remove all BlueStacks files

3. **Install BlueStacks 5.21**
   - Download from **[Uptodown Archive](https://bluestacks-app-player.en.uptodown.com/windows/versions)**
   - Look for version **5.21.x.xxxx** (January 2025)

4. **Disable auto-updates**
   - Edit `C:\ProgramData\BlueStacks_nxt\bluestacks.conf`
   - Add or modify: `bst.auto_update="0"`

5. **Apply rooting guide** - Follow normal steps above

</details>

**Tracking:** See [Issue #11](https://github.com/RobThePCGuy/Root-Bluestacks-with-Kitsune-Mask/issues/11) for updates.

### Common Issues

**No instances listed / "Path Not Found"**
- Run GUI as **Administrator**
- Verify registry keys exist: `HKLM\SOFTWARE\BlueStacks_nxt` or `HKLM\SOFTWARE\BlueStacks_msi5`
- Perform clean reinstall using official cleaner tool

**Permission errors during toggle**
- Must run as Administrator

**R/W toggle doesn't persist**
- Ensure BlueStacks processes were fully terminated
- Manually kill processes via Task Manager if needed
- Keep R/W **ON** after installing Kitsune Mask

**"Direct Install to /system" option missing**
- Verify both **Root** and **R/W** are ON before launching instance
- Close and reopen Kitsune Mask app within BlueStacks

**Toggle operation errors**
- Check status bar in GUI for error messages
- Review console logs if running from source

## Development

### Project Structure

- `main.py` - PyQt5 GUI, application logic, threading
- `config_handler.py` - Reads/writes `bluestacks.conf`
- `instance_handler.py` - Modifies `.bstk` files, handles processes
- `registry_handler.py` - Reads BlueStacks paths from Windows Registry
- `constants.py` - Shared constants (keys, filenames, modes)

### Dependencies

See `requirements.txt`. Key dependencies:
- PyQt5
- pywin32
- psutil

## Contributing

Contributions are welcome! Please:

- Maintain existing code style and structure
- Use the `logging` module for debugging output
- Add/update docstrings for new or modified code
- Use background threads for blocking operations to keep UI responsive
- Update `constants.py` for new configurable values
- Submit pull requests with clear descriptions
- Open an issue to discuss significant changes before implementing

---

**Related Project:** [Root BlueStacks with Kitsune Mask](https://github.com/RobThePCGuy/Root-Bluestacks-with-Kitsune-Mask/)
