# Backend Dev — 03-no-distribution-mode — атом 1

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-03-no-distribution-mode/backend/app/models/fbs_supply.py` — сохраняемые nullable-поля времени включения режима и пользователя, включившего режим.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-03-no-distribution-mode/backend/alembic/versions/20260821_0094_fbs_supplies_boxes_without_distribution.py` — добавляющая миграция колонок и внешнего ключа на `users` с `SET NULL`.

Изменения атома уже присутствовали в рабочей копии из коммита `bf6bc61`; сервис, API и UI не изменялись.

## Миграции

- `20260821_0094` — добавляет `fbs_supplies.boxes_without_distribution_at`, `fbs_supplies.boxes_without_distribution_by_user_id` и внешний ключ на `users`.

## Тесты

- Целевой тест `backend/tests/test_fbs_packing_box.py` запускался системным `pytest`, но процесс не вернул результат в доступное время.

## Гейты

- `ruff` — PASS для двух изменённых backend-файлов (`All checks passed!`). Полный `ruff check .` не подтверждён из-за отсутствующего проектного окружения.
- `mypy` — NOT RUN: проектное виртуальное окружение отсутствует; системный запуск полного набора не получил результата.
- `pytest` — NOT CONFIRMED: системный целевой запуск не вернул результат; проектное виртуальное окружение отсутствует.
- `back_guard.py` — NOT RUN: `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-03-no-distribution-mode/scripts/ci/back_guard.py` отсутствует.
- `check_migrations.py` — NOT RUN: `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-03-no-distribution-mode/scripts/ci/check_migrations.py` отсутствует.

## Не реализовано

- Сервис переключения, API/workspace и UI не входят в атом 1 и не изменялись.
- Массовая миграция legacy-ключей `no-distribution:` не входит в контракт атома; совместимость остаётся для следующих слоёв.

## Находки

- Секреты, ключи, токены и `.env` не читались.
- Боевой прод и кабинет Wildberries не затрагивались.

## Блокеры

- Нет блокеров реализации; техническая верификация полного набора gate-команд ограничена отсутствующими локальными файлами окружения и CI-скриптами.
