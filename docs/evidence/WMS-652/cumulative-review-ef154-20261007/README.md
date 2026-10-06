# Independent cumulative process review, exact ef154

Target: `ef154664e365644f4ba002c6e8affc5607fae725`. Previous accepted review source: `65049df62d2bac87932fc5349f6326caec43dea5`. Report: [WMS-652-cumulative-process-review-20261007.md](../../../reviews/WMS-652-cumulative-process-review-20261007.md).

The reviewer used a private detached fixture under the permanent review worktree. It contained exact target scripts/policy/requirements, used existing local Python 3.14/pytest 9.0.2 and installed TypeScript, and was removed after checks. No dependencies were installed. Execution was sequential with one local worker, without xdist.

Recreate the source fixture from the review checkout:

```sh
git worktree add --detach --no-checkout .review-fixture-ef154 ef154664e365644f4ba002c6e8affc5607fae725
git -C .review-fixture-ef154 restore --source=HEAD --worktree -- scripts/ci guards docs/requirements docs/reviews/contract-corrections
cd .review-fixture-ef154
python3 -m pytest -q scripts/ci/test_check_task_documents.py scripts/ci/tests/test_promote_guards.py -k 'accepted_report_without_report_commit or wms687_ancillary_correction_with_report or exact_chain or two_by_two or binding_canary or protected_wms687 or unprotected_legacy or wms680' --junitxml=../docs/evidence/WMS-652/cumulative-review-ef154-20261007/targeted.xml
cd ..
python3 docs/evidence/WMS-652/cumulative-review-ef154-20261007/replay_red.py
python3 docs/evidence/WMS-652/cumulative-review-ef154-20261007/audit.py
node docs/evidence/WMS-652/cumulative-review-ef154-20261007/integration_probe.cjs
git worktree remove --force .review-fixture-ef154
```

`targeted.xml` and `targeted.log`: this review's 21 passing named tests and 29 subtests, 129.35 seconds. XML has 21 testcase elements and suite aggregate 50; subtests are not 29 additional policy IDs.

`independent-red.log`: seven new positive frozen contracts independently replayed against exact previous 65049 implementation; all seven fail/error as expected. The RED script verifies the count and does not change tests.

`audit.py`/`audit.json`: immutable Git policy/hash/mode/old-ID comparison; approved frozen-definition comparison; actual collection mapping; workflow dependency and attempt-artifact inspection; source comparisons; historical JUnit/Vitest parsing; six real parser rejections of incomplete/skipped/failed/wrong/extra C6 reports. Recorded historical executions are attributed separately. Prior/current report coverage is compared as sets; no combined CI receipt is manufactured.

`integration_probe.cjs`/`integration-probe.json`: five addressed runtime probes compile exact target pure TypeScript modules in memory. The script reads the existing sibling integration TypeScript installation. Input mutation, WB color fallback, Ozon external identifier/null/undefined fallback, assembly path and separate article/color/size print columns are checked. No React/browser/physical print or product files are changed.

Historical developer source evidence remains at `docs/evidence/WMS-652/final-closure-20261007` in target ef154; actual PG evidence remains at `docs/evidence/WMS-681/postgres-c6`. Raw historical files were parsed directly from target Git blobs. This directory is independent review evidence, **not full CI, product acceptance, final P/S or release proof**.
