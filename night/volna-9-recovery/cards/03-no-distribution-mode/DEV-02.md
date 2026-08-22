# Backend Dev — 03-no-distribution-mode — фича 2

## Изменённые файлы

- /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-03-no-distribution-mode/backend/app/services/fbs_packing_box_service.py
- /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-03-no-distribution-mode/backend/tests/test_fbs_packing_box.py

## Реализовано

- Добавлен сервис `set_boxes_without_distribution`: режим меняется при пустых коробах независимо от их количества.
- При наличии хотя бы одного `FbsPackingBoxItem` переключение отклоняется доменной ошибкой `boxes_already_distributed`; после удаления назначения снова разрешается.
- Новое состояние записывается в поля поставки, а legacy-приписка `no-distribution:` не изменялась и продолжает читаться существующими путями совместимости.
- Добавлен интеграционный тест полного сценария: пустой короб → включение → удаление и пересоздание → выключение → назначение/запрет → удаление назначения/повторное включение.

## Гейты

- ruff: PASS для изменённых файлов; полный `ruff check .` — FAIL на 82 существующих ошибках вне этого изменения.
- mypy: FAIL на 19 существующих ошибках вне изменённых файлов; ошибок в изменённых файлах нет.
- pytest: целевой тест PASS; полный прогон остановлен после 152 PASS и 3 skipped из 817 за 4:57 (KeyboardInterrupt, итоговый код неуспешный).
- back_guard.py: NOT RUN — `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-03-no-distribution-mode/scripts/ci/back_guard.py` отсутствует.
- check_migrations.py: NOT RUN — `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-03-no-distribution-mode/scripts/ci/check_migrations.py` отсутствует.
- git commit: BLOCKED — Git не может создать `/Users/deniscivkunov/Projects/WMS/.git/worktrees/lane-3-03-no-distribution-mode1/index.lock` из-за ограничений sandbox.

## Не реализовано

- API и workspace не менялись: они относятся к следующей атомарной фиче 3.
- Миграции не менялись: поля поставки уже добавлены предыдущей фичей 1.

## Находки

- В рабочем дереве до начала работы уже были изменения `night/volna-9-recovery/JOURNAL.md` и удалённый прежний `DEV.md`; они не относятся к этой реализации и не включались в изменения backend.
