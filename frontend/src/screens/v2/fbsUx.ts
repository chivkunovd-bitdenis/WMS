import { compactPrintWidth, printColgroup } from '../../utils/printTableColumns'
import { resolveProductBarcodeOptions } from '../../types/wbProductCatalog'
import type { FbsOrderMetadata, FbsPickOptionLocation, FbsWorkspace } from './fbsApi'

export type FbsMarketplace = 'wb' | 'ozon'

export function buildFbsSyncTargets(
  sellerIds: string[],
  selectedSellerId: string,
): Array<{ sellerId: string; marketplace: FbsMarketplace }> {
  const targets = selectedSellerId === '__all__' ? sellerIds : [selectedSellerId]
  return targets.flatMap((sellerId) => ([
    { sellerId, marketplace: 'wb' as const },
    { sellerId, marketplace: 'ozon' as const },
  ]))
}

export function mixedMarketplaceSelectionMessage(marketplaces: FbsMarketplace[]): string | null {
  return new Set(marketplaces).size > 1
    ? 'Нельзя объединить заказы Wildberries и Ozon в одну поставку.'
    : null
}

export function fbsBoxOperationsDisabled(_marketplace: FbsMarketplace): boolean {
  return false
}

export function fbsBoxEditingDisabled(
  marketplace: FbsMarketplace,
  deliveryConfirmed: boolean,
): boolean {
  return fbsBoxOperationsDisabled(marketplace) || deliveryConfirmed
}

export function fbsUnassignedPositionQuantity(
  positions: Array<{ id?: string | null; quantity: number }>,
  assignedPositionIds: Set<string>,
): number {
  return positions.reduce((sum, position) => sum + (position.id && assignedPositionIds.has(position.id) ? 0 : position.quantity), 0)
}

type OzonAutoBoxOrder = {
  id: string
  status: string
  external_order_id: string | null
  positions: Array<{ id?: string | null; quantity: number }>
}

type OzonAutoBox = {
  id: string
  box_number: number
  assigned_order_ids: string[]
  assigned_order_product_ids?: string[]
  qr_asset: { status: string; preview_url: string | null } | null
}

/** Готовая этикетка Ozon короба — то же условие, по которому кнопка короба открывает печать, а не сборку. */
export function fbsOzonBoxLabelReady(box: Pick<OzonAutoBox, 'qr_asset'>): boolean {
  return box.qr_asset?.status === 'ready' && Boolean(box.qr_asset.preview_url)
}

/**
 * WMS-526: что осталось сделать кнопке «Создать автоматически».
 * unassignedPositions — позиции неотменённых заказов, не лежащие ни в одном коробе.
 * labelTargets — неотменённые заказы, все позиции которых разложены, а готовой
 * этикетки нет: по одному коробу на заказ (сборка Ozon одним запросом берёт все короба заказа).
 */
export function fbsOzonAutoBoxesPlan(
  orders: OzonAutoBoxOrder[],
  boxes: OzonAutoBox[],
): { unassignedPositions: number; labelTargets: Array<{ orderId: string; externalOrderId: string | null; boxId: string }> } {
  const assignedPositionIds = new Set(boxes.flatMap((box) => box.assigned_order_product_ids ?? []))
  const sortedBoxes = [...boxes].sort((a, b) => a.box_number - b.box_number)
  let unassignedPositions = 0
  const labelTargets: Array<{ orderId: string; externalOrderId: string | null; boxId: string }> = []
  for (const order of orders) {
    if (order.status === 'cancelled') continue
    unassignedPositions += order.positions.filter((position) => position.id && !assignedPositionIds.has(position.id)).length
    if (order.positions.length === 0 || fbsUnassignedPositionQuantity(order.positions, assignedPositionIds) > 0) continue
    const orderBoxes = sortedBoxes.filter((box) => box.assigned_order_ids.includes(order.id))
    if (orderBoxes.length === 0 || orderBoxes.some(fbsOzonBoxLabelReady)) continue
    labelTargets.push({ orderId: order.id, externalOrderId: order.external_order_id, boxId: orderBoxes[0].id })
  }
  return { unassignedPositions, labelTargets }
}

/** Итог сбоев этикеток: причины с номерами Ozon, одинаковые причины — одной строкой. */
export function fbsOzonLabelFailuresText(failures: Array<{ externalOrderId: string | null; reason: string }>): string {
  const byReason = new Map<string, string[]>()
  for (const failure of failures) {
    const numbers = byReason.get(failure.reason) ?? []
    numbers.push(failure.externalOrderId ? `№${failure.externalOrderId}` : 'без номера')
    byReason.set(failure.reason, numbers)
  }
  const details = [...byReason.entries()].map(([reason, numbers]) => `Ozon ${numbers.join(', ')} — ${reason.replace(/[.\s]+$/, '')}`)
  return `Без этикетки заказов: ${failures.length}. ${details.join('; ')}.`
}

export function fbsOrdersAvailableForBox<T extends { id: string }>(
  orders: T[],
  assignedOrderIds: Set<string>,
): T[] {
  // Для WB упаковка — отметка, а не ворота. Backend уже разрешает положить в
  // короб неупакованный заказ, поэтому frontend не должен прятать его из списка.
  return orders.filter((order) => !assignedOrderIds.has(order.id))
}

