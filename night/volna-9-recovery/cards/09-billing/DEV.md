# Фича 1

# 09-billing — screen-dev

## Изменённые файлы

В рамках атома «Общая денежная ячейка и печать счёта» изменений в исходных файлах не потребовалось: требуемая реализация уже присутствует в checkout.

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/frontend/src/ui-kit/Cells.tsx` — `MoneyCell` и `formatMoney`: RUB, две цифры, сторно без сигнальной окраски, правое выравнивание.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/frontend/src/ui-kit/Actions.tsx` — `PrintAction` принимает `what="счёт"` и формирует подпись «Печать счёта».
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/frontend/src/ui-kit/index.ts` — экспортирует `MoneyCell`, `formatMoney` и `PrintAction`.

## Гейты

- `npx tsc --noEmit -p tsconfig.app.json` — не подтверждён: команда `npx` зависла без вывода в окружении без доступного локального результата.
- `python3 scripts/ui/ui_guard.py` — красный из-за пяти ранее существующих нарушений в чужих файлах (`src/App.tsx`, `src/components/WbProductPickerDialog.tsx`, `src/screens/ff/FfSettingsScreen.tsx`, `src/screens/v2/FfFbsSupplyWorkspace.tsx`, `src/screens/v2/SellerInboundDraftScreen.tsx`); файлы этого атома не указаны.
- `npm run test:unit` — красный: `vitest: command not found`.
- Адресный unit-тест `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/frontend/src/ui-kit/Cells.test.ts` уже покрывает положительную сумму, ноль, сторно и `—`.

## Не реализовано

По относящимся к этому атому пунктам контракта нереализованных требований не обнаружено. Находки `REVIEW.md` относятся к backend и соседним экранам; исправление их выходило бы за границы разрешённых файлов этого атома.

# Фича 2

# 09-billing · screen-dev

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/frontend/src/ui-kit/PeriodPicker.tsx`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/night/volna-9-recovery/cards/09-billing/DEV.md`

Компонент сохраняет контролируемое значение `YYYY-MM` при любых перерисовках родителя,
передаёт новое значение через `onChange`, поддерживает границы `min`/`max`, disabled-состояние
и текст ошибки. Для ошибки добавлена доступная связь поля с подсказкой через `aria-invalid` и
`aria-describedby`. Экспорт `PeriodPicker` и `PeriodPickerProps` уже присутствовал в
`frontend/src/ui-kit/index.ts`, поэтому файл экспорта не изменялся.

## Гейты

- `npx tsc --noEmit -p tsconfig.app.json` — не запущен: в окружении отсутствует `frontend/node_modules/.bin/tsc` (exit 127).
- `python3 scripts/ui/ui_guard.py` — красный по пяти несвязанным существующим монолитным экранам: `src/App.tsx`, `src/components/WbProductPickerDialog.tsx`, `src/screens/ff/FfSettingsScreen.tsx`, `src/screens/v2/FfFbsSupplyWorkspace.tsx`, `src/screens/v2/SellerInboundDraftScreen.tsx`. Нарушений в изменённом `PeriodPicker.tsx` не указано; базовую линию не обновлял.
- `npm run test:unit` — не запущен: команда `vitest` отсутствует в окружении (exit 127).
- `git diff --check` — зелёный.

## Не реализовано

Пунктов контракта, относящихся к `PeriodPicker`, которые не удалось реализовать буквально, нет.

# Фича 3

# 09-billing — backend-dev · rework атома 3 / 09-A

## Что реализовано

- Эндпоинты: нет; атом финансового фундамента не добавляет HTTP-маршруты.
- Сервисы: нет; атом закрепляет модели и миграционную цепочку общего финансового ядра.
- Миграционные идентификаторы billing-цепочки заменены на уникальные для карточки 09: `20260822_09a → 20260822_09b → 20260822_09c`. Это устраняет коллизии с ревизиями `0094` и `0096` соседних карточек при интеграции волны.
- Адресный тест миграции теперь проверяет единственную вершину, порядок всей billing-цепочки и то, что 09-A создаёт только `billing_profiles`, `billing_tariff_versions` и `billing_ledger_entries`.
- Тест неизменяемого журнала подтверждает, что второе начисление одного исходного события и второе сторно отклоняются базой, а запись исходного начисления после сторно остаётся неизменной.

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/backend/alembic/versions/20260822_09a_billing_financial_core.py`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/backend/alembic/versions/20260822_09b_billing_invoices.py`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/backend/alembic/versions/20260822_09c_billing_activation_date.py`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/backend/tests/test_billing_models.py`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/backend/tests/test_billing_financial_core_migration.py`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/night/volna-9-recovery/cards/09-billing/DEV.md`

Удалённые прежние имена тех же миграций:

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/backend/alembic/versions/20260822_0094_billing_financial_core.py`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/backend/alembic/versions/20260822_0095_billing_invoices.py`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/backend/alembic/versions/20260822_0096_billing_activation_date.py`

