# DEV · 03-no-distribution-mode · атом 1

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-03-no-distribution-mode/backend/alembic/versions/20260821_0094_fbs_supplies_boxes_without_distribution.py` — добавляющая миграция 0094: nullable-время включения режима и nullable UUID пользователя с FK `ON DELETE SET NULL`.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-03-no-distribution-mode/backend/app/models/fbs_supply.py` — поля `boxes_without_distribution_at` и `boxes_without_distribution_by_user_id` в `FbsSupply`.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-03-no-distribution-mode/night/volna-9-recovery/cards/03-no-distribution-mode/DEV.md` — отчёт backend-разработки.

## Миграции

- `20260821_0094` — добавляет в `fbs_supplies` `boxes_without_distribution_at` и `boxes_without_distribution_by_user_id`; данных и существующих таблиц не удаляет. `alembic heads` подтверждает, что это единственная head-ревизия.

## Тесты

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-03-no-distribution-mode/backend/tests/test_fbs_packing_box.py` — проверяет сохранение режима через удаление и повторное создание пустых коробов.
- Проверка метаданных `FbsSupply` подтвердила nullable-поля и FK пользователя с `ON DELETE SET NULL`.

## Гейты

- ruff: FAIL — 80 ранее существующих ошибок в несвязанных файлах; изменённые миграция и модель в выводе отсутствуют.
- mypy: FAIL — 21 ранее существующая ошибка в 6 несвязанных файлах; изменённые миграция и модель в выводе отсутствуют.
- pytest: целевые `tests/test_fbs_packing_box.py tests/test_fbs_operator_flow_migration.py` — PASS, `11 passed, 1 skipped`; полный `pytest` был запущен и собрал 822 теста, но его итоговый вывод не вернулся из исполнителя.
- back_guard.py: NOT RUN — `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-03-no-distribution-mode/scripts/ci/back_guard.py` отсутствует.
- check_migrations.py: NOT RUN — `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-03-no-distribution-mode/scripts/ci/check_migrations.py` отсутствует.

## Не реализовано

- Ничего в пределах атома 1. Замечание `REVIEW.md` о повторной идемпотентности POST после выключения режима относится к сервису коробов — атому 2 из `FEATURES.md`; этот атом намеренно не смешивался с хранением схемы и модели.

## Находки

- Нет.
