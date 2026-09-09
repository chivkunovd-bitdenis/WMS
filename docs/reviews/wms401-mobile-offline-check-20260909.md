# WMS-401: bounded offline mobile verification inventory

**Result: current Kotlin tests/compilation not executed because the required offline
Gradle runtime and dependency cache are absent.** This is not a test failure and does
not establish mobile readiness or release publication readiness.

Read-only target: `/Users/deniscivkunov/Projects/WMS/.worktrees/wms397-mobile`, current
commit `dfcb7624216a6bb26bae1641357d4145764b85cf`, clean working tree before and after.
No application source, build configuration, credential, signing material or nested Git
state was changed. The only task artifact is this report in the separate QA worktree.

## Exact targeted tests

Root clarified that "three tests" means the three new cases in dfcb762, all in
`FbsViewModelTest`, not three test suites. The commit diff was read and identifies:

1. `physical choices use server availability and the deepest container`.
2. `cancel chooser preserves queued scan oldest order and explicit cell stays loose`.
3. `switching supply cancels chooser and discards scans queued for previous supply`.

They cover available physical source selection, retaining the queued operation through
source-choice cancellation, and discarding previous-supply work. Unrelated scanner/auth
tests were not run. The API-contract suite was not modified in dfcb762 and was not added
to this bounded check.

## Verified resources

- Working JDK: `/opt/homebrew/opt/openjdk@17/bin/java`, version17.0.19.
  macOS `java_home` does not list a registered runtime, but direct Java execution works.
- Installed Android SDK: `/opt/homebrew/share/android-commandlinetools`.
  `platforms/android-35/android.jar` and `build-tools/35.0.0/aapt2` exist.
  The standard `~/Library/Android/sdk` and this checkout's `android/local.properties`
  do not exist; the discovered SDK path would need to be supplied to a future build.
- Project configuration requires Gradle8.11.1, Android Gradle Plugin8.7.3,
  Kotlin2.0.21, compileSdk35 and Java17. The existing generated API JAR is present.
- `~/.gradle/wrapper/dists` contains only `CACHEDIR.TAG`; the required Gradle8.11.1
  distribution is absent. Installed Homebrew Gradle is9.6.1 only, and was not substituted.
- `~/.gradle/caches/modules-2` is absent; the default caches directory contains only
  `jars-9` and `journal-1`. `GRADLE_USER_HOME` is not set to an alternate cache.
- Existing checkout artifacts occupy26MiB in `android/app/build` and3.1MiB in
  `android/.gradle`. Their presence does not supply the missing runtime/dependency cache
  or prove a fresh test pass on dfcb762. Free disk was495MiB at the final inventory.

The existing `docs/reviews/wms397-398-mobile-20260909.md` describes an earlier offline
compilation and earlier test passes, but provides no alternate Gradle/cache path. It is
historical evidence, not a current execution result. No credential-bearing README,
keychain, keystore, secret value or historical credential log was opened.

## Why the command was not started

The Gradle wrapper may download its own distribution before Gradle processes `--offline`.
Therefore invoking this wrapper with `--offline` would not satisfy the no-download
constraint when its distribution is absent. A safe run first needs the matching existing
Gradle8.11.1 distribution and all required plugin/library artifacts restored or otherwise
made available through an approved offline cache. No downloads or installations were made.

After those resources exist, the intended narrow task is `:app:testDebugUnitTest` with
three exact `--tests` filters above, `--offline --no-daemon --max-workers=1`, a supplied
SDK path and bounded JVM memory. Debug Kotlin compilation is its normal prerequisite;
no release signing or release publication task is part of this check.

The separately unresolved release-signing question remains outside this QA task. No
claim of a signed APK, published mobile release, device acceptance or physical printing
is made.
