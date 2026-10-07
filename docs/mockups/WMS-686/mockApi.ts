// WMS-686 · локальный API макета. Отвечает настоящим экранам WMS вымышленными
// данными из fboModel.ts. Никакого сетевого fallback: неизвестный маршрут — явный
// отказ (legacy-контракт model.test.ts C9 импортирует отсюда createMockFetch).
import {
  boxedQty, cells, closeBox, createBoxes, createFboState, isKizScan, linkKiz, linksOf, loadFboState, packUnit,
  pickUnit, pickedQty, printUnitCode, productByBarcode, productById, products, removeUnitFromBox, returnPickedUnit, saveFboState,
  setPass, setPicked, shipmentById, shipments, sourceById, sources, takeWhole, unlinkKiz, unpackUnit,
  type FboState,
} from './fboModel.ts'

export { products, shipments }

let state: FboState = createFboState()
const listeners = new Set<() => void>()
let failNextMutation = false
let activeShipment = 'demo-shipment'
export const activeShipmentId = () => activeShipment

export const isBaseline = () => typeof location !== 'undefined' && new URLSearchParams(location.search).has('baseline')
export const getFbo = () => state
export function subscribeFbo(listener: () => void) {
  listeners.add(listener)
  return () => listeners.delete(listener)
}
function commit(next: FboState) {
  state = next
  if (typeof localStorage !== 'undefined' && !isBaseline()) saveFboState(state, localStorage)
  listeners.forEach((listener) => listener())
  if (typeof window !== 'undefined') window.dispatchEvent(new Event('wms686-change'))
}
export function resetFbo() {
  commit(createFboState())
}
/** Демо-кнопка «Сбой сервера на следующем действии»: следующий изменяющий запрос получает 500. */
export function armServerFailure() {
  failNextMutation = true
}
export const serverFailureArmed = () => failNextMutation

const SELLER = { id: 'demo-seller', name: 'Демо селлер · ИП Иванов' }
export const taskIdFor = (shipmentId: string) => `pack-${shipmentId}`

export function catalogRows() {
  return products.map((product) => ({
    id: product.id, name: product.name, sku_code: product.sku, seller_name: SELLER.name,
    wb_nm_id: product.nmId, wb_vendor_code: product.vendorCode, wb_subject_name: 'Демо',
    wb_primary_image_url: null, wb_barcodes: [product.barcode], wb_primary_barcode: product.barcode,
    wb_size: product.size, wb_color: product.color, marketplaces: ['wb'],
  }))
}

const boxesOf = (shipmentId: string) => state.boxes.filter((box) => box.shipmentId === shipmentId)
const totalPicked = (shipmentId: string) => products.reduce((sum, product) => sum + pickedQty(state, shipmentId, product.id), 0)
const totalBoxed = (shipmentId: string) => products.reduce((sum, product) => sum + boxedQty(state, shipmentId, product.id), 0)

export function taskFor(shipmentId: string) {
  const shipment = shipmentById(shipmentId)
  const anyPick = totalPicked(shipmentId) > 0
  const lines = products.filter((product) => shipment.plan[product.id]).map((product, index) => {
    const picked = pickedQty(state, shipmentId, product.id)
    const boxed = boxedQty(state, shipmentId, product.id)
    const links = linksOf(state, shipmentId).filter((link) => link.productId === product.id)
    const total = anyPick ? picked : shipment.plan[product.id]
    return {
      id: `${shipmentId}-line-${index}`, product_id: product.id, seller_id: SELLER.id, seller_name: SELLER.name,
      sku_code: product.sku, product_name: product.name, size: product.size, color: product.color,
      storage_location_id: 'sorting', storage_location_code: '__SORTING__',
      packaging_instructions: 'Переклеить ШК WB поверх ШК продавца. Пакет не вскрывать.',
      requires_honest_sign: product.honestSign, qty_total: total, qty_suggested_packed: 0, qty_confirmed_packed: 0,
      qty_need_pack: total, qty_packed_in_task: boxed, qty_done: boxed,
      // R18: напечатанный при скане и отсканированный КИЗ — одна связь, считается один раз.
      qty_marking_printed: links.filter((link) => link.printed).length,
      qty_marking_external: links.filter((link) => !link.printed).length,
      qty_product_label_printed: 0, marking_available_count: product.honestSign ? 120 : 0,
      is_complete: total > 0 && boxed >= total,
    }
  })
  const done = lines.reduce((sum, line) => sum + line.qty_done, 0)
  const total = lines.reduce((sum, line) => sum + line.qty_total, 0)
  return {
    id: taskIdFor(shipmentId), document_number: `У-${shipment.number}`, display_number: `У-${shipment.number}`,
    warehouse_id: 'demo-wh', warehouse_name: 'Демо склад ФФ', seller_id: SELLER.id, seller_name: SELLER.name,
    status: 'in_progress', marketplace_unload_request_id: shipmentId, inbound_intake_request_id: null,
    is_complete: total > 0 && done >= total, pick_resync_warning: false, events: [], lines,
    created_at: '2026-10-07T09:00:00Z',
  }
}

