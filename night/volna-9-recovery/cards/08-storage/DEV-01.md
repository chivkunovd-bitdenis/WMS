# DEV · 08-storage · переделка по REVIEW.md (Finding 1 + Finding 2)

## Что реализовано

- **`POST /operations/storage/tariffs`** (HTTP 201) — принимает `{warehouse_id, amount, valid_from}` и опциональный `seller_exception: {seller_id, amount, valid_from}`; доступен только роли `fulfillment_admin`; оба INSERT выполняются в одной транзакции — сбой второго не оставляет частичного состояния.
- **`create_storage_tariff()`** — новая функция сервисного слоя в `storage_statement_service.py`; атомарно создаёт строку общего склада и (при наличии) строку-исключение для пары «селлер + склад»; ловит `IntegrityError`, откатывает транзакцию и пробрасывает `StorageStatementError("tariff_already_exists")`.

## Изменённые файлы

- `backend/app/api/storage.py` — добавлены Pydantic-модели (`SellerExceptionBody`, `TariffCreateBody`, `TariffVersionOut`, `TariffCreateOut`), импорты `date`, `require_fulfillment_admin`, `create_storage_tariff`, маршрут `POST /tariffs`.
- `backend/app/services/storage_statement_service.py` — добавлена функция `create_storage_tariff`.
- `backend/tests/test_storage_tariff_api.py` — новый тестовый файл (3 теста).

## Миграции

Нет. Таблица `billing_tariff_versions` существует; новые строки в неё вставляет сервис через существующие модели SQLAlchemy без изменения схемы.

## Тесты

| Функция | Что проверяет |
|---|---|
| `test_admin_creates_warehouse_tariff` | POST с `{warehouse_id, amount, valid_from}` → 201; ровно одна строка в `billing_tariff_versions` с `seller_id IS NULL` |
| `test_admin_creates_tariff_with_seller_exception` | Happy-path → 201, две строки; затем конфликт на втором INSERT (pre-seeded seller tariff) → 409, ноль строк у общего тарифа склада (атомарный откат) |
| `test_staff_inventory_cannot_set_tariff` | `fulfillment_staff` с правом `inventory` без роли `fulfillment_admin` → 403 |

## Гейты

Выполненные команды (из `backend/`):

```
python3 -m ruff check app/api/storage.py app/services/storage_statement_service.py tests/test_storage_tariff_api.py
→ All checks passed!

python3 -m mypy app/api/storage.py app/services/storage_statement_service.py tests/test_storage_tariff_api.py
→ 4 errors in 3 pre-existing FBS/reporting files (wildberries_credentials_service.py, fbs_stock_sync_service.py, fbs_warehouse_binding_service.py) — совпадают с зафиксированными ревьюером до правки; изменённые файлы ошибок не дали.

python3 -m pytest -q tests/test_storage_tariff_api.py
→ 3 passed in 3.35s

python3 -m pytest -q tests/test_storage_tariff_api.py tests/test_storage_statement_service.py tests/test_storage_models.py
→ 17 passed in 6.02s

python3 -m pytest -q tests/test_storage_statement_service.py tests/test_storage_models.py tests/test_storage_measurement_service.py tests/test_storage_movement_scope.py
→ 28 passed in 5.22s
```

back_guard.py, check_migrations.py — в этом worktree не присутствуют; согласно инструкции полный регресс запускается после интеграции всех карточек волны.

## Не реализовано

- **Finding 3 (REVIEW.md)** — `frontend/src/screens/ff/FfStoragePage.tsx:42`: дата начала тарифа вычисляется через UTC (`toISOString()`), а контракт требует московского времени. Файл относится к фронтенд-слою, который в этом атоме не затрагивается. Записано в «Не реализовано» для передачи в следующую итерацию фронтенда.

## Находки

- Pre-existing mypy: 4 ошибки в `wildberries_credentials_service.py`, `fbs_stock_sync_service.py`, `fbs_warehouse_binding_service.py` — совпадают с перечнем из REVIEW.md «пять ошибок в четырёх соседних FBS/reporting-файлах вне переданного списка реализации карточки». Не трогались.
