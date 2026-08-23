# DEV · 08-storage · backend-dev · атом 3

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/backend/app/api/storage.py` — ответ `POST /operations/storage/tariffs` дополнен списком `recalculated_statements` с пересчитанными открытыми черновиками и новыми суммами.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/backend/app/services/storage_statement_service.py` — сохранение тарифа теперь после успешного `flush` пересчитывает затронутые черновики выбранного склада и пересекающегося периода в той же транзакции; зафиксированные statements исключены из выборки.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/backend/tests/test_storage_tariff_api.py` — сценарий смены тарифа проверяет ответ POST, повторную загрузку, границы склада/даты, нулевой черновик, неизменность fixed-документа и финансовой строки, а также отказ сохранения до пересчёта.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/night/volna-9-recovery/cards/08-storage/DEV.md` — отчёт backend-dev по атому 3.

## Что реализовано

- Эндпоинт `POST /operations/storage/tariffs`: после атомарной записи тарифа возвращает только затронутые открытые черновики в `recalculated_statements`, уже с действующими ставками и суммами; fixed-документы в ответ не попадают.
- Сервис `reprice_open_storage_drafts()`: выбирает draft-statements текущего tenant только по выбранному складу и периодам, пересекающим дату новой общей или индивидуальной ставки, и рассчитывает серверный preview без публикации финансовых строк.
- Сервис `create_storage_tariff()`: выполняет INSERT-проверку через `flush`, затем пересчёт и только после этого `commit`; конфликт INSERT делает rollback до запуска пересчёта, ошибка пересчёта откатывает новые версии тарифа.

## Миграции

Нет.

## Тесты

- Расширен `test_new_tariff_reprices_open_draft_on_reload`: успешный POST возвращает два открытых черновика выбранного склада с новой суммой и ставкой, включая нулевой расчёт.
- Тот же тест доказывает, что черновик другого склада, открытый черновик периода до даты действия и fixed-statement не пересчитываются.
- Контрольная `BillingLedgerEntry` fixed-документа сохраняет прежние `rate=1.00` и `amount=1.00`; для draft-документов новые ledger-строки не создаются.
- Повторная запись тарифа на конфликтующую дату получает 409, не создаёт вторую версию и не меняет доступный расчёт.

## Гейты

```text
cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/backend && ruff check app/api/storage.py app/services/storage_statement_service.py tests/test_storage_tariff_api.py
```

Результат: `All checks passed!`.

```text
cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/backend && mypy --follow-imports=silent app/api/storage.py app/services/storage_statement_service.py tests/test_storage_tariff_api.py
```

Результат: `Success: no issues found in 3 source files`.

```text
cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/backend && pytest -q tests/test_storage_tariff_api.py::test_new_tariff_reprices_open_draft_on_reload
```

Финальный результат целевого сценария: `1 passed in 1.00s`.

```text
cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/backend && pytest -q tests/test_storage_tariff_api.py
```

Финальный результат назначенного файла: `11 passed in 10.47s`.

```text
cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage && git diff --check -- backend/app/api/storage.py backend/app/services/storage_statement_service.py backend/tests/test_storage_tariff_api.py night/volna-9-recovery/cards/08-storage/DEV.md
```

Результат: exit 0, ошибок пробелов нет.

`python3 scripts/ci/back_guard.py` не запускался: атом не добавляет новый маршрут, а расширяет ответ существующего `POST /operations/storage/tariffs`.

`python3 scripts/ci/check_migrations.py` не запускался: миграций нет.

Полные `pytest`, `ruff check .` и `mypy .` не запускались: они прямо запрещены для этого атомарного шага.

Попытка сохранить атом отдельным коммитом:

```text
cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage && git add -- /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/backend/app/api/storage.py /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/backend/app/services/storage_statement_service.py /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/backend/tests/test_storage_tariff_api.py /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/night/volna-9-recovery/cards/08-storage/DEV.md
```

Результат: Git не смог создать `/Users/deniscivkunov/Projects/WMS/.git/worktrees/lane-2-08-storage1/index.lock`: `Operation not permitted`. Файлы не попали в индекс; `night/volna-9-recovery/JOURNAL.md` не затрагивался и не включался.

## Не реализовано

- Атомы 4–6 из `FEATURES.md` не выполнялись.
- Frontend, сквозной Playwright-сценарий, модели, миграции, внешние API, production и живой кабинет Wildberries не затрагивались.
- Отдельные сохраняемые поля суммы или ставки в `StorageStatement` не добавлялись: по архитектурному контракту черновик остаётся вычисляемым preview, а неизменяемый денежный снимок существует только в `BillingLedgerEntry` после фиксации.

## Находки

Нет. Секреты, ключи, токены, `.env`, кабинеты учётных данных и production не читались и не использовались.

## Блокеры

Backend-реализация и целевые тесты завершены без блокеров. Сохранение отдельного commit заблокировано правами среды на общий Git-каталог за пределами разрешённой рабочей копии; commit SHA не создан, изменения остаются только в рабочем дереве.
