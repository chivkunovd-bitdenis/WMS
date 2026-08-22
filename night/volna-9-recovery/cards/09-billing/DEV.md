# 09-billing — backend-dev · rework атома 09-A

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/backend/tests/test_billing_models.py` — реальная SQLite-проверка: второй charge с тем же tenant/source event и второе reversal для одной исходной строки отклоняются ограничениями базы.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/backend/tests/test_billing_financial_core_migration.py` — проверка, что финансовое ядро присутствует в единственной Alembic-цепочке и в checkout нет нескольких heads.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/night/volna-9-recovery/cards/09-billing/DEV.md` — отчёт этого rework-прохода.

## Миграции

Нет новых миграций. Существующая `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/backend/alembic/versions/20260822_0094_billing_financial_core.py` уже создаёт общий набор billing-таблиц; адресная проверка подтверждает одну текущую вершину `20260822_0095`.

## Тесты

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/backend/tests/test_billing_models.py` — уникальность исходного события и уникальность reversal на уровне БД.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/backend/tests/test_billing_financial_core_migration.py` — единственная Alembic-линия финансового ядра.

## Гейты

- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/backend && ruff check app/models/billing.py tests/test_billing_models.py tests/test_billing_financial_core_migration.py` — PASS.
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/backend && mypy app/models/billing.py` — PASS.
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/backend && pytest -q tests/test_billing_models.py tests/test_billing_financial_core_migration.py` — PASS, 4 passed (одно предупреждение Alembic о конфигурации `path_separator`).
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/backend && alembic heads` — PASS, `20260822_0095 (head)`.
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing && python3 scripts/ci/back_guard.py` — не выполнен: файла нет по этому абсолютному пути (exit 2).
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing && python3 scripts/ci/check_migrations.py` — не выполнен: файла нет по этому абсолютному пути (exit 2).
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/backend && git diff --check` — PASS.

## Не реализовано

- Находки `REVIEW.md` по API, сервисам, задачам, реальным storage-statement, UI и e2e не относятся к модели и миграции атома 09-A; они не менялись.
- Изменять `down_revision` на отсутствующие в этом checkout миграции 03/07-A нельзя: Alembic перестанет собирать локальный граф. Вместо этого добавлена проверка единственного head; при интеграции соседних миграций она не позволит оставить несколько вершин.

## Находки

- Секреты, ключи, токены, `.env`, кабинеты учётных данных и боевой прод не читались и не затрагивались.