/** WB has one unit per order. This is display-only; assignment keeps its existing logic. */
export function fbsBoxProductProgress(
  orders: Array<{ id: string; product: { id: string | null } }>,
  assignedOrderIds: Set<string>,
  draftQuantities: Record<string, string>,
): Map<string, { planned: number; remaining: number }> {
  const progress = new Map<string, { planned: number; remaining: number }>()
  for (const order of orders) {
    const key = order.product.id ?? order.id
    const current = progress.get(key) ?? { planned: 0, remaining: 0 }
    current.planned += 1
    if (!assignedOrderIds.has(order.id)) current.remaining += 1
    progress.set(key, current)
  }
  for (const [key, current] of progress) {
    // Match the existing order slice: only whole available units enter the box.
    const selected = Math.min(current.remaining, Math.max(0, Number(draftQuantities[key]) || 0))
    current.remaining -= Math.trunc(selected)
  }
  return progress
}

export function fbsDeliveryConfirmDisabled(
  marketplace: FbsMarketplace,
  loading: boolean,
  preflight: { can_deliver: boolean } | null,
): boolean {
  // Ошибка получения preflight оставляет `preflight=null`. В этом состоянии
  // оператор вправе повторить проверку или попробовать передачу: сам deliver
  // заново синхронизирует WB и вернёт честный ответ. Серой кнопка остаётся
  // только пока запрос выполняется или сервер вернул реальный blocker.
  if (loading) return true
  if (marketplace !== 'wb' && preflight === null) return true
  return Boolean(preflight && !preflight.can_deliver)
}

export function supplyQrExpectedForStatus(status: string): boolean {
  // WB issues the supply QR only after handoff. Cargo-place QR codes are
  // available earlier and must stay printable without counting the future
  // supply QR as a missing label.
  return status === 'in_delivery' || status === 'done'
}

export type FbsOperatorStageKey = 'composition' | 'picking' | 'packing' | 'boxes'

const FBS_OPERATOR_STAGES: FbsOperatorStageKey[] = ['composition', 'picking', 'packing', 'boxes']

export function fbsAccessibleStageIndex(_input: {
  marketplace: FbsMarketplace
  currentStage: FbsOperatorStageKey
}): number {
  // Все рабочие поверхности открыты одновременно, включая черновик, и одинаково
  // для WB и Ozon. «Начать работу» может создать удобное упаковочное задание, но
  // наличие этого задания не даёт права открыть короба или передать поставку —
  // право уже есть. Упаковка — только зафиксированный факт, а не право открыть
  // короба. Не добавляйте сюда progress.packed/pack.status.
  //
  // Ветку по маркетплейсу возвращать нельзя: у Ozon вкладки запирались по
  // серверному этапу, а сам этап упирался в стикеры, которых до передачи не
  // существует, — оператор не мог дойти ни до коробов, ни до передачи.
  return FBS_OPERATOR_STAGES.indexOf('boxes')
}

export function fbsStageAfterWorkspaceRefresh(
  _marketplace: FbsMarketplace,
  currentStage: FbsOperatorStageKey,
  serverStage: FbsOperatorStageKey,
): FbsOperatorStageKey {
  // Опрос и обычные мутации не должны выкидывать оператора назад из коробов или
  // упаковки только потому, что на сервере изменился какой-то необязательный
  // факт. Правило одно для WB и Ozon: серверный этап задаёт стартовую
  // поверхность, но не перехватывает навигацию у уже работающего человека.
  return currentStage !== 'composition' ? currentStage : serverStage
}

export function fbsDeliveryErrorKeepsIdempotencyKey(error: {
  code?: string
  retryable?: boolean
}): boolean {
  // Эти ответы означают, что исход WB ещё неизвестен либо WB просит повторить
  // ту же операцию. Для окончательного отказа следующая попытка обязана получить
  // новый ключ, иначе исправленный оператором запрос застрянет на старом failed.
  return error.retryable === true && new Set([
    'wb_timeout',
    'wb_pending_confirmation',
    'operation_in_progress',
  ]).has(error.code ?? '')
}

