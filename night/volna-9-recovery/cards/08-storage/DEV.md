# Фича 1

# 08-storage · screen-dev · атом 1

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/frontend/src/screens/ff/FfStoragePage.tsx`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/frontend/tests-e2e/storage.spec.ts`

У поля «Месяц» добавлено видимое объяснение «Будущие месяцы недоступны: расчёт ещё не начался». Атрибут `max` сохранён. Новый сценарий открывает S-11 как сотрудник ФФ, проверяет этот текст и `max="2026-08"` при зафиксированной московской дате.

## Гейты

- Зелёный: `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/frontend && npx tsc --noEmit -p tsconfig.app.json`
- Зелёный: `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/frontend && npm run test:unit -- src/screens/ff/FfStoragePage.test.ts` — 1 файл, 6 тестов.
- Красный вне атома: `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage && python3 scripts/ui/ui_guard.py`. Сторож сообщил три новых отступления в чужих экранах: `frontend/src/components/WbProductPickerDialog.tsx`, `frontend/src/screens/v2/FfFbsSupplyWorkspace.tsx`, `frontend/src/screens/v2/SellerInboundDraftScreen.tsx`. Для S-11 новых отступлений нет; базовую линию не обновлял.
- Не запущен до результата: `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/frontend && npx playwright test tests-e2e/storage.spec.ts --grep "staff sees why future storage months are unavailable"`. Playwright начал запуск, но его API web server не смог привязать `127.0.0.1:18000`: `operation not permitted`.
- Не сохранено коммитом: `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage && git add frontend/src/screens/ff/FfStoragePage.tsx frontend/tests-e2e/storage.spec.ts night/volna-9-recovery/cards/08-storage/DEV.md` не смог создать `/Users/deniscivkunov/Projects/WMS/.git/worktrees/lane-2-08-storage1/index.lock`: `Operation not permitted`. Commit SHA отсутствует.

## Не реализовано

Все пункты первого атома из `FEATURES.md` реализованы буквально. Находки о ширинах истории габаритов и печатной таблице намеренно не трогались: это второй и третий атомы, запрещённые текущим заданием.

## Находки

Секреты, ключи, токены, `.env`, кабинеты учётных данных и боевой прод не открывались и не использовались. Ограничение среды не позволило запустить локальный API Playwright на порту 18000.

# Фича 2

# 08-storage · screen-dev · атом 2

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/frontend/src/screens/ff/FfStoragePage.tsx` — всем пяти колонкам `DataTable` диалога «История габаритов» заданы явные ширины: 170, 140, 250, 180 и 140 px.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/frontend/tests-e2e/storage.spec.ts` — сценарий S-11-TC-007 открывает историю через UI, с длинным именем автора проверяет порядок всех заголовков, объявленные ширины и видимый статус «Действует».
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/night/volna-9-recovery/cards/08-storage/DEV.md` — этот артефакт выполнения.

## Гейты

- Зелёный: `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/frontend && npx tsc --noEmit -p tsconfig.app.json`.
- Красный вне границ атома: `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage && python3 scripts/ui/ui_guard.py` сообщает о трёх уже существующих отступлениях в чужих файлах: `frontend/src/components/WbProductPickerDialog.tsx`, `frontend/src/screens/v2/FfFbsSupplyWorkspace.tsx`, `frontend/src/screens/v2/SellerInboundDraftScreen.tsx`. Файлы не принадлежат S-11 и не менялись.
- Зелёный: `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/frontend && npm run test:unit -- src/screens/ff/FfStoragePage.test.ts` — 6 tests passed.
- Playwright-сценарий найден: `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/frontend && npx playwright test storage.spec.ts --grep 'S-11-TC-007 opens dimension history' --list` — 1 test.
- Полный запуск только этого сценария: `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/frontend && npx playwright test storage.spec.ts --grep 'S-11-TC-007 opens dimension history'` — не стартовал: sandbox запретил API webServer привязать `127.0.0.1:18000` (`operation not permitted`). Код сценария проверен командой `--list`.
- Не сохранено коммитом: `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage && git add frontend/src/screens/ff/FfStoragePage.tsx frontend/tests-e2e/storage.spec.ts night/volna-9-recovery/cards/08-storage/DEV.md` не смог создать `/Users/deniscivkunov/Projects/WMS/.git/worktrees/lane-2-08-storage1/index.lock`: `Operation not permitted`. Commit SHA отсутствует.

## Не реализовано

Все пункты второго атома из `FEATURES.md` реализованы буквально. Находки про объяснение будущих месяцев и печатную SKU-таблицу намеренно не трогались: это первый и третий атомы соответственно.

## Находки

Секреты, ключи, токены, `.env`, кабинеты учётных данных и боевой прод не открывались и не использовались. Полный Playwright-прогон ограничен запретом среды на локальный порт 18000.

# Фича 3

# 08-storage · screen-dev · атом 3

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/frontend/src/screens/ff/FfStoragePage.tsx`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/frontend/tests-e2e/storage.spec.ts`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/night/volna-9-recovery/cards/08-storage/DEV.md`

В A4-предпросмотре у всех семи колонок заданы явные ширины. Между «Литро-дни» и «Сумма, ₽» добавлена числовая правая колонка «Ставка, ₽/л·день», показывающая `rate_snapshot`. E2E-сценарий открывает предпросмотр кнопкой печати у зафиксированной строки, проверяет полный набор заголовков, ширины, длинный артикул, снимок ставки и итог.

## Гейты

- ЗЕЛЁНЫЙ: `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/frontend && npx tsc --noEmit -p tsconfig.app.json`
- ЗЕЛЁНЫЙ: `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/frontend && npm run test:unit -- src/screens/ff/FfStoragePage.test.ts` — 1 файл, 6 тестов.
- КРАСНЫЙ вне границ S-11: `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage && python3 scripts/ui/ui_guard.py`. Сторож сообщил о новых экран-монолитах только в `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/frontend/src/components/WbProductPickerDialog.tsx`, `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/frontend/src/screens/v2/FfFbsSupplyWorkspace.tsx` и `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/frontend/src/screens/v2/SellerInboundDraftScreen.tsx`. Эти файлы не относятся к карточке и не менялись; дизайн-вердикт фиксирует те же три посторонние находки.
- НЕ ЗАПУЩЕНЫ: `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/frontend && npx playwright test tests-e2e/storage.spec.ts --grep 'S-11-TC-008|S-11-TC-009|fixed storage print preview shows the rate snapshot'`. Playwright остановился до выполнения тестов: webServer не смог привязать `127.0.0.1:18000` (`operation not permitted`).
- НЕ СОХРАНЕНО КОММИТОМ: `git add frontend/src/screens/ff/FfStoragePage.tsx frontend/tests-e2e/storage.spec.ts night/volna-9-recovery/cards/08-storage/DEV.md` не смог создать `/Users/deniscivkunov/Projects/WMS/.git/worktrees/lane-2-08-storage1/index.lock` (`Operation not permitted`). SHA отсутствует.

## Не реализовано

Нет. Все пункты атома 3 реализованы буквально. Проверка E2E в этой среде не выполнена из-за запрета локального bind, а не из-за продуктового расхождения.

## Находки

Секреты, ключи, токены, `.env` и кабинеты учётных данных не открывались и не использовались.
