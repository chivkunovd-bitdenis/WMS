# DEV · 08-storage · атом 6 · исправления ревью

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/backend/app/services/storage_measurement_service.py` — расчёт теперь режет положительный остаток также в момент смены версии габаритов; поздний обмер не применяется к более раннему остатку, а любой положительный интервал без объёма остаётся проблемой.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/backend/app/api/storage.py` — запрос rebuild сразу отклоняет неполную пару года и месяца, несуществующий и будущий месяц; при отсутствии периода по-прежнему передаётся предыдущий календарный месяц МСК.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/backend/tests/test_storage_measurement_service.py` — добавлены проверки разбиения непрерывного остатка сменой габаритов и запрета ретроактивного применения позднего обмера.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/night/volna-9-recovery/cards/08-storage/DEV.md` — обязательный отчёт backend-dev по текущему атому.

## Миграции

Нет.

## Тесты

- `test_volume_segments_split_continuous_stock_at_dimension_change` — литро-дни используют прежний объём до даты новой версии и новый после неё.
- `test_volume_segments_do_not_apply_later_measurement_to_earlier_stock` — отсутствие исторического объёма до первого обмера не подменяется текущим значением товара.

## Гейты

- `cd backend && ruff check app/services/storage_measurement_service.py app/api/storage.py tests/test_storage_measurement_service.py` — `All checks passed!`.
- `cd backend && pytest -q tests/test_storage_measurement_service.py` — `5 passed in 0.02s`.
- `cd backend && mypy app/services/storage_measurement_service.py app/api/storage.py` — не прошёл из-за 48 уже существующих ошибок вне расчёта: отсутствует внешний `app.models.billing` (находка ревью о зависимости 09-A), а также существующие типовые ошибки `storage_statement_service` и его зависимостей.
- `cd backend && mypy --follow-imports=skip app/services/storage_measurement_service.py app/api/storage.py` — не прошёл из-за 7 существующих типовых ошибок API-модуля: FastAPI/Pydantic импортируются как `Any` в этом режиме и у старого `_statement_out` нет полной аннотации.
- `git diff --check` — пройден без вывода.
- `python3 scripts/ci/back_guard.py` — неприменим: новый роут не добавлялся, исправлена валидация существующего `/operations/storage/measurements/rebuild`.
- `python3 scripts/ci/check_migrations.py` — неприменим: миграции не добавлялись и не изменялись.

## Не реализовано

- Находка ревью №3 о `InventoryMovement.seller_id/warehouse_id`, backfill и writer-контракте не изменялась: это внешний фундамент 07-A, прямо исключённый границей атома 6.
- Находки №2 и №5–9 о фиксации, тарифах, ledger, печатном DTO и API габаритов относятся к другим атомам и финансовому фундаменту 09-A; в этом атоме деньги не создаются.
- Находки по секретам, ключам, токенам, `.env` и кабинетам учётных данных отсутствуют: они не читались и не использовались.