const FBS_ERROR_TEXT: Record<string, string> = {
  missing_marketplace_token: 'У селлера не подключён ключ Wildberries. Добавьте ключ WB в карточке селлера.',
  wb_transport_error: 'Не удалось связаться с Wildberries. Проверьте соединение и повторите запрос через минуту.',
  wb_timeout: 'Wildberries не ответил вовремя. Результат операции пока неизвестен — повторите проверку через минуту.',
  wb_pending_confirmation: 'Wildberries ещё не подтвердил результат операции. Повторите проверку через минуту.',
  wb_invalid_response: 'Wildberries вернул ответ, который не удалось прочитать. Повторите запрос через минуту.',
  wb_stickers_incomplete: 'Wildberries вернул не все стикеры. Повторите получение стикеров.',
  fbs_shipment_source_missing: 'Не указано, откуда списать товар при передаче. Проверьте источник товара в подборе.',
  fbs_shipment_product_missing: 'У заказа не определён товар. Проверьте сопоставление товара перед передачей.',
  stale_preflight: 'Данные поставки изменились. Обновите проверку перед передачей.',
  operation_in_progress: 'Операция ещё выполняется. Дождитесь результата и обновите данные.',
  ozon_not_connected: 'У селлера не подключён кабинет Ozon. Попросите администратора проверить подключение.',
  ozon_auth_failed: 'Ozon не принял данные подключения селлера. Попросите администратора проверить подключение.',
  ozon_account_blocked: 'Кабинет Ozon заблокирован. Обратитесь в поддержку Ozon.',
  ozon_rate_limited: 'Ozon ограничил частоту запросов. Повторите запрос через минуту.',
  ozon_unavailable: 'Ozon временно недоступен. Повторите запрос через минуту.',
  ozon_ship_unconfirmed: 'Ozon ещё не подтвердил передачу заказа. Повторите проверку результата.',
  sgtinemitted: 'Код только выпущен и ещё не введён в оборот. Попросите селлера проверить его в Честном знаке.',
  sgtinapplied: 'Код нанесён, но не введён в оборот. Попросите селлера ввести его в оборот в Честном знаке.',
  sgtinappliednotpaid: 'Код не оплачен в Честном знаке. Передайте вопрос селлеру.',
  sgtinnogs: 'Код без разделителей — отсканируйте Честный знак заново целиком.',
  sgtinnotfound: 'Честный знак не знает такого кода. Проверьте этикетку и обратитесь к селлеру.',
  sgtinretired: 'Код Честного знака выведен из оборота. Замените его на упаковке.',
  sgtinwrittenoff: 'Код уже выведен из оборота. Попросите селлера проверить маркировку товара.',
  sgtinwithdrawn: 'Код отозван в Честном знаке. Попросите селлера проверить маркировку товара.',
  sgtininvalidformat: 'Неверный формат кода маркировки. Отсканируйте код заново целиком.',
  sgtininvalidpattern: 'Код маркировки не соответствует ожидаемому формату. Отсканируйте код заново целиком.',
  sgtinhasinvalidsymbols: 'В коде маркировки недопустимые символы. Проверьте настройки сканера и повторите сканирование.',
  sgtinhasnonlatinsymbols: 'В коде маркировки нелатинские символы. Переключите сканер на английскую раскладку и повторите сканирование.',
}

/** Переводим только машинные коды; подробный текст сервера сохраняем целиком. */
export function fbsErrorText(message: string): string {
  const code = message.trim()
  const markingCode = code.toLowerCase().replaceAll(/[_-]/g, '')
  const known = FBS_ERROR_TEXT[code] ?? FBS_ERROR_TEXT[markingCode]
  if (known) return known
  const upstream = /^(wb|ozon)_upstream_error_(\d{3})$/.exec(code)
  if (upstream) {
    const provider = upstream[1] === 'wb' ? 'Wildberries' : 'Ozon'
    const status = Number(upstream[2])
    if (status === 401 || status === 403) {
      return `${provider} не принял данные подключения или права доступа селлера. Попросите администратора проверить подключение в карточке селлера.`
    }
    if (status === 429) return `${provider} ограничил частоту запросов. Повторите запрос через минуту.`
    if (status >= 500) return `${provider} временно недоступен. Повторите запрос через минуту.`
    return `${provider} отклонил запрос. Проверьте данные операции; если ошибка повторится, обратитесь к администратору.`
  }
  if (/^sgtin[a-z_-]+$/i.test(code)) {
    return 'Результат проверки маркировки требует уточнения. Попросите селлера проверить состояние кода в Честном знаке.'
  }
  if (/^[a-z][a-z0-9]*(?:_[a-z0-9]+)+$/i.test(code)) {
    return 'Не удалось выполнить действие. Обновите данные; если ошибка повторится, обратитесь к администратору.'
  }
  return message
}

export function fbsOrdersSyncErrorMessage(cause: unknown): string {
  if (cause instanceof Error) return fbsErrorText(cause.message)
  if (cause && typeof cause === 'object' && 'message' in cause && typeof cause.message === 'string') {
    return fbsErrorText(cause.message)
  }
  if (cause && typeof cause === 'object' && 'code' in cause && typeof cause.code === 'string') {
    return fbsErrorText(cause.code)
  }
  return 'Не удалось синхронизировать заказы. Обновите данные и повторите запрос.'
}

export function orderStatusForChip(order: {
  marketplace: FbsMarketplace
  status: string
  wb_status: string | null
}): string {
  return order.marketplace === 'ozon' && order.status === 'external_processing'
    ? order.wb_status || order.status
    : order.status
}

export function ordersWord(count: number) {
  const lastTwo = Math.abs(count) % 100
  if (lastTwo >= 11 && lastTwo <= 14) return 'заказов'
  const last = lastTwo % 10
  if (last === 1) return 'заказ'
  if (last >= 2 && last <= 4) return 'заказа'
  return 'заказов'
}

