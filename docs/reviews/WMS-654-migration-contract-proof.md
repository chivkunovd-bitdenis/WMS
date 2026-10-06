# WMS-654 C8 harness result

State: locally verified, intentionally uncommitted and unstaged.  The controller
must create the separate test-only commit after the frontend developer's commit.

## Change boundary

Only `backend/tests/test_wms654_migration.py` changed.  The fragile selection of
every migration absent from product baseline `4b298efc95be7b4b6b7fe5665be9f3671f1fe747`
was replaced with `task_owned_tier_migrations()`, which selects by the stable
filename `20261007_2302_wms654_location_tier.py` from an actual Alembic
`ScriptDirectory`.  The target migration is the nullable-tier-only module whose
revision is `20261007_2302` and whose `down_revision` is `20261001_2301`.

No existing C8 assertion changed: the diff has no added or removed `assert` line.
The old identity/code/barcode/coordinate equality, nullable tier and old `None`,
new saved-list coordinates, and barcode-resolve checks remain exactly as before.
If the task migration is absent, selection is empty and the existing assertion
that the upgrade leaves a persisted `tier` still fails; there is no skip, xfail,
or pass-on-error path.

`ruff check tests/test_wms654_migration.py` and `git diff --check` pass.

## Common-base scope proof

Read-only Git object used for the accepted common base:
`f71b99c0f19bdbf48e8e0b95b62aefe8709307fc`.

An ignored harness at `.agent-runs/c8-combined-alembic` was assembled from that
object's `backend/alembic` tree, then supplied only the current WMS-654 migration
file.  A real `ScriptDirectory` loaded from that combined directory was passed to
the new helper.  `git diff --name-only 4b298efc..f71b99c0f19bdbf48e8e0b95b62aefe8709307fc -- backend/alembic/versions`
identified these nine unrelated files:

- `20260912_0305_assistant_messages.py`
- `20260913_2200_assistant_executor_attempts.py`
- `20260925_0433_merge_assistant_staging.py`
- `20260929_0589_merge_staging_etalon.py`
- `20260929_0590_merge_wms_588_and_staging_heads.py`
- `20260930_0566_ff_section_permissions.py`
- `20260930_0567_product_primary_print_barcode.py`
- `20261001_0612_merge_staging_urgent.py`
- `20261003_0001_merge_staging_etalon.py`

The actual selected module list was exactly
`[20261007_2302_wms654_location_tier.py]`; it intersected none of those nine.
No unrelated migration was upgraded in the shared test database.

This proves the selection boundary over common-base revisions.  The successful
C8 API/migration run below uses the current checkout's models and metadata; it is
not a claim that the full common-base application model has been exercised.  The
integrator must repeat the real integration check after the cherry-pick.

## PostgreSQL receipts

The requested sequential (`-n 0`) command produced
`.agent-runs/c8-pg-receipts.xml`.  Its `pytest` suite reports `tests=3`,
`failures=0`, `errors=0`, and `skipped=0`:

- `test_c8_migration_preserves_legacy_rows_and_new_list_coordinates` — passed
- `test_c4_postgresql_concurrent_requests_have_one_winner[False]` — passed
- `test_c4_postgresql_concurrent_requests_have_one_winner[True]` — passed

Using the same pre-import wiring as pytest's `tests.conftest`, the test engine
reported `dialect=postgresql`, `driver=postgresql+asyncpg`, host `127.0.0.1`, and
database `wms_test_654_tester_20261006_1840`.  This is PostgreSQL evidence, not
a SQLite substitute.  C4 itself has an explicit PostgreSQL-only guard; with zero
skips both parametrized receipts exercised that branch.

## Limits

No full suite, xdist parallel run, frontend build, dependency install, source
change outside the owned test file, staging, commit, push, PR, merge, deploy, or
write to the root-owned integration checkout was performed.  Current checkout
HEAD during verification: `a3953f971652e47793bccd9cf2da7d95cc0937c5` on
`codex/wms654-product-20261006`.
