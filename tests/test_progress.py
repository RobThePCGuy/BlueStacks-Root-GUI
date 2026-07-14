from views.progress import step_percent, OperationProgressBar


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
