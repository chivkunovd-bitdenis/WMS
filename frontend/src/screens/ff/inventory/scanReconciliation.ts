import type { ContainerKind, InventoryCount, InventoryNode, ProductNode } from './InventoryTypes'
import { allProducts, setActual } from './InventoryRows'

// Ревью Astra №1 (26.09.2026, docs/reviews/artifacts/wms-542/review-astra-1.md):
// смешение ручного ввода, оптимистичного прироста скана на экране и сетевых
// ответов позволяло завысить счёт и стереть чужие сканы (F1), теряло ручную
// правку другой строки, сделанную пока летит PUT скана (F2), и позволяло
// запоздалому ответу «Сохранить» откатить уже подтверждённый сканом счёт (F3).
//
// Корень всех трёх — скан тянул за собой абсолютный PUT из общего снимка
// документа, а подтверждение этого PUT решало «что ещё тронуто» разницей по
// ВСЕМ строкам сразу. Модуль ниже полностью разделяет два независимых слоя:
//
//   * РУЧНАЯ ПРАВКА — то, что оператор набрал руками в поле числа. Живёт в
//     `manual`, по одной записи на строку, с версией (растёт на каждый ввод).
//     Скан НИКОГДА не читает и не пишет эту карту как «тронуто вообще» —
//     только явно спрашивает `planScanFlush`, нужно ли сперва сохранить её.
//   * СКАН — работает только через POST /found (+1 на сервере, идемпотентно
//     по scan_id, под блокировкой документа — см. backend record_found).
//     Если у строки есть несохранённая ручная правка, её значение сначала
//     кладут ЦЕЛЕВЫМ PUT одной строки (`planScanFlush` → `confirmManualFlush`)
//     — без оптимистичных +1 сверху, — и только потом шлют POST. Повтор
//     скана после потери ответа НЕ повторяет уже подтверждённый PUT: как
//     только `confirmManualFlush` снял правку по совпавшей версии, следующий
//     `planScanFlush` для той же строки сам вернёт null, без отдельного
//     флага «шаг сделан» на элементе очереди.
//
// Отображаемое число строки — это ВСЕГДА «база + неподтверждённые локальные
// сканы» (`pendingScans`): базу даёт либо несохранённая ручная правка, либо
// последнее подтверждённое сервером значение. Applying любого ответа
// (скан, PUT ручной правки, «Сохранить») ограничено СКОПОМ — множеством
// строк, которых этот конкретный запрос реально касался — и для каждой такой
// строки кладёт СЕРВЕРНОЕ число ПЛЮС то, что ещё числится в pendingScans на
// эту строку (сканы, которые сам этот ответ не мог знать). Для всех
// остальных строк документа ответ не значит ничего: экран остаётся таким,
// каким был. Пустой скоп (например, «Сохранить» без несохранённых правок)
// не трогает вообще ничего — так поздний ответ такого запроса не может
// откатить то, что уже подтвердил более ранний по применению ответ скана
// (F3): он просто не авторитетен ни для одной строки документа.

/** Несохранённая ручная правка одной строки и её порядковый номер. */
export type ManualEdit = { value: number | null; version: number }

/** Состояние сверки экрана с сервером для одного документа. */
export type ScanSyncState = {
  count: InventoryCount
  /** lineId → несохранённая ручная правка. Скан сюда никогда не пишет. */
  manual: ReadonlyMap<string, ManualEdit>
  /**
   * lineId → сколько локальных «+1» от сканов уже нарисовано на экране, но
   * ответ на них ещё не применён. Только для строк, уже известных на
   * экране — у настоящей находки (строки ещё нет) сканов не считаем: она
   * не сравнивается с прежним локальным числом, а вставляется ответом сервера.
   */
  pendingScans: ReadonlyMap<string, number>
}

export function initSyncState(count: InventoryCount): ScanSyncState {
  return { count, manual: new Map(), pendingScans: new Map() }
}