## Миграции

- `20260822_09a_billing_financial_core.py` (`revision = 20260822_09a`) — добавляет единый набор таблиц профилей, версионных тарифов и неизменяемого журнала начислений/сторно; поддерживает `document`, `item`, `liter_day`, `storage_liter_day` и `storage_measurement` на уровне модели данных без параллельных финансовых таблиц.
- `20260822_09b_billing_invoices.py` (`revision = 20260822_09b`) — существующая добавляющая миграция счетов и проблем запуска; в этом атоме изменены только её идентификатор и ссылка на предыдущую ревизию.
- `20260822_09c_billing_activation_date.py` (`revision = 20260822_09c`) — существующая добавляющая миграция даты включения биллинга; в этом атоме изменены только её идентификатор и ссылка на предыдущую ревизию.

## Тесты

- `backend/tests/test_billing_models.py` — проверяет частичные уникальные индексы, запрет второго начисления для одного source event, запрет второго сторно и неизменность исходного charge после сторно.
- `backend/tests/test_billing_financial_core_migration.py` — проверяет единственный Alembic head, непрерывный порядок `09a → 09b → 09c`, ровно три таблицы финансового ядра в 09-A, уникальность исходного события и внешний ключ сторно с `ON DELETE RESTRICT`.

## Гейты

- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/backend && ruff check app/models/billing.py alembic/versions/20260822_09a_billing_financial_core.py alembic/versions/20260822_09b_billing_invoices.py alembic/versions/20260822_09c_billing_activation_date.py tests/test_billing_models.py tests/test_billing_financial_core_migration.py` — PASS: `All checks passed!`.
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/backend && mypy app/models/billing.py` — PASS: `Success: no issues found in 1 source file`.
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/backend && pytest -q tests/test_billing_models.py tests/test_billing_financial_core_migration.py` — PASS: `5 passed, 2 warnings in 0.33s`; оба предупреждения относятся к устаревающей настройке Alembic `path_separator`, не к поведению атома.
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/backend && alembic heads` — PASS: `20260822_09c (head)`.
- `python3 scripts/ci/back_guard.py` — не применим: новый роут не добавлялся.
- `python3 scripts/ci/check_migrations.py` — не запускался: атом не добавляет миграцию, а исправляет идентификаторы существующей добавляющей цепочки; кроме того, этого файла в рабочей копии нет.

Полный `pytest`, `ruff check .` и `mypy .` не запускались согласно ограничению атомарной проверки.

## Не реализовано

- Находки 1–6 и 8 из `REVIEW.md` относятся к API, invoice/ledger-сервисам и frontend, а не к моделям и миграции атома 09-A; эти слои не изменялись.
- Схема таблиц миграций 09-B и даты активации не менялась: для устранения коллизий достаточно уникальных Alembic revision ID и непрерывных `down_revision` внутри billing-ветки.

## Блокеры

- Сохранение отдельным Git-коммитом невозможно в текущей среде: `git add` завершился с `fatal: Unable to create '/Users/deniscivkunov/Projects/WMS/.git/worktrees/lane-3-09-billing1/index.lock': Operation not permitted`. Исходники и этот артефакт записаны в разрешённую рабочую копию, но Git index и SHA не созданы.

## Находки

- Секреты, ключи, токены, `.env`, кабинеты учётных данных и боевой прод не читались и не затрагивались.

# Фича 4

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

# Фича 5

