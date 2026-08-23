# 09-billing — backend-dev, атом 6

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/backend/tests/test_billing_invoice_api.py` — добавлены два HTTP-сценария формирования счёта: при отсутствии профиля ФФ API возвращает `missing_ff_profile`, при отсутствии профиля плательщика-селлера — `missing_seller_profile`.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/docs/blockers/S-31.md` — единая устаревшая блокировка `missing_profile` разделена на два фактических серверных кода; для каждого сохранены шесть обязательных полей и отдельный путь снятия.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/night/volna-9-recovery/cards/09-billing/DEV.md` — этот отчёт атома.

## Миграции

Нет.

## Тесты

- `test_form_invoice_api_returns_missing_ff_profile_reason` проверяет ответ `POST /billing/invoices/{seller_id}/2026-07/form` без профиля ФФ.
- `test_form_invoice_api_returns_missing_seller_profile_reason` проверяет тот же HTTP-контракт без профиля плательщика-селлера.

## Гейты

- В `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/backend`: `ruff check tests/test_billing_invoice_api.py` — пройдено (`All checks passed!`).
- В `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/backend`: `mypy tests/test_billing_invoice_api.py` — пройдено (`Success: no issues found in 1 source file`).
- В `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/backend`: `pytest -q tests/test_billing_invoice_api.py` — пройдено (`7 passed`).
- `python3 scripts/ci/back_guard.py` — не применим: новый маршрут не добавлялся.
- `python3 scripts/ci/check_migrations.py` — не применим: миграции не добавлялись.

## Не реализовано

Нет: выполнен только атом 6 из `FEATURES.md`. Находки ревью о денежных копейках, фронтенд-переходах и московском периоде относятся к отдельным атомам и не менялись.

## Находки

Нет.
