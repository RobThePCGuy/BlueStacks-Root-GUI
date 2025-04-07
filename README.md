# BlueStacks Root GUI

[![GitHub Repo Stars](https://img.shields.io/github/stars/RobThePCGuy/BlueStacks-Root-GUI?style=social)](https://github.com/RobThePCGuy/BlueStacks-Root-GUI) [![YouTube Video Views](https://img.shields.io/youtube/views/zpihBs3FtEc?style=social)](https://youtu.be/zpihBs3FtEc) [![Last Updated](https://img.shields.io/github/last-commit/RobThePCGuy/BlueStacks-Root-GUI)](https://github.com/RobThePCGuy/BlueStacks-Root-GUI/commits/main)

---

![GUI Screenshot](https://github.com/user-attachments/assets/10f965eb-e1cc-4d61-9b6f-0cbb484a4ef0)

BlueStacks Root GUI is a utility designed to toggle root access and enable read/write (R/W) permissions for your BlueStacks instances. It automatically detects both master and cloned instances—eliminating the need to manually edit configuration files as described in the original guide: **[Root BlueStacks with Kitsune Mask](https://github.com/RobThePCGuy/Root-Bluestacks-with-Kitsune-Mask/)**.

---

## Table of Contents

- [Features](#features)
- [Prerequisites](#prerequisites)
- [Installation & Download](#installation--download)
- [Usage](#usage)
- [Troubleshooting](#troubleshooting)
- [Development](#development)
- [Changelog](#changelog)
- [Contributing](#contributing)
- [License](#license)

---

## Features

- **Auto-Detection:**  
  Quickly identifies BlueStacks instances using the Windows Registry.

- **Root Toggle:**  
  Easily enable or disable root access by modifying `bluestacks.conf`.

- **Read/Write Permissions:**  
  Toggle R/W mode per instance to control filesystem access.

- **Dynamic Status Updates:**  
  Real-time GUI updates reflect the current state of root and R/W settings.

- **Improved Responsiveness:**  
  Background operations via QThread ensure the UI remains responsive during lengthy tasks.

---

## Prerequisites

- **Operating System:**  
  Windows 10 or later is recommended.

- **Python Version:**  
  Python 3.7 or higher.

- **Administrator Rights:**  
  Required for modifying registry keys and terminating BlueStacks processes.

- **Dependencies:**  
  Refer to `requirements.txt` for a full list of dependencies.

---

## Installation & Download

### For End Users (Executable Download)

1. **Download the Latest Executable:**  
   Visit the **[Releases](https://github.com/RobThePCGuy/BlueStacks-Root-GUI/releases)** page and download the latest `.exe` file.

2. **Run the Executable:**  
   Simply run the downloaded `.exe` file. This version is portable—no formal installation is needed.

3. **Prerequisites before Running:**  
   - **Fully Uninstall BlueStacks:**  
     Use the official tool to completely **[uninstall all previous BlueStacks installations](https://support.bluestacks.com/hc/en-us/articles/360057724751-How-to-uninstall-BlueStacks-5-BlueStacks-X-and-BlueStacks-Services-completely-from-your-PC)**.  
   - **Install the Latest BlueStacks:**  
     Download the latest version from the **[BlueStacks website](https://www.bluestacks.com/)**.

### For Developers (Building from Source)

1. **Clone the Repository:**
   ```bash
   git clone https://github.com/RobThePCGuy/BlueStacks-Root-GUI.git
   cd BlueStacks-Root-GUI
   ```

2. **Install Dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

3. **Run the Application:**
   ```bash
   python main.py
   ```

4. **Build the Executable (Optional):**
   ```bash
   pyinstaller --onefile --windowed --icon=main.ico main.py
   ```
   The built executable will be located in the `dist/` folder.

---

## Usage

1. **Launch the Application:**  
   Open the executable (or run `python main.py` if building from source).

2. **Instance Detection:**  
   The GUI will auto-detect and list all available BlueStacks instances.

3. **Select Instances:**  
   Check the boxes next to the instances you wish to modify.

4. **Toggle Operations:**
   - **Toggle Root:**  
     Click this button to enable root access. (Switch this **ON** only until Kitsune Mask is installed to `/system`.)
   - **Toggle R/W:**  
     Click to switch the instance’s filesystem mode. (Keep this **ON** for the instance to remain rooted.)

5. **Install Kitsune Mask:**
   - Download the **[Kitsune Mask](https://github.com/1q23lyc45/KitsuneMagisk/releases)** APK.
   - Launch the instance from the Multi-Instance Manager and install the APK.
   - Open the Kitsune Mask app, click on **Install**, then **Next**, and select **Direct Install to /system**.  
     > **Note:** If the **Direct Install to /system** option is missing. Simply close and reopen the Kitsune Mask app.

6. **Final Steps:**
   - Once Kitsune Mask has finished installing, you **must**:
	   - Toggle **root** *off*.
	   - Leave **R/W** on to keep the instance rooted.
   - Close the GUI when finished.

---

## Troubleshooting

### Common Issues

- **Configuration Not Found:**
  - **Solution:**  
    Fully uninstall previous BlueStacks installations using the official tool, then reinstall the latest version from the [BlueStacks website](https://www.bluestacks.com/).

- **Permission Errors:**
  - **Solution:**  
    Run the GUI as an administrator.

- **BlueStacks Not Detected:**
  - **Solution:**  
    Ensure that the required registry keys (`UserDefinedDir` and `DataDir`) are present. If missing, reinstall BlueStacks.

---

## Development

### Getting Started

1. **Clone the Repository:**
   ```bash
   git clone https://github.com/RobThePCGuy/BlueStacks-Root-GUI.git
   cd BlueStacks-Root-GUI
   ```

2. **Install Dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

3. **Run the Application:**
   ```bash
   python main.py
   ```

4. **Build the Executable:**
   ```bash
   pyinstaller --onefile --windowed --icon=main.ico main.py
   ```
   The built executable will be located in the `dist/` folder.

---

## Changelog

### v2.0.0 (Latest)
- Refactored the GUI to use QThread for improved responsiveness.
- Enhanced error handling and logging across all modules.
- Updated configuration parsing and file modification logic.
- Removed print statements in favor of consistent logging.
- Updated README to include clear instructions for downloading the executable.

*(For a complete history, please review the commit log.)*

---

## Contributing

Contributions are highly encouraged! Please follow these guidelines:
- Adhere to existing logging and error-handling practices.
- Maintain consistent code style and structure.
- Update tests and documentation as necessary.
- Submit pull requests with a clear description of your changes.

For any questions or suggestions, please open an issue in the repository.

---

## License

This project is licensed under the MIT License. See the [LICENSE](LICENSE) file for details.