# 09-billing · screen-dev · атом 5

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/frontend/src/screens/v2/SellersScreen.tsx`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/frontend/tests-e2e/billing-seller-profile.spec.ts`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/night/volna-9-recovery/cards/09-billing/DEV.md`

## Гейты

- `npx tsc --noEmit -p tsconfig.app.json` — не выполнен: в `frontend/node_modules/.bin` отсутствует `tsc`; `npx` не завершился в доступное время.
- `python3 scripts/ui/ui_guard.py` — красный из-за пяти существующих нарушений в соседних файлах: `src/App.tsx`, `src/components/WbProductPickerDialog.tsx`, `src/screens/ff/FfSettingsScreen.tsx`, `src/screens/v2/FfFbsSupplyWorkspace.tsx`, `src/screens/v2/SellerInboundDraftScreen.tsx`. Изменённый `SellersScreen.tsx` новым нарушением не отмечен.
- `npm run test:unit` — не выполнен: `vitest: command not found`.
- `git diff --check` — зелёный.

## Не реализовано

- Пунктов контракта в пределах атома 5, которые не удалось реализовать буквально, нет. Исправлены загрузка сохранённого профиля при раскрытии блока и негативный сценарий `S-31-TC-009`: после ошибочного ИНН success скрывается, а повторное открытие подтверждает ранее сохранённый ИНН.

# Фича 6

## Изменённые файлы

- /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/frontend/src/screens/ff/FfSettingsScreen.tsx
- /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/night/volna-9-recovery/cards/09-billing/DEV.md

## Гейты

- `npx tsc --noEmit -p tsconfig.app.json` из `frontend/` — зелёный.
- `python3 scripts/ui/ui_guard.py` из корня — красный: обнаружены новые/накопленные нарушения монолитности, включая `FfSettingsScreen.tsx: 701 → 795`; baseline не обновлялся.
- `npm run test:unit -- --runInBand` из `frontend/` — не запущен: в окружении отсутствует команда `vitest` (`vitest: command not found`).

## Не реализовано

- Полная продуктовая browser-проверка сценариев S-31-TC-002, S-31-TC-003, S-31-TC-010, S-31-TC-011 и S-19-TC-001 не выполнена: в среде нет установленного test runner/dependency setup.
- Ревью-находки, относящиеся к backend и другим экранам, не менялись: контракт этого атома разрешает только `FfSettingsScreen.tsx` и его E2E-файл.

# Фича 7

# 09-billing — backend-dev · ремонт атома 7

## Что реализовано

- Эндпоинт: существующий `POST /operations/marketplace-unload-requests/{request_id}/cancel` теперь передаёт исполнителя отмены и идемпотентно отменяет уже финальную marketplace-отгрузку.
- Сервис: `record_operational_reversal` находит исходное начисление по tenant и складскому факту, сохраняет отдельную отрицательную строку с тем же снимком тарифа, единицей и количеством и защищён от дубля уникальностью `reversal_of_id` и savepoint (вложенной транзакцией).
- Сервис: `cancel_request` разделяет предфинальную отмену и позднюю финансовую корректировку. Для `shipped` физически отгруженный товар не возвращается на склад; создаётся сторно и документ переходит в `cancelled`. Повторная отмена возвращает уже достигнутое состояние и не создаёт вторую строку.

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/backend/app/api/marketplace_unload_requests.py`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/backend/app/services/billing_invoice_service.py`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/backend/app/services/billing_ledger_service.py`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/backend/app/services/marketplace_unload_service.py`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/backend/app/services/marketplace_unload_status.py`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/backend/tests/test_billing_ledger_service.py`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/backend/tests/test_marketplace_unload_completion.py`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/night/volna-9-recovery/cards/09-billing/DEV.md`

## Миграции

Нет: схема базы данных не менялась.

## Тесты

- `backend/tests/test_billing_ledger_service.py::test_operational_reversal_preserves_snapshot_and_is_idempotent` — отрицательная строка сохраняет снимок исходной ставки, количество и исполнителя; повтор возвращает существующее сторно.
- `backend/tests/test_marketplace_unload_completion.py::test_cancel_shipped_unload_records_one_reversal_http` (`S-31-TC-016`) — живой HTTP-путь завершает отгрузку, отменяет её, повторяет отмену и подтверждает ровно одну положительную и одну отрицательную строку журнала с правильными суммами и исполнителем.
- Повторно пройдены `test_ship_unload_without_discrepancy_http` и `test_marketplace_unload_cancel_partial_distribution_restores_inventory`: обычная финализация и прежняя предфинальная отмена не сломаны.

## Гейты

- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/backend && ruff check app/services/billing_ledger_service.py app/services/billing_invoice_service.py app/services/marketplace_unload_status.py app/services/marketplace_unload_service.py app/api/marketplace_unload_requests.py tests/test_billing_ledger_service.py tests/test_marketplace_unload_completion.py` — PASS: `All checks passed!`.
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/backend && mypy app/services/billing_ledger_service.py app/services/billing_invoice_service.py app/services/marketplace_unload_status.py app/services/marketplace_unload_service.py app/api/marketplace_unload_requests.py` — внешний FAIL: четыре ранее существующие ошибки только в импортируемых соседних `wildberries_credentials_service.py`, `fbs_stock_sync_service.py` и `fbs_warehouse_binding_service.py`; изменённые файлы в выводе ошибок отсутствуют.
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/backend && mypy --follow-imports=skip app/services/billing_ledger_service.py app/services/billing_invoice_service.py app/services/marketplace_unload_status.py app/services/marketplace_unload_service.py` — PASS: `Success: no issues found in 4 source files`.
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/backend && pytest -q tests/test_billing_ledger_service.py tests/test_marketplace_unload_completion.py::test_cancel_shipped_unload_records_one_reversal_http` — PASS: `6 passed in 2.41s`.
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/backend && pytest -q tests/test_marketplace_unload_completion.py::test_ship_unload_without_discrepancy_http tests/test_marketplace_unload_and_discrepancy_acts.py::test_marketplace_unload_cancel_partial_distribution_restores_inventory` — PASS: `2 passed in 4.48s`.
- `python3 scripts/ci/back_guard.py` — не применим: новый маршрут не добавлялся.
- `python3 scripts/ci/check_migrations.py` — не применим: миграция не добавлялась.
- Полный backend `pytest`, `ruff check .` и `mypy .` не запускались согласно ограничению атомарной проверки.

