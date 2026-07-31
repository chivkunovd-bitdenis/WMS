# TASK — fbs-frontend-supply-detail: Экран 2 «Карточка отгрузки» FBS

- **Эпик:** FBS — см. `../fbs-marketplace-orders/SPEC.md` и `DESIGN.md`. Гейт 1 эпика ✅, под-задача наследует.
- **Тип / размер:** feature / L
- **Зависит от:** `fbs-frontend` (Экран 1 готов), backend API из `fbs_supplies.py`, `fbs_orders.py`, `fbs_marking.py`
- **Слои:** frontend: `src/screens/v2/`, `src/components/fbs/`, `src/api/fbsApi.ts`

## Описание (для Composer)

Реализуем Экран 2 — детальную карточку отгрузки FBS, которая открывается по клику на отгрузку (drawer или отдельная страница). Экран показывает полный цикл жизни отгрузки: от сборки до передачи в доставку, с виджетами (QR код, стоимость), составом заказов и действиями (печать, передача, отмена).

**Основные элементы:**
- Stepper этапов: Сборка → Грузоместа (для ПВЗ) → В доставке → Завершено
- Шапка с названием (редактируемое), селлер, тип доставки, статус
- Состав отгрузки в виде таблицы заказов со статусами и чекбоксом собранности
- Виджеты справа: QR отгрузки (кнопка печать), стоимость, пропуск
- Первичное действие в footer: контекстное (сборка → передать в доставку)
- ConfirmDialog для необратимых действий (передача в доставку)

## Scope
- Drawer/страница детали отгрузки: GET `/operations/fbs-supplies/{id}` (FbsSupplyOut с заказами)
- Таблица заказов: колонки (чекбокс, №, статус, товар, цена, склад продавца)
- Stepper визуальный: 4 этапа (Сборка, Грузоместа, В доставке, Завершено)
- Действия:
  - Печать стикеров заказов: `POST /operations/fbs-supplies/{id}/stickers` → FbsStickersOut → генерируем PDF
  - Печать QR отгрузки: `GET /operations/fbs-supplies/{id}/barcode` → PNG → открыть в предпросмотре
  - Передать в доставку: `POST /operations/fbs-supplies/{id}/deliver` (через ConfirmDialog)
  - Печать КИЗ/идентификаторов (если требуется)
- Для ПВЗ: отдельный раздел «Грузоместа» с таблицей trbx (получить из `GET /operations/fbs-supplies/{id}/trbx`)
- Bulk-действие на Экране 1: выделить N заказов → кнопка «Создать отгрузку» → POST `/operations/fbs-supplies` с массивом order_ids

## Out of scope
- Редактирование названия отгрузки (может быть в UI, но сохранение — фаза 2)
- Откат статусов (отмена передачи в доставку)
- Интеграция с ТСД (печать там — отдельная фаза)
- Расчёт стоимости (если это отдельный сервис)

## Арх-подход (реальные ручки/файлы)

**Frontend:**
- Новый файл `src/screens/v2/FbsSupplyDetailScreen.tsx` (или `FbsSupplyScreen.tsx`)
  - Props: `suppplyId: string`, `onClose?: () => void`, `token`, `authHeaders`
  - Загрузка: `GET /operations/fbs-supplies/{id}` (FbsSupplyOut с include_orders=true)
  - Layout: шапка + stepper + таблица заказов + виджеты справа + footer с действиями
  - Состояния: loading, error, success
  - data-testid по §9 DESIGN: `fbs-supply-stepper`, `fbs-supply-orders-table`, `fbs-deliver-btn`, `fbs-print-menu`, `fbs-confirm-dialog`

- Расширить `src/api/fbsApi.ts`:
  - `fetchFbsSupply(supplyId: string)` → FbsSupplyOut
  - `fetchFbsSupplyStickers(supplyId: string, force?: boolean)` → FbsStickersOut (список стикеров)
  - `fetchFbsSupplyBarcode(supplyId: string)` → blob (PNG)
  - `deliverFbsSupply(supplyId: string)` → FbsSupplyOut (updated)
  - `fetchFbsTrbxList(supplyId: string)` → FbsTrbxListOut
  - `createFbsSupply(body: FbsSupplyCreateBody)` → FbsSupplyOut

- Компоненты:
  - `FbsSupplyStepper` — четырёхэтапный stepper (статус → текущий шаг)
  - `FbsSupplyOrdersTable` — таблица заказов (FbsSupplyOrderOut[]), чекбоксы для select
  - `FbsSupplyWidgets` — справа: QR (с кнопкой печать), стоимость, пропуск
  - Переиспользовать `FbsStatusChip`, `SellerBadge`, `DeadlinePill` из FbsChips
  - Переиспользовать `PrintMenu` компонент (если существует; иначе собрать меню печати)

- На Экране 1 (FfFbsOrdersScreen):
  - Bulk-action bar при выделении заказов
  - Кнопка «Создать отгрузку» → modal с параметрами (тип доставки, sellerIdи warehouse_id)
  - POST `/operations/fbs-supplies` (FbsSupplyCreateBody) → затем добавить каждый заказ (POST `/{id}/orders`)

