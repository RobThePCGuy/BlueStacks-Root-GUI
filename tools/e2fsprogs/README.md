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

## Verification (audited 2026-07-07)

The bundled binaries were audited before inclusion:

- **PE import tables** contain no networking, crypto, or process-injection APIs.
  `debugfs.exe` / `e2fsck.exe` link only the sibling `cyg*` DLLs, `cygwin1.dll`,
  and `KERNEL32`; `cygwin1.dll` imports only `KERNEL32` + `ntdll` (the normal
  Cygwin runtime shape). A tool that phoned home or injected would need APIs
  that are simply absent here.
- **Version self-report** in `debugfs.exe` / `e2fsck.exe` is `1.44.5`
  (build date `15-Dec-2018`), matching the e2fsprogs 1.44.5 claim above.

SHA-256 of each shipped file (verify after any change to this folder):

```
cb2228400b88b60e685d7ca8815b7f3d7773aeb53f2943586545b66568dd745a debugfs.exe
aadfcfbb1f69e2e4af9980c566f718d34177acb4529a6ae29af4f2f01984f378 e2fsck.exe
c648a92c3881e904abaff5369917bb8dd0cecfafc5cccd93c0fc30e670e311d3 cygblkid-1.dll
8d7451ebc8bd8601d9116c4873d4a8b0ea5fc2d9c2330716180efeeb2ae7045b cygcom_err-2.dll
b6fc78c540f69f3c47cbfedcea34c608bb6217dca9684e0ea274eb486f1f8ace cyge2p-2.dll
9d7ba40ac9eee500f6590eb68a9d9a19e7a5a57a6df0e625432d22838968b1ae cygext2fs-2.dll
bbb18620491599a93676a96c67ab986c3e5a592ba1bbdfb43abf2f26ab09c1ba cyggcc_s-seh-1.dll
20c86120799424c45a981ffa4b3bfe8a99204845633b6c3c6dda06770fdbb7e8 cygiconv-2.dll
4e8159a9eba4ccd4c73864e74d0ad6811598e84ad7e23c27a3cf0dc9da5e183e cygintl-8.dll
29728a0cfbb09e850547b6787b0b6881a9273483548f0a400981ad2226bb74ed cygss-2.dll
53cf0bd45e4a3e8cde1ca30b0a0797055286a56ad9c271d4903b971da7354fcb cyguuid-1.dll
d5562774ec1475bd1dab84c5249b273e60cc53e6aa968981414a4d6a3f8e2bfd cygwin1.dll
```