## Не реализовано

- Для завершённой приёмки в текущем backend нет рабочего перехода отмены из `done`; новый маршрут или новый складской процесс контракт атома не вводит. Начисление при первом `done` остаётся прежним и не дублируется. Универсальный сервис сторно готов к подключению, когда такой доменный переход появится отдельным контрактом.
- Находки ревью 1–5, 7 и 8 относятся к read-model/API счетов, storage-barrier, миграционному графу и frontend; эти соседние атомы не менялись.

## Блокеры

- Git-сохранение заблокировано правами среды: команда `git add ... && git commit -m "fix(billing): reverse cancelled final unload charges"` завершилась `fatal: Unable to create '/Users/deniscivkunov/Projects/WMS/.git/worktrees/lane-3-09-billing1/index.lock': Operation not permitted`. Код и артефакт находятся в постоянном зарегистрированном worktree, но не добавлены в индекс и не сохранены коммитом; проверенного SHA нет.

## Находки

- Секреты, ключи, токены, `.env`, кабинеты учётных данных и боевой прод не читались и не затрагивались.

# Фича 8

# 09-billing — backend-dev · ремонт атома 8

## Что реализовано

- Эндпоинт: существующий `GET /billing/ledger` принимает согласованные параметры `period=YYYY-MM` и `date=YYYY-MM-01`, возвращает человекочитаемый номер приёмки/marketplace-отгрузки и ищет по нему вместо технического UUID.
- Эндпоинты: существующие `POST /billing/invoices/{seller_id}/{period}/form`, `GET /billing/invoices`, `GET /billing/invoices/{invoice_id}` и `POST /billing/invoices/{invoice_id}/cancel` используют один tenant-изолированный алгоритм, возвращают только актуальные блокирующие причины и сохраняют идемпотентность параллельного формирования и повторной отмены.
- Сервис: `billing_invoice_service` требует зафиксированный `StorageStatement` каждого операционного склада и опубликованную ledger-строку каждого measurement, включая нулевой statement; при ещё не интегрированных моделях карточки 08 барьер безопасно остаётся закрытым.
- Сервис: при успешном повторе старые `BillingRunIssue` очищаются, текущая блокировка заменяет прежнюю ровно одной причиной, а `no_entries` не сохраняется и не выдаётся как блокирующая ошибка.
- Сервис: неизменяемая детализация счёта сохраняет `document_number`/`display_number` исходного документа; хранение получает подпись `Расчёт хранения за YYYY-MM`, а позднее сторно наследует номер исходного факта и выбирается только по месяцу самого сторно.
- Задача: существующее расписание `wms.billing_invoices_daily` в 02:30 по `Europe/Moscow` и вызов того же `form_invoice`, что использует ручной повтор, закреплены адресным тестом.

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/backend/app/api/billing.py`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/backend/app/services/billing_invoice_service.py`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/backend/tests/test_billing_invoice_service.py`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/backend/tests/test_billing_invoice_api.py`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/backend/tests/test_billing_tasks.py`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/night/volna-9-recovery/cards/09-billing/DEV.md`

