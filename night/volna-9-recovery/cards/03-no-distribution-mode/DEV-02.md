# Backend development report · 03-no-distribution-mode

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-03-no-distribution-mode/backend/app/services/fbs_packing_box_service.py`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-03-no-distribution-mode/backend/tests/test_fbs_packing_box.py`

Режим переключается только после проверки назначений под блокировкой строки поставки. Повторное включение не перезаписывает аудит; явное выключение очищает legacy-префикс `no-distribution:` у коробов, после чего источником истины остаются поля поставки. Добавлен регрессионный тест идемпотентности и отключения legacy-поставки.

## Миграции

Нет: схема для этого атома уже добавлена предыдущей фичей.

## Тесты

- `pytest -q tests/test_fbs_packing_box.py` — 9 passed.

## Гейты

- `ruff check .` — не пройден: 80 существующих ошибок в несвязанных файлах; проверка изменённых файлов проходит.
- `mypy .` — не пройден: существующие ошибки в `wildberries_credentials_service.py`, `fbs_stock_sync_service.py`, `fbs_warehouse_binding_service.py` и тестах; после исправления nullable-проверки новых ошибок в добавленном тесте нет.
- `pytest` — полный прогон запущен, остановлен во время длительного прогона после прохождения целевого набора; целевой набор зелёный.
- `back_guard.py` — недоступен: файл отсутствует в этой рабочей копии.
- `check_migrations.py` — недоступен: файл отсутствует в этой рабочей копии.

## Не реализовано

- Находки, относящиеся к API, workspace и frontend, не входят в backend-атом 2 и не изменялись.
- Полный репозиторный прогон невозможно объявить зелёным из-за предварительно существующих ошибок и отсутствующих CI-скриптов в этой копии.

## Блокеры

Нет блокеров для реализации атома; ограничения проверок описаны выше.
