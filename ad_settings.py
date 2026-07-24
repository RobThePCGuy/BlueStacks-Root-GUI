"""Turn BlueStacks' own ad / promo / telemetry switches off in ``bluestacks.conf``.

Why this exists (and why the guest hosts block isn't enough)
-----------------------------------------------------------
BlueStacks' own advertising is served by **HD-Player.exe on Windows**, not by the
Android guest.  A live capture settled it: with the guest **completely powered
off**, HD-Player still held open connections to googlesyndication, inmobi,
rubiconproject, adnxs and a dozen RTB exchanges.  A guest ``/system/etc/hosts``
file cannot reach any of that -- there is no guest involved.  Measured on
5.22.250.1015, applying the guest block changed the player's ad endpoints not at
all (40 before, 40+ after).

BlueStacks ships explicit switches for this in its own config.  Turning them off
is dramatically more effective *and* less invasive than editing the guest system
image -- same capture rig, same instance:

===========================  ==================  ==================
measurement                  guest hosts block   these switches
===========================  ==================  ==================
ad/tracker endpoints         40  (no change)     **0**
unique remote IPs            151 -> 133          151 -> **14**
===========================  ==================  ==================

What survived was purely Play/GMS/Firebase infrastructure, and the emulator
stayed healthy.  ``bst.enable_programmatic_ads="0"`` is the load-bearing switch.

Surviving version updates
-------------------------
Keys get renamed, added and removed between BlueStacks builds, and a hard-coded
list silently rots.  So this module **discovers** the keys in whatever config is
actually present, by matching concept patterns (``programmatic_ads``,
``send_*_stats``, ``auto_upload``, ...) rather than fixed names.  A future build
that adds ``bst.feature.send_new_ad_stats`` is handled with no code change.

Three gates keep that safe -- a rename can never make us flip something harmful:

1. the key must match a curated concept pattern (:data:`SWITCH_PATTERNS`),
2. it must NOT match an exclusion (:data:`NEVER_TOUCH`) -- rooting, ADB, the
   ``*_preference`` keys that control whether BlueStacks' own settings toggle is
   *visible*, and anything with inverted ``disable``/``skip`` semantics,
3. its current value must be exactly ``"0"`` or ``"1"``.  That alone protects
   every id/string/number key, e.g. ``android_google_ad_id``.

We only ever write ``"0"``, so gate 3 plus the ``disable``/``skip`` exclusion
means the semantics are always "turn this feature off".

Reversibility and drift
-----------------------
``apply`` records each key's original value in a sidecar next to the config, so
``remove`` restores exactly what was there -- including keys that were already
``"0"``.

BlueStacks **selectively rewrites** keys when it starts, and the split observed
on 5.22.250.1015 is informative: the ``bst.enable_*`` keys and
``feature.show_gp_ads`` **stick**, while most ``bst.feature.*`` keys are put back
to ``"1"`` from the service's own defaults (``nowbux``, the ``nowgg_*`` pair, and
four ``send_*_stats`` beacons all came back).  The ads stayed gone anyway,
because the load-bearing ``enable_programmatic_ads`` is one of the survivors --
but the *telemetry beacons* did get re-enabled, which is exactly what
:func:`lock` is for.  :func:`status` reports the drift honestly so the UI can
offer a re-apply, and the read-only pin is offered rather than forced because a
locked config also stops BlueStacks editing its own settings.

The config is BlueStacks' single **global** file -- these switches apply to every
instance, not one.  Write them with BlueStacks shut down; it rewrites the file on
exit.
"""
from __future__ import annotations

import datetime
import json
import logging
import os
import re

import config_handler
import root_persistence

logger = logging.getLogger(__name__)

_STATE_NAME = ".bsrgui_ad_settings.json"

