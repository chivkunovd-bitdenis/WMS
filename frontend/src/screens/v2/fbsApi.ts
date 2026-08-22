import { apiUrl } from '../../api'
import { readApiErrorMessage } from '../../utils/readApiErrorMessage'

// Реальный backend-контракт (HANDOFF Composer):
//   GET /operations/fbs-orders?seller_id=&limit=&offset=  → list[FbsOrderOut]
// Параметра статуса/вкладки на сервере НЕТ — заказы отдаются списком, а группировку
// по вкладкам (Новые / На сборке / В доставке / Завершённые) делаем на клиенте по полю status.
// Имя селлера и товара в ответе отсутствуют: имя селлера резолвим из списка sellers,
// товар показываем по артикулу/штрихкоду, а «не сопоставлен» — по mapping_status.

export type FbsOrderRow = {
  id: string
  seller_id: string
  warehouse_id: string
  product_id: string | null
  wb_order_id: number
  wb_rid: string | null
  wb_nm_id: number | null
  wb_chrt_id: number | null
  wb_article: string | null
  wb_barcode: string | null
  price: number | null
  is_legal: boolean
  cargo_type: string | null
  wb_office_id: number | null
  can_pvz: boolean
  supply_id: string | null
  trbx_id: string | null
  status: string
  wb_status: string | null
  supplier_status: string | null
  created_at_wb: string
  deadline_at: string
  mapping_status: string // mapped | missing
  reserve_status: string
  created_at: string
  updated_at: string
}

export type FbsOrdersTab = 'new' | 'active'

// Рабочие вкладки FF: создание поставки и сборка уже созданной поставки.
export const TAB_STATUSES: Record<FbsOrdersTab, string[]> = {
  new: ['new'],
  active: ['in_supply', 'assembling', 'packed'],
}

export async function fetchFbsOrders(
  token: string,
  authHeaders: (t: string) => Record<string, string>,
  params: { sellerId?: string | null },
): Promise<FbsOrderRow[]> {
  const qs = new URLSearchParams({ limit: '500' })
  if (params.sellerId) qs.set('seller_id', params.sellerId)
  const res = await fetch(apiUrl(`/operations/fbs-orders?${qs.toString()}`), {
    headers: { ...authHeaders(token) },
  })
  if (!res.ok) {
    throw new Error(await readApiErrorMessage(res))
  }
  return (await res.json()) as FbsOrderRow[]
}

// ── Отгрузки (supplies) ──────────────────────────────────────────────────────
// Реальные ручки backend/app/api/fbs_supplies.py (все под /operations/fbs-supplies).
// Списка отгрузок на сервере нет: карточку открываем по id (из заказа или после создания).

export type FbsSupplyOrder = {
  id: string
  wb_order_id: number
  status: string
  supply_id: string | null
  sticker_code: string | null
  sticker_file: string | null // base64 PNG
}

export type FbsSupply = {
  id: string
  seller_id: string
  warehouse_id: string
  wb_supply_id: string
  name: string
  status: string // draft | assembling | in_delivery | done
  delivery_type: string // warehouse_sc | pvz
  cargo_type: string | null
  wb_office_id: number | null
  barcode_file: string | null // base64 PNG QR поставки
  document_number: string | null
  display_number: string | null
  planned_shipment_date: string | null
  created_at_wb: string | null
  delivered_at: string | null
  created_at: string
  updated_at: string
  orders: FbsSupplyOrder[] | null
}

export type FbsSticker = {
  order_id: string
  wb_order_id: number
  sticker_code: string | null
  sticker_file: string | null
}

async function jsonOrThrow<T>(res: Response): Promise<T> {
  if (!res.ok) {
    const copy = res.clone()
    try {
      const payload = (await copy.json()) as {
        detail?: { code?: unknown; message?: unknown; context?: unknown; retryable?: unknown }
      }
      const detail = payload.detail
      if (
        detail &&
        typeof detail === 'object' &&
        typeof detail.code === 'string' &&
        typeof detail.message === 'string'
      ) {
        throw new FbsApiError(
          detail.code,
          detail.message,
          detail.context,
          detail.retryable === true,
          res.status,
        )
      }
    } catch (error) {
      if (error instanceof FbsApiError) throw error
    }
    throw new Error(await readApiErrorMessage(res))
  }
  return (await res.json()) as T
}

export class FbsApiError extends Error {
  readonly code: string
  readonly context: unknown
  readonly retryable: boolean
  readonly status: number

  constructor(code: string, message: string, context: unknown, retryable: boolean, status: number) {
    super(message)
    this.name = 'FbsApiError'
    this.code = code
    this.context = context
    this.retryable = retryable
    this.status = status
  }
}

export type FbsOrderMetadata = {
  required: string[]
  optional: string[]
  states: Array<{
    kind: string
    status:
      | 'missing'
      | 'assigned'
      | 'sending'
      | 'pending'
      | 'accepted'
      | 'allowed_without_check'
      | 'rejected'
      | 'replacement_required'
    reason: string | null
    source?: 'pool' | 'operator'
    /** Последние символы кода маркировки — чтобы оператор сверил строку с этикеткой. */
    value_tail?: string | null
  }>
  delivery_allowed: boolean
  last_checked_at: string | null
}

export type FbsWorklistWarehouseOption = {
  id: string
  name: string
  wb_warehouse: { id: number; name: string | null }
}

export type FbsSellerWarehouse = {
  id: number | null
  name: string | null
  address: string | null
  officeId: number | null
  cargoType: number | null
  deliveryType: number | null
  isDeleting: boolean | null
  isProcessing: boolean | null
}

export type FbsSellerOffice = {
  id: number | null
  officeId: number | null
  name: string | null
  city: string | null
  address: string | null
  selected: boolean | null
}

