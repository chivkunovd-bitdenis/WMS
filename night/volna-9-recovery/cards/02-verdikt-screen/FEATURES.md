ФИЧ: 1

## Фичи

### 1. Убрать зелёную заливку строки заказа по WB-вердикту в рабочем месте поставки

**Что меняется словами оператора.**
Сейчас строка заказа с принятым WB-кодом (`delivery_allowed = true`) отображается с зелёным фоном (`success.light`) и зелёной левой границей (`success.main`). Это второй сигнал той же сущности, которую уже несёт `StatusChip` «WB: принято» в зоне «ЧЗ». После правки строка имеет нейтральный фон во всех состояниях: активная на сканере — `info.light`/`info.main`-бордер, напечатана — `action.hover`, обычная — `background.paper`. WB-вердикт транслируется исключительно чипом.

**Открытая находка DESIGN-REVIEW:** R-11 → R-35, `FfFbsSupplyWorkspace.tsx:1911, 1922–1928` — строка всё ещё красится в `success.light`/`success.main` при `metadata.verdict.delivery_allowed = true`.

**Что именно менять:**

В `frontend/src/screens/v2/FfFbsSupplyWorkspace.tsx`:
- Строка 1911: удалить `const markingReady = Boolean(tail) && order.metadata.verdict.delivery_allowed`
- Строки 1922–1926: заменить `markingReady ? 'success.light' :` → убрать ветку; оставить `kizRowActive ? 'info.light' : (printed ? 'action.hover' : 'background.paper')`
- Строка 1928: заменить `(markingReady ? 'success.main' : 'transparent')` → `(kizRowActive ? 'info.main' : 'transparent')`

В `frontend/tests-e2e/ff-fbs-supply.spec.ts` (S-03-TC-007, строки 292–301):
- Утверждение `expect(blockedStyle.backgroundColor).not.toBe(acceptedStyle.backgroundColor)` заменить на проверку, что `acceptedRow` имеет тот же нейтральный фон, что и `blockedRow` (оба `background.paper`); убедиться, что ни у одной строки нет зелёного цвета.

**Файлы:**
- `frontend/src/screens/v2/FfFbsSupplyWorkspace.tsx`
- `frontend/tests-e2e/ff-fbs-supply.spec.ts`

**Зависит от:** ничего — независимая правка.

**Как проверить:**
1. В рабочем месте поставки открыть заказ с хвостом кода ЧЗ и `delivery_allowed = true` — строка НЕ зелёная, фон `background.paper`, нет зелёного бордера.
2. Рядом открыть заказ с `delivery_allowed = false` — строка тоже `background.paper`.
3. Оба заказа имеют одинаковый нейтральный фон строки.
4. `StatusChip` «WB: принято» в зоне «ЧЗ» по-прежнему виден — единственный зелёный сигнал.
5. Активная строка сканера по-прежнему `info.light` + `info.main`-бордер.
6. Напечатанная строка — `action.hover`.
7. `npm run test:unit` из `frontend/` — зелёный.
8. `npx tsc --noEmit -p tsconfig.app.json` из `frontend/` — зелёный.

---

## Порядок

Единственная фича: выполняется самостоятельно, без блокирующих зависимостей.

---

## Что осталось за бортом

- Коммит в Git не создан: изменения в рабочей копии есть (DEV-01 — DEV-05), но sandbox заблокировал запись в `.git/worktrees/.../index.lock`. Оркестратор коммитит вручную.
- Playwright-прогон S-03-TC-004/005/007: порт `127.0.0.1:18000` недоступен в sandbox; запускать в полной среде.
- Предсуществующие нарушения `ui_guard.py` в `WbProductPickerDialog.tsx` и `SellerInboundDraftScreen.tsx` — вне границы карточки 02, не созданы ею.
- Предсуществующие mypy-ошибки в `wildberries_credentials_service.py`, `fbs_stock_sync_service.py`, `fbs_warehouse_binding_service.py` — не создавались карточкой 02.
