# WMS-652 · independent literal contract migration review, 07.10.2026

**PASS for the bounded test literal and protected digest migration. No final
SOURCE pin approval is issued at this stage.** Reviewed immutable
`ce212ec254a87a4f5570b549d6aa721db971b5ef`, separate testwriter contract
`88343975e13f8819d6b81cd03cddbba1d67db078`, included throughf12f9b410.
Same independent Sol6.1/high reviewer session01a11389-3a47-7ec0-b74c-b8d920bfcca8;
no nested agents or broad audit. No blocking defect found in this exact delta.

The earlier `f4d095aa4280c89075bfafcef2883f88e17c25d4` review missed the protected
test constant in test_ci_release_additions.py that still demanded d618 after
the workflow reference changed to independently accepted25eb. This precise gap
caused the actual guards-job failure in fullCI37548248403, tested merge
`ac845328b27b5be265962695e10766efddef339e`:131 infrastructure tests,130PASS/1FAIL.
The saved raw job-log hash and target/summary lines were independently matched.
It is a missed literal contract migration, not a new software/business defect.
The old software/reference/pin9dae approval remains historical; it does not
approve ce212 or any new pin automatically.

Independent byte and Python AST comparison confirms **exactly one SHA literal
replacement** d618→`25ebc6fe13384a55cf1f2b7e5e4054bb862d002d` inside the existing
full hardcoded command. Normalizing that one string makes the complete module
AST identical. assertIn and its guard argument, the second JUnit assertion,
all three case IDs, other two methods and every other byte remain unchanged.
No dynamic HEAD/reference selection, catch, early return, skip or relaxed
expectation was introduced. The exact25eb acceptance input was verified from
distinct analyst4eb81c; this does not substitute for acceptance of the new
migration by the next distinct analyst.

Saved testwriter BEFORE is2PASS/1 targeted assertion RED; AFTER is3PASS/0skip.
The preserved negative control executes the same actual target test with only
module.ROOT redirected to an automatically removed workflow copy whose reference
is reverted to d618. Its raw failure is the exact25eb assertIn mismatch, not an
import/setup error. The original/counterexample workflow hashes and failure
receipt match. This control was inspected, not rerun.

This reviewer executed **only once**:

```sh
python3 -B -m unittest scripts.ci.tests.test_ci_release_additions -v
```

Result: **3PASS,0failure/error/skip**, exit0; raw three-tests.log and receipt are
preserved here. Sparse checkout initially lacked the workflow: preflight stopped
before unittest, then only that tracked file was restored from exactce212 without
changing its bytes. No initial failed/repeated test execution occurred.

All229 regular Git paths/modes and SHA256 independently match the policy.
Policy SHA256 is`8a3e69096cf9823309d1060269071c5b391256780142d0f930907d41c4933abd`.
The only protected digest change against approved9dae is this test:
`9fe9ca325e8fa264e609449ab70cd3742fd5d54af501ea54bfe3c69a8742af4a`.
All other228 protected bytes, all21 complete suite definitions/1173 cases,
frozen scope51/CLI, native7/peer2/raster3, product and workflow remain unchanged.
App/package/migration diff to25eb is empty; C5 source is byte-identical.
Previousbfba accepted fullC5/positive causal-prefix evidence is preserved and
requires no repeat or new no-loss condition.

This technical PASS is ready for the **next distinct analyst's bounded migration
acceptance**, then the same reviewer can perform the tiny final exact-SHA/pin
check. Current installed pin9dae/main8df is the parent-provided state, not a new
activation readback here. No main/config/pin edit, finalSOURCE approval, CI job
cancellation/dispatch, dependency installation, other131/130/51/71 tests, build,
browser/C5, provider/print/deploy or physical proof occurred. The original full
CI remains historical and is not made green by these3 local tests.

Only this new evidence directory has Git changes. source-checks.py reproducibly
reads immutable Git blobs and receipts without rerunning tests; source-checks.json
records the exact source/policy/digest, case IDs, preserved protections, actual
three-test execution and explicit pending-stage boundaries.
