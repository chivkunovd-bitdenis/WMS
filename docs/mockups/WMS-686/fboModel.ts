// WMS-686 · вымышленная модель FBO-подбора и упаковки для макета.
//
// Не продуктовый код и не эталон реализации: локальная модель, на которой
// настоящие экраны WMS показывают поведение R1–R27 из docs/requirements/WMS-686.md.
// У физической штуки нет собственного номера (D2): КИЗ помечает уже посчитанную
// единицу пары «отгрузка + товар + источник/короб», кодов не больше единиц.

export const FBO_STORAGE_KEY = 'wms686-fbo-v2'

export type FboProduct = {
  id: string
  sku: string
  name: string
  barcode: string
  vendorCode: string
  size: string
  color: string
  nmId: number
  honestSign: boolean
}

export type FboSource = { id: string; kind: 'box' | 'pallet'; code: string; cellId: string }
export type FboCell = { id: string; code: string }
export type FboStock = { productId: string; cellId: string; sourceId: string | null; qty: number }
export type FboShipment = {
  id: string
  number: string
  warehouse: string
  wbWarehouseId: number
  plan: Record<string, number>
}
export type FboPick = { shipmentId: string; productId: string; cellId: string; sourceId: string | null; qty: number }
export type FboBox = { id: string; shipmentId: string; code: string; closed: boolean; whole: boolean; createdAt: number }
export type FboBoxLine = { boxId: string; productId: string; qty: number }
export type FboKizLink = {
  cis: string
  shipmentId: string
  productId: string
  cellId: string | null
  sourceId: string | null
  boxId: string | null
  intakeDoc: string | null
  printed: boolean
  at: number
}
export type FboPass = { shipmentId: string; filename: string; size: number; contentType: string; dataUrl: string }

export type FboState = {
  version: 2
  clock: number
  stockTotal: Record<string, number>
  stock: FboStock[]
  picks: FboPick[]
  boxes: FboBox[]
  boxLines: FboBoxLine[]
  links: FboKizLink[]
  passes: FboPass[]
  receipts: Record<string, unknown>
  poolNext: Record<string, number>
  boxSeq: number
  /** R30: известные коды тары хранения (только из атомарных возвратов): «точно» или «возможно». */
  known: Record<string, { sourceId: string; certain: boolean }>
}

export const products: FboProduct[] = [
  { id: 'p1', sku: 'DEMO-TS-48', name: 'Футболка хлопковая оверсайз с длинным названием для проверки переноса · демонстрационный товар', barcode: '4600000000017', vendorCode: 'DEMO-TS', size: '48', color: 'Синий', nmId: 100000001, honestSign: true },
  { id: 'p2', sku: 'DEMO-TS-50', name: 'Футболка хлопковая', barcode: '4600000000024', vendorCode: 'DEMO-TS', size: '50', color: 'Серый', nmId: 100000002, honestSign: true },
  { id: 'p3', sku: 'DEMO-SOCK', name: 'Носки демо (без ЧЗ)', barcode: '4600000000031', vendorCode: 'DEMO-SK', size: '40', color: 'Белый', nmId: 100000003, honestSign: false },
]

export const cells: FboCell[] = [
  { id: 'cell-a11', code: 'А-1-1' },
  { id: 'cell-a12', code: 'А-1-2' },
]

export const sources: FboSource[] = [
  { id: 'src-inb-1', kind: 'box', code: 'INB-DEMO-001', cellId: 'cell-a11' },
  { id: 'src-inb-2', kind: 'box', code: 'INB-DEMO-002', cellId: 'cell-a11' },
  { id: 'src-plt-1', kind: 'pallet', code: 'PLT-DEMO-01', cellId: 'cell-a12' },
]

export const shipments: FboShipment[] = [
  { id: 'demo-shipment', number: '000086', warehouse: 'Демо · Краснодар', wbWarehouseId: 1, plan: { p1: 6, p2: 4, p3: 4 } },
  { id: 'demo-shipment-kazan', number: '000087', warehouse: 'Демо · Казань', wbWarehouseId: 2, plan: { p1: 2, p2: 2 } },
]

