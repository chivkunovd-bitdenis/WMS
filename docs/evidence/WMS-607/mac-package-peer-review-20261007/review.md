# WMS-607: independent package harness review, 07.10.2026

**CHANGES REQUIRED: one P1 and one P2. Do not dispatch this harness yet.**
Reviewed harness: `cfcac84450113c772b3d416d188d724534dc703b`; prior software
review: `49da13fd2a0d22f207818248f274cf5ff400e39f`. Distinct reviewer Sol 6.1/high
session `01a11370-eea3-7533-a616-2943d59a7bca` did not author this integrator harness,
WMS-607 product or tests. This is finite technical packaging review, not source
re-acceptance, analyst acceptance or package delivery proof.

## P1: depth-one checkout omits the immutable historical source required by tests

`.github/workflows/ci.yml:34–38` checks out the requested SOURCE with
`fetch-depth: 1`, and no subsequent history/object fetch exists. The frozen
updater ten use `git show 9a33b651c309796707053e1056c7f80dff7194d5:tools/print-agent/wms_print_direct_macos.swift`
in `UpdaterContract.setUpClass` (`test_macos_direct_updater_contract.py:154`,
through `source()` at lines 37–40). The old ArtMaks six independently read the
same historical source in `test_macos_artmaks_contract.py:60–63`.

A fresh depth-one checkout of the new accepted SOURCE has its tree but not that
historical commit object. These are real setup dependencies, not fixture metadata
strings: native journal compatibility compilation cannot complete without them.
The first test step therefore cannot produce ten executed passing cases. This is
an exact static object-dependency finding; no CI/native execution or observed
GitHub failure is claimed. `review.json` records the actual literals, source hash,
checkout settings and absent history-fetch step.

Return to the integrator: obtain the required immutable historical Git object
before the test runners, through full history or a bounded explicit fetch of the
exact required commit, retaining the requested SOURCE as actual HEAD. Verify the
historical source can be read. Do not substitute a fixture/current source or edit
frozen tests to avoid this compatibility check.

## P2: XML status checks accept failed, errored and skipped reports

At `.github/workflows/ci.yml:78`, `any(root.iter('failure'))` (and the equivalent
error/skipped checks) tests the Boolean value of each ElementTree element.
These report nodes have text/attributes but no child elements, so their Boolean
value is false. The actual two reporters and stop CLI write precisely that shape.
Consequently this assertion does not enforce zero failure/error/skip.

A bounded probe executed the **actual `ids` FunctionDef extracted from the
workflow AST**, on copies of the accepted ten-case XML. The unmodified control
was accepted. Adding one childless failure, error or skipped node, and setting
the corresponding suite count to one, preserved exact ten unique IDs; all three
invalid reports were also accepted. `review.json` records these actual results.
No replacement classifier/filter was implemented and no native test ran.

Normal test failures still return nonzero and stop their shell step; this finding
is not a claim they silently pass the whole workflow. Skips normally return zero,
so the promised explicit skip rejection is ineffective, and independently saved
report statuses are not validated as intended. Exact count/unique IDs still work.

Return to the integrator: check **node presence**, e.g. `any(True for _ in
root.iter('skipped'))` or `len(list(root.iter('skipped')))`, consistently for all
three statuses, and retain exact ID/count/duplicate checks. The same copied-XML
controls must reject all three flags while preserving the clean control. No test
expectation or reporter change is needed.

## Checks that passed and boundaries

Fresh origin/etalon AGENTS was read. Entire owner/failure libraries and developer
handoff guidance from the previous independent review remain applicable; no new
business condition is introduced. The exact delta from 49da is only the isolated
ci.yml override and preparation README. Product, frozen tests and requirements
are byte unchanged. Reporter `--report` flags, module paths, stop CLI and baseline
XML names/IDs were read from actual Git bytes. Baselines contain exactly ten,
four and nineteen unique passing IDs, with zero errors/skips.

Using existing PyYAML, YAML parsed successfully. All **eight** run blocks passed
`/bin/bash -n` once, and both extracted inline Python blocks compiled once.
These syntax successes do not close the two semantic findings. The controlled
XML probe was the only executed harness Python logic; tests, native compilation,
builder, self-test and CI were not run locally.

The intended matrix retains original Mac14 ARM64/Mac15 Intel x86_64 runners,
original native `build_console.py` and unpacked self-test. Explicit full SOURCE
input is checked against actual Git HEAD; harness SHA is stored separately and
run/attempt appear in artifact identity. Dispatch is confined to the integrator's
named branch and attempt one, with contents-read permissions and no deployment,
production environment or secret access. Existing builder retains Direct console
metadata, codesign verification and unpacked actual binary self-test. Archive
checks bind actual source/architecture/runtime, embedded updater bytes, measured
checksum and unchanged tracked source. Nothing modifies executable distribution
code. These source checks support the approach, but do not make the current
harness dispatchable until the findings are corrected.

Accepted SOURCE is still awaiting the distinct analyst and is not pinned here.
Integrator alone dispatches after software acceptance and independent harness
PASS. Public immutable packages/manifest, customer installation, permissions and
physical paper remain unclaimed. The old32c ARM package is not final bdd source.

Only this evidence directory was authored. No harness/product/test fix, other
worktree, WMS-652/common edit, native build/check, CI, browser, install, release,
customer message or secret operation occurred. Stash
`b396ded869bc8932ad25dc448b5f7163aa62a2f7` is preserved. Findings return through
this published handoff to the same integrator; bounded re-review follows correction.
