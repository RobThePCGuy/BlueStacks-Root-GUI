"""Privacy tab controller: BlueStacks' own ad/telemetry switches (global) and
the in-guest tracker block (per instance).

Extraction of responsibility out of ``MainWindow``, same pattern as
``MagiskController`` -- constructed with the owning ``MainWindow`` and reaches
back into it for the confirm dialog, the async job runner, and the Privacy
page widget.

The two controls are deliberately separate. The ad switches are what actually
stop BlueStacks' advertising (it is served by the Windows player, so no guest
edit can reach it) and they live in the one global config. The hosts block only
reaches apps running inside the emulator, and because it modifies the guest
system image it needs the engine patch -- without it BlueStacks detects the
tampering and shuts the instance down mid-session.
"""
from __future__ import annotations

from PyQt5.QtCore import QThread
from PyQt5.QtWidgets import QMessageBox

import ad_settings
import constants
import instance_handler
import telemetry_block


class PrivacyController:
    def __init__(self, window):
        self._window = window

    # --- shared -------------------------------------------------------------

    def _config_path(self):
        """BlueStacks' single global config. Any instance points at the same one."""
        for data in self._window.instance_data.values():
            path = data.get("config_path")
            if path:
                return path
        return None

    def refresh_statuses(self) -> None:
        """Fill the Privacy tab: global ad-switch state + per-instance blocks."""
        w = self._window
        statuses = {uid: telemetry_block.status(data["data_path"])
                    for uid, data in w.instance_data.items()}
        w.privacy_page.set_instances(statuses)

        config_path = self._config_path()
        if not config_path:
            w.privacy_page.set_ad_status(None, 0)
            return
        try:
            total = len(ad_settings.discover(config_path))
            w.privacy_page.set_ad_status(ad_settings.status(config_path), total)
        except OSError:
            w.privacy_page.set_ad_status(None, 0)

    # --- global: BlueStacks' own ad/telemetry switches -----------------------

    def handle_ads_off(self) -> None:
        w = self._window
        config_path = self._config_path()
        if not config_path:
            QMessageBox.information(w, "No BlueStacks config found",
                                    "BlueStacks and its instances need to be "
                                    "detected first.")
            return
        if not w._confirm(
                "Turn off ads & telemetry",
                "Turn off BlueStacks' own ad and telemetry switches?",
                "<p>Turns off every advertising, promo and stats-upload switch "
                "found in <code>bluestacks.conf</code>. All BlueStacks processes "
                "close first, because BlueStacks rewrites that file on exit.</p>"
                "<p>This is BlueStacks' one shared config, so it applies to "
                "<b>every instance</b>, not just one.</p>"
                "<p>Fully reversible: each switch's original value is recorded, "
                "and <b>Restore BlueStacks defaults</b> puts them all back.</p>"):
            return

        def job(progress):
            progress("Closing BlueStacks...", 0)
            instance_handler.terminate_bluestacks()
            QThread.msleep(constants.PROCESS_TERMINATION_WAIT_MS)
            results = ad_settings.apply(config_path, progress=lambda m: progress(m, -1))
            return results[-1] if results else "Ads and telemetry turned off."

        w._run_async(job, "Turning off BlueStacks ads & telemetry...")

    def handle_ads_restore(self) -> None:
        w = self._window
        config_path = self._config_path()
        if not config_path:
            return
        if not w._confirm(
                "Restore BlueStacks defaults",
                "Put BlueStacks' ad and telemetry switches back?",
                "<p>Restores every switch to the value it had before this tool "
                "changed it. All BlueStacks processes close first.</p>"):
            return

        def job(progress):
            progress("Closing BlueStacks...", 0)
            instance_handler.terminate_bluestacks()
            QThread.msleep(constants.PROCESS_TERMINATION_WAIT_MS)
            results = ad_settings.remove(config_path, progress=lambda m: progress(m, -1))
            return results[-1] if results else "BlueStacks ad settings restored."

        w._run_async(job, "Restoring BlueStacks ad settings...")

    def handle_ads_lock(self, checked: bool) -> None:
        """Pin/unpin bluestacks.conf read-only so the switches can't be reverted."""
        w = self._window
        config_path = self._config_path()
        if not config_path:
            return
        try:
            if checked:
                ad_settings.lock(config_path)
            else:
                ad_settings.unlock(config_path)
        except OSError as exc:
            QMessageBox.warning(w, "Could not change the config lock", str(exc))
        finally:
            self.refresh_statuses()

    # --- per instance: guest hosts block -------------------------------------

    def _selected_instance(self):
        w = self._window
        uid = w.privacy_page.selected_instance_id()
        if not uid or uid not in w.instance_data:
            QMessageBox.information(w, "No instance selected",
                                    "Select an instance on the Privacy tab first.")
            return None, None
        return uid, w.instance_data[uid]

    def handle_block(self) -> None:
        w = self._window
        uid, instance = self._selected_instance()
        if instance is None:
            return
        # Editing the guest hosts file modifies the system image. On an unpatched
        # engine BlueStacks detects that and shuts the instance down mid-session
        # ("illegally tampered") -- root isn't required to trip it, any change is.
        if instance.get("patch_mode") and w._engine_state() != "patched":
            QMessageBox.warning(
                w, "Patch the engine first",
                "Blocking trackers edits the guest system image, and BlueStacks "
                "shuts down an instance whose system image was modified unless "
                "the engine is patched. Patch it from the Dashboard, then try "
                "again.\n\nTo stop BlueStacks' own ads you don't need this at "
                "all. Use \"Turn off ads & telemetry\" above.")
            return
        if not w._confirm(
                "Block in-guest trackers",
                "Block tracker domains inside %s?" % uid,
                "<p>Null-routes ad, tracker, and analytics domains in the guest "
                "hosts file while the instance is shut down (all BlueStacks "
                "processes close first). Emulator-only, and reversible.</p>"
                "<p>This reaches apps running <b>inside</b> the emulator. It does "
                "not affect BlueStacks' own ads, which are served by the Windows "
                "player and never pass through the guest.</p>"
                "<p>One master Root.vhd is shared by every instance of this "
                "Android version, so this applies to all of them.</p>"):
            return
        data_path = instance["data_path"]

        def job(progress):
            progress("Closing BlueStacks...", 0)
            instance_handler.terminate_bluestacks()
            QThread.msleep(constants.PROCESS_TERMINATION_WAIT_MS)
            results = telemetry_block.apply(data_path, progress=lambda m: progress(m, -1))
            return results[-1] if results else "Trackers blocked."

        w._run_async(job, "Blocking trackers in %s..." % uid)

    def handle_unblock(self) -> None:
        w = self._window
        uid, instance = self._selected_instance()
        if instance is None:
            return
        if not w._confirm(
                "Remove tracker block",
                "Restore the original guest hosts file for %s?" % uid,
                "<p>Removes the in-guest tracker block, while the instance is "
                "shut down (all BlueStacks processes close first).</p>"):
            return
        data_path = instance["data_path"]

        def job(progress):
            progress("Closing BlueStacks...", 0)
            instance_handler.terminate_bluestacks()
            QThread.msleep(constants.PROCESS_TERMINATION_WAIT_MS)
            results = telemetry_block.remove(data_path, progress=lambda m: progress(m, -1))
            return results[-1] if results else "Block removed."

        w._run_async(job, "Removing the block from %s..." % uid)
