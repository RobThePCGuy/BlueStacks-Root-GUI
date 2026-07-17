"""Pure decision logic for patch-gating and update-revert detection.

Kept free of Qt so it can be unit-tested without a QApplication.
"""
from __future__ import annotations


def blocked_for_root_toggle(selected: dict, engine_state: str) -> list[str]:
    """Names of selected instances that must not have root ENABLED yet.

    An instance is blocked only when the user is turning root ON (it is
    currently off), it needs the engine patch (`patch_mode` True), and the
    engine is in a known-not-patched state ("unpatched" or "partial").

    Turning root OFF is never blocked -- disabling root does not depend on
    the engine patch, so a user must always be able to clear a stale root
    (e.g. after an auto-update reverts the patch). An "unknown" engine
    state (unrecognized build we can't read) blocks nothing either, rather
    than trapping the user behind a Dashboard button that is itself
    disabled for "unknown". ``selected`` maps unique_id -> instance dict
    (needs at least ``patch_mode`` and ``root_enabled``).
    """
    if engine_state not in ("unpatched", "partial"):
        return []
    return [uid for uid, data in selected.items()
            if data.get("patch_mode") and not data.get("root_enabled")]


def update_was_reverted(previous_state: str | None, current_state: str,
                        any_rooted: bool) -> bool:
    """True when the engine flips from patched to not-patched while a
    rooted instance still exists -- the signature of an auto-update
    silently undoing the engine patch."""
    return previous_state == "patched" and current_state != "patched" and any_rooted
