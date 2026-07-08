# Bundled e2fsprogs (`debugfs` / `e2fsck`)

These are prebuilt **e2fsprogs 1.44.5** binaries (from the official
[Cygwin](https://www.cygwin.com/) distribution) plus the Cygwin runtime DLLs they
need. They are bundled so the app can edit an instance's ext4 `/system` image
(inside `Root.vhd`) **offline**, with no Cygwin/WSL install required by the end
user.

## Why they're here

Classic (MSI / pre-5.22.150) BlueStacks builds expose root only as
`/system/xbin/bstk/su` — there is no `su` on the app `PATH`, so root-checker
*apps* report "not rooted". `ext4_symlink.py` adds a `/system/xbin/su -> bstk/su`
symlink offline. `/system` lives in an ext4 image (htree directories +
`gdt_csum`/`metadata_csum` checksums), which `debugfs` edits correctly;
`e2fsck` verifies the result. See `ext4_symlink.py` for how they are invoked
(the tool `diskpart`-attaches `Root.vhd`, runs `debugfs` at the ext4 partition
offset, then detaches).

Patch-mode builds (NXT/CN, 5.22.150.1014+) do **not** use these — their app root
is done purely in Python by `su_patch_offline.py`.

## Files

| File | Purpose |
|------|---------|
| `debugfs.exe` | create the `su` symlink inside the ext4 image |
| `e2fsck.exe` | verify filesystem consistency after the edit |
| `cygwin1.dll`, `cygext2fs-2.dll`, `cyge2p-2.dll`, `cygcom_err-2.dll`, `cygss-2.dll`, `cygblkid-1.dll`, `cyguuid-1.dll`, `cygintl-8.dll`, `cygiconv-2.dll`, `cyggcc_s-seh-1.dll` | runtime DLLs (full dependency closure of the two tools) |

The binaries run standalone from this directory (Windows resolves the DLLs from
the executable's own folder) — no `PATH`/registry setup needed.

## Licensing / source

- **e2fsprogs** (`debugfs`, `e2fsck`, `libext2fs`, `libe2p`, `libcom_err`,
  `libss`) — GPL-2.0 / LGPL-2.0. Source: <https://git.kernel.org/pub/scm/fs/ext2/e2fsprogs.git/>
  (release 1.44.5), as packaged by Cygwin: <https://cygwin.com/packages/summary/e2fsprogs.html>
- **Cygwin runtime** (`cygwin1.dll`, etc.) — LGPL-3.0 with the Cygwin linking
  exception. Source: <https://cygwin.com/git/>

Both are redistributable. To reproduce this bundle, install the `e2fsprogs`
package with Cygwin's `setup-x86_64.exe`, then copy `usr/sbin/debugfs.exe` +
`usr/sbin/e2fsck.exe` and the DLLs listed above (from Cygwin's `bin/`) here.

## Packaging

The PyInstaller build ships this folder inside the executable:

```
--add-data "tools/e2fsprogs;tools/e2fsprogs"
```

At runtime `ext4_symlink._tool_dir()` resolves it from `sys._MEIPASS` (frozen) or
this directory (running from source).
