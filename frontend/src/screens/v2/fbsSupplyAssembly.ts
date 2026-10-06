import type { FbsPickingListPrintRow } from './fbsUx'
import type {
  FbsAssemblyTask,
  FbsSupplyWorklistItem,
  FbsWorklistOrder,
  FbsWorkspace,
} from './fbsApi'

// WMS-574: групповая сборка нескольких поставок WB FBS.
//
// Здесь только чистые правила без React: как выбор делится на поставки (Д1),
// как считается шапка окна сборки (R5), как штука общего подбора раздаётся по
// поставкам группы (Д5) и где хранится выбранная вкладка (Д4). Карточка одной
// поставки и окно создания одной поставки этот модуль не используют.

/** Шесть признаков, по которым сервер отказывает в объединении заказов (fbs_supply_validator_service). */
export function fbsSupplyGroupKey(order: FbsWorklistOrder): string {
  return [
    order.marketplace,
    order.seller.id,
    Number(order.wb_warehouse.id),
    order.wms_warehouse.id,
    order.buyer_type,
    order.cargo_type,
  ].join('|')
}

export type FbsSupplyGroupDraft = {
  key: string
  sellerName: string
  wbWarehouseName: string
  cargoType: string
  orderIds: string[]
}

function wbWarehouseLabel(order: FbsWorklistOrder): string {
  return order.wb_warehouse.name || `WB ${order.wb_warehouse.id}`
}

/**
 * Д1: делим выбранные заказы на будущие поставки. Порядок групп — по селлеру,
 * затем по складу WB и грузовому типу: он же порядок создания, порядок рамок
 * и порядок раздачи подбора (Д5). Внутри группы заказы идут в порядке выбора.
 */
export function groupFbsOrdersForSupplies(orders: FbsWorklistOrder[]): FbsSupplyGroupDraft[] {
  const byKey = new Map<string, FbsSupplyGroupDraft & { sort: string[] }>()
  for (const order of orders) {
    const key = fbsSupplyGroupKey(order)
    const current = byKey.get(key)
    if (current) {
      current.orderIds.push(order.id)
      continue
    }
    byKey.set(key, {
      key,
      sellerName: order.seller.name,
      wbWarehouseName: wbWarehouseLabel(order),
      cargoType: order.cargo_type,
      orderIds: [order.id],
      sort: [
        order.seller.name,
        wbWarehouseLabel(order),
        order.cargo_type,
        order.wms_warehouse.name,
        order.buyer_type,
        key,
      ],
    })
  }
  return [...byKey.values()]
    .sort((a, b) => {
      for (let index = 0; index < a.sort.length; index += 1) {
        const diff = a.sort[index].localeCompare(b.sort[index], 'ru')
        if (diff !== 0) return diff
      }
      return 0
    })
    .map((group) => ({
      key: group.key,
      sellerName: group.sellerName,
      wbWarehouseName: group.wbWarehouseName,
      cargoType: group.cargoType,
      orderIds: group.orderIds,
    }))
}

/**
 * Д2: новое окно появляется, только когда выбор WB делится на две и больше
 * поставок. Выбор Ozon, смешанный выбор и выбор на одну поставку идут прежним
 * путём — окном одной поставки без изменений.
 */
export function fbsSelectionNeedsGroupCreate(orders: FbsWorklistOrder[]): boolean {
  if (orders.length < 2) return false
  if (!orders.every((order) => order.marketplace === 'wb')) return false
  return groupFbsOrdersForSupplies(orders).length > 1
}

/** Те же числа, что шапка карточки поставки показывает для одной поставки. */
export function fbsWorkspaceReadiness(workspace: FbsWorkspace): { ready: number; total: number } {
  const total = workspace.progress.total
  const ready = workspace.supply.marketplace === 'wb'
    ? total
    : Math.min(
      total,
      workspace.progress.picked,
      workspace.progress.packed,
      workspace.progress.metadata_ready,
      workspace.progress.stickers_ready,
    )
  return { ready, total }
}

export function fbsAssemblyReadiness(workspaces: FbsWorkspace[]): { ready: number; total: number } {
  return workspaces.reduce(
    (sum, workspace) => {
      const one = fbsWorkspaceReadiness(workspace)
      return { ready: sum.ready + one.ready, total: sum.total + one.total }
    },
    { ready: 0, total: 0 },
  )
}

export function fbsSupplyRouteLabel(workspace: FbsWorkspace): string {
  return workspace.supply.delivery_type === 'pvz' ? 'ПВЗ' : 'Склад / СЦ'
}

