# WMS-607 updater: independent source review, 07.10.2026

Verdict: **CHANGES REQUIRED — one reproduced P1**. This is software source
review, not analytical acceptance, release, installation or physical print proof.

Reviewer: distinct Sol 6.1/high session `01a11370-eea3-7533-a616-2943d59a7bca`.
This session authored WMS-652 contracts only; it did not author WMS-607 tests or
implementation. Testwriter `01a11389`, developer
`01a114ab-ae5b-7771-8983-7135bb61f5b3`, and analyst `01a11390` are separate.

Reviewed product: `32c3212406eaf57b904c207bfb45d7acfd25a0b0`, exactly the three
files `build_console.py`, `update_macos_direct.sh`, and
`wms_print_direct_macos.swift` under `tools/print-agent`. Receipt base:
`6232cf29765f1b25466e96919ee7840bf5874c62`. Frozen updater contract:
`a40bf5b9a2f833a16cb9ff8c941c46c02a0b9d72`.

## P1: rollback replaces application underneath an owned process that failed to stop

At `update_macos_direct.sh:217`, every `stop_owned` failure becomes `foreign=1`.
The function then proceeds through application renames at lines 218–225 and
`clear_transaction` at line 230. Only afterwards, at lines 232–234, does it return
failure. `stop_owned` also returns failure when the **owned** process survives
TERM (lines 126–132); that outcome does not establish a foreign owner or safe
replacement. A target that keeps listening while readiness fails can therefore
continue running after its files have been replaced with the previous version.
The target tree and recovery intent are deleted. The diagnostic incorrectly
reports a foreign owner.

This violates R-U4's safe stop before whole-tree replacement and R-U5/R-U6's
recoverable failed launch/rollback. It is not a claim that customer data has
already been lost: the controlled current journal remained unchanged.

`probe-rollback.py` extracts the exact committed function block, retaining actual
`owned_pid`, `process_matches`, `stop_owned`, `rollback`, `tree_inventory` and
`clear_transaction`. Only `lsof`, `ps`, `kill` and `sleep` are controlled: one
known selected executable listens, TERM succeeds, but it remains alive. Temporary
filesystem inventories, renames, removals and comparisons are real. No executable
is launched, no port used and no print/provider command executed.

Command:

```sh
python3 -B docs/evidence/WMS-607/updater-independent-review-20261007/probe-rollback.py
```

Actual result in `rollback-result.json` and `rollback.log`: one TERM attempt,
`rollback_exit=1`, but `transaction=0`, previous application bytes installed,
target removed, recovery record removed, and the controlled owned process still
alive. This is a behavioral failure of the actual function, not setup failure.

Return to the **same developer** through the integrator: distinguish failure to
stop an owned process from confirmed foreign/no-owner outcomes. Do not replace
the tree or clear recovery intent until safe owned-process termination is
confirmed; retain a truthful recoverable failure. Do not force-kill unrelated
processes or restore an old state snapshot. A narrow controlled stubborn-owned
process check should accompany the correction; immutable contract expectations
remain unchanged. No code/test correction was made by this reviewer.

## Source and evidence checks

Fresh `origin/etalon:AGENTS.md` was read at
`4c532f0cccfb8f99b34d68d9630a3763038fbc5f`, together with the entire owner-cases
and failure-cases libraries, R-U1–R-U8/U-C1–U-C10, and the actual frozen contract.
No dedicated reviewer skill exists in the tracked skill catalog; the developer
skill's independent handoff rules were read, without claiming it is a review skill.

`source-checks.json` independently compares Git bytes: all existing print-agent
test files, updater test/runner/contract, requirements, history and C observer
remain unchanged from the contract commit (15 paths). Reversing only the exact
authorized launch/state-option changes reproduces the **whole** prior Swift file.
The HTTP handlers, ordinary default startup and native self-test are preserved.
The real `--self-test` path uses temporary roots and injected submission/queue
functions, including its child fixtures; it does not reach customer Library or
native print/CUPS submission. `--readiness` resolves the queue without submission.
The updater's state path matches the native Direct application-support path;
its default application and manifest paths are beside the console executable.

Architecture/Rosetta selection, immutable manifest/checksum/source/Direct metadata,
Mach-O architecture/signature, ZIP path/link rejection and unpacked self-test are
performed before the selected old process is stopped. No global security,
Chrome/default-printer mutation or dependency installation is added. Staging and
application renames are on the application volume; the updater lock serializes
calls and intent is recorded before replacement. App/state inventory verification
preserves files, modes and links, with the state snapshot after stop. Rollback
copies application only, never archived state over current receipts/unknown.
The P1 above prevents approval of the failure/recovery path despite these checks.

Saved final XML has the exact ten frozen IDs, 10 PASS and zero fail/error/skip;
each of its ten raw records binds the actual updater/Swift/frozen-test hashes.
Saved existing XML has 19 PASS and zero fail/error/skip. These receipts were read
and validated, **not rerun**. The CLI fixtures execute actual shell decisions and
real temporary ZIP/files, while hardware/process/start/signature/extraction OS
boundaries are controlled. In particular their `kill` fixture always stops and
their executable exits after marking a fake running process; they do not cover
the stubborn live-process failure reproduced here. These are honest fixture
limits, not evidence that the native architecture or ZIP processor succeeded.

The separate actual ARM64 package receipt identifies product SHA above, native
Direct console metadata, unpacked signature/self-test success and archive checksum
`409f1afd0ab3743729dad0f1f3105f86822d89d99e509dad02ccf94dd7a09cf3`.
Its updater hash matches reviewed bytes. This validates saved local provenance;
the binary/archive was not rebuilt or independently rerun here. Fixed `dc652...`
metadata in the CLI fixtures is not misrepresented as the new actual package.

## Remaining boundaries

No default reviewed manifest/public URLs exist yet; the command explicitly refuses
without them. A public one-command update is **pending**, as are actual Intel
build/run, package distribution, customer installation, normal macOS/Chrome
permission acceptance (U-C9), and physical label/QR verification (U-C10).
Existing HTTP review/acceptance concern `dc652...` and are not updater approval.
Separate analytical acceptance and future package provenance verification remain
required after correction and independent re-review.

Only this evidence directory changed. No product/test/requirements/policy/workflow,
other worktree, WMS-652/common files or stash was edited. No broad suites, CI,
builds, installs, browser, actual CUPS, external requests, secrets or customer
messages were used. Stash `b396ded869bc8932ad25dc448b5f7163aa62a2f7` is preserved.
