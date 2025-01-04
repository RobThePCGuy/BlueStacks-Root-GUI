# BlueStacks Root GUI

This is an AIO application designed to simplify the configuration part of my original tutorial on how to [root BlueStacks](https://github.com/RobThePCGuy/Root-Bluestacks-with-Kitsune-Mask/) with Kitsune Mask. If you want to do things manually, then the original repo is where you go. This tool will allow you to toggle root access and read/write (R/W) modes for BlueStacks instances. It provides an intuitive interface for managing these settings without manually editing configuration files.

## Features

- Reads Windows Registry to auto-detect the right directories and lists them individually for you to pick.
- Toggles root access (`Root: On/Off`) for individual instances.
- Toggles file system read/write access (`R/W: On/Off`) for individual instances.
- Updates the current status of root and R/W modes dynamically in the GUI.

## Installation

1. **Download the Executable**:
   - Download the latest `.exe` file from the [Releases](https://github.com/RobThePCGuy/BlueStacks-Root-GUI/releases) section.

2. **Run the App**:
   - Double-click the `.exe` file to open the GUI.
   - No installation is required.

3. **Requirements**:
   - Ensure BlueStacks is installed on your system.
   - The app detects BlueStacks configuration and instance files automatically.

---

## Usage Instructions

1. Open the app by running the `.exe` file.
2. The app will automatically detect available BlueStacks instances and display them in the GUI.
3. Select an instance by checking its corresponding checkbox.
4. Use the following buttons:
   - **Toggle Root**: Toggles root access (`On`/`Off`) for the selected instance.
   - **Toggle R/W**: Toggles read/write mode (`On`/`Off`) for the selected instance.
5. Observe the status updates (`Root: On/Off` and `R/W: On/Off`) next to each instance.
6. Close the app when finished.

---

## Requirements

- **BlueStacks**: The app is designed to work with BlueStacks Android Emulator.
- **Windows**: This app runs on Windows systems.

---

## Troubleshooting

### Common Issues

1. **Error: Configuration file not found**:
   - Ensure BlueStacks is installed and running.
   - Verify that the `bluestacks.conf` file exists in the expected directory.

2. **Status not updating**:
   - Restart the app to refresh instance detection.
   - Ensure the `.bstk` files are not locked by another process.

3. **Permissions error**:
   - Run the app as an administrator to ensure it can modify the necessary files.

---

## Development

### For Developers

1. Clone the repository:
   ```bash
   git clone https://github.com/your-repo-name.git
   cd your-repo-name
   ```

2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

3. Run the app:
   ```bash
   python main.py
   ```

4. Build the `.exe` file:
   ```bash
   pyinstaller --onefile --windowed main.py
   ```

---

## Contributions

Contributions are welcome! Feel free to open an issue or submit a pull request.