export function detailFor(shipmentId: string) {
  const shipment = shipmentById(shipmentId)
  const task = taskFor(shipmentId)
  const pass = state.passes.find((one) => one.shipmentId === shipmentId)
  return {
    id: shipment.id, document_number: shipment.number, display_number: shipment.number,
    public_number: null, human_number: null, warehouse_id: 'demo-wh', warehouse_name: 'Демо склад ФФ',
    status: 'collecting', ff_modified: false, seller_id: SELLER.id, seller_name: SELLER.name, marketplace: 'wb',
    wb_mp_warehouse_id: shipment.wbWarehouseId, planned_shipment_date: '2026-10-10', created_at: '2026-10-06T12:00:00Z',
    lines: products.filter((product) => shipment.plan[product.id]).map((product, index) => ({
      id: `${shipmentId}-plan-${index}`, product_id: product.id, sku_code: product.sku, product_name: product.name,
      quantity: shipment.plan[product.id], picked_qty: pickedQty(state, shipmentId, product.id), has_discrepancy: false,
    })),
    boxes: boxesOf(shipmentId).map((box) => ({
      id: box.id, box_preset: '60_40_40', internal_barcode: box.code, closed_at: box.closed ? '2026-10-07T12:00:00Z' : null,
      lines: state.boxLines.filter((line) => line.boxId === box.id && line.qty > 0).map((line) => {
        const product = productById(line.productId)!
        return { id: `${box.id}-${line.productId}`, product_id: product.id, sku_code: product.sku, product_name: product.name, quantity: line.qty }
      }),
    })),
    pick_allocations: state.picks.filter((pick) => pick.shipmentId === shipmentId).map((pick, index) => {
      const product = productById(pick.productId)!
      return { id: `alloc-${index}`, product_id: product.id, sku_code: product.sku, product_name: product.name,
        storage_location_id: pick.cellId, location_code: cells.find((cell) => cell.id === pick.cellId)?.code ?? null, quantity: pick.qty }
    }),
    linked_packaging_task: { task_id: task.id, status: task.status, qty_done: totalBoxed(shipmentId), qty_total: totalPicked(shipmentId), is_complete: task.is_complete },
    pass: pass ? { filename: pass.filename, size: pass.size, content_type: pass.contentType } : null,
  }
}

