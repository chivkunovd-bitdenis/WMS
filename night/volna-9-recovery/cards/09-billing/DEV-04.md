# 09-billing · backend-dev

Исправлен backend-атом 4 по замечаниям ревьюера.

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/backend/app/services/billing_configuration_service.py` — исправлена проверка контрольных цифр 12-значного ИНН; версии тарифа теперь конфликтуют на уровне услуги и селлера независимо от единицы расчёта.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/backend/tests/test_billing_configuration_service.py` — регрессии для валидного/невалидного 12-значного ИНН и пересечения тарифов по разным единицам.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/night/volna-9-recovery/cards/09-billing/DEV.md` — этот отчёт.

## Гейты

- `ruff check .` из `backend/` — НЕ ПРОЙДЕН: 84 существующих нарушения в несвязанных FBS, marketplace и scripts-файлах; затронутые billing-файлы проходят адресный `ruff check`.
- `mypy .` из `backend/` — НЕ ПРОЙДЕН из-за общего запуска после ruff-блока; адресный `mypy` для `billing_configuration_service.py`, `billing.py` и `api/billing.py` — ПРОЙДЕН.
- `pytest` из `backend/` — ПРЕРВАН по тайм-ауту рабочего прохода после `223 passed, 3 skipped`; адресные billing-тесты — `4 passed`.
- `python3 scripts/ci/back_guard.py` — НЕ ПРОЙДЕН: файл отсутствует в checkout (`scripts/ci/back_guard.py` не найден).
- `python3 scripts/ci/check_migrations.py` — НЕ ПРОЙДЕН: файл отсутствует в checkout (`scripts/ci/check_migrations.py` не найден).

## Миграции

Нет. Частичный уникальный индекс профиля ФФ уже содержит `postgresql_where` и `sqlite_where` в существующей миграции `20260822_0094_billing_financial_core.py`; новую миграцию для этого исправления не добавлял.

## Не реализовано

- Остальные находки ревьюера относятся к invoice/ledger automation, frontend или product-browser тестам и не входят в API/данные атома 4.
- Секреты, ключи, токены, `.env`, кабинеты учётных данных и боевой прод не читались и не затрагивались.