## Миграции

Нет. Схема данных в этом атоме не менялась. Названная ревьюером коллизия уже устранена в текущей ветке последовательностью `20260822_09a -> 20260822_09b -> 20260822_09c`; адресный migration-тест проходит.

## Тесты

- `backend/tests/test_billing_invoice_service.py` — `unpriced`, неперсистентный `no_entries`, очистка старой причины, барьер двух операционных складов, публикация измеряемого и нулевого statement (`S-31-TC-006`, `S-31-TC-013`).
- `backend/tests/test_billing_invoice_api.py` — живые HTTP-ручки ledger/invoices: `date=YYYY-MM-01`, поиск и снимок `ПР-101`, два параллельных формирования одного счёта, повторная отмена, скрытие устранённых и неблокирующих причин (`S-31-TC-006`, `S-31-TC-013`, `S-31-TC-014`, `S-31-TC-015`).
- `backend/tests/test_billing_tasks.py` — ежедневное расписание 02:30 МСК.
- `backend/tests/test_marketplace_unload_completion.py::test_cancel_shipped_unload_records_one_reversal_http` — относящаяся к вердикту production-регрессия позднего сторно (`S-31-TC-016`).
- `backend/tests/test_billing_financial_core_migration.py` — единый migration head и порядок billing-ревизий.

## Гейты

- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/backend && ruff check app/services/billing_invoice_service.py app/tasks/billing_tasks.py app/api/billing.py tests/test_billing_invoice_service.py tests/test_billing_invoice_api.py tests/test_billing_tasks.py tests/test_billing_financial_core_migration.py tests/test_marketplace_unload_completion.py` — PASS: `All checks passed!`.
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/backend && mypy app/services/billing_invoice_service.py app/tasks/billing_tasks.py app/api/billing.py` — PASS: `Success: no issues found in 3 source files`.
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/backend && pytest -q tests/test_billing_invoice_service.py tests/test_billing_invoice_api.py tests/test_billing_tasks.py tests/test_billing_financial_core_migration.py tests/test_marketplace_unload_completion.py::test_cancel_shipped_unload_records_one_reversal_http` — PASS: `11 passed, 2 warnings in 3.97s`; предупреждения только Alembic `path_separator` deprecation.
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/backend && git diff --check` — PASS, вывода нет.
- `python3 scripts/ci/back_guard.py` — не применим: новый маршрут не добавлялся, исправлены существующие ручки.
- `python3 scripts/ci/check_migrations.py` — не применим: миграция не добавлялась и не менялась.
- Полный backend `pytest`, `ruff check .` и `mypy .` не запускались согласно ограничению атомарной проверки.

## Не реализовано

- Клик из номера начисления в существующий документ относится к frontend-находке 2 и не входит в роль `backend-dev`; backend теперь отдаёт стабильный человекочитаемый номер, необходимый экрану.
- Исправление frontend-кода `storage` -> `storage_liter_day` и e2e-моков относится к находкам 3 и 8 вне файлов backend-атома и не выполнялось.
- Production-путь позднего сторно не переписывался: он уже подключён предыдущим атомом 7 через отмену финальной marketplace-отгрузки и повторно подтверждён целевым HTTP-тестом `S-31-TC-016`.

## Блокеры

- Git-сохранение недоступно из-за прав среды: адресная команда `git add backend/app/api/billing.py backend/app/services/billing_invoice_service.py backend/tests/test_billing_invoice_service.py backend/tests/test_billing_invoice_api.py backend/tests/test_billing_tasks.py night/volna-9-recovery/cards/09-billing/DEV.md && git commit -m "fix(billing): harden immutable invoice formation"` завершилась `fatal: Unable to create '/Users/deniscivkunov/Projects/WMS/.git/worktrees/lane-3-09-billing1/index.lock': Operation not permitted`. Изменения находятся в постоянном зарегистрированном worktree, но не добавлены в индекс и не сохранены Git-коммитом; проверенного SHA нет. Чужое изменение `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/night/volna-9-recovery/JOURNAL.md` не затрагивалось и не включалось в попытку коммита.