function pickOptionsFor(shipmentId: string) {
  const shipment = shipmentById(shipmentId)
  return products.filter((product) => shipment.plan[product.id]).map((product) => ({
    product_id: product.id, sku_code: product.sku, product_name: product.name, seller_article: product.vendorCode,
    barcode: product.barcode, planned_qty: shipment.plan[product.id], picked_qty: pickedQty(state, shipmentId, product.id),
    boxed_qty: boxedQty(state, shipmentId, product.id),
    locations: cells.map((cell) => {
      const keys = new Map<string, { sourceId: string | null }>()
      for (const line of state.stock) if (line.productId === product.id && line.cellId === cell.id) keys.set(String(line.sourceId), { sourceId: line.sourceId })
      for (const pick of state.picks) if (pick.shipmentId === shipmentId && pick.productId === product.id && pick.cellId === cell.id) keys.set(String(pick.sourceId), { sourceId: pick.sourceId })
      const sourcesOut = [...keys.values()].map(({ sourceId }) => {
        const lying = state.stock.find((line) => line.productId === product.id && line.cellId === cell.id && line.sourceId === sourceId)?.qty ?? 0
        const taken = pickedQty(state, shipmentId, product.id, sourceId, cell.id)
        const source = sourceById(sourceId)
        return {
          quantity: lying, available: lying, picked: taken, is_loose: !source,
          known_marking_codes: source ? Object.entries(state.known).filter(([, entry]) => entry.sourceId === source.id && entry.certain).map(([cis]) => cis) : [],
          uncertain_marking_codes: source ? Object.entries(state.known).filter(([, entry]) => entry.sourceId === source.id && !entry.certain).map(([cis]) => cis) : [],
          source_label: source ? `${source.kind === 'pallet' ? 'Палета' : 'Короб'} ${source.code}` : 'Россыпью',
          container_path: source ? [{ kind: source.kind, id: source.id, code: source.code, label: `${source.kind === 'pallet' ? 'Палета' : 'Короб'} ${source.code}` }] : [],
        }
      }).filter((source) => source.quantity > 0 || source.picked > 0)
      const quantity = sourcesOut.reduce((sum, source) => sum + source.quantity, 0)
      const picked = sourcesOut.reduce((sum, source) => sum + source.picked, 0)
      return { storage_location_id: cell.id, location_code: cell.code, quantity, reserved: 0, available: quantity, picked, sources: sourcesOut }
    }).filter((location) => location.sources.length > 0),
  }))
}

function linkOut(shipmentId: string) {
  return linksOf(state, shipmentId).map((link) => ({
    marking_code_id: link.cis, cis_code: link.cis, product_id: link.productId,
    storage_location_id: link.cellId, container_id: link.sourceId, box_id: link.boxId,
    intake_document_number: link.intakeDoc, printed: link.printed, linked_seq: link.at,
  }))
}

const json = (data: unknown, status = 200) => new Response(JSON.stringify(data), { status, headers: { 'Content-Type': 'application/json' } })
const refuse = (detail: string, status = 422) => json({ detail }, status)
const ERRORS: Record<string, string> = {
  plan_limit_exceeded: 'plan_limit_exceeded',
  nothing_picked_to_pack: 'Все подобранные единицы этого товара уже упакованы — подберите ещё на вкладке «Подбор» или используйте «Наполнить».',
  unit_may_be_marked: 'Единица может быть уже с КИЗ: отсканируйте её КИЗ. Новый код из пула не выдан; единица упакована.',
  marking_pool_empty: 'В пуле нет кодов для этого товара. Единица упакована, печати нет.',
  marking_unit_ambiguous: 'У всех единиц этого товара в коробе есть КИЗ — выберите конкретный КИЗ.',
  return_place_required: 'Источник этого кода неизвестен — выберите, куда возвращаете единицу.',
  invalid_return_place: 'Можно вернуть только в источник, из которого этот товар подбирался в этой отгрузке.',
  box_empty: 'Короб уже пуст: его содержимое уже в отгрузке.',
  box_barcode_unknown: 'Короб с таким ШК не найден.',
}

type Body = Record<string, unknown>

function handleKiz(shipmentId: string, body: Body, boxId: string | null) {
  const source = typeof body.container_id === 'string' ? sourceById(body.container_id) : null
  const cellId = typeof body.storage_location_id === 'string' ? body.storage_location_id : source?.cellId ?? null
  const result = linkKiz(state, shipmentId, String(body.barcode), {
    productId: typeof body.product_id === 'string' ? body.product_id : null,
    cellId: boxId ? null : cellId, sourceId: boxId ? null : source?.id ?? null, boxId,
  }, body.printed === true)
  if (!result.ok) return refuse(result.error)
  if (!result.value.already || result.value.confirmed) commit(result.value.state)
  const link = result.value.link
  return json({
    kind: 'marking', product_id: link.productId, marking_code_id: link.cis, cis_code: link.cis,
    already_linked: result.value.already, confirmed_in_box: Boolean(result.value.confirmed), warning: result.value.warning ?? null,
    box_id: link.boxId, intake_document_number: link.intakeDoc,
    picked_qty: pickedQty(state, shipmentId, link.productId),
    allocation_quantity: link.cellId ? pickedQty(state, shipmentId, link.productId, link.sourceId, link.cellId) : null,
  })
}

