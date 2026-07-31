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
  created_at_wb: string
  deadline_at: string
  mapping_status: string // mapped | missing
  reserve_status: string
  created_at: string
  updated_at: string
}

export type FbsOrdersTab = 'new' | 'assembly' | 'delivery' | 'done'

// Группировка статусов заказа по вкладкам (зеркалит WB).
export const TAB_STATUSES: Record<FbsOrdersTab, string[]> = {
  new: ['new'],
  assembly: ['in_supply', 'assembling', 'packed'],
  delivery: ['in_delivery', 'sorted'],
  done: ['done', 'cancelled', 'defect'],
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
  if (!res.ok) throw new Error(await readApiErrorMessage(res))
  return (await res.json()) as T
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

export async function deliverFbsSupply(
  token: string,
  ah: (t: string) => Record<string, string>,
  id: string,
): Promise<FbsSupply> {
  const res = await fetch(apiUrl(`/operations/fbs-supplies/${id}/deliver`), {
    method: 'POST',
    headers: { ...ah(token) },
  })
  return jsonOrThrow<FbsSupply>(res)
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

// ── Грузоместа (trbx) для ПВЗ-отгрузок ───────────────────────────────────────
// Реальные ручки backend/app/api/fbs_supplies.py:
//   POST /operations/fbs-supplies/{id}/trbx          → создать N грузомест (FbsTrbxCreateBody → FbsTrbxListOut)
//   POST /operations/fbs-supplies/{id}/trbx/stickers  → получить QR всех грузомест поставки (FbsTrbxStickersOut)
// Отдельной ручки "список грузомест" на backend нет: /trbx/stickers всегда возвращает
// ПОЛНЫЙ список грузомест поставки (и попутно докачивает недостающие стикеры у WB),
// поэтому используем её и как список при открытии карточки.

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

export type FbsMarkingKind = 'sgtin' | 'uin' | 'imei' | 'gtin'

export const MARKING_KIND_LABEL: Record<FbsMarkingKind, string> = {
  sgtin: 'КИЗ (SGTIN)',
  uin: 'УИН',
  imei: 'IMEI',
  gtin: 'GTIN',
}

export type FbsOrderMarking = {
  id: string
  order_id: string
  kind: string
  value: string
  check_status: string // new | checking | ok | error | no_check
  marking_code_id: string | null
}

export async function getFbsOrderMarkings(
  token: string,
  ah: (t: string) => Record<string, string>,
  orderId: string,
): Promise<FbsOrderMarking[]> {
  const res = await fetch(apiUrl(`/operations/fbs-orders/${orderId}/markings`), {
    headers: { ...ah(token) },
  })
  return jsonOrThrow<FbsOrderMarking[]>(res)
}

export async function putFbsOrderMarking(
  token: string,
  ah: (t: string) => Record<string, string>,
  orderId: string,
  kind: FbsMarkingKind,
  value: string,
): Promise<FbsOrderMarking> {
  const res = await fetch(apiUrl(`/operations/fbs-orders/${orderId}/markings/${kind}`), {
    method: 'PUT',
    headers: { ...ah(token), 'Content-Type': 'application/json' },
    body: JSON.stringify({ value }),
  })
  return jsonOrThrow<FbsOrderMarking>(res)
}
