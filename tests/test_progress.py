import os
import re

from views.progress import step_percent, OperationProgressBar, StepReporter

VIEWS = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "views")


def test_step_percent_midpoint():
    assert step_percent(1, 4) == 25


def test_step_percent_final_step_is_100():
    assert step_percent(4, 4) == 100


def test_step_percent_zero_total_is_zero():
    assert step_percent(1, 0) == 0


def test_progress_bar_starts_with_ready_text_and_hidden_bar(qtbot):
    bar = OperationProgressBar()
    qtbot.addWidget(bar)
    assert bar._label.text() == "Ready"
    assert bar._bar.isVisible() is False


def test_start_shows_bar_and_sets_text(qtbot):
    bar = OperationProgressBar()
    qtbot.addWidget(bar)
    bar.start("Working...")
    assert bar._bar.isVisible() is True
    assert bar._label.text() == "Working..."
    assert bar._bar.minimum() == 0 and bar._bar.maximum() == 0


def test_set_progress_determinate(qtbot):
    bar = OperationProgressBar()
    qtbot.addWidget(bar)
    bar.set_progress("Step 2", 50)
    assert bar._bar.maximum() == 100
    assert bar._bar.value() == 50


def test_set_progress_indeterminate(qtbot):
    bar = OperationProgressBar()
    qtbot.addWidget(bar)
    bar.set_progress("Working...", None)
    assert bar._bar.maximum() == 0
    assert bar._bar.minimum() == 0


def test_finish_hides_bar_and_sets_summary_text(qtbot):
    bar = OperationProgressBar()
    qtbot.addWidget(bar)
    bar.start("Working...")
    bar.finish("Done. 3 instances updated.")
    assert bar._bar.isVisible() is False
    assert bar._label.text() == "Done. 3 instances updated."


# --- StepReporter -----------------------------------------------------------
# The backends report what they are doing, not how far along they are, so every
# long operation used to pass -1 and the bar sat on an indeterminate marquee
# that looked identical at 5% and 95%.

def test_step_reporter_advances_with_each_message():
    seen = []
    report = StepReporter(lambda msg, pct: seen.append((msg, pct)), expected=4)
    for msg in ("one", "two", "three"):
        report(msg)
    assert [m for m, _p in seen] == ["one", "two", "three"]
    percents = [p for _m, p in seen]
    assert percents == sorted(percents), "must never go backwards"
    assert percents[0] < percents[-1], "must actually advance"


def test_step_reporter_never_reaches_100_before_the_work_ends():
    """An operation that talks more than expected must not look finished."""
    seen = []
    report = StepReporter(lambda _m, pct: seen.append(pct), expected=3)
    for _ in range(20):          # far more messages than expected
        report("chatter")
    assert max(seen) <= 95


def test_step_reporter_survives_a_zero_expected_count():
    seen = []
    StepReporter(lambda _m, pct: seen.append(pct), expected=0)("only message")
    assert seen == [95]          # clamped, not a divide-by-zero


def test_no_operation_reports_an_indeterminate_bar():
    """Source guard: a handler passing -1 gives the user a spinner with no
    number, which is the complaint this replaced. Percentages are approximate,
    but a moving estimate beats an endless marquee."""
    offenders = []
    pattern = re.compile(r"progress\([^)]*,\s*-1\s*\)")
    for name in sorted(os.listdir(VIEWS)):
        if not name.endswith(".py"):
            continue
        path = os.path.join(VIEWS, name)
        with open(path, encoding="utf-8") as f:
            for lineno, line in enumerate(f, 1):
                if pattern.search(line):
                    offenders.append("%s:%d %s" % (name, lineno, line.strip()))
    assert not offenders, "these still show an indeterminate bar:\n" + "\n".join(offenders)
