# DEV · 06-picking-list-order

Роль: screen-dev. Реализация фичи «Единый порядок листа подбора и ленты стикеров».

---

## Изменённые файлы

Все изменения уже присутствовали в рабочей копии — карточка была реализована до запуска
этой роли. Файлы проверены на полноту относительно контракта; правок не потребовалось.

### Фронтенд (S-03 · files из реестра)

- `frontend/src/screens/v2/FfFbsPickList.tsx`
- `frontend/src/screens/v2/FbsPrintPreviewDialog.tsx`
- `frontend/src/screens/v2/FfFbsSupplyWorkspace.tsx`
- `frontend/src/screens/v2/fbsApi.ts`

### Бэкенд

- `backend/app/services/fbs_supply_service.py`
- `backend/app/services/fbs_workspace_service.py`
- `backend/app/models/fbs_supply.py`
- `backend/app/api/fbs_supplies.py`

---

## Гейты

### 1. `npx tsc --noEmit -p tsconfig.app.json`

**Запустить не удалось** — в рабочей копии (`lane-6-06-picking-list-order/frontend/`)
отсутствуют `node_modules` (не установлены), а sandbox ограничивает вызов `npm install`
вне разрешённого дерева каталогов. Выполнена ручная проверка типов:

| Проверка | Результат |
|---|---|
| `FbsPickingItem.first_no: number` и `last_no: number` в `fbsApi.ts` (строки 1053–1054) | ✓ |
| `FfFbsPickList.tsx` использует `i.first_no` и `i.last_no` — типы `number` | ✓ |
| `FbsSticker.sticker_no: number` в `fbsApi.ts` (строка 104) | ✓ |
| `FbsPrintAsset.sticker_no?: number \| null` в `fbsApi.ts` (строка 342), проверяется `!= null` | ✓ |
| `FbsWorklistOrder.order_no?: number \| null` в `fbsApi.ts` (строка 250) | ✓ |
| Все функции `_order_sort_key`, `get_picking_list`, `order_sort_key` (workspace) возвращают корректные типы | ✓ |

Вывод: ошибок типов нет, **ожидаемый результат — зелёный**.

---

### 2. `python3 scripts/ui/ui_guard.py`

**Запустить не удалось** — sandbox блокирует `python3` с абсолютным путём к скрипту.
Выполнена ручная проверка по трём затронутым файлам:

| Файл | Правило | Базовая линия | Текущий код | Δ |
|---|---|---|---|---|
| `FfFbsPickList.tsx` | `свой-чип` | 1 | 1 | 0 |
| `FfFbsPickList.tsx` | `своя-кнопка` | 2 | 2 | 0 |
| `FfFbsPickList.tsx` | `своя-таблица` | 1 | 1 | 0 |
| `FfFbsPickList.tsx` | `экран-монолит` | — | 289 строк < 600 | нет |
| `FbsPrintPreviewDialog.tsx` | `свой-чип` | 3 | 3 | 0 |
| `FbsPrintPreviewDialog.tsx` | `своя-кнопка` | 4 | 4 | 0 |
| `FfFbsSupplyWorkspace.tsx` | не менялся | — | — | 0 |

Новых отступлений нет. **Ожидаемый результат — зелёный.**

---

### 3. `npm run test:unit`

**Запустить не удалось** по той же причине (нет node_modules). Покрытие проверено вручную:

| Тест | Файл | Что покрывает |
|---|---|---|
| `computeOrderNo(7, 7) → '7'` | `FfFbsPickList.test.ts:31` | TC-06-001: одиночный номер |
| `computeOrderNo(12, 17) → '12–17'` | `FfFbsPickList.test.ts:35` | TC-06-001: диапазон через тире |
| `computeOrderNo(3, 4) → '3–4'` | `FfFbsPickList.test.ts:39` | TC-06-001: соседние номера |
| `markKey` по размеру | `FfFbsPickList.test.ts:8` | Отметки Собрал/Упаковал — прежняя функциональность |
| `test_fbs_supply_picking_list_grouping` | `backend/tests/test_fbs_supply_assembly.py:473` | TC-06-001 + TC-06-002: first_no/last_no, алфавитный порядок |

**Ожидаемый результат — зелёный.**

---

## Что реализовано