/** GS1-конверт КИЗ, как в приёмке: «01» + GTIN14 + «21» + серийный. */
export function kizFor(product: FboProduct, serial: string): string {
  return `010${product.barcode}21${serial}`
}

export function isKizScan(value: string): boolean {
  const code = value.trim().replace(/^\]d2/i, '')
  return /^01\d{14}21/.test(code) || /^\(01\)\d{14}\(21\)/.test(code) || code.includes('\x1d')
}

export function gtinProduct(cis: string): FboProduct | null {
  const match = /^01(\d{14})21/.exec(cis.trim().replace(/^\]d2/i, ''))
  if (!match) return null
  return products.find((product) => `0${product.barcode}` === match[1]) ?? null
}

/** Коды, отсканированные в вымышленной приёмке 000041 (D3: приёмка знает товар, не короб). */
export const intakeKiz: Record<string, string> = Object.fromEntries([
  [kizFor(products[0], 'P1A0001'), '000041'],
  [kizFor(products[0], 'P1A0002'), '000041'],
  [kizFor(products[0], 'P1A0003'), '000041'],
  [kizFor(products[1], 'P2A0001'), '000041'],
])

/** Размер вымышленного пула кодов для «Печатать ЧЗ»: у DEMO-TS-50 пул пуст (R16б). */
export const poolSize: Record<string, number> = { p1: 50, p2: 0, p3: 0 }

/** КИЗ, однажды привязанные в другой отгрузке/заказе FBS (для показа отказа). */
export const usedElsewhere: Record<string, string> = {
  [kizFor(products[0], 'P1FBS01')]: 'заказ FBS 4471',
}

export function createFboState(): FboState {
  const stock: FboStock[] = [
    { productId: 'p1', cellId: 'cell-a11', sourceId: 'src-inb-1', qty: 6 },
    { productId: 'p2', cellId: 'cell-a11', sourceId: 'src-inb-1', qty: 4 },
    { productId: 'p1', cellId: 'cell-a11', sourceId: 'src-inb-2', qty: 3 },
    { productId: 'p3', cellId: 'cell-a11', sourceId: 'src-inb-2', qty: 2 },
    { productId: 'p3', cellId: 'cell-a12', sourceId: null, qty: 4 },
    { productId: 'p2', cellId: 'cell-a12', sourceId: 'src-plt-1', qty: 2 },
  ]
  const stockTotal: Record<string, number> = {}
  for (const line of stock) stockTotal[line.productId] = (stockTotal[line.productId] ?? 0) + line.qty
  return {
    version: 2, clock: 1, stockTotal, stock, picks: [], boxes: [], boxLines: [], links: [], passes: [],
    receipts: {}, poolNext: {}, boxSeq: 0, known: {},
  }
}

export type FboResult<T> = { ok: true; value: T } | { ok: false; error: string; status?: number }
const ok = <T,>(value: T): FboResult<T> => ({ ok: true, value })
const fail = <T,>(error: string, status = 422): FboResult<T> => ({ ok: false, error, status })

export const productById = (id: string) => products.find((product) => product.id === id) ?? null
export const productByBarcode = (code: string) =>
  products.find((product) => product.barcode === code.trim() || product.sku.toLowerCase() === code.trim().toLowerCase()) ?? null
export const sourceById = (id: string | null) => sources.find((source) => source.id === id) ?? null
export const shipmentById = (id: string) => shipments.find((shipment) => shipment.id === id) ?? shipments[0]

export function pickedQty(state: FboState, shipmentId: string, productId: string, sourceId?: string | null, cellId?: string): number {
  return state.picks
    .filter((pick) => pick.shipmentId === shipmentId && pick.productId === productId
      && (sourceId === undefined || pick.sourceId === sourceId) && (cellId === undefined || pick.cellId === cellId))
    .reduce((sum, pick) => sum + pick.qty, 0)
}

export function boxedQty(state: FboState, shipmentId: string, productId: string, boxId?: string): number {
  const ids = new Set(state.boxes.filter((box) => box.shipmentId === shipmentId && (!boxId || box.id === boxId)).map((box) => box.id))
  return state.boxLines.filter((line) => ids.has(line.boxId) && line.productId === productId).reduce((sum, line) => sum + line.qty, 0)
}

