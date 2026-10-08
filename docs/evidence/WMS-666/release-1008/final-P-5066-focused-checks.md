# Focused checks for product candidate `5066f1dc3c362935fe31292671ca6fad2a4205bf`

These checks run after the candidate commit was published. The Python tests use
the repository's isolated SQLite pytest fixture, not the native-print PostgreSQL
database.

| Command | Result |
|---|---|
| `/Users/deniscivkunov/Projects/WMS/backend/.venv/bin/pytest -q backend/tests/test_fbs_kiz.py backend/tests/test_wms666_ozon_quantity_print_bindings.py backend/tests/test_wms666_rejected_exact_reprint_validation.py` | `125 passed, 6 warnings in 108.62s` |
| `/Users/deniscivkunov/Projects/WMS/backend/.venv/bin/ruff check app/api/fbs_kiz.py app/services/fbs_print_binding_service.py app/services/fbs_order_tape_print_service.py` | passed |
| `git diff --check` | passed before commit |
| `./node_modules/.bin/tsc --noEmit -p tsconfig.app.json` | exit 0 |
| `./node_modules/.bin/vitest run src/screens/v2/FfFbsSupplyWorkspace.reprintKiz.dom.test.tsx -t 'стрелка открывает|обычная печать' --config vitest.config.ts --reporter verbose --testTimeout 10000 --pool=threads --maxWorkers=1 --minWorkers=1` | `2 passed` (`FfFbsSupplyWorkspace.reprintKiz.dom.test.tsx`, 95.30s cold transform) |

The reprint UI assertion checks that the exact selected marking ID is carried
into the late-validation context; the backend contract checks that explicit
current rejected WB reprints pass while ordinary rejected bindings, replaced
generations, and unlinked supplies remain rejected. The Ozon API contract checks
the actual prepared tape output against the same late validator.

Exact-P recovery DOM checks are saved in `final-P-5066-targeted-ui.log`. The
combined Vitest run covered the partial-tape warning after ack-only recovery,
HTTP-200 missing-QR same-window retry, and late response fencing after switching
supplies: `3 passed, 27 skipped` in 93.56s. The skips are other cases in those
same test files and are not whole-file or CI results.
