# Offline Kyubi payload

Drop the Kyubi release APK here to install Manager Root (Magisk) without any
network access:

```
magisk_assets/kyubi/app-release.apk
```

Where to get it: <https://github.com/RobThePCGuy/Kyubi/releases> — the asset is
named **`app-release.apk`**. Use the newest release; the filename must stay
exactly `app-release.apk`.

What changes once it is here: `magisk_payload.fetch_apk()` uses this file
verbatim and makes **no request at all** — install, update, and "Manager app" all
run offline. With no file here it falls back to the previous behaviour (resolve
the newest release over the GitHub API and download it), which is what fails with
`HTTP Error 403: rate limit exceeded`.

Optional integrity pin: put the SHA-256 next to it as
`app-release.apk.sha256` (`sha256sum` output is fine — `"<hex>"` or
`"<hex>  app-release.apk"`). When the pin is present a mismatch refuses the
install; without it the file is trusted as-is but still checked for the Kyubi
layout (x86/x86_64 and/or arm64-v8a `lib/*` binaries plus `assets/stub.apk`).

Notes:

- The APK is the user's own download and is **git-ignored** — Kyubi is GPLv3 and
  this project redistributes none of it. A release build only carries one if
  whoever built it chose to put it here.
- For the packaged `.exe`, either build with this file in place, or put it in a
  `magisk_assets/kyubi/` folder next to the exe — both are searched.
- Point somewhere else entirely with `KYUBI_PAYLOAD_APK=<path>` (that path wins;
  pointing it at a missing file is an error, not a silent download).
