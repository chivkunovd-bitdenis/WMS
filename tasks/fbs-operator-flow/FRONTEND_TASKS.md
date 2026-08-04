# Codex implementation plan — frontend полноценного FBS-процесса

> **Исполнитель:** Codex.  
> **Стартовать только после backend-задач, указанных в `depends_on`.**  
> Backend URL, JSON и коды ошибок из `BACKEND_CONTRACT.md` менять запрещено. Если фактический backend расходится с контрактом — исправлять backend-задачу, а не добавлять скрытый frontend fallback.

## 1. Жёсткие имена frontend API

Все функции находятся в `frontend/src/screens/v2/fbsApi.ts`. Не создавать второй конкурирующий FBS client.

| Функция | HTTP | Request | Response |
|---|---|---|---|
| `fetchFbsWorklist` | `GET /operations/fbs-orders/worklist` | query `seller_id?`, `status_group?`, `search?`, `limit`, `cursor?` | `FbsWorklistPage` |
| `preflightFbsSupply` | `POST /operations/fbs-supplies/preflight` | `FbsSupplyPreflightRequest` | `FbsSupplyPreflight` |
| `createFbsSupplyFromOrders` | `POST /operations/fbs-supplies/from-orders` | `FbsSupplyCreateFromOrdersRequest` | `FbsWorkspace` |
| `fetchFbsWorkspace` | `GET /operations/fbs-supplies/{id}/workspace` | — | `FbsWorkspace` |
| `startFbsSupplyWork` | `POST /operations/fbs-supplies/{id}/start-work` | empty | `FbsWorkspace` |
| `scanFbsPickLocation` | `POST /operations/fbs-supplies/{id}/pick/scan-location` | `{location_barcode}` | `FbsPickLocation` |
| `scanFbsPickProduct` | `POST /operations/fbs-supplies/{id}/pick/scan-product` | `{location_id, product_barcode, order_id?, idempotency_key}` | `FbsWorkspace` |
| `undoFbsPick` | `POST /operations/fbs-supplies/{id}/pick/{order_id}/undo` | `{idempotency_key}` | `FbsWorkspace` |
| `fetchFbsOrderMetadata` | `GET /operations/fbs-orders/{order_id}/metadata` | — | `FbsOrderMetadata` |
| `scanFbsOrderMetadata` | `POST /operations/fbs-orders/{order_id}/metadata/scan` | `{kind, raw_value, idempotency_key}` | `FbsOrderMetadata` |
| `fetchFbsPrintBatch` | `POST /operations/fbs-supplies/{id}/print-assets` | `FbsPrintBatchRequest` | `FbsPrintBatch` |
| `confirmFbsPrintApplied` | `POST /operations/fbs-print-assets/{asset_id}/applied` | `{idempotency_key}` | `FbsPrintAsset` |
| `preflightFbsCargoPlaces` | `POST /operations/fbs-supplies/{id}/cargo-places/preflight` | `{boxes: FbsCargoPlaceDraft[]}` | `FbsCargoPlacesPreflight` |
| `createFbsCargoPlaces` | `POST /operations/fbs-supplies/{id}/cargo-places` | `{count, boxes: FbsCargoPlaceDraft[], idempotency_key}` | `FbsCargoPlace[]` |
| `fetchFbsCargoPlaces` | `GET /operations/fbs-supplies/{id}/cargo-places` | — | `FbsCargoPlace[]` |
| `preflightFbsDelivery` | `POST /operations/fbs-supplies/{id}/delivery-preflight` | empty | `FbsDeliveryPreflight` |
| `deliverFbsSupply` | `POST /operations/fbs-supplies/{id}/deliver` | `{idempotency_key, confirmed_preflight_version}` | `FbsWorkspace` |

Старые функции `createFbsSupply` + цикл `addOrderToFbsSupply` удалить из пользовательского пути после перехода. `generateFbsSupplyStickers`, принимающий `sticker_file` за base64, заменить `fetchFbsPrintBatch`.

## 2. Обязательные TypeScript-типы

Ниже показан минимальный контракт. Поля нельзя переименовывать; можно только добавлять согласованные optional-поля.

