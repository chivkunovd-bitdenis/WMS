# Фича 1

# DEV · 02-verdikt-screen · Атом 1: убрать зелёную заливку строки по WB-вердикту

## Изменённые файлы

- `frontend/src/screens/v2/FfFbsSupplyWorkspace.tsx`
- `frontend/tests-e2e/ff-fbs-supply.spec.ts`

## Что сделано

**`FfFbsSupplyWorkspace.tsx`** (строки 1911–1928):

- Удалена переменная `markingReady = Boolean(tail) && order.metadata.verdict.delivery_allowed` — она была единственным мостом между `delivery_allowed` и цветом строки.
- Выражение `bgcolor` упрощено: `kizRowActive ? 'info.light' : (printed ? 'action.hover' : 'background.paper')` — ветка `success.light` удалена.
- `borderLeftColor` упрощён: `kizRowActive ? 'info.main' : 'transparent'` — ветка `success.main` удалена.

WB-вердикт отображается теперь исключительно через `StatusChip` в зоне «ЧЗ».

**`ff-fbs-supply.spec.ts`** (S-03-TC-007, строки 290–301):

- Удалены два утверждения «фоны разные / границы разные» (`expect(blockedStyle.backgroundColor).not.toBe(acceptedStyle.backgroundColor)` и аналогичное для `borderLeftColor`).
- Добавлено: `acceptedBg === blockedBg` — оба ряда должны иметь одинаковый нейтральный фон, зелёного нет ни у одного.

## Гейты

**Выполненные команды:**
```
cd frontend && npx tsc --noEmit -p tsconfig.app.json   # из worktree
npm run test:unit
python3 scripts/ui/ui_guard.py
```

| Гейт | Результат |
|------|-----------|
| `tsc --noEmit -p tsconfig.app.json` | ✅ зелёный (нет вывода) |
| `npm run test:unit` | ✅ зелёный — 149 тестов, 20 файлов, все прошли |
| `python3 scripts/ui/ui_guard.py` | ✅ для целевых файлов — только улучшения; два новых нарушения (`WbProductPickerDialog.tsx`, `SellerInboundDraftScreen.tsx`) находятся вне границы карточки и были зафиксированы в DESIGN-REVIEW.md как предсуществующие |

Детали `ui_guard.py` по целевому файлу:
```
стало лучше  src/screens/v2/FfFbsSupplyWorkspace.tsx: своя-кнопка 37 → 36
стало лучше  src/screens/v2/FfFbsSupplyWorkspace.tsx: экран-монолит 2493 → 2490
```

## Не реализовано

Нет пунктов, которые не легли буквально. Контракт выполнен полностью:

- Зелёная заливка строки (`success.light` / `success.main`) при `delivery_allowed = true` — удалена.
- Нейтральный фон во всех состояниях без активности сканера и печати сохранён.
- Состояние «активная строка» (`info.light` / `info.main`-бордер) — не тронуто.
- Состояние «напечатана» (`action.hover`) — не тронуто.
- `StatusChip` в зоне «ЧЗ» — единственный зелёный сигнал WB-вердикта, не тронут.
