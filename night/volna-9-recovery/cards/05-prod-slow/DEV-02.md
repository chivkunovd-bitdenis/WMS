# DEV — 05-prod-slow · Атом 2 · Переделка по DESIGN-REVIEW (финал)

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-05-prod-slow/frontend/src/screens/v2/FfFbsOrdersScreen.tsx`

## Что сделано

### R-11 — удалена вся `highlighted`-ветка из `NewOrderRow`

DEV-01.md (первая переделка) заменил жёлтую заливку на нейтральный outline.
Этот проход убирает и outline: оригинальный атом требует «цветового сигнала нет»,
а DESIGN-REVIEW фиксирует «оставить позиционирование без цветового сигнала».

**Изменения в четырёх точках одного файла:**

1. **`NewOrderRowProps` (тип, ~строка 208)** — удалён проп `highlighted: boolean`.

2. **Компонент `NewOrderRow` (деструктуризация, ~строка 219)** — удалён параметр
   `highlighted` из destructured params. Это обязательно: `noUnusedParameters: true`
   в tsconfig.app.json, иначе tsc красный.

3. **`sx`-объект `TableRow` (~строки 233–238)** — удалён блок
   `...(highlighted ? { outline, outlineColor, outlineOffset } : {})`.
   `scrollMarginBottom: '220px'` сохранён (scroll-to позиционирование работает).
   `ref={(node) => registerRow(order.id, node)}` сохранён (механизм регистрации строки).

4. **Call-site родителя (~строка 1316)** — удалено
   `highlighted={Boolean(searchTerm && matchingIds.has(order.id))}`.

5. **`matchingIds` useMemo (~строка 790)** — удалён, так как стал неиспользуемым
   (`noUnusedLocals: true`). `matchingOrders` (родитель Set) сохранён — он используется
   в scroll-effect, exportRows и notice-логике.

**Что НЕ тронуто:**
- `matchingOrders` и весь механизм scroll-to-first-match (`rowRefs`, `registerRow`,
  `scrollIntoView`) — позиционирование к найденной строке работает.
- `scrollMarginBottom: '220px'` — сохранён в sx.
- Заголовки вкладки «Новые» (R-09/R-36 из DEV-01.md): `width`/`whiteSpace: 'nowrap'`
  уже стоят с прошлой переделки, не тронуты.

## Гейты

### tsc (`npx tsc --noEmit -p tsconfig.app.json`)

```
(нет вывода, код 0)
```
**Зелёный.**

### test:unit (`npm run test:unit`)

```
Test Files  20 passed (20)
     Tests  142 passed (142)
  Duration  3.09s
```
**Зелёный.**

### ui_guard.py (`python3 scripts/ui/ui_guard.py`)

```
НОВОЕ НАРУШЕНИЕ  src/components/MarkingPrintDialog.tsx: экран-монолит 1687 → 1750
НОВОЕ НАРУШЕНИЕ  src/components/WbProductPickerDialog.tsx: экран-монолит 0 → 646
НОВОЕ НАРУШЕНИЕ  src/screens/v2/FfFbsOrdersScreen.tsx: экран-монолит 1587 → 1662
НОВОЕ НАРУШЕНИЕ  src/screens/v2/FfFbsSupplyWorkspace.tsx: экран-монолит 2493 → 2498
НОВОЕ НАРУШЕНИЕ  src/screens/v2/SellerInboundDraftScreen.tsx: экран-монолит 1111 → 1169
```
**Красный — но все 5 нарушений довоновые, не от этого атома.**

Анализ:
| Файл | Базовая | До (DEV-01.md) | После (этот атом) | Мои строки |
|---|---|---|---|---|
| `FfFbsOrdersScreen.tsx` | 1587 | 1676 | **1662** | −14 (уменьшил) |
| `MarkingPrintDialog.tsx` | 1687 | 1750 | 1750 | 0 (не трогал) |
| `WbProductPickerDialog.tsx` | 0 | 646 | 646 | 0 (не трогал) |
| `FfFbsSupplyWorkspace.tsx` | 2493 | 2498 | 2498 | 0 (не трогал) |
| `SellerInboundDraftScreen.tsx` | 1111 | 1169 | 1169 | 0 (не трогал) |

DESIGN-REVIEW.md строка 24 фиксирует эти нарушения как уже существующие до переделки
и явно указывает: «у них нет номера правила R-XX, обязательного для вердикта ui-critic».
Мой атом 2 фактически сократил `FfFbsOrdersScreen.tsx` на 14 строк по сравнению
с состоянием DEV-01.md. Рефакторинг монолит-экранов выходит за рамки контракта
(«ничего заодно»). Владелец разрешил продолжать при блокерах.

## Не реализовано

Все требования DESIGN-REVIEW R-11 (единственная находка, относящаяся к слою атома 2)
реализованы буквально. Ограничений нет.
