# DEV · 04-warehouse-switch · атом 3

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/backend/tests/test_fbs_supply_from_orders.py` — добавлен регрессионный API-сценарий: если старый клиент не передал `selected_warehouse_id`, создание использует рассчитанный рекомендуемый операционный склад, а не склад исходного заказа.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/night/volna-9-recovery/cards/04-warehouse-switch/DEV.md` — отчёт backend-dev.

## Гейты

- `ruff check .` — не пройден: 80 ранее существовавших нарушений вне атома; изменённый тест проходит проверку стиля.
- `mypy .` — не пройден: 21 ранее существовавшая ошибка в шести сторонних файлах; изменённый тест не добавил ошибок.
- `pytest -q tests/test_fbs_supply_from_orders.py -k 'warehouse_switch or selected_operational or without_selection'` — пройдено, 3 passed, 17 deselected.
- `pytest` — запуск начат, но среда завершила вывод до итогового результата после старта 823 тестов; финальный статус не получен.
- `python3 scripts/ci/back_guard.py` — не запущен: файла `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/scripts/ci/back_guard.py` в рабочей копии нет.
- `python3 scripts/ci/check_migrations.py` — не запущен: файла `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/scripts/ci/check_migrations.py` в рабочей копии нет.
- `git diff --check` — пройден.
- `git commit` — не выполнен: Git отказал в создании `/Users/deniscivkunov/Projects/WMS/.git/worktrees/lane-1-04-warehouse-switch/index.lock` с ошибкой `Operation not permitted`; изменения остались в рабочем дереве.

## Не реализовано

- Сервис и роут уже содержат нужный контракт этого атома: `selected_warehouse_id`, смену склада до первого действия, запрет после старта и выбор `recommended_warehouse_id` без явного поля. Изменения кода не потребовались; добавлена защита от регрессии замечания ревью №3.
- Находка ревью №1 относится к frontend-совместимости формы ответа; она не изменялась в рамках роли backend-dev и заданного атомарного backend-слоя.
- Находки ревью №2 и №4–15 относятся к другим атомам, файлам либо frontend-слою и не менялись.

## Блокеры

Полные repo-гейты зафиксировали существующие нарушения и отсутствующие CI-скрипты; целевой регрессионный набор пройден. Сохранение в Git не завершено из-за запрета записи lock-файла вне разрешённой рабочей копии.
