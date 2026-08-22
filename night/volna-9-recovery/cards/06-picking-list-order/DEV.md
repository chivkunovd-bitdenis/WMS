# Backend development report · 06-picking-list-order · атом 4 · переделка

## Что реализовано

- Эндпоинт `POST /operations/fbs-supplies/{supply_id}/order-print-tape` — ранее реализованная нормализация полного набора ID по канонической серверной последовательности и выдача постоянного `order_number` проверены без изменения API.
- Сервис `print_fbs_order_tape` — добавлен регрессионный сценарий, доказывающий, что отсутствующий PNG сохраняет номер проблемного заказа, а следующий готовый заказ не сдвигается в освободившийся номер.

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-06-picking-list-order/backend/tests/test_fbs_supply_assembly.py` — добавлен сервисный тест пропуска WB PNG с постоянными номерами `1, ошибка № 2, 3` при перемешанном запросе.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-06-picking-list-order/night/volna-9-recovery/cards/06-picking-list-order/DEV.md` — отчёт текущей переделки.

## Миграции

Нет.

## Тесты

- `test_fbs_order_tape_missing_png_preserves_following_order_number` — один отсутствующий WB PNG получает постоянный номер `2`, готовые заказы возвращаются с номерами `1` и `3`, порядок входных ID не используется как порядок ленты.
- Существующие `test_fbs_order_tape_*` — полный набор, каноническая сортировка и номер при построчной перепечатке.
- `test_tape_covers_every_order_and_matches_picking_list` — endpoint принимает перемешанный полный состав, возвращает порядок и номера листа `1..N`, повторная печать сохраняет их.

## Гейты

- `ruff check app/services/fbs_order_tape_print_service.py app/api/fbs_supplies.py tests/test_fbs_supply_assembly.py` из `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-06-picking-list-order/backend` — пройдено: `All checks passed!`.
- `mypy app/services/fbs_order_tape_print_service.py app/api/fbs_supplies.py tests/test_fbs_supply_assembly.py` из `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-06-picking-list-order/backend` — не пройдено: `21 errors in 5 files`; все диагностики существовали до переделки, новый тест новых ошибок не добавил.
- `pytest -q tests/test_fbs_supply_assembly.py -k 'fbs_order_tape'` из `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-06-picking-list-order/backend` — пройдено: `5 passed, 15 deselected in 0.14s`.
- `pytest -q tests/test_fbs_packaging_integration.py -k 'tape_covers_every_order_and_matches_picking_list'` из `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-06-picking-list-order/backend` — пройдено: `1 passed, 14 deselected in 2.12s`.
- `python3 scripts/ci/back_guard.py` — не применим: текущая переделка не добавляет и не меняет роут.
- `python3 scripts/ci/check_migrations.py` — не применим: миграций нет.
- `git add -- backend/tests/test_fbs_supply_assembly.py night/volna-9-recovery/cards/06-picking-list-order/DEV.md && git diff --cached --check && git commit -m "test(fbs): preserve tape numbers across sticker gaps"` — не выполнено: Git не смог создать `/Users/deniscivkunov/Projects/WMS/.git/worktrees/lane-3-06-picking-list-order/index.lock` (`Operation not permitted`).

## Не реализовано

- Находки 1–4 из `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-06-picking-list-order/night/volna-9-recovery/cards/06-picking-list-order/REVIEW.md` относятся к подключению модалки, физическому frontend-рендереру ленты и UI-тестам. Они находятся вне роли `backend-dev` и файлов backend-атома, поэтому не исправлялись.
- Следующие атомы из `FEATURES.md` не выполнялись.

## Находки

- Серверная реализация атома уже присутствовала в истории ветки и в `REVIEW.md` отмечена как корректная; переделка закрывает отсутствовавшее целевое доказательство сценария с ошибкой одного PNG.
- Несвязанное изменение `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-06-picking-list-order/night/volna-9-recovery/JOURNAL.md` сохранено без изменений и в коммит атома не включается.

## Блокеры

- Переделка локально реализована и проверена, но новый тест и этот отчёт не сохранены отдельным коммитом: среда запрещает запись в общую метапапку Git worktree. Последний сохранённый `HEAD` — `a62c8de8`; он не содержит текущую переделку.
