"""In-guest hosts blocking on Air, and how it shares an image with rooting.

Both features edit the same ``Root.qcow2``, so the interesting cases are not
the individual edits (those mirror ``telemetry_block``, which has its own
tests) but the interaction: which one takes the pristine backup, and which one
is allowed to restore it. Getting that wrong either strands a modified image
or silently reverts the *other* feature.
"""
from __future__ import annotations

import os

import pytest

import macos_hosts
import macos_root
import platform_support
import telemetry_block


@pytest.fixture
def install(tmp_path, monkeypatch):
    """An Air install with a stub image, and the image edit stubbed out.

    ``open_image`` is replaced by a fake session backed by a dict, so these
    tests exercise the decision logic without a 1.7 GB qcow2 round-trip.
    """
    app = tmp_path / "BlueStacks.app"
    (app / "Contents" / "img").mkdir(parents=True)
    image = app / "Contents" / "img" / "Root.qcow2"
    image.write_bytes(b"pristine-image")
    data = tmp_path / "data"
    data.mkdir()

    files = {macos_hosts.HOSTS_IMAGE_PATH: "127.0.0.1       localhost\n"}

    class FakeSession:
        workdir = str(tmp_path)

        def read_file(self, path):
            return files.get(path)

        def write_file(self, path, content, mode=0o100644):
            files[path] = content

        def run(self, commands):
            for line in commands.splitlines():
                if line.startswith("rm "):
                    files.pop(line[3:].strip(), None)
            return ""

    import contextlib

    @contextlib.contextmanager
    def fake_open_image(app_path, progress=None, *, results=None):
        yield FakeSession()
        # Any edit rewrites the image, so its bytes change -- which is what
        # invalidates the fingerprints the state files are checked against.
        image.write_bytes(image.read_bytes() + b"+edit")

    monkeypatch.setattr(macos_root, "open_image", fake_open_image)
    monkeypatch.setattr(platform_support, "IS_MACOS", True)
    return str(app), str(data), image, files


def test_apply_adds_the_block_and_keeps_existing_entries(install):
    app, data, _, files = install

    macos_hosts.apply(app, data_dir=data)

    hosts = files[macos_hosts.HOSTS_IMAGE_PATH]
    assert "127.0.0.1       localhost" in hosts, "must not clobber the real file"
    assert "0.0.0.0 doubleclick.net" in hosts
    assert macos_hosts.status(app, data)["hosts"] == len(macos_hosts.blocked_hosts())


def test_reapplying_does_not_stack_duplicate_blocks(install):
    app, data, _, files = install

    macos_hosts.apply(app, data_dir=data)
    macos_hosts.apply(app, data_dir=data)

    hosts = files[macos_hosts.HOSTS_IMAGE_PATH]
    assert hosts.count("0.0.0.0 doubleclick.net") == 1
    assert telemetry_block.has_block(hosts)


def test_apply_creates_a_hosts_file_when_the_guest_has_none(install):
    app, data, _, files = install
    del files[macos_hosts.HOSTS_IMAGE_PATH]

    macos_hosts.apply(app, data_dir=data)

    hosts = files[macos_hosts.HOSTS_IMAGE_PATH]
    assert "localhost" in hosts, "a hosts file with only the block is malformed"
    assert "0.0.0.0 doubleclick.net" in hosts


def test_first_edit_takes_the_pristine_backup(install):
    app, data, image, _ = install
    original = image.read_bytes()

    macos_hosts.apply(app, data_dir=data)

    backup = macos_root.backup_path(data)
    assert os.path.isfile(backup)
    assert open(backup, "rb").read() == original


def test_removing_the_only_edit_restores_the_untouched_image(install):
    """Byte-for-byte, which is what repairs the bundle's signature seal."""
    app, data, image, _ = install
    original = image.read_bytes()

    macos_hosts.apply(app, data_dir=data)
    assert image.read_bytes() != original       # the edit really changed it
    macos_hosts.remove(app, data_dir=data)

    assert image.read_bytes() == original
    assert not os.path.isfile(macos_root.backup_path(data))
    assert macos_hosts.status(app, data) is None


def test_blocking_trackers_does_not_forget_that_root_is_applied(install):
    """Regression: the block edit must not invalidate root's recorded state.

    Both are recorded against a fingerprint of the same image, so applying one
    rewrites the image the other was stamped against. Caught live -- blocking
    trackers on a rooted install reported it as un-rooted.
    """
    app, data, image, _ = install
    macos_root.write_modstate(app, data, {"root": True})

    macos_hosts.apply(app, data_dir=data)

    assert macos_root.image_root_state(app, data) is True
    assert macos_hosts.status(app, data) is not None


def test_removing_the_block_while_rooted_does_not_restore_over_root(install):
    """Restoring the pristine image here would silently un-root the user."""
    app, data, image, files = install
    macos_root.write_modstate(app, data, {"root": True})
    macos_hosts.apply(app, data_dir=data)
    backup_before = open(macos_root.backup_path(data), "rb").read()

    macos_hosts.remove(app, data_dir=data)

    assert telemetry_block.has_block(files[macos_hosts.HOSTS_IMAGE_PATH]) is False
    # Root survives, and so does its backup -- otherwise there would be nothing
    # left to un-root to.
    assert macos_root.image_root_state(app, data) is True
    assert os.path.isfile(macos_root.backup_path(data))
    assert open(macos_root.backup_path(data), "rb").read() == backup_before


def test_a_replaced_image_clears_the_recorded_block(install):
    """A BlueStacks update, or an un-root, drops the block with the image."""
    app, data, image, _ = install
    macos_hosts.apply(app, data_dir=data)
    assert macos_hosts.status(app, data) is not None

    image.write_bytes(b"a-new-build-from-an-update")

    assert macos_hosts.status(app, data) is None


def test_backup_is_not_overwritten_by_a_second_edit(install):
    """The backup must stay the *pristine* image, not the once-edited one."""
    app, data, image, _ = install
    original = image.read_bytes()
    macos_hosts.apply(app, data_dir=data)

    macos_root.ensure_backup(str(image), data, image_is_pristine=False)

    assert open(macos_root.backup_path(data), "rb").read() == original
