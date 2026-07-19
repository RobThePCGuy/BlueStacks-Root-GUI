# BlueStacks Root GUI

[![GitHub Repo Stars](https://img.shields.io/github/stars/RobThePCGuy/BlueStacks-Root-GUI?style=social)](https://github.com/RobThePCGuy/BlueStacks-Root-GUI)
[![YouTube Video Views](https://img.shields.io/youtube/views/zpihBs3FtEc?style=social)](https://youtu.be/zpihBs3FtEc)
[![Last Updated](https://img.shields.io/github/last-commit/RobThePCGuy/BlueStacks-Root-GUI)](https://github.com/RobThePCGuy/BlueStacks-Root-GUI/commits/master)

---

![GUI Screenshot](https://github.com/user-attachments/assets/10f965eb-e1cc-4d61-9b6f-0cbb484a4ef0)

**A one-click tool to root BlueStacks 5.** It turns root access on and off from a simple window — no command line, no reverse-engineering, no hunting for an old version. Point it at your BlueStacks, click a couple of buttons, done.

> [!TIP]
> **The latest BlueStacks now roots — no downgrade required.** BlueStacks 5.22 added a security check that shut rooted instances down with *"Android system doesn't meet security requirements."* This tool patches that check out, so you can root the current build. Confirmed working on **5.22.232.1002 / Android 13** — the latest official build as of July 2026. If someone told you to downgrade to 5.21, you don't have to anymore.

---

## Table of Contents

- [Quick Start](#quick-start)
- [What You'll See](#what-youll-see)
- [Installation](#installation)
- [Usage Guide](#usage-guide)
  - [Rooting the Current BlueStacks (Patch Mode)](#rooting-the-current-bluestacks-patch-mode)
  - [Magisk Modules, Kitsune Mask & Older Builds](#magisk-modules-kitsune-mask--older-builds)
  - [Keep Root After Updates](#keep-root-after-updates)
- [Troubleshooting](#troubleshooting)
- [How It Works](#how-it-works)
- [Features](#features)
- [Development](#development)
- [Contributing](#contributing)
- [Credits](#credits)

---

## Quick Start

You don't need to know which BlueStacks version you have — the app detects it and shows you the right buttons. Just run it as administrator and follow along.

1. **Install BlueStacks and open it once.** Let your instance finish booting, then close it. (The tool can only root an instance that already exists.)
2. **Download the tool.** Grab the latest `.exe` from **[Releases](https://github.com/RobThePCGuy/BlueStacks-Root-GUI/releases)**.
3. **Right-click the `.exe` → Run as administrator.** It opens on the **Dashboard** and finds your BlueStacks automatically.
4. **Patch the engine.** Click the red **"Patch BlueStacks Engine (required for root)"** button and confirm. Let it finish.
   > Don't see that button? You're on an older build that doesn't need it — skip straight to step 5.
5. **Turn on root.** Click **Instances** in the left menu, tick the checkbox next to your instance, and click **Toggle Root**. Watch the progress bar at the bottom and wait for it to finish.
6. **Start BlueStacks.** It boots with no security popup, and your root apps (Root Checker, Kitsune Mask, Magisk) now see root. **Done.**

That's the whole thing for most people. Want Magisk with modules and hiding, or you're on an older/MSI build? See the [Usage Guide](#usage-guide) below.

## What You'll See

The window has three tabs down the left side. You'll only ever need the first two for basic rooting.

| Tab | What it's for |
|-----|---------------|
| **Dashboard** | Where BlueStacks was found, the engine-patch button, and how many instances are rooted. **Start here.** |
| **Instances** | Your instances with live **Root** and **R/W** status. This is where you flip root on and off. |
| **Modules** | Push a Magisk module `.zip` into a running instance and flash it for you. Optional. |

A **light/dark theme** toggle sits in the header, and a **progress bar** along the bottom shows what the tool is doing during any operation.

## Installation

### Option 1: Download the Executable (Recommended)

1. Download the latest `.exe` from **[Releases](https://github.com/RobThePCGuy/BlueStacks-Root-GUI/releases)**.
2. Right-click it and choose **"Run as administrator."**

You need **Windows 10 or later** and **administrator rights** (the tool reads the registry, patches files under `Program Files`, and closes BlueStacks). You do **not** need to uninstall or downgrade BlueStacks first — the tool patches whatever current version you have, in place.

### Option 2: Run from Source

For developers, or anyone who'd rather run the Python directly. Requires **Python 3.7+**.

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
pyinstaller --onefile --windowed --icon="favicon.ico" --add-data "favicon.ico;." --add-data "tools/e2fsprogs;tools/e2fsprogs" --name BlueStacksRootGUI main.py
```

Output lands in the `dist/` folder.

> [!NOTE]
> You normally don't need to build by hand — pushing a version tag (`v*`) triggers the `release.yml` workflow, which builds this exact executable on a Windows runner and publishes it to **[Releases](https://github.com/RobThePCGuy/BlueStacks-Root-GUI/releases)** automatically.

## Usage Guide

The [Quick Start](#quick-start) covers the common case. This section has the full detail, plus the paths for Magisk/Kitsune modules and older builds. Launch the GUI **as administrator** — it opens on the **Dashboard**, auto-detects your install, and only shows the engine-patch button when a modern build (5.22.150.1014+) is present.

### Rooting the Current BlueStacks (Patch Mode)

This is the path for current BlueStacks (5.22.150.1014 and newer). You get root for apps without touching `/system` or installing anything inside Android.

1. **Create the instance first** — if this is a brand-new install, open BlueStacks once so it builds and boots your instance, then close it. Root can't be added until the instance's disk exists.
2. **Patch the engine (once per install)** — on the **Dashboard**, click **"Patch BlueStacks Engine (required for root)"** → **Yes**. All BlueStacks processes are closed first, then the tool patches and backs up the engine files. Until you do this, the **Instances** page shows a *"Patch-mode root is locked"* banner with a **Fix it** shortcut back to the Dashboard.
3. **Toggle root (per instance)** — go to the **Instances** page, tick the instance, and click **"Toggle Root."** **Watch the progress bar at the bottom** — it walks through *"Part 1/2: enabling root access..."* then *"Part 2/2: patching guest su in Data.vhdx..."* before the button is usable again. Don't launch the instance while that's running — wait for it to finish. If it says `su` isn't there yet, a dialog will tell you to boot the instance once and toggle again.
4. **Restart the instance** — start it from BlueStacks. It should boot with **no** security/tamper popup, and root-checker apps (or Kitsune Mask / Magisk) will see root.

> [!NOTE]
> If a background BlueStacks auto-update later replaces the patched files, the Dashboard raises an **"auto-update reverted your engine patch"** alert with a **Re-patch now** button. See [Keep Root After Updates](#keep-root-after-updates) to stop it happening again.

> [!TIP]
> This gets **apps** working root — enough for most root-requiring apps and root checkers. If you want **Magisk/Kitsune-managed root with modules and hiding** (Zygisk, Play Integrity Fix, LSPosed, etc.), that's a separate, more involved setup with real emulator gotchas. It's documented in the companion guide: **[Root BlueStacks with Kitsune Mask → Magisk Modules & Hiding](https://github.com/RobThePCGuy/Root-Bluestacks-with-Kitsune-Mask#magisk-modules--hiding-advanced)**.

### Magisk Modules, Kitsune Mask & Older Builds

Everything past basic root — installing **Kitsune Mask** into `/system`, choosing and flashing **Magisk modules**, **hiding** (ReZygisk, LSPosed, Play Integrity Fix, module load order), and rooting **older or MSI builds** — lives in the companion guide, so it stays in one maintained place instead of being half-covered in two:

> [!TIP]
> **➡️ [Root BlueStacks with Kitsune Mask](https://github.com/RobThePCGuy/Root-Bluestacks-with-Kitsune-Mask)** — the full written walkthrough.
> Stuck, or want to share a setup that works? Ask and help out in **[Discussions](https://github.com/RobThePCGuy/Root-Bluestacks-with-Kitsune-Mask/discussions)** there.

One tool-specific note: this app's **Modules** tab pushes and flashes a module `.zip` into a running, rooted instance for you — start the instance, open the **Modules** tab, pick it, **Browse...** to the `.zip`, and click **Push and flash module**, then reopen the instance. It exists because BlueStacks' own file picker hands Magisk an *"Invalid Uri"* it can't open. (If the ADB root shell isn't reachable, the tool drops the `.zip` in the instance's `Download` folder so you can flash it by hand.)

### Keep Root After Updates

Root sticks across normal restarts, but a background **BlueStacks auto-update can silently replace the patched files and bring the security check back**. If that happens, just click **Re-patch now** on the Dashboard (or re-run "Patch BlueStacks Engine"). To stop it from happening, disable the two update paths (Administrator terminal):

```powershell
sc.exe stop BstHdUpdaterSvc
sc.exe config BstHdUpdaterSvc start= disabled
schtasks /Change /TN "BlueStacksHelper_nxt" /DISABLE
```

> [!WARNING]
> The scheduled task is the one that matters most. Some builds don't even install the `BstHdUpdaterSvc` service — the `sc.exe` lines will report *"service does not exist,"* which is fine — but they still ship the `BlueStacksHelper_nxt` scheduled task, which can update independently. Disable whichever exist. Setting `bst.auto_update="0"` in `bluestacks.conf` does **not** work; it is silently ignored.

## Troubleshooting

### Common Issues

**No instances listed / "Path Not Found"**
- Run the GUI as **Administrator**
- Verify registry keys exist: `HKLM\SOFTWARE\BlueStacks_nxt` (Normal), `HKLM\SOFTWARE\BlueStacks_nxt_cn` (China), or `HKLM\SOFTWARE\BlueStacks_msi5` (MSI)
- Perform a clean reinstall using the official cleaner tool

**"Permission denied" while patching `HD-MultiInstanceManager.exe`**
- This means the Multi-Instance Manager window was open, locking the file. The tool now closes it automatically before patching — make sure you're on the latest version, then re-run "Patch BlueStacks Engine."

**"Toggle Root" says `su` isn't in `Data.vhdx` yet**
- The guest `su` only materializes after the instance's first boot. Start the instance once, shut it down, and toggle root again.

**Root worked, then stopped after a while**
- BlueStacks likely auto-updated and reverted the patch. Click **Re-patch now** on the Dashboard, then follow [Keep Root After Updates](#keep-root-after-updates).

**R/W toggle doesn't persist**
- Ensure BlueStacks processes were fully terminated (kill leftovers in Task Manager if needed)

**Installing a module fails with "Invalid Uri"**
- Don't use BlueStacks' own file picker — use the app's **Modules** tab instead (see [Magisk Modules, Kitsune Mask & Older Builds](#magisk-modules-kitsune-mask--older-builds)). Deeper Kitsune/module help lives in the [companion guide's Discussions](https://github.com/RobThePCGuy/Root-Bluestacks-with-Kitsune-Mask/discussions).

**Toggle operation errors**
- Check the progress bar/status text at the bottom of the window for the error message
- A full log is written to `%TEMP%\BlueStacksRootGUI.log` — helpful when reporting an issue

**BlueStacks won't launch after patching (locked-down / corporate PCs)**
- Patching `HD-Player.exe` invalidates its digital signature. Machines that enforce **Windows Defender Application Control (WDAC)** or strict **AppLocker** publisher rules may then block the patched binary from running. This does not affect normal home PCs.
- If you're on a managed machine and BlueStacks silently fails to start after patching, use **"Undo Engine Patch"** to restore the signed original, or run on a machine without those policies.

### Version Compatibility

| BlueStacks Version | Root Working? | Method |
|-------------------|---------------|--------|
| 5.20.x – 5.21.x | Yes | Classic `enable_root_access` rooting |
| 5.22.x (pre-5.22.150.1014) | Yes | Classic rooting + engine integrity patch to clear the security popup |
| 5.22.150.1014+ | Yes | Patch mode: engine patch + `Data.vhdx` guest-`su` patch |

**Verified rooted** — every instance reports `uid=0` after toggling root:

| Edition | Registry key | Version | Mode | Android versions verified |
|---------|--------------|---------|------|---------------------------|
| Normal | `BlueStacks_nxt` | 5.22.232.1002 | patch | 7 (32/64-bit), 9, 11, 13 |
| China | `BlueStacks_nxt_cn` | 5.22.170.6509 | patch | 7 (32/64-bit), 9, 11, 13 |
| MSI | `BlueStacks_msi5` | 5.22.75.6322 | classic | 7 (32/64-bit), 9, 11, 13 |

> **Note:** On classic / MSI builds the guest `su` is exposed at `/system/xbin/bstk/su`; on patch-mode builds `su` is on the `PATH` directly. `bst.feature.rooting` resets to `0` on launch, but root stays live via the per-instance `enable_root_access` flag.

<details>
<summary><b>Background: the 5.22 "security" popup</b></summary>

**Issue:** BlueStacks 5.22+ (October 2025) shows *"Android system doesn't meet security requirements"* and shuts the instance down when root/R/W is enabled.

**Cause:** Google replaced SafetyNet with the Play Integrity API in January 2025. BlueStacks 5.22 added a disk-integrity check that detects the modified system and refuses to boot it.

**Fix:** This tool's engine patch disables that check, so downgrading to 5.21 is no longer required. Downgrade instructions are kept below only for reference.

</details>

<a id="how-to-downgrade-to-521-legacy"></a>
<details>
<summary><b>How to Downgrade to 5.21 (legacy)</b></summary>

You should not need this anymore — it's kept for reference only.

1. **Backup your data** - Export important app data/saves

2. **Complete uninstall**
   - Download **[BSTCleaner](https://support.bluestacks.com/hc/en-us/articles/360057724751)**
   - Run to remove all BlueStacks files

3. **Install BlueStacks 5.21**
   - Download from **[Uptodown Archive](https://bluestacks-app-player.en.uptodown.com/windows/versions)**
   - Look for version **5.21.x.xxxx** (January 2025)

4. **Disable auto-updates** - see [Keep Root After Updates](#keep-root-after-updates)

5. **Apply rooting guide** - follow the classic-build steps above

</details>

**Tracking:** See [Issue #11](https://github.com/RobThePCGuy/Root-Bluestacks-with-Kitsune-Mask/issues/11) for history and discussion.

## How It Works

*(For the curious — you don't need any of this to use the tool.)*

BlueStacks changed how it locks down root across versions, so the tool uses two approaches and chooses automatically based on the detected version.

**Classic builds (5.22.130 and older, and MSI):** root is the original flag-based method. Setting `bst.instance.<name>.enable_root_access=1` exposes the guest `su`. On some builds `su` only lives at `/system/xbin/bstk/su` (not on the app `PATH`), so root-checker *apps* report "not rooted" even though a shell gets `uid=0`; the tool adds a `/system/xbin/su` symlink offline so apps see it too.

**Patch-mode builds (5.22.150.1014+):** BlueStacks added two locks. First, `HD-Player.exe` runs a disk-integrity check on boot and force-closes a modified instance with the *"illegally tampered"* popup. Second, the guest `su` was rewritten to grant root only to a signed whitelist. The tool defeats both:

1. **Engine patch** - flips `_isDiskVerificationRequired()` in `HD-Player.exe` to return 0, which disables the integrity shutdown **and** turns on Developer Mode. It also NOPs the routine in `HD-MultiInstanceManager.exe` that resets `enable_root_access` to 0.
2. **Guest-`su` patch** - opens the instance's `Data.vhdx` directly (no running instance, no ADB), finds every guest `su`, and flips its `isDeveloperMode()` gate to always-grant so root works for **every app**.

Both patches are located by byte signature, not hard-coded offsets, so they survive minor version rebuilds, and both are fully reversible.

> [!NOTE]
> The patch-mode method — the `HD-Player.exe` / `HD-MultiInstanceManager.exe` engine patch **and** the offline `Data.vhdx` guest-`su` patch that root the latest BlueStacks — was contributed by **[@AndnixSH](https://github.com/AndnixSH)** in [PR #27](https://github.com/RobThePCGuy/BlueStacks-Root-GUI/pull/27). See [Credits](#credits).

## Features

- **Nav-Rail Layout** - A left navigation rail splits the app into three pages: **Dashboard** (install paths, engine-patch state, rooted-instance count), **Instances** (per-instance root/R-W toggles), and **Modules** (push and flash a Magisk module). A light/dark theme toggle sits in the header
- **Auto-Detection** - Discovers BlueStacks installation paths via the Windows Registry (Normal, China, and MSI editions) and picks the right rooting method per version automatically
- **Instance Listing** - Lists every instance by its display name with live Root and R/W status (root shows a green highlight when on), including newer instances that use a single `Data.vhdx` layout (created or cloned) — not just the classic `fastboot.vdi`/`Root.vhd` ones
- **Engine-Patch Status** - The Dashboard's engine button reads its own state at a glance: *"Patch BlueStacks Engine (required for root),"* *"Engine patched (click to Undo),"* or *"Engine partially patched (click to finish)."* It's per-install and applies to every instance
- **Patch-Gating Banner** - On patch-mode builds, the Instances page shows a banner while the engine is unpatched (*"Patch-mode root is locked…"*) with a **Fix it** button that jumps straight to the Dashboard, so you can't try to root an instance before the engine is ready
- **Update-Revert Alert** - If a background auto-update silently replaces the patched files, the Dashboard raises an alert with a one-click **Re-patch now** button
- **Root Toggle** - Enables root the right way for your build: the `enable_root_access` / `bst.feature.rooting` flags on classic builds, plus an offline guest-`su` patch on 5.22.150.1014+. Prompts you to boot a fresh instance once if its `su` isn't generated yet
- **Engine Patch (5.22+)** - Patches `HD-Player.exe` to disable the *"doesn't meet security"* integrity shutdown, and `HD-MultiInstanceManager.exe` so root isn't reset back off when you edit instances
- **Read/Write Toggle** - Switches disk files (`fastboot.vdi`, `Root.vhd`) between `Normal` and `Readonly`
- **Push and Flash Module** - The Modules page pushes a module `.zip` into a running instance and flashes it directly over BlueStacks' bundled ADB (`magisk --install-module`), so you skip BlueStacks' file dialog entirely (it hands Magisk an *"Invalid Uri"* it can't open). Just close and reopen the instance afterwards to activate it
- **Reversible** - Every binary patch backs up to a `.prepatch.bak`; every guest-`su` patch records the original bytes. "Undo Engine Patch" and toggling root off restore the originals
- **Process Handling** - Closes all BlueStacks processes (player, services, and the Multi-Instance Manager) before applying changes
- **Responsive UI** - Long operations run on background threads (`QThread`) so the window never freezes, and a docked progress bar reports real step-by-step percentages
- **Internationalization** - Includes English and Japanese translations

## Development

### Project Structure

- `main.py` - Application entry point and controller: wires the UI to the handlers, owns the background-thread orchestration
- `views/` - PyQt5 UI package (nav-rail layout)
  - `main_window.py` - Main window: nav rail, page stack, worker threads, docked progress bar
  - `nav_rail.py` - Left navigation rail (Dashboard / Instances / Modules)
  - `dashboard_page.py` - Install paths, engine-patch button, update-revert alert, rooted-count stat
  - `instances_page.py` - Instance grid, Toggle Root/R-W, patch-gating banner
  - `modules_page.py` - Pick a running instance, pick a module `.zip`, push and flash
  - `progress.py` - Docked status/progress indicator with step percentages
  - `theme.py` - Light/dark QSS themes and persistence
  - `engine_rules.py` - Qt-free decision logic for patch-gating and update-revert detection (unit-testable without a `QApplication`)
- `config_handler.py` - Reads/writes `bluestacks.conf`
- `instance_handler.py` - Modifies `.bstk` files, handles processes
- `registry_handler.py` - Reads BlueStacks paths and versions from the Windows Registry
- `constants.py` - Shared constants (keys, filenames, modes, process list, patch-mode version cutoff, `APP_VERSION`)
- `admin.py` - UAC elevation helpers (relaunch as administrator, network-drive-safe)
- `adb_handler.py` - Pushes and flashes a module `.zip` into a running instance over BlueStacks' bundled ADB (the app's one online operation)
- `integrity_patch.py` / `root_persistence.py` - Engine patches (5.22+ integrity bypass, keep root enabled) with `.prepatch.bak` backups
- `su_patch.py` / `su_patch_offline.py` - Patch-mode app root: flips the guest `su` `isDeveloperMode` gate inside `Data.vhdx` (bundled VHD/VHDX + ext4 reader, no ADB required)
- `ext4_symlink.py` - Classic/MSI app root: adds `/system/xbin/su` in `Root.vhd` via bundled `debugfs` (`tools/e2fsprogs/`)

### Dependencies

See `requirements.txt`. Key dependencies:
- PyQt5
- pywin32
- psutil

### Running Tests

The suite uses `pytest` with `pytest-qt` (for the Qt view tests):

```bash
pip install -r requirements-dev.txt
pytest
```

## Contributing

Contributions are welcome! Please:

- Maintain existing code style and structure
- Use the `logging` module for debugging output
- Add/update docstrings for new or modified code
- Use background threads for blocking operations to keep the UI responsive
- Update `constants.py` for new configurable values
- Submit pull requests with clear descriptions
- Open an issue to discuss significant changes before implementing

## Credits

- **Rooting the latest BlueStacks (patch mode):** the engine patch (`HD-Player.exe` + `HD-MultiInstanceManager.exe`) and the offline `Data.vhdx` guest-`su` patch that defeat the 5.22.150.1014+ integrity check were contributed by **[@AndnixSH](https://github.com/AndnixSH)** in [PR #27](https://github.com/RobThePCGuy/BlueStacks-Root-GUI/pull/27). This tool automates that method; without it there'd be no root on current builds without downgrading.
- **Maintainer:** [@RobThePCGuy](https://github.com/RobThePCGuy) — original GUI, the classic flag-based rooting, and the hardening around the patch-mode method (auto-kill Multi-Instance Manager, restore brick-guard, binary-provenance audit).

---

**Related Project:** [Root BlueStacks with Kitsune Mask](https://github.com/RobThePCGuy/Root-Bluestacks-with-Kitsune-Mask/) — the full Kitsune Mask, Magisk modules, and hiding guide, plus [Discussions](https://github.com/RobThePCGuy/Root-Bluestacks-with-Kitsune-Mask/discussions) for help and sharing setups.