export function fbsSupplyWbWarehouseName(workspace: FbsWorkspace): string {
  return workspace.supply.wb_warehouse.name || `WB ${workspace.supply.wb_warehouse.id}`
}

/** Подзаголовок «Состава» называет именно ту площадку, к которой относится поставка. */
export function fbsAssemblySupplyTitle(workspace: FbsWorkspace): string {
  const parts = [`Поставка ${workspace.supply.name}`]
  if (workspace.supply.marketplace === 'wb') {
    if (workspace.supply.wb_supply_id) parts.push(`WB № ${workspace.supply.wb_supply_id}`)
    parts.push(workspace.supply.seller.name, `Склад WB ${fbsSupplyWbWarehouseName(workspace)}`)
  } else {
    parts.push('Ozon', workspace.supply.seller.name, `Склад WMS ${workspace.supply.wms_warehouse.name}`)
  }
  return parts.join(' · ')
}

/** Поставка передана в WB — те же признаки, что у карточки (deliveryConfirmed без локального флага). */
export function fbsSupplyTransferred(workspace: FbsWorkspace): boolean {
  return workspace.stage === 'tracking' || ['in_delivery', 'done'].includes(workspace.supply.status)
}

// ── Адрес и вкладка окна сборки (Д4) ───────────────────────────────────────

export const FBS_ASSEMBLY_QUERY_PARAM = 'supply_ids'

export function parseFbsAssemblySupplyIds(value: string | null): string[] {
  if (!value) return []
  const ids = value.split(',').map((one) => one.trim()).filter(Boolean)
  return [...new Set(ids)]
}

export type FbsAssemblyStageKey = 'composition' | 'picking' | 'packing' | 'boxes'

type StageStorage = Pick<Storage, 'getItem' | 'setItem'>

function assemblyStageKey(supplyIds: string[]): string {
  return `wms:fbs:assembly:${supplyIds.join(',')}:stage`
}

export function readFbsAssemblyStage(supplyIds: string[], storage?: StageStorage): FbsAssemblyStageKey | null {
  try {
    const value = (storage ?? window.sessionStorage).getItem(assemblyStageKey(supplyIds))
    return value === 'composition' || value === 'picking' || value === 'packing' || value === 'boxes' ? value : null
  } catch {
    return null
  }
}

export function saveFbsAssemblyStage(supplyIds: string[], stage: FbsAssemblyStageKey, storage?: StageStorage): void {
  try {
    (storage ?? window.sessionStorage).setItem(assemblyStageKey(supplyIds), stage)
  } catch {
    // Хранилище может быть недоступно — вкладка работает в пределах открытия.
  }
}

// ── «В работе»: задания и поставки (WMS-588 R3) ───────────────────────────

export type FbsAssemblyTaskSupplyGroup = {
  task: FbsAssemblyTask
  supplies: FbsSupplyWorklistItem[]
}

/**
 * Собирает существующие строки поставок под строками заданий, не меняя сами
 * данные строки. Задания идут в порядке ответа API, поставки внутри — в порядке
 * состава задания. Поставки без задания остаются самостоятельными и сохраняют
 * прежний порядок worklist.
 */
export function groupFbsAssemblyTaskSupplies(
  tasks: FbsAssemblyTask[],
  supplies: FbsSupplyWorklistItem[],
): { groups: FbsAssemblyTaskSupplyGroup[]; standalone: FbsSupplyWorklistItem[] } {
  const supplyById = new Map(supplies.map((supply) => [supply.id, supply]))
  const assigned = new Set<string>()
  const groups: FbsAssemblyTaskSupplyGroup[] = []

  for (const task of tasks) {
    const visible = task.supplies
      .map((supply) => supplyById.get(supply.id))
      .filter((supply): supply is FbsSupplyWorklistItem => (
        supply !== undefined && !assigned.has(supply.id)
      ))
    if (visible.length === 0) continue
    visible.forEach((supply) => assigned.add(supply.id))
    groups.push({ task, supplies: visible })
  }

  return {
    groups,
    standalone: supplies.filter((supply) => !assigned.has(supply.id)),
  }
}

// ── Общий подбор: кому достаётся штука (Д5) ────────────────────────────────

/** Состояние одной поставки группы по одному товару в одном месте. */
export type GroupPickSupplyState = {
  /** Индекс поставки в группе — порядок раздачи. */
  index: number
  /** План поставки по товару. */
  planned: number
  /** Сколько этого товара уже подобрано в поставке по всем местам. */
  pickedTotal: number
  /** Сколько подобрано в поставке именно из этого места. */
  pickedHere: number
}

