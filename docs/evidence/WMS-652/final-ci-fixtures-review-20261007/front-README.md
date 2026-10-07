# WMS-684: DOM deadline cascade at ca6d86

Test-only correction: `a0261518f5d292e7f178f1e59ad1d20ec10a051e`, parent
`ca6d86bd994b87b87ab9ffd878008cbbdf251860`, branch
`codex/night1007-684-dom-ci`. Only the dedicated harness and its WMS-684 DOM
test changed. Product, requirements, PDF tests and CI configuration are unchanged.

## Cause and bounded proof

Linux CI `37553998053` reports 1667 passes and five failures, all in this DOM
file. The source log is
`/Users/deniscivkunov/Projects/WMS/.agent-runs/night-20261006-01a112a8/integration/frontend-build-ca6-final.log`.
The first failure is the date/missing-metadata scenario's 5000 ms deadline.
It runs six complete print jobs plus two remounts. Subsequent tests show
overlapping `act()` calls, a terminal-state failure and zero detail loads.

The isolated **unchanged** file passes 11/11 ([before.log](before.log)); its date
scenario takes 2301 ms. This is not a reproduction of Linux scheduling load.
The fixture spent real wall time on the production 100 ms print delay and
10 ms polling turns. Vitest's test deadline does not cancel those promises.
Teardown unmounted/restored mocks while the old polling `act()` was still alive.

A targeted deadline fault reproduced this causal sequence without changing
product code. Temporary diagnostic statements logged print start, terminal jobs
and teardown busy state. Under `--testTimeout=1500`, the first two prints finish
with job counts 1/2 and mark counts 1/4. The third begins for missing metadata;
teardown then runs with `busy: true`, jobs 2, marks 4. The next test immediately
reports overlapping `act()` calls. All five selected cases fail
([deadline-before.log](deadline-before.log)). These diagnostic statements were
removed before the test commit.

## Correction and results

Only this DOM suite selects controlled Date/setTimeout/clearTimeout clocks.
The harness advances those timers asynchronously inside `act()` while continuing
to require real production transfer, mark calls and terminal UI state. It does
not invoke `beforeTransfer`, replace the printer or relax the 5000 ms deadline.
Other consumers keep real timers. The platform adapter delivers its recorded
`onload` once, so jsdom's queued navigation event cannot duplicate that handoff.
Teardown aborts and drains owned polling waits before restoring mocks, then the
DOM suite clears its timers and restores the real clock. Accepted production
decode concurrency of 16 is unchanged.

All 11 original cases and their business assertions remain. HTTP and lost-response
cases additionally require job counts 1 before/after recovery and 2 only after
printing document B. The ordinary file passes 11/11
([after.log](after.log)); the date scenario takes 1468 ms. ESLint and TypeScript
pass. No full frontend suite, build, PDF rerun or dependency installation was run.

The same 1500 ms fault after the correction still intentionally interrupts the
first scenario, but **all four following cases pass**, with no overlapping
`act()` warning ([deadline-after.log](deadline-after.log)). This negative result
proves that a deadline no longer poisons subsequent fixtures; it is not counted
as a green suite. The full ordinary file is the green result above.

## Exact commands

From the worktree root, before and after the correction:

```sh
node frontend/node_modules/vitest/vitest.mjs run --root frontend --no-cache --maxWorkers=1 --no-file-parallelism src/screens/ff/FfInboundRequestView.wms684.dom.test.tsx
```

For the original-order fault, before and after (before additionally set
`WMS684_TRACE=1` for the temporary diagnostic statements):

```sh
node frontend/node_modules/vitest/vitest.mjs run --root frontend --no-cache --maxWorkers=1 --no-file-parallelism --testTimeout=1500 src/screens/ff/FfInboundRequestView.wms684.dom.test.tsx -t 'uses the Moscow|escapes complete|mark .* failure|keeps cargo'
```

Sequential static checks, from `frontend`:

```sh
node_modules/.bin/eslint src/test-contracts/inbound684586Harness.tsx src/screens/ff/FfInboundRequestView.wms684.dom.test.tsx
node_modules/.bin/tsc --noEmit -p tsconfig.app.json
```

The commands use the existing shared dependencies read-only. All assertions ran
on the actual screen, JsBarcode encoder and production print utility, with only
the existing synthetic HTTP/canvas/jsdom platform boundaries. Local results do
not substitute for independent review or Linux full CI. No push was performed;
the release integrator owns publication. Physical paper is not proved by DOM/PDF.