#: Concept patterns for switches worth turning off.  Matched case-insensitively
#: against the whole key.  Deliberately about *concepts* ("programmatic ads",
#: "stats upload") rather than exact names, so a renamed or newly added key in a
#: later BlueStacks build is still recognised.
SWITCH_PATTERNS = (
    r"programmatic_ads",        # the player's ad unit (the load-bearing one)
    r"show_gp_ads",             # ads on the game-player surface
    r"android_ads_stats",
    r"split_ad_enabled",
    r"enable_ads",
    r"show_ads",
    r"boot_banner",             # promo banner on instance start
    r"nowbux",                  # nowbux rewards promo
    r"bluestacksx",             # BlueStacksX promo surface
    r"nowgg_login_popup",
    r"nowgg_cloud_upload",
    r"auto_upload",             # recording / "moments" cloud uploads
    r"send_\w*stats",           # every stats-beacon key
    r"send_offer",
)

#: Hard exclusions, checked before :data:`SWITCH_PATTERNS`.  These protect keys
#: that merely *look* related, or where writing ``"0"`` would be backwards.
NEVER_TOUCH = (
    r"_preference$",   # controls whether BlueStacks' own ad toggle is VISIBLE in
                       # Settings -- turning it off hides the user's control
    r"root",           # rooting keys belong to root_persistence, never here
    r"adb",            # "adb" contains "ad"; bst.enable_adb_access is not an ad key
    r"disable",        # inverted semantics -- writing "0" would turn a feature ON
    r"skip",           # e.g. skipNowggLogin: "1" is the desirable value
)

#: The value written to every managed key.
OFF = "0"

_KEY_RE = re.compile(r"^\s*([\w.]+)\s*=\s*\"?([^\"\r\n]*)\"?\s*$")
_SWITCH_RE = re.compile("|".join(SWITCH_PATTERNS), re.IGNORECASE)
_NEVER_RE = re.compile("|".join(NEVER_TOUCH), re.IGNORECASE)


def is_managed(key: str, value: str) -> bool:
    """Whether this config key is one we turn off.

    All three gates, in order: not excluded, matches a concept pattern, and is a
    boolean-valued switch.  ``value`` matters -- it is what keeps id/string keys
    such as ``android_google_ad_id`` out of scope no matter what they are named.
    """
    if _NEVER_RE.search(key):
        return False
    if not _SWITCH_RE.search(key):
        return False
    return value.strip() in ("0", "1")


def _parse(text: str) -> dict[str, str]:
    """All ``key -> value`` pairs in a bluestacks.conf."""
    found: dict[str, str] = {}
    for line in text.splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        m = _KEY_RE.match(line)
        if m:
            found[m.group(1)] = m.group(2)
    return found


def _read(config_path: str) -> str:
    with open(config_path, encoding="utf-8") as f:
        return f.read()


def discover(config_path: str) -> dict[str, str]:
    """The managed switches present in this config, mapped to current values.

    Discovery runs against the real file every time, so a BlueStacks update that
    adds or renames switches is picked up without a code change.
    """
    return {k: v for k, v in _parse(_read(config_path)).items() if is_managed(k, v)}


def _state_path(config_path: str) -> str:
    return os.path.join(os.path.dirname(config_path), _STATE_NAME)


def status(config_path: str) -> dict | None:
    """Current state, or ``None`` if these switches have not been turned off.

    On top of the stored sidecar this re-reads the live config and reports:

    ``off``
        managed keys currently sitting at ``"0"``.
    ``reverted``
        keys we set that BlueStacks has since put back -- expected for a couple
        of them on every start, and the reason the UI offers a re-apply.
    ``unmanaged``
        switches present now that we have no original recorded for, i.e. keys a
        BlueStacks update introduced since. Re-applying adopts them.
    """
    try:
        with open(_state_path(config_path), encoding="utf-8") as f:
            state = json.load(f)
    except (OSError, ValueError):
        return None

    try:
        live = discover(config_path)
    except OSError:
        return state

    originals = state.get("originals", {})
    state = dict(state)
    state["off"] = sorted(k for k, v in live.items() if v.strip() == OFF)
    state["reverted"] = sorted(k for k, v in live.items()
                               if k in originals and v.strip() != OFF)
    state["unmanaged"] = sorted(k for k in live if k not in originals)
    state["locked"] = root_persistence.is_locked(config_path)
    return state


