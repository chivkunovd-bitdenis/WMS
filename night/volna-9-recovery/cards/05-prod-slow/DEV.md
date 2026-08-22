# Фича 1

# DEV · 05-prod-slow · экран S-03 · атом 1

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-05-prod-slow/frontend/src/screens/v2/FfFbsOrdersScreen.tsx`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-05-prod-slow/frontend/tests-e2e/ff-fbs-orders.spec.ts`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-05-prod-slow/night/volna-9-recovery/cards/05-prod-slow/DEV.md`

В таблице вкладки «Новые» закреплена табличная раскладка и ширина 713 px
(48 px служебной колонки чекбокса + 210 / 135 / 180 / 140 px четырёх
информационных колонок). Четыре заголовка остаются `nowrap`. Ремонтный E2E
сценарий теперь проверяет фиксированную раскладку, ширину таблицы, отсутствие
переноса заголовков и отсутствие удалённой жёлтой заливки как до hover, так и
во время hover.

## Гейты

- Зелёный: `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-05-prod-slow/frontend && npx tsc --noEmit -p tsconfig.app.json`.
- Красный, существующие baseline-нарушения, baseline не менялся: `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-05-prod-slow && python3 scripts/ui/ui_guard.py`. Вывод: `MarkingPrintDialog.tsx` 1687 → 1750, `WbProductPickerDialog.tsx` 0 → 646, `FfFbsOrdersScreen.tsx` 1587 → 1667, `FfFbsSupplyWorkspace.tsx` 2493 → 2498, `SellerInboundDraftScreen.tsx` 1111 → 1169. Исправление этих монолитов и обновление baseline выходят за границы атома; флаг `--update` не применялся.
- Зелёный: `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-05-prod-slow/frontend && npm run test:unit` — 20 файлов, 142 теста.
- Не выполнен из-за ограничений песочницы, а не падения проверки: `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-05-prod-slow/frontend && npx playwright test tests-e2e/ff-fbs-orders.spec.ts --grep 'fbs orders: search keeps list, selected drawer stays stable and Excel downloads'`. Playwright webServer не смог привязать API к `127.0.0.1:18000`: `operation not permitted`.

## Не реализовано

Нет пунктов текущего атома, которые не удалось реализовать буквально.

Находка: секреты, токены, `.env`, кабинеты учётных данных, боевой прод и живой
кабинет Wildberries не открывались и не затрагивались.

# Фича 2

# DEV · 05-prod-slow · атом 2: поиск без жёлтой заливки

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-05-prod-slow/frontend/tests-e2e/ff-fbs-orders.spec.ts` — сценарий S-03-TC-016 теперь проверяет фактические фиксированные ширины четырёх колонок вкладки «Новые», а также отсутствие жёлтого фона у результата поиска в обычном и hover-состоянии.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-05-prod-slow/night/volna-9-recovery/cards/05-prod-slow/DEV.md` — артефакт выполнения атома.

`/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-05-prod-slow/frontend/src/screens/v2/FfFbsOrdersScreen.tsx` дополнительно не менялся: требуемая ветка жёлтой заливки уже отсутствует, а `scrollMarginBottom: '220px'` и `registerRow` сохранены. Таблица уже использует `tableLayout: 'fixed'` и ширину 713px, заголовки имеют 210 / 135 / 180 / 140px и `whiteSpace: 'nowrap'`.

## Гейты

- Зелёный: `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-05-prod-slow/frontend && npx tsc --noEmit -p tsconfig.app.json`.
- Зелёный: `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-05-prod-slow/frontend && npm run test:unit -- src/screens/v2/fbsApi.test.ts` — 1 файл, 5 тестов.
- Красный, без изменения baseline: `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-05-prod-slow && python3 scripts/ui/ui_guard.py`. Новые относительно baseline нарушения: `src/components/MarkingPrintDialog.tsx` 1687 → 1750, `src/components/WbProductPickerDialog.tsx` 0 → 646, `src/screens/v2/FfFbsOrdersScreen.tsx` 1587 → 1667, `src/screens/v2/FfFbsSupplyWorkspace.tsx` 2493 → 2498, `src/screens/v2/SellerInboundDraftScreen.tsx` 1111 → 1169. Базовую линию флагом `--update` не менял по правилу роли.
- Не запущен до теста: `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-05-prod-slow/frontend && npx playwright test tests-e2e/ff-fbs-orders.spec.ts -g 'fbs orders: search keeps list, selected drawer stays stable and Excel downloads'`. Веб-сервер не смог привязаться к `127.0.0.1:18000`: `operation not permitted`.
- Зелёный: `git diff --check`.

## Не реализовано

- Нет. В границах атома устранены относящиеся к нему находки REVIEW.md: сценарий больше не закрепляет жёлтую подсветку и проверяет фактические фиксированные ширины. Находка о модалке печати относится к следующему атому; глобальный `inventory.generated.ts` в текущем diff не изменён.

## Находки

- Секреты, ключи, токены, `.env`, кабинеты учётных данных, боевой прод и живой кабинет Wildberries не читались и не затрагивались.

# Фича 3

# DEV · 05-prod-slow · Атом 3 — Убрать кнопку «Закрыть» в состоянии «Готовим ленту…»

## Изменённые файлы

- `frontend/tests-e2e/ff-marking-print-constructor.spec.ts` — строки 125 и 133: заменены `page.getByTestId('marking-print-close-preparing').click()` на `page.keyboard.press('Escape')`, добавлены inline-комментарии (R-31)

> **Компонент `frontend/src/components/MarkingPrintDialog.tsx` не изменялся**: ветка `state === 'preparing'` (строка 127–128) уже содержит правильный код — `ActionGroup`/`SecondaryAction «Закрыть»` отсутствуют. Кнопка в `preparing`-состоянии не рендерится. Нарушение R-31, зафиксированное в DESIGN-REVIEW, в коде компонента уже было устранено до текущего прохода.

## Что сделано

1. **R-31 (MarkingPrintDialog.tsx:128)** — подтверждено: ветка `preparing` рендерит только `StatusChip "Готовим к печати"` и подпись «Можно продолжать работу в WMS», без `ActionGroup` или `SecondaryAction`. Закрытие по Esc и клику по backdrop работает через штатный `onClose` диалога (строка 1088, без `disableEscapeKeyDown`).

2. **Регрессия в e2e-тесте** — тест `ff-marking-print-constructor.spec.ts` обращался к удалённому `data-testid="marking-print-close-preparing"` (строки 125 и 133). После фикса компонента кнопки нет, поэтому тест падал бы в e2e-прогоне. Заменено на `page.keyboard.press('Escape')` — корректный способ закрытия, подтверждённый контрактом («Закрытие модалки остаётся доступным через клик по backdrop и Esc»).

3. **Состояния `ready` и ошибок** — не трогались. Пара `PrimaryAction «Повторить»` + `SecondaryAction «Закрыть»` в ветке ошибок остаётся корректной и не нарушает R-31 (пара есть).

## Гейты

### tsc
```
npx tsc --noEmit -p tsconfig.app.json
```
**Зелёный** — нет вывода, нет ошибок.

### test:unit
```
npm run test:unit
```
**Зелёный** — 20 файлов, 142 теста, все прошли.

```
Test Files  20 passed (20)
     Tests  142 passed (142)
  Duration  3.44s
