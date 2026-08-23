# Фича 1

# 09-billing — backend-dev, атом 1

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/backend/app/api/billing.py`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/backend/app/services/billing_configuration_service.py`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/backend/tests/test_billing_configuration_api.py`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/night/volna-9-recovery/cards/09-billing/DEV.md`

## Реализовано

- `POST /billing/tariffs`: входное поле `amount` остаётся суммой в рублях с двумя знаками, а ответ и `GET /billing/tariffs` возвращают целые копейки.
- `create_tariff`: до записи преобразует рубли в `int` копеек; дооценка ранее неоценённых строк этого же сервиса также записывает целые копейки.

## Миграции

Нет.

## Тесты

- `test_billing_configuration_api_validates_profiles_tariffs_and_tenant_boundary`: `0.00` и `45.00` создают тарифы с `0` и `4500` копеек в HTTP-ответах и базе; отрицательная и трёхзнаковая дробная ставки отклоняются валидацией.

## Гейты

- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/backend && ruff check app/api/billing.py app/services/billing_configuration_service.py tests/test_billing_configuration_api.py` — пройдено (`All checks passed!`).
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/backend && mypy app/api/billing.py app/services/billing_configuration_service.py` — пройдено (`Success: no issues found in 2 source files`).
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/backend && pytest -q tests/test_billing_configuration_api.py` — пройдено (`1 passed`).
- `back_guard.py` и `check_migrations.py` не запускались: атом не добавляет роут и миграцию.

## Не реализовано

- Атомы 2–7 из `FEATURES.md` не затрагивались. Изменение дооценки внутри `create_tariff` ограничено устранением связанной находки ревью о передаче `Decimal` в целочисленные поля.
- Отдельный Git-коммит не создан: `git add` не смог создать `/Users/deniscivkunov/Projects/WMS/.git/worktrees/lane-3-09-billing1/index.lock` (`Operation not permitted`). Поэтому изменения существуют только в рабочем дереве и нуждаются в сохранении после восстановления доступа к Git-метаданным.

## Блокеры

Нет.

# Фича 2

# 09-billing — backend-dev, атом 2

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/backend/tests/test_billing_configuration_api.py`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/night/volna-9-recovery/cards/09-billing/DEV.md`

## Реализовано

- `POST /billing/tariffs`: покрывающий тариф дооценивает ранее неоценённые строки `BillingLedgerEntry` для документной, поштучной и литр-дневной услуг целыми копейками.
- `create_tariff`: существующая реализация закрепляет снимок версии тарифа, ставку и итог без передачи `Decimal` в поля `rate` и `amount`; этот атом добавляет регрессионную проверку поведения после `flush`.

## Миграции

Нет.

## Тесты

- `test_creating_covering_tariffs_reprices_unpriced_entries_in_kopecks`: создаёт неоценённые строки журнала, добавляет покрывающие тарифы через API и проверяет после `flush` снимок тарифа, целые `rate`/`amount`, нормализацию документного количества до одного и точные количества для `item` и `liter_day`.

## Гейты

- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/backend && ruff check app/services/billing_configuration_service.py tests/test_billing_configuration_api.py` — пройдено (`All checks passed!`).
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/backend && mypy app/services/billing_configuration_service.py` — пройдено (`Success: no issues found in 1 source file`).
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/backend && pytest -q tests/test_billing_configuration_api.py` — пройдено (`2 passed`).
- `back_guard.py` и `check_migrations.py` не запускались: атом не добавляет маршрут или миграцию.

## Не реализовано

- Следующие атомы `FEATURES.md` не затрагивались.
- Git-коммит не создан: `git add` не может создать `/Users/deniscivkunov/Projects/WMS/.git/worktrees/lane-3-09-billing1/index.lock` (`Operation not permitted`). Изменения остаются в рабочем дереве и не защищены коммитом.

## Находки

- Секреты, ключи, токены, `.env`, кабинеты учётных данных и боевой прод не читались и не затрагивались.

# Фича 3

