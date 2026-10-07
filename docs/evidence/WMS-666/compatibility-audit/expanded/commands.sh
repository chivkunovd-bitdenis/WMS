#!/bin/sh
# Recorded commands. Run one target at a time from this audit worktree's root.
# Never run `server` concurrently with either PostgreSQL pytest target.
set -eu
PY=/Users/deniscivkunov/Projects/WMS/backend/.venv/bin/python
export WMS_TEST_DATABASE_URL=postgresql+psycopg_async://deniscivkunov@127.0.0.1:5432/wms_test_666_compatibility_audit
E=docs/evidence/WMS-666/compatibility-audit/expanded
case "${1:-help}" in
  actions)
    "$PY" -m pytest -q backend/tests/test_fbs_kiz.py backend/tests/test_fbs_kiz_applied.py \
      backend/tests/test_wms518_kiz_pool_return.py backend/tests/test_wms635_kiz_no_wb_wait.py \
      backend/tests/test_wms642_kiz_no_locks_handover.py backend/tests/test_fbs_skip_reprint.py \
      backend/tests/test_packaging_fact_contract.py backend/tests/test_fbs_packaging_integration.py \
      backend/tests/test_fbs_print_assets.py backend/tests/test_ozon_box_positions.py \
      backend/tests/test_ozon_box_assembly.py backend/tests/test_ozon_fbs_process_contract.py \
      backend/tests/test_fbs_packing_box.py backend/tests/test_fbs_packaging_fulfillment.py \
      --disable-warnings --junitxml="$E/actions-postgres.xml" > "$E/actions-postgres.txt" 2>&1 ;;
  transfer-original)
    "$PY" -m pytest -q backend/tests/test_fbs_supply_transfer.py backend/tests/test_wms581_supply_transfer.py \
      backend/tests/test_wms560_tape_pending_kiz.py --disable-warnings \
      --junitxml="$E/transfer-postgres.xml" > "$E/transfer-postgres.txt" 2>&1 ;;
  transfer-valid-actor)
    PYTHONPATH=backend/tests:backend "$PY" -m pytest -p wms666_transfer_pg_fixture -q \
      backend/tests/test_fbs_supply_transfer.py backend/tests/test_wms581_supply_transfer.py \
      --disable-warnings --junitxml="$E/transfer-postgres-valid-actor.xml" \
      > "$E/transfer-postgres-valid-actor.txt" 2>&1 ;;
  frontend)
    cd frontend
    node node_modules/vitest/vitest.mjs run src/components/MarkingPrintDialog.test.ts \
      src/components/MarkingPrintDialog.confirmOrder.test.ts \
      src/components/MarkingPrintDialog.availability.dom.test.tsx \
      src/screens/v2/FbsScanPrintToggles.dom.test.tsx src/screens/v2/fbsPdfPrintTape.test.ts \
      src/utils/printMarkingCodeLabel.test.ts src/utils/printPreparedQr.test.ts \
      --maxWorkers=1 --no-file-parallelism > "../$E/manual-frontend.txt" 2>&1 ;;
  frontend-transfer)
    cd frontend
    node node_modules/vitest/vitest.mjs run src/screens/v2/FbsTransferSupplyDialog.test.tsx \
      src/utils/printPackagingInstructions.test.ts src/utils/printProductThermalLabel.test.ts \
      --maxWorkers=1 --no-file-parallelism > "../$E/transfer-document-frontend.txt" 2>&1 ;;
  server)
    PYTHONPATH=backend "$PY" backend/tests/wms666_audit_server.py ;;
  vite)
    node frontend/node_modules/vite/bin/vite.js --config frontend/tests-e2e/wms652-critical/vite.config.ts ;;
  browser)
    # Start server and Vite in separate terminals first; wait until /idle answers.
    # Examples: WMS666_VARIANTS=delete-before-claim,delete-after-claim
    # WMS666_VARIANTS=replace-before-claim,replace-after-claim
    # WMS666_VARIANTS=manual-then-delete-scan
    # WMS666_VARIANTS=rapid-scans,flags-after-claim
    # WMS666_VARIANTS=multi-seller WMS666_ENTRIES=supply_ids
    # WMS666_VARIANTS=clear-partial WMS666_ENTRIES=supply_id
    # WMS666_VARIANTS=controls
    WMS652_EVIDENCE="$E/replay" node frontend/tests-e2e/wms652-critical/compatibility-browser.audit.mjs ;;
  ozon)
    # Vite only, synthetic HTTP boundary. Expected RED on current product.
    WMS652_EVIDENCE="$E/ozon-replay" node frontend/tests-e2e/wms652-critical/compatibility-ozon.audit.mjs ;;
  *) echo 'Choose actions|transfer-original|transfer-valid-actor|frontend|frontend-transfer|server|vite|browser|ozon' ;;
esac
