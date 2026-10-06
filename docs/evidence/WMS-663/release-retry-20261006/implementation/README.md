# WMS-663: исправление повторной отправки после доказанного отказа

Код выполняется в постоянной worktree
`/Users/deniscivkunov/Projects/WMS/.worktrees/wms663-release-retry-fix`,
ветка `codex/wms663-release-retry-fix`. База — зафиксированный до реализации
контракт тестировщика `fe1d37d9045c7fc6e51048367a680356eff19a78`, продукт
`f68a7a93bf29f0ef07b000b918da14dab8a3a121`. Frozen tests, требования и постоянные
guards не изменены. Прочитаны актуальный origin/etalon:AGENTS.md, навыки
разработчика, текущий документ WMS-663/R11 и README тестировщика.

## Поведение

Сохранённое намерение само по себе не запрещает новую явную операцию после
`rejected`. Новая отправка получает следующую версию через существующий claim,
блокировку строки и сверку версии. Unknown/checking/preparing и завершённое
accepted остаются read-only. Старый GET не стирает доказанный отказ batch:
неполный/старый статус, несовпадение posting и ошибка чтения сохраняют возможность
нового явного действия. Проверяемый matching accepted либо validation_in_process
имеют прежний приоритет. Это правило сохранения отказа узко относится к
`all_required_absent`, не меняет классификацию отдельных документов/маркировки.

Одна существующая checked-галка обрабатывает новый клик при rejected, сохраняя
само намерение. В смешанном наборе accepted/pending только перечитываются;
повторный POST относится к rejected. Новых кнопок, окон или состояний нет.

## Команды и результаты

Из `backend/`, абсолютный существующий interpreter:

```sh
WMS_TEST_DATABASE_URL=postgresql+asyncpg://wms_test_runner@127.0.0.1:56633/wms_test_663_retry /Users/deniscivkunov/Projects/WMS/backend/.venv/bin/python -m pytest tests/test_wms663_release_retry_contract.py -q -n 0 --tb=short -o asyncio_default_fixture_loop_scope=session -o asyncio_default_test_loop_scope=session
/Users/deniscivkunov/Projects/WMS/backend/.venv/bin/python -m pytest tests/test_wms663_customs_documents_contract.py tests/test_wms663_astra_regressions.py tests/test_wms663_owner_absent_batch_contract.py tests/test_wms663_residual_behavior_contract.py tests/test_wms663_accepted_current_status.py tests/test_wms663_absent_pre_set_recovery_contract.py tests/test_wms663_requirements_completeness_contract.py tests/test_wms663_partial_accepted_status.py tests/test_wms663_accepted_read_regressions.py -q -n auto --tb=short
WMS_TEST_DATABASE_URL=postgresql+asyncpg://wms_test_runner@127.0.0.1:56633/wms_test_663_retry /Users/deniscivkunov/Projects/WMS/backend/.venv/bin/python -m pytest tests/test_wms663_customs_documents_contract.py -q -n 0 --tb=short -o asyncio_default_fixture_loop_scope=session -o asyncio_default_test_loop_scope=session
/Users/deniscivkunov/Projects/WMS/backend/.venv/bin/python -m ruff check app/services/ozon_exemplar_documents_service.py
/Users/deniscivkunov/Projects/WMS/backend/.venv/bin/python -m mypy app/services/ozon_exemplar_documents_service.py
```

Новый frozen контракт PostgreSQL: **5 PASS, 0 SKIP** (`backend-pg.log`).
Прежние девять файлов663 в SQLite: **79 PASS, 1 SKIP**, только PostgreSQL
row-lock случай (`backend-regressions.log`). Дополнительно исходный документный
контракт на PostgreSQL: **17 PASS, 0 SKIP** (`backend-existing-pg.log`), включая
его прежние реальные гонки. Ruff PASS (`backend-ruff.log`), mypy PASS
(`backend-static.log`). Полный backend suite не запускался.

Из `frontend/`:

```sh
npm run test:unit -- src/screens/v2/OzonDocumentsAbsence.release-retry.dom.test.tsx src/screens/v2/OzonDocumentsAbsence.required-orders.dom.test.tsx src/screens/v2/OzonDocumentsAbsence.incomplete-requirements.dom.test.tsx src/screens/v2/FfFbsSupplyWorkspace.wms663.dom.test.tsx src/screens/v2/OzonExemplarDocuments.wms663.residual.dom.test.tsx src/screens/v2/OzonExemplarDocuments.wms663.developer.dom.test.tsx
npx tsc --noEmit -p tsconfig.app.json
npm run build
```

**6 файлов / 23 PASS** (`frontend-tests.log`), в том числе4 новых контрактных
случая. Typecheck exit0 без output (`frontend-typecheck.log`); build PASS
(`frontend-build.log`), известное предупреждение размера JS chunks.
Зависимости — ссылка на существующий node_modules worktree тестировщика;
установок не было. Git diff --check PASS.

## Браузер

Настоящий компонент OzonDocumentsAbsence загружен через локальный Vite в Codex
In-app Browser. Синтетический harness сохраняет refused version1, accepted9,
unknown7. На открытии POST нет (`[]`). Один клик по checked галке даёт ровно
`[1]`: только rejected превращён в accepted2. Unknown/accepted соседей не
перезаписываются. Следующий обратный клик сохраняет `[1]` и checked.
Снимок `browser-mixed-after.png` показывает тот же единственный контрол;
`browser-mixed-probe.tsx.txt`/`.html.txt` сохраняют точный временный harness
(скопировать в frontend/ под именами wms663-retry-probe.tsx/.html для повтора).
Структура экрана не менялась. Проверка всей поставки/эталона «Ячейки», staging
и реальные Ozon-ответы здесь не выполнялись; снимок не выдаётся за эту проверку.

## Изолированная база и границы

Homebrew PostgreSQL17, собственный тестовый cluster:

```sh
/opt/homebrew/opt/postgresql@17/bin/initdb -D /private/tmp/wms663-release-retry-pg -A trust -U wms_test_runner --no-locale
/opt/homebrew/opt/postgresql@17/bin/pg_ctl -D /private/tmp/wms663-release-retry-pg -l /private/tmp/wms663-release-retry-pg/server.log -o '-h 127.0.0.1 -p 56633' -w start
/opt/homebrew/opt/postgresql@17/bin/createdb -h 127.0.0.1 -p 56633 -U wms_test_runner wms_test_663_retry
/opt/homebrew/opt/postgresql@17/bin/pg_ctl -D /private/tmp/wms663-release-retry-pg -m fast -w stop
```

База synthetic и loopback-only; после проверки остановлена. Данные продукта
сохранены в Git, временный cluster не является результатом реализации.
Независимое Astra review, приёмка аналитика, полный CI точного SHA и внешний
C19 остаются отдельными этапами ведущего. Main/etalon, deployment, production,
внешний SET/ship, физическая печать и управление секретами не затрагивались.