export const linksOf = (state: FboState, shipmentId: string) => state.links.filter((link) => link.shipmentId === shipmentId)

function physical(state: FboState, productId: string, cellId: string, sourceId: string | null): FboStock | undefined {
  return state.stock.find((line) => line.productId === productId && line.cellId === cellId && line.sourceId === sourceId)
}

function clone(state: FboState): FboState {
  return JSON.parse(JSON.stringify(state)) as FboState
}

/** Скан ШК в «Подборе» (R2): +1 из источника сразу, остаток не меняется — товар уходит на «Сортировку». */
export function pickUnit(state: FboState, shipmentId: string, productId: string, cellId: string, sourceId: string | null, qty = 1): FboResult<FboState> {
  const shipment = shipmentById(shipmentId)
  const plan = shipment.plan[productId] ?? 0
  if (!plan) return fail('Этого товара нет в плане отгрузки')
  if (pickedQty(state, shipmentId, productId) + qty > plan) return fail('plan_limit_exceeded')
  const line = physical(state, productId, cellId, sourceId)
  if (!line || line.qty < qty) return fail('В выбранном источнике недостаточно товара')
  const next = clone(state)
  const stockLine = physical(next, productId, cellId, sourceId)!
  stockLine.qty -= qty
  const pick = next.picks.find((one) => one.shipmentId === shipmentId && one.productId === productId && one.cellId === cellId && one.sourceId === sourceId)
  if (pick) pick.qty += qty
  else next.picks.push({ shipmentId, productId, cellId, sourceId, qty })
  if (sourceId) degradeKnown(next, sourceId, productId, stockLine.qty)
  next.clock += 1
  return ok(next)
}

/** R30: снятие без кода — оператор мог взять единицу с известным кодом; код никому не назначается. */
function degradeKnown(state: FboState, sourceId: string, productId: string, leftInSource: number) {
  for (const [cis, entry] of Object.entries(state.known)) {
    if (entry.sourceId !== sourceId || gtinProduct(cis)?.id !== productId) continue
    if (leftInSource <= 0) delete state.known[cis]
    else entry.certain = false
  }
}

/** Итог «Снять» по источнику (R8, R9): уменьшение — сначала единицы без КИЗ. */
export function setPicked(state: FboState, shipmentId: string, productId: string, cellId: string, sourceId: string | null, quantity: number): FboResult<FboState> {
  const current = pickedQty(state, shipmentId, productId, sourceId, cellId)
  if (quantity > current) return pickUnit(state, shipmentId, productId, cellId, sourceId, quantity - current)
  if (quantity === current) return ok(state)
  const remove = current - quantity
  const withKiz = state.links.filter((link) => link.shipmentId === shipmentId && link.productId === productId
    && link.sourceId === sourceId && link.cellId === cellId).length
  if (quantity < withKiz) {
    return fail('Все оставшиеся единицы этого источника с КИЗ. Уберите КИЗ возвращаемой единицы (✕ у кода), затем уменьшите количество.')
  }
  const boxed = boxedQty(state, shipmentId, productId)
  const picked = pickedQty(state, shipmentId, productId)
  if (picked - remove < boxed) return fail('Эти единицы уже в коробах. Сначала уберите их из короба.')
  const next = clone(state)
  const pick = next.picks.find((one) => one.shipmentId === shipmentId && one.productId === productId && one.cellId === cellId && one.sourceId === sourceId)!
  pick.qty -= remove
  if (pick.qty <= 0) next.picks = next.picks.filter((one) => one !== pick)
  const line = physical(next, productId, cellId, sourceId)
  if (line) line.qty += remove
  else next.stock.push({ productId, cellId, sourceId, qty: remove })
  next.clock += 1
  return ok(next)
}

export type KizTarget = { productId: string | null; cellId: string | null; sourceId: string | null; boxId: string | null }
export type KizLinkResult = { state: FboState; link: FboKizLink; already: boolean; confirmed?: boolean; warning?: string }

const linksIn = (state: FboState, shipmentId: string, productId: string, where: (link: FboKizLink) => boolean) =>
  state.links.filter((link) => link.shipmentId === shipmentId && link.productId === productId && where(link)).length

