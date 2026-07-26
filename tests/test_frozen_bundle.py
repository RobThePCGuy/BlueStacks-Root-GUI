"""The built exe must actually find the files it ships with.

Every live check of this app has run from source, so a mismatch between what the
PyInstaller build bundles and where the code looks when frozen was invisible:
the released exe bundled the e2fsprogs tools at ``tools/e2fsprogs`` while
``ext4_symlink._tool_dir`` looked in ``e2fsprogs``, so every release reported
"bundled e2fsprogs (debugfs) not found" and no offline operation worked at all.
The captured Magisk assets were never passed to ``--add-data`` in the first
place, so ``Install Magisk`` would have failed on the frozen build too.

These tests read the release workflow's own ``--add-data`` arguments, lay out a
fake ``sys._MEIPASS`` exactly as those arguments would produce, and assert the
code resolves its resources inside it. Change the build or the lookup and this
fails in CI rather than in a user's download.
"""
import os
import re
import shutil
import sys

import pytest

import ext4_symlink as es
import magisk_system as ms

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WORKFLOW = os.path.join(REPO, ".github", "workflows", "release.yml")


def _add_data_pairs():
    """The (source, destination) pairs the release build passes to PyInstaller."""
    with open(WORKFLOW, encoding="utf-8") as f:
        text = f.read()
    pairs = re.findall(r'--add-data\s+"([^";]+);([^"]+)"', text)
    assert pairs, "no --add-data arguments found in release.yml"
    return pairs


@pytest.fixture
def frozen_bundle(tmp_path, monkeypatch):
    """A fake _MEIPASS populated the way the release build populates it.

    PyInstaller copies a directory source *into* the destination directory, and
    a file source to that name inside it, which is what is mirrored here.
    """
    root = tmp_path / "meipass"
    root.mkdir()
    for src_rel, dest_rel in _add_data_pairs():
        src = os.path.join(REPO, src_rel.replace("/", os.sep))
        dest = root / dest_rel if dest_rel != "." else root
        if os.path.isdir(src):
            shutil.copytree(src, dest, dirs_exist_ok=True)
        elif os.path.isfile(src):
            dest.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dest / os.path.basename(src))
        else:
            pytest.fail("release.yml bundles %r, which does not exist" % src_rel)
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "_MEIPASS", str(root), raising=False)
    return root


def test_release_bundles_every_source_it_names():
    """A --add-data pointing at a path that no longer exists fails the build."""
    for src_rel, _dest in _add_data_pairs():
        src = os.path.join(REPO, src_rel.replace("/", os.sep))
        assert os.path.exists(src), src_rel


def test_frozen_build_finds_the_e2fsprogs_tools(frozen_bundle):
    """The bug that shipped: debugfs was bundled but looked for elsewhere."""
    assert es.tools_available() is True, (
        "the frozen build cannot find debugfs/e2fsck; _tool_dir resolved %r"
        % es._tool_dir())
    assert os.path.isfile(es._debugfs())
    assert os.path.isfile(es._e2fsck())


def test_frozen_build_finds_the_captured_magisk_assets(frozen_bundle):
    """install_to_system reads these; they were never bundled at all."""
    asset_dir = ms._asset_dir()
    assert os.path.isdir(asset_dir), asset_dir
    for name in ("config", "bootanim.rc", "bootanim.rc.gz"):
        assert os.path.isfile(os.path.join(asset_dir, name)), name


def test_frozen_build_finds_the_window_icon(frozen_bundle):
    from views.main_window import resource_path
    assert os.path.isfile(resource_path("favicon.ico"))


def test_source_layout_still_resolves_when_not_frozen(monkeypatch):
    """Running from source must keep working after the frozen-path change."""
    monkeypatch.delattr(sys, "frozen", raising=False)
    monkeypatch.delattr(sys, "_MEIPASS", raising=False)
    assert es.tools_available() is True
    assert os.path.isdir(ms._asset_dir())
