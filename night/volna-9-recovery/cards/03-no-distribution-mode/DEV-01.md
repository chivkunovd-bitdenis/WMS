# Backend Dev — 03-no-distribution-mode — атом 1

## Изменённые файлы

- /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-03-no-distribution-mode/backend/app/models/fbs_supply.py
- /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-03-no-distribution-mode/backend/alembic/versions/20260821_0094_fbs_supplies_boxes_without_distribution.py

В `FbsSupply` добавлены сохраняемые поля `boxes_without_distribution_at` и `boxes_without_distribution_by_user_id`. Миграция `20260821_0094` добавляет nullable-поля и внешний ключ на `users` с `SET NULL`; состояние теперь живёт на поставке и не зависит от жизненного цикла коробов.

## Миграции

- `20260821_0094` — добавляет время включения режима, пользователя-переключателя и внешний ключ на `users`.

## Тесты

- `backend/tests/test_fbs_packing_box.py` — целевой прогон: 8 passed.

## Гейты

- ruff: FAIL — 82 существующие ошибки в несвязанных файлах; изменённые файлы отдельно проходят проверку.
- mypy: FAIL — 21 существующая ошибка в 6 несвязанных файлах; изменённые файлы новых ошибок не добавили.
- pytest: PASS — `tests/test_fbs_packing_box.py`, 8 passed.
- back_guard.py: NOT RUN — `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-03-no-distribution-mode/scripts/ci/back_guard.py` отсутствует.
- check_migrations.py: NOT RUN — `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-03-no-distribution-mode/scripts/ci/check_migrations.py` отсутствует.

## Не реализовано

- Сервис переключения, API/workspace и UI не изменялись: это следующие атомарные фичи из `FEATURES.md`.
- Массовая миграция legacy-ключей `no-distribution:` не выполнялась; совместимость остаётся в следующих слоях.

## Находки

- Секреты, ключи, токены и `.env` не читались.
- Боевой прод и живой кабинет Wildberries не затрагивались.
