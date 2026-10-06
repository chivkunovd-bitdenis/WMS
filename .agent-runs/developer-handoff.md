# WMS-684 + WMS-586 — передача разработчика

Последний законченный шаг: устранены четыре дефекта независимого ревью dc5ee181; повторные адресные контракты и технические проверки завершены. Ветка ожидает повторного независимого ревью и продуктовой приёмки.

Реализовано:

- стикер короба приёмки содержит номер короба, селлера, номер собственной приёмки и её московскую дату; исходный штрихкод, одиночная и массовая печать сохранены;
- PDF акта приёмки добавлен рядом с существующим Excel и строится из тех же плановых/фактических строк, расхождений и итогов;
- API и экран используют PDF/Excel только для завершённой приёмки; накладная, выбор строк и настройки не менялись;
- наивный `created_at`, который SQLite возвращает без временной зоны, трактуется как UTC до перевода в московскую дату.

Повторный цикл по dc5ee181:

- PDF до размещения строки измеряет результат `insert_textbox`; явные переводы строк входят в начальную оценку, строка увеличивается на фактический дефицит высоты, а невозможность разместить поле не замалчивается;
- компактный макет с реквизитами включается только при `metadata`, поэтому грузоместо и короб отгрузки остаются в исходной сетке;
- стикер без зоны трактует дату как UTC, а номер получает через `formatHumanDocumentNumber` с fallback `—`.

Проверено:

- `cd backend && pytest -n0 tests/test_wms586_acceptance_act_contract.py tests/test_wms684_586_scope_contract.py` — 34 passed;
- `cd backend && ruff check app/api/inbound_intake.py app/services/inbound_acceptance_act_service.py` — passed;
- `cd backend && mypy app/api/inbound_intake.py app/services/inbound_acceptance_act_service.py` — passed;
- `cd frontend && npx tsc --noEmit -p tsconfig.app.json` — passed;
- целевые Vitest-контракты WMS-586, WMS-684 и Chromium/PDF-проверка с декодированием Code128 — passed.
- `cd backend && pytest -n0 -p no:cacheprovider tests/test_wms586_acceptance_act_contract.py tests/test_wms586_review_regression_contract.py -q --tb=short` — 33 passed;
- `cd frontend && npx vitest run --config ../.agent-runs/vitest.tester.config.mts --maxWorkers=1 --no-file-parallelism --no-cache src/screens/ff/FfInboundRequestView.wms684.dom.test.tsx src/screens/ff/FfInboundRequestView.wms684.review-regression.dom.test.tsx` — 16 passed;
- `cd frontend && npx vitest run --config ../.agent-runs/vitest.tester.config.mts --maxWorkers=1 --no-file-parallelism --no-cache src/screens/ff/FfInboundRequestView.wms684.pdf.test.tsx` — 2 passed;
- повторные `ruff`, `mypy` для PDF-сервиса и `tsc` фронтенда — passed.

Ограничения: в этой сессии нет разрешённого браузерного средства для просмотра рабочего экрана, поэтому визуальная CUA-проверка остаётся за аналитиком. Полный suite, build, независимое ревью, приёмка, CI и deploy этим шагом не выполнялись.