/**
 * Привязка КИЗ (R3, R5, R6, R14, R29, R30): товар — по GTIN, иначе последний ШК;
 * единица — только в текущем источнике/коробе, без молчаливого переноса. Количество не меняется.
 */
export function linkKiz(state: FboState, shipmentId: string, rawCis: string, target: KizTarget, printed = false): FboResult<KizLinkResult> {
  const cis = rawCis.trim().replace(/^\]d2/i, '')
  const own = state.links.find((link) => link.cis === cis)
  const boxId = target.boxId
  if (own && own.shipmentId !== shipmentId) {
    return fail(`КИЗ уже числится в отгрузке ${shipmentById(own.shipmentId).number}. Единица посчитана, код не привязан.`)
  }
  if (own && boxId) {
    if (own.boxId === boxId) return ok({ state, link: own, already: true })
    if (own.boxId) {
      const other = state.boxes.find((box) => box.id === own.boxId)?.code ?? ''
      return fail(`КИЗ числится в коробе ${other}. Уберите его там или отсканируйте короб ${other}.`)
    }
    // R29б: код подбора без короба подтверждается в текущем коробе — без +1 и без второй связи.
    const inBox = boxedQty(state, shipmentId, own.productId, boxId)
    if (linksIn(state, shipmentId, own.productId, (link) => link.boxId === boxId) >= inBox) {
      return fail(`В текущем коробе нет единицы ${productById(own.productId)?.sku} без КИЗ. Отсканируйте ШК короба, в котором лежит эта единица.`)
    }
    const next = clone(state)
    next.clock += 1
    const link = next.links.find((one) => one.cis === cis)!
    link.boxId = boxId
    return ok({ state: next, link, already: true, confirmed: true })
  }
  if (own) return ok({ state, link: own, already: true })
  if (usedElsewhere[cis]) return fail(`КИЗ уже использован: ${usedElsewhere[cis]}. Единица посчитана, код не привязан.`)
  const byGtin = gtinProduct(cis)
  // D16: после ШК цель — эта единица; несовместимый GTIN — отказ, без смены цели.
  if (target.productId && byGtin && byGtin.id !== target.productId) {
    return fail(`КИЗ относится к товару ${byGtin.sku}, а последним отсканирован ${productById(target.productId)?.sku}. Код не привязан.`)
  }
  const productId = target.productId ?? byGtin?.id ?? null
  if (!productId) return fail('Сначала отсканируйте ШК товара, затем его КИЗ.')
  const sku = productById(productId)?.sku ?? productId
  let { cellId, sourceId } = target
  let warning: string | undefined
  if (boxId) {
    if (linksIn(state, shipmentId, productId, (link) => link.boxId === boxId) >= boxedQty(state, shipmentId, productId, boxId)) {
      const box = state.boxes.find((one) => one.id === boxId)?.code ?? ''
      return fail(`В текущем коробе ${box} нет единицы ${sku} без КИЗ. Отсканируйте ШК короба, в котором лежит эта единица.`)
    }
    cellId = null
    sourceId = null
  } else {
    if (!cellId) {
      const candidates = state.picks.filter((pick) => pick.shipmentId === shipmentId && pick.productId === productId
        && pick.qty > linksIn(state, shipmentId, productId, (link) => link.cellId === pick.cellId && link.sourceId === pick.sourceId))
      if (candidates.length !== 1) return fail(`Отсканируйте ячейку или тару, из которой снята эта единица ${sku}.`)
      cellId = candidates[0].cellId
      sourceId = candidates[0].sourceId
    }
    const units = pickedQty(state, shipmentId, productId, sourceId, cellId)
    if (linksIn(state, shipmentId, productId, (link) => link.cellId === cellId && link.sourceId === sourceId) >= units) {
      const place = sourceById(sourceId)?.code ?? cells.find((cell) => cell.id === cellId)?.code ?? 'источник'
      return fail(units ? `Коды уже есть у всех снятых из ${place} единиц ${sku}. Сначала отсканируйте ШК следующей единицы.` : `Нет снятой единицы ${sku} без КИЗ в ${place}.`)
    }
  }
  const next = clone(state)
  next.clock += 1
  const knownIn = next.known[cis]
  if (knownIn) {
    if (!boxId && knownIn.sourceId !== sourceId) warning = `КИЗ числился в таре ${sourceById(knownIn.sourceId)?.code ?? knownIn.sourceId} — запись исправлена.`
    delete next.known[cis]
  }
  const link: FboKizLink = { cis, shipmentId, productId, cellId, sourceId, boxId: boxId ?? null, intakeDoc: intakeKiz[cis] ?? null, printed, at: next.clock }
  next.links.push(link)
  return ok({ state: next, link, already: false, warning })
}

