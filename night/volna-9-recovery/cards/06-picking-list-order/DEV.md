# Backend development report · 06-picking-list-order · atom 4 rework

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-06-picking-list-order/backend/app/services/fbs_order_tape_print_service.py` — полная лента (`include_order_qr=true`) теперь принимает только актуальный полный состав поставки, по одному ID каждого заказа; построчная печать (`include_order_qr=false`) сохраняет прежний режим подмножества.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-06-picking-list-order/backend/app/api/fbs_supplies.py` — неполный состав полной ленты возвращает `409 full_supply_order_set_required`; PNG-ассеты заказа отдают `order_id`, `wb_order_id` и канонический `order_number` для предпросмотра и физической пары WB → WMS № K.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-06-picking-list-order/backend/tests/test_fbs_supply_assembly.py` — проверка точного полного множества ID, включая перемешанный порядок и дубликат.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-06-picking-list-order/backend/tests/test_fbs_packaging_integration.py` — endpoint-регресс: неполный состав отклоняется, перемешанный полный состав сохраняет канонические номера; QR-ассеты несут номер и WB ID.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-06-picking-list-order/night/volna-9-recovery/cards/06-picking-list-order/DEV.md` — отчёт этого прохода.

## Миграции

Нет: изменены правила валидации и API-представление существующих данных.

## Тесты

- `tests/test_fbs_supply_assembly.py -k fbs_order_tape` — 4 passed: канонический порядок, номер подмножества для старого режима, внешний ID и полный набор ID.
- `tests/test_fbs_packaging_integration.py -k tape_covers_every_order_and_matches_picking_list` — 1 passed: полный состав в перемешанном порядке, стабильная повторная печать, отказ для неполного состава и метаданные ассета.

## Гейты

- `ruff check .` — не пройден: 82 существующие диагностики вне изменённых файлов; точечный `ruff check` четырёх изменённых backend-файлов пройден.
- `mypy .` — не пройден: 21 существующая ошибка в 6 других файлах; затронутые сервис и API среди ошибок отсутствуют.
- `pytest` — полный запуск не дал финального отчёта в среде запуска (вывод остановился после первых тестов без диагностик); обязательные целевые тесты пройдены, как указано выше.
- `python3 scripts/ci/back_guard.py` — не запущен: `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-06-picking-list-order/scripts/ci/back_guard.py` отсутствует.
- `python3 scripts/ci/check_migrations.py` — не запущен: `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-06-picking-list-order/scripts/ci/check_migrations.py` отсутствует.
- `git diff --check` — пройден.
- `git commit` — не выполнен: среда запретила создание `/Users/deniscivkunov/Projects/WMS/.git/worktrees/lane-3-06-picking-list-order/index.lock` (`Operation not permitted`); изменения остаются незакоммиченными в этой рабочей копии.

## Не реализовано

- Frontend-находки ревью о печати кодов Честного знака и popup относятся к UI-слою и не менялись в роли `backend-dev`.
- Новые маршруты и миграции не нужны.

## Находки

- Рабочее дерево уже содержало несвязанные изменения в `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-06-picking-list-order/night/volna-9-recovery/JOURNAL.md`; они не изменялись.
- Git-метаданные общего worktree недоступны для записи, поэтому commit SHA не создан.