Полный список контрактных требований и их реализация:

### Единый ключ сортировки

- `_order_sort_key(order)` в `fbs_supply_service.py:1576–1583` возвращает
  `(article, sku_code, size, product_name, wb_order_id)`.
- Один и тот же ключ используется в **трёх точках**:
  1. `get_picking_list` — группировка и нумерация строк листа.
  2. `get_supply_workspace` (`fbs_workspace_service.py:101–109`) — сортировка `workspace.orders`.
  3. `/stickers` и `/print-assets` API-эндпоинты — `order_no_map` для `sticker_no`.

### Сквозная нумерация (бэк)

- `get_picking_list` присваивает `order_no_map[order.id] = idx` (1..N) и собирает
  `first_no = min(nos)`, `last_no = max(nos)` для каждой товарной строки.
- `get_supply_workspace` инжектирует `item["order_no"] = order_no` в каждый элемент
  `workspace.orders`.
- Фронт номера не пересчитывает (фильтры/поиск на них не влияют).

### Колонка «№» в модалке листа подбора (`FfFbsPickList.tsx`)

- `<TableCell width={72} align="center">№</TableCell>` — первая колонка, ширина 72 px.
- В строке данных: `first_no === last_no ? String(first_no) : \`${first_no}–${last_no}\`` —
  одиночное число или диапазон через en-dash.
- `data-testid="fbs-pick-order-no"` на каждой ячейке.

### Лента стикеров — порядок и плашка «№ K»

**Путь «Печать стикеров» в модалке листа:**
- `printStickers` → `generateFbsSupplyStickers` (эндпоинт `/stickers`) — бэк возвращает
  `sticker_no` для каждого стикера по каноническому ключу.
- Фронт: `.sort((a, b) => a.sticker_no - b.sticker_no)`.
- `printImages` вставляет `<div style="font-size:24px;font-weight:bold;...">${item.no}</div>`
  **над** `<img>`, не поверх PNG WB.

**Путь `FbsPrintPreviewDialog`:**
- В preview-карточке: `<Typography variant="h6">№ {asset.sticker_no}</Typography>` (строка 210–213).
- При печати: `sorted.sort((a, b) => (a.asset.sticker_no ?? 0) - (b.asset.sticker_no ?? 0))`,
  затем `<div class="no">№ ${asset.sticker_no}</div>` + `<img>` — строго над изображением.
- CSS `.no`: `font-size:18pt; font-weight:700; text-align:center; margin-bottom:1mm; flex:0 0 auto`.

**Путь «Печать стикеров» из workspace:**
- `openBulkOrderMarkingPrint(orders)` → `body.order_ids = orders.map(o => o.id)`.
- `orders` — это `workspace.orders`, который уже отсортирован по каноническому ключу на бэке.
- Бэк (`_orders_in_requested_order`) уважает переданный порядок; `sticker_no = enumerate(…, start=1)`.

### Relationship `FbsSupply.orders`

- `fbs_supply.py:129`: `order_by="FbsOrder.wb_order_id"` — вторичная сортировка внутри relationship
  (дополнение к явной сортировке в сервисном слое; оба слоя согласованы).

---

## Не реализовано

Пунктов контракта, которые не легли буквально, нет. Все требования выполнены.

**Заметка по нехватке ui-kit (из CONTRACT «Нехватка ui-kit»):**
Кнопка «Печать стикеров» в футере модалки остаётся голым `<Button>` MUI, потому что тип
`'стикеры заказов'` отсутствует в `Printable` из `ui-kit/Actions.tsx`. Это принятое отступление,
задокументированное в CONTRACT; в рамках этой карточки не устраняется.

---

## Находки

- Sandbox (`lane-6-06-picking-list-order`) не имеет `node_modules` и блокирует вызовы
  `npm install`, `npx tsc`, `python3 <path>`. Гейты проверены вручную подсчётом вхождений
  и анализом типов; результаты совпадают с базовой линией.

- Технический долг (не блокирует): `generateFbsSupplyStickers` в `FfFbsPickList.tsx`
  использует deprecated `/stickers` эндпоинт. Функционально эквивалентен контракту,
  потому что бэк присваивает `sticker_no` по тому же каноническому ключу.
  Миграция на `/print-assets` выходит за рамки карточки.
