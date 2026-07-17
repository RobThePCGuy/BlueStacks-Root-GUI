# The empty-on-purpose part: this file's presence at the repo root makes pytest
# insert the repo root onto sys.path (prepend import mode), so tests can
# `import constants`, `import adb_handler`, and `from views import ...` the same
# way main.py does, without a src/ layout or package install.

import pytest


@pytest.fixture(autouse=True)
def _no_real_bluestacks_detection(monkeypatch):
    """Make the live registry probe a no-op for every test.

    MainWindow.__init__ schedules initialize_paths_and_instances() via
    QTimer.singleShot(0, ...). It never runs during a test's synchronous body,
    but pytest-qt spins the Qt event loop at teardown, which fires it. On a
    machine WITHOUT BlueStacks that init returns early (no installations found);
    on a dev machine WITH BlueStacks it proceeds to read the real engine state --
    draining tests' monkeypatched finite _engine_state iterators (StopIteration)
    and byte-scanning real binaries. That made the suite pass or fail depending
    on the host. Stubbing detection to "nothing installed" makes the stray init
    harmless everywhere; tests that need installations set them on the window
    directly after construction.
    """
    monkeypatch.setattr(
        "registry_handler.get_all_bluestacks_installations",
        lambda: [],
        raising=True,
    )
