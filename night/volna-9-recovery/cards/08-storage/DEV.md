# DEV · 08-storage · атом 4

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/backend/app/api/products.py`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/backend/app/services/catalog_service.py`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/backend/tests/test_products_api.py`

## Что реализовано

- История габаритов фильтруется по tenant и явно ограничивается seller-владельцем товара; чужой товар для seller возвращает `product_not_found`.
- API ручного обмера сохраняет `container_override`; тестами закреплены запрет неполного и нулевого обмера.
- Доступ сотрудника с правом `inventory` к ручному обмеру сохранён в API-ветке.

## Миграции

Нет.

## Тесты

- `backend/tests/test_products_api.py`: история container-обмера, запрет неполных и нулевых габаритов.

## Гейты

- `ruff check .`: FAIL — существующие ошибки вне изменённых файлов (80 ошибок, включая `storage_statement_service.py` и FBS-модули).
- `mypy .`: FAIL — существующие ошибки, включая отсутствующий `app.models.billing`; ошибок в изменённых строках не показано.
- `pytest -q tests/test_products_api.py`: PASS — 1 passed.
- `pytest -q`: INTERRUPTED вручную после прохождения 26% набора без ошибки; полный результат не получен.
- `python3 scripts/ci/back_guard.py`: BLOCKED — файл отсутствует в рабочей копии.
- `python3 scripts/ci/check_migrations.py`: BLOCKED — файл отсутствует в рабочей копии.
- Commit: BLOCKED — Git не смог создать `/Users/deniscivkunov/Projects/WMS/.git/worktrees/lane-2-08-storage1/index.lock` из-за запрета доступа к общему git-метадаталогу.

## Не реализовано

- Остальные находки ревью по storage statements, billing, WB-импорту и frontend находятся за пределами атома 4 и не изменялись.

## Блокеры

- Нет блокеров по коду атома; общие гейты требуют исправлений/файлов, отсутствующих в этой рабочей копии.
- Сохранение commit заблокировано правами на общий git worktree; изменения остаются в рабочей копии до устранения ограничения.