export function unlinkKiz(state: FboState, shipmentId: string, cis: string): { state: FboState; removed: boolean } {
  if (!state.links.some((link) => link.shipmentId === shipmentId && link.cis === cis)) return { state, removed: false }
  const next = clone(state)
  next.links = next.links.filter((link) => !(link.shipmentId === shipmentId && link.cis === cis))
  next.clock += 1
  return { state: next, removed: true }
}

export function createBoxes(state: FboState, shipmentId: string, count: number): FboState {
  const next = clone(state)
  for (let i = 0; i < count; i += 1) {
    next.boxSeq += 1
    next.clock += 1
    next.boxes.push({ id: `box-${next.boxSeq}`, shipmentId, code: `WHB-DEMO-${String(next.boxSeq).padStart(4, '0')}`, closed: false, whole: false, createdAt: next.clock })
  }
  return next
}

/** Скан ШК на «Упаковке» (R13): кладёт только подобранную, ещё не уложенную единицу. */
export function packUnit(state: FboState, shipmentId: string, boxId: string, productId: string): FboResult<FboState> {
  const box = state.boxes.find((one) => one.id === boxId && one.shipmentId === shipmentId)
  if (!box) return fail('Короб не найден в этой отгрузке', 404)
  if (!(shipmentById(shipmentId).plan[productId] ?? 0)) return fail('Этого товара нет в отгрузке')
  if (pickedQty(state, shipmentId, productId) - boxedQty(state, shipmentId, productId) < 1) {
    return fail('nothing_picked_to_pack')
  }
  const next = clone(state)
  const line = next.boxLines.find((one) => one.boxId === boxId && one.productId === productId)
  if (line) line.qty += 1
  else next.boxLines.push({ boxId, productId, qty: 1 })
  next.clock += 1
  return ok(next)
}

/** «Отменить последний скан» упаковки: единица возвращается в подобранные, КИЗ этой единицы — отвязывается. */
export function unpackUnit(state: FboState, shipmentId: string, boxId: string, productId: string): FboState {
  const next = clone(state)
  const line = next.boxLines.find((one) => one.boxId === boxId && one.productId === productId)
  if (!line || line.qty < 1) return state
  line.qty -= 1
  if (line.qty === 0) next.boxLines = next.boxLines.filter((one) => one !== line)
  const linked = next.links.filter((link) => link.shipmentId === shipmentId && link.productId === productId && link.boxId === boxId)
  if (linked.length > (line.qty ?? 0)) {
    const last = linked.sort((a, b) => b.at - a.at)[0]
    next.links = next.links.filter((link) => link !== last)
  }
  next.clock += 1
  return next
}