export function normalizeMetadataKind(kind: string | undefined) {
  const normalized = kind?.toLowerCase() ?? 'sgtin'
  return normalized === 'kiz' ? 'sgtin' : normalized
}

export function metadataKindLabel(kind: string) {
  const normalized = normalizeMetadataKind(kind)
  return ({ sgtin: 'КИЗ', uin: 'УИН', imei: 'IMEI', gtin: 'GTIN' } as Record<string, string>)[normalized]
    ?? 'Идентификатор'
}

export type FbsPickingListPrintRow = {
  name: string
  size: string | null
  color?: string | null
  article?: string | null
  imageUrl: string | null
  identifiers: string[]
  locations: string[]
  required: number
  picked: number
  /** Historical field name; Ozon rows store the posting identifier here. */
  wbOrders: Array<string | number>
  stickerCodes: Array<string | null>
  marking: string
}

export type FbsPickingListPrintInput = {
  supplyName: string
  wbSupplyId: string | null
  /** Older callers are WB; group Ozon sheets must not present their postings as WB orders. */
  marketplace?: 'wb' | 'ozon' | 'mixed'
  sellerName: string
  wmsWarehouseName: string
  routeLabel: string
  deadlineLabel: string
  printedAtLabel: string
  rows: FbsPickingListPrintRow[]
}

/**
 * WB отдаёт баркод позиции Ozon-отправления и её привязки к площадкам — то же
 * правило, что и для баркода целого заказа (см. productBarcodeOptionsForOrder
 * в FfFbsSupplyWorkspace.tsx): баркод WB никогда не подставляется вместо
 * отсутствующего баркода Ozon.
 */
export function productBarcodeOptionsForPosition(
  position: FbsWorkspace['orders'][number]['positions'][number],
  marketplace: 'wb' | 'ozon',
) {
  const options = resolveProductBarcodeOptions({
    wb_primary_barcode: position.barcode,
    marketplace_bindings: position.marketplace_bindings,
  })
  return marketplace === 'ozon'
    ? options.filter((option) => option.marketplace === 'ozon')
    : options
}

export type FbsPickingRow = FbsPickingListPrintRow & {
  key: string
  nearestDeadline: string
}

/**
 * WMS-580: лист подбора и лента «Печать всего»/«Печать выбранного» карточки
 * поставки должны идти в одной последовательности. Единственный источник
 * порядка — tape_order_index (тот же ключ picking_list_order_key, что и на
 * сервере, см. backend/app/services/fbs_picking_order_service.py). Здесь
 * строится и отсортированный по нему список заказов (его же карточка берёт
 * для «Печать всего»/«Печать выбранного»), и строки листа подбора — группировкой
 * ПО ЭТОМУ ЖЕ списку, поэтому оба потребителя физически не могут разойтись
 * в порядке. Раньше (443638a1 → 30237f3b → 5fb9a6fc, 23.08.2026) их считали
 * порознь, и порядок расходился трижды за один день.
 */
export function fbsBuildPickingRows(
  orders: FbsWorkspace['orders'],
  isOzonSupply: boolean,
): { sortedOrders: FbsWorkspace['orders']; rows: FbsPickingRow[] } {
  const sortedOrders = [...orders].sort((a, b) => a.tape_order_index - b.tape_order_index)
  const grouped = new Map<string, FbsPickingRow>()
  for (const order of sortedOrders) {
    const rows = isOzonSupply
      ? order.positions.map((position) => ({
        key: position.product_id ?? position.id ?? `unmapped-${order.id}`,
        name: position.name,
        article: position.seller_article?.trim() || position.sku?.trim() || null,
        size: position.size ?? null,
        color: position.color ?? null,
        imageUrl: position.image_url ?? null,
        identifiers: [
          position.seller_article,
          position.sku ? `SKU ${position.sku}` : null,
          productBarcodeOptionsForPosition(position, 'ozon')[0]?.barcode,
        ].filter((value): value is string => Boolean(value)),
        required: position.quantity,
        picked: position.picked_quantity,
      }))
      : [{
        key: order.product.id ?? `unmapped-${order.id}`,
        name: order.product.name,
        article: order.product.seller_article?.trim() || null,
        size: order.product.size,
        color: order.product.color ?? null,
        imageUrl: order.product.image_url,
        identifiers: [
          order.product.seller_article,
          order.product.wb_article ? `WB ${order.product.wb_article}` : null,
          order.product.barcode,
        ].filter((value): value is string => Boolean(value)),
        required: 1,
        picked: order.pick.status === 'picked' ? 1 : 0,
      }]
    for (const row of rows) {
      const current = grouped.get(row.key) ?? {
        ...row,
        locations: [],
        required: 0,
        picked: 0,
        wbOrders: [],
        stickerCodes: [],
        marking: order.metadata.required.length ? order.metadata.required.join(', ') : 'Не требуется',
        nearestDeadline: order.deadline_at,
      }
      current.required += row.required
      current.picked += row.picked
      if (!current.color) current.color = row.color
      current.wbOrders.push(isOzonSupply
        ? (order.external_order_id ?? order.wb_order_id)
        : order.wb_order_id)
      current.stickerCodes.push(order.sticker.code)
      const locations = order.inventory.locations
        .filter((location) => location.available_unpacked > 0)
        .map((location) => `${location.code}: ${location.available_unpacked}`)
      current.locations = [...new Set([...current.locations, ...locations])]
      if (new Date(order.deadline_at).getTime() < new Date(current.nearestDeadline).getTime()) current.nearestDeadline = order.deadline_at
      grouped.set(row.key, current)
    }
  }
  return { sortedOrders, rows: [...grouped.values()] }
}

