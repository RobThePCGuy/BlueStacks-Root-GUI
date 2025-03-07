# BlueStacks Root GUI

![GUI Screenshot](https://github.com/user-attachments/assets/10f965eb-e1cc-4d61-9b6f-0cbb484a4ef0)

This tool allows you to toggle root access and enable read/write (R/W) permissions for your BlueStacks instances. It automatically detects both master and cloned instances, eliminating the need to manually edit configuration files as described in my original guide: **[Root BlueStacks with Kitsune Mask](https://github.com/RobThePCGuy/Root-Bluestacks-with-Kitsune-Mask/)**.

## ✨ Features

- **Auto-detection:** Quickly identifies BlueStacks instances from the Windows Registry.
- **Root Toggle:** Enables or disables root access **(`Root: On/Off`)** in `bluestacks.conf`.
- **Read/Write Permissions:** Easily sets filesystem permissions **(`R/W: On/Off`)** per instance.
- **Dynamic Status Updates:** Real-time GUI updates reflect current root and R/W states.

## 📥 Installation

1. **Download** the latest executable (`.exe`) from the **[Releases](https://github.com/RobThePCGuy/BlueStacks-Root-GUI/releases)** page.
2. **Run** the downloaded `.exe` file (portable—no formal installation needed).
3. **Prerequisites:**
   **Fully Uninstall BlueStacks:**
      - Use the official tool to completely **[uninstall all previous BlueStacks installations](https://support.bluestacks.com/hc/en-us/articles/360057724751-How-to-uninstall-BlueStacks-5-BlueStacks-X-and-BlueStacks-Services-completely-from-your-PC)**.
      - Download the latest BlueStacks version from the official website: **[BlueStacks](https://www.bluestacks.com/)**.

## 🎯 Usage

1. Launch the downloaded `.exe` file.
2. The GUI auto-detects and lists all available BlueStacks instances.
3. Select the instances you wish to modify.
4. Use provided toggles:
   - **Toggle Root** – Switch this **ON** only until you have installed Kitsune to **`/system`**.
   - **Toggle R/W** – This must be **ON** for the instance to remain rooted.
5. Download the **[Kitsune Mask](https://github.com/1q23lyc45/KitsuneMagisk/releases)** apk file.
6. Launch the instance from the Multi-Instance Manager and install the apk.
7. You should see the Kitsune Mask application; click on it to run.
8. Root using **Kitsune Mask**:
   - Once open, look to the top under the Kitsune Mask section and select the **Install** option.
   - At the top right, tap the **Next** link to proceed.
   - Select the **Direct Install to /system** option.

>[!NOTE]
> If the **Direct Install to /system** option is missing, do not select **Direct Install**.
>
> Completely close and reopen the Kitsune Mask app. This usually resolves the issue.

9. Click Next and watch the install log for any errors.
10. Allow Kitsune Mask to finish installing, then close the BlueStacks emulator.
11. Use the provided toggles:
    - **Toggle Root** – Switch this **OFF** once the Kitsune Mask install has been completed.
    - **Toggle R/W** – This must be **ON** for the instance to remain rooted.
12. Close the BlueStacks-Root-Gui.

## ⚠️ Troubleshooting

### Common Issues:
- **Configuration not found:**
   **Fully Uninstall BlueStacks:**
      - Use the official tool to completely **[uninstall all previous BlueStacks installations](https://support.bluestacks.com/hc/en-us/articles/360057724751-How-to-uninstall-BlueStacks-5-BlueStacks-X-and-BlueStacks-Services-completely-from-your-PC)**.
      - Download the latest BlueStacks version from the official website: **[BlueStacks](https://www.bluestacks.com/)**.
- **Permissions errors**: Run the GUI as an administrator.

## 👩‍💻 Development

### Getting Started:

**Clone the repo:**
```bash
git clone https://github.com/RobThePCGuy/BlueStacks-Root-GUI.git
cd BlueStacks-Root-GUI
```

**Install dependencies:**
```bash
pip install -r requirements.txt
```

**Run the application:**
```bash
python main.py
```

**Build executable:**
```bash
pyinstaller --onefile --windowed --icon=main.ico main.py
```

The built executable will be located in the `dist/` folder.

## 🤝 Contributing

Contributions are highly encouraged! Please open issues or submit pull requests to enhance this project.