/** Целиком (R7): всё содержимое тары → короб отгрузки с собственным ШК; повтор не удваивает. */
export function takeWhole(state: FboState, shipmentId: string, sourceCode: string, allowOverPlan: boolean): FboResult<FboState> {
  const source = sources.find((one) => one.code === sourceCode)
  if (!source) return fail('box_barcode_unknown')
  const contents = state.stock.filter((line) => line.sourceId === source.id && line.qty > 0)
  if (!contents.length) return fail('box_empty')
  const plan = shipmentById(shipmentId).plan
  if (contents.some((line) => !(plan[line.productId] ?? 0))) return fail('В таре есть товар не из этой отгрузки')
  if (!allowOverPlan && contents.some((line) => pickedQty(state, shipmentId, line.productId) + line.qty > (plan[line.productId] ?? 0))) {
    return fail('plan_limit_exceeded')
  }
  const next = clone(state)
  next.clock += 1
  const box: FboBox = { id: `box-whole-${source.id}-${next.clock}`, shipmentId, code: source.code, closed: true, whole: true, createdAt: next.clock }
  next.boxes.push(box)
  for (const line of contents) {
    const qty = line.qty
    const stockLine = physical(next, line.productId, line.cellId, line.sourceId)!
    stockLine.qty -= qty
    const pick = next.picks.find((one) => one.shipmentId === shipmentId && one.productId === line.productId && one.cellId === line.cellId && one.sourceId === line.sourceId)
    if (pick) pick.qty += qty
    else next.picks.push({ shipmentId, productId: line.productId, cellId: line.cellId, sourceId: line.sourceId, qty })
    next.boxLines.push({ boxId: box.id, productId: line.productId, qty })
  }
  // R30а: известные коды тары уходят в короб отгрузки конкретными кодами.
  for (const [cis, entry] of Object.entries(next.known)) {
    if (entry.sourceId !== source.id) continue
    const product = gtinProduct(cis)
    delete next.known[cis]
    // «Возможно в таре» не переносится и никому не назначается.
    if (!product || !entry.certain) continue
    next.links.push({ cis, shipmentId, productId: product.id, cellId: source.cellId, sourceId: source.id, boxId: box.id, intakeDoc: intakeKiz[cis] ?? null, printed: false, at: next.clock })
  }
  return ok(next)
}

/** «Печатать ЧЗ» (R16б, R29г): один код из пула на непомеченную единицу в коробе. */
export function printUnitCode(state: FboState, shipmentId: string, boxId: string, productId: string): FboResult<KizLinkResult> {
  const product = productById(productId)!
  if (state.links.some((link) => link.shipmentId === shipmentId && link.productId === productId && !link.boxId)) {
    return fail('unit_may_be_marked')
  }
  if (linksIn(state, shipmentId, productId, (link) => link.boxId === boxId) >= boxedQty(state, shipmentId, productId, boxId)) {
    return fail('unit_may_be_marked')
  }
  if ((state.poolNext[productId] ?? 0) >= (poolSize[productId] ?? 0)) return fail('marking_pool_empty')
  const next = clone(state)
  next.poolNext[productId] = (next.poolNext[productId] ?? 0) + 1
  const cis = kizFor(product, `POOL${String(next.poolNext[productId]).padStart(4, '0')}`)
  return linkKiz(next, shipmentId, cis, { productId, cellId: null, sourceId: null, boxId }, true)
}

/** Куда вернётся единица без КИЗ (D14): последний источник подбора с непомеченными единицами. */
export function returnSourceFor(state: FboState, shipmentId: string, productId: string): FboPick | null {
  const candidates = state.picks.filter((pick) => pick.shipmentId === shipmentId && pick.productId === productId
    && pick.qty > linksIn(state, shipmentId, productId, (link) => link.cellId === pick.cellId && link.sourceId === pick.sourceId))
  return candidates.at(-1) ?? null
}

export type ReturnPlace = { cellId: string; sourceId: string | null }
export type RemoveResult = { state: FboState; returnedTo: ReturnPlace; sourceKnown: boolean }

/** Источники подбора товара в отгрузке — существующий контекст выбора места возврата (R28). */
export function pickSourcesOf(state: FboState, shipmentId: string, productId: string): ReturnPlace[] {
  return state.picks.filter((pick) => pick.shipmentId === shipmentId && pick.productId === productId && pick.qty > 0)
    .map((pick) => ({ cellId: pick.cellId, sourceId: pick.sourceId }))
}

function moveBack(next: FboState, shipmentId: string, productId: string, place: ReturnPlace) {
  const pick = next.picks.find((one) => one.shipmentId === shipmentId && one.productId === productId && one.cellId === place.cellId && one.sourceId === place.sourceId)!
  pick.qty -= 1
  if (pick.qty <= 0) next.picks = next.picks.filter((one) => one !== pick)
  const stock = physical(next, productId, place.cellId, place.sourceId)
  if (stock) stock.qty += 1
  else next.stock.push({ productId, cellId: place.cellId, sourceId: place.sourceId, qty: 1 })
}