/**
 * Применяет ответ сервера к строкам из `overlay`: число строки становится
 * «серверное значение из этого ответа + overlay.get(id)» (обычно — сколько
 * ещё непогашенных локальных сканов на неё числится). Все строки документа,
 * которых нет в `overlay`, остаются такими, какими их видит экран сейчас —
 * этот ответ для них не авторитетен, даже если сервер прислал по ним другие
 * числа (например, полный снимок документа со сканом другого оператора).
 *
 * Строка, которой нет на экране, но есть в `server` (настоящая находка,
 * только что созданная сервером), просто появляется — `merged` изначально
 * есть `server`, а цикл ниже трогает только то, что уже было на экране.
 */
export function applyAuthoritative(
  server: InventoryCount,
  current: InventoryCount,
  overlay: ReadonlyMap<string, number>,
): InventoryCount {
  if (current.id !== server.id) return current
  const serverValues = new Map(allProducts(server).map((item) => [item.id, item.actual]))
  let merged = server
  for (const item of allProducts(current)) {
    if (!overlay.has(item.id)) {
      merged = setActual(merged, item.id, item.actual)
      continue
    }
    const base = serverValues.get(item.id) ?? null
    const extra = overlay.get(item.id) ?? 0
    merged = setActual(merged, item.id, extra === 0 ? base : (base ?? 0) + extra)
  }
  return merged
}

/** Оператор вручную ввёл число — отдельный от сканов слой, своя версия правки. */
export function recordManualEdit(
  state: ScanSyncState,
  lineId: string,
  value: number | null,
): ScanSyncState {
  const version = (state.manual.get(lineId)?.version ?? 0) + 1
  const manual = new Map(state.manual)
  manual.set(lineId, { value, version })
  return { ...state, manual, count: setActual(state.count, lineId, value) }
}

/**
 * Мгновенный локальный прирост от скана уже известной строки — рисуется на
 * экране сразу, до всякого ответа сервера. Только для строк, у которых уже
 * есть id на экране (не для настоящей находки).
 */
export function applyLocalScanBump(state: ScanSyncState, lineId: string): ScanSyncState {
  const item = allProducts(state.count).find((p) => p.id === lineId)
  const now = (item?.actual ?? 0) + 1
  const pendingScans = new Map(state.pendingScans)
  pendingScans.set(lineId, (pendingScans.get(lineId) ?? 0) + 1)
  return { ...state, pendingScans, count: setActual(state.count, lineId, now) }
}

/**
 * Нужно ли перед POST-сканом строки сперва сохранить несохранённую ручную
 * правку — и каким значением. `null` — сохранять нечего, скан идёт прямо в
 * POST. Значение и версия читаются из `manual` в момент вызова: если правку
 * уже сохранил предыдущий скан этой же строки (стоявший в очереди раньше),
 * здесь будет `null`, и повторный PUT не отправится.
 */
export function planScanFlush(state: ScanSyncState, lineId: string): ManualEdit | null {
  return state.manual.get(lineId) ?? null
}

/**
 * Применяет ответ на целевой PUT одной строки (введённое оператором число,
 * без оптимистичных сканов сверху). Снимает флаг ручной правки, только если
 * это ТА ЖЕ версия, что отправляли: правка, сделанная уже ПОСЛЕ отправки
 * (пока PUT летел), сохраняется и будет отправлена следующим шагом отдельно
 * (F2) — сюда мы просто не заходим, версия не совпадёт.
 */
export function confirmManualFlush(
  state: ScanSyncState,
  lineId: string,
  sentVersion: number,
  serverAfterPut: InventoryCount,
): ScanSyncState {
  const stillPending = state.manual.get(lineId)
  if (stillPending === undefined || stillPending.version !== sentVersion) return state
  const manual = new Map(state.manual)
  manual.delete(lineId)
  const overlay = new Map([[lineId, state.pendingScans.get(lineId) ?? 0]])
  return { ...state, manual, count: applyAuthoritative(serverAfterPut, state.count, overlay) }
}