/** Одна запись истории снятия: сколько штук этого места ушло какой поставке. */
export type GroupPickLogEntry = { index: number; qty: number }

/**
 * Скан товара: первая по порядку поставка, которой этот товар ещё нужен.
 * Если не нужен никому — первая поставка с этим товаром, чтобы оператор
 * получил прежний отказ сервера («уже подобран»), а не новый текст.
 */
export function pickScanTargets(states: GroupPickSupplyState[]): number[] {
  const ordered = [...states].sort((a, b) => a.index - b.index)
  const needing = ordered.filter((one) => one.planned - one.pickedTotal > 0).map((one) => one.index)
  if (needing.length > 0) return needing
  return ordered.length > 0 ? [ordered[0].index] : []
}

/**
 * Новое число в поле «Снять» места раскладывается на итоговые числа поставок.
 * Увеличение идёт по порядку поставок, пока у них есть неподобранные заказы;
 * уменьшение сначала снимает последние снятия этого места (история), потом
 * с поставок в обратном порядке. Возвращает только поставки, у которых
 * число меняется, — в порядке отправки запросов, и новую историю.
 */
export function planGroupPickSet(
  states: GroupPickSupplyState[],
  target: number,
  log: GroupPickLogEntry[],
): { changes: Array<{ index: number; quantity: number }>; log: GroupPickLogEntry[] } {
  const ordered = [...states].sort((a, b) => a.index - b.index)
  const current = ordered.reduce((sum, one) => sum + one.pickedHere, 0)
  const next = new Map(ordered.map((one) => [one.index, one.pickedHere]))
  const nextLog = log.map((entry) => ({ ...entry }))
  let delta = Math.max(0, target) - current

  if (delta > 0) {
    const order: number[] = []
    for (const one of ordered) {
      if (delta <= 0) break
      const room = Math.max(0, one.planned - one.pickedTotal)
      const give = Math.min(room, delta)
      if (give <= 0) continue
      next.set(one.index, one.pickedHere + give)
      nextLog.push({ index: one.index, qty: give })
      order.push(one.index)
      delta -= give
    }
    if (delta > 0 && ordered.length > 0) {
      // Больше, чем ждут заказы группы: отдаём остаток последней поставке —
      // сервер ответит тем же отказом, что и в карточке одной поставки.
      const last = ordered[ordered.length - 1]
      next.set(last.index, (next.get(last.index) ?? 0) + delta)
      if (!order.includes(last.index)) order.push(last.index)
    }
    return {
      changes: order.map((index) => ({ index, quantity: next.get(index) ?? 0 })),
      log: nextLog,
    }
  }

  if (delta < 0) {
    let remove = -delta
    const removed = new Map<number, number>()
    const canRemove = (index: number) => (next.get(index) ?? 0) - (removed.get(index) ?? 0)
    for (let position = nextLog.length - 1; position >= 0 && remove > 0; position -= 1) {
      const entry = nextLog[position]
      const take = Math.min(entry.qty, remove, Math.max(0, canRemove(entry.index)))
      if (take <= 0) continue
      entry.qty -= take
      removed.set(entry.index, (removed.get(entry.index) ?? 0) + take)
      remove -= take
    }
    for (const one of [...ordered].reverse()) {
      if (remove <= 0) break
      const take = Math.min(Math.max(0, canRemove(one.index)), remove)
      if (take <= 0) continue
      removed.set(one.index, (removed.get(one.index) ?? 0) + take)
      remove -= take
    }
    const changes = [...ordered]
      .reverse()
      .filter((one) => (removed.get(one.index) ?? 0) > 0)
      .map((one) => ({ index: one.index, quantity: one.pickedHere - (removed.get(one.index) ?? 0) }))
    return { changes, log: nextLog.filter((entry) => entry.qty > 0) }
  }

  return { changes: [], log: nextLog }
}

// ── Лист подбора группы (Д14) ──────────────────────────────────────────────