// Так сервер подписывает служебную зону сортировки (UNASSIGNED_LABEL).
const SORTING_LOCATION_LABEL = 'Без ячеек'

/**
 * WMS-528: откуда брать товар по листу подбора. В сортировке называется только
 * тара, в настоящей ячейке — ячейка и тара на ней. Источники идут по убыванию
 * свободного количества и берутся, пока не покроют оставшееся к подбору.
 */
export function fbsPickSourceLabels(locations: FbsPickOptionLocation[], need: number): string[] {
  if (need <= 0) return []
  const candidates: Array<{ label: string; available: number }> = []
  for (const location of locations) {
    const isSorting = location.location_code === SORTING_LOCATION_LABEL
    const sources = location.sources.length
      ? location.sources
      : [{ available: location.available, is_loose: true, source_label: '', container_path: [] }]
    for (const source of sources) {
      if (source.available <= 0) continue
      const container = source.is_loose || !source.container_path.length
        ? null
        : source.container_path.map((item) => item.label).join(' › ')
      const label = isSorting
        ? container ?? 'Россыпью'
        : container ? `${location.location_code} · ${container}` : location.location_code
      candidates.push({ label, available: source.available })
    }
  }
  candidates.sort((a, b) => b.available - a.available)
  const picked: string[] = []
  let covered = 0
  for (const candidate of candidates) {
    if (covered >= need) break
    picked.push(`${candidate.label}: ${candidate.available}`)
    covered += candidate.available
  }
  return picked
}

function escapePrintHtml(value: string | number) {
  return String(value)
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;')
    .replaceAll("'", '&#039;')
}

function printableImageUrl(value: string | null) {
  if (!value || !/^(https?:|data:image\/)/i.test(value)) return ''
  return escapePrintHtml(value)
}

function renderStickerCode(value: string | null) {
  if (!value) return '—'
  const compact = value.replace(/\s+/g, '')
  if (compact.length <= 4) return `<strong>${escapePrintHtml(compact)}</strong>`
  const prefix = compact.slice(0, -4)
  const suffix = compact.slice(-4)
  return `${escapePrintHtml(prefix)} <strong>${escapePrintHtml(suffix)}</strong>`
}

