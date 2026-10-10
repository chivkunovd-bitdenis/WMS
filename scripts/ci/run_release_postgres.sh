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
    public.ecr.aws/docker/library/postgres:16 -p "$port" -h 127.0.0.1
  for attempt in {1..40}; do
    if docker exec "$name" pg_isready -h 127.0.0.1 -p "$port" -U wms_test -d "$db"; then return; fi
    sleep 1
  done
  docker logs "$name"
  return 1
}
start_pg wms-ci-662-contract 55462 wms_test_662
start_pg wms-ci-662-f6 55467 wms_test_662_f6

# The PostgreSQL suites below are independent diagnostics. Keep database startup
# fail-fast because every later test depends on it, but collect each suite's
# failure so one red contract does not hide the rest of the primary errors.
failures=()
run_suite() {
  local label="$1"
  shift
  if "$@"; then
    printf 'PASS: %s\n' "$label"
  else
    local status=$?
    printf 'FAIL: %s (exit %s)\n' "$label" "$status"
    failures+=("$label (exit $status)")
  fi
}

run_suite 'WMS-662 PostgreSQL contracts' env \
  WMS_TEST_DATABASE_URL=postgresql+asyncpg://wms_test@127.0.0.1:55462/wms_test_662 \
  pytest -n 0 -q tests/test_wms662_postgres.py --junitxml="$evidence/662.xml"
run_suite 'WMS-662 cancellation lock ordering' env \
  WMS_TEST_DATABASE_URL=postgresql+asyncpg://wms_test@127.0.0.1:55467/wms_test_662_f6 \
  pytest -n 0 -q tests/test_wms662_cancellation_lock_order.py --junitxml="$evidence/662-f6.xml"
cp ../scripts/ci/wms663-proof/c10_mixed.py tests/test_wms663_remote_c10.py
run_suite 'WMS-663/669/670/683 PostgreSQL contracts' env \
  WMS_TEST_DATABASE_URL=postgresql+psycopg_async://postgres:fixture-only@127.0.0.1:5432/wms_test_517 \
  pytest -n 0 -q \
    tests/test_wms663_customs_documents_contract.py::test_wms663_two_sessions_commit_one_posting_version_once \
    tests/test_wms663_remote_c10.py \
    tests/test_wms669_seller_catalog_once.py::test_c10_postgresql_json_sizes_and_stock \
    tests/test_wms469_stock_dialog_backend.py::test_c24_parallel_complete_saves_never_mix_rules \
    tests/test_wms469_stock_dialog_backend.py::test_c23_parallel_same_binding_create_keeps_one_row \
    tests/test_fbs_supply_from_orders.py::test_parallel_from_orders_one_order_one_supply \
    -o asyncio_default_fixture_loop_scope=session \
    -o asyncio_default_test_loop_scope=session \
    --junitxml="$evidence/663-669-670-683.xml"
run_suite 'WMS-663 release retry contract' env \
  WMS_TEST_DATABASE_URL=postgresql+psycopg_async://postgres:fixture-only@127.0.0.1:5432/wms_test_517 \
  pytest -n 0 -q tests/test_wms663_release_retry_contract.py \
    -o asyncio_default_fixture_loop_scope=session \
    -o asyncio_default_test_loop_scope=session \
    --junitxml="$evidence/663-release-retry.xml"
run_suite 'FBS concurrency PostgreSQL contracts' env \
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
run_suite 'WMS-744 inbound product lock ordering on PostgreSQL' env \
  WMS_TEST_DATABASE_URL=postgresql+asyncpg://postgres:fixture-only@127.0.0.1:5432/wms_test_517 \
  pytest -n 0 -q tests/test_wms744_inbound_product_lock_order.py \
    --junitxml="$evidence/744.xml"
report_status=0
python - "$evidence" <<'PY' || report_status=$?
import pathlib, sys, xml.etree.ElementTree as ET
root = pathlib.Path(sys.argv[1])
expected_reports = [('662.xml', 10), ('662-f6.xml', 4), ('663-669-670-683.xml', 6), ('663-release-retry.xml', 5), ('fbs-concurrency.xml', 6), ('744.xml', 2)]
failed = False
for name, expected in expected_reports:
    path = root / name
    if not path.is_file():
        print(f'{name}: missing execution report')
        failed = True
        continue
    try:
        tree = ET.parse(path)
    except ET.ParseError as error:
        print(f'{name}: malformed execution report: {error}')
        failed = True
        continue
    cases = tree.findall('.//testcase')
    problems = [tag for tag in ['skipped', 'failure', 'error'] if tree.findall('.//' + tag)]
    if len(cases) != expected or problems:
        print(f'{name}: {len(cases)} executed; expected {expected}; report issues={problems}')
        failed = True
    else:
        print(f'{name}: {len(cases)} executed, no skipped/failure/error')
if failed:
    sys.exit(1)
PY
if (( ${#failures[@]} > 0 || report_status != 0 )); then
  printf 'Independent PostgreSQL failures: %s\n' "${failures[*]:-none}"
  exit 1
fi
