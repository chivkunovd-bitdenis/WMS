# S-03 local verification

- `pytest backend/tests/test_fbs_ozon_lane.py backend/tests/test_marketplace_foundation.py backend/tests/test_fbs_worklist_query_count.py -q` — 22 passed.
- `npm run test:unit -- --run src/screens/v2/fbsApi.test.ts src/screens/v2/FfFbsSupplyWorkspace.test.ts src/screens/v2/FbsSupplyCreateDialog.test.ts` — 9 passed.
- `npx tsc --noEmit -p tsconfig.app.json` and `npm run build` — exit 0.
- `ruff check --ignore RUF100` on changed backend files — exit 0. The repository's ordinary `ruff` also reports three pre-existing unused file-level `noqa` directives outside this slice.
- Browser evidence is not recorded: the in-app Browser binding is unavailable because its installed package has no required `browser-client.mjs`; the started local Playwright run did not reach an exit code before the command window elapsed.

No live Ozon request or stock mutation was made.

## Correction round 1/2

- Одна нейтральная кнопка синхронизации обходит пары `seller × marketplace`; неподключённая пара пропускается, а подключённый Ozon проходит только через fake transport и возвращает human `403/code 7`.
- Order label/QR выбирает adapter по `supply.marketplace`; WB-path сохранён, Ozon-path использует только fake boundary. Логика Честного знака не менялась.
- Смешанный WB/Ozon выбор блокирует обе кнопки создания/добавления; серверный `different_marketplace` сохранён.
- Для Ozon заблокированы все коробные обработчики и controls, включая «убрать из короба».
- `pytest backend/tests/test_fbs_ozon_lane.py backend/tests/test_marketplace_foundation.py backend/tests/test_fbs_order_tape_qr_only.py backend/tests/test_fbs_stock_models.py -q`: 30 passed, exit 0.
- `pytest backend/tests/test_fbs_print_assets.py backend/tests/test_fbs_order_tape_qr_only.py backend/tests/test_fbs_cancellations.py -k 'print or qr_only or sync_fbs_order_statuses_endpoint' -q`: 9 passed, 7 deselected, exit 0.
- Frontend unit: 13 passed, exit 0; `npx tsc --noEmit -p tsconfig.app.json`: exit 0.
- Ruff на затронутых backend-файлах: exit 0 с `--ignore RUF100`.
