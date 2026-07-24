"""Magisk tab controller: owns the handler logic for Magisk system-root
install/uninstall, the manager app, ReZygisk, and LSPosed.

This is an extraction of responsibility out of ``MainWindow``, not a
decoupling from it -- the controller is constructed with the owning
``MainWindow`` and reaches back into it for shared infrastructure (the
confirm dialog, the async job runner, the Magisk page widget, instance data,
engine state). ``MainWindow`` previously owned all of this directly; moving
it here keeps the Magisk tab's ~10 handler methods together instead of
interleaved with every other tab's handlers in one 1000+ line file.
"""
from __future__ import annotations

import os
import tempfile

from PyQt5.QtCore import QThread
from PyQt5.QtWidgets import QMessageBox

import adb_handler
import constants
import instance_handler
import lsposed_payload
import magisk_payload
import magisk_system
import rezygisk_payload


class MagiskController:
    def __init__(self, window):
        self._window = window

    def refresh_statuses(self) -> None:
        """Fill the Magisk tab with each instance's current install state."""
        w = self._window
        statuses = {uid: magisk_system.magisk_status(data["data_path"])
                    for uid, data in w.instance_data.items()}
        w.instances_page.set_magisk_statuses(statuses)

    def _selected_instance(self):
        w = self._window
        uid = w.instances_page.selected_instance_id()
        if not uid or uid not in w.instance_data:
            QMessageBox.information(w, "No instance selected",
                                    "Tick exactly one instance on the Instances tab first.")
            return None, None
        return uid, w.instance_data[uid]

    def handle_install(self) -> None:
        w = self._window
        uid, instance = self._selected_instance()
        if instance is None:
            return
        # The modified guest /system only boots on a patched engine.
        if instance.get("patch_mode") and w._engine_state() != "patched":
            QMessageBox.warning(
                w, "Patch the engine first",
                "Installing Magisk modifies the guest system image, which only "
                "boots on a patched engine. Patch it from the Dashboard, then "
                "try again.")
            return
        app_root_note = (
            "<p><b>Heads up:</b> this instance has app-root (Toggle Root) on. "
            "Magisk brings its own <code>su</code>. Turn app-root off on the "
            "Instances tab to avoid two competing su providers.</p>"
            if instance.get("root_enabled") else "")
        if not w._confirm(
                "Install Magisk",
                "Install full offline Magisk system-root into %s?" % uid,
                "<p>Writes Magisk into the instance's system and data images while "
                "it's shut down, no R/W toggle, no temp-root. All BlueStacks "
                "processes close first.</p>"
                "<p>When it finishes: start the instance, enable ADB, then click "
                "<b>Install manager app</b>.</p>"
                "<p>All instances of this Android version share one master "
                "Root.vhd: installing here roots every clone of it, not just "
                "%s.</p>"
                "<p>This gives you root, Zygisk, and Xposed. It does not give "
                "you Play Integrity: Google limits emulator integrity to its own "
                "Google Play Games, so apps that gate on it stay broken.</p>"
                % uid + app_root_note):
            return
        data_path = instance["data_path"]

        def job(progress):
            progress("Closing BlueStacks...", 0)
            instance_handler.terminate_bluestacks()
            QThread.msleep(constants.PROCESS_TERMINATION_WAIT_MS)
            try:
                results = magisk_system.install(data_path, progress=lambda m: progress(m, -1))
            except magisk_system.RollbackFailedError as exc:
                # Distinct from a plain install failure: the automatic /system
                # rollback also failed, so the instance may be left half-installed
                # and unable to boot rather than cleanly reverted to stock.
                raise RuntimeError(
                    "Install failed AND the automatic cleanup also failed (%s). "
                    "%s may now be left half-installed and unable to boot. Try "
                    "\"Uninstall Magisk\" to force-clean it; if that also fails, "
                    "restore this instance from a backup." % (exc, uid)) from exc
            return results[-1] if results else "Magisk installed."

        w._run_async(job, "Installing Magisk into %s..." % uid)

    def handle_uninstall(self) -> None:
        w = self._window
        uid, instance = self._selected_instance()
        if instance is None:
            return
        if not w._confirm(
                "Uninstall Magisk",
                "Remove Magisk from %s?" % uid,
                "<p>Removes the Magisk system footprint (restoring the stock boot "
                "sequence) and <code>/data/adb/magisk</code>, while the instance "
                "is shut down. All BlueStacks processes close first.</p>"
                "<p>All instances of this Android version share one master "
                "Root.vhd: this removes root from every clone of it, not just "
                "%s.</p>" % uid):
            return
        data_path = instance["data_path"]

        def job(progress):
            progress("Closing BlueStacks...", 0)
            instance_handler.terminate_bluestacks()
            QThread.msleep(constants.PROCESS_TERMINATION_WAIT_MS)
            results = magisk_system.uninstall(data_path, progress=lambda m: progress(m, -1))
            return results[-1] if results else "Magisk removed."

        w._run_async(job, "Removing Magisk from %s..." % uid)

    def _adb_and_port(self, instance):
        """(adb_exe, port) for an over-ADB action on a running instance, or
        (None, None) after warning if ADB isn't present."""
        w = self._window
        install_dirs = [i.get("install_path") for i in w.installations]
        adb_exe = adb_handler.find_adb(install_dirs)
        if not adb_exe:
            QMessageBox.warning(
                w, "ADB not found",
                "Couldn't find HD-Adb.exe in the BlueStacks install folder, so "
                "this can't run over ADB.")
            return None, None
        port = adb_handler.instance_adb_port(instance["config_path"], instance["original_name"])
        return adb_exe, port

    def _cache_dir(self):
        return os.path.join(tempfile.gettempdir(), "BlueStacksRootGUI-magisk", "cache")

    def handle_install_manager(self) -> None:
        w = self._window
        uid, instance = self._selected_instance()
        if instance is None:
            return
        adb_exe, port = self._adb_and_port(instance)
        if not adb_exe:
            return
        data_path = instance["data_path"]

        def job(progress):
            def relay(msg):
                progress(msg, -1)
            progress("Fetching the Magisk manager...", -1)
            apk = magisk_payload.fetch_apk(self._cache_dir(), progress=relay)
            msg = adb_handler.install_manager(adb_exe, port, apk, progress=relay)
            magisk_system.add_component(data_path, "manager")  # reflect it in the status
            w.show_notice.emit("Manager installed", msg)
            return msg

        w._run_async(job, "Installing the Magisk manager into %s..." % uid)

    def handle_uninstall_manager(self) -> None:
        w = self._window
        uid, instance = self._selected_instance()
        if instance is None:
            return
        adb_exe, port = self._adb_and_port(instance)
        if not adb_exe:
            return
        data_path = instance["data_path"]

        def job(progress):
            msg = adb_handler.uninstall_manager(adb_exe, port, progress=lambda m: progress(m, -1))
            magisk_system.remove_component(data_path, "manager")
            w.show_notice.emit("Manager removed", msg)
            return msg

        w._run_async(job, "Removing the Magisk manager from %s..." % uid)

    def handle_install_rezygisk(self) -> None:
        w = self._window
        uid, instance = self._selected_instance()
        if instance is None:
            return
        adb_exe, port = self._adb_and_port(instance)
        if not adb_exe:
            return

        def job(progress):
            def relay(msg):
                progress(msg, -1)
            progress("Fetching ReZygisk...", -1)
            zip_path = rezygisk_payload.fetch_module(self._cache_dir(), progress=relay)
            msg = adb_handler.install_module(adb_exe, port, zip_path, progress=relay)
            w.show_notice.emit("ReZygisk installed", msg)
            return "%s Reboot the instance to activate Zygisk." % msg

        w._run_async(job, "Installing ReZygisk into %s..." % uid)

    def handle_install_lsposed(self) -> None:
        w = self._window
        uid, instance = self._selected_instance()
        if instance is None:
            return
        adb_exe, port = self._adb_and_port(instance)
        if not adb_exe:
            return

        def job(progress):
            def relay(msg):
                progress(msg, -1)
            progress("Fetching LSPosed...", -1)
            zip_path = lsposed_payload.fetch_module(self._cache_dir(), progress=relay)
            msg = adb_handler.install_module(adb_exe, port, zip_path, progress=relay)
            w.show_notice.emit("LSPosed installed", msg)
            return ("%s Reboot the instance to activate it (needs ReZygisk); then "
                    "manage modules from the LSPosed app." % msg)

        w._run_async(job, "Installing LSPosed into %s..." % uid)
