from types import SimpleNamespace

from adb_handler import list_running_instances


def _fake_runner(responses):
    calls = []

    def runner(cmd):
        calls.append(cmd)
        key = cmd[-1] if len(cmd) >= 2 and cmd[1] == "connect" else None
        stdout = responses.get(key, "")
        return SimpleNamespace(stdout=stdout, stderr="", returncode=0)

    runner.calls = calls
    return runner


def test_list_running_instances_returns_connected_ports(tmp_path):
    config_path = tmp_path / "bluestacks.conf"
    config_path.write_text(
        'bst.instance.Pie64.status.adb_port="5555"\n'
        'bst.instance.Idle.status.adb_port="5565"\n'
    )
    responses = {
        "127.0.0.1:5555": "connected to 127.0.0.1:5555",
        "127.0.0.1:5565": "failed to connect to 127.0.0.1:5565",
    }
    runner = _fake_runner(responses)
    instances = [
        ("Pie64 (Normal)", str(config_path), "Pie64"),
        ("Idle (Normal)", str(config_path), "Idle"),
    ]

    result = list_running_instances("HD-Adb.exe", instances, runner=runner)

    assert result == {"Pie64 (Normal)": 5555}


def test_list_running_instances_skips_instances_with_no_recorded_port(tmp_path):
    config_path = tmp_path / "bluestacks.conf"
    config_path.write_text("")  # no adb_port keys at all
    runner = _fake_runner({})
    instances = [("NeverBooted (Normal)", str(config_path), "NeverBooted")]

    result = list_running_instances("HD-Adb.exe", instances, runner=runner)

    assert result == {}
    assert runner.calls == []  # never attempted an adb connect
