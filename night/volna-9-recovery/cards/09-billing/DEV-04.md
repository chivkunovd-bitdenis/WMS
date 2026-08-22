# 09-billing — backend-dev · повторное ревью атома 4

## Что реализовано

- Эндпоинты: существующие `PUT/GET /billing/profiles/ff`, `PUT/GET /billing/profiles/sellers/{seller_id}` и `POST/GET /billing/tariffs` повторно проверены на валидацию реквизитов, tenant-границы и неизменность данных после отклонённого запроса.
- Сервисы: существующие `save_profile`, `assert_seller_in_tenant` и `create_tariff` повторно проверены на ИНН, обязательные банковские поля, допустимые пары услуги/единицы, нулевую ставку и версионное закрытие периода.
- Адресный HTTP-тест усилен: после попытки заменить профиль неверным ИНН сервер сохраняет прежние реквизиты; попытка вставить ставку между уже существующими сентябрьской и ноябрьской версиями возвращает понятный конфликт и не меняет историю или границы периодов.
- Находок повторного `REVIEW.md`, относящихся к конфигурационным ручкам атома 4, нет: сам вердикт отдельно подтверждает tenant-фильтры профилей, покрывающую ставку, допустимые единицы, чужого селлера и пробельные банковские поля. Проблемные участки `ledger` и `invoices` появились в последующих атомах 8–10 и в этот шаг не включены.

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/backend/tests/test_billing_configuration_api.py`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/night/volna-9-recovery/cards/09-billing/DEV.md`

## Миграции

Нет: атом не меняет схему базы данных.

## Тесты

- `backend/tests/test_billing_configuration_api.py` — дополнено доказательство атомарности ошибок: неверный ИНН не перезаписывает валидный профиль; конфликт с будущей версией не добавляет ставку и не меняет границы сохранённых версий.
- `backend/tests/test_billing_configuration_service.py` — существующие адресные проверки ИНН, обязательных полей, допустимых услуг/единиц и даты активации повторно пройдены.

## Гейты

- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/backend && ruff check app/services/billing_configuration_service.py app/api/billing.py tests/test_billing_configuration_service.py tests/test_billing_configuration_api.py` — PASS: `All checks passed!`.
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/backend && mypy app/services/billing_configuration_service.py app/api/billing.py` — PASS: `Success: no issues found in 2 source files`.
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/backend && pytest -q tests/test_billing_configuration_service.py tests/test_billing_configuration_api.py` — PASS: `7 passed in 1.34s`.
- `python3 scripts/ci/back_guard.py` — не применим: атом не добавляет новый маршрут.
- `python3 scripts/ci/check_migrations.py` — не применим: атом не добавляет миграцию.
- Полный backend `pytest`, `ruff check .` и `mypy .` не запускались согласно ограничению атомарной проверки.

## Не реализовано

- Находки 1–6 и 8 повторного ревью относятся к read-model начислений, формированию и lifecycle счетов, storage-barrier, сторно и frontend. По истории строк `billing.py` эти участки добавлены атомами 8–10, поэтому в атоме 4 не менялись.
- Новые эндпоинты, сервисы и миграции не добавлялись: контракт конфигурационного API уже реализован, а повторный проход закрыл недостающее тестовое доказательство неизменности данных при ошибке.

## Блокеры

Нет.

## Находки

- Секреты, ключи, токены, `.env`, кабинеты учётных данных и боевой прод не читались и не затрагивались.