function replay(mutationId: unknown, compute: () => Response): Promise<Response> | Response {
  if (typeof mutationId !== 'string') return compute()
  const saved = state.receipts[mutationId] as { status: number; body: string } | undefined
  if (saved) return new Response(saved.body, { status: saved.status, headers: { 'Content-Type': 'application/json' } })
  const response = compute()
  return response.clone().text().then((text) => {
    if (response.ok) commit({ ...state, receipts: { ...state.receipts, [mutationId]: { status: response.status, body: text } } })
    return response
  })
}

export function createMockFetch(): typeof fetch {
  return async (input, init) => {
    const raw = typeof input === 'string' ? input : input instanceof URL ? input.href : input.url
    const url = new URL(raw, 'http://wms686.local')
    const path = url.pathname
    const method = (init?.method ?? (input instanceof Request ? input.method : 'GET')).toUpperCase()
    if (url.host === '127.0.0.1:17843') return refuse('Макет: WMS Print не вызывается, задания на принтер не отправляются.', 400)
    let body: Body = {}
    if (init?.body && !(init.body instanceof FormData)) {
      try { body = JSON.parse(String(init.body)) as Body } catch { return refuse('Некорректный JSON в запросе макета', 400) }
    }
    if (method !== 'GET' && failNextMutation) {
      failNextMutation = false
      return refuse('Макет: искусственный сбой сервера (500). Ничего не сохранено — повторите действие.', 500)
    }
    if (method === 'GET' && path === '/api/products/linked-wb-catalog') return json(catalogRows())
    if (method === 'GET' && path === '/api/operations/wb-mp-warehouses') {
      return json(shipments.map((shipment) => ({ wb_warehouse_id: shipment.wbWarehouseId, name: shipment.warehouse })))
    }
    if (method === 'GET' && path === '/api/operations/marketplace-unload-requests/available-products') {
      return json(products.map((product) => ({ product_id: product.id, sku_code: product.sku, product_name: product.name,
        available: state.stock.filter((line) => line.productId === product.id).reduce((sum, line) => sum + line.qty, 0) })))
    }
    const task = /^\/api\/operations\/packaging-tasks\/(?:by-unload\/)?([^/]+)(\/complete)?$/.exec(path)
    if (task) {
      const shipmentId = shipments.find((one) => one.id === task[1] || taskIdFor(one.id) === task[1])?.id
      if (!shipmentId) return refuse('Неизвестное задание макета', 404)
      activeShipment = shipmentId
      if (task[2] && method === 'POST') {
        const current = taskFor(shipmentId)
        return current.is_complete ? json({ ...current, status: 'done' }) : refuse('Сначала упакуйте все подобранные единицы.')
      }
      if (method === 'GET') return json(taskFor(shipmentId))
    }
    const match = /^\/api\/operations\/marketplace-unload-requests\/([^/]+)(\/.*)?$/.exec(path)
    const shipmentId = match && shipments.some((one) => one.id === match[1]) ? match[1] : null
    if (!shipmentId) return refuse(`Неизвестный маршрут локального макета: ${method} ${path}`, 400)
    const rest = match![2] ?? ''
    activeShipment = shipmentId
    if (method === 'GET' && rest === '') return json(detailFor(shipmentId))
    if (method === 'PATCH' && rest === '') return json(detailFor(shipmentId))
    if (method === 'GET' && rest === '/pick-options') return json(pickOptionsFor(shipmentId))
    if (method === 'POST' && rest === '/pick/scan') {
      return replay(body.mutation_id, () => {
        const code = String(body.barcode ?? '').trim()
        const cell = cells.find((one) => one.code === code)
        if (cell) return json({ kind: 'location', storage_location_id: cell.id, location_code: cell.code })
        const source = sources.find((one) => one.code === code)
        // R1/K23 (предложение): ШК тары распознаётся и при уже выбранной таре.
        if (source) {
          const cellCode = cells.find((one) => one.id === source.cellId)!.code
          return json({ kind: 'container', storage_location_id: source.cellId, location_code: cellCode, container_kind: source.kind, container_id: source.id, container_code: source.code })
        }
        if (isKizScan(code)) return handleKiz(shipmentId, body, null)
        const product = productByBarcode(code)
        if (!product) return refuse('barcode_unknown')
        const chosen = typeof body.container_id === 'string' ? sourceById(body.container_id) : null
        let cellId = typeof body.storage_location_id === 'string' ? body.storage_location_id : chosen?.cellId ?? null
        let sourceId = chosen?.id ?? null
        if (!cellId) {
          const only = state.stock.filter((line) => line.productId === product.id && line.qty > 0)
          if (only.length !== 1) return refuse('location_required')
          cellId = only[0].cellId
          sourceId = only[0].sourceId
        }
        const result = pickUnit(state, shipmentId, product.id, cellId, sourceId)
        if (!result.ok) return refuse(result.error)
        commit(result.value)
        return json({ kind: 'product', storage_location_id: cellId, location_code: cells.find((one) => one.id === cellId)?.code,
          product_id: product.id, sku_code: product.sku, product_name: product.name,
          picked_qty: pickedQty(state, shipmentId, product.id), allocation_quantity: pickedQty(state, shipmentId, product.id, sourceId, cellId) })
      })
    }
    if (method === 'POST' && rest === '/pick/set') {
      const source = typeof body.container_id === 'string' ? sourceById(body.container_id) : null
      const result = setPicked(state, shipmentId, String(body.product_id), String(body.storage_location_id), source?.id ?? null, Number(body.quantity))
      if (!result.ok) return refuse(result.error)
      commit(result.value)
      const product = productById(String(body.product_id))!
      return json({ id: 'alloc', product_id: product.id, sku_code: product.sku, product_name: product.name,
        storage_location_id: body.storage_location_id, location_code: null, quantity: Number(body.quantity) })
    }
    if (method === 'GET' && rest === '/marking-codes') return json(linkOut(shipmentId))
    const pickReturn = /^\/marking-codes\/(.+)\/return$/.exec(rest)
    if (method === 'POST' && pickReturn) {
      return replay(body.mutation_id, () => {
        const result = returnPickedUnit(state, shipmentId, decodeURIComponent(pickReturn[1]))
        if (!result.ok) return refuse(ERRORS[result.error] ?? result.error, result.status)
        commit(result.value.state)
        return json({ returned_to: { storage_location_id: result.value.returnedTo.cellId, container_id: result.value.returnedTo.sourceId }, source_known: true })
      })
    }
    const unlink = /^\/marking-codes\/(.+)$/.exec(rest)
    if (method === 'DELETE' && unlink) {
      const result = unlinkKiz(state, shipmentId, decodeURIComponent(unlink[1]))
      if (result.removed) commit(result.state)
      return json({ removed: result.removed })
    }
    if (method === 'POST' && rest === '/boxes/batch') {
      commit(createBoxes(state, shipmentId, Math.max(1, Math.min(50, Number(body.count ?? 1)))))
      return json(detailFor(shipmentId))
    }
    if (method === 'POST' && rest === '/boxes/attach') {
      const result = takeWhole(state, shipmentId, String(body.barcode ?? ''), body.allow_over_plan === true)
      if (!result.ok) return refuse(ERRORS[result.error] ?? result.error)
      commit(result.value)
      return json(detailFor(shipmentId))
    }
    const boxScan = /^\/boxes\/([^/]+)\/scan$/.exec(rest)
    if (method === 'POST' && boxScan) {
      return replay(body.mutation_id, () => {
        const code = String(body.barcode ?? '').trim()
        if (isKizScan(code)) return handleKiz(shipmentId, body, boxScan[1])
        const product = productByBarcode(code)
        if (!product) return refuse('barcode_unknown')
        const result = packUnit(state, shipmentId, boxScan[1], product.id)
        if (!result.ok) return refuse(ERRORS[result.error] ?? result.error)
        commit(result.value)
        return json({ kind: 'product', product_id: product.id, sku_code: product.sku, product_name: product.name,
          quantity: boxedQty(state, shipmentId, product.id, boxScan[1]), picked_qty: pickedQty(state, shipmentId, product.id) })
      })
    }
    const printUnit = /^\/boxes\/([^/]+)\/print-marking$/.exec(rest)
    if (method === 'POST' && printUnit) {
      return replay(body.mutation_id, () => {
        const result = printUnitCode(state, shipmentId, printUnit[1], String(body.product_id))
        if (!result.ok) return refuse(ERRORS[result.error] ?? result.error)
        commit(result.value.state)
        return json({ marking_code_id: result.value.link.cis, cis_code: result.value.link.cis, box_id: printUnit[1] })
      })
    }
    const removeLine = /^\/boxes\/([^/]+)\/lines\/([^/]+)\/remove$/.exec(rest)
    if (method === 'POST' && removeLine) {
      return replay(body.mutation_id, () => {
        const boxId = removeLine[1]
        const productId = decodeURIComponent(removeLine[2]).slice(boxId.length + 1)
        const place = body.return_to as { storage_location_id?: string; container_id?: string | null } | undefined
        const result = removeUnitFromBox(state, shipmentId, boxId, productId, typeof body.marking_code_id === 'string' ? body.marking_code_id : null,
          place?.storage_location_id ? { cellId: place.storage_location_id, sourceId: place.container_id ?? null } : null)
        if (!result.ok) return refuse(ERRORS[result.error] ?? result.error, result.status)
        commit(result.value.state)
        return json({ returned_to: { storage_location_id: result.value.returnedTo.cellId, container_id: result.value.returnedTo.sourceId }, source_known: result.value.sourceKnown })
      })
    }
    const close = /^\/boxes\/([^/]+)\/close$/.exec(rest)
    if (method === 'POST' && close) {
      commit(closeBox(state, shipmentId, close[1]))
      return json(detailFor(shipmentId))
    }
    const unpack = /^\/boxes\/([^/]+)\/unpack-last$/.exec(rest)
    if (method === 'POST' && unpack) {
      commit(unpackUnit(state, shipmentId, unpack[1], String(body.product_id)))
      return json(detailFor(shipmentId))
    }
    if (method === 'PUT' && rest === '/pass') {
      const file = init?.body instanceof FormData ? init.body.get('file') : null
      if (!(file instanceof File)) return refuse('Выберите файл пропуска')
      const dataUrl = await new Promise<string>((resolve) => {
        const reader = new FileReader()
        reader.onload = () => resolve(String(reader.result))
        reader.readAsDataURL(file)
      })
      commit(setPass(state, { shipmentId, filename: file.name, size: file.size, contentType: file.type || 'application/octet-stream', dataUrl }))
      return json({ filename: file.name, content_type: file.type, size: file.size })
    }
    if (method === 'GET' && rest === '/pass') {
      const pass = state.passes.find((one) => one.shipmentId === shipmentId)
      return pass ? json({ filename: pass.filename, size: pass.size, content_type: pass.contentType, data_url: pass.dataUrl }) : refuse('Пропуск не прикреплён', 404)
    }
    if (method === 'GET' && rest === '/wb-fbw-packaging.xlsx') {
      return refuse('Макет: XLSX не формируется. В рабочем WMS колонки прежние (Баркод товара, Кол-во товаров, ШК короба); короб, взятый целиком, идёт со своим ШК — например INB-DEMO-001.')
    }
    if (method === 'POST' && (rest === '/ship' || rest === '/cancel')) {
      return refuse('Макет: документ не проводится и не отменяется. Списание остатка — только при «Завершить» в рабочем WMS.', 400)
    }
    return refuse(`Неизвестный маршрут локального макета: ${method} ${path}`, 400)
  }
}

export function installMockApi() {
  if (typeof localStorage !== 'undefined' && !isBaseline()) {
    const params = new URLSearchParams(location.search)
    if (params.has('reset')) {
      localStorage.removeItem('wms686-fbo-v2')
      params.delete('reset')
      history.replaceState(null, '', `?${params.toString()}`)
    }
    state = loadFboState(localStorage)
  }
  globalThis.fetch = createMockFetch()
}
