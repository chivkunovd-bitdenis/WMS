// WMS-616: read-only список FBS-заказов селлера. Отдельный модуль от fbsApi.ts
// (там — рабочее место фулфилмента с заявками/подборами), чтобы не тащить
// складские контракты в seller-кабинет и не плодить лишние выборки селлеру.
//
// Контракт сервера, который backend-агент добавляет параллельно:
//   GET /seller-fbs/orders?limit=&offset=&marketplace=&status=
//   → { items: SellerFbsOrderRow[]; total: number; server_now: string }
// Фильтры marketplace/status применяются до пагинации (R6/R10). seller/tenant
// scope — из токена, server-side (R2); на фронте scope не кладём.

import { apiUrl } from '../../api'
import { readApiErrorMessage } from '../../utils/readApiErrorMessage'

export type SellerFbsMarketplace = 'wb' | 'ozon'

// Группы статусов из D3 WMS-616. Backend сам вычисляет группу — frontend не
// добавляет второй источник правды (R5).
export type SellerFbsStatusGroup =
  | 'new'
  | 'in_work'
  | 'handed'
  | 'accepted'
  | 'external_processing'
  | 'done'
  | 'cancelled'
  | 'defect'

export type SellerFbsOrderRow = {
  id: string
  marketplace: SellerFbsMarketplace
  external_order_id: string | null
  status_group: SellerFbsStatusGroup
  // null — состав повреждён или неизвестен. По R4 это рисуется «—», а не
  // выдуманной единицей.
  items_quantity: number | null
  // created_at_wb — время у площадки. ISO 8601 UTC.
  received_at: string
}

export type SellerFbsOrdersPage = {
  items: SellerFbsOrderRow[]
  total: number
  // Сервер-ный now для расчёта «Возраст» (R7). Без якоря часы селлера
  // отвечали бы за цифру, что ломается на любом clock skew.
  server_now: string
}

export type SellerFbsMarketplaceFilter = 'all' | SellerFbsMarketplace
export type SellerFbsStatusFilter = 'all' | SellerFbsStatusGroup

export type LoadSellerFbsOrdersOutcome =
  | { outcome: 'loaded'; page: SellerFbsOrdersPage }
  | { outcome: 'failed'; message: string }
  | { outcome: 'stale' }

export function buildSellerFbsOrdersParams(input: {
  limit: number
  offset: number
  marketplace: SellerFbsMarketplaceFilter
  status: SellerFbsStatusFilter
}): URLSearchParams {
  const params = new URLSearchParams({
    limit: String(input.limit),
    offset: String(input.offset),
  })
  if (input.marketplace !== 'all') params.set('marketplace', input.marketplace)
  if (input.status !== 'all') params.set('status', input.status)
  return params
}

/**
 * Один запрос списка. Защита от запоздалого ответа после смены сессии (R8,
 * WMS-488) — через `isCurrentSession()`, как в seller catalog. Абортировать
 * нельзя через signal.aborted в catch: fetch сам кидает AbortError, который
 * выше превратится в 'stale'.
 */
export async function loadSellerFbsOrdersPage(
  fetchImpl: typeof fetch,
  headers: Record<string, string>,
  params: URLSearchParams,
  isCurrentSession: () => boolean,
  signal?: AbortSignal,
): Promise<LoadSellerFbsOrdersOutcome> {
  try {
    const res = await fetchImpl(apiUrl(`/seller-fbs/orders?${params.toString()}`), { headers, signal })
    if (!isCurrentSession()) return { outcome: 'stale' }
    if (!res.ok) {
      const message = await readApiErrorMessage(res)
      return isCurrentSession() ? { outcome: 'failed', message } : { outcome: 'stale' }
    }
    const page = (await res.json()) as SellerFbsOrdersPage
    return isCurrentSession() ? { outcome: 'loaded', page } : { outcome: 'stale' }
  } catch (e) {
    if ((e as { name?: string }).name === 'AbortError') return { outcome: 'stale' }
    if (!isCurrentSession()) return { outcome: 'stale' }
    return {
      outcome: 'failed',
      message: e instanceof Error ? e.message : 'Не удалось загрузить FBS-заказы.',
    }
  }
}