export function buildFbsPickingListPrintHtml(input: FbsPickingListPrintInput) {
  const marketplace = input.marketplace ?? 'wb'
  const marketplaceLabel = marketplace === 'ozon' ? 'Ozon' : marketplace === 'mixed' ? 'маркетплейса' : 'WB'
  const supplyReference = input.wbSupplyId
    ? marketplace === 'ozon'
      ? ` · № Ozon ${escapePrintHtml(input.wbSupplyId)}`
      : marketplace === 'mixed'
        ? ` · № ${escapePrintHtml(input.wbSupplyId)}`
        : ` · № WB ${escapePrintHtml(input.wbSupplyId)}`
    : ''
  const articleFor = (row: FbsPickingListPrintRow) => row.article?.trim() || row.identifiers[0]?.trim() || '—'
  const columns = printColgroup(277, [
    { width: 28 * 25.4 / 96 },
    { width: 54 * 25.4 / 96 },
    { grow: 2 },
    { width: compactPrintWidth('Артикул', input.rows.map(articleFor), 25, 12) },
    { width: compactPrintWidth('Цвет', input.rows.map((row) => row.color), 22, 12) },
    { width: compactPrintWidth('Размер', input.rows.map((row) => row.size), 20, 20) },
    { grow: 1 },
    { width: compactPrintWidth(`Заказы ${marketplaceLabel}`, input.rows.flatMap((row) => row.wbOrders), 24, 12) },
    { width: 116 * 25.4 / 96 },
    { width: compactPrintWidth('Взять', input.rows.map((row) => row.required), 20, 12) },
    { width: compactPrintWidth('Подобрано', input.rows.map((row) => `${row.picked} / ${row.required}`), 27, 12) },
    { width: compactPrintWidth('Маркировка', input.rows.map((row) => row.marking), 24, 12) },
  ])
  let position = 1
  const rows = input.rows.map((row) => {
    const positionFrom = position
    const positionTo = positionFrom + row.required - 1
    position = positionTo + 1
    const positionLabel = positionFrom === positionTo ? `${positionFrom}` : `${positionFrom}–${positionTo}`
    const article = articleFor(row)
    const identifiers = row.identifiers.filter((identifier) => identifier.trim() !== article)
    const imageUrl = printableImageUrl(row.imageUrl)
    const nonEmptyStickerCodes = row.stickerCodes.filter((code): code is string => Boolean(code))
    const stickerCodes = nonEmptyStickerCodes.length
      ? nonEmptyStickerCodes.map(renderStickerCode).join('<br />')
      : '—'
    return `
      <tr>
        <td class="number">${positionLabel}</td>
        <td class="image">${imageUrl ? `<img src="${imageUrl}" alt="" />` : '<span>—</span>'}</td>
        <td>
          <strong>${escapePrintHtml(row.name)}</strong>
          <div class="muted">${identifiers.length ? identifiers.map(escapePrintHtml).join(' · ') : ''}</div>
        </td>
        <td>${escapePrintHtml(article)}</td>
        <td>${escapePrintHtml(row.color?.trim() || '—')}</td>
        <td class="size">${escapePrintHtml(row.size?.trim() || '—')}</td>
        <td>${row.locations.length ? row.locations.map(escapePrintHtml).join('<br />') : 'Нет свободного остатка'}</td>
        <td>${row.wbOrders.map((id) => `№${escapePrintHtml(id)}`).join('<br />')}</td>
        <td class="sticker">${stickerCodes}</td>
        <td class="quantity">${escapePrintHtml(row.required)}</td>
        <td class="quantity">${escapePrintHtml(row.picked)} / ${escapePrintHtml(row.required)}</td>
        <td>${escapePrintHtml(row.marking)}</td>
      </tr>`
  }).join('')

  return `<!doctype html>
<html lang="ru">
  <head>
    <meta charset="utf-8" />
    <title>Лист подбора — ${escapePrintHtml(input.supplyName)}</title>
    <style>
      @page { size: A4 landscape; margin: 10mm; }
      * { box-sizing: border-box; }
      body { margin: 0; color: #172033; font: 12px/1.35 Arial, sans-serif; }
      h1 { margin: 0 0 4px; font-size: 22px; }
      .subtitle { margin-bottom: 14px; color: #5c6475; }
      .meta { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 8px; margin-bottom: 14px; }
      .meta div { border: 1px solid #d9dce5; border-radius: 6px; padding: 7px 9px; }
      .meta span { display: block; color: #687083; font-size: 10px; }
      .meta strong { display: block; margin-top: 2px; }
      table { width: 100%; border-collapse: collapse; table-layout: fixed; }
      th, td { border: 1px solid #cfd3df; padding: 6px; text-align: left; vertical-align: middle; overflow-wrap: anywhere; }
      th { background: #f1eefb; font-size: 10px; text-transform: uppercase; }
      tr { break-inside: avoid; }
      .number { width: 28px; text-align: center; }
      .image { width: 54px; text-align: center; }
      .image img { display: block; width: 42px; height: 42px; margin: auto; object-fit: contain; }
      .size { text-align: center; }
      td.size { font-size: 20px; font-weight: 700; }
      .quantity { text-align: center; font-weight: 700; }
      .sticker { width: 116px; font-size: 12px; white-space: nowrap; font-variant-numeric: tabular-nums; }
      .muted { margin-top: 3px; color: #687083; font-size: 10px; }
      .footer { margin-top: 8px; color: #687083; font-size: 10px; }
    </style>
  </head>
  <body>
    <h1>Лист подбора FBS</h1>
    <div class="subtitle">${escapePrintHtml(input.supplyName)}${supplyReference}</div>
    <div class="meta">
      <div><span>Селлер</span><strong>${escapePrintHtml(input.sellerName)}</strong></div>
      <div><span>Склад WMS</span><strong>${escapePrintHtml(input.wmsWarehouseName)}</strong></div>
      <div><span>Маршрут</span><strong>${escapePrintHtml(input.routeLabel)}</strong></div>
      <div><span>Сдать до</span><strong>${escapePrintHtml(input.deadlineLabel)}</strong></div>
    </div>
    <table>
      ${columns}
      <thead><tr><th class="number">№</th><th class="image">Фото</th><th>Товар</th><th>Артикул</th><th>Цвет</th><th class="size">Размер</th><th>Ячейка / тара</th><th>Заказы ${marketplaceLabel}</th><th class="sticker">Стикер</th><th class="quantity">Взять</th><th class="quantity">Подобрано</th><th>Маркировка</th></tr></thead>
      <tbody>${rows || `<tr><td colspan="12">В поставке нет товаров для подбора.</td></tr>`}</tbody>
    </table>
    <div class="footer">Сформировано WMS: ${escapePrintHtml(input.printedAtLabel)} · Актуальное серверное состояние на момент печати.</div>
    <script>
      const images = Array.from(document.images);
      const ready = images.map((image) => image.complete ? Promise.resolve() : new Promise((resolve) => {
        image.addEventListener('load', resolve, { once: true });
        image.addEventListener('error', resolve, { once: true });
      }));
      Promise.all(ready).then(() => { window.focus(); window.print(); });
    </script>
  </body>
</html>`
}

export type FbsDeliveryCheckRow = {
  code: string
  message: string
  ok: boolean
  severity: 'blocker' | 'warning' | 'info'
  order_id: string | null
}

