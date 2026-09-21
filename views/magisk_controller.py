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

import logging
import os
import tempfile

from PyQt5.QtCore import QThread
from PyQt5.QtWidgets import QMessageBox

import adb_handler
import config_handler
import constants
import instance_handler
import lsposed_payload
import macos_kyubi
import macos_locator
import magisk_payload
import magisk_system
import rezygisk_payload
from views.progress import StepReporter

logger = logging.getLogger(__name__)

# Roughly how many progress messages each operation emits. StepReporter turns
# that into a moving percentage and clamps below 100, so an operation that talks
# more than expected still never looks finished early. Approximate on purpose:
# the backends report what they are doing, not how far along they are.
_STEPS_INSTALL = 18
_STEPS_UNINSTALL = 8
_STEPS_UPDATE = 20
_STEPS_MANAGER = 6
_STEPS_MODULE = 7


class MagiskController:
    def __init__(self, window):
        self._window = window

    def refresh_statuses(self) -> None:
        """Fill the Magisk tab with each instance's current install state."""
        w = self._window
        statuses = {uid: self._status(data) for uid, data in w.instance_data.items()}
        w.instances_page.set_magisk_statuses(statuses)

    # --- BlueStacks Air ----------------------------------------------------
    # Kyubi on Air lives in the one system image every instance shares, so its
    # status and its components are recorded per installation, not per instance
    # (macos_kyubi). These helpers let every handler below stay one code path.

    @staticmethod
    def _air_args(instance) -> tuple[str, str]:
        return (instance.get("app_path"),
                instance.get("user_path") or macos_locator.DATA_DIR)

    def _status(self, instance):
        if instance.get("air_mode"):
            return macos_kyubi.status(*self._air_args(instance))
        return magisk_system.magisk_status(instance["data_path"])

    def _add_component(self, instance, component) -> None:
        if instance.get("air_mode"):
            app_path, data_dir = self._air_args(instance)
            macos_kyubi.add_component(app_path, component, data_dir)
        else:
            magisk_system.add_component(instance["data_path"], component)

    def _remove_component(self, instance, component) -> None:
        if instance.get("air_mode"):
            app_path, data_dir = self._air_args(instance)
            macos_kyubi.remove_component(app_path, component, data_dir)
        else:
            magisk_system.remove_component(instance["data_path"], component)

    def _clean_air_data(self, instance, report) -> None:
        """Best effort, before shutdown: clear Kyubi's files from /data.

        The system image is what makes Kyubi run, so removing it there is the
        uninstall. The copy in /data/adb/magisk is inert without it, but a
        running instance lets us leave /data as tidy as the Windows uninstall
        does. Instances that are not running keep an inert copy.
        """
        w = self._window
        adb_exe = adb_handler.find_adb([i.get("install_path") for i in w.installations])
        port = adb_handler.instance_adb_port(instance["config_path"],
                                             instance["original_name"])
        if not adb_exe or not port:
            return
        try:
            report("Removing Kyubi's files from the running instance...")
            adb_handler.remove_databin(adb_exe, port)
        except Exception:  # noqa: BLE001 - the uninstall itself does not depend on it
            logger.info("could not clean /data/adb over ADB", exc_info=True)

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
        native_on = bool(instance.get("root_enabled"))
        if instance.get("air_mode"):
            self._install_air(uid, instance, native_on)
            return
        swap_note = ("<p>Native Root is on. Both provide <code>su</code> and would "
                     "fight, so it is switched off first.</p>" if native_on else "")
        if not w._confirm(
                "Manager Root",
                "Install Magisk-managed root into %s?" % uid,
                "<p>Writes Magisk into the system image while the instance is shut "
                "down, then starts it and installs the manager app for you.</p>"
                + swap_note +
                "<p>Every instance of this Android version shares one system image, "
                "so this affects its clones too.</p>"):
            return

        data_path = instance["data_path"]
        install_dir = instance.get("install_path")
        instance_name = instance["original_name"]
        config_path = instance["config_path"]
        # Resolved here, on the UI thread: _adb_and_port can raise a dialog, and
        # the manager step below runs in the worker.
        install_dirs = [i.get("install_path") for i in w.installations]
        adb_exe = adb_handler.find_adb(install_dirs)
        port = (adb_handler.instance_adb_port(config_path, instance_name)
                if adb_exe else None)

        def job(progress):
            steps = StepReporter(progress, _STEPS_INSTALL)
            progress("Closing BlueStacks...", 0)
            instance_handler.terminate_bluestacks()
            QThread.msleep(constants.PROCESS_TERMINATION_WAIT_MS)
            if native_on:
                # The conflict is mechanical and the app understands it, so it
                # resolves it rather than sending the user off to do a chore.
                steps("Switching Native Root off...")
                w._toggle_single_instance_root(uid, steps)
            try:
                magisk_system.install(data_path, progress=steps)
            except magisk_system.RollbackFailedError as exc:
                # Distinct from a plain install failure: the automatic /system
                # rollback also failed, so the instance may be left half-installed
                # and unable to boot rather than cleanly reverted to stock.
                raise RuntimeError(
                    "Install failed AND the automatic cleanup also failed (%s). "
                    "%s may now be left half-installed and unable to boot. Try "
                    "\"Remove Manager Root\" to force-clean it; if that also "
                    "fails, restore this instance from a backup." % (exc, uid)) from exc
            return self._finish_with_manager(
                instance, install_dir, instance_name, config_path,
                adb_exe, port, steps)

        w._run_async(job, "Installing Manager Root into %s..." % uid)

    def _install_air(self, uid, instance, native_on) -> None:
        w = self._window
        swap_note = ("<p>Root is on. Kyubi brings its own <code>su</code>, so the "
                     "plain one is removed in the same pass.</p>" if native_on else "")
        if not w._confirm(
                "Manager Root",
                "Install Kyubi into BlueStacks Air?",
                "<p>Writes Kyubi into the Android system image while BlueStacks "
                "is closed, then starts %s and installs the Kyubi app for you.</p>"
                % uid + swap_note +
                "<p>Every Air instance shares that one image, so this covers all "
                "of them.</p>"):
            return
        app_path, data_dir = self._air_args(instance)
        install_dir = instance.get("install_path")
        instance_name = instance["original_name"]
        config_path = instance["config_path"]
        adb_exe = adb_handler.find_adb([i.get("install_path") for i in w.installations])
        port = (adb_handler.instance_adb_port(config_path, instance_name)
                if adb_exe else None)

        def job(progress):
            steps = StepReporter(progress, _STEPS_INSTALL)
            progress("Closing BlueStacks...", 0)
            instance_handler.terminate_bluestacks()
            QThread.msleep(constants.PROCESS_TERMINATION_WAIT_MS)
            macos_kyubi.install(app_path, progress=steps, data_dir=data_dir)
            return self._finish_with_manager(
                instance, install_dir, instance_name, config_path,
                adb_exe, port, steps)

        w._run_async(job, "Installing Kyubi into BlueStacks Air...")

    def _finish_with_manager(self, instance, install_dir, instance_name,
                             config_path, adb_exe, port, report) -> str:
        """Start the instance and install the manager app over ADB.

        The offline install leaves working root but no manager app, and making
        the user boot the instance and press a second button for something the
        app can do itself was the most confusing part of the flow. Every failure
        here is reported as a follow-up, never as a failed install: the root is
        already in and valuable on its own, so this must not turn a success into
        an error.
        """
        if not adb_exe or not install_dir:
            return ("Manager Root installed. Start the instance, then use "
                    "\"Manager app\" to add the Kyubi app.")
        try:
            # ADB is off by default on a fresh instance, and the manager install
            # needs it; enabling it here is what makes this step reliable.
            config_handler.modify_config_file(config_path, constants.ENABLE_ADB_KEY, "1")
            report("Starting the instance to finish setup...")
            instance_handler.launch_instance(install_dir, instance_name)
            serial = adb_handler.wait_until_ready(adb_exe, port, progress=report)
            if not serial:
                return ("Manager Root installed, but the instance did not finish "
                        "booting in time. Once it is up, use \"Manager app\".")
            apk = magisk_payload.fetch_apk(self._cache_dir(), progress=report)
            adb_handler.install_manager(adb_exe, port, apk, progress=report)
            self._add_component(instance, "manager")
        except Exception as exc:  # noqa: BLE001 - the root install already succeeded
            logger.warning("automatic manager install failed", exc_info=True)
            return ("Manager Root installed. The Kyubi app could not be added "
                    "automatically (%s); use \"Manager app\" to retry." % exc)
        return ("Manager Root and the Kyubi app are installed. Restart the "
                "instance when you want to add modules.")

    def handle_uninstall(self) -> None:
        w = self._window
        uid, instance = self._selected_instance()
        if instance is None:
            return
        if instance.get("air_mode"):
            self._uninstall_air(instance)
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
            results = magisk_system.uninstall(
                data_path, progress=StepReporter(progress, _STEPS_UNINSTALL))
            return results[-1] if results else "Magisk removed."

        w._run_async(job, "Removing Magisk from %s..." % uid)

    def _uninstall_air(self, instance) -> None:
        w = self._window
        if not w._confirm(
                "Remove Manager Root",
                "Remove Kyubi from BlueStacks Air?",
                "<p>Takes Kyubi out of the Android system image every Air "
                "instance shares. BlueStacks closes first. If Kyubi was the only "
                "change, the original image is put back exactly.</p>"):
            return
        app_path, data_dir = self._air_args(instance)

        def job(progress):
            steps = StepReporter(progress, _STEPS_UNINSTALL)
            self._clean_air_data(instance, steps)
            progress("Closing BlueStacks...", 0)
            instance_handler.terminate_bluestacks()
            QThread.msleep(constants.PROCESS_TERMINATION_WAIT_MS)
            results = macos_kyubi.uninstall(app_path, progress=steps, data_dir=data_dir)
            return results[-1] if results else "Kyubi removed."

        w._run_async(job, "Removing Kyubi from BlueStacks Air...")

    def handle_update(self) -> None:
        w = self._window
        uid, instance = self._selected_instance()
        if instance is None:
            return
        st = w.instances_page.selected_status()   # the refreshed manifest for this row
        if not st:
            QMessageBox.information(w, "Magisk not installed",
                                    "There is no Magisk install on %s to update." % uid)
            return
        if instance.get("air_mode"):
            self._update_air(instance, st)
            return
        # An update rewrites the guest system image, same as a fresh install, so
        # it needs the same patched engine to boot afterwards.
        if instance.get("patch_mode") and w._engine_state() != "patched":
            QMessageBox.warning(
                w, "Patch the engine first",
                "Updating Magisk rewrites the guest system image, which only "
                "boots on a patched engine. Patch it from the Dashboard, then "
                "try again.")
            return
        if not w._confirm(
                "Update Magisk",
                "Check for a newer Magisk and update %s?" % uid,
                "<p>Looks up the latest build and, if it is newer than the one "
                "installed, refreshes the system files and binaries offline "
                "(BlueStacks closes first). Nothing happens if you are already "
                "up to date.</p>"
                "<p>Your manager app and any modules (ReZygisk, LSPosed) are left "
                "in place. All instances of this Android version share one master "
                "Root.vhd, so this updates every clone of it.</p>"):
            return
        data_path = instance["data_path"]
        installed_sha = (st.get("payload_sha256") or "").lower()

        def job(progress):
            progress("Checking the latest Magisk...", 0)
            try:
                # Small fixed percentages rather than -1: flipping the bar to its
                # indeterminate animation for the lookup and back again reads as
                # a glitch mid-operation.
                latest_ver, latest_sha = magisk_payload.latest_identity(
                    progress=lambda m: progress(m, 3))
            except RuntimeError as exc:
                return "Could not check for an update: %s" % exc
            # Only claim "up to date" when we have a real installed hash to match:
            # an empty one (a manifest predating the field) means we can't tell, so
            # refresh rather than silently assume current. A SHA difference proves
            # "different", not "newer", so the copy says "update to", not "newer".
            if installed_sha and latest_sha == installed_sha:
                return "Magisk is already up to date (%s)." % st.get("version", "?")
            step = ("Updating to %s" if installed_sha
                    else "Installed version unknown; refreshing to %s") % latest_ver
            progress("%s; closing BlueStacks..." % step, 5)
            instance_handler.terminate_bluestacks()
            QThread.msleep(constants.PROCESS_TERMINATION_WAIT_MS)
            try:
                results = magisk_system.update(
                    data_path, progress=StepReporter(progress, _STEPS_UPDATE))
            except magisk_system.RollbackFailedError as exc:
                raise RuntimeError(
                    "Update failed AND the automatic cleanup also failed (%s). %s "
                    "may be left half-installed; try \"Uninstall Magisk\" then "
                    "\"Install Magisk\"." % (exc, uid)) from exc
            return results[-1] if results else "Magisk updated."

        w._run_async(job, "Updating Magisk on %s..." % uid)

    def _update_air(self, instance, st) -> None:
        w = self._window
        if not w._confirm(
                "Update Kyubi",
                "Check for a newer Kyubi and update BlueStacks Air?",
                "<p>Looks up the latest build and, if it differs from the one "
                "installed, rewrites Kyubi in the system image (BlueStacks closes "
                "first). Your modules and the Kyubi app stay. Nothing happens if "
                "you are already up to date.</p>"):
            return
        app_path, data_dir = self._air_args(instance)
        installed_sha = (st.get("payload_sha256") or "").lower()
        had_manager = "manager" in (st.get("components") or [])

        def job(progress):
            progress("Checking the latest Kyubi...", 0)
            try:
                latest_ver, latest_sha = magisk_payload.latest_identity(
                    progress=lambda m: progress(m, 3))
            except RuntimeError as exc:
                return "Could not check for an update: %s" % exc
            if installed_sha and latest_sha == installed_sha:
                return "Kyubi is already up to date."
            progress("Updating to %s; closing BlueStacks..." % latest_ver, 5)
            instance_handler.terminate_bluestacks()
            QThread.msleep(constants.PROCESS_TERMINATION_WAIT_MS)
            macos_kyubi.install(app_path, progress=StepReporter(progress, _STEPS_UPDATE),
                                data_dir=data_dir)
            if had_manager:
                macos_kyubi.add_component(app_path, "manager", data_dir)
            return ("Kyubi updated to %s. Start BlueStacks; if the Kyubi app "
                    "asks, update it too." % latest_ver)

        w._run_async(job, "Updating Kyubi...")

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

        def job(progress):
            relay = StepReporter(progress, _STEPS_MANAGER)
            relay("Fetching the Kyubi app...")
            apk = magisk_payload.fetch_apk(self._cache_dir(), progress=relay)
            msg = adb_handler.install_manager(adb_exe, port, apk, progress=relay)
            self._add_component(instance, "manager")  # reflect it in the status
            w.show_notice.emit("Manager installed", msg)
            return msg

        w._run_async(job, "Installing the Kyubi app into %s..." % uid)

    def handle_uninstall_manager(self) -> None:
        w = self._window
        uid, instance = self._selected_instance()
        if instance is None:
            return
        adb_exe, port = self._adb_and_port(instance)
        if not adb_exe:
            return

        def job(progress):
            msg = adb_handler.uninstall_manager(
                adb_exe, port, progress=StepReporter(progress, _STEPS_MANAGER))
            self._remove_component(instance, "manager")
            w.show_notice.emit("Manager removed", msg)
            return msg

        w._run_async(job, "Removing the Kyubi app from %s..." % uid)

    def handle_install_rezygisk(self) -> None:
        w = self._window
        uid, instance = self._selected_instance()
        if instance is None:
            return
        adb_exe, port = self._adb_and_port(instance)
        if not adb_exe:
            return

        def job(progress):
            relay = StepReporter(progress, _STEPS_MODULE)
            relay("Fetching ReZygisk...")
            zip_path = rezygisk_payload.fetch_module(self._cache_dir(), progress=relay)
            msg = adb_handler.install_module(
                adb_exe, port, zip_path, progress=relay,
                min_magisk_ver_code=rezygisk_payload.MIN_MAGISK_VER_CODE)
            w.show_notice.emit("ReZygisk installed", msg)
            return msg

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
            relay = StepReporter(progress, _STEPS_MODULE)
            relay("Fetching LSPosed...")
            zip_path = lsposed_payload.fetch_module(self._cache_dir(), progress=relay)
            msg = adb_handler.install_module(adb_exe, port, zip_path, progress=relay)
            w.show_notice.emit("LSPosed installed", msg)
            return ("%s LSPosed needs ReZygisk; manage its modules from the "
                    "LSPosed app." % msg)

        w._run_async(job, "Installing LSPosed into %s..." % uid)
