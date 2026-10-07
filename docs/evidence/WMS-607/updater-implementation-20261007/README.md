# WMS-607: replacement developer handoff, 07.10.2026

This is a **separate replacement developer** receipt, not the original
`artmaks_developer` role or session. The supplied follow-up failed with
`failedagentthreadlimit`; the supplied interrupt returned `not_found`.
Only the updater and necessary existing native/package integration were owned.
No other checkout, common WMS-652 work, backlog, requirements, frozen tests,
release, deployment, customer installation or Telegram action was changed.

The permanent checkout is
`/Users/deniscivkunov/Projects/WMS/.worktrees/wms607-artmaks-test-contract`, branch
`codex/wms607-direct-updater-implementation-20261007`.
Base: `a40bf5b9a2f833a16cb9ff8c941c46c02a0b9d72`.
**Product-only source commit: `32c3212406eaf57b904c207bfb45d7acfd25a0b0`.**
The product commit contains only `update_macos_direct.sh`, `build_console.py`
and `wms_print_direct_macos.swift`. This evidence is saved separately.

## What changed and why

`tools/print-agent/update_macos_direct.sh` selects the hardware architecture,
including ARM under Rosetta, from an explicit reviewed immutable manifest. It
checks the download checksum, ZIP boundaries/links, source commit, Direct console
metadata, binary architecture, absence of embedded Python, signature and unpacked
native self-test before stopping the selected executable. There is no guessed
release URL, generated release manifest or public artifact in this change.

The updater verifies the port owner, retains complete readable application and
state archives with modes/links, serializes concurrent calls, records recovery
intent before rename, and replaces a prepared tree on the application volume.
Rollback restores application bytes only. It never restores archived state over
current receipts, unknown outcomes or labels. A repeat verifies the installed
binary/process/health/readiness and preserves the genuine previous archive.
The supplied manifest is carried into the prepared tree, so app/manifest defaults
continue to work after replacement. Canonical path comparison recognizes macOS
`/var` versus `/private/var` aliases without identifying another executable as owned.

The native change adds technical `--updater-start STATE` and `--readiness`
entrypoints. `--updater-start` suppresses automatic resumption of existing saved
jobs; subsequent explicit requests retain the ordinary worker. `--readiness`
only resolves the existing system default queue. Earlier compatible binaries
are checked using read-only queue commands; saved/unreadable journals prevent an
automatic older restart rather than permitting an updater-triggered submission.
That case reports restored bytes without claiming a working restart. The ordinary
entrypoint, HTTP handlers, native self-test, receipt and unknown logic retain their
previous behavior. No new product screen, mode or print status was introduced.

`build_console.py` includes the command in the existing native Mac console ZIP.
The shell command uses existing macOS tools. Security settings, Chrome, default
printer, host Library and physical printers were not changed by these checks.

## Local verification

- **Before the first product edit:** [precode.xml](precode.xml) and
  [precode.log](precode.log): 10 tests, two existing actual builder/Swift journal
  preservation PASS, eight missing-entry assertion FAIL, zero ERROR/SKIP.
  Missing entry is unimplemented integration, **not behavioral RED**.
- **Frozen actual CLI contract, final product source:** [final.xml](final.xml),
  [final.log](final.log), [final/](final/): exact ten contract IDs, 10 PASS,
  zero FAIL/ERROR/SKIP. Each raw record matches the final updater, native source
  and frozen test hashes. CLI logic and real temporary ZIP/files/archives are
  product code; hardware, downloads, process, startup executable and OS commands
  are controlled external fixtures. Their fixed `dc652...` metadata is fixture
  data, **not the source metadata of the changed real package**.
- **Existing checks, once:** [existing.xml](existing.xml), [existing.log](existing.log),
  [http/](http/): old ArtMaks 6 + resolver 5 + native 3 + HTTP 5 = 19 PASS,
  zero FAIL/ERROR/SKIP. Existing test files/expectations remain byte unchanged.
- **Actual new native entrypoints:** [native-start.json](native-start.json):
  existing HTTP external boundaries, real compiled Swift, real journal. Startup
  and readiness made zero submissions; one explicit new scan made one fake
  submission; the pre-update saved job remained saved. No physical printing.
- **Default app/manifest repeat:** [default-repeat.json](default-repeat.json):
  real CLI with frozen OS boundaries, installed command and installed manifest,
  no `--app-dir`/`--manifest`, explicit temporary state/backup only, no HOME
  override. Repeat preserves archives and makes no stop or print call.
