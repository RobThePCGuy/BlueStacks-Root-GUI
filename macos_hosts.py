"""In-guest tracker blocking for BlueStacks Air -- the macOS ``telemetry_block``.

``telemetry_block`` does this on Windows by attaching ``Root.vhd`` as a disk and
driving the bundled Cygwin ``debugfs`` over it. None of that exists here: Air has
no VHD, no disk-attach step, and its system tree lives in a qcow2 inside the app
bundle. The *edit* is the same idea, though -- rewrite ``/system/etc/hosts`` in
the guest system image offline -- so this module reuses ``macos_root``'s image
session and keeps the block text itself shared with ``telemetry_block`` rather
than maintaining a second domain list that could drift.

Scope, and why it differs from Windows
--------------------------------------
This reaches apps running *inside* the emulator only. BlueStacks' own ads are
served by the host player, so ``ad_settings`` handles those; that part is
already cross-platform because it edits ``bluestacks.conf``.

Like rooting on Air, the block is **install-wide**: every instance boots the one
shared system image, so there is no per-instance hosts file. (Windows has the
same property for a different reason -- ``Root.vhd`` is shared across all
instances of an Android version -- so this is a difference of degree, not kind.)

Interaction with root
---------------------
Both features edit the same image, and either can be applied first, so state is
kept in ``macos_root``'s single shared record rather than a file of its own.
That is not tidiness -- it is required. The record is validated by fingerprinting
the image, and *any* edit rewrites the image; two separately-fingerprinted files
would therefore invalidate each other, so blocking trackers on a rooted install
would make it read as un-rooted (and removing the block would then "restore" over
the root). One record, one fingerprint, re-stamped by whichever edit ran last.
"""
from __future__ import annotations

import logging
import os

import macos_locator
import macos_root
import telemetry_block

logger = logging.getLogger(__name__)

# Path inside the image; the guest bind-mounts /android/system as /system.
HOSTS_IMAGE_PATH = "/android/system/etc/hosts"
HOSTS_GUEST_PATH = "/system/etc/hosts"

# Android ships this exact file; used when the guest has no hosts file at all so
# the result is still a valid hosts file rather than only the block.
DEFAULT_HOSTS = "127.0.0.1       localhost\n::1             ip6-localhost\n"


def blocked_hosts() -> tuple[str, ...]:
    """The domain list, shared with the Windows implementation."""
    return telemetry_block.blocked_hosts()


def status(app_path: str, data_dir: str = macos_locator.DATA_DIR) -> dict | None:
    """Recorded block state, or None when no block is in place.

    Shaped like ``telemetry_block.status`` so the Privacy page renders both
    without caring which backend produced it.
    """
    return macos_root.read_modstate(app_path, data_dir).get("hosts")


def apply(app_path: str, progress=None,
          data_dir: str = macos_locator.DATA_DIR) -> list[str]:
    """Null-route the tracker domains in the guest hosts file."""
    def _step(msg: str) -> None:
        logger.info(msg)
        if progress:
            progress(msg)

    results: list[str] = []
    image = macos_locator.root_image_path(app_path)
    state = macos_root.read_modstate(app_path, data_dir)
    active = macos_root.applied_modifications(state)
    # Shared with rooting: whichever edit lands first takes the pristine copy.
    macos_root.ensure_backup(image, data_dir, image_is_pristine=not active,
                             step=_step)

    with macos_root.open_image(app_path, progress, results=results) as img:
        _step("Editing the guest hosts file...")
        current = img.read_file(HOSTS_IMAGE_PATH)
        if current is None:
            logger.info("Guest has no %s; creating one.", HOSTS_GUEST_PATH)
            current = DEFAULT_HOSTS
        # Strip any previous block first so re-applying updates the domain list
        # instead of appending a second copy.
        base = telemetry_block._strip_block(current)
        img.write_file(HOSTS_IMAGE_PATH, base + telemetry_block._block_text())
        results.append("blocked %d hosts in %s"
                       % (len(blocked_hosts()), HOSTS_GUEST_PATH))

    # Re-stamps root's entry against the rewritten image too, so blocking
    # trackers cannot make an already-rooted install read as un-rooted.
    state["hosts"] = {"applied": True, "hosts": len(blocked_hosts()),
                      "when": None, "path": HOSTS_GUEST_PATH}
    macos_root.write_modstate(app_path, data_dir, state)
    _step("Done. Restart BlueStacks for the change to take effect.")
    return results


def remove(app_path: str, progress=None,
           data_dir: str = macos_locator.DATA_DIR) -> list[str]:
    """Remove the block, leaving any other hosts entries untouched."""
    def _step(msg: str) -> None:
        logger.info(msg)
        if progress:
            progress(msg)

    results: list[str] = []
    image = macos_locator.root_image_path(app_path)
    state = macos_root.read_modstate(app_path, data_dir)
    active = macos_root.applied_modifications(state)

    # Last edit standing: restore the untouched image rather than editing it,
    # which also repairs the app bundle's code-signature seal. If root is still
    # applied this must NOT run -- restoring the pre-root image would silently
    # un-root the user while claiming only to have removed a hosts block.
    if not (active - {"hosts"}) and os.path.isfile(macos_root.backup_path(data_dir)):
        results += macos_root.restore_pristine(image, data_dir, _step)
        macos_root.write_modstate(app_path, data_dir, {})
        _step("Block removed. Restart BlueStacks for the change to take effect.")
        return results

    with macos_root.open_image(app_path, progress, results=results) as img:
        _step("Restoring the guest hosts file...")
        current = img.read_file(HOSTS_IMAGE_PATH)
        if current is None:
            results.append("no %s in the guest; nothing to undo" % HOSTS_GUEST_PATH)
        else:
            img.write_file(HOSTS_IMAGE_PATH, telemetry_block._strip_block(current))
            results.append("removed the block from %s" % HOSTS_GUEST_PATH)

    state["hosts"] = None
    macos_root.write_modstate(app_path, data_dir, state)
    _step("Done. Restart BlueStacks for the change to take effect.")
    return results
