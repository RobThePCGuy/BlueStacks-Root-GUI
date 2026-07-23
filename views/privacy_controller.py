"""Privacy tab controller: owns the handler logic for blocking/unblocking
ad and telemetry domains in an instance's guest hosts file.

Extraction of responsibility out of ``MainWindow``, same pattern as
``MagiskController`` -- constructed with the owning ``MainWindow`` and reaches
back into it for the confirm dialog, the async job runner, and the Privacy
page widget.
"""
from __future__ import annotations

from PyQt5.QtCore import QThread
from PyQt5.QtWidgets import QMessageBox

import constants
import instance_handler
import telemetry_block


class PrivacyController:
    def __init__(self, window):
        self._window = window

    def refresh_statuses(self) -> None:
        """Fill the Privacy tab with each instance's current telemetry-block state."""
        w = self._window
        statuses = {uid: telemetry_block.status(data["data_path"])
                    for uid, data in w.instance_data.items()}
        w.privacy_page.set_instances(statuses)

    def handle_block(self) -> None:
        w = self._window
        uid = w.privacy_page.selected_instance_id()
        if not uid or uid not in w.instance_data:
            QMessageBox.information(w, "No instance selected",
                                    "Select an instance on the Privacy tab first.")
            return
        if not w._confirm(
                "Block ads & telemetry",
                "Block ad/telemetry domains in %s?" % uid,
                "<p>Null-routes ad, tracker, and analytics domains in the guest "
                "hosts file while the instance is shut down (all BlueStacks "
                "processes close first). Emulator-only, and reversible.</p>"):
            return
        data_path = w.instance_data[uid]["data_path"]

        def job(progress):
            progress("Closing BlueStacks...", 0)
            instance_handler.terminate_bluestacks()
            QThread.msleep(constants.PROCESS_TERMINATION_WAIT_MS)
            results = telemetry_block.apply(data_path, progress=lambda m: progress(m, -1))
            return results[-1] if results else "Telemetry blocked."

        w._run_async(job, "Blocking ads/telemetry in %s..." % uid)

    def handle_unblock(self) -> None:
        w = self._window
        uid = w.privacy_page.selected_instance_id()
        if not uid or uid not in w.instance_data:
            QMessageBox.information(w, "No instance selected",
                                    "Select an instance on the Privacy tab first.")
            return
        if not w._confirm(
                "Remove telemetry block",
                "Restore the original guest hosts file for %s?" % uid,
                "<p>Removes the ad/telemetry block, while the instance is shut "
                "down (all BlueStacks processes close first).</p>"):
            return
        data_path = w.instance_data[uid]["data_path"]

        def job(progress):
            progress("Closing BlueStacks...", 0)
            instance_handler.terminate_bluestacks()
            QThread.msleep(constants.PROCESS_TERMINATION_WAIT_MS)
            results = telemetry_block.remove(data_path, progress=lambda m: progress(m, -1))
            return results[-1] if results else "Block removed."

        w._run_async(job, "Removing the block from %s..." % uid)
