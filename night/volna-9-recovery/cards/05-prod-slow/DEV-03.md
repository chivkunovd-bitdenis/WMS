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
