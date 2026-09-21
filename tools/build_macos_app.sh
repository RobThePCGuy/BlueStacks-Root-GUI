#!/bin/bash
# Build BlueStacksRootGUI.app for BlueStacks Air (Apple Silicon) and zip it.
#
# The .app is self-contained: it carries its own debugfs/e2fsck, so the person
# downloading it needs neither Python nor Homebrew. Those two tools are taken
# from Homebrew's e2fsprogs at build time, together with every non-system dylib
# they load, and rewritten to find those dylibs next to themselves
# (@loader_path) instead of under /opt/homebrew.
#
# Needs: Apple Silicon, Homebrew, `brew install e2fsprogs`, and a Python env
# (the script installs requirements.txt, pyinstaller and pillow into it).
# Output: dist/BlueStacksRootGUI.app and dist/BlueStacksRootGUI-macOS.zip.
set -euo pipefail

cd "$(dirname "$0")/.."
PYTHON="${PYTHON:-python3}"
E2FS_SRC="$(brew --prefix e2fsprogs)/sbin"
STAGE="build/e2fsprogs-macos"

[ "$(uname -m)" = "arm64" ] || { echo "Build on Apple Silicon: BlueStacks Air is arm64-only." >&2; exit 1; }
[ -x "$E2FS_SRC/debugfs" ] || { echo "Missing debugfs: brew install e2fsprogs" >&2; exit 1; }

"$PYTHON" -m pip install -q -r requirements.txt pyinstaller pillow

rm -rf "$STAGE" build/BlueStacksRootGUI dist/BlueStacksRootGUI.app dist/BlueStacksRootGUI-macOS.zip
mkdir -p "$STAGE"

# Non-system libraries a Mach-O file links against (anything outside /usr/lib
# and /System, which every Mac already has).
foreign_deps() {
    otool -L "$1" | tail -n +2 | awk '{print $1}' | grep -v -E '^(/usr/lib/|/System/|@)' || true
}

# Copy the tools, then walk their dependency graph until no new dylib appears.
cp "$E2FS_SRC/debugfs" "$E2FS_SRC/e2fsck" "$STAGE/"
chmod u+w "$STAGE"/*
queue=("$STAGE/debugfs" "$STAGE/e2fsck")
while [ ${#queue[@]} -gt 0 ]; do
    file="${queue[0]}"; queue=("${queue[@]:1}")
    for dep in $(foreign_deps "$file"); do
        name="$(basename "$dep")"
        if [ ! -e "$STAGE/$name" ]; then
            cp "$(realpath "$dep")" "$STAGE/$name"
            chmod u+w "$STAGE/$name"
            install_name_tool -id "@loader_path/$name" "$STAGE/$name" 2>/dev/null
            queue+=("$STAGE/$name")
        fi
        install_name_tool -change "$dep" "@loader_path/$name" "$file" 2>/dev/null
    done
done

# install_name_tool invalidates the signatures; arm64 refuses to run unsigned
# code, so re-sign ad hoc.
for f in "$STAGE"/*; do codesign --force --sign - "$f" 2>/dev/null; done

# Fail the build, not the user, if anything still points into Homebrew.
for f in "$STAGE"/*; do
    if [ -n "$(foreign_deps "$f")" ]; then
        echo "$f still links outside the bundle:" >&2; foreign_deps "$f" >&2; exit 1
    fi
done
"$STAGE/debugfs" -V >/dev/null 2>&1 || { echo "Relocated debugfs does not run" >&2; exit 1; }

# The --add-data destination must match macos_root._bundled_e2fs_dir().
"$PYTHON" -m PyInstaller --noconfirm --windowed \
    --name BlueStacksRootGUI \
    --icon favicon.ico \
    --osx-bundle-identifier com.robthepcguy.bluestacksrootgui \
    --add-data "favicon.ico:." \
    --add-data "build/e2fsprogs-macos:tools/e2fsprogs-macos" \
    main.py

# Smoke-test the tools where the finished app will look for them. A mismatch
# between the --add-data destination above and macos_root._bundled_e2fs_dir()
# would otherwise ship an app that silently needs Homebrew again.
BUNDLED="dist/BlueStacksRootGUI.app/Contents/Frameworks/tools/e2fsprogs-macos"
for tool in debugfs e2fsck; do
    "$BUNDLED/$tool" -V >/dev/null 2>&1 || { echo "Bundled $tool missing or broken in $BUNDLED" >&2; exit 1; }
done
grep -q '"tools", "e2fsprogs-macos"' macos_root.py \
    || { echo "macos_root._bundled_e2fs_dir() no longer points at tools/e2fsprogs-macos" >&2; exit 1; }

# ditto keeps the bundle's symlinks and signature intact; plain zip does not.
ditto -c -k --keepParent dist/BlueStacksRootGUI.app dist/BlueStacksRootGUI-macOS.zip
echo "Built dist/BlueStacksRootGUI.app and dist/BlueStacksRootGUI-macOS.zip"
