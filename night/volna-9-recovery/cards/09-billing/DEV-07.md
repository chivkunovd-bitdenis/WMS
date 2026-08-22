# 09-billing — backend-dev, атом 7

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/backend/app/services/billing_ledger_service.py`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/backend/app/services/inbound_intake_service.py`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/backend/app/services/marketplace_unload_service.py`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/backend/app/services/marketplace_unload_pick_service.py`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/backend/app/api/inbound_intake.py`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/backend/app/api/marketplace_unload_requests.py`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/backend/tests/test_billing_ledger_service.py`

Операционные начисления создаются в той же транзакции при первом `done` приёмки и первом `shipped` Marketplace-отгрузки. Тариф и его снимок выбираются по дате факта с приоритетом тарифа селлера; отсутствие тарифа сохраняет `unpriced`-строку и не блокирует склад. Повтор исходного документа возвращает существующую запись и не добавляет дубль. Внутренняя отгрузка не изменялась.

## Гейты

- `ruff check .` — BLOCKED: 84 существующие ошибки в репозитории; изменённые файлы проходят адресную проверку, кроме существующего B007 в `marketplace_unload_pick_service.py`.
- `mypy .` — BLOCKED: 22 ошибки, включая существующие ошибки в 7 файлах; после исправления неверной передачи аргумента в `create_cargo_places` ошибок от этого атома не остаётся.
- `pytest` — BLOCKED по времени: полный набор прерван после 63 тестов за 42.73 секунды; `tests/test_billing_ledger_service.py` — PASS, 2 passed.
- `back_guard.py` — BLOCKED: `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/scripts/ci/back_guard.py` отсутствует в checkout.
- `check_migrations.py` — BLOCKED: `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/scripts/ci/check_migrations.py` отсутствует в checkout.

## Не реализовано

- Новые API-роуты и внутренняя отгрузка не добавлялись: они не входят в атом 7.
- Полная гонка двух параллельных финальных запросов защищена существующим уникальным ограничением ledger; отдельный retry после `IntegrityError` не добавлялся.

## Находки

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/night/volna-9-recovery/JOURNAL.md` содержит несвязанное изменение; его не включал.
- Секреты, ключи, токены, `.env`, кабинеты учётных данных и боевой прод не читались и не затрагивались.