```ts
export type FbsWorklistPage = {
  items: FbsWorklistOrder[]
  next_cursor: string | null
  server_now: string
}

export type FbsWorklistOrder = {
  id: string
  wb_order_id: number
  status: string
  wb_status: string | null
  seller: { id: string; name: string }
  wb_warehouse: { id: number; name: string | null }
  wms_warehouse: { id: string; name: string }
  product: {
    id: string | null
    name: string
    image_url: string | null
    seller_article: string | null
    wb_article: number | null
    barcode: string | null
    size: string | null
  }
  inventory: {
    available_unpacked: number
    locations: Array<{ id: string; code: string; available_unpacked: number }>
  }
  buyer_type: 'individual' | 'legal'
  cargo_type: string
  can_pvz: boolean
  metadata: FbsOrderMetadata
  sticker: {
    status: 'not_requested' | 'requesting' | 'ready' | 'print_opened' | 'applied' | 'error'
    asset_url: string | null
    applied_at: string | null
  }
  pick: { status: 'pending' | 'picked' | 'returned'; location_code: string | null; picked_at: string | null }
  pack: { status: 'pending' | 'packed'; packed_at: string | null }
  created_at_wb: string
  deadline_at: string
  supply_id: string | null
  selection_blockers: Array<{ code: string; message: string }>
}

export type FbsOrderMetadata = {
  required: string[]
  optional: string[]
  states: Array<{
    kind: string
    status: 'missing' | 'assigned' | 'sending' | 'pending' | 'accepted' | 'allowed_without_check' | 'rejected' | 'replacement_required'
    reason: string | null
  }>
  delivery_allowed: boolean
  last_checked_at: string | null
}

export type FbsSupplyPreflightRequest = {
  order_ids: string[]
  planned_delivery_type: 'warehouse_sc' | 'pvz'
}

export type FbsSupplyPreflight = {
  compatible: boolean
  summary: {
    seller: { id: string; name: string }
    wb_warehouse: { id: number; name: string | null }
    wms_warehouse: { id: string; name: string }
    buyer_type: 'individual' | 'legal'
    cargo_type: string
    orders_count: number
    required_marking_count: number
    pvz_allowed_count: number
    pvz_blocked_count: number
    nearest_deadline_at: string
  }
  issues: Array<{ order_id: string; code: string; message: string }>
}

export type FbsSupplyCreateFromOrdersRequest = {
  name: string
  order_ids: string[]
  planned_delivery_type: 'warehouse_sc' | 'pvz'
  planned_destination?: { office_id: number; name: string; zone: string } | null
  idempotency_key: string
}

export type FbsPickLocation = {
  id: string
  code: string
  warehouse_id: string
  warehouse_name: string
  expected_products: Array<{
    product_id: string
    name: string
    barcode: string | null
    remaining_qty: number
    nearest_deadline_at: string
  }>
}

export type FbsWorkspace = {
  supply: {
    id: string
    wb_supply_id: string
    name: string
    status: string
    delivery_type: 'warehouse_sc' | 'pvz'
    seller: { id: string; name: string }
    wb_warehouse: { id: number; name: string | null }
    wms_warehouse: { id: string; name: string }
    planned_destination: { office_id: number; name: string; zone: string } | null
    nearest_deadline_at: string
    packaging_task_id: string | null
    barcode_asset: FbsPrintAsset | null
  }
  stage: 'composition' | 'picking' | 'packing' | 'order_stickers' | 'handoff_prep' | 'delivery' | 'tracking'
  progress: { picked: number; packed: number; metadata_ready: number; stickers_ready: number; total: number }
  blockers: Array<{ stage: string; code: string; message: string; order_id: string | null; retryable: boolean }>
  orders: FbsWorklistOrder[]
  cargo_places: FbsCargoPlace[]
  delivery_preflight: FbsDeliveryPreflight | null
  last_wb_sync_at: string | null
  server_now: string
}

export type FbsPrintAsset = {
  id: string
  kind: 'order_sticker' | 'cargo_place_qr' | 'supply_qr'
  status: 'requesting' | 'ready' | 'error'
  content_type: string | null
  width_mm: number | null
  height_mm: number | null
  preview_url: string | null
  download_url: string | null
  checksum: string | null
  applied_at: string | null
  error: { code: string; message: string } | null
}

export type FbsPrintBatchRequest = {
  kind: 'order_sticker' | 'cargo_place_qr' | 'supply_qr'
  order_ids?: string[]
  retry_missing: boolean
}

export type FbsPrintBatch = {
  requested: number
  ready: number
  missing: number
  failed: number
  assets: FbsPrintAsset[]
  order_errors: Array<{ order_id: string; wb_order_id: number; code: string; message: string }>
}

export type FbsCargoPlace = {
  id: string
  wb_trbx_id: string
  length_mm: number | null
  width_mm: number | null
  height_mm: number | null
  weight_g: number | null
  qr_asset: FbsPrintAsset | null
  applied_at: string | null
}

export type FbsCargoPlaceDraft = {
  client_id: string
  length_mm: number | null
  width_mm: number | null
  height_mm: number | null
  weight_g: number | null
  measurements_confirmed: boolean
}

export type FbsCargoPlacesPreflight = {
  compatible: boolean
  limits: {
    max_side_mm: number
    max_sides_sum_mm: number
    max_weight_g: number
    max_total_volume_m3: number
  }
  summary: { boxes_count: number; orders_count: number; total_volume_m3: number | null }
  issues: Array<{ client_id: string | null; code: string; message: string }>
}

export type FbsDeliveryPreflight = {
  can_deliver: boolean
  version: string
  checked_at: string
  checks: Array<{ code: string; message: string; ok: boolean; order_id: string | null }>
}
```

