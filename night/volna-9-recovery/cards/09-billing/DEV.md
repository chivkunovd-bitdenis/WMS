# DEV-09 — API реквизитов и версионных тарифов

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/backend/app/services/billing_configuration_service.py` — закрытый набор услуг и единиц (`inbound`, `marketplace_outbound`, `storage_liter_day`), включая явный `liter_day` для хранения и понятные ошибки.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/backend/app/api/billing.py` — GET профилей ФФ/селлера и GET тарифов с tenant-фильтрацией; существующие mutation-ручки сохранены.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/backend/tests/test_billing_configuration_service.py` — проверки неизвестной услуги и недопустимой единицы хранения.

## Миграции

Нет: схема базы данных этим атомом не изменялась.

## Тесты

- Проверена валидация ИНН и конфликт дат версий.
- Добавлены проверки, что неизвестная услуга и `storage_liter_day` с единицей `item` отклоняются.
- Запущены `tests/test_billing_configuration_service.py` и `tests/test_billing_models.py`: 6 passed.

## Гейты

- `ruff`: пройден для изменённых backend-файлов.
- `mypy`: пройден для изменённых API и сервиса.
- `pytest`: профильный набор пройден, 6 passed; полный набор не запускался.
- `back_guard.py`: не запущен — файл отсутствует в этой рабочей копии по пути `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/scripts/ci/back_guard.py`.
- `check_migrations.py`: не запущен — файл отсутствует в этой рабочей копии по пути `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/scripts/ci/check_migrations.py`.
- `git diff --check`: пройден.

## Не реализовано

- Исправления начислений, счетов, фоновых задач, UI и внешних интеграций не входят в атом API конфигурации и не изменялись.
- Конкурентная защита от двух одновременных записей остаётся на существующих индексах базы; новую миграцию для перестройки индексов в этот атом не добавлял.

## Находки

- Секреты, ключи, токены, `.env`, кабинеты учётных данных и боевой прод не читались и не затрагивались.
