# DEV · 08-storage · атом 2 · rework

## Что реализовано

- Эндпоинты: нет, атом не добавляет и не меняет маршруты.
- Сервис `catalog_service._record_dimension_event`: повторные WB-наблюдения по-прежнему дедуплицируются, а каждый ручной обмер `manual` / `container_override` создаёт новую неизменяемую версию и не переписывает дату или автора прежней записи.
- Модель `ProductDimensionEvent`: уникальность fingerprint ограничена источником `wb`, поэтому одинаковые осознанные ручные обмеры в разные моменты сохраняются отдельными событиями.

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/backend/app/models/product_dimension_event.py`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/backend/app/services/catalog_service.py`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/backend/alembic/versions/20260822_0095_product_dimension_events.py`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/backend/tests/test_product_dimension_history.py`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/night/volna-9-recovery/cards/08-storage/DEV.md`

## Миграции

- `20260822_0095` — добавляет снимок действующего источника габаритов в `products` и журнал `product_dimension_events`; в rework уникальный индекс `(product_id, fingerprint)` сделан частичным для `source = 'wb'`, чтобы дедуплицировать импорт, но не терять повторные ручные обмеры.

## Тесты

- `test_repeated_manual_measurement_keeps_both_immutable_observations` — проверяет сценарий ревью: одинаковый ручной обмер после возврата к WB создаёт новую версию с новым автором, не меняет аудит первой версии и оставляет ровно одну действующую запись.
- `tests/test_product_dimension_history.py` и `tests/test_wb_import_dimensions.py` — проверяют ручную и WB-историю, единственную действующую версию, сохранность ручного значения при импорте, возврат к WB и отсутствие дублей повторного WB-наблюдения.

## Гейты

- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/backend && ruff check app/models/product.py app/models/product_dimension_event.py app/services/catalog_service.py alembic/versions/20260822_0095_product_dimension_events.py tests/test_product_dimension_history.py tests/test_wb_import_dimensions.py` — успешно, `All checks passed!`.
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/backend && mypy app/models/product.py app/models/product_dimension_event.py` — успешно, `Success: no issues found in 2 source files`.
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/backend && mypy --follow-imports=skip --disable-error-code=misc --disable-error-code=no-any-return app/services/catalog_service.py` — успешно, `Success: no issues found in 1 source file`. Обычный запуск `mypy app/models/product.py app/models/product_dimension_event.py app/services/catalog_service.py` рекурсивно остановился на четырёх ранее существовавших ошибках в `wildberries_credentials_service.py`, `fbs_stock_sync_service.py` и `fbs_warehouse_binding_service.py`; эти файлы атом не меняет.
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/backend && pytest -q tests/test_product_dimension_history.py tests/test_wb_import_dimensions.py` — успешно, `8 passed in 8.64s`.
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage && python3 scripts/ci/check_migrations.py` — не запущен: файла `scripts/ci/check_migrations.py` в этой рабочей копии нет, команда завершилась с кодом 2.
- `back_guard.py` не применим: новый маршрут не добавлялся.
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage && git diff --check` — успешно, замечаний нет.
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage && git add backend/alembic/versions/20260822_0095_product_dimension_events.py backend/app/models/product_dimension_event.py backend/app/services/catalog_service.py backend/tests/test_product_dimension_history.py night/volna-9-recovery/cards/08-storage/DEV.md && git diff --cached --check && git commit -m "fix(storage): preserve repeated manual measurements"` — не выполнено: Git не смог создать `/Users/deniscivkunov/Projects/WMS/.git/worktrees/lane-2-08-storage1/index.lock` (`Operation not permitted`).

## Не реализовано

- Находки ревью №1–4 и №6–10 относятся к API списка, биллингу, writer движения, расчёту хранения и frontend; они не входят в файлы и слой атома 2.
- Миграция `0095` по обязательному порядку `ARCH-CROSS.md` продолжает внешнюю миграцию `0094` карточки 03. Файл `0094` в этой изолированной рабочей копии отсутствует, поэтому сквозной `alembic upgrade` здесь не выдаётся за выполненную проверку.
- Сохранить rework отдельным Git-коммитом не удалось из-за запрета среды на запись в метаданные worktree; результат локально реализован, но не опубликован и не может считаться сохранённым по SHA.

## Блокеры

- Интеграционная проверка цепочки миграций требует предшествующую карточку 03 и отсутствующий в checkout скрипт `scripts/ci/check_migrations.py`.
- Git-коммит заблокирован правами среды на общий каталог метаданных worktree.

## Находки

- Секреты, ключи, токены, `.env`, кабинеты учётных данных и боевой production не читались и не затрагивались.