# 09-billing — DEV

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/frontend/src/ui-kit/Cells.tsx`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/frontend/src/ui-kit/Cells.test.ts`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/night/volna-9-recovery/cards/09-billing/DEV.md`

## Гейты

- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/frontend && npm run test:unit -- src/ui-kit/Cells.test.ts` — зелёный: 1 файл, 2 теста.
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/frontend && npx tsc --noEmit -p tsconfig.app.json` — зелёный.
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing && python3 scripts/ui/ui_guard.py` — красный из-за новых нарушений вне файлов атома: `frontend/src/components/WbProductPickerDialog.tsx`, `frontend/src/screens/v2/FfFbsSupplyWorkspace.tsx`, `frontend/src/screens/v2/SellerInboundDraftScreen.tsx`. Базовая линия не менялась, эти файлы не правились по ограничению атома.
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing && git diff --check` — зелёный.
- `git commit -m "fix: format MoneyCell values as kopecks"` — не выполнен: Git не разрешил создать `/Users/deniscivkunov/Projects/WMS/.git/worktrees/lane-3-09-billing1/index.lock` (`Operation not permitted`).

## Не реализовано

Все пункты контракта, относящиеся к атому MoneyCell, реализованы. Общий `ui_guard.py` не проходит из-за трёх внешних для атома экранов, перечисленных выше; их исправление не входит в разрешённые файлы.

## Находки

Секреты, ключи, токены, `.env` и кабинеты учётных данных не читались и не затрагивались.

# Фича 4

# 09-billing — DEV

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/frontend/src/screens/ff/FfBillingScreen.tsx`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/frontend/src/screens/ff/FfBillingScreen.test.ts`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/frontend/tests-e2e/billing-invoices.spec.ts`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/night/volna-9-recovery/cards/09-billing/DEV.md`

## Гейты

- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/frontend && npm run test:unit -- src/screens/ff/FfBillingScreen.test.ts` — зелёный: 1 файл, 8 тестов.
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/frontend && npx tsc --noEmit -p tsconfig.app.json` — зелёный.
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing && python3 scripts/ui/ui_guard.py` — красный только из-за не относящихся к атому файлов: `frontend/src/components/WbProductPickerDialog.tsx`, `frontend/src/screens/v2/FfFbsSupplyWorkspace.tsx`, `frontend/src/screens/v2/SellerInboundDraftScreen.tsx`. Базовая линия не менялась, эти файлы не правились.
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/frontend && npm run test:e2e -- billing-invoices.spec.ts` — не запустился: окружение запретило bind `127.0.0.1:18000` (`operation not permitted`) на этапе `webServer`, тестовые утверждения не выполнялись.
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing && git diff --check` — зелёный.

## Не реализовано

- Все пункты контракта атома 4 реализованы: экран, детализация и печатный HTML передают копейки в единый форматтер без повторного деления; E2E-фикстуры используют значения API `1200`, `1494000`, `8`, `1455200` и добавлена проверка `63000 → 630,00 ₽` в таблице начислений.
- Целевой Playwright не выполнен из-за запрета окружения на запуск локального веб-сервера. Повторный запуск нужен там, где разрешён bind порта.

## Находки

- Секреты, ключи, токены, `.env` и кабинеты учётных данных не читались и не затрагивались.

# Фича 5

# 09-billing — screen-dev, атом 5

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/frontend/src/screens/ff/FfBillingScreen.tsx`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/frontend/src/screens/v2/SellersScreen.tsx`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/frontend/tests-e2e/billing-invoices.spec.ts`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/night/volna-9-recovery/cards/09-billing/DEV.md`

## Гейты

- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/frontend && npx tsc --noEmit -p tsconfig.app.json` — зелёный.
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/frontend && npm run test:unit -- src/screens/ff/FfBillingScreen.test.ts src/screens/ff/FfSettingsScreen.test.ts` — зелёный: 2 файла, 14 тестов.
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing && python3 scripts/ui/ui_guard.py` — красный только из-за новых нарушений в не относящихся к атому файлах: `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/frontend/src/components/WbProductPickerDialog.tsx`, `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/frontend/src/screens/v2/FfFbsSupplyWorkspace.tsx`, `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/frontend/src/screens/v2/SellerInboundDraftScreen.tsx`. Базовая линия не менялась.
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/frontend && npm run test:e2e -- billing-invoices.spec.ts --grep "seller-profile issue opens|FF-profile issue opens"` — не запустился: окружение запретило bind `127.0.0.1:18000` (`operation not permitted`) на этапе `webServer`; утверждения сценариев не выполнялись.
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing && git diff --check` — зелёный.
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing && git add -- frontend/src/screens/ff/FfBillingScreen.tsx frontend/src/screens/v2/SellersScreen.tsx frontend/tests-e2e/billing-invoices.spec.ts night/volna-9-recovery/cards/09-billing/DEV.md && git commit -m "fix(billing): open profile blocking details"` — не выполнен: Git не смог создать `/Users/deniscivkunov/Projects/WMS/.git/worktrees/lane-3-09-billing1/index.lock` из-за `Operation not permitted`.

