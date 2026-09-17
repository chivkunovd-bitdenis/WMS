import type { FbsOrderMetadata, FbsPackingBoxPosition } from './fbsApi'

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

/**
 * Сколько штук каждой позиции Ozon уже лежит в коробах поставки (WMS-453):
 * позиция может быть разбита по нескольким коробам, поэтому количества
 * строк состава складываются по order_product_id.
 */
export function fbsAssignedPositionQuantities(
  boxes: Array<{ assigned_positions?: Array<{ order_product_id: string; quantity: number }> | null }>,
): Map<string, number> {
  const totals = new Map<string, number>()
  for (const box of boxes) {
    for (const entry of box.assigned_positions ?? []) {
      totals.set(entry.order_product_id, (totals.get(entry.order_product_id) ?? 0) + entry.quantity)
    }
  }
  return totals
}

/** Остаток позиции к раскладке: количество в заказе минус уже положенное в короба. */
export function fbsPositionRemainingQuantity(
  position: { id?: string | null; quantity: number },
  assignedQuantities: ReadonlyMap<string, number>,
): number {
  const assigned = position.id ? assignedQuantities.get(position.id) ?? 0 : 0
  return Math.max(0, position.quantity - assigned)
}

export function fbsUnassignedPositionQuantity(
  positions: Array<{ id?: string | null; quantity: number }>,
  assignedQuantities: ReadonlyMap<string, number>,
): number {
  return positions.reduce((sum, position) => sum + fbsPositionRemainingQuantity(position, assignedQuantities), 0)
}

/**
 * Ввод количества в строке Ozon-модалки «Добавить товары в короб»: целое
 * от 1 до остатка позиции, выход за границы приводится к ближайшей — как
 * в WB-варианте той же модалки. Пустое поле остаётся пустым, пока оператор
 * не ввёл число.
 */
export function fbsBoxPositionQuantityInput(raw: string, max: number): string {
  if (raw.trim() === '') return ''
  const parsed = Math.floor(Number(raw))
  if (!Number.isFinite(parsed)) return ''
  return String(Math.min(Math.max(1, max), Math.max(1, parsed)))
}

/**
 * Отправка «Добавить» в Ozon-короб (WMS-453, R6): ключ идемпотентности живёт
 * вместе с телом, которое под ним ушло. Пока исход отправки неизвестен (обрыв,
 * таймаут), повтор уходит ровно с этим телом и ключом; изменённый ввод под
 * старый ключ не попадает.
 */
export type FbsBoxShipment = {
  key: string
  boxId: string
  positions: FbsPackingBoxPosition[]
}

/** Один и тот же состав отправки: те же позиции с теми же количествами, порядок не важен. */
export function fbsSameBoxPositions(a: FbsPackingBoxPosition[], b: FbsPackingBoxPosition[]): boolean {
  const normalize = (list: FbsPackingBoxPosition[]) => [...list]
    .sort((x, y) => x.order_product_id.localeCompare(y.order_product_id))
    .map((entry) => `${entry.order_product_id}:${entry.quantity}`)
    .join('|')
  return a.length === b.length && normalize(a) === normalize(b)
}

export type FbsBoxShipmentResult<W> =
  /** Отправка применена ровно один раз (ответ сервера на неё) — модалку можно закрыть. */
  | { ok: true; workspace: W; pending: null }
  /** Ошибка: показать; pending — что повторять с тем же телом и ключом (или ничего). */
  | { ok: false; error: unknown; pending: FbsBoxShipment | null }
  /**
   * Ввод изменился, а прежняя незавершённая отправка только что подтверждена
   * повтором с тем же ключом: изменённый ввод не отправлен, старая отправка
   * закрыта. Показать свежее состояние (остатки), сохранить ввод оператора,
   * модалку не закрывать; следующее «Добавить» — новое действие.
   */
  | { ok: 'resolved'; workspace: W; pending: null }