export type FbsWorklistOrder = {
  id: string
  wb_order_id: number
  status: string
  wb_status: string | null
  supplier_status: string | null
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
    sku: string | null
    chrt_id: number | null
    category: string | null
    color: string | null
    size: string | null
    packaging_instructions?: string | null
    has_packaging_instructions?: boolean
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
    code: string | null
    status: 'not_requested' | 'requesting' | 'ready' | 'print_opened' | 'applied' | 'error'
    asset_url: string | null
    applied_at: string | null
  }
  pick: {
    status: 'pending' | 'picked' | 'returned'
    location_code: string | null
    picked_at: string | null
  }
  pack: { status: 'pending' | 'packed'; packed_at: string | null }
  created_at_wb: string
  deadline_at: string
  supply_id: string | null
  selection_blockers: Array<{ code: string; message: string }>
}

export type FbsWorklistPage = {
  items: FbsWorklistOrder[]
  next_cursor: string | null
  server_now: string
  warehouse_options: FbsWorklistWarehouseOption[]
}

export type FbsSupplyPreflightRequest = {
  order_ids: string[]
  planned_delivery_type: 'warehouse_sc' | 'pvz'
  selected_warehouse_id?: string | null
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
  stock_preflight: {
    compatible: boolean
    recommended_warehouse: { id: string; name: string } | null
    warning_lines: FbsSupplyPreflightInventoryLine[]
    blocking_lines: FbsSupplyPreflightInventoryLine[]
  }
  warehouse_options: Array<{ id: string; name: string }>
  recommended_warehouse: { id: string; name: string } | null
  inventory: FbsSupplyPreflightInventoryLine[]
}

export type FbsSupplyPreflightInventoryLine = {
  product_id: string
  product_name: string
  required: number
  current: number
  total: number
  shortage: number
  source_warehouse: { id: string; name: string; available: number } | null
  source_warehouses: Array<{
    id: string
    name: string
    quantity: number
    available: number
  }>
}

export type FbsSupplyCreateFromOrdersRequest = {
  name: string
  order_ids: string[]
  planned_delivery_type: 'warehouse_sc' | 'pvz'
  planned_destination?: { office_id: number; name: string; zone: string } | null
  idempotency_key: string
  selected_warehouse_id?: string | null
}

export type FbsSupplyAddOrdersRequest = {
  order_ids: string[]
  idempotency_key: string
}

export type FbsSupplyWorklistItem = {
  id: string
  wb_supply_id: string
  name: string
  status: string
  seller: { id: string; name: string }
  wb_warehouse: { id: number; name: string | null }
  wms_warehouse: { id: string; name: string }
  orders_count: number
  units_count: number
  boxes_count: number
  planned_shipment_date: string | null
  can_add_orders: boolean
}

