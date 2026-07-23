import pytest

import win_retry


@pytest.fixture(autouse=True)
def _no_real_sleep(monkeypatch):
    monkeypatch.setattr(win_retry.time, "sleep", lambda s: None)


def test_succeeds_first_try_without_retrying():
    calls = []

    def fn():
        calls.append(1)
        return "ok"

    assert win_retry.retry_on_sharing_violation(fn) == "ok"
    assert len(calls) == 1


def test_recovers_after_transient_permission_errors():
    attempts = []

    def fn():
        attempts.append(1)
        if len(attempts) < 3:
            raise PermissionError("sharing violation")
        return "recovered"

    assert win_retry.retry_on_sharing_violation(fn, attempts=5) == "recovered"
    assert len(attempts) == 3


def test_raises_last_error_after_exhausting_attempts():
    attempts = []

    def fn():
        attempts.append(1)
        raise PermissionError("still locked")

    with pytest.raises(PermissionError, match="still locked"):
        win_retry.retry_on_sharing_violation(fn, attempts=3)
    assert len(attempts) == 3


def test_does_not_retry_non_permission_errors():
    attempts = []

    def fn():
        attempts.append(1)
        raise ValueError("not a sharing violation")

    with pytest.raises(ValueError):
        win_retry.retry_on_sharing_violation(fn, attempts=5)
    assert len(attempts) == 1
