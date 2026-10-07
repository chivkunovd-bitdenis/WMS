# WMS-607 P1 correction: same replacement developer, 07.10.2026

Correction of the finite owned-process rollback boundary from independent review
`30ffc6bce9fffcdc1b4e0b95b9c8782bfb41896c`. This continues the same replacement
developer session; it is not independent re-review or analytical acceptance.
Fresh `origin/etalon:AGENTS.md` at `4c532f0cccfb8f99b34d68d9630a3763038fbc5f`,
the developer skill, review/probe and applicable R-U4/R-U5/R-U6 were read.

In the existing permanent checkout and named branch, frozen test commit
`040e94c956b8cc99d69d04e8cc90499a01e61a95` was cherry-picked first as
`905687027`; evidence-only handoff `6b85c90e4719dc652e595321f268ca96a62d982a`
followed as `dfc68052c`. All frozen bytes are unchanged.

**Source-only correction: `bdd5a8eee8606d667a90a3b61da299b4097dc877`.**
Only `tools/print-agent/update_macos_direct.sh` changes: 11 insertions and five
deletions. The source commit was pushed promptly before the older suites finished.

`stop_owned` now distinguishes safe no-owner/confirmed-stop, confirmed foreign
owner, and an owned stop that cannot be confirmed. `rollback` returns immediately
on the last outcome, before renaming/deleting application or recovery trees and
before clearing transaction. TERM failure has a truthful owned-process diagnostic.
The existing foreign-owner application-only recovery remains nonzero, sends no
signal, and does not claim restart. No forced kill or broad process-name kill was
added. Current journal, unknowns, receipts, backup and payload are not restored
from an old snapshot or erased.

## Checks and actual boundaries

| Run | PASS | Behavioral FAIL | ERROR | SKIP |
|---|---:|---:|---:|---:|
| New four, before first source edit | 2 | 2 | 0 | 0 |
| New four, corrected source | 4 | 0 | 0 | 0 |
| Immutable old updater ten | 10 | 0 | 0 | 0 |
| Existing ArtMaks 6 + resolver 5 + native 3 + HTTP 5 | 19 | 0 | 0 | 0 |

The precode failures reproduced actual application replacement and intent deletion
under an owned process which survives TERM or rejects TERM. They are behavioral
assertions, not missing-entry or setup failures. The corrected raw records show
unchanged target/previous/archive/journal bytes, modes and links, live controlled
process and retained transaction/intent for both failures. Successful stop and
foreign-owner preservation still pass.

The new four execute the actual complete shell function block with real temporary
filesystem operations. Only lsof/ps/kill/sleep are controlled. The older CLI ten
use the frozen external OS/startup fixtures and actual installer decisions. The
19 existing checks compile/run their unchanged Swift boundaries with fake print
submission/queues; no host process, Library or physical printer is used.
Existing SDK/default native compilation caches were retained; no dependencies,
cache clean or package build occurred. Test harnesses create/clean their own
temporary executables normally.

Evidence: `precode.xml/log` + `precode/`, `green.xml/log` + `green/`,
`updater.xml/log` + `updater/`, `existing.xml/log` + `http/`.
`preservation.json` verifies exact XML IDs, raw source hashes, all new frozen
contract/handoff files, the old frozen contract and previous print sources/tests.
Swift, builder and requirements remain byte exact. `bash -n` and the source-only
`git diff --check` pass.

After cherry-pick, sparse checkout omitted the two old report runners. The initial
launches could not open them; those diagnostics are retained in
`*-sparse-runner-absent.log`. Runners were materialized from exact Git bytes,
without editing expectations, and then the suites above ran successfully.

To verify saved source/results without rerunning suites:

```sh
python3 -B docs/evidence/WMS-607/updater-stop-fix-20261007/verify.py
```

For the narrow behavioral rerun:

```sh
WMS607_STOP_RAW=docs/evidence/WMS-607/updater-stop-fix-20261007/green python3 -B tools/print-agent/test_macos_direct_updater_stop_contract.py --report docs/evidence/WMS-607/updater-stop-fix-20261007/green.xml
```

Separate independent re-review and analyst acceptance remain required. No tests,
requirements, common WMS-652 files, other checkout, policy or workflow were edited.
No release, install, browser, broad backend/WMS suite, CI dispatch, secret action,
provider, Telegram or customer message occurred. No package was built: the saved
ARM artifact from `32c3212406eaf57b904c207bfb45d7acfd25a0b0` contains the previous
updater and **is not the final package**. Rebuilding packages follows independent
re-review and analytical acceptance, as instructed.
