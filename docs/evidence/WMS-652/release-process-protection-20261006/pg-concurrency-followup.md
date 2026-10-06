# WMS-652: six existing concurrency contracts on isolated PostgreSQL

Auditor B, Astra high. Product/test candidate: `d61805978b3e7878d1056c99b4e6e0823edf49a5`.
Run date: 2026-10-06, local Tbilisi time. This is the requested bounded execution followup, not a new product audit or release approval.

All six requested tests executed and passed, in two groups of three, with zero skipped, failed, or errored cases. The first group took 4.39 seconds; the scan/reprint group took 7.66 seconds. Existing product code, test cases, fixtures and expectations were unchanged. These results prove local execution on PostgreSQL; they do not claim that the six nodes are already enforced by a required CI job or protected against removal. The leading agent owns that integration.

## Isolation and an observed fixture boundary

The database was newly initialized PostgreSQL 16.14 (Homebrew), listening only on `127.0.0.1:55473`, database `wms_test_audit_three`, synthetic role `wms_test`. No preexisting database was reused. Unix sockets were disabled because this worktree's long socket path exceeds macOS's 103-byte limit. This startup issue happened before tests and was resolved by `-k ''`; it was not a product failure. Docker's daemon was unavailable, so native PostgreSQL was used. The test server was stopped after execution.

The unchanged `tests/conftest.py:89–104` accepts only loopback/CI PostgreSQL hosts and a database starting with `wms_test`; its fixtures rebuild the schema and clear records between cases. API requests use in-process `ASGITransport`, while SQLAlchemy/asyncpg makes real transactions against the isolated database. Both pytest fixture and test event loops use session scope. `-n 0` avoids sharing this database across parallel test workers; the concurrency inside each test still uses `asyncio.gather`.

The saved [network-blocking harness](pg-three-evidence/run_network_blocked.py) installs a Python socket audit hook before importing pytest/application modules. It permits only this PG endpoint, rejects external DNS and socket connections, and records attempts. This is appropriate for the selected asyncpg driver, which uses Python sockets; it is not claimed to sandbox arbitrary native libraries or subprocesses. These selected tests do not start external clients or printer processes.

The supply test's existing `enable_wb_marketplace_supplies_mock` fixture mocks supply operations and actual-composition lookup. It does **not** isolate all background integration work. Saving its synthetic token in `_setup_seller_with_token` (`test_fbs_supply_assembly.py:44–61`) schedules `autofill_requisites_after_key_saved` (`wildberries_integration.py:481–483`). That function attempts WB seller-info through `seller_marketplace_requisites_service.py:167–170` and catches unexpected errors at lines 359–362. The first group therefore recorded one attempted DNS lookup of `common-api.wildberries.ru:443`, blocked **before DNS resolution or network connection**. The tests still passed because the auxiliary autofill intentionally does not fail token saving. There were four permitted PG connections in that group. The WMS-514 group recorded two PG connections and no external attempts.

This is an isolation finding, not a false claim that marketplace integration passed. A permanent runner must retain network denial (or explicitly isolate this irrelevant background boundary) rather than assume that the supplies fixture blocks every external call. No real marketplace request, token management, production operation, printer action or external write occurred.

## What the six assertions establish

| Operator/process contract | Exact pytest node after `tests/` | Meaningful assertion | JUnit classname |
|---|---|---|---|
| Two requests add the same order to different supplies | `test_fbs_supply_assembly.py::test_fbs_supply_add_order_concurrent_race` | Exactly `[200,409]`; winner is `in_supply`; loser reports already-in-supply/bad-status; stored order has one supply | `tests.test_fbs_supply_assembly` |
| Two pick scans compete for the last available source unit | `test_fbs_picking.py::test_fbs_pick_concurrent_same_order_allocation_one_success` | Exactly `[200,409]`; picked progress is one and remains stable on reread | `tests.test_fbs_picking` |
| Two scans compete for the last unit in sorting | `test_fbs_picking.py::test_fbs_pick_sorting_last_unit_is_atomic` | Exactly `[200,409]`; picked progress one; exactly one active pick; sorting balance stays one | `tests.test_fbs_picking` |
| Concurrent redelivery of the same scan key | `test_wms514_scan_auto_print.py::test_concurrent_replay_returns_one_scan_selection` | Both 200; same scan ID and order ID; exactly one response has `replayed=true` | `tests.test_wms514_scan_auto_print` |
| Concurrent separate scan keys | `test_wms514_scan_auto_print.py::test_concurrent_distinct_scans_select_distinct_units` | Both 200; different order IDs | `tests.test_wms514_scan_auto_print` |
| Concurrent attempts to recover the same reprint | `test_wms514_scan_auto_print.py::test_concurrent_atomic_reprint_recovery_claims_only_once` | Exactly one claim returns the canonical KIZ; other returns `{claimed:false,started:false,kiz:null}` | `tests.test_wms514_scan_auto_print` |