## FBSFE-010 — API client и error mapping

**depends_on:** FBSFLOW-030, FBSFLOW-040, FBSFLOW-130  
**ownership:** `frontend/src/screens/v2/fbsApi.ts`, `frontend/src/utils/readApiErrorMessage.ts`, новые unit tests клиента.

### Сделать

1. Ввести типы и функции ровно из разделов 1–2.
2. Ни одна функция не делает business fallback на старый endpoint.
3. `idempotency_key` создаёт caller один раз на пользовательскую операцию и переиспользует при retry.
4. `preview_url`/`download_url` открываются как URL; `sticker_file` и `barcode_file` больше не интерпретируются как base64.
5. Разобрать structured error envelope и показать русский `message`; `code` сохранить для branching/tests.

### Gate

Unit tests проверяют exact URL/method/body, structured 409, timeout, retry with same idempotency key, binary asset URL без base64 prefix.

## FBSFE-020 — операторский список заказов

**depends_on:** FBSFE-010  
**ownership:** `FfFbsOrdersScreen.tsx`, `FbsChips.tsx`, `ff-fbs-orders.spec.ts`.

### Сделать

1. В строке: увеличиваемое фото, полное название, артикулы, ШК, размер, seller, оба склада, locations, available unpacked, buyer type, cargo, can_pvz, metadata state, order status, created/deadline.
2. Удалить цену.
3. Live timer обновлять раз в 30 секунд от пары `server_now` + client elapsed, чтобы clock skew клиента не искажал дедлайн.
4. В selection сразу отображать per-order blockers от сервера.
5. Не заменять missing data буквой/прочерком без пояснения: писать `Товар не сопоставлен`, `Ячейка не назначена`, `Остаток отсутствует`.

### Gate

TC-01..05; Playwright видит изменившийся timer без reload, фото preview, полные identifiers, отсутствие колонки цены.

## FBSFE-030 — создание поставки через preflight

**depends_on:** FBSFE-010, FBSFE-020  
**ownership:** `FfFbsOrdersScreen.tsx`, новый `FbsSupplyCreateDialog.tsx`, `ff-fbs-supply-create.spec.ts`.

### Сделать

1. Dialog показывает summary из server preflight: seller, WB/WMS warehouses, buyer, cargo, counts, marking count, PVZ split, nearest deadline.
2. Label только `Планируемый способ сдачи`; для PVZ пояснить, что конкретный пункт заранее не фиксируется.
3. Любое изменение selection/delivery type заново вызывает preflight.
4. Submit доступен только при `compatible=true` и вызывает один `createFbsSupplyFromOrders`.
5. Запрещён цикл frontend `create supply → add order N раз`.
6. После успеха открыть workspace из ответа, не делать blind success toast.

### Gate

TC-02..06; network assertion доказывает один WMS create command и отсутствие N add requests.

## FBSFE-040 — большой workspace поставки

**depends_on:** FBSFE-010, FBSFE-030  
**ownership:** заменить `FfFbsSupplyDrawer.tsx` на `FfFbsSupplyWorkspace.tsx`, routing/caller, `ff-fbs-workspace.spec.ts`.

### Сделать

1. Почти полноэкранный Dialog/Page: width min(1500px, 98vw), height 94vh; xs full screen.
2. Header всегда показывает supply number/name, seller, WB/WMS warehouses, planned route, nearest deadline, overall progress, blocker count.
3. Этапы строго: Состав → Подбор → Упаковка и маркировка → Стикеры WB → Подготовка к сдаче → Передача и статусы.
4. На этапе одна primary action; disabled action сопровождается видимыми blockers.
5. При переключении supply/action очищать старые notifications.
6. Старый drawer можно оставить только как read-only quick view, но из worklist открывается workspace.

### Gate

TC-06, 19; 1280×720 и 1920×1080 без горизонтально обрезанной primary action; browser test проходит каждый tab.

## FBSFE-050 — подбор без localStorage

**depends_on:** FBSFLOW-050, FBSFE-040  
**ownership:** `FfFbsPickList.tsx`, `fbsApi.ts`, `ff-fbs-picking.spec.ts`.

### Сделать

1. Удалить `loadMarks`, `saveMarks`, checkbox `Собрал`, checkbox `Упаковал` и фильтр `Не упакованы`.
2. Показать aggregated rows: location, photo/product, identifiers, required, picked, linked WB order numbers, marking need, nearest deadline.
3. Scanner sequence: location Enter → server confirmation → product focus → product Enter → server workspace replaces local state.
4. Poll workspace после операций и раз в 10–15 секунд на активном этапе; visibility hidden не poll.
5. Ошибка показывает конкретный product/location/requested/available.
6. Undo доступен только если server order pick state допускает.