/**
 * Жизненный цикл одной отправки «Добавить» в Ozon-короб (WMS-453, R6/R9).
 *
 * Единственное надёжное подтверждение применения — успешный ответ сервера на
 * отправку с тем же телом и тем же ключом: сервер либо применит её ровно один
 * раз, либо узнает ключ и вернёт текущее состояние без изменений. Прирост
 * количества в коробе доказательством не считается — его мог дать другой
 * оператор (ревью F3).
 *
 * - Нет незавершённой отправки — новый ключ; тело и ключ запоминаются до ответа.
 * - Ввод оператора (typedPositions — отмеченные строки с введёнными
 *   количествами, без фильтра по остатку: фоновое обновление могло убрать
 *   полностью разложенную позицию из списка, а ввод при этом не менялся)
 *   совпадает с незавершённой отправкой — повтор с тем же телом и ключом.
 * - Ввод изменился, а исход прежней отправки неизвестен — сначала повторяем
 *   прежнюю отправку тем же телом и ключом; её успешный ответ — 'resolved'
 *   (изменённый ввод не отправлен; ответ уже содержит свежее рабочее
 *   пространство). Обрыв на этом повторе — ошибка, отправка сохранена.
 *   Окончательный отказ на повторе — прежняя отправка не применена и снята,
 *   изменённый ввод уходит как новое действие с новым ключом.
 * - Окончательный отказ сервера (структурный 4xx без просьбы повторить) —
 *   отправка снята: сервер занимает ключ только на пути записи, ничего не
 *   сохранено. Обрыв или неизвестный исход — отправка остаётся для повтора.
 */
export async function sendFbsBoxShipment<W>(input: {
  pending: FbsBoxShipment | null
  boxId: string
  /** Тело новой отправки: отмеченные строки с остатком и введённым количеством. */
  positions: FbsPackingBoxPosition[]
  /** Ввод оператора как есть (без фильтра по остатку) — для сравнения с незавершённой отправкой. */
  typedPositions?: FbsPackingBoxPosition[]
  send: (shipment: FbsBoxShipment) => Promise<W>
  createKey: () => string
  isDefinitiveRefusal: (error: unknown) => boolean
}): Promise<FbsBoxShipmentResult<W>> {
  const { pending, boxId, positions } = input
  const typed = input.typedPositions ?? positions
  if (pending && pending.boxId === boxId && fbsSameBoxPositions(pending.positions, typed)) {
    return sendOnce(pending)
  }
  if (pending) {
    try {
      return { ok: 'resolved', workspace: await input.send(pending), pending: null }
    } catch (error) {
      if (!input.isDefinitiveRefusal(error)) return { ok: false, error, pending }
      // Прежняя отправка сервером отвергнута и снята; если нового тела нет
      // (оператор всё снял), показать этот отказ, а не слать пустую отправку.
      if (positions.length === 0) return { ok: false, error, pending: null }
    }
  }
  return sendOnce({ key: input.createKey(), boxId, positions })

  async function sendOnce(shipment: FbsBoxShipment): Promise<FbsBoxShipmentResult<W>> {
    try {
      return { ok: true, workspace: await input.send(shipment), pending: null }
    } catch (error) {
      return { ok: false, error, pending: input.isDefinitiveRefusal(error) ? null : shipment }
    }
  }
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
  wbSupplyId: string | null
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
    <div class="subtitle">${escapePrintHtml(input.supplyName)}${input.wbSupplyId ? ` · № WB ${escapePrintHtml(input.wbSupplyId)}` : ''}</div>
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
      const text = fbsErrorText(message)
      if (orders.length === 0) return text
      const sorted = [...orders].sort((a, b) => a - b)
      const label = sorted.length === 1 ? 'заказ' : 'заказы'
      return `${text} (${label} ${sorted.join(', ')})`
    })
  }
  return { blockers: collect('blocker'), warnings: collect('warning') }
}

/** Only the confirmed remote status is an acceptance; no UI navigation gates. */
export function fbsOrderMarkingAccepted(metadata: FbsOrderMetadata): boolean {
  const kinds = [...new Set([...metadata.required, ...metadata.states.filter((state) => state.value_tail).map((state) => state.kind)])]
  return kinds.every((kind) => metadata.states.some((state) =>
    state.kind === kind && state.status === 'accepted' && !state.reason?.trim(),
  ))
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