The second node's name says “same order”, but its actual setup seeds **two** orders and one source unit; its assertions prove one allocation from that stock, not a separately explicit single-order fixture. The WMS-514 tests use product barcodes; they prove backend selection/replay/reprint claims, not the UI's technical sticker QR parsing, physical printing, or an end-to-end QR→KIZ→print→next QR journey. The sorting assertion preserves stock during picking, as required by the existing process. No purposeful mutation was needed or performed in this followup, so the six PASS results alone are not evidence that every imaginable lock removal is detected.

## Reproduction and mandatory registry handoff

Full argument lists, working directories and non-secret environment values are in [first command](pg-three-evidence/command.json) and [WMS-514 command](pg-three-evidence/514-command.json). The actual Python runtime was 3.14.3, pytest 9.1.1, pytest-asyncio 1.4.0, xdist 3.8.0. No physical-guard migrations were enabled; these cases use the existing ORM schema fixture.

Initialize a new isolated database (the paths and port below may be changed together):

```sh
initdb -D "$AUDIT_PG_DATA" -U wms_test --auth=trust --no-locale --encoding=UTF8
pg_ctl -D "$AUDIT_PG_DATA" -l "$AUDIT_PG_LOG" -o "-h 127.0.0.1 -p 55473 -k ''" start
createdb -h 127.0.0.1 -p 55473 -U wms_test wms_test_audit_three
```

Run from the candidate's `backend/`. `$AUDIT_HARNESS` points to the saved `run_network_blocked.py`; `$EVIDENCE` and `$AUDIT_APP_DATA` are dedicated output paths. Use these common options in each group:

```sh
export WMS_TEST_DATABASE_URL=postgresql+asyncpg://wms_test@127.0.0.1:55473/wms_test_audit_three
export WMS_TEST_DATA_DIR="$AUDIT_APP_DATA"
export AUDIT_PG_PORT=55473
export AUDIT_NETWORK_REPORT="$EVIDENCE/network.json"
python "$AUDIT_HARNESS" -n 0 -vv --tb=long \
  -o asyncio_default_fixture_loop_scope=session \
  -o asyncio_default_test_loop_scope=session \
  tests/test_fbs_supply_assembly.py::test_fbs_supply_add_order_concurrent_race \
  tests/test_fbs_picking.py::test_fbs_pick_concurrent_same_order_allocation_one_success \
  tests/test_fbs_picking.py::test_fbs_pick_sorting_last_unit_is_atomic \
  --junitxml="$EVIDENCE/three.xml"

export AUDIT_NETWORK_REPORT="$EVIDENCE/514-network.json"
python "$AUDIT_HARNESS" -n 0 -vv --tb=long \
  -o asyncio_default_fixture_loop_scope=session \
  -o asyncio_default_test_loop_scope=session \
  tests/test_wms514_scan_auto_print.py::test_concurrent_replay_returns_one_scan_selection \
  tests/test_wms514_scan_auto_print.py::test_concurrent_distinct_scans_select_distinct_units \
  tests/test_wms514_scan_auto_print.py::test_concurrent_atomic_reprint_recovery_claims_only_once \
  --junitxml="$EVIDENCE/514.xml"
pg_ctl -D "$AUDIT_PG_DATA" stop -m fast
```

Evidence: [first log](pg-three-evidence/three.log), [first XML](pg-three-evidence/three.xml), [scan log](pg-three-evidence/514.log), [scan XML](pg-three-evidence/514.xml), [machine-readable verification](pg-three-evidence/verification.json). XML `testcase.name` equals the function name in the table; classname is listed separately. The registry should require these six exact classname/name pairs, not just total count six. Both XML files were parsed and independently checked for exactly three cases each and no `skipped`, `failure` or `error` elements.

There was no collection/setup/test failure to diagnose or expectation to adjust. Only the blocked auxiliary seller-info attempt needs explicit preservation of the isolation boundary in CI. A final required CI execution and anti-removal/mutation enforcement remain the leading agent's release gate; this report does not weaken that gate.
