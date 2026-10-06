# WMS-663: отдельный контракт до исправления release blocker

База продукта: `f68a7a93bf29f0ef07b000b918da14dab8a3a121`.
Worktree: `/Users/deniscivkunov/Projects/WMS/.worktrees/wms663-retry-contract-20261006`.
Ветка: `codex/wms663-retry-contract-20261006`. Продуктовый код не изменён.

R11 уже разрешает новую явную запись после доказанного отказа. Проверки
продолжают R11/C8/C10/C16 в актуальном интерфейсе одной галки. Новый бизнес-вопрос
не требуется. Checked означает сохранённое намерение; его нельзя приравнивать
к accepted или использовать как вечный запрет retry после определённого отказа.

## RED точной базы

- `backend-red.log`: SQLite — 1 failed, 2 passed, 2 skipped. Оба SKIP относятся
  только к реальным блокировкам PostgreSQL; SQLite не считается их доказательством.
- `backend-pg-red.log`: отдельная PostgreSQL17 — **2 failed, 3 passed, 0 skipped**.
  Retry после определённого429 не делает новый SET; rejected batch concurrency
  не достигает нового snapshot/claim. Первоначальный batch concurrency PASS.
- `frontend-red.log`: реальный `OzonDocumentsAbsence` через React DOM —
  **1 failed, 3 passed**. После rejected и reopen галка остаётся checked;
  следующий явный клик не отправляет POST версии1. Unknown/checking/accepted
  сохраняют checked без нового POST.

Внешняя граница Ozon заменена FakeMarketplaceTransport; сервис, сохранение
в базе, новая SessionLocal и компонент галки настоящие. В retry-тесте Ozon
отвечает accepted только **после нового SET**. GET/reopen после429 остаётся
read-only. Полный payload сравнивается с существующим owner batch контрактом:
реальные synthetic product/exemplar ID, marks, weight и соседние документы
сохраняются. Отдельные unrelated metadata также проверяются после accepted.

## Точные команды

Из `backend/` (абсолютный interpreter существующего окружения, без установки):

```sh
/Users/deniscivkunov/Projects/WMS/backend/.venv/bin/python -m pytest tests/test_wms663_release_retry_contract.py -q -n 0 --tb=short
WMS_TEST_DATABASE_URL=postgresql+asyncpg://wms_test_runner@127.0.0.1:56633/wms_test_663_retry /Users/deniscivkunov/Projects/WMS/backend/.venv/bin/python -m pytest tests/test_wms663_release_retry_contract.py -q -n 0 --tb=short -o asyncio_default_fixture_loop_scope=session -o asyncio_default_test_loop_scope=session
/Users/deniscivkunov/Projects/WMS/backend/.venv/bin/python -m ruff check tests/test_wms663_release_retry_contract.py
```

Локальная PostgreSQL17 поднята установленным Homebrew `initdb`/`pg_ctl` на
отдельном порту56633, role `wms_test_runner`, database `wms_test_663_retry`.
Это исключительно synthetic тестовая база, не production/staging. Инициализация
`initdb -D <temporary-test-cluster> -A trust -U wms_test_runner --no-locale`,
запуск `pg_ctl -D <temporary-test-cluster> -l <temporary-test-cluster>/server.log
-o '-h 127.0.0.1 -p 56633' -w start`, создание `createdb -h 127.0.0.1 -p 56633
-U wms_test_runner wms_test_663_retry`. После фиксации cluster остановлен.
В CI можно использовать уже выделенный postgres service и loopback/CI
`wms_test*` database. **Указать обе session loop настройки и -n0**: без них
pooled asyncpg между function loops даёт setup ошибки. Полный файл содержит
ровно5 backend cases; PostgreSQL release proof обязан выполнить все без SKIP.

Из `frontend/`:

```sh
npm run test:unit -- src/screens/v2/OzonDocumentsAbsence.release-retry.dom.test.tsx
```

Зависимости взяты символьной ссылкой на уже существующие `node_modules`
соседнего release candidate; новых пакетов не устанавливалось.

## Доказательство сохранных защит через временную порчу

На собственной worktree временно убраны guards из продукта, затем исходные
файлы восстановлены побайтно в `finally`. Окончательный Git diff не содержит
изменений продукта. Это не реализация исправления.

Backend mutation: в `save_absent_exemplar_documents` убрать ранний pending/
selected read-only возврат, в `claim_exemplar_write` убрать pending и version
fencing. Команда PostgreSQL выше с `-k 'unknown or accepted or initial'` даёт
**3 failed, 2 deselected, 0 skipped**: новый контракт ловит повтор unknown,
повтор accepted и второй SET двух сессий одной версии.
`backend-preservation-mutation-red.log` сохраняет содержательные ошибки.

DOM mutation: в `choose` убрать pending/selected read-only ветку и в
`onChange` вызвать choose независимо от enabled. Команда frontend выше
с `-t 'never POST again'` даёт **3 failed, 1 skipped по фильтру**: три состояния
ловят появление POST после reverse click. Это фильтр mutation-прогона, не
SKIP окончательного frontend-контракта. После восстановления вся baseline
матрица снова дала **1 failed, 3 passed**.
`frontend-preservation-mutation-red.log` сохраняет ошибки на запрете POST.

## Передача разработчику

Ожидания двух новых файлов и предыдущих контрактов не менять. Исправить
серверную разрешённость новой явной операции после определённого отказа и её
достижимость через одну существующую галку, сохранив unknown/accepted защиту,
current version, один полный SET, durable intent и соседние данные.

После исправления выполнить этот контракт с PostgreSQL без SKIP, новый DOM
файл и существующие owner batch/UI guards. Потом отдельное независимое ревью,
приёмка аналитика и полный CI точного SHA. Эти RED-доказательства не являются
приёмкой, живым Ozon циклом C19, разрешением внешнего SET/ship или деплоем.