def _write_state(config_path: str, originals: dict[str, str] | None) -> None:
    path = _state_path(config_path)
    if originals is None:
        try:
            os.unlink(path)
        except OSError:
            pass
        return
    payload = {
        "ads_disabled": True,
        "keys": len(originals),
        "originals": originals,
        "applied_at": datetime.datetime.now().replace(microsecond=0).isoformat(),
    }
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)


def apply(config_path: str, progress=None) -> list[str]:
    """Turn every discovered ad/telemetry switch off.

    Idempotent, and safe to re-run after BlueStacks reverts a key.  Originals are
    recorded on the first apply and preserved across re-applies, so
    :func:`remove` always restores the true pre-BSRGUI values; keys introduced by
    a later BlueStacks build are adopted (with their current value recorded) on
    the next apply.  BlueStacks should be shut down -- it rewrites this file on
    exit.
    """
    def _p(msg: str) -> None:
        logger.info(msg)
        if progress:
            progress(msg)

    if not os.path.isfile(config_path):
        raise FileNotFoundError(config_path)

    switches = discover(config_path)
    if not switches:
        return ["No ad/telemetry switches found in bluestacks.conf "
                "(BlueStacks may have renamed them in this build)."]

    prior = (status(config_path) or {}).get("originals", {})
    originals = dict(prior)
    for key, value in switches.items():
        originals.setdefault(key, value)

    _p("Turning off %d BlueStacks ad/telemetry switches..." % len(switches))
    changed = 0
    for key in sorted(switches):
        if config_handler.modify_config_file(config_path, key, OFF):
            changed += 1

    _write_state(config_path, originals)
    _p("Verifying...")
    still_on = sorted(k for k, v in discover(config_path).items() if v.strip() != OFF)
    if still_on:
        # Not a failure: the write is verified below by re-reading, so this means
        # something outside this process is holding values on.
        logger.warning("Switches still on after write: %s", still_on)
        return ["Turned off %d of %d BlueStacks ad/telemetry switches (%d still on: %s)."
                % (len(switches) - len(still_on), len(switches), len(still_on),
                   ", ".join(still_on))]
    return ["Turned off %d BlueStacks ad/telemetry switches (%d newly changed)."
            % (len(switches), changed)]


def remove(config_path: str, progress=None) -> list[str]:
    """Restore every switch to the value it had before :func:`apply`."""
    def _p(msg: str) -> None:
        logger.info(msg)
        if progress:
            progress(msg)

    state = status(config_path)
    if not state:
        return ["BlueStacks ad/telemetry switches were not changed by this tool."]

    originals = state.get("originals", {})
    if not originals:
        _write_state(config_path, None)
        return ["Nothing recorded to restore."]

    _p("Restoring %d BlueStacks ad/telemetry switches..." % len(originals))
    restored = 0
    for key in sorted(originals):
        if config_handler.modify_config_file(config_path, key, originals[key]):
            restored += 1

    _write_state(config_path, None)
    return ["Restored %d BlueStacks ad/telemetry switches (%d changed back)."
            % (len(originals), restored)]


def lock(config_path: str) -> bool:
    """Pin the config read-only so BlueStacks cannot revert the switches.

    Optional.  The load-bearing ``enable_programmatic_ads`` key survives without
    it, and a locked config stops BlueStacks editing its own settings, so this is
    offered rather than applied automatically.  Shares the one read-only bit with
    the root-persistence lock -- see :mod:`root_persistence`.
    """
    return root_persistence.lock(config_path)


def unlock(config_path: str) -> bool:
    """Release the read-only pin taken by :func:`lock`."""
    return root_persistence.unlock(config_path)
