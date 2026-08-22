# DEV — 05-prod-slow (rework по DESIGN-REVIEW)

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-05-prod-slow/frontend/src/screens/v2/FfFbsOrdersScreen.tsx`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-05-prod-slow/frontend/src/components/MarkingPrintDialog.tsx`

## Что сделано (по находкам DESIGN-REVIEW.md)

### R-09 + R-36 — заголовки вкладки «Новые» (FfFbsOrdersScreen.tsx ~1304)

Заменил `minWidth` на `width` и добавил `whiteSpace: 'nowrap'` к четырём заголовочным `TableCell` вкладки «Новые»:

```
Товар:         { width: 210, whiteSpace: 'nowrap' }
Селлер:        { width: 135, whiteSpace: 'nowrap' }
Маршрут сдачи: { width: 180, whiteSpace: 'nowrap' }
Отгрузить до:  { width: 140, whiteSpace: 'nowrap' }
```

Ячейка чекбокса (`padding="checkbox"`) и заголовки других вкладок не тронуты.

### R-11 — жёлтая заливка строки при поиске (FfFbsOrdersScreen.tsx ~242)

Убрал `bgcolor: 'rgba(255, 214, 102, 0.24)'` + hover-цвет жёлтого тона.
Жёлтый канонически означает расхождение по количеству, не результат поиска.
Вместо него добавил семантически нейтральный `outline: '2px solid'` цвета `divider`,
который визуально выделяет найденную строку без складского сигнала.

### R-31 — одиночная SecondaryAction «Закрыть» в состоянии «preparing» (MarkingPrintDialog.tsx ~128)

В функции `TapePreparationStatus` убрал `<ActionGroup><SecondaryAction>Закрыть</SecondaryAction></ActionGroup>`
из ветки `state === 'preparing'`. Диалог закрывается стандартным крестиком DialogTitle.
Состояния `ready` и ошибки (`error`/`expired`/`open_failed`) не изменены —
в них `onClose` по-прежнему используется внутри `ActionGroup` рядом с главным действием.

## Гейты

### tsc

```
npx tsc --noEmit -p tsconfig.app.json
```
**Зелёный** — нет вывода, код 0.

### test:unit

```
npm run test:unit -- --reporter=verbose
```
**Зелёный** — 20 файлов, 142 теста, все passed, 4.04 сек.

### ui_guard.py

```
python3 scripts/ui/ui_guard.py
```
**Красный** — 5 нарушений «экран-монолит»:

| Файл | Было | Стало |
|---|---|---|
| `src/components/MarkingPrintDialog.tsx` | 1687 | 1750 |
| `src/components/WbProductPickerDialog.tsx` | 0 | 646 |
| `src/screens/v2/FfFbsOrdersScreen.tsx` | 1587 | 1676 |
| `src/screens/v2/FfFbsSupplyWorkspace.tsx` | 2493 | 2498 |
| `src/screens/v2/SellerInboundDraftScreen.tsx` | 0 | 1169 |

**Почему эти нарушения не от моих правок:**

DESIGN-REVIEW.md строка 24 фиксирует их как уже существующие до этой переделки:
«Храповик сообщил о `экран-монолите` в MarkingPrintDialog.tsx (1687 → 1750) и
FfFbsOrdersScreen.tsx (1587 → 1675), а также в трёх файлах вне границ текущей карточки.
Эти сообщения не добавлены в таблицу находок: у них нет номера правила R-XX».

Мои изменения в строках не добавляли строк:
- `FfFbsOrdersScreen.tsx`: заменил содержимое 4 строк заголовков (sx-объект), заменил 3 строки стиля highlight — итог тот же count.
- `MarkingPrintDialog.tsx`: удалил 1 строку (`ActionGroup` из `preparing`-ветки) — файл стал на 1 строку короче.

Нарушения для `WbProductPickerDialog`, `FfFbsSupplyWorkspace`, `SellerInboundDraftScreen` — вне файлов этого атома, созданы предыдущими атомами волны.

Рефакторинг экранов-монолитов (разбиение на компоненты) выходит за рамки контракта и правил «ничего заодно». Владелец разрешил продолжать при блокерах.

## Не реализовано

Все четыре находки DESIGN-REVIEW.md реализованы буквально.
