# WMS-652: frozen accepted-reference contract migration

Actual fullCI37548248403 attempt1 on merge
`ac845328b27b5be265962695e10766efddef339e` had130PASS/1FAIL in131 infrastructure
tests. The failing assertion still expected the old d618 command, while the
workflow already uses the exact accepted product
`25ebc6fe13384a55cf1f2b7e5e4054bb862d002d`. The completed job log was read only;
its hash and exact failure/summary lines are in `provenance.json`.

Same separate testwriter session, clean permanent checkout base
`eabfad3656ec7ac923c6014657d4bf8ba5e63400`. Fresh origin/etalon rules and testwriter
skill read; no nested agents. Exact25eb was approved by distinct analyst
`4eb81c378babf081b3342f3bf36ac17bf136a8bf`; reviewer
`f4d095aa4280c89075bfafcef2883f88e17c25d4` approved the earlier workflow/SOURCE9dae
migration. Those approvals establish the reference, not approval of this new
test-file delta or a future SOURCE.

Only one SHA literal in `test_ci_release_additions.py` changes d618→25eb.
The full command remains hardcoded; assertIn, its guard argument, the second
JUnit assert and the other two functions are retained. `migration.diff` and
`byte-ast-proof.json` prove exact byte substitution and one changed Python AST
constant; all three IDs/assertion methods and every other byte are preserved.
`cases.json` lists the original three fully qualified IDs.

```sh
python3 -B -m unittest scripts.ci.tests.test_ci_release_additions -v
python3 -B docs/evidence/WMS-652/accepted-reference-contract-migration-20261007/negative-control.py
```

`before.log`:3 tests,2PASS/1FAIL/0skip, exit1, exactly the old-reference assertion.
`after.log`:3PASS/0FAIL/0skip, exit0. The negative control executes the **same actual
target test**, overriding only module.ROOT to an automatically removed untracked
workflow copy with the trusted ref reverted to d618. Its raw
`old-reference-counterexample.log`:1FAIL/0errors/0skip on the exact25eb command.
No tracked workflow or product was corrupted. This preserves refusal of the
obsolete baseline rather than accepting HEAD or an arbitrary current candidate.

`frozen-hashes.json` proves unchanged workflow, scope CLI/frozen51 test file,
raster3/peer2/native7 and browser contract bytes. The raster file additionally
matches accepted40df exactly. No other tests/product/workflow/policy/requirements/
backlog changed; no131/71/fullCI/browser/build/install or other-job rerun occurred.
Only this test file and new evidence directory are committed. CI/policy digest,
independent technical review, analytical delta, final SOURCE approval and pin
activation remain with the integrator and distinct roles. No self-review,
acceptance, main merge, configuration change or deployment is claimed.