// Подписи групп по D3. Карта — чтобы «обрабатывается площадкой» и «передан»
// шли точно теми же словами, что в требованиях. Неизвестный код статуса не
// превращается в основную подпись — R5: «неизвестный код не показывается
// как необъяснённая основная подпись», так что падение на дефолт даёт
// «Обрабатывается площадкой» (нейтральный этап).
const STATUS_GROUP_LABEL: Record<SellerFbsStatusGroup, string> = {
  new: 'Новый',
  in_work: 'В работе',
  handed: 'Передан площадке',
  accepted: 'Принят площадкой',
  external_processing: 'Обрабатывается площадкой',
  done: 'Завершён',
  cancelled: 'Отменён',
  defect: 'Дефект',
}

export function sellerFbsStatusLabel(group: SellerFbsStatusGroup): string {
  return STATUS_GROUP_LABEL[group] ?? STATUS_GROUP_LABEL.external_processing
}

export const SELLER_FBS_STATUS_FILTER_OPTIONS: ReadonlyArray<{
  value: SellerFbsStatusFilter
  label: string
}> = [
  { value: 'all', label: 'Все статусы' },
  { value: 'new', label: STATUS_GROUP_LABEL.new },
  { value: 'in_work', label: STATUS_GROUP_LABEL.in_work },
  { value: 'handed', label: STATUS_GROUP_LABEL.handed },
  { value: 'accepted', label: STATUS_GROUP_LABEL.accepted },
  { value: 'external_processing', label: STATUS_GROUP_LABEL.external_processing },
  { value: 'done', label: STATUS_GROUP_LABEL.done },
  { value: 'cancelled', label: STATUS_GROUP_LABEL.cancelled },
  { value: 'defect', label: STATUS_GROUP_LABEL.defect },
]

export function sellerFbsMarketplaceLabel(marketplace: SellerFbsMarketplace): string {
  return marketplace === 'ozon' ? 'Ozon' : 'Wildberries'
}

/**
 * Короткое название маркетплейса для столбца «Внешний номер» вида «WB №123».
 * Полный «Wildberries» занимает слишком много места в узкой колонке и уже
 * продублирован слева иконкой/подписью площадки.
 */
export function sellerFbsMarketplaceShort(marketplace: SellerFbsMarketplace): string {
  return marketplace === 'ozon' ? 'Ozon' : 'WB'
}

/**
 * «Товаров» для одной строки (R4/D5). WB — всегда 1 шт.; Ozon — сумма
 * количеств позиций (`items_quantity` уже посчитан сервером). Нулевой или
 * null на Ozon → «—», не 1 (R4: нулевой/повреждённый состав не превращаем
 * в выдуманную единицу).
 */
export function sellerFbsItemsLabel(row: SellerFbsOrderRow): string {
  if (row.marketplace === 'wb') return '1 шт.'
  if (row.items_quantity == null || row.items_quantity <= 0) return '—'
  return `${row.items_quantity} шт.`
}

/**
 * «Возраст» в полных часах от received_at до server_now. R7:
 *   меньше часа → «< 1 ч»; будущая/битая дата → «—»; отрицательных нет.
 * server_now и received_at — ISO строки. Расчёт берёт серверные значения,
 * чтобы часы селлера не меняли цифру.
 */
export function sellerFbsAgeLabel(input: {
  receivedAtIso: string
  serverNowIso: string
}): string {
  const received = Date.parse(input.receivedAtIso)
  const now = Date.parse(input.serverNowIso)
  if (!Number.isFinite(received) || !Number.isFinite(now)) return '—'
  const diffMs = now - received
  if (diffMs < 0) return '—'
  if (diffMs < 3_600_000) return '< 1 ч'
  const hours = Math.floor(diffMs / 3_600_000)
  return `${hours} ч`
}

/** Формат «Поступил»: локальная дата+время в русском формате ru-RU. */
export function sellerFbsReceivedAtLabel(receivedAtIso: string): string {
  const ms = Date.parse(receivedAtIso)
  if (!Number.isFinite(ms)) return '—'
  return new Date(ms).toLocaleString('ru-RU', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  })
}