/** Строки листа по всем поставкам группы — тем же правилом, что строки листа карточки. */
export function fbsAssemblyPickingRows(workspaces: FbsWorkspace[]): Array<FbsPickingListPrintRow & { key: string }> {
  const grouped = new Map<string, FbsPickingListPrintRow & { key: string }>()
  for (const workspace of workspaces) {
    const orders = [...workspace.orders].sort((a, b) => a.tape_order_index - b.tape_order_index)
    for (const order of orders) {
      // Older position-bearing responses can omit the marketplace discriminator.
      const rows = order.marketplace !== 'wb' && (order.positions?.length ?? 0) > 0
        ? order.positions.map((position, positionIndex) => ({
            key: position.product_id ?? `unmapped-${order.id}-${position.id ?? positionIndex}`,
            name: position.name,
            size: position.size ?? null,
            color: position.color ?? null,
            imageUrl: position.image_url ?? null,
            identifiers: [
              position.seller_article,
              position.sku ? `SKU ${position.sku}` : null,
              position.barcode,
            ].filter((value): value is string => Boolean(value)),
            required: position.quantity,
            picked: position.picked_quantity,
          }))
        : [{
            key: order.product.id ?? `unmapped-${order.id}`,
            name: order.product.name,
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
        }
        current.required += row.required
        current.picked += row.picked
        // Field name is historical; for Ozon it contains the posting number.
        current.wbOrders.push(order.marketplace === 'ozon'
          ? (order.external_order_id ?? String(order.wb_order_id))
          : order.wb_order_id)
        current.stickerCodes.push(order.sticker.code)
        const locations = order.inventory.locations
          .filter((location) => location.available_unpacked > 0)
          .map((location) => `${location.code}: ${location.available_unpacked}`)
        current.locations = [...new Set([...current.locations, ...locations])]
        grouped.set(row.key, current)
      }
    }
  }
  return [...grouped.values()]
}

// ── Создание нескольких поставок (Д3, R3, R4) ──────────────────────────────

export type FbsGroupCreateResult =
  | { status: 'created'; supplyId: string; name: string; wbSupplyId: string | null }
  | { status: 'pending'; message: string }
  | { status: 'failed'; message: string }

export type FbsGroupCreatedSupply = {
  groupKey: string
  supplyId: string
}

type CreateErrorLike = {
  message?: unknown
  code?: unknown
  retryable?: unknown
  context?: unknown
}

/**
 * Итог неудачной попытки группы и судьба её ключа повтора. Тексты — те же,
 * что у окна одной поставки. Ключ живёт, пока исход у WB неизвестен или ответ
 * потерян: повтор с ним не создаёт вторую поставку. Окончательный отказ
 * сервера ключ меняет, как в окне одной поставки, иначе повтор упрётся
 * в сохранённую неудачную попытку.
 */
export function fbsGroupCreateFailure(cause: unknown, isApiError: boolean): {
  result: FbsGroupCreateResult
  keepKey: boolean
} {
  const error = (cause && typeof cause === 'object' ? cause : {}) as CreateErrorLike
  const message = typeof error.message === 'string' && error.message
    ? error.message
    : 'Не удалось создать поставку.'
  if (!isApiError) return { result: { status: 'failed', message }, keepKey: true }
  const retryable = error.retryable === true
  if (retryable && (error.code === 'wb_timeout' || error.code === 'wb_pending_confirmation')) {
    const context = error.context && typeof error.context === 'object'
      ? error.context as { wb_supply_id?: unknown }
      : null
    const wbSupply = typeof context?.wb_supply_id === 'string' ? ` WB: ${context.wb_supply_id}.` : ''
    return {
      result: { status: 'pending', message: `${message}${wbSupply} Повторите проверку, чтобы прочитать фактический состав WB.` },
      keepKey: true,
    }
  }
  return { result: { status: 'failed', message }, keepKey: retryable }
}

/**
 * По очереди создаёт поставки групп, у которых ещё нет созданной поставки.
 * Каждая группа уходит своим прежним ключом; неудача одной группы не
 * останавливает остальные (R4). После прохода одним вызовом передаёт все
 * поставки, созданные именно в этой попытке, для создания сборочного задания:
 * при частичном успехе задание всё равно сохраняет успешную часть (WMS-588 R2).
 */
