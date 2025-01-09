# BlueStacks Root GUI

![GUI Screenshot](https://github.com/user-attachments/assets/10f965eb-e1cc-4d61-9b6f-0cbb484a4ef0)

> [!IMPORTANT]
> This is an unofficial modification for the BlueStacks Android emulator. If you encounter any issues, please open a GitHub issue.
>
> *As of January 9, 2025, this tool works as expected. However, it's important to note that this method is not compatible with Nougat instances. This README will be updated if that changes.*

This GUI streamlines the configuration process outlined in my guide to [rooting BlueStacks](https://github.com/RobThePCGuy/Root-Bluestacks-with-Kitsune-Mask/). While it simplifies certain steps, **both repositories** are still required for complete rooting because the linked repository contains the core rooting process. This tool lets you toggle root access and enable read/write permissions for the filesystem within the `bluestacks.conf` file of selected BlueStacks instances, providing a user-friendly alternative to manual editing.

## Features

- Automatically detects BlueStacks instances via the Windows Registry and displays them for selection.
- Toggles root access (`Root: On/Off`) in `bluestacks.conf` for selected instances.
- Toggles read/write (`R/W: On/Off`) filesystem permissions for selected instances.
- Dynamically updates the displayed root and R/W status in the GUI.

### Roadmap
- Download the latest version of BlueStacks
- Download the latest version of Magisk Delta
- Integrate ADB-based rooting directly within the GUI.

## Installation

1. **Download:** Get the latest `.exe` release from the [Releases](https://github.com/RobThePCGuy/BlueStacks-Root-GUI/releases) page.
2. **Run:** Double-click the downloaded `.exe` file. The application is portable and requires no formal installation.
3. **Prerequisites:**
   - BlueStacks must already be installed.
   - Refer to my main rooting guide ([Root BlueStacks](https://github.com/RobThePCGuy/Root-Bluestacks-with-Kitsune-Mask/)) to complete the rooting process.

## Usage

1. Run the `.exe` file.
2. The GUI will automatically detect and list available BlueStacks instances.
3. Select the instance(s) you want to modify.
4. Use the buttons:
   - **Toggle Root:** Enables or disables root access.
   - **Toggle R/W:** Enables or disables read/write permissions.
5. The GUI displays the current `Root` and `R/W` status for each instance.
6. After installing Kitsune Mask and completing the system partition installation steps described in the linked tutorial, you can **disable `Root` while leaving `R/W` enabled** if desired.
7. Close the application when finished.

## Troubleshooting

**Common Issues:**

- **"Configuration file not found":** Ensure that BlueStacks is installed. Confirm that the `bluestacks.conf` file exists in the correct directory (the GUI should handle this automatically). If the problem persists, open a GitHub issue.
- **Status not updating:** Restart the application. Ensure BlueStacks is not running (it could be locking the `.bstk` files).
- **Permissions error:** Run the application as an administrator.

## Development

**For Developers:**

1. **Clone:**
   ```bash
   git clone https://github.com/RobThePCGuy/BlueStacks-Root-GUI.git
   cd BlueStacks-Root-GUI
   ```
2. **Dependencies:**
   ```bash
   pip install -r requirements.txt
   ```
3. **Run:**
   ```bash
   python main.py
   ```
4. **Build (exe):**
   ```bash
   pyinstaller --onefile --windowed --icon=main.ico main.py
   ```
   The output file will be located inside the `dist/` folder.

## Contributing

Contributions are welcome! Please open an issue or submit a pull request.
