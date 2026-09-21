#!/bin/sh
# Run from this audit worktree. All schemas/data below are disposable.
# This is an executable record of the test selection, not a production command.
set -eu
PY=/Users/deniscivkunov/Projects/WMS/backend/.venv/bin/python
AUDIT_ROOT=/Users/deniscivkunov/Projects/WMS/.worktrees/wms501-performance-isolation-audit
[ "$(pwd -P)" = "$AUDIT_ROOT" ] || { echo 'Run only from the dedicated WMS-501 audit worktree'; exit 2; }
pg_run() {
  env -i PATH=/usr/bin:/bin:/usr/sbin:/sbin PYTHONPATH=backend:backend/tests \
    WMS_ALLOW_PUBLIC_REGISTRATION=true APP_ENV=development \
    JWT_SECRET_KEY=wms501-isolated-test-secret-at-least-32-characters \
    WMS_TEST_DATABASE_URL=postgresql+psycopg_async://deniscivkunov@127.0.0.1:55451/wms501_isolation \
    WMS_TEST_DATA_DIR="$AUDIT_ROOT/.audit-runtime/isolation-data" \
    "$PY" -m pytest -q "$@"
}
case "${1:-}" in
  primary)
    pg_run backend/tests/test_wms488_catalog_isolation.py backend/tests/test_wms488_home_scope.py \
      backend/tests/test_wms488_product_api_matrix.py backend/tests/test_seller_isolation.py \
      backend/tests/test_seller_wb_catalog_isolation.py backend/tests/test_wb_import_seller_isolation.py \
      backend/tests/test_fbs_print_assets.py backend/tests/test_fbs_print_job_delivery.py \
      backend/tests/test_sorting_print_wms442.py backend/tests/test_warehouse_map_api.py \
      backend/tests/test_inventory_counts.py backend/tests/test_wms489_kiz_reprints.py ;;
  secondary)
    pg_run backend/tests/test_notifications.py backend/tests/test_background_jobs.py \
      backend/tests/test_staff_users.py backend/tests/test_seller_staff_and_delete_drafts.py \
      backend/tests/test_billing_configuration_api.py backend/tests/test_billing_invoice_v2_api.py \
      backend/tests/test_billing_invoice_api.py backend/tests/test_marking_pools_read.py \
      backend/tests/test_marking_pool_products.py backend/tests/test_inbound_package_catalog.py \
      backend/tests/test_marketplace_unload_and_discrepancy_acts.py backend/tests/test_auth.py \
      backend/tests/test_product_tz_idempotency.py ;;
  probes)
    pg_run -o asyncio_mode=auto -p conftest docs/evidence/WMS-501/isolation-probes.py ;;
  *) echo 'Usage: sh docs/evidence/WMS-501/isolation-test-commands.sh primary|secondary|probes'; exit 2 ;;
esac
