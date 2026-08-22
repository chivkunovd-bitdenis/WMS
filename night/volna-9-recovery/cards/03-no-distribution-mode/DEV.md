# Backend Dev — 03-no-distribution-mode — атом 2

## Изменённые файлы

- /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-03-no-distribution-mode/backend/app/services/fbs_packing_box_service.py
- /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-03-no-distribution-mode/backend/tests/test_fbs_packing_box.py

Сервис `set_boxes_without_distribution` теперь разрешает включать и выключать режим при любом количестве пустых коробов. Изменение блокируется только при наличии хотя бы одного `FbsPackingBoxItem` в коробах этой поставки; после удаления назначения переключение снова разрешено. Новое состояние записывается в поля поставки, а legacy-приписка `no-distribution:` остаётся только совместимым чтением существующего поведения.

## Миграции

Нет: поля поставки и миграция добавлены атомом 1.

## Тесты

- `backend/tests/test_fbs_packing_box.py::test_without_distribution_mode_depends_on_assignments_not_box_count` — пустой короб, удаление и пересоздание, выключение режима, запрет при назначении и повторное включение после удаления назначения.

## Гейты

- ruff: PASS — изменённые backend-файлы.
- mypy: FAIL — существующая ошибка в `backend/app/services/wildberries_credentials_service.py:167`, вне изменённых файлов.
- pytest: PASS — `backend/tests/test_fbs_packing_box.py`, 8 passed.
- back_guard.py: NOT RUN — `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-03-no-distribution-mode/scripts/ci/back_guard.py` отсутствует.
- check_migrations.py: NOT RUN — `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-03-no-distribution-mode/scripts/ci/check_migrations.py` отсутствует.

## Не реализовано

- API, workspace и UI не входят в этот атом и не изменялись.
- Массовая миграция legacy-прицепок `no-distribution:` не входит в контракт; совместимое чтение сохранено.

## Находки

- Секреты, ключи, токены и `.env` не читались.
- Боевой прод и живой кабинет Wildberries не затрагивались.