export type FbsSupplyWorklistPage = {
  items: FbsSupplyWorklistItem[]
  server_now: string
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

export type FbsWarehouseScan = {
  type: 'warehouse' | 'location'
  id: string
  warehouse_id: string
  name?: string | null
  code: string
}

export type PickScanAttempt = { orderId: string; key: string }

export function resolvePickScanAttempt(
  orders: Array<{ id: string; pending: boolean; matches: boolean }>,
  remembered: PickScanAttempt | undefined,
  createKey: () => string,
): PickScanAttempt | null {
  const pendingOrder = orders.find((order) => order.pending && order.matches)
  const matchingOrder = pendingOrder ?? (remembered
    ? orders.find((order) => order.id === remembered.orderId && order.matches)
    : undefined)
  if (!matchingOrder) return null
  if (remembered?.orderId === matchingOrder.id) return remembered
  return { orderId: matchingOrder.id, key: createKey() }
}

export async function resolveFbsWarehouseScan(
  token: string,
  ah: AuthHeaders,
  barcode: string,
): Promise<FbsWarehouseScan> {
  const qs = new URLSearchParams({ barcode })
  return jsonOrThrow<FbsWarehouseScan>(
    await fetch(apiUrl(`/warehouses/resolve?${qs.toString()}`), {
      headers: { ...ah(token) },
    }),
  )
}

export type FbsPrintAsset = {
  id: string
  kind: 'order_sticker' | 'cargo_place_qr' | 'supply_qr' | 'box_qr'
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
  kind: FbsPrintAsset['kind']
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

export type FbsOrderPrintTapeRequest = {
  order_ids: string[]
  layout_json: { units: Array<{ block: 'cz' | 'label'; copies: number }> } | null
  allow_partial: boolean
  include_order_qr: boolean
  reprint: boolean
}

export type FbsOrderPrintTapeOrder = {
  order_id: string
  wb_order_id: number
  requires_honest_sign: boolean
  qr_asset: FbsPrintAsset | null
  codes: string[]
  printed_codes: Array<{ id: string; cis_code: string; has_label_artifact: boolean }>
  shortage: number | null
}

export type FbsOrderPrintTape = {
  orders: FbsOrderPrintTapeOrder[]
  requested: number
  ready: number
  missing: number
  failed: number
  order_errors: Array<{ order_id: string; wb_order_id: number; code: string; message: string }>
  shortage: number
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

export type FbsPackingBox = {
  id: string
  box_number: number
  barcode: string
  assigned_order_ids: string[]
  trbx_id: string | null
  wb_trbx_id: string | null
  qr_asset: FbsPrintAsset | null
  without_distribution: boolean
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

export type FbsTrackingOrder = {
  order_id: string
  wb_order_id: number
  tracking_label: string
  wb_status: string | null
  local_status: string
}

export type FbsTrackingSummary = {
  status: string
  orders: FbsTrackingOrder[]
  last_wb_sync_at: string | null
  checked_at: string
}

export type FbsPartialRejection = {
  accepted_orders: Array<FbsTrackingOrder & { reason: string | null; remaining_deadline: string }>
  rejected_orders: Array<FbsTrackingOrder & { reason: string | null; remaining_deadline: string }>
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
    planned_shipment_date: string | null
    nearest_deadline_at: string
    packaging_task_id: string | null
    barcode_asset: FbsPrintAsset | null
    honest_sign_skipped?: boolean
  }
  stage:
    | 'composition'
    | 'picking'
    | 'packing'
    | 'order_stickers'
    | 'handoff_prep'
    | 'delivery'
    | 'tracking'
  progress: { picked: number; packed: number; metadata_ready: number; stickers_ready: number; total: number }
  blockers: Array<{
    stage: string
    code: string
    message: string
    order_id: string | null
    retryable: boolean
  }>
  orders: FbsWorklistOrder[]
  cargo_places: FbsCargoPlace[]
  boxes: FbsPackingBox[]
  marking_pool?: { required: number; available: number; shortage: number; orders_without_code: string[] }
  delivery_preflight: FbsDeliveryPreflight | null
  last_wb_sync_at: string | null
  server_now: string
  tracking_summary?: FbsTrackingSummary | null
  partial_rejection?: FbsPartialRejection | null
  picking_auto_passed_reason?: string | null
  wb_sync_stale?: boolean
}

type AuthHeaders = (token: string) => Record<string, string>

function jsonHeaders(token: string, ah: AuthHeaders): Record<string, string> {
  return { ...ah(token), 'Content-Type': 'application/json' }
}

export function createFbsIdempotencyKey(): string {
  return globalThis.crypto?.randomUUID?.() ?? `${Date.now()}-${Math.random().toString(16).slice(2)}`
}

export function resolveFbsAssetUrl(path: string): string {
  return /^(https?:|data:)/i.test(path) ? path : apiUrl(path)
}

export async function fetchFbsWorklist(
  token: string,
  ah: AuthHeaders,
  params: {
    seller_id?: string | null
    status_group?: string | null
    wb_warehouse_id?: string | null
    search?: string | null
    limit?: number
    cursor?: string | null
  } = {},
): Promise<FbsWorklistPage> {
  const qs = new URLSearchParams({ limit: String(params.limit ?? 100) })
  if (params.seller_id) qs.set('seller_id', params.seller_id)
  if (params.status_group) qs.set('status_group', params.status_group)
  if (params.wb_warehouse_id) qs.set('wb_warehouse_id', params.wb_warehouse_id)
  if (params.search) qs.set('search', params.search)
  if (params.cursor) qs.set('cursor', params.cursor)
  return jsonOrThrow<FbsWorklistPage>(
    await fetch(apiUrl(`/operations/fbs-orders/worklist?${qs.toString()}`), {
      headers: { ...ah(token) },
    }),
  )
}

export async function preflightFbsSupply(
  token: string,
  ah: AuthHeaders,
  body: FbsSupplyPreflightRequest,
): Promise<FbsSupplyPreflight> {
  return jsonOrThrow<FbsSupplyPreflight>(
    await fetch(apiUrl('/operations/fbs-supplies/preflight'), {
      method: 'POST',
      headers: jsonHeaders(token, ah),
      body: JSON.stringify(body),
    }),
  )
}

export async function createFbsSupplyFromOrders(
  token: string,
  ah: AuthHeaders,
  body: FbsSupplyCreateFromOrdersRequest,
): Promise<FbsWorkspace> {
  return jsonOrThrow<FbsWorkspace>(
    await fetch(apiUrl('/operations/fbs-supplies/from-orders'), {
      method: 'POST',
      headers: jsonHeaders(token, ah),
      body: JSON.stringify(body),
    }),
  )
}

export async function fetchFbsSupplyWorklist(
  token: string,
  ah: AuthHeaders,
  params: {
    seller_id?: string | null
    warehouse_id?: string | null
    status_group?: string | null
    limit?: number
  } = {},
): Promise<FbsSupplyWorklistPage> {
  const qs = new URLSearchParams({ limit: String(params.limit ?? 100) })
  if (params.seller_id) qs.set('seller_id', params.seller_id)
  if (params.warehouse_id) qs.set('warehouse_id', params.warehouse_id)
  if (params.status_group) qs.set('status_group', params.status_group)
  return jsonOrThrow<FbsSupplyWorklistPage>(
    await fetch(apiUrl(`/operations/fbs-supplies/worklist?${qs.toString()}`), {
      headers: { ...ah(token) },
    }),
  )
}

export async function addFbsOrdersToSupply(
  token: string,
  ah: AuthHeaders,
  supplyId: string,
  body: FbsSupplyAddOrdersRequest,
): Promise<FbsWorkspace> {
  return jsonOrThrow<FbsWorkspace>(
    await fetch(apiUrl(`/operations/fbs-supplies/${supplyId}/orders/batch`), {
      method: 'POST',
      headers: jsonHeaders(token, ah),
      body: JSON.stringify(body),
    }),
  )
}

export async function fetchFbsWorkspace(
  token: string,
  ah: AuthHeaders,
  id: string,
): Promise<FbsWorkspace> {
  return jsonOrThrow<FbsWorkspace>(
    await fetch(apiUrl(`/operations/fbs-supplies/${id}/workspace`), {
      headers: { ...ah(token) },
    }),
  )
}

export async function updateFbsSupplyPlannedShipmentDate(
  token: string,
  ah: AuthHeaders,
  id: string,
  planned_shipment_date: string | null,
): Promise<FbsWorkspace> {
  return jsonOrThrow<FbsWorkspace>(
    await fetch(apiUrl(`/operations/fbs-supplies/${id}/planned-shipment-date`), {
      method: 'PATCH',
      headers: jsonHeaders(token, ah),
      body: JSON.stringify({ planned_shipment_date }),
    }),
  )
}

export async function syncFbsSupplyTracking(
  token: string,
  ah: AuthHeaders,
  id: string,
): Promise<FbsWorkspace> {
  return jsonOrThrow<FbsWorkspace>(
    await fetch(apiUrl(`/operations/fbs-supplies/${id}/sync-tracking`), {
      method: 'POST',
      headers: { ...ah(token) },
    }),
  )
}

export async function retryFbsSupplyQr(
  token: string,
  ah: AuthHeaders,
  id: string,
): Promise<FbsWorkspace> {
  return jsonOrThrow<FbsWorkspace>(
    await fetch(apiUrl(`/operations/fbs-supplies/${id}/retry-supply-qr`), {
      method: 'POST',
      headers: { ...ah(token) },
    }),
  )
}

export async function skipFbsSupplyHonestSign(
  token: string,
  ah: AuthHeaders,
  id: string,
): Promise<FbsWorkspace> {
  // Снятие требования Честного знака со всей поставки.
  // Тело пустое, ответ — обычная выдача поставки с обновлённым флагом honest_sign_skipped.
  return jsonOrThrow<FbsWorkspace>(
    await fetch(apiUrl(`/operations/fbs-supplies/${id}/honest-sign-skip`), {
      method: 'POST',
      headers: jsonHeaders(token, ah),
      body: JSON.stringify({}),
    }),
  )
}

export async function startFbsSupplyWork(token: string, ah: AuthHeaders, id: string): Promise<FbsWorkspace> {
  return jsonOrThrow<FbsWorkspace>(
    await fetch(apiUrl(`/operations/fbs-supplies/${id}/start-work`), {
      method: 'POST',
      headers: { ...ah(token) },
    }),
  )
}

export async function scanFbsPickLocation(
  token: string,
  ah: AuthHeaders,
  id: string,
  location_barcode: string,
): Promise<FbsPickLocation> {
  return jsonOrThrow<FbsPickLocation>(
    await fetch(apiUrl(`/operations/fbs-supplies/${id}/pick/scan-location`), {
      method: 'POST',
      headers: jsonHeaders(token, ah),
      body: JSON.stringify({ location_barcode }),
    }),
  )
}

export async function scanFbsPickProduct(
  token: string,
  ah: AuthHeaders,
  id: string,
  body: { location_id: string; product_barcode: string; order_id: string; idempotency_key: string },
): Promise<FbsWorkspace> {
  return jsonOrThrow<FbsWorkspace>(
    await fetch(apiUrl(`/operations/fbs-supplies/${id}/pick/scan-product`), {
      method: 'POST',
      headers: jsonHeaders(token, ah),
      body: JSON.stringify(body),
    }),
  )
}

export async function selectFbsManualPickLocation(
  token: string,
  ah: AuthHeaders,
  supplyId: string,
  location_id: string,
): Promise<FbsPickLocation> {
  return jsonOrThrow<FbsPickLocation>(
    await fetch(apiUrl(`/operations/fbs-supplies/${supplyId}/pick/manual/location`), {
      method: 'POST', headers: jsonHeaders(token, ah), body: JSON.stringify({ location_id }),
    }),
  )
}

export async function confirmFbsManualPick(
  token: string,
  ah: AuthHeaders,
  supplyId: string,
  body: { location_id: string; product_id: string; order_id: string; idempotency_key: string },
): Promise<FbsWorkspace> {
  return jsonOrThrow<FbsWorkspace>(
    await fetch(apiUrl(`/operations/fbs-supplies/${supplyId}/pick/manual`), {
      method: 'POST', headers: jsonHeaders(token, ah), body: JSON.stringify(body),
    }),
  )
}

export async function undoFbsPick(
  token: string,
  ah: AuthHeaders,
  supplyId: string,
  orderId: string,
  idempotency_key: string,
): Promise<FbsWorkspace> {
  return jsonOrThrow<FbsWorkspace>(
    await fetch(apiUrl(`/operations/fbs-supplies/${supplyId}/pick/${orderId}/undo`), {
      method: 'POST',
      headers: jsonHeaders(token, ah),
      body: JSON.stringify({ idempotency_key }),
    }),
  )
}

export async function createFbsPackingBoxes(
  token: string,
  ah: AuthHeaders,
  supplyId: string,
  body: { count: number; idempotency_key: string; without_distribution?: boolean },
): Promise<FbsWorkspace> {
  return jsonOrThrow<FbsWorkspace>(
    await fetch(apiUrl(`/operations/fbs-supplies/${supplyId}/boxes`), {
      method: 'POST', headers: jsonHeaders(token, ah), body: JSON.stringify(body),
    }),
  )
}

export async function assignFbsPackingBoxOrders(
  token: string,
  ah: AuthHeaders,
  supplyId: string,
  boxId: string,
  order_ids: string[],
): Promise<FbsWorkspace> {
  return jsonOrThrow<FbsWorkspace>(
    await fetch(apiUrl(`/operations/fbs-supplies/${supplyId}/boxes/${boxId}/orders`), {
      method: 'POST', headers: jsonHeaders(token, ah), body: JSON.stringify({ order_ids }),
    }),
  )
}

export async function removeFbsPackingBoxOrder(
  token: string,
  ah: AuthHeaders,
  supplyId: string,
  boxId: string,
  orderId: string,
): Promise<FbsWorkspace> {
  return jsonOrThrow<FbsWorkspace>(
    await fetch(apiUrl(`/operations/fbs-supplies/${supplyId}/boxes/${boxId}/orders/${orderId}`), {
      method: 'DELETE', headers: { ...ah(token) },
    }),
  )
}

export async function deleteFbsPackingBox(
  token: string,
  ah: AuthHeaders,
  supplyId: string,
  boxId: string,
  idempotency_key: string,
): Promise<FbsWorkspace> {
  return jsonOrThrow<FbsWorkspace>(
    await fetch(apiUrl(`/operations/fbs-supplies/${supplyId}/boxes/${boxId}`), {
      method: 'DELETE', headers: jsonHeaders(token, ah), body: JSON.stringify({ idempotency_key }),
    }),
  )
}

export async function clearFbsPackingBox(
  token: string,
  ah: AuthHeaders,
  supplyId: string,
  boxId: string,
): Promise<FbsWorkspace> {
  return jsonOrThrow<FbsWorkspace>(
    await fetch(apiUrl(`/operations/fbs-supplies/${supplyId}/boxes/${boxId}/clear`), {
      method: 'POST', headers: { ...ah(token) },
    }),
  )
}

export async function retryFbsPackingBoxQr(
  token: string,
  ah: AuthHeaders,
  supplyId: string,
  boxId: string,
): Promise<FbsWorkspace> {
  return jsonOrThrow<FbsWorkspace>(
    await fetch(apiUrl(`/operations/fbs-supplies/${supplyId}/boxes/${boxId}/retry-qr`), {
      method: 'POST', headers: { ...ah(token) },
    }),
  )
}

export async function fetchFbsOrderMetadata(
  token: string,
  ah: AuthHeaders,
  orderId: string,
): Promise<FbsOrderMetadata> {
  return jsonOrThrow<FbsOrderMetadata>(
    await fetch(apiUrl(`/operations/fbs-orders/${orderId}/metadata`), {
      headers: { ...ah(token) },
    }),
  )
}

export async function fetchFbsPrintBatch(
  token: string,
  ah: AuthHeaders,
  supplyId: string,
  body: FbsPrintBatchRequest,
): Promise<FbsPrintBatch> {
  return jsonOrThrow<FbsPrintBatch>(
    await fetch(apiUrl(`/operations/fbs-supplies/${supplyId}/print-assets`), {
      method: 'POST',
      headers: jsonHeaders(token, ah),
      body: JSON.stringify(body),
    }),
  )
}

export async function printFbsOrderTape(
  token: string,
  ah: AuthHeaders,
  supplyId: string,
  body: FbsOrderPrintTapeRequest,
): Promise<FbsOrderPrintTape> {
  return jsonOrThrow<FbsOrderPrintTape>(
    await fetch(apiUrl(`/operations/fbs-supplies/${supplyId}/order-print-tape`), {
      method: 'POST',
      headers: jsonHeaders(token, ah),
      body: JSON.stringify(body),
    }),
  )
}

export async function confirmFbsPrintApplied(
  token: string,
  ah: AuthHeaders,
  assetId: string,
  idempotency_key: string,
): Promise<FbsPrintAsset> {
  return jsonOrThrow<FbsPrintAsset>(
    await fetch(apiUrl(`/operations/fbs-print-assets/${assetId}/applied`), {
      method: 'POST',
      headers: jsonHeaders(token, ah),
      body: JSON.stringify({ idempotency_key }),
    }),
  )
}

export async function preflightFbsCargoPlaces(
  token: string,
  ah: AuthHeaders,
  supplyId: string,
  body: { count: number; boxes: FbsCargoPlaceDraft[] },
): Promise<FbsCargoPlacesPreflight> {
  return jsonOrThrow<FbsCargoPlacesPreflight>(
    await fetch(apiUrl(`/operations/fbs-supplies/${supplyId}/cargo-places/preflight`), {
      method: 'POST',
      headers: jsonHeaders(token, ah),
      body: JSON.stringify(body),
    }),
  )
}

export async function createFbsCargoPlaces(
  token: string,
  ah: AuthHeaders,
  supplyId: string,
  body: { count: number; boxes: FbsCargoPlaceDraft[]; idempotency_key: string },
): Promise<FbsCargoPlace[]> {
  const response = await jsonOrThrow<{ cargo_places: FbsCargoPlace[] }>(
    await fetch(apiUrl(`/operations/fbs-supplies/${supplyId}/cargo-places`), {
      method: 'POST',
      headers: jsonHeaders(token, ah),
      body: JSON.stringify(body),
    }),
  )
  return response.cargo_places
}

export async function deleteFbsCargoPlaces(
  token: string,
  ah: AuthHeaders,
  supplyId: string,
  body: { wb_trbx_ids: string[]; idempotency_key: string },
): Promise<FbsCargoPlace[]> {
  const response = await jsonOrThrow<{ cargo_places: FbsCargoPlace[] }>(
    await fetch(apiUrl(`/operations/fbs-supplies/${supplyId}/cargo-places`), {
      method: 'DELETE',
      headers: jsonHeaders(token, ah),
      body: JSON.stringify(body),
    }),
  )
  return response.cargo_places
}

export async function fetchFbsCargoPlaces(
  token: string,
  ah: AuthHeaders,
  supplyId: string,
): Promise<FbsCargoPlace[]> {
  const response = await jsonOrThrow<{ cargo_places: FbsCargoPlace[] }>(
    await fetch(apiUrl(`/operations/fbs-supplies/${supplyId}/cargo-places`), {
      headers: { ...ah(token) },
    }),
  )
  return response.cargo_places
}

export async function preflightFbsDelivery(
  token: string,
  ah: AuthHeaders,
  supplyId: string,
): Promise<FbsDeliveryPreflight> {
  return jsonOrThrow<FbsDeliveryPreflight>(
    await fetch(apiUrl(`/operations/fbs-supplies/${supplyId}/delivery-preflight`), {
      method: 'POST',
      headers: { ...ah(token) },
    }),
  )
}

export async function createFbsSupply(
  token: string,
  ah: (t: string) => Record<string, string>,
  body: {
    seller_id: string
    warehouse_id: string
    name: string
    delivery_type: string
    cargo_type?: string | null
    wb_office_id?: number | null
  },
): Promise<FbsSupply> {
  const res = await fetch(apiUrl('/operations/fbs-supplies'), {
    method: 'POST',
    headers: { ...ah(token), 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  return jsonOrThrow<FbsSupply>(res)
}

export async function getFbsSupply(
  token: string,
  ah: (t: string) => Record<string, string>,
  id: string,
): Promise<FbsSupply> {
  const res = await fetch(apiUrl(`/operations/fbs-supplies/${id}`), { headers: { ...ah(token) } })
  return jsonOrThrow<FbsSupply>(res)
}

export async function addOrderToFbsSupply(
  token: string,
  ah: (t: string) => Record<string, string>,
  id: string,
  orderId: string,
): Promise<FbsSupply> {
  const res = await fetch(apiUrl(`/operations/fbs-supplies/${id}/orders`), {
    method: 'POST',
    headers: { ...ah(token), 'Content-Type': 'application/json' },
    body: JSON.stringify({ order_id: orderId }),
  })
  return jsonOrThrow<FbsSupply>(res)
}

export async function generateFbsSupplyStickers(
  token: string,
  ah: (t: string) => Record<string, string>,
  id: string,
  force = false,
): Promise<FbsSticker[]> {
  const res = await fetch(apiUrl(`/operations/fbs-supplies/${id}/stickers`), {
    method: 'POST',
    headers: { ...ah(token), 'Content-Type': 'application/json' },
    body: JSON.stringify({ force }),
  })
  const data = await jsonOrThrow<{ stickers: FbsSticker[] }>(res)
  return data.stickers
}

export function deliverFbsSupply(
  token: string,
  ah: (t: string) => Record<string, string>,
  id: string,
  body: { idempotency_key: string; confirmed_preflight_version?: string | null },
): Promise<FbsWorkspace>
export async function deliverFbsSupply(
  token: string,
  ah: (t: string) => Record<string, string>,
  id: string,
  body: { idempotency_key: string; confirmed_preflight_version?: string | null },
): Promise<FbsWorkspace> {
  const res = await fetch(apiUrl(`/operations/fbs-supplies/${id}/deliver`), {
    method: 'POST',
    headers: jsonHeaders(token, ah),
    body: JSON.stringify(body),
  })
  return jsonOrThrow<FbsWorkspace>(res)
}

/** Delivery is allowed only after packaging task completed (supply.status === packed). */
export function canDeliverFbsSupply(supply: FbsSupply): boolean {
  return supply.status === 'packed'
}

// Лист подбора (Экран 3). GET /operations/fbs-supplies/{id}/picking-list → { items }.
export type FbsPickingItem = {
  article: string
  sku_code: string | null
  size: string | null
  product_name: string
  quantity: number
}

export async function getFbsPickingList(
  token: string,
  ah: (t: string) => Record<string, string>,
  id: string,
): Promise<FbsPickingItem[]> {
  const res = await fetch(apiUrl(`/operations/fbs-supplies/${id}/picking-list`), {
    headers: { ...ah(token) },
  })
  const data = await jsonOrThrow<{ items: FbsPickingItem[] }>(res)
  return data.items
}

// ── Legacy trbx compatibility (deprecated) ───────────────────────────────────
// Канонический контракт ПВЗ — count-only cargo-places выше (preflightFbsCargoPlaces,
// createFbsCargoPlaces, fetchFbsCargoPlaces). Без order→trbx allocation.
// Deprecated compatibility layer:
//   POST /operations/fbs-supplies/{id}/trbx
//   POST /operations/fbs-supplies/{id}/trbx/stickers

export type FbsTrbx = {
  id: string
  wb_trbx_id: string
  packaging_box_id: string | null
  length_mm: number | null
  width_mm: number | null
  height_mm: number | null
  weight_g: number | null
  sticker_file: string | null // base64 PNG
}

export async function createFbsTrbx(
  token: string,
  ah: (t: string) => Record<string, string>,
  supplyId: string,
  count: number,
): Promise<FbsTrbx[]> {
  const res = await fetch(apiUrl(`/operations/fbs-supplies/${supplyId}/trbx`), {
    method: 'POST',
    headers: { ...ah(token), 'Content-Type': 'application/json' },
    body: JSON.stringify({ count }),
  })
  const data = await jsonOrThrow<{ trbxes: FbsTrbx[] }>(res)
  return data.trbxes
}

export async function fetchFbsTrbxStickers(
  token: string,
  ah: (t: string) => Record<string, string>,
  supplyId: string,
): Promise<FbsTrbx[]> {
  const res = await fetch(apiUrl(`/operations/fbs-supplies/${supplyId}/trbx/stickers`), {
    method: 'POST',
    headers: { ...ah(token) },
  })
  const data = await jsonOrThrow<{ trbxes: FbsTrbx[] }>(res)
  return data.trbxes
}

// ── Идентификаторы заказа (КИЗ/УИН/IMEI/GTIN) ────────────────────────────────
// Маркировка в WB привязана к ЗАКАЗУ, а не к артикулу — ручки backend/app/api/fbs_marking.py
// под /operations/fbs-orders/{order_id}/markings...

// ── Внесение чужих КИЗ по стикеру ────────────────────────────────────────────
// backend/app/api/fbs_kiz.py — спека tasks/fbs-kiz-manual-binding/TASK.md §5.
// Сопоставление идёт ТОЛЬКО по стикеру: QR даёт заказ, КИЗ вешается на этот заказ.

export type FbsKizLookup = {
  order_id: string
  wb_order_id: number
  product: {
    name: string
    image_url: string | null
    barcode: string | null
    seller_article: string | null
  }
  current_kiz: { masked: string; meta_status: string; from_pool: boolean } | null
  needs_confirmation: boolean
  can_bind: boolean
  block_reason: string | null
}

export type FbsKizPair = { order_id: string; value: string; confirmed: boolean }

export type FbsKizValidateResult = {
  ok: boolean
  hints: string[]
}

export type FbsKizCommitResult = {
  order_id: string
  status: 'ok' | 'error'
  code: string | null
  message: string | null
}

export async function lookupFbsOrderBySticker(
  token: string,
  ah: (t: string) => Record<string, string>,
  supplyId: string,
  sticker: string,
): Promise<FbsKizLookup> {
  const query = new URLSearchParams({ supply_id: supplyId, sticker })
  const res = await fetch(apiUrl(`/operations/fbs-orders/kiz/lookup?${query.toString()}`), {
    headers: { ...ah(token) },
  })
  return jsonOrThrow<FbsKizLookup>(res)
}

export async function validateFbsKiz(
  token: string,
  ah: (t: string) => Record<string, string>,
  orderId: string,
  value: string,
): Promise<FbsKizValidateResult> {
  const res = await fetch(apiUrl('/operations/fbs-orders/kiz/validate'), {
    method: 'POST',
    headers: { ...ah(token), 'Content-Type': 'application/json' },
    body: JSON.stringify({ order_id: orderId, value }),
  })
  return jsonOrThrow<FbsKizValidateResult>(res)
}

export async function commitFbsKiz(
  token: string,
  ah: (t: string) => Record<string, string>,
  pairs: FbsKizPair[],
  idempotencyKey: string,
): Promise<FbsKizCommitResult[]> {
  const res = await fetch(apiUrl('/operations/fbs-orders/kiz/commit'), {
    method: 'POST',
    headers: { ...ah(token), 'Content-Type': 'application/json' },
    body: JSON.stringify({ pairs, idempotency_key: idempotencyKey }),
  })
  return jsonOrThrow<FbsKizCommitResult[]>(res)
}

export async function deleteFbsOrderKiz(
  token: string,
  ah: (t: string) => Record<string, string>,
  orderId: string,
): Promise<void> {
  const res = await fetch(apiUrl(`/operations/fbs-orders/${orderId}/kiz`), {
    method: 'DELETE',
    headers: { ...ah(token) },
  })
  // Успех приходит пустым 204 — разбирать в нём JSON нечего, иначе отмена,
  // которая на самом деле прошла, показывается оператору ошибкой.
  if (res.ok) return
  await jsonOrThrow<{ ok: boolean }>(res)
}

// ── Привязки складов WB ↔ WMS + синхронизация остатков ───────────────────────
// backend/app/api/fbs_sellers.py — /operations/fbs-sellers/{seller_id}/...

export async function fetchFbsSellerWarehouses(
  token: string,
  ah: AuthHeaders,
  sellerId: string,
): Promise<FbsSellerWarehouse[]> {
  return jsonOrThrow<FbsSellerWarehouse[]>(
    await fetch(apiUrl(`/operations/fbs-sellers/${sellerId}/warehouses`), {
      headers: { ...ah(token) },
    }),
  )
}

export async function fetchFbsSellerOffices(
  token: string,
  ah: AuthHeaders,
  sellerId: string,
): Promise<FbsSellerOffice[]> {
  return jsonOrThrow<FbsSellerOffice[]>(
    await fetch(apiUrl(`/operations/fbs-sellers/${sellerId}/offices`), {
      headers: { ...ah(token) },
    }),
  )
}

export type FbsWarehouseBinding = {
  id: string
  wb_warehouse_id: number
  wms_warehouse_id: string
  is_active: boolean
  stock_sync_enabled: boolean
  last_sync_status: string | null
  last_sync_at: string | null
  last_error_code: string | null
  allocated_pool_total: number
}

export type FbsStockSyncResult = {
  bindings_processed: number
  products_targeted: number
  products_confirmed: number
  products_zeroed: number
  conflicts: number
  errors: number
  binding_errors: number
}

export type FbsStockSyncJob = {
  id: string
  status: string
}

export type FbsStockSyncStatusItem = {
  chrt_id: number
  product_id: string | null
  target: number | null
  confirmed: number | null
  status: string
  error: string | null
  timestamp: string
}

export type FbsStockSyncStatus = {
  wb_warehouse_id: number
  binding_last_sync_at: string | null
  binding_last_sync_status: string | null
  binding_last_error_code: string | null
  items: FbsStockSyncStatusItem[]
}

export const STOCK_SYNC_STATUS_LABEL: Record<string, string> = {
  pending: 'Ожидание',
  confirmed: 'Подтверждено',
  error: 'Ошибка',
  conflict: 'Конфликт',
}

function sellerBase(sellerId: string): string {
  return `/operations/fbs-sellers/${sellerId}`
}

export async function fetchFbsWarehouseBindings(
  token: string,
  ah: (t: string) => Record<string, string>,
  sellerId: string,
): Promise<FbsWarehouseBinding[]> {
  const res = await fetch(apiUrl(`${sellerBase(sellerId)}/warehouse-bindings`), {
    headers: { ...ah(token) },
  })
  return jsonOrThrow<FbsWarehouseBinding[]>(res)
}

export async function upsertFbsWarehouseBinding(
  token: string,
  ah: (t: string) => Record<string, string>,
  sellerId: string,
  wbWarehouseId: number,
  body: { wms_warehouse_id: string; stock_sync_enabled: boolean },
): Promise<FbsWarehouseBinding> {
  const res = await fetch(
    apiUrl(`${sellerBase(sellerId)}/warehouse-bindings/${wbWarehouseId}`),
    {
      method: 'PUT',
      headers: { ...ah(token), 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    },
  )
  return jsonOrThrow<FbsWarehouseBinding>(res)
}

export async function disableFbsWarehouseBinding(
  token: string,
  ah: (t: string) => Record<string, string>,
  sellerId: string,
  wbWarehouseId: number,
): Promise<FbsWarehouseBinding> {
  const res = await fetch(
    apiUrl(`${sellerBase(sellerId)}/warehouse-bindings/${wbWarehouseId}`),
    { method: 'DELETE', headers: { ...ah(token) } },
  )
  return jsonOrThrow<FbsWarehouseBinding>(res)
}

export type FbsStockPoolProduct = {
  product_id: string
  sku_code: string
  name: string
  wb_chrt_id: number | null
  pool_limit: number
  allocated_this_binding: number
  allocated_elsewhere: number
  available_for_this_binding: number
}

export type FbsStockPoolSetResult = {
  product_id: string
  quantity: number
  pool_limit: number
  allocated_total: number
  available: number
}

export async function fetchFbsBindingStockPool(
  token: string,
  ah: (t: string) => Record<string, string>,
  sellerId: string,
  wbWarehouseId: number,
): Promise<FbsStockPoolProduct[]> {
  const res = await fetch(
    apiUrl(`${sellerBase(sellerId)}/warehouse-bindings/${wbWarehouseId}/stock-pool`),
    { headers: { ...ah(token) } },
  )
  return jsonOrThrow<FbsStockPoolProduct[]>(res)
}

export async function setFbsBindingStockPoolQuantity(
  token: string,
  ah: (t: string) => Record<string, string>,
  sellerId: string,
  wbWarehouseId: number,
  productId: string,
  quantity: number,
): Promise<FbsStockPoolSetResult> {
  const res = await fetch(
    apiUrl(
      `${sellerBase(sellerId)}/warehouse-bindings/${wbWarehouseId}/stock-pool/${productId}`,
    ),
    {
      method: 'PUT',
      headers: { ...ah(token), 'Content-Type': 'application/json' },
      body: JSON.stringify({ quantity }),
    },
  )
  return jsonOrThrow<FbsStockPoolSetResult>(res)
}

export async function triggerFbsStockSync(
  token: string,
  ah: (t: string) => Record<string, string>,
  sellerId: string,
  wbWarehouseId?: number | null,
): Promise<FbsStockSyncResult | FbsStockSyncJob> {
  const res = await fetch(apiUrl(`${sellerBase(sellerId)}/stocks/sync`), {
    method: 'POST',
    headers: { ...ah(token), 'Content-Type': 'application/json' },
    body: JSON.stringify(
      wbWarehouseId != null ? { wb_warehouse_id: wbWarehouseId } : {},
    ),
  })
  if (!res.ok) throw new Error(await readApiErrorMessage(res))
  return (await res.json()) as FbsStockSyncResult | FbsStockSyncJob
}

export async function fetchFbsStockSyncStatus(
  token: string,
  ah: (t: string) => Record<string, string>,
  sellerId: string,
  wbWarehouseId: number,
): Promise<FbsStockSyncStatus> {
  const qs = new URLSearchParams({ wb_warehouse_id: String(wbWarehouseId) })
  const res = await fetch(
    apiUrl(`${sellerBase(sellerId)}/stocks/sync-status?${qs.toString()}`),
    { headers: { ...ah(token) } },
  )
  return jsonOrThrow<FbsStockSyncStatus>(res)
}

// ── Ручная синхронизация заказов с WB ──────────────────────────────────────
// POST /operations/fbs-orders/sync ставит фоновую задачу и сразу отдаёт её id.
// Результат приезжает в background job, поэтому его надо дождаться опросом.

export type BackgroundJobRow = {
  id: string
  job_type: string
  status: string
  payload_json: Record<string, unknown> | null
  result_json: Record<string, unknown> | null
  error_message: string | null
  created_at: string
  started_at: string | null
  finished_at: string | null
}

export type FbsOrdersSyncOutcome = {
  ordersReceived: number
  ordersCreated: number
  ordersUpserted: number
  supplyLinkSkippedUnmappedWarehouse: number
  supplyLinkSkippedUnmappedWarehouseSupplyIds: string[]
  supplyLinkSkippedWarehouseMismatchOrders: number
}

export async function startFbsOrdersSync(
  token: string,
  ah: (t: string) => Record<string, string>,
  sellerId: string,
): Promise<{ id: string; status: string }> {
  const res = await fetch(apiUrl('/operations/fbs-orders/sync'), {
    method: 'POST',
    headers: { ...ah(token), 'Content-Type': 'application/json' },
    body: JSON.stringify({ seller_id: sellerId }),
  })
  return jsonOrThrow<{ id: string; status: string }>(res)
}

export async function fetchBackgroundJob(
  token: string,
  ah: (t: string) => Record<string, string>,
  jobId: string,
): Promise<BackgroundJobRow> {
  const res = await fetch(apiUrl(`/operations/background-jobs/${jobId}`), {
    headers: { ...ah(token) },
  })
  return jsonOrThrow<BackgroundJobRow>(res)
}

// Статусы задачи из background_job_service: pending → running → done | failed.
const JOB_TERMINAL_STATUSES = new Set(['done', 'failed'])
const JOB_FAILED_STATUSES = new Set(['failed'])

function readCount(result: Record<string, unknown> | null, key: string): number {
  const value = result?.[key]
  return typeof value === 'number' ? value : 0
}

function readStringArray(result: Record<string, unknown> | null, key: string): string[] {
  const value = result?.[key]
  if (!Array.isArray(value)) return []
  return value.every((item) => typeof item === 'string') ? value : []
}

/** Ждёт завершения фоновой задачи, опрашивая её раз в секунду. */
export async function waitForBackgroundJob(
  token: string,
  ah: (t: string) => Record<string, string>,
  jobId: string,
  options: { timeoutMs?: number; intervalMs?: number } = {},
): Promise<BackgroundJobRow> {
  const timeoutMs = options.timeoutMs ?? 120_000
  const intervalMs = options.intervalMs ?? 1000
  const deadline = Date.now() + timeoutMs
  for (;;) {
    const job = await fetchBackgroundJob(token, ah, jobId)
    if (JOB_TERMINAL_STATUSES.has(job.status)) {
      if (JOB_FAILED_STATUSES.has(job.status)) {
        throw new Error(job.error_message || 'Синхронизация с WB завершилась ошибкой.')
      }
      return job
    }
    if (Date.now() > deadline) {
      throw new Error('Синхронизация с WB не завершилась за 2 минуты. Проверьте фоновые задачи.')
    }
    await new Promise((resolve) => setTimeout(resolve, intervalMs))
  }
}

/** Полный цикл «дёрнуть синхронизацию и дождаться результата» для одного селлера. */
export async function runFbsOrdersSync(
  token: string,
  ah: (t: string) => Record<string, string>,
  sellerId: string,
): Promise<FbsOrdersSyncOutcome> {
  const started = await startFbsOrdersSync(token, ah, sellerId)
  const job = await waitForBackgroundJob(token, ah, started.id)
  return {
    ordersReceived: readCount(job.result_json, 'orders_received'),
    ordersCreated: readCount(job.result_json, 'orders_created'),
    ordersUpserted: readCount(job.result_json, 'orders_upserted'),
    supplyLinkSkippedUnmappedWarehouse: readCount(job.result_json, 'supply_link_skipped_unmapped_warehouse'),
    supplyLinkSkippedUnmappedWarehouseSupplyIds: readStringArray(job.result_json, 'supply_link_skipped_unmapped_warehouse_supply_ids'),
    supplyLinkSkippedWarehouseMismatchOrders: readCount(job.result_json, 'supply_link_skipped_warehouse_mismatch_orders'),
  }
}

export async function syncFbsOrderStatuses(
  token: string,
  ah: (t: string) => Record<string, string>,
  sellerId: string,
): Promise<number> {
  const res = await fetch(apiUrl('/operations/fbs-orders/sync-statuses'), {
    method: 'POST',
    headers: { ...ah(token), 'Content-Type': 'application/json' },
    body: JSON.stringify({ seller_id: sellerId }),
  })
  const payload = await jsonOrThrow<{ statuses_updated: number }>(res)
  return payload.statuses_updated
}
