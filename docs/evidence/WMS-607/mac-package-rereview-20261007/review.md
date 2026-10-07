# WMS-607: independent package harness re-review, 07.10.2026

**PASS for the bounded technical harness correction.** Both findings from
`a98c85781779a708f250b81a7dc232b1461778c8` are closed. Reviewed exact harness:
`d0a0be566e2fd6ea10c64c650875d72319f9a103`, published branch
`codex/wms607-direct-updater-mac-package-20261007`.
The only permitted SOURCE input is the literal independently accepted commit
`a04a7b35f1e866c1283bdc46fff2d41eaf68b4d6`. Both remote heads were verified.

Same distinct Sol 6.1/high reviewer `01a11370-eea3-7533-a616-2943d59a7bca` authored
neither this integrator harness nor WMS-607 product/tests. Original owned-stop P1
remains closed by software review `49da13fd2a0d22f207818248f274cf5ff400e39f` on
product `bdd5a8eee8606d667a90a3b61da299b4097dc877`. Fresh origin/etalon AGENTS was
read; previously read complete owner/failure libraries and handoff guidance were
reused. Scope is two findings plus the standard document gate/pin, without new
business requirements or broad re-audit.

## Closure evidence

P1: checkout now uses `fetch-depth: 0`, preserving explicit SOURCE checkout and
`persist-credentials: false`. The historical `.4` commit
`9a33b651c309796707053e1056c7f80dff7194d5` and its actual Swift source are present
in full Git history reachable from published remote
`refs/heads/chore/staging-sync-20261003` at
`9301daeddb56337992ca2d6b8cec1de091e6bc05`; remote tip and ancestry were checked.
It need not be an ancestor of SOURCE: full branch/history fetching makes the
unchanged compatibility fixture's literal `git show` dependency available.
No fresh clone/full local fetch or native fixture execution was performed here.

P2: actual validator checks `list(root.iter(...))` presence for failure, error
and skipped. The actual new `ids` FunctionDef was extracted from workflow AST
and executed on copied accepted XML. **Clean ten IDs: ACCEPTED; one childless
failure/error/skipped node each: REFUSED.** Exact ten IDs were retained in every
copy. This is the same finite negative boundary as the original review, with no
fake/replacement validator. Temporary XML copies were removed; tracked baseline
reports stayed byte unchanged. Existing count, unique-ID and exact baseline-set
checks remain unchanged, preserving mandatory 10+4+19 named executions on each
architecture. No skip, error, duplicate or missing case can satisfy that gate.

The first guard now requires the literal accepted SOURCE as well as full SHA
shape, isolated integrator branch and attempt one. Checkout consumes the same
input; actual HEAD is checked before tests and after build. No arbitrary SOURCE
can pass the guard. Before native tests, `git merge-base --is-ancestor 49da... HEAD`
and the unchanged standard `check_task_documents.py 49da...` command enforce the
complete-source document gate. The source is an actual descendant of 49da.
Saved native document-check exit0/log were read, not rerun. The analyst's twelve
reference suffix corrections exactly reconstruct the new requirements bytes from
accepted 2f7294b; scenarios/verdicts and actual test IDs did not change.

## Preservation and static verification

`review.json` records exact workflow/script hashes, remote/history facts, copied
XML outcomes, accepted baseline identities, document gate receipt and closure
hashes. Existing PyYAML parsed YAML. All **nine** run blocks passed `/bin/bash -n`
once; both inline Python blocks compiled once. A read-only comparison driver
initially collided on unnamed checkout/setup entries after those checks passed;
its named-step comparison was corrected without rerunning syntax/XML/native
checks. This was a reviewer proof-driver issue, not a harness defect.

Actual 10/4/19 baseline XML bytes and IDs remain unchanged. Product three-file
bytes match bdd5a8; frozen 14 plus old19 test modules, both reporters and the
standard document checker remain exact. Native test/report paths and `--report`
flags, builder/self-test, archive metadata/source/architecture/Direct checks,
codesign, embedded updater equality, measured archive checksum and tracked Git
cleanliness steps are unchanged from the previously reviewed harness. Source,
harness and run/attempt artifact identities remain distinct. Original ARM Mac14
and Intel Mac15 runner matrix remains, with read-only contents permissions and
no production environment, deployment or secret operations.

## Handoff and limits

Integrator alone may now dispatch this exact harness with only input
`source_sha=a04a7b35f1e866c1283bdc46fff2d41eaf68b4d6`, under the existing owner
authorization and separate completed software acceptance. This reviewer did not
dispatch CI or run native tests/build/self-test. Actual ARM/Intel job results,
archives and source-bound checksums remain to be collected; PASS here is source
and controlled-validator review of the harness, not 33 actual Mac executions.
The old32c ARM archive is not a final package. Public packages/manifest, customer
installation, permissions and physical paper/QR are not claimed.

Only these review evidence files changed. Harness/source/tests/requirements,
WMS-652/common, main/etalon and other worktrees were not edited. Stash
`b396ded869bc8932ad25dc448b5f7163aa62a2f7` remains preserved.