- `bash -n`, `git diff --check`, actual ZIP readback and source comparison passed.
  [preservation.json](preservation.json) contains hashes and exact comparisons.
  Frozen contract/runner/contract.json, all four old test files, C observer,
  history and requirements are byte unchanged from the supplied base.
  Native source intentionally changes from `42b9f0dc...` to `5b055e32...` for
  the technical launch integration; HTTP/self-test bytes and the Printer core
  except the explicit `resumeSaved` gate are checked against the base.

Reproduction (from this checkout, macOS, existing SDK and Python):

```sh
WMS607_UPDATER_EVIDENCE_DIR=docs/evidence/WMS-607/updater-implementation-20261007/final python3 -B docs/evidence/WMS-607/updater-test-contract-20261007/run-contract.py --report docs/evidence/WMS-607/updater-implementation-20261007/final.xml
python3 -B docs/evidence/WMS-607/updater-implementation-20261007/run-existing.py --report docs/evidence/WMS-607/updater-implementation-20261007/existing.xml
python3 -B docs/evidence/WMS-607/updater-implementation-20261007/check-native-start.py
python3 -B docs/evidence/WMS-607/updater-implementation-20261007/check-default-repeat.py
python3 -B docs/evidence/WMS-607/updater-implementation-20261007/verify-sources.py
```

Development log/XML runs (`actual`, `corrected`, `before-manifest`,
`manifest-development`, `zip-validation-development`) retain the debugging
history and can contain intermediate code versions; redundant intermediate raw
files were omitted. They are not final-source
acceptance evidence. The two `native-start-harness-*-error.log` files are errors
in this developer's separate proof driver, corrected without changing the frozen
contract. The superseded local ARM build log is not the final package proof.
The final exact-source evidence is explicitly identified above.

## Actual local artifact and architecture plan

Only after local software checks, the existing builder compiled the actual native
ARM64 package from the product SHA above, signed ad hoc, verified the signature,
unpacked the ZIP and ran the native self-test successfully. No dependencies,
checkouts or large downloads were installed. Build outputs use the existing
ignored `dist-console`/`build-console` directories and remain local.

See [local-arm64-artifact.json](local-arm64-artifact.json),
[local-arm64-build.json](local-arm64-build.json) and
[local-arm64-build.log](local-arm64-build.log). Actual values:

- Source: `32c3212406eaf57b904c207bfb45d7acfd25a0b0`.
- ZIP: `WMS-Print-Console-Mac-arm64.zip`, 182031 bytes.
- Archive SHA256:
  `409f1afd0ab3743729dad0f1f3105f86822d89d99e509dad02ccf94dd7a09cf3`.
- Native executable SHA256:
  `6e114c15815ebc02e25dd91478f66c7ca6a5030b6d1e7c8fa8480a4bbfb0d007`.
- Updater SHA256:
  `2b0eba04a230ca5d0b09043f716505617ddea7bb6bf715f7eb5e09cf39a5432a`.
- Metadata: `platform=darwin`, `architecture=arm64`, `runtime=direct`,
  `console=true`, `physical_print_verified=false`.

The future packaging path is the existing `print-console-package.yml` native
matrix: `macos-14` ARM64 and `macos-15-intel` x86_64. No workflow was dispatched or
modified here. Both published artifacts must be built from the independently
reviewed exact source, checked after unpacking, and measured separately. A future
CI build can have different archive/binary hashes; it must not reuse these local
hashes without byte comparison. Intel has selection-fixture coverage but no
actual Intel build/run in this receipt. Its hash and both public immutable URLs
remain unset. The distribution manifest must be prepared from actual accepted
artifacts, delivered beside the command, then used by the ordinary command with
its defaults. It must not label this changed package as old `dc652...` source.

## Remaining gates and ownership

This developer does **not** claim independent review, analyst acceptance, CI,
release publication, customer installation, ordinary macOS/Chrome permission
acceptance, physical label size/copies or QR reading. U-C9/U-C10 remain manual and
pending; R-U1..8 and the requirement document were not amended or self-signed.

The next implementation/package reviewer must be a distinct Sol 6.1 session,
separate from this developer and testwriter `01a11389`. Analytical acceptance
belongs to the original replacement analyst `01a11390`, resumed by the lead.
Confirmed review defects return to this same replacement developer session.
The supplied existing HTTP review `12c782` and HTTP acceptance
`756b45a4d46b9e9a33657549e2c2addb6bae89c1` concern the prior accepted HTTP product
`dc652472d75812dbebc68ef4353a718b0f629cbe`; they do not approve this updater/package.
Distribution publication and customer install follow distinct review and
acceptance. Main/etalon merge, deployment, workflow dispatch, provider, printer,
secret management, Telegram and customer messages were not performed.