## Находки

- В текущей ветке ещё нет моделей `StorageStatement`, `StorageMeasurement` и признака `Warehouse.is_operational` межкарточного результата 08-B. Сервис подготовлен к их обязательной последующей интеграции и до неё при действующем storage-тарифе закрывает выпуск счёта, а не создаёт неполный документ.
- Секреты, ключи, токены, `.env`, кабинеты учётных данных и боевой прод не читались и не затрагивались.

# Фича 9

# 09-billing · screen-dev · rework атома 9

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/frontend/src/screens/ff/FfBillingScreen.tsx`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/frontend/src/screens/ff/FfBillingScreen.test.ts`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/frontend/tests-e2e/billing-ledger.spec.ts`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/frontend/tests-e2e/billing-invoices.spec.ts`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/night/volna-9-recovery/cards/09-billing/DEV.md`

В `FfBillingScreen` журнал начислений теперь запрашивает выбранный месяц через `period=YYYY-MM`, совпадающий с живым API. Хранение во всех трёх местах экрана — метка, фильтр и детализация счёта — использует единый межкарточный код `storage_liter_day`. Технический UUID расчёта хранения в детализации заменяется на «Расчёт хранения за {месяц}».

`AuthedAppLayout.tsx` и `App.tsx` проверены без правок: пунк «Расчёты» и маршрут `/app/ff/billing` уже ограничены `isFulfillmentAdmin`; селлер и складской сотрудник не видят пунк, а прямой маршрут возвращает экран отказа без финансовых данных. Общие UI-примитивы не добавлялись.

## Гейты

- Красный: `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/frontend && npx tsc --noEmit -p tsconfig.app.json` — локального `typescript` нет, `npx` попытался обратиться к `https://registry.npmjs.org/tsc` и завершился `ENOTFOUND`.
- Красный, но новых нарушений текущего атома нет: `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing && python3 scripts/ui/ui_guard.py`. Храповик указал на уже существующий рост файлов `src/App.tsx` (3492 → 3503), `src/components/WbProductPickerDialog.tsx` (0 → 646), `src/screens/ff/FfSettingsScreen.tsx` (701 → 795), `src/screens/v2/FfFbsSupplyWorkspace.tsx` (2493 → 2498), `src/screens/v2/SellerInboundDraftScreen.tsx` (1111 → 1169). Базовая линия не обновлялась.
- Красный: `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/frontend && npm run test:unit -- src/screens/ff/FfBillingScreen.test.ts` — `vitest: command not found`, потому что в рабочей копии нет `node_modules`.
- Красный: `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/frontend && npm run test:e2e -- billing-ledger.spec.ts billing-invoices.spec.ts` — npm не нашёл локальный Playwright и вызвал одноимённый Python CLI, который завершился `error: unknown command 'test'`.
- Зелёный: `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing && git diff --check`.
- Красный: `git add <файлы атома> && git commit -m "night(09-billing): rework billing screen contract"` — Git не смог создать `/Users/deniscivkunov/Projects/WMS/.git/worktrees/lane-3-09-billing1/index.lock`: `Operation not permitted`. Изменения остались только в рабочем дереве и не сохранены в новом commit.

Полные backend `pytest`, `ruff check .` и `mypy .` не запускались: они прямо запрещены для этого атома.

## Не реализовано

- Backend-находки 2, 4, 5, 6 и 7 из `REVIEW.md` не изменялись: роль `screen-dev` и границы этого атома запрещают править API, сервисы биллинга и миграции.
- Живой frontend e2e с настоящим billing read-model из находки 8 не добавлялся: это интеграционная backend-проверка за границами экранного слоя. Фронтендные моки приведены к реальной форме `{ entries: [...] }` и параметру `period`.
- Предписанные frontend-гейты не подтверждены зелёными из-за отсутствующих локальных npm-зависимостей и недоступного npm registry.
- Результат локально реализован, но не сохранён в Git: служебный Git-каталог worktree недоступен для записи в этой среде.

## Находки

