"""Retry helper for Windows sharing-violation races.

Windows raises ``PermissionError`` (not a silent success, unlike POSIX) when a
file operation collides with another process briefly holding a handle open --
AV, the Search indexer, or BlueStacks itself. This is a real, expected
transient state, not a hard failure, so operations that can hit it (an
``os.replace`` over a config file another process might glance at, a VHD
attach right after killing BlueStacks) should retry with backoff rather than
fail on the first collision.
"""
from __future__ import annotations

import logging
import time
from typing import Callable, TypeVar

logger = logging.getLogger(__name__)

T = TypeVar("T")


def retry_on_sharing_violation(fn: Callable[[], T], *, attempts: int = 5,
                               base_delay: float = 0.1, label: str = "operation") -> T:
    """Call ``fn()``, retrying on ``PermissionError`` with linear backoff.

    Raises the last ``PermissionError`` if every attempt fails. Any other
    exception from ``fn`` propagates immediately, unretried -- this only
    absorbs the specific "someone else briefly has a handle open" case.
    """
    last_exc: PermissionError | None = None
    for attempt in range(1, attempts + 1):
        try:
            return fn()
        except PermissionError as exc:
            last_exc = exc
            if attempt < attempts:
                delay = base_delay * attempt
                logger.debug("%s: sharing violation (attempt %d/%d), retrying in %.2fs",
                            label, attempt, attempts, delay)
                time.sleep(delay)
    raise last_exc
