# Independent evidence: ef154 → 6da0

Reviewed immutable SHA: `6da0eb63b143d71d789c25a20ee04e3c49cbf14b`.
Prior accepted SHA: `ef154664e365644f4ba002c6e8affc5607fae725`.
Overall verdict: **FAIL**; existing four green scope tests miss two real forbidden-path cases.

`reproduce_scope.py` retrieves the immutable candidate module and uses three isolated Git histories. Run with `python3 docs/evidence/WMS-652/delta-review-6da0-20261007/reproduce_scope.py`. Exit 0 confirms reproduction of the defect; it does not mean candidate PASS. Results: `scope-canaries.json` and `scope-canaries.log`.

The reviewer created a sparse detached worktree at the exact candidate, restoring only required immutable files. No integration worktree changes, installs or full suite execution were performed. Own sequential commands inside that fixture:

```sh
python3 -m pytest -q scripts/ci/test_check_task_documents.py scripts/ci/tests/test_promote_guards.py -k 'wms681_integration_fixture or protected_ci_shards_junit or protected_wms663_c10_copy' --junitxml=../docs/evidence/WMS-652/delta-review-6da0-20261007/targeted.xml
python3 -m pytest -q backend/tests/test_wms684_586_scope_contract.py --junitxml=../docs/evidence/WMS-652/delta-review-6da0-20261007/scope-existing.xml
python3 -m pytest --collect-only -q scripts/ci/tests/test_backend_shards.py scripts/ci/tests/test_backend_shard_failclosed.py scripts/ci/tests/test_ci_release_additions.py scripts/ci/tests/test_backend_shard_redis_setup.py scripts/ci/tests/test_promote_guards.py scripts/ci/tests/test_process_contracts.py scripts/ci/tests/test_process_deploy_gate.py scripts/ci/tests/test_server_process_gate.py scripts/ci/test_check_task_documents.py
```

Results: 12 named tests + 7 subtests passed; 4 scope tests passed. Collection: 166 process cases (162 registered, four C10 cases pending registration). Collection is not execution. Own `audit.py` runs from the permanent review checkout and loads the process parser directly from the immutable Git blob; the detached fixture is not needed to replay this audit. Run with `python3 docs/evidence/WMS-652/delta-review-6da0-20261007/audit.py`. It checks policy retention, frozen test ASTs, actual workflow commands, the migration graph and pure PG protocol helpers. It records pending hash/case closure and confirms the real C10 report's extra cases are rejected. It does not apply migrations or execute real PG/backend mocks.

`audit.json`/`audit.log` record that audit. The three pending policy hashes and four pending IDs are explicit; the audit's bounded PASS is not an overall candidate PASS. `targeted.xml`/`.log`, `scope-existing.xml`/`.log` are own execution reports.

`integration-681-binding-green.xml`, `integration-script-module-green.xml`, `integration-c10-alias-green.xml` are copies of existing coordinator reports, not new reviewer executions. `integration-scope-evidence.md` preserves the specifically requested previously untracked developer account. `integration-provenance.json` records their original paths and SHA-256, plus bounded raw historical CI RED excerpts and whole-log digests. It does not bind historical runs to the later reviewed SHA. No secrets or database connection values are captured.

Published af7 evidence contains a narrative of warning-injected real-PG 1 PASS, not its new raw XML/log. This review independently checks the protocol change and retained race assertions, and does not substitute an older receipt for that run. The published WB 20 PASS and migration 4 PASS likewise remain attributed results; own review checks their code and graph as stated in the report.

Final P/S, full CI, pending WMS-673/PDF and seller-info C4 changes are excluded. Prior ef154 PASS remains within its original scope.