export async function runFbsSupplyGroupCreation(
  groups: FbsSupplyGroupDraft[],
  previous: ReadonlyMap<string, FbsGroupCreateResult>,
  keys: Map<string, string>,
  create: (group: FbsSupplyGroupDraft, idempotencyKey: string) => Promise<FbsWorkspace>,
  options: {
    newKey: () => string
    isApiError: (cause: unknown) => boolean
    onProgress?: (groupKey: string, result: FbsGroupCreateResult | 'creating') => void
    afterCreated?: (created: FbsGroupCreatedSupply[]) => Promise<void>
  },
): Promise<Map<string, FbsGroupCreateResult>> {
  const results = new Map(previous)
  const created: FbsGroupCreatedSupply[] = []
  const createOne = async (group: FbsSupplyGroupDraft) => {
    if (results.get(group.key)?.status === 'created') return
    let idempotencyKey = keys.get(group.key)
    if (!idempotencyKey) {
      idempotencyKey = options.newKey()
      keys.set(group.key, idempotencyKey)
    }
    options.onProgress?.(group.key, 'creating')
    try {
      const workspace = await create(group, idempotencyKey)
      const result: FbsGroupCreateResult = {
        status: 'created',
        supplyId: workspace.supply.id,
        name: workspace.supply.name,
        wbSupplyId: workspace.supply.wb_supply_id,
      }
      results.set(group.key, result)
      created.push({ groupKey: group.key, supplyId: result.supplyId })
      options.onProgress?.(group.key, result)
    } catch (cause) {
      const failure = fbsGroupCreateFailure(cause, options.isApiError(cause))
      if (!failure.keepKey) keys.set(group.key, options.newKey())
      results.set(group.key, failure.result)
      options.onProgress?.(group.key, failure.result)
    }
  }
  // WB limits and locks are seller-scoped. Keep each seller sequential while
  // independent sellers proceed in at most three lanes; every group keeps its
  // original idempotency key and individual recoverable result.
  const bySeller = new Map<string, FbsSupplyGroupDraft[]>()
  for (const group of groups) {
    const sellerKey = group.key.split('|')[1] ?? 'legacy'
    bySeller.set(sellerKey, [...(bySeller.get(sellerKey) ?? []), group])
  }
  const lanes = [...bySeller.values()]
  const worker = async () => {
    while (lanes.length) {
      const lane = lanes.shift()!
      for (const group of lane) await createOne(group)
    }
  }
  await Promise.all(Array.from({ length: Math.min(3, lanes.length) }, worker))
  created.sort((a, b) => groups.findIndex((group) => group.key === a.groupKey)
    - groups.findIndex((group) => group.key === b.groupKey))
  if (created.length > 0) await options.afterCreated?.(created)
  return results
}

// ── Чей это код (Д19) ─────────────────────────────────────────────────────

function sameGtin(a: string, b: string): boolean {
  const digitsA = a.trim().replace(/^0+/, '')
  const digitsB = b.trim().replace(/^0+/, '')
  return Boolean(digitsA) && digitsA === digitsB
}

/** GTIN из кода Честного знака: «01» + 14 цифр в начале или после разделителя GS. */
function gtinFromKiz(code: string): string | null {
  const cleaned = code.trim().replace(/^\][A-Za-z]\d/, '')
  // GS — разделитель групп GS1 (код 29).
  const match = cleaned.match(new RegExp(`(?:^|${String.fromCharCode(29)})01(\\d{14})`))
  return match ? match[1] : null
}

/**
 * Д19: код относится к поставке, если это ШК товара её заказа (товар заказа,
 * позиции, штрихкоды привязок маркетплейса) или ЧЗ, чей GTIN совпадает с ШК
 * товара её заказа. Стикеры заказов распознаёт сервер (lookup).
 */
export function fbsCodeBelongsToSupply(code: string, workspace: Pick<FbsWorkspace, 'orders'>): boolean {
  const value = code.trim()
  if (!value) return false
  const barcodes = new Set<string>()
  const addBindings = (bindings: Array<{ external_barcodes?: string[] }> | undefined) => {
    for (const binding of bindings ?? []) {
      for (const barcode of binding.external_barcodes ?? []) if (barcode) barcodes.add(barcode.trim())
    }
  }
  for (const order of workspace.orders) {
    if (order.product.barcode) barcodes.add(order.product.barcode.trim())
    addBindings(order.product.marketplace_bindings)
    for (const position of order.positions) {
      if (position.barcode) barcodes.add(position.barcode.trim())
      addBindings(position.marketplace_bindings)
    }
  }
  if (barcodes.has(value)) return true
  const gtin = gtinFromKiz(value)
  if (!gtin) return false
  return [...barcodes].some((barcode) => sameGtin(gtin, barcode))
}

/** Поставка группы и её товар, совпавший со сканом. */
export type GroupPickCandidate = { index: number; productId: string; planned: number; pickedTotal: number }

/**
 * Д5 при одном штрихкоде у разных товаров (разные селлеры группы): штука идёт
 * в первую по порядку поставку, которой ещё нужен именно её товар с этим ШК.
 * Если не нужен никому — первая пара, чтобы сервер ответил прежним отказом.
 */
export function pickScanCandidates(candidates: GroupPickCandidate[]): GroupPickCandidate[] {
  const ordered = candidates
    .map((candidate, position) => ({ candidate, position }))
    .sort((a, b) => a.candidate.index - b.candidate.index || a.position - b.position)
    .map(({ candidate }) => candidate)
  const needing = ordered.filter((one) => one.planned - one.pickedTotal > 0)
  if (needing.length > 0) return needing
  return ordered.slice(0, 1)
}
