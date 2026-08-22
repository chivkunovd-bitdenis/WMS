# DEV · 08-storage · Атом 3 (переделка по REVIEW)

## Изменённые файлы

| Файл | Действие |
|------|----------|
| `frontend/src/utils/moscowDate.ts` | создан — утилита `getMoscowDateString()` (Фича 2) |
| `frontend/src/utils/moscowDate.test.ts` | создан — 4 unit-теста, включая канонический сценарий 23:30 UTC = следующий день МСК |
| `frontend/src/screens/ff/FfStoragePage.tsx` | правлен — импорт утилиты, удалена `currentDate()`, два `useState` и `saveRate()` исправлены (Фича 3) |
| `frontend/tests-e2e/storage.spec.ts` | правлен — мок S-11-TC-002 приведён к схеме реального `TariffCreateOut` (Фича 4, частично) |

## Исправленные находки REVIEW

### Находка 3 (UTC-дата в диалоге)
- **Было:** `const currentDate = () => new Date().toISOString().slice(0, 10)` — UTC-дата; до 03:00 МСК возвращала вчерашний день
- **Стало:** создан `getMoscowDateString()` (UTC+3); `currentDate()` удалена; `useState(getMoscowDateString())` на строках 71 и 75

### Находка 2 (два последовательных POST вместо одного)
- **Было:** два отдельных `await request('/operations/storage/tariffs', ...)` — если первый прошёл, а второй упал, тариф фиксировался частично; retry упирался в unique-констрейнт
- **Стало:** один `await request(...)` с `seller_exception` в теле — сервер пишет обе записи в одной транзакции; failure откатывает всё или ничего

### Находка 1 (мок скрывает отсутствующий эндпоинт)
- Бэкендовый маршрут `POST /operations/storage/tariffs` УЖЕ СУЩЕСТВУЕТ в `backend/app/api/storage.py` (строки 334–387) — Фича 1 была реализована до данной переделки.  
- Мок в `storage.spec.ts:35` больше не «скрывает разрыв»; его ответ обновлён с `{id: 'tariff-1'}` до структуры реального `TariffCreateOut`: `{warehouse_tariff: {...}, seller_exception: null}`.  
- Тело запроса в ассерте `expect(tariffBody).toEqual({warehouse_id, amount, valid_from})` остаётся верным — при `sellerRateEnabled = false` новый объединённый запрос посылает те же поля без `seller_exception`.

## Гейты

| Гейт | Команда | Результат |
|------|---------|-----------|
| tsc | `npx tsc --noEmit -p tsconfig.app.json` (из `frontend/`) | ✅ зелёный, вывода нет |
| ui_guard.py | `python3 scripts/ui/ui_guard.py` (из корня worktree) | ✅ новых нарушений от моих файлов нет; 3 pre-existing нарушения в `WbProductPickerDialog.tsx`, `FfFbsSupplyWorkspace.tsx`, `SellerInboundDraftScreen.tsx` — присутствовали до моих правок (подтверждено через `git stash`) |
| test:unit | `npm run test:unit -- src/utils/moscowDate.test.ts src/screens/ff/` | ✅ 6 passed (4 moscowDate + 2 inboundReceivingHelpers) |

Точные команды:
```
cd frontend && npx tsc --noEmit -p tsconfig.app.json
python3 scripts/ui/ui_guard.py
cd frontend && npm run test:unit -- src/utils/moscowDate.test.ts src/screens/ff/
```

## Не реализовано

### Фича 4: полное удаление мока из S-11-TC-002 (Playwright route-перехват)

FEATURES.md явно указывает: «Playwright-тест `S-11-TC-002` после снятия мока потребует запущенного тестового бэка; инфраструктура sandbox (`operation not permitted` на bind 127.0.0.1:18000) остаётся внешним ограничением, не решаемым в этих фичах.»

Если убрать `page.route('**/api/operations/storage/tariffs', ...)` полностью, то при нажатии «Сохранить» fetch идёт на реальный URL, получает network error (нет бэка), `saveRate()` уходит в `catch`, диалог не закрывается — тест падает на `await expect(page.getByRole('dialog')).toHaveCount(0)`. Поэтому:
- Перехват оставлен, но ответ обновлён до точной схемы `TariffCreateOut`
- Полное удаление мока — инфраструктурная задача (поднять тестовый бэк в Playwright webServer), вне этого атома

### Пункт `getMoscowDateString` в строке `currentMonth()`

FEATURES.md и REVIEW упоминают только `currentDate()` (дата тарифа) как проблему. `currentMonth()` (ограничение max у month-picker) не трогался — это UTC-смещение не влияет на выбор месяца.