- Секреты, ключи, токены, `.env`, кабинеты учётных данных и боевой прод не открывались и не затрагивались.

# Фича 10

# 09-billing · screen-dev · переделка атома 10

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/frontend/src/screens/ff/FfBillingScreen.tsx` — экранная часть находок 1 и 3 из `REVIEW.md` уже сохранена в текущем `HEAD`: журнал запрашивает живой API через `period=YYYY-MM`, читает `{ entries: [...] }`, не отправляет `seller_id=all`, а хранение использует единый код `storage_liter_day` в фильтре, строках и детализации счёта.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/frontend/tests-e2e/billing-ledger.spec.ts` — экранная часть находки 8 уже сохранена в текущем `HEAD`: `S-31-TC-004`, `S-31-TC-005`, `S-31-TC-012`, очистка устаревших строк при ошибке и регресс канонического кода хранения проверяют реальную форму ответа и параметр `period`.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/night/volna-9-recovery/cards/09-billing/DEV.md` — записан этот отчёт переделки.

Экран и e2e-файл не потребовали нового diff в этом проходе: относящиеся к ним исправления уже находятся в коммите `b9387460608031ec9267c5d606e42e9b78d5e313`, который является текущим `HEAD`. Чужое изменение `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/night/volna-9-recovery/JOURNAL.md` не менялось и не добавлялось в индекс.

## Гейты

- Красный: `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/frontend && npx tsc --noEmit -p tsconfig.app.json` — в рабочей копии нет локального `typescript`; `npx` не получил бинарник из недоступной сети и после 60 секунд без вывода был остановлен (`exit 130`).
- Красный, новых нарушений в файлах атома нет: `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing && python3 scripts/ui/ui_guard.py` — храповик сообщил только о росте чужих файлов: `src/App.tsx` (3492 → 3503), `src/components/WbProductPickerDialog.tsx` (0 → 646), `src/screens/ff/FfSettingsScreen.tsx` (701 → 795), `src/screens/v2/FfFbsSupplyWorkspace.tsx` (2493 → 2498), `src/screens/v2/SellerInboundDraftScreen.tsx` (1111 → 1169). Базовая линия не обновлялась.
- Красный: `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/frontend && npm run test:unit -- src/screens/ff/FfBillingScreen.test.ts` — `sh: vitest: command not found`, потому что в рабочей копии нет `node_modules`.
- Красный: `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/frontend && npx playwright test tests-e2e/billing-ledger.spec.ts --grep 'billing ledger preserves filters and month context|billing ledger performer mode hides money columns|billing ledger shows unpriced operation without blocking it|billing ledger clears stale rows on load error|billing ledger uses the canonical storage service code'` — в рабочей копии нет локального Playwright; `npx` не получил бинарник из недоступной сети и после 30 секунд без вывода был остановлен (`exit 130`).
- Зелёный: `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing && git diff --check`.
- Красный: `git add night/volna-9-recovery/cards/09-billing/DEV.md && git commit -m 'night(09-billing): document atom 10 rework'` — Git не смог создать `/Users/deniscivkunov/Projects/WMS/.git/worktrees/lane-3-09-billing1/index.lock`: `Operation not permitted`. Чужой `JOURNAL.md` в индекс не добавлялся.

Полные backend `pytest`, `ruff check .` и `mypy .` не запускались: они прямо запрещены для этого атома.

## Не реализовано

- Находки 2, 4, 5, 6 и 7 из `REVIEW.md` относятся к backend API, сервисам, миграциям и живому read-model. Роль `screen-dev` и список разрешённых файлов запрещают исправлять их в этом атоме.
- Клик по человекочитаемому номеру исходного документа нельзя реализовать буквально только в `FfBillingScreen.tsx`: текущий ledger API не возвращает маршрут или тип документа, а по замечанию 2 возвращает UUID вместо пользовательского номера. Выдумывать маршрут на экранном слое запрещено контрактом роли.
- Зелёные frontend-гейты подтвердить не удалось из-за отсутствующих локальных npm-зависимостей и недоступного npm registry. Кодовые исправления атома сохранены в Git-коммите `b9387460608031ec9267c5d606e42e9b78d5e313`, но новый отчёт `DEV.md` остался незакоммиченным из-за запрета записи в служебный Git-каталог worktree.

## Находки

- Секреты, ключи, токены, `.env`, кабинеты учётных данных, живой кабинет Wildberries и боевой прод не открывались и не затрагивались.

# Фича 11

# 09-billing — screen-dev, переделка атома 11

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/frontend/src/screens/ff/FfBillingScreen.tsx` — печатный HTML счёта показывает полные снимки реквизитов с пользовательскими русскими подписями, строки и суммы в формате RUB; повторное подтверждение отмены заблокировано до завершения первого запроса.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/frontend/src/screens/ff/FfBillingScreen.test.ts` — добавлена точечная unit-проверка печатного HTML: русские подписи, формат суммы, отсутствие технического `legal_name` и управляющих кнопок.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/frontend/tests-e2e/billing-invoices.spec.ts` — усилены `S-31-TC-007` и `S-31-TC-008`: печатная сумма и отсутствие технического имени поля, блокировка повторной отмены во время незавершённого запроса и ровно один POST отмены.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/night/volna-9-recovery/cards/09-billing/DEV.md` — обязательный артефакт этапа.

## Гейты

- Красный по инфраструктуре: `npx --no-install tsc --noEmit -p tsconfig.app.json` из `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/frontend` не запустил компилятор: локального `frontend/node_modules/.bin/tsc` нет, затем `npx` завершился `ENOTFOUND registry.npmjs.org`.
- Красный только на чужих файлах: `python3 scripts/ui/ui_guard.py` из `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing` сообщил прежние новые нарушения в `frontend/src/App.tsx`, `frontend/src/components/WbProductPickerDialog.tsx`, `frontend/src/screens/ff/FfSettingsScreen.tsx`, `frontend/src/screens/v2/FfFbsSupplyWorkspace.tsx`, `frontend/src/screens/v2/SellerInboundDraftScreen.tsx`. Затронутый `FfBillingScreen.tsx` в отчёте отсутствует; базовая линия не менялась.
- Красный по инфраструктуре: `npm run test:unit -- --run src/screens/ff/FfBillingScreen.test.ts` из `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/frontend` завершился `sh: vitest: command not found`, потому что локальные frontend-зависимости отсутствуют.
- Красный по инфраструктуре: `npx --no-install playwright test tests-e2e/billing-invoices.spec.ts --grep 'billing invoice opens|billing invoice cancellation'` из `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/frontend` не запустил два назначенных сценария: локального Playwright нет, попытка `npx` обратиться к registry завершилась `ENOTFOUND`.
- Зелёный: `git diff --check` из `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing`.
- Красный по ограничениям рабочей копии: `git add -- frontend/src/screens/ff/FfBillingScreen.tsx frontend/src/screens/ff/FfBillingScreen.test.ts frontend/tests-e2e/billing-invoices.spec.ts night/volna-9-recovery/cards/09-billing/DEV.md && git diff --cached --check && git status --short && git commit -m 'night(09-billing): harden invoice print and cancellation'` не дошёл до индексации: Git не смог создать `/Users/deniscivkunov/Projects/WMS/.git/worktrees/lane-3-09-billing1/index.lock` (`Operation not permitted`). Чужой `JOURNAL.md` не индексировался.

## Не реализовано

- Буквальная реализация экранной части пунктов 6–7 контракта атома 11 выполнена в разрешённом слое. Доказать зелёными `tsc`, unit и e2e в этой рабочей копии не удалось из-за отсутствующих локальных npm-зависимостей и закрытого доступа к registry; поэтому результат нельзя считать прошедшим технические гейты.
- Находки 2, 4–7 из `REVIEW.md` относятся к backend API, сервисам, моделям и миграциям и не входят в роль `screen-dev` и разрешённые файлы атома 11; они не менялись.
- Часть находки 8 о тестировании живого backend read-model не может быть закрыта фронтенд-моком `billing-invoices.spec.ts`; для неё нужен отдельный backend/integration-атом. В этом атоме усилены только назначенные пользовательские сценарии `S-31-TC-007` и `S-31-TC-008`.
- Изменения и этот отчёт остались только в рабочем дереве: обязательный отдельный Git-коммит создать невозможно из-за запрета записи в служебный каталог worktree. Без снятия этого ограничения результат не сохранён в восстанавливаемом SHA.

## Находки

- Секреты, ключи, токены, `.env`, кабинеты учётных данных и боевой production не читались и не затрагивались.
