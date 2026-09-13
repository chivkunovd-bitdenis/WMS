# WMS-440–445: APK test-channel delivery, 13 September 2026

The separately versioned mobile source is commit
`117de6d7c57817c93080a66bf44bdbebf3a16ee2`.  It changes the Android package
from `versionCode` 11 to 12, because the published candidate also had code 11
and Android correctly rejects a same-code replacement.

The public prerelease channel remains
[tsd-preview](https://github.com/chivkunovd-bitdenis/WMS/releases/tag/tsd-preview).
The prior APK assets were retained.  Its active `update.json` now names this
new asset:

- [WMS-TSD-0.1.11-tsd-package-a776769fdb8e-debug.apk](https://github.com/chivkunovd-bitdenis/WMS/releases/download/tsd-preview/WMS-TSD-0.1.11-tsd-package-a776769fdb8e-debug.apk)
- package `ru.wms.tsd`; `versionCode` 12; version name `0.1.11-tsd-package`; min SDK 24
- size 45,527,649 bytes; SHA-256 `a776769fdb8e5352808f84528110e6e4ed07f8eeac4320e3b904122ed7df3003`

The APK was built with `testDebugUnitTest`, `lintDebug`, and `assembleDebug`.
The published asset was then downloaded anonymously and its SHA-256, package,
version, min SDK, and APK Signature Scheme v2 certificate were read again.
The certificate matched the previously installed version 11 on the dedicated
`emulator-5580` test emulator.  Android accepted that publicly downloaded APK
as an in-place update: package manager subsequently reported version code 12,
version `0.1.11-tsd-package`, and APK signing version 2.

The app itself was opened after the update and reached its existing saved-user
selection screen.  No employee PIN was entered, so no account or warehouse
operation was performed during delivery.  The remaining physical acceptance is
to use the in-app “Обновление приложения” button between assignments on a test
TSD, which will download the same public manifest and require the normal
Android installation confirmation.
