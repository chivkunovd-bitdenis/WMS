# Фича 1

# 08-storage · backend-dev · атом 1

## Что реализовано

- `POST /operations/storage/tariffs` — общая и индивидуальная ставки нормализуются до точности денежного поля `0.01`; значение, которое после округления становится `0.00`, отклоняется с `422` до записи версии тарифа и пересчёта черновиков.
- `create_storage_tariff` — та же проверка действует для прямых вызовов сервиса: ставка нормализуется с `ROUND_HALF_UP`, затем отклоняется до чтения или изменения БД; ставка `0.005` сохраняется как `0.01`.

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/backend/app/api/storage.py`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/backend/app/services/storage_statement_service.py`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/backend/tests/test_storage_tariff_api.py`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/night/volna-9-recovery/cards/08-storage/DEV.md`

## Миграции

Нет: точность `Numeric(14, 2)` уже существует; атом добавляет проверку до сохранения.

## Тесты

- `test_tariff_amount_must_be_positive` проверяет для общей и индивидуальной ставки `0.001`: `422`, отсутствие версии тарифа и отсутствие пересчёта черновиков.
- `test_storage_tariff_service_rejects_amount_rounding_to_zero` проверяет прямые вызовы сервиса и отсутствие обращения к БД или пересчёта.
- `test_tariff_amount_rounding_that_stays_positive_is_saved` проверяет сохранение общей и индивидуальной ставок `0.005` как `0.01`.

## Гейты

- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/backend && python3 -m ruff check app/api/storage.py app/services/storage_statement_service.py tests/test_storage_tariff_api.py` — успешно, `All checks passed!`.
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/backend && python3 -m mypy --follow-imports=silent app/api/storage.py app/services/storage_statement_service.py` — успешно, `Success: no issues found in 2 source files`.
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/backend && python3 -m pytest -q tests/test_storage_tariff_api.py` — успешно, `16 passed`.
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/backend && python3 -m pytest tests/test_storage_tariff_api.py` — успешно, `16 passed in 24.28s`.
- `python3 /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/scripts/ci/back_guard.py` не запускался: этот атом не добавляет маршрут.
- `python3 /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/scripts/ci/check_migrations.py` не запускался: миграций нет.

## Не реализовано

- Находка 2 из `REVIEW.md` относится к frontend и к фиче 2; она вне backend-слоя и текущего атома.
- Находка 3 из `REVIEW.md` относится к реестру блокировок и к фиче 3; она вне текущего атома.

## Находки

Нет. Секреты, ключи, токены, `.env`, кабинеты учётных данных, production и живой кабинет Wildberries не открывались и не использовались.

## Блокеры

Обновлённый `DEV.md` остался локальным: `git add` / `git commit` не могут создать `/Users/deniscivkunov/Projects/WMS/.git/worktrees/lane-2-08-storage1/index.lock` из-за ограничения прав. Реализация backend-атома сохранена ранее в commit `6f59b94fa792db672cbe8e0df76975956f3f71d9`.

# Фича 2

# 08-storage · screen-dev · атом 2

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/frontend/src/screens/ff/FfStoragePage.tsx`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/frontend/src/screens/ff/FfStoragePage.test.ts`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/night/volna-9-recovery/cards/08-storage/DEV.md`

После успешного сохранения ставки S-11 больше не выставляет `tariff_configured` локально и безусловно. До ответа сервера он сохраняет только пересчитанные им строки, затем повторно загружает снимок открытого месяца. Поэтому для прошлого месяца, который новая ставка не покрывает, остаётся пустое состояние «Тариф хранения ещё не задан» и действие «Задать тариф». Для покрытого месяца сохраняются зафиксированные строки, а пересчитанный черновик заменяется только ответом сервера.

## Гейты

- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/frontend && npx tsc --noEmit -p tsconfig.app.json` — зелёный, завершён с кодом `0`.
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/frontend && npm run test:unit -- src/screens/ff/FfStoragePage.test.ts` — зелёный: `1 passed`, `6 passed`.
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/frontend && python3 /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/scripts/ui/ui_guard.py` — красный из-за трёх чужих файлов вне S-11: `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/frontend/src/components/WbProductPickerDialog.tsx`, `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/frontend/src/screens/v2/FfFbsSupplyWorkspace.tsx`, `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/frontend/src/screens/v2/SellerInboundDraftScreen.tsx`. Базовая линия не обновлялась; эти файлы не менялись в атоме.

## Не реализовано

Нет. Находка 2 из `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/night/volna-9-recovery/cards/08-storage/REVIEW.md`, относящаяся к frontend-слою атома, исправлена. Находки 1 и 3 относятся соответственно к backend-валидации и реестру блокировок и в этот атом не входят.

## Находки

Секреты, ключи, токены, `.env`, кабинеты учётных данных, production и живой кабинет Wildberries не открывались и не использовались.

## Сохранность

Реализация S-11 и unit-тесты уже находятся в commit `11637874ad8bea2ab6378280bcf6f343da2e0e7b`. Актуальный отчёт `DEV.md` записан в рабочей копии, но отдельный commit отчёта не создан: `git add` не может создать `/Users/deniscivkunov/Projects/WMS/.git/worktrees/lane-2-08-storage1/index.lock` из-за `Operation not permitted`.

# Фича 3

# 08-storage · screen-dev · атом 3

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/frontend/src/screens/ff/FfStoragePage.test.ts`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/docs/blockers/S-11.md`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/night/volna-9-recovery/cards/08-storage/DEV.md`

## Гейты

- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/frontend && npx tsc --noEmit -p tsconfig.app.json` — зелёный, код завершения `0`.
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/frontend && npm run test:unit -- src/screens/ff/FfStoragePage.test.ts` — зелёный: `1 passed`, `7 passed`.
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage && python3 scripts/ui/ui_guard.py` — красный из-за новых нарушений в чужих файлах вне атома: `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/frontend/src/components/WbProductPickerDialog.tsx`, `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/frontend/src/screens/v2/FfFbsSupplyWorkspace.tsx`, `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/frontend/src/screens/v2/SellerInboundDraftScreen.tsx`. Базовая линия не обновлялась, эти файлы не менялись.

## Не реализовано

Нет. Добавлен отдельный шестипольный блок запрета ретроактивной даты тарифа: что блокируется, условие, оба слоя, текст оператору, разблокировка и бизнес-причина. Unit-тест закрепляет московский пример `2026-08-23` / `2026-08-22`, текст причины и передачу `disabledReason` в кнопку «Сохранить».

## Находки

Секреты, ключи, токены, `.env`, кабинеты учётных данных, production и живой кабинет Wildberries не открывались и не использовались.

## Сохранность

Отдельный commit не создан: команда `git add -- docs/blockers/S-11.md frontend/src/screens/ff/FfStoragePage.test.ts night/volna-9-recovery/cards/08-storage/DEV.md` остановилась с ошибкой `Unable to create '/Users/deniscivkunov/Projects/WMS/.git/worktrees/lane-2-08-storage1/index.lock': Operation not permitted`. Изменения остаются в рабочей копии и не могут считаться сохранёнными в Git, пока среда не разрешит запись индекса.