export type FbsDeliveryCheckGroup = {
  key: string
  title: string
  description: string | null
  orderIds: number[]
  orderDetails?: Record<number, string[]>
}

export type FbsDeliveryCheckSummary = {
  blockers: FbsDeliveryCheckGroup[]
  warnings: FbsDeliveryCheckGroup[]
}

function deliveryCheckPresentation(check: FbsDeliveryCheckRow) {
  if (check.code === 'marking_required') {
    return {
      key: 'marking_required',
      title: 'Не нанесён Честный знак',
      description: 'Передаче не мешает; нанести можно и после неё.',
    }
  }
  const titles: Record<string, string> = {
    marking_not_allowed: 'Маркировка требует проверки',
    wb_terminal_order_ignored: 'Заказы уже отменены или закрыты',
    wb_supply_composition_discrepancy: 'Состав поставки не совпадает с WB',
    negative_stock: 'Недостаточно остатка; после подтверждения он будет списан в минус.',
  }
  return {
    key: check.code,
    title: titles[check.code] ?? fbsErrorText(check.message),
    description: check.code === 'wb_terminal_order_ignored'
      ? 'Исключены из списания и не мешают передаче поставки.'
      : null,
  }
}

function deliveryCheckWbOrderId(check: FbsDeliveryCheckRow, orderIds: Map<string, number>) {
  const mapped = check.order_id ? orderIds.get(check.order_id) : undefined
  if (mapped !== undefined) return mapped
  // A composition discrepancy can reference an order absent from the local
  // workspace. The existing API carries that WB number in this exact prefix.
  if (check.code === 'wb_terminal_order_ignored' || check.code === 'wb_supply_composition_discrepancy') {
    const match = /^Заказ WB (\d+)(?=[:\s])/.exec(check.message)
    if (match) return Number(match[1])
  }
  return undefined
}

/**
 * Готовит текст предполётной проверки для оператора.
 *
 * Сервер отдаёт по одной строке на заказ. Здесь одинаковые причины
 * схлопываются в одну строку, а номера заказов WB остаются отдельным списком,
 * который интерфейс раскрывает по запросу оператора. Устаревшие проверки
 * коробов отбрасываются: наличие и распределение коробов передаче не мешает
 * и владельцу не нужно даже как предупреждение.
 *
 * Запреты и предупреждения разводятся по уровню, а не по полю `ok`: уход
 * остатка в минус и отменённый заказ WB приходят с `ok = false`, но передачу
 * не запрещают, и красить их как отказ — врать оператору.
 */
export function summarizeDeliveryChecks(
  checks: FbsDeliveryCheckRow[],
  wbOrderIdByOrderId: Map<string, number>,
): FbsDeliveryCheckSummary {
  const collect = (severity: 'blocker' | 'warning') => {
    const groups = new Map<string, FbsDeliveryCheckGroup>()
    for (const check of checks) {
      if (check.severity !== severity) continue
      if (check.code === 'physical_boxes_required' || check.code === 'packed_order_unassigned') {
        continue
      }
      const presentation = deliveryCheckPresentation(check)
      const group: FbsDeliveryCheckGroup = groups.get(presentation.key) ?? {
        key: presentation.key,
        title: presentation.title,
        description: presentation.description,
        orderIds: [],
      }
      const wbOrderId = deliveryCheckWbOrderId(check, wbOrderIdByOrderId)
      if (wbOrderId !== undefined && !group.orderIds.includes(wbOrderId)) {
        group.orderIds.push(wbOrderId)
      }
      if (wbOrderId !== undefined && ['marking_not_allowed', 'negative_stock', 'wb_supply_composition_discrepancy'].includes(check.code)) {
        // The type is shared, but provider reasons and shortage quantities are
        // specific to each order. Keep every distinct detail inside its row.
        const message = check.code === 'wb_supply_composition_discrepancy'
          ? check.message.replace(/^Заказ WB \d+[:\s]+/, '')
          : check.message
        const detail = fbsErrorText(message.trim())
        group.orderDetails ??= {}
        const details = group.orderDetails[wbOrderId] ??= []
        if (detail && !details.includes(detail)) details.push(detail)
      }
      groups.set(presentation.key, group)
    }
    return [...groups.values()]
      .map((group) => ({
        ...group,
        orderIds: [...group.orderIds].sort((a, b) => a - b),
      }))
  }
  return { blockers: collect('blocker'), warnings: collect('warning') }
}

/**
 * WMS-612: подпись заказа в раскрытых строках окна передачи. Проверки группируют
 * заказы по wb_order_id, но у Ozon это служебный (отрицательный) номер, который
 * оператору ничего не говорит: показываем номер отправления Ozon, а если его нет —
 * просто «Отправление Ozon». Сравниваем строками: номер может прийти и числом, и строкой.
 */
export function fbsDeliveryCheckOrderLabel(
  marketplace: 'wb' | 'ozon',
  orders: Array<{ wb_order_id: number | string; external_order_id: string | null }>,
): (orderId: number) => string {
  if (marketplace !== 'ozon') return (orderId) => `Заказ WB №${orderId}`
  const postingByWbOrderId = new Map(orders.map((order) => [String(order.wb_order_id), order.external_order_id?.trim() ?? '']))
  return (orderId) => {
    const posting = postingByWbOrderId.get(String(orderId))
    return posting ? `Отправление Ozon №${posting}` : 'Отправление Ozon'
  }
}

