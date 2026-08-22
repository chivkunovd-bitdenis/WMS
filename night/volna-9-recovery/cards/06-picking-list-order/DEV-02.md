# Backend Dev · 06-picking-list-order · атом 2 · переделка

## Что реализовано

- Эндпоинты: новых нет; существующая загрузка поставки получает `orders` из relationship в стабильном порядке.
- Сервисы: новых и изменённых нет.
- Модель: `FbsSupply.orders` упорядочивает заказы по `FbsOrder.wb_order_id`, затем по `FbsOrder.id`.

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-06-picking-list-order/backend/app/models/fbs_supply.py` — реализация атома уже сохранена в ветке: relationship `FbsSupply.orders` содержит `order_by="(FbsOrder.wb_order_id, FbsOrder.id)"`; переделка после ревью не потребовала изменения модели.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-06-picking-list-order/backend/tests/test_fbs_supply_assembly.py` — реализация атома уже сохранена в ветке: интеграционный тест вставляет заказы с одинаковым `wb_order_id` в порядке, обратном их внутренним UUID, загружает поставку через API и проверяет развязку по `order.id`; отдельный тест фиксирует состав `order_by`; переделка после ревью не потребовала изменения теста.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-06-picking-list-order/night/volna-9-recovery/cards/06-picking-list-order/DEV.md` — записан отчёт переделки атома и результаты повторных целевых проверок.

## Миграции

- Нет: схема базы данных не менялась.

## Тесты

- `test_fbs_supply_orders_are_returned_in_stable_order` — проверяет фактическую загрузку relationship для одинакового `wb_order_id` при обратном порядке вставки внутренних идентификаторов и ожидает сортировку по `order.id`.
- `test_fbs_supply_relationship_orders_by_wb_id_then_internal_id` — проверяет, что relationship содержит оба уровня сортировки в требуемой последовательности.

## Гейты

- `ruff check app/models/fbs_supply.py tests/test_fbs_supply_assembly.py` из `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-06-picking-list-order/backend` — пройдено: `All checks passed!`.
- `mypy app/models/fbs_supply.py` из `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-06-picking-list-order/backend` — пройдено: `Success: no issues found in 1 source file`.
- `pytest -q tests/test_fbs_supply_assembly.py -k 'orders_are_returned_in_stable_order or relationship_orders_by_wb_id_then_internal_id'` из `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-06-picking-list-order/backend` — пройдено: `2 passed, 17 deselected in 4.54s`.
- `python3 scripts/ci/back_guard.py` — не применим: атом не добавляет и не меняет роут.
- `python3 scripts/ci/check_migrations.py` — не применим: атом не добавляет миграцию.
- `git diff --check -- night/volna-9-recovery/cards/06-picking-list-order/DEV.md` из корня рабочей копии — пройдено.
- `git add night/volna-9-recovery/cards/06-picking-list-order/DEV.md && git commit -m "docs(night): record backend atom 2 rework"` — не выполнено из-за ограничения песочницы: Git не смог создать `/Users/deniscivkunov/Projects/WMS/.git/worktrees/lane-3-06-picking-list-order/index.lock` (`Operation not permitted`). Сама модель сохранена в коммите `c8f3458b6`, усиление интеграционного теста — в `3dc855d9591ca1f1c4f271304ee63fe42bd62b2c`; незакоммичен только обновлённый `DEV.md`.

## Не реализовано

- Находки 1–4 из `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-06-picking-list-order/night/volna-9-recovery/cards/06-picking-list-order/REVIEW.md` относятся к подключению модалки, физической печатной ленте и тестам frontend. Они не относятся к двум backend-файлам и слою атома 2, поэтому в этой переделке не исправлялись.
- Следующие атомы из `FEATURES.md` не выполнялись.

## Блокеры

- Backend-реализация и тест сохранены в Git. Новый отчёт переделки записан в рабочую копию, но его отдельный коммит заблокирован запретом записи в общую мета-папку Git worktree.

## Находки

- `REVIEW.md` отдельно подтверждает корректность серверного ключа с развязкой по `wb_order_id`, затем `order.id`; backend-находок для атома 2 нет.
- Секреты, ключи, токены, `.env` и кабинеты учётных данных не читались.