## Не реализовано

Нет. `FfSettingsScreen.tsx` не менялся: он уже открывает вкладку `tariffs` из параметра `?tab=tariffs`; атом исправляет передаваемый URL, открывает нужного селлера с раскрытыми реквизитами и проверяет видимые состояния в e2e-сценариях.

## Находки

Секреты, ключи, токены, `.env`, кабинеты учётных данных и боевой прод не читались и не затрагивались.

# Фича 6

# 09-billing — backend-dev, атом 6

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/backend/tests/test_billing_invoice_api.py` — добавлены два HTTP-сценария формирования счёта: при отсутствии профиля ФФ API возвращает `missing_ff_profile`, при отсутствии профиля плательщика-селлера — `missing_seller_profile`.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/docs/blockers/S-31.md` — единая устаревшая блокировка `missing_profile` разделена на два фактических серверных кода; для каждого сохранены шесть обязательных полей и отдельный путь снятия.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/night/volna-9-recovery/cards/09-billing/DEV.md` — этот отчёт атома.

## Миграции

Нет.

## Тесты

- `test_form_invoice_api_returns_missing_ff_profile_reason` проверяет ответ `POST /billing/invoices/{seller_id}/2026-07/form` без профиля ФФ.
- `test_form_invoice_api_returns_missing_seller_profile_reason` проверяет тот же HTTP-контракт без профиля плательщика-селлера.

## Гейты

- В `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/backend`: `ruff check tests/test_billing_invoice_api.py` — пройдено (`All checks passed!`).
- В `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/backend`: `mypy tests/test_billing_invoice_api.py` — пройдено (`Success: no issues found in 1 source file`).
- В `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/backend`: `pytest -q tests/test_billing_invoice_api.py` — пройдено (`7 passed`).
- `python3 scripts/ci/back_guard.py` — не применим: новый маршрут не добавлялся.
- `python3 scripts/ci/check_migrations.py` — не применим: миграции не добавлялись.

## Не реализовано

Нет: выполнен только атом 6 из `FEATURES.md`. Находки ревью о денежных копейках, фронтенд-переходах и московском периоде относятся к отдельным атомам и не менялись.

## Находки

Нет.

# Фича 7

# 09-billing — screen-dev, атом 7

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/frontend/src/screens/ff/FfBillingScreen.tsx`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/frontend/src/screens/ff/FfBillingScreen.test.ts`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/night/volna-9-recovery/cards/09-billing/DEV.md`

## Гейты

- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/frontend && npx tsc --noEmit -p tsconfig.app.json` — зелёный.
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing && python3 scripts/ui/ui_guard.py` — красный только из-за существующих новых нарушений вне файлов атома: `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/frontend/src/components/WbProductPickerDialog.tsx`, `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/frontend/src/screens/v2/FfFbsSupplyWorkspace.tsx`, `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/frontend/src/screens/v2/SellerInboundDraftScreen.tsx`. Базовая линия не менялась.
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/frontend && npm run test:unit -- src/screens/ff/FfBillingScreen.test.ts` — зелёный: 1 файл, 8 тестов.

## Не реализовано

Нет. Начальный период «Начислений» и предыдущий период «Счетов» теперь берутся из года и месяца в `Europe/Moscow`; ручные периоды продолжают храниться раздельно по вкладкам. Unit-тест закрепляет границу `2026-08-31T21:30:00Z`: сентябрь для начислений и август для счетов.

## Находки

Секреты, ключи, токены, `.env`, кабинеты учётных данных и боевой прод не читались и не затрагивались.
