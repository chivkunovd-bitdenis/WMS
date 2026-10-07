# WMS-607: independent owned-stop P1 re-review, 07.10.2026

**PASS for the finite source correction.** P1 from independent review
`30ffc6bce9fffcdc1b4e0b95b9c8782bfb41896c` is closed at product source
`bdd5a8eee8606d667a90a3b61da299b4097dc877`. No remaining defect was found in
this bounded correction. This verdict is separate from analytical acceptance,
package build/distribution, customer installation and physical print proof.

Same independent reviewer: Sol 6.1/high session
`01a11370-eea3-7533-a616-2943d59a7bca`, author of the original P1, not WMS-607
tests or product. Developer `01a114ab-ae5b-7771-8983-7135bb61f5b3`, testwriter
`01a11389`, and analyst `01a11390` remain separate. Review base/receipts:
`2022d0de2321fca352789a496d11413a7a816b06`. New frozen contract:
`040e94c956b8cc99d69d04e8cc90499a01e61a95`; old ten:
`a40bf5b9a2f833a16cb9ff8c941c46c02a0b9d72`.

Fresh origin/etalon AGENTS and R-U1–R-U8/U-C1–U-C10 were read. Entire owner/failure
libraries from the previous review were reused after confirming exact byte
identity with fresh origin/etalon. Developer handoff skill was already read;
no dedicated reviewer skill was invented. Requirements remain unchanged.

## Why the correction closes the finding

The source-only commit changes **one file**, `tools/print-agent/update_macos_direct.sh`,
11 insertions and five deletions. `stop_owned` now returns 0 for no owner or a
confirmed stop, 2 for a confirmed foreign/unsafe owner, and 1 when stopping the
owned process is unconfirmed (ownership recheck failure, TERM error or survivor).
The existing empty-port path in `owned_pid` returns 1 and is explicitly converted
to safe no-owner success by `stop_owned`; confirmed-stop success still requires
both loss of the listener and failure of the process-existence check.

At `rollback`, stop status 1 returns before any application rename/removal or
`clear_transaction`. Consequently the target, previous tree, backup, current
journal, all three recovery records and active transaction remain intact. The
diagnostic identifies an owned stop failure, without incorrectly naming a foreign
owner. Cleanup can release the updater lock while retaining recoverable intent;
the next invocation attempts recovery before another replacement. No forced kill
or new retry/submission is added.

Status 2 retains the existing application-only recovery: no signal to the foreign
process, previous bytes restored, journal and archive unchanged, transaction
finalized, nonzero result and no successful-restart claim. Status 0 retains the
successful existing recovery. All other rollback/start/cleanup code is byte
unchanged, including the prohibition on restoring archived state over current
receipts/unknowns.

## Actual independent check and immutable receipts

Only the new four-case frozen module was executed here, unchanged from its
published contract. The sparse test file was materialized from exact tracked
bytes; the updater came from actual HEAD Git bytes. Command:

```sh
WMS607_STOP_RAW=docs/evidence/WMS-607/updater-stop-rereview-20261007/raw python3 -B tools/print-agent/test_macos_direct_updater_stop_contract.py --report docs/evidence/WMS-607/updater-stop-rereview-20261007/updater-stop.xml
```

Result: **4 PASS, 0 FAIL, 0 ERROR, 0 SKIP**; actual log/XML and four raw records are
saved here. They execute the exact complete production function block with real
temporary filesystem operations, controlling only lsof/ps/kill/sleep replies.
No host process, listener, native binary or print/CUPS command is used.

The TERM-error and TERM-success-survivor cases each retain all before/after
inventories and recovery records, with one TERM attempt, process alive,
transaction=1 and nonzero failure. Successful stop restores previous application
and preserves journal/archive. Foreign owner stays alive and receives zero
signals while the previously valid application-only recovery is preserved.

`verify-evidence.py` / `source-checks.json` independently bind source before/after,
the exact one-file delta, all new frozen contract bytes, the previous 15
preservation paths and unchanged whole Swift/build files. The old ten plus new
four assertions/IDs are unchanged. It validates saved developer reports and raw
source/test identities: precode four had **2 behavioral FAIL + 2 PASS**, then
four PASS; old ten and existing nineteen PASS with zero errors/skips. Their logs,
ten CLI raw records and five HTTP raw records were read/checked, not rerun. The
precode failures were the actual premature replacement/intent deletion, not setup
errors. Four local raw records also match the corrected updater and frozen test
hashes. No need to rerun the old reviewer probe: the new immutable survivor case
executes the same actual function block and verifies the previously broken invariant.

Read-only evidence validation command:

```sh
python3 -B docs/evidence/WMS-607/updater-stop-rereview-20261007/verify-evidence.py
```

## Limits and next handoff

This closes the source-level P1 only. The earlier ARM ZIP was built from
`32c3212406eaf57b904c207bfb45d7acfd25a0b0` and contains the old updater; it is
**not a final bdd5a8 package**. No current-source ARM/Intel package was built or
published here. Default reviewed manifest/public URLs, customer installation,
macOS/Chrome permission acceptance (U-C9), physical paper/QR (U-C10) remain pending.
The distinct analyst performs software acceptance next; subsequent package build
and distribution must bind actual artifacts to the accepted corrected source.

Only this evidence directory is authored. Product, tests, requirements, workflows,
policy, WMS-652/common files and other worktrees are unchanged. Old suites,
native builds, CI, browser, installation, real printers/CUPS, customer messages
and secret operations were not run. Existing stash
`b396ded869bc8932ad25dc448b5f7163aa62a2f7` remains preserved.
