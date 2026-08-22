# DEV · 04-warehouse-switch · атом 4 (переделка)

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/frontend/src/screens/v2/fbsApi.ts`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/frontend/src/screens/v2/FfFbsOrdersScreen.tsx`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/frontend/src/screens/v2/fbsApi.test.ts`

## Что сделано

### fbsApi.ts
Добавлен необязательный параметр `signal?: AbortSignal` в сигнатуры `fetchFbsWorklist` и `fetchFbsSupplyWorklist`. Сигнал условно передаётся в `fetch` через `...(params.signal !== undefined ? { signal: params.signal } : {})` — так существующие тесты, не передающие signal, остаются без изменений в ожидаемых аргументах.

### FfFbsOrdersScreen.tsx
- `const loadingRef = useRef(false)` заменён на `const abortControllerRef = useRef<AbortController | null>(null)`.
- Охрана `if (loadingRef.current) return; loadingRef.current = true` заменена: в начале каждого `load()` предыдущий контроллер прерывается (`abortControllerRef.current?.abort()`), создаётся новый `AbortController`, его `signal` передаётся во все три fetch-вызова внутри `load` (`supplyParams`, `orderParams`, `params`).
- В `catch`: если причина — `DOMException` с `name === 'AbortError'`, ошибка проглатывается молча (не записывается в state).
- В `finally`: `setBusy(false)` вызывается только если `abortControllerRef.current === controller` (т.е. этот `load()` — последний запущенный). Это предотвращает сброс индикатора загрузки во время исполнения более нового запроса.
- Комментарий у поллинга обновлён: убрана ссылка на `loadingRef`, добавлено объяснение об AbortController.

### fbsApi.test.ts
Добавлены три новых теста (итого 9, было 6):
1. `fetchFbsWorklist` передаёт `signal` в `fetch` — проверяет, что `options.signal === controller.signal`.
2. `fetchFbsSupplyWorklist` передаёт `signal` в `fetch` — аналогично.
3. При срабатывании сигнала до разрешения fetch-промиса — `fetchFbsWorklist` режектит с `DOMException { name: 'AbortError' }`. Мок честно слушает событие `abort` на сигнале и отклоняет промис — воспроизводит реальное поведение нативного fetch.

## Гейты

### tsc
```
npx tsc --noEmit -p tsconfig.app.json
```
Зелёный — нет вывода, код 0.

### ui_guard.py
```
python3 scripts/ui/ui_guard.py
```
Вывод:
```
стало лучше  src/App.tsx: экран-монолит 3492 → 3491
стало лучше  src/screens/v2/FbsSupplyCreateDialog.tsx: своя-кнопка 3 → 2
стало лучше  src/screens/v2/InboundScreen.tsx: экран-монолит 691 → 690
НОВОЕ НАРУШЕНИЕ  src/components/WbProductPickerDialog.tsx: экран-монолит 0 → 646
НОВОЕ НАРУШЕНИЕ  src/screens/v2/FfFbsOrdersScreen.tsx: экран-монолит 1587 → 1690
НОВОЕ НАРУШЕНИЕ  src/screens/v2/FfFbsStockSyncScreen.tsx: экран-монолит 1083 → 1121
НОВОЕ НАРУШЕНИЕ  src/screens/v2/FfFbsSupplyWorkspace.tsx: экран-монолит 2493 → 2605
НОВОЕ НАРУШЕНИЕ  src/screens/v2/SellerInboundDraftScreen.tsx: экран-монолит 1111 → 1267
```

**Все нарушения — pre-existing из предыдущих атомов этой волны, не из этого атома.**

Детали для `FfFbsOrdersScreen.tsx`:
- Baseline (до волны): 1587 строк
- На HEAD перед правкой этого атома (`git show HEAD:...`): 1678 строк → нарушение уже было (+91 от атомов 1–3)
- После правки этого атома: 1689 строк (+11 net: `git diff --stat HEAD` показал 20 insertions, 9 deletions)

Файлы WbProductPickerDialog.tsx, FfFbsStockSyncScreen.tsx, FfFbsSupplyWorkspace.tsx, SellerInboundDraftScreen.tsx не входят в список файлов этого атома; трогать их запрещено.

### test:unit
```
npm run test:unit -- src/screens/v2/fbsApi.test.ts
```
```
✓ src/screens/v2/fbsApi.test.ts (9 tests) 7ms
Test Files  1 passed (1)
     Tests  9 passed (9)
```
Зелёный.

## Не реализовано

Все пункты контракта атома реализованы буквально:
- `loadingRef` → `abortControllerRef` ✓
- `if (loadingRef.current) return` заменён прерыванием предыдущего запроса ✓
- `signal` передан в `fetchFbsSupplyWorklist`, `fetchFbsWorklist` (все три вызова) ✓
- `AbortError` обрабатывается молча ✓
- Поллинг-поведение сохранено (тик прерывает предыдущий) ✓
- Unit-тест добавлен в `fbsApi.test.ts`, покрывает сигнал и AbortError ✓