/**
 * Применяет ответ на POST /found одного скана: серверное число — для ЭТОЙ
 * строки (плюс то, что ещё не погашено другими её сканами), остальной
 * документ не трогаем. Снимает один локальный «+1» — ровно тот, что этот
 * скан нарисовал сам.
 */
export function applyScanResponse(
  state: ScanSyncState,
  lineId: string,
  serverAfterPost: InventoryCount,
): ScanSyncState {
  const pendingScans = new Map(state.pendingScans)
  const left = Math.max((pendingScans.get(lineId) ?? 0) - 1, 0)
  if (left > 0) pendingScans.set(lineId, left)
  else pendingScans.delete(lineId)
  const overlay = new Map([[lineId, left]])
  return { ...state, pendingScans, count: applyAuthoritative(serverAfterPost, state.count, overlay) }
}

/**
 * Применяет ответ «Сохранить»: серверное число — только для строк, реально
 * отправленных в ЭТОМ PUT (`sentVersions`, читается из `manual` в момент
 * отправки — сам скан там никогда не значится). Пустой набор (нет
 * несохранённых правок) не меняет ни одной строки. Снимает флаг ручной
 * правки только у тех строк и тех версий, что реально ушли — правка,
 * сделанная уже после отправки (та же гонка, что в confirmManualFlush),
 * версией не совпадёт и останется несохранённой для следующего «Сохранить».
 */
export function applySaveResponse(
  state: ScanSyncState,
  sentVersions: ReadonlyMap<string, number>,
  serverAfterSave: InventoryCount,
): ScanSyncState {
  const manual = new Map(state.manual)
  for (const [lineId, version] of sentVersions) {
    const stillPending = manual.get(lineId)
    if (stillPending !== undefined && stillPending.version === version) manual.delete(lineId)
  }
  const overlay = new Map(
    [...sentVersions.keys()].map((id) => [id, state.pendingScans.get(id) ?? 0]),
  )
  return { ...state, manual, count: applyAuthoritative(serverAfterSave, state.count, overlay) }
}

type ScanPlace = {
  cellId: string | null
  containerKind: ContainerKind | null
  containerId: string | null
}

/** ШК WB — основной код, SKU — код на внутренней этикетке при отсутствии ШК WB. */
function matchesCodes(product: ProductNode, normalized: Set<string>): boolean {
  return [product.barcode, product.wbBarcode, product.sku].some((value) => {
    const lowered = value?.trim().toLowerCase()
    return Boolean(lowered && normalized.has(lowered))
  })
}

/**
 * Находит в ответе сервера строку, которой касался скан без заранее
 * известного line_id — настоящая находка. Ищем строго по тому же адресу,
 * что отправляли (тара или ячейка), а внутри него — товар, совпавший по
 * коду: тот же контракт, что резолвит сам сервер в record_found, только по
 * уже пришедшему дереву, без второго похода в сеть.
 */
export function findScannedLineId(
  server: InventoryCount,
  place: ScanPlace,
  codes: string[],
): string | undefined {
  const normalized = new Set(codes.map((code) => code.trim().toLowerCase()))
  if (place.containerId) {
    let found: string | undefined
    const walk = (nodes: InventoryNode[]): void => {
      for (const node of nodes) {
        if (node.kind === 'product') continue
        if (node.id === place.containerId) {
          const hit = node.children.find(
            (child): child is ProductNode => child.kind === 'product' && matchesCodes(child, normalized),
          )
          found = hit?.id
          return
        }
        walk(node.children)
      }
    }
    for (const cell of server.cells) walk(cell.children)
    return found
  }
  const targetCellId = place.cellId ?? 'unassigned'
  const cell =
    server.cells.find((item) => item.id === targetCellId) ??
    // Адресное хранение выключено — единственная техническая обёртка «inventory».
    server.cells.find((item) => item.id === 'inventory')
  if (!cell) return undefined
  const hit = cell.children.find(
    (child): child is ProductNode => child.kind === 'product' && matchesCodes(child, normalized),
  )
  return hit?.id
}