### Gate

TC-07..09; reload и второй browser context показывают тот же progress; localStorage key `fbs-picklist-*` не создаётся.

## FBSFE-060 — существующая упаковка и metadata

**depends_on:** FBSFLOW-060, FBSFLOW-070, FBSFE-040  
**ownership:** workspace packing stage, `FfPackagingPage.tsx` только reusable panel props, metadata row/dialog, `ff-fbs-packaging.spec.ts`.

### Сделать

1. По `packaging_task_id` встроить существующий `FfPackagingTaskPanel`; второй form/state не создавать.
2. Убрать внутри FBS глобальный link `Осталось промаркировать`.
3. На каждой WB-order row показать required metadata и фактический state.
4. Scanner metadata сохраняет raw input, включая GS; обычный `.trim()` для КИЗ запрещён.
5. Отдельную primary button `Передать напечатанные КИЗ в WB` не делать: автоматическое server state после physical confirmation.
6. Manual input спрятать в admin emergency dialog с reason, если backend его предоставляет.

### Gate

TC-10..14; two same SKU pack into two exact orders; rejected KIZ visible and blocks delivery.

## FBSFE-070 — preview и печать

**depends_on:** FBSFLOW-080, FBSFE-040  
**ownership:** новый `FbsPrintPreviewDialog.tsx`, workspace sticker stage, `ff-fbs-print.spec.ts`.

### Сделать

1. One/selected/all-ready/retry-missing через `fetchFbsPrintBatch`.
2. До `window.print()` показать preview, ready/missing/failed counts и exact order errors.
3. Для order sticker CSS page 58mm×40mm, margin 0, scale 100%.
4. Не открывать print window при ready=0.
5. `print_opened` и `applied` — разные actions; applied подтверждается после физического нанесения.
6. Точные labels: `Печать стикера заказа WB`, `Печать QR грузоместа WB`, `Печать QR поставки WB`.

### Gate

TC-15,16; asset response с relative path не рендерится; PNG preview non-empty; missing list visible; no blank popup.

## FBSFE-080 — ПВЗ / склад-СЦ / delivery / tracking

**depends_on:** FBSFLOW-090, FBSFLOW-100, FBSFLOW-110, FBSFE-040, FBSFE-070  
**ownership:** workspace handoff/delivery stages, cargo place component, `ff-fbs-delivery.spec.ts`.

### Сделать

1. PVZ: count physical boxes, preflight dimensions, create cargo places, list, preview/print each/all QR, applied confirmation.
2. Не показывать order→cargo-place assignment и не требовать WHB box.
3. Warehouse/SC: no cargo places; planned destination/zone is internal plan; after deliver show supply QR.
4. Перед deliver всегда call `preflightFbsDelivery`, render every check, keep returned `version`.
5. Deliver uses same version + one idempotency key. Timeout/409 не показывают success и не меняют workspace status локально.
6. Tracking показывает per-order accepted/rejected/retry status and last sync freshness.

### Gate

TC-17..22; route-specific components mutually exclusive; stale preflight rejected; timeout text exactly says WB did not confirm and local status is unchanged.

## FBSFE-090 — полный браузерный gate

**depends_on:** FBSFLOW-120 и все FBSFE-020..080  
**ownership:** `frontend/tests-e2e/ff-fbs-full-flow.spec.ts`, shared e2e helpers, final `HANDOFF.md` evidence.

### Сделать

1. Playwright не route-mock’ает WMS API: браузер идёт в настоящий backend/PostgreSQL/queue/emulator.
2. Два flows: PVZ и warehouse/SC.
3. Второй browser context доказывает shared picking progress.
4. Fault cases: timeout, 409 MetaValidationFail, missing sticker.
5. Screenshots ключевых этапов приложить как evidence, но assertions остаются semantic/data-testid.

### Gate

```bash
cd frontend
npm run build
npm run test:e2e -- tests-e2e/ff-fbs-full-flow.spec.ts
```

Плюс backend full-flow gate из FBSFLOW-140. Готовность live WB отдельно не заявлять без TC-24.

## Что нельзя делать на frontend

- не хранить operational state в localStorage/sessionStorage;
- не рассчитывать совместимость только в браузере;
- не делать optimistic success для WB mutation;
- не использовать общий label `Стикеры`;
- не считать `window.open()` доказательством печати/нанесения;
- не показывать конкретный ПВЗ как назначенный WB;
- не оставлять цену в основном операторском worklist;
- не создавать ещё одну форму упаковки;
- не добавлять frontend fallback на старый unsafe create/add-order flow.
