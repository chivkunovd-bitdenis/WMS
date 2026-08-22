# DEV · 01-wb-marking · атом 5/5 · rework после JUDGE

## Что реализовано

- Эндпоинты: новых и изменённых backend-роутов нет; устаревший внешний вызов `GET /api/v3/orders/{orderId}/meta` удалён ранее и на текущем `HEAD` отсутствует.
- Сервис `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-01-wb-marking/backend/app/services/wildberries_client.py`: функции `fetch_marketplace_order_meta` и её вызовов больше нет; одиночные операции записи метаданных не изменены.
- Сервис `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-01-wb-marking/backend/app/services/wildberries_fbs_client.py`: `fetch_marketplace_orders_meta_batch` через batch `POST /api/marketplace/v3/orders/meta` подтверждён как единственный путь чтения метаданных заказов.
- Находка `JUDGE.md` относится только к неподнятому живому UI-стенду; дефектов разрешённого backend-файла или слоя атома 5 в вердикте нет, поэтому необоснованный кодовый diff не создавался.

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-01-wb-marking/night/volna-9-recovery/cards/01-wb-marking/DEV.md` — восстановлен обязательный отчёт текущего атома после удаления внешним оркестратором.

Backend-реализация атома уже сохранена в истории текущей ветки:

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-01-wb-marking/backend/app/services/wildberries_client.py` — удаление функции в `db5503842415145860237d989d9a403dc834c288`, очистка последнего устаревшего упоминания в `a70c4f03a622c41495c94b39ab33333455bb3343`.

## Миграции

- Нет.

## Тесты

- Новые тесты не добавлялись: новый роут или поведение не вводились, а атом удаляет мёртвую клиентскую функцию.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-01-wb-marking/backend/tests/test_wildberries_client.py` — проверены импорты и действующие операции клиента, включая запись метаданных.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-01-wb-marking/backend/tests/test_wildberries_marketplace_fbs_client.py` — проверены импорт и контракт актуального batch-чтения метаданных, включая успешный ответ, повтор 429 и ошибки ответа.

## Гейты

- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-01-wb-marking/backend && ruff check app/services/wildberries_client.py tests/test_wildberries_client.py tests/test_wildberries_marketplace_fbs_client.py` — успешно: `All checks passed!`.
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-01-wb-marking/backend && mypy app/services/wildberries_client.py` — успешно: `Success: no issues found in 1 source file`.
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-01-wb-marking/backend && pytest -q tests/test_wildberries_client.py tests/test_wildberries_marketplace_fbs_client.py` — успешно: `28 passed in 0.15s`.
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-01-wb-marking && if rg -n 'fetch_marketplace_order_meta' backend/app backend/tests --glob '*.py'; then exit 1; else printf '%s\n' 'PASS: fetch_marketplace_order_meta отсутствует в backend/app и backend/tests'; fi` — успешно: определений и вызовов нет.
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-01-wb-marking && rg -n 'fetch_marketplace_orders_meta_batch|MARKETPLACE_ORDERS_META_BULK_PATH' backend/app/services backend/tests/test_wildberries_marketplace_fbs_client.py` — успешно: batch-функция определена, вызывается сервисами и покрыта тестами.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-01-wb-marking/scripts/ci/back_guard.py` — не запускался: атом не добавляет и не меняет роуты.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-01-wb-marking/scripts/ci/check_migrations.py` — не запускался: атом не добавляет миграцию.

## Не реализовано

- Браузерный стенд и снимки зон `S-03`, `S-14`, `S-15` из находки `JUDGE.md` не поднимались: это Product Browser Review, а не разрешённый backend-слой атома 5.
- Новые fallback-пути, пользовательские действия, роуты, модели и миграции не добавлялись.

## Находки

- В `CONTRACT.md` нет отдельного раздела `API и данные`; rework ограничен однозначным backend-контрактом атома 5 из `FEATURES.md` и уже принятой реализацией в истории ветки.
- Секреты, ключи, токены, `.env`, кабинеты учётных данных, боевой прод и живой кабинет Wildberries не читались и не затрагивались.

## Блокеры

- Нет для backend-атома 5.
