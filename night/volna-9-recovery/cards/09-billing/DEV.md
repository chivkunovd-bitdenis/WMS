# 09-billing — backend-dev

## Изменённые файлы

- /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/backend/app/services/billing_ledger_service.py — подбор тарифа по календарной дате МСК и безопасная постановка ledger-записи внутри savepoint.
- /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/backend/app/services/inbound_intake_service.py — начисление при финализации коробочного и сохранённого распределения; передача исполнителя.
- /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/backend/app/api/inbound_intake.py — передача user.id в оба финальных backend-пути.
- /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/backend/tests/test_billing_ledger_service.py — тест границы календарного месяца МСК.

## Миграции

Нет.

## Тесты

- Адресные: `13 passed` для ledger, distribution и box putaway сценариев.
- Добавлен тест выбора тарифа для операции `2026-03-01 00:30` по МСК.

## Гейты

- `ruff check .` — FAIL на существующих несвязанных нарушениях в baseline; адресный ruff изменённых файлов — PASS.
- `mypy .` — FAIL на существующих несвязанных ошибках в baseline; ошибок в изменённых файлах в выводе нет.
- `pytest` — FAIL в baseline на `tests/test_fbs_supply_from_orders.py` (полная прогонка остановлена после обнаружения unrelated failure); адресный набор PASS (13 тестов).
- `python3 scripts/ci/back_guard.py` — не запущен: файла нет в этой рабочей копии по требуемому пути.
- `python3 scripts/ci/check_migrations.py` — не запущен вместе с back_guard из-за отсутствия `scripts/ci/back_guard.py`.

## Не реализовано

- Остальные находки REVIEW.md относятся к UI, billing API/invoice или соседним атомам и намеренно не менялись.
- Новых роутов и миграций в этом атоме нет.

## Блокеры

- Реализация проверена, но commit невозможен: Git не смог создать `/Users/deniscivkunov/Projects/WMS/.git/worktrees/lane-3-09-billing1/index.lock` из-за запрета доступа к общем worktree metadata. Поэтому результат локальный, SHA отсутствует.
