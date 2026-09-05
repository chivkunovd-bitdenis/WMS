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

export function fbsOrdersAvailableForBox<T extends { id: string }>(
  orders: T[],
  assignedOrderIds: Set<string>,
): T[] {
  // Для WB упаковка — отметка, а не ворота. Backend уже разрешает положить в
  // короб неупакованный заказ, поэтому frontend не должен прятать его из списка.
  return orders.filter((order) => !assignedOrderIds.has(order.id))
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

export function fbsOrdersSyncErrorMessage(cause: unknown): string {
  if (cause instanceof Error && cause.message === 'missing_marketplace_token') {
    return 'У селлера не подключён ключ Wildberries. Добавьте ключ WB в карточке селлера.'
  }
  if (
    cause
    && typeof cause === 'object'
    && 'code' in cause
    && cause.code === 'missing_marketplace_token'
  ) {
    return 'У селлера не подключён ключ Wildberries. Добавьте ключ WB в карточке селлера.'
  }
  return cause instanceof Error ? cause.message : 'ошибка синхронизации'
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
  imageUrl: string | null
  identifiers: string[]
  locations: string[]
  required: number
  picked: number
  wbOrders: number[]
  stickerCodes: Array<string | null>
  marking: string
}

export type FbsPickingListPrintInput = {
  supplyName: string
  wbSupplyId: string
  sellerName: string
  wmsWarehouseName: string
  routeLabel: string
  deadlineLabel: string
  printedAtLabel: string
  addressStorageEnabled?: boolean
  rows: FbsPickingListPrintRow[]
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
  let position = 1
  const rows = input.rows.map((row) => {
    const positionFrom = position
    const positionTo = positionFrom + row.required - 1
    position = positionTo + 1
    const positionLabel = positionFrom === positionTo ? `${positionFrom}` : `${positionFrom}–${positionTo}`
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
          <div class="muted">${row.identifiers.length ? row.identifiers.map(escapePrintHtml).join(' · ') : 'Идентификаторы не указаны'}</div>
        </td>
        <td class="size">${row.size ? escapePrintHtml(row.size) : '—'}</td>
        ${input.addressStorageEnabled === false ? '' : `<td>${row.locations.length ? row.locations.map(escapePrintHtml).join('<br />') : 'Ячейка не назначена'}</td>`}
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
      .size { width: 78px; text-align: center; white-space: nowrap; }
      td.size { font-size: 20px; font-weight: 700; }
      .quantity { width: 62px; text-align: center; font-weight: 700; }
      .sticker { width: 116px; font-size: 12px; white-space: nowrap; font-variant-numeric: tabular-nums; }
      .muted { margin-top: 3px; color: #687083; font-size: 10px; }
      .footer { margin-top: 8px; color: #687083; font-size: 10px; }
    </style>
  </head>
  <body>
    <h1>Лист подбора FBS</h1>
    <div class="subtitle">${escapePrintHtml(input.supplyName)} · № WB ${escapePrintHtml(input.wbSupplyId)}</div>
    <div class="meta">
      <div><span>Селлер</span><strong>${escapePrintHtml(input.sellerName)}</strong></div>
      <div><span>Склад WMS</span><strong>${escapePrintHtml(input.wmsWarehouseName)}</strong></div>
      <div><span>Маршрут</span><strong>${escapePrintHtml(input.routeLabel)}</strong></div>
      <div><span>Сдать до</span><strong>${escapePrintHtml(input.deadlineLabel)}</strong></div>
    </div>
    <table>
      <thead><tr><th class="number">№</th><th class="image">Фото</th><th>Товар и идентификаторы</th><th class="size">Размер</th>${input.addressStorageEnabled === false ? '' : '<th>Ячейка</th>'}<th>Заказы WB</th><th class="sticker">Стикер</th><th class="quantity">Взять</th><th class="quantity">Подобрано</th><th>Маркировка</th></tr></thead>
      <tbody>${rows || `<tr><td colspan="${input.addressStorageEnabled === false ? 9 : 10}">В поставке нет товаров для подбора.</td></tr>`}</tbody>
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

export type FbsDeliveryCheckSummary = {
  blockers: string[]
  warnings: string[]
}

/**
 * Готовит текст предполётной проверки для оператора.
 *
 * Сервер отдаёт по одной строке на заказ, поэтому «Честный знак не нанесён»
 * приходило три раза подряд без единого номера заказа — понять, какие именно
 * заказы виноваты, было нельзя. Здесь одинаковые причины схлопываются в одну
 * строку, а номера заказов WB собираются в её конце.
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
    const byMessage = new Map<string, number[]>()
    for (const check of checks) {
      if (check.severity !== severity) continue
      const orders = byMessage.get(check.message) ?? []
      const wbOrderId = check.order_id ? wbOrderIdByOrderId.get(check.order_id) : undefined
      if (wbOrderId !== undefined && !orders.includes(wbOrderId)) orders.push(wbOrderId)
      byMessage.set(check.message, orders)
    }
    return [...byMessage.entries()].map(([message, orders]) => {
      if (orders.length === 0) return message
      const sorted = [...orders].sort((a, b) => a - b)
      const label = sorted.length === 1 ? 'заказ' : 'заказы'
      return `${message} (${label} ${sorted.join(', ')})`
    })
  }
  return { blockers: collect('blocker'), warnings: collect('warning') }
}