**Конвенции MUI:**
- Таблица: `TableContainer` + `Table` с `sticky` шапкой
- Dialog: `Dialog` (для ConfirmDialog передачи в доставку)
- Stepper: `Stepper` (linear, не editable)
- Печать: открываем PDF/PNG в новом окне (window.open с blob-url)
- Статусы: цвета по палитре из `docs/UI_DESIGN_SYSTEM_RU.md` (нейтральный синий, зелёный, янтарь, красный)

**Пути эндпоинтов и типы (из backend):**
- `GET /operations/fbs-supplies/{id}` → `FbsSupplyOut` (id, seller_id, warehouse_id, wb_supply_id, name, status, delivery_type, cargo_type, barcode_file, created_at, orders)
- `POST /operations/fbs-supplies/{id}/orders` (FbsSupplyAddOrderBody: order_id) → ?
- `POST /operations/fbs-supplies/{id}/stickers` (FbsSupplyStickersBody: force) → `FbsStickersOut` (stickers: [{order_id, wb_order_id, sticker_code, sticker_file}])
- `GET /operations/fbs-supplies/{id}/barcode` (type=png) → PNG blob
- `POST /operations/fbs-supplies/{id}/deliver` → `FbsSupplyOut` (updated, status=in_delivery)
- `GET /operations/fbs-supplies/{id}/trbx` → `FbsTrbxListOut` (trbxes: [{id, wb_trbx_id, packaging_box_id, sticker_file}])
- `POST /operations/fbs-supplies` (FbsSupplyCreateBody) → `FbsSupplyOut`

## Критерии приёмки (DoD)

- [ ] Компонент `FbsSupplyDetailScreen` загружает отгрузку и показывает шапку + stepper + таблицу
- [ ] Кнопка печати стикеров: `POST /stickers` → генерирует PDF из base64-файлов (FbsStickersOut)
- [ ] Кнопка печати QR: `GET /barcode` → открывает PNG в новой вкладке
- [ ] Кнопка «Передать в доставку»: показывает ConfirmDialog, `POST /deliver` обновляет статус
- [ ] Таблица заказов показывает состав отгрузки, чекбоксы функциональны
- [ ] Bulk-действие на Экране 1: выделить заказы → создать отгрузку (модальное окно с параметрами)
- [ ] Для ПВЗ: показывается раздел грузомест (GET `/trbx`)
- [ ] data-testid на все ключевые элементы (fbs-supply-stepper, fbs-deliver-btn, fbs-print-menu, fbs-confirm-dialog, и т.д.)
- [ ] Состояния loading/error обработаны (скелетоны, повтор)

## Test coverage (в описание PR — требование CI)

| TC-ID | Title | Applies (Y/N) | Notes |
|-------|-------|---------------|-------|
| TC-NEW-FBS-SUPPLYUI-001 | Загрузка и отображение карточки отгрузки | Y | Given: отгрузка id=s1, статус assembling, 3 заказа / When: открыть экран / Then: заголовок показывает имя, stepper на «Сборка», таблица с 3 строками, loading исчезает |
| TC-NEW-FBS-SUPPLYUI-002 | Печать стикеров заказов | Y | Given: отгрузка с 2 заказами, у каждого sticker_file (base64 PNG) / When: клик на «Печать стикеры» / Then: POST /stickers вызывается, открывается PDF-окно с двумя стикерами, user может распечатать |
| TC-NEW-FBS-SUPPLYUI-003 | Печать QR отгрузки | Y | Given: отгрузка, barcode_file заполнен / When: клик на кнопку QR → «Печать QR» / Then: GET /barcode вызывается, PNG открывается в новой вкладке, user видит QR-код |
| TC-NEW-FBS-SUPPLYUI-004 | Передача в доставку с подтверждением | Y | Given: отгрузка в assembling / When: клик «Передать в доставку» / Then: ConfirmDialog появляется, user кликает «Да» / Then: POST /deliver вызывается, статус переходит в delivery, stepper переместился, диалог закрыт |
| TC-NEW-FBS-SUPPLYUI-005 | Отмена передачи через ConfirmDialog | Y | Given: диалог открыт (передача в доставку) / When: user кликает «Отмена» / Then: POST не вызывается, диалог закрыт, статус остался прежним |
| TC-NEW-FBS-SUPPLYUI-006 | Bulk-действие: создать отгрузку из выделенных заказов | Y | Given: на Экране 1 выделено 5 заказов (статус new) / When: клик «Создать отгрузку», в модале выбран тип доставки + warehouse / Then: POST /supplies (order_ids=[...], delivery_type, warehouse_id), отгрузка создана, navigate в её карточку |
| TC-NEW-FBS-SUPPLYUI-007 | ПВЗ-отгрузка: таблица грузомест | Y | Given: ПВЗ отгрузка, 2 грузоместа с wb_trbx_id и sticker_file / When: открыть детали / Then: раздел «Грузоместа» показывает 2 строки с QR кодами, иконка скопировать ID |
| TC-NEW-FBS-SUPPLYUI-008 | Ошибка загрузки: показать карточку ошибки | Y | Given: fetch /supplies/{id} возвращает 404 / When: открыть экран / Then: показана карточка ошибки с текстом, кнопка «Повтор» (retry) функциональна |

## Где тесты

frontend e2e: `cd frontend && npm run test:e2e` (Playwright, data-testid), specs в `tests/e2e/fbs-supply-detail.spec.ts`

## Гейт перед PR

```bash
cd frontend && npm run build && npm run test:e2e
```
