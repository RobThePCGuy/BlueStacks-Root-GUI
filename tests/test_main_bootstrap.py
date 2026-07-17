import importlib


def test_main_module_imports_without_running_gui():
    main = importlib.import_module("main")
    assert main.LOG_PATH.endswith("BlueStacksRootGUI.log")
    assert hasattr(main, "MainWindow")
