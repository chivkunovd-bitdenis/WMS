# DEV · 01-wb-marking · атом 5 · rework

## Что реализовано

- Эндпоинты: новых и изменённых эндпоинтов нет; устаревший одиночный `GET /api/v3/orders/{orderId}/meta` отсутствует.
- Сервис `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-01-wb-marking/backend/app/services/wildberries_client.py`: удалённая ранее функция `fetch_marketplace_order_meta` и её вызовы отсутствуют; комментарий mock-хранилища очищен от упоминания удалённого одиночного `GET`.
- Сервис `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-01-wb-marking/backend/app/services/wildberries_fbs_client.py`: batch `POST /api/marketplace/v3/orders/meta` подтверждён как единственный путь чтения метаданных.
- Находки `REVIEW.md`: четыре исправления соседних атомов присутствуют в текущей ветке и повторно подтверждены названными ревью-сценариями; дополнительного изменения их файлов в атоме 5 не потребовалось.

## Миграции

- Нет.

## Тесты

- Новые тесты не добавлялись: атом удаляет мёртвое чтение, а существующие клиентские тесты полностью покрывают разрешённые операции записи/удаления и batch-чтение.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-01-wb-marking/backend/tests/test_wildberries_client.py` и `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-01-wb-marking/backend/tests/test_wildberries_marketplace_fbs_client.py`: подтверждены клиентские контракты, включая batch-чтение `metaDetails`.
- Адресные тесты из `REVIEW.md`: подтверждены полный сырой снимок, контрактный `check_status`, отсутствие legacy fallback и конкурентная однократность `wb_orphaned`.

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-01-wb-marking/backend/app/services/wildberries_client.py`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-01-wb-marking/night/volna-9-recovery/cards/01-wb-marking/DEV.md`

## Гейты

- `ruff check app/services/wildberries_client.py tests/test_wildberries_client.py tests/test_wildberries_marketplace_fbs_client.py` из `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-01-wb-marking/backend` — пройдено: `All checks passed!`.
- `mypy app/services/wildberries_client.py` из `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-01-wb-marking/backend` — пройдено: `Success: no issues found in 1 source file`.
- `pytest -q tests/test_wildberries_client.py tests/test_wildberries_marketplace_fbs_client.py` из `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-01-wb-marking/backend` — пройдено: `26 passed in 0.24s`.
- `pytest -q tests/test_fbs_marking.py::test_fbs_marking_autopoll_batches_unique_ids_and_skips_partial_or_failed_batches tests/test_fbs_marking.py::test_fbs_marking_sync_updates_check_status tests/test_fbs_kiz.py::test_fbs_marking_wb_meta_decision_is_safe_and_preserves_raw_detail tests/test_fbs_kiz.py::test_fbs_marking_partial_wb_row_is_unknown_without_fresh_check_time tests/test_fbs_kiz.py::test_fbs_marking_orphaned_audit_is_created_once_for_concurrent_and_repeated_missing` из `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-01-wb-marking/backend` — пройдено: `13 passed in 22.69s`.
- `if rg -n 'fetch_marketplace_order_meta' backend/app backend/tests; then exit 1; else printf '%s\\n' 'PASS: fetch_marketplace_order_meta отсутствует в backend/app и backend/tests'; fi` из `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-01-wb-marking` — пройдено: определений и вызовов нет.
- `rg -n 'fetch_marketplace_orders_meta_batch|MARKETPLACE_ORDERS_META_BULK_PATH' backend/app/services backend/tests/test_wildberries_marketplace_fbs_client.py` из `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-01-wb-marking` — пройдено: batch-функция определена, вызывается сервисами и покрыта тестами.
- `python3 scripts/ci/back_guard.py` — неприменим: новый роут не добавлялся.
- `python3 scripts/ci/check_migrations.py` — неприменим: миграция не добавлялась.

## Не реализовано

- Нет: атом 5 выполнен буквально; новый fallback и новое пользовательское действие не добавлялись.

## Находки

- В `CONTRACT.md` нет отдельного раздела `API и данные`; для rework использованы однозначные backend-границы атома 5 из `FEATURES.md`, решения `ARCH.md` и проверяемые требования `REVIEW.md`.
- Секреты, ключи, токены, `.env`, кабинеты учётных данных, боевой прод и живой кабинет Wildberries не читались и не затрагивались.

## Блокеры

- Нет.
