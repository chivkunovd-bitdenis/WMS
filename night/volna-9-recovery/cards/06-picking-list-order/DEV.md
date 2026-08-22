# DEV · 06-picking-list-order · атом 3

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-06-picking-list-order/backend/tests/test_fbs_supply_assembly.py` — расширен API-сценарий `S-03-TC-009`: две позиции без товарных признаков образуют одну каноническую строку `№ 1–2`, а полный `order_ids` отсортирован по `wb_order_id`; запрос повторяется с идентичным ответом.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-06-picking-list-order/night/volna-9-recovery/cards/06-picking-list-order/DEV.md` — отчёт backend-разработки по атому 3.

Существующая реализация в `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-06-picking-list-order/backend/app/services/fbs_supply_service.py` и `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-06-picking-list-order/backend/app/api/fbs_supplies.py` уже возвращает канонический порядок `(article, sku_code, size, product_name)`, непрерывные диапазоны и полный `order_ids`; изменений в ней не потребовалось.

## Гейты

- `ruff check tests/test_fbs_supply_assembly.py` — PASS.
- `ruff check .` — FAIL: 82 существующие несвязанные нарушения в backend; изменённый тест в них не указан.
- `mypy .` — FAIL: 21 существующая ошибка в 6 несвязанных файлах; атом 3 их не меняет.
- `pytest tests/test_fbs_supply_assembly.py` — PASS: `18 passed`.
- `pytest` — не завершён: после `61 passed` за 178 секунд остановлен вручную; до остановки ошибок не было.
- `python3 scripts/ci/back_guard.py` — NOT RUN: файл `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-06-picking-list-order/scripts/ci/back_guard.py` отсутствует.
- `python3 scripts/ci/check_migrations.py` — NOT RUN: файл `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-06-picking-list-order/scripts/ci/check_migrations.py` отсутствует.
- `git diff --check` — PASS.

## Не реализовано

- Миграций нет: атом 3 меняет вычисление и выдачу листа, не схему данных.
- Находки `REVIEW.md` о физической печати, popup, Честном знаке и предпросмотре относятся к frontend и слою ленты, не к серверной выдаче листа этого атома.

## Находки

- Нет.
