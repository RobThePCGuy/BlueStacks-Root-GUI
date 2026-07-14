from views.main_window import MainWindow


def test_on_async_progress_maps_negative_pct_to_indeterminate(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)
    window._on_async_progress("Working...", -1)
    assert window.progress_bar._bar.minimum() == 0
    assert window.progress_bar._bar.maximum() == 0


def test_on_async_progress_sets_determinate_value(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)
    window._on_async_progress("Step 2", 50)
    assert window.progress_bar._bar.maximum() == 100
    assert window.progress_bar._bar.value() == 50