```

### ui_guard.py
```
python3 scripts/ui/ui_guard.py
```
**Красный** — 5 нарушений, все **pre-existing**, атомом 3 не введены:

| Файл | Нарушение | Источник |
|---|---|---|
| `src/components/MarkingPrintDialog.tsx` | экран-монолит 1687 → 1750 | Другие атомы волны (подтверждено DESIGN-REVIEW: «1687 → 1750 строк», до прохода атома 3) |
| `src/components/WbProductPickerDialog.tsx` | экран-монолит 0 → 646 | Другой атом волны |
| `src/screens/v2/FfFbsOrdersScreen.tsx` | экран-монолит 1587 → 1662 | Другой атом волны (DESIGN-REVIEW видел «1587 → 1675») |
| `src/screens/v2/FfFbsSupplyWorkspace.tsx` | экран-монолит 2493 → 2498 | Другой атом волны |
| `src/screens/v2/SellerInboundDraftScreen.tsx` | экран-монолит 1111 → 1169 | Другой атом волны |

Атом 3 не изменил ни один `.tsx`-файл компонентов — изменён только `tests-e2e/*.spec.ts`, который `ui_guard.py` не сканирует. Базовую линию не двигал (`--update` не применялся).

## Не реализовано

Все требования контракта выполнены буквально:

- Кнопка «Закрыть» отсутствует в состоянии `preparing` ✓
- Закрытие по Esc и backdrop работает через штатный `onClose` ✓
- Состояния `ready`, `expired`, `open_failed`, `failed` не затронуты ✓
- E2e-тест обновлён под новое поведение ✓

Юнит-тест для `TapePreparationStatus` не написан: функция не экспортируется, `vitest` настроен на `environment: node` без jsdom, в проекте нет React-rendering тестов — паттерн для компонентных тестов в репозитории отсутствует.
