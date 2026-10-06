#!/usr/bin/env bash
# Execute unchanged contracts that SQLite cannot prove. Synthetic CI databases only.
set -euo pipefail
[[ "${GITHUB_ACTIONS:-}" == true && "$(uname -s)" == Linux ]]
cd "$(dirname "$0")/../../backend"
evidence="${RUNNER_TEMP:?}/release-postgres"
mkdir -p "$evidence"
cleanup() {
  rm -f tests/test_wms663_remote_c10.py
  docker rm -f wms-ci-662-contract wms-ci-662-f6 >/dev/null 2>&1 || true
}
trap cleanup EXIT
start_pg() {
  local name="$1" port="$2" db="$3"
  docker run --detach --name "$name" --network host --tmpfs /var/lib/postgresql/data \
    -e POSTGRES_USER=wms_test -e POSTGRES_DB="$db" -e POSTGRES_HOST_AUTH_METHOD=trust \
    postgres:16 -p "$port" -h 127.0.0.1
  for attempt in {1..40}; do
    if docker exec "$name" pg_isready -h 127.0.0.1 -p "$port" -U wms_test -d "$db"; then return; fi
    sleep 1
  done
  docker logs "$name"
  return 1
}
start_pg wms-ci-662-contract 55462 wms_test_662
start_pg wms-ci-662-f6 55467 wms_test_662_f6
WMS_TEST_DATABASE_URL=postgresql+asyncpg://wms_test@127.0.0.1:55462/wms_test_662 \
  pytest -n 0 -q tests/test_wms662_postgres.py --junitxml="$evidence/662.xml"
WMS_TEST_DATABASE_URL=postgresql+asyncpg://wms_test@127.0.0.1:55467/wms_test_662_f6 \
  pytest -n 0 -q tests/test_wms662_cancellation_lock_order.py --junitxml="$evidence/662-f6.xml"
cp ../scripts/ci/wms663-proof/c10_mixed.py tests/test_wms663_remote_c10.py
WMS_TEST_DATABASE_URL=postgresql+psycopg_async://postgres:fixture-only@127.0.0.1:5432/wms_test_517 \
  pytest -n 0 -q \
    tests/test_wms663_customs_documents_contract.py::test_wms663_two_sessions_commit_one_posting_version_once \
    tests/test_wms663_remote_c10.py \
    tests/test_wms669_seller_catalog_once.py::test_c10_postgresql_json_sizes_and_stock \
    tests/test_wms469_stock_dialog_backend.py::test_c24_parallel_complete_saves_never_mix_rules \
    tests/test_wms469_stock_dialog_backend.py::test_c23_parallel_same_binding_create_keeps_one_row \
    tests/test_fbs_supply_from_orders.py::test_parallel_from_orders_one_order_one_supply \
    --junitxml="$evidence/663-669-670-683.xml"
WMS_TEST_DATABASE_URL=postgresql+psycopg_async://postgres:fixture-only@127.0.0.1:5432/wms_test_517 \
  pytest -n 0 -q tests/test_wms663_release_retry_contract.py \
    -o asyncio_default_fixture_loop_scope=session \
    -o asyncio_default_test_loop_scope=session \
    --junitxml="$evidence/663-release-retry.xml"
WMS_CI_PG_PORT=5432 WMS_CI_NETWORK_REPORT="$evidence/fbs-network.json" \
WMS_TEST_DATABASE_URL=postgresql+asyncpg://postgres:fixture-only@127.0.0.1:5432/wms_test_517 \
  python ../scripts/ci/run_isolated_pytest.py -n 0 -q \
    tests/test_fbs_supply_assembly.py::test_fbs_supply_add_order_concurrent_race \
    tests/test_fbs_picking.py::test_fbs_pick_concurrent_same_order_allocation_one_success \
    tests/test_fbs_picking.py::test_fbs_pick_sorting_last_unit_is_atomic \
    tests/test_wms514_scan_auto_print.py::test_concurrent_replay_returns_one_scan_selection \
    tests/test_wms514_scan_auto_print.py::test_concurrent_distinct_scans_select_distinct_units \
    tests/test_wms514_scan_auto_print.py::test_concurrent_atomic_reprint_recovery_claims_only_once \
    -o asyncio_default_fixture_loop_scope=session \
    -o asyncio_default_test_loop_scope=session \
    --junitxml="$evidence/fbs-concurrency.xml"
python - "$evidence" <<'PY'
import pathlib, sys, xml.etree.ElementTree as ET
root = pathlib.Path(sys.argv[1])
for name, expected in [('662.xml', 10), ('662-f6.xml', 4), ('663-669-670-683.xml', 6), ('663-release-retry.xml', 5), ('fbs-concurrency.xml', 6)]:
    tree = ET.parse(root / name)
    cases = tree.findall('.//testcase')
    assert len(cases) == expected, (name, len(cases), expected)
    for tag in ['skipped', 'failure', 'error']:
        assert not tree.findall('.//' + tag), (name, tag)
    print(f'{name}: {len(cases)} executed, no skipped/failure/error')
PY