/** Only the confirmed remote status is an acceptance; no UI navigation gates. */
export function fbsOrderMarkingAccepted(metadata: FbsOrderMetadata): boolean {
  const kinds = [...new Set([...metadata.required, ...metadata.states.filter((state) => state.value_tail).map((state) => state.kind)])]
  return kinds.every((kind) => metadata.states.some((state) =>
    state.kind === kind && state.status === 'accepted' && !state.reason?.trim(),
  ))
}

/**
 * WMS-477: итог «Проверено в WB: подтверждено X из Y» после кнопки «Проверить в WB».
 * Y — заказы, у которых внесён Честный знак, X — те из них, чьи коды WB подтвердил
 * (accepted или allowed_without_check). Считается по ответу сервера, отдельного
 * счётчика не нужно.
 *
 * Наличие кода — по хвосту значения (value_tail), как у соседнего «Очистить ЧЗ»,
 * а не по статусу: сервер ставит `missing` и сохранённой записи, когда WB отвечает
 * «required» с пустым значением, и такой заказ он по кнопке всё равно сверяет.
 * У заказа без записи value_tail пустой.
 */
export function fbsMarkingVerdictsSummary(
  orders: ReadonlyArray<{ metadata: FbsOrderMetadata }>,
): { confirmed: number; withCode: number } {
  let withCode = 0
  let confirmed = 0
  for (const order of orders) {
    const codes = order.metadata.states.filter((state) => state.kind === 'sgtin' && Boolean(state.value_tail))
    if (codes.length === 0) continue
    withCode += 1
    if (codes.every((state) => state.status === 'accepted' || state.status === 'allowed_without_check')) {
      confirmed += 1
    }
  }
  return { confirmed, withCode }
}

export function fbsMarkingPresentation(
  state: FbsOrderMetadata['states'][number] | undefined,
  provider = 'WB',
): { tone: 'success' | 'error' | 'neutral'; label: string | null; reason: string | null } {
  if (!state) return { tone: 'neutral', label: null, reason: null }
  const reason = state.reason?.trim()
  if (state.status === 'rejected' || state.status === 'replacement_required'
    || (state.status === 'accepted' && reason)) {
    const decisionReason = /^sgtin/i.test(state.decision ?? '') ? state.decision : null
    return {
      tone: 'error',
      label: state.status === 'replacement_required' ? 'ЧЗ требует замены' : `${provider} не принял ЧЗ`,
      reason: reason ? fbsErrorText(reason) : decisionReason ? fbsErrorText(decisionReason) : null,
    }
  }
  if (state.status === 'accepted') return { tone: 'success', label: `ЧЗ принят ${provider}`, reason: null }
  if (state.status === 'allowed_without_check') {
    return { tone: 'neutral', label: `${provider}: проверка ЧЗ не требуется`, reason: null }
  }
  if (state.status === 'missing') return { tone: 'neutral', label: 'ЧЗ не внесён', reason: null }
  return { tone: 'neutral', label: `${provider} ещё не подтвердил ЧЗ`, reason: null }
}

/**
 * WMS-636: заказ WB с непринятым КИЗ — ровно та строка, чья подпись ЧЗ сейчас
 * красная (то же состояние и то же правило, что рисует строку упаковки WB).
 */
export function fbsOrderKizRejectedByWb(order: { metadata: FbsOrderMetadata }): boolean {
  return fbsMarkingPresentation(order.metadata.states.find((state) => state.kind === 'sgtin')).tone === 'error'
}

// Same scanner normalization as fbs_kiz_service.sticker_scan_candidates.
const stickerKeyboardMap: Record<string, string> = Object.fromEntries(
  [
    ["ёйцукенгшщзхъфывапролджэячсмитьбю.", "`qwertyuiop[]asdfghjkl;'zxcvbnm,./"],
    ["ЁЙЦУКЕНГШЩЗХЪФЫВАПРОЛДЖЭЯЧСМИТЬБЮ,", "~QWERTYUIOP{}ASDFGHJKL:\"ZXCVBNM<>?"],
    ["\"№;:?/", "@#$^&|"],
  ].flatMap(([russian, qwerty]) => [...russian].map((char, index) => [char, qwerty[index]])),
)

function stickerScanCandidates(raw: string): string[] {
  const value = raw.replace(/[\s\u0085\u001c-\u001f]/g, '')
  if (!value) return []
  if (![...value].some((char) => stickerKeyboardMap[char] && /[\u0400-\u04ff№]/.test(char))) return [value]
  return [value, [...value].map((char) => stickerKeyboardMap[char] ?? char).join('')]
}

export function fbsSameStickerScan(raw: string, selected: string): boolean {
  const selectedCandidates = new Set(stickerScanCandidates(selected))
  return stickerScanCandidates(raw).some((candidate) => selectedCandidates.has(candidate))
}