/** R28: убрать одну конкретную единицу из короба отгрузки; место — известное или выбранное оператором. */
export function removeUnitFromBox(state: FboState, shipmentId: string, boxId: string, productId: string, cis: string | null, returnTo: ReturnPlace | null): FboResult<RemoveResult> {
  const line = state.boxLines.find((one) => one.boxId === boxId && one.productId === productId)
  if (!line || line.qty < 1) return fail('В коробе нет этого товара', 404)
  const boxLinks = state.links.filter((link) => link.shipmentId === shipmentId && link.productId === productId && link.boxId === boxId)
  let link: FboKizLink | undefined
  if (cis) {
    link = boxLinks.find((one) => one.cis === cis)
    if (!link) return fail('Этот КИЗ не в этом коробе')
  } else if (boxLinks.length >= line.qty) {
    return fail('marking_unit_ambiguous')
  }
  const sources = pickSourcesOf(state, shipmentId, productId)
  const sourceKnown = Boolean(link?.cellId)
  let place: ReturnPlace | null = null
  if (link?.cellId) {
    place = { cellId: link.cellId, sourceId: link.sourceId }
  } else if (returnTo) {
    if (!sources.some((one) => one.cellId === returnTo.cellId && one.sourceId === returnTo.sourceId)) return fail('invalid_return_place')
    place = returnTo
  } else if (link) {
    return fail('return_place_required')
  } else {
    const suggested = returnSourceFor(state, shipmentId, productId)
    place = suggested ? { cellId: suggested.cellId, sourceId: suggested.sourceId } : sources.at(-1) ?? null
  }
  if (!place) return fail('Не найден источник подбора единицы')
  const next = clone(state)
  next.clock += 1
  const nextLine = next.boxLines.find((one) => one.boxId === boxId && one.productId === productId)!
  nextLine.qty -= 1
  if (nextLine.qty === 0) next.boxLines = next.boxLines.filter((one) => one !== nextLine)
  moveBack(next, shipmentId, productId, place)
  if (link) {
    next.links = next.links.filter((one) => one.cis !== link!.cis)
    if (place.sourceId) next.known[link.cis] = { sourceId: place.sourceId, certain: true }
  }
  return ok({ state: next, returnedTo: place, sourceKnown })
}

/** R9в: атомарно вернуть единицу с кодом из подбора в её источник; код — «точно в таре». */
export function returnPickedUnit(state: FboState, shipmentId: string, cis: string): FboResult<RemoveResult> {
  const link = state.links.find((one) => one.shipmentId === shipmentId && one.cis === cis)
  if (!link) return fail('Код не числится в этой отгрузке', 404)
  if (!link.cellId) return fail('return_place_required')
  if (link.boxId) return fail('Единица уже в коробе — уберите её из короба (блок «Короба»)')
  const place = { cellId: link.cellId, sourceId: link.sourceId }
  const next = clone(state)
  next.clock += 1
  moveBack(next, shipmentId, link.productId, place)
  next.links = next.links.filter((one) => one.cis !== cis)
  if (place.sourceId) next.known[cis] = { sourceId: place.sourceId, certain: true }
  return ok({ state: next, returnedTo: place, sourceKnown: true })
}

export function closeBox(state: FboState, shipmentId: string, boxId: string): FboState {
  const next = clone(state)
  const box = next.boxes.find((one) => one.id === boxId && one.shipmentId === shipmentId)
  if (box) box.closed = true
  next.clock += 1
  return next
}

export function setPass(state: FboState, pass: FboPass): FboState {
  const next = clone(state)
  next.passes = [...next.passes.filter((one) => one.shipmentId !== pass.shipmentId), pass]
  next.clock += 1
  return next
}

export function loadFboState(storage: Pick<Storage, 'getItem'> | null): FboState {
  try {
    const raw = storage?.getItem(FBO_STORAGE_KEY)
    if (!raw) return createFboState()
    const parsed = JSON.parse(raw) as FboState
    return parsed.version === 2 ? { ...parsed, known: parsed.known ?? {} } : createFboState()
  } catch {
    return createFboState()
  }
}

export function saveFboState(state: FboState, storage: Pick<Storage, 'setItem'> | null): void {
  try {
    storage?.setItem(FBO_STORAGE_KEY, JSON.stringify(state))
  } catch {
    // Демо продолжает работать без сохранения.
  }
}
