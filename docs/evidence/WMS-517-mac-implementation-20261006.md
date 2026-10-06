# WMS-517: Mac helper implementation checkpoint, 06.10.2026

Implementation branch: `codex/wms517-mac-dynamic-eligible`.
Persistent checkout: `.worktrees/wms517-mac-dynamic-eligible`, base `4f89eafad1edda1a4bf4d0ac95ad06bccb9c5a40`.
Fresh `origin/etalon` rules read at `4b298efc95be7b4b6b7fe5665be9f3671f1fe747`.
Developer skill and current WMS-517 R26/R27/SC17 contract read before implementation.
Frozen test contract `136ce395ff085955eff669ed8a96cf68fe9938c1` already exists in the base history; tests, requirements, CI and guard files were not changed.

Only four product files were recovered from historical `c42f4d318c094253ce82ba6947c80a342cda57e0` as the starting point and then corrected. No older WMS-665 product history was merged.

The helper reads the complete current server sales-backed registry with `only_not_withdrawn=true`, checking exact page lengths, stable totals, duplicate IDs and session/scope. It selects current `not_withdrawn` rows without operation/error; no fixed80 IDs, independent WB status predicate, price calculation or WB call remains. Dry-run only reads and inspects. Execute clears the two dates, product and search, enables only-not-withdrawn and uses the native selection/certificate dialog. Its temporary registry GET adapter obtains all original server pages again on each native request, refuses changed eligible IDs, and restores the original fetch on success or failed preparation. The native backend fresh recheck remains untouched.

The launcher, injected status and system JXA command accept a positive safe integer N. The same run marker, exact production URL/tab identity, sanitized results, bounded polling and no automatic rerun remain. The generated `.command` embeds the exact helper and launcher bytes and retains mode 0755.

Validation:

- Baseline current109 against restored historical helper: **78 PASS, 31 FAIL**, recorded in `WMS-517-mac-developer-baseline-20261006.txt`.
- Current frozen contract: **109 PASS, 0 FAIL**; TAP in `WMS-517-mac-developer-green-20261006.tap`. Cases include1/80/81/84/305/501, default DOM305, excluded returns/claims/errors, partial pages, changed IDs, session/identity, launcher N and executable/generator/JXA checks.
- `node --check` on helper, launcher and generator; `zsh -n` on generated command: PASS.
- Rebuilding with `node scripts/ops/build-avpack-macos-command.cjs` produces identical bytes. Generated file SHA256: `279fe4faa53cb64a6e760b66cb52c1bcb7e3d210c6d44e0170019d5ede866f0a`.

Reproduce the contract from this checkout:

```sh
node --test --test-reporter=tap scripts/ops/tests/wms517-sold-kiz-filter.test.cjs scripts/ops/tests/wms517-mac-launcher.test.cjs scripts/ops/tests/wms517-mac-dom.test.cjs
```

The DOM/Chrome/API checks are synthetic local doubles, with shared declared jsdom26 available from root frontend dependencies. No Chrome, actual Mac certificate, PIN, CryptoPro signing, create/submit, WB/CRPT production operation, secret-management console, deployment, independent review or analyst acceptance was performed by this developer checkpoint. Software publication/deployment is not gated on Vitaliy; actual Mac dialog/signature/withdrawal remains separately unproved. Repeated fresh registry reads trade extra GETs for checking current composition; their real-network latency has not been measured.
