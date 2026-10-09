// @vitest-environment jsdom
import { act } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from 'vitest'
import { FfUnloadPickPage } from './FfUnloadPickPage'

// База контракта: a6cdddb021872f59807509d2ade266e55ddfaaac, чистое дерево.
// Среда: подключённые node_modules, Vitest/jsdom; иных известных красных
// адресных проверок до этого этапа не зафиксировано, общий suite не запускался.
// До реализации C1–C15 красные из-за отсутствия кнопки/галок; последующие
// шаги этих сценариев заблокированы этой предпосылкой, а не приняты.
// C16 WB/Ozon зелёные. Обе проверки ловят три временные порчи FfUnloadPickPage:
// isFbo=true, scan container_id=null, set quantity=payload.quantity+1.
// Каждая порча дала содержательные 2/2 падения; продуктовый файл восстановлен
// побайтно и проверен git diff. Commit/push выполняет ведущий.
// WMS-731: настоящий экран, настоящие преобразования pick-options и подготовка HTML.
// Подменены только HTTP и окно/iframe браузерной печати. Никаких mock экрана,
// генератора листа, состояния галок или модели выбранных строк.
// Новый UI ищется по тексту действия и checkbox в существующей строке дерева;
// новые data-testid и новые экспорты продуктового кода контракт не навязывает.
const A = 'doc-731-a'
const B = 'doc-731-b'
const NAME = 'Футболка хлопковая с очень длинным названием для проверки состава листа'
const PRODUCTS = [
  { id: 'p-a', sku: 'SKU-A', name: NAME, size: '48', barcode: '4600000000011', plan: 10 },
  { id: 'p-b', sku: 'SKU-B', name: NAME, size: '50', barcode: '4600000000028', plan: 3 },
  { id: 'p-none', sku: 'SKU-NONE', name: 'Товар без мест', size: null, barcode: '4600000000035', plan: 2 },
]
type Source = { product: string; cellId: string; cell: string; path: Array<{ kind: 'box' | 'pallet'; id: string; code: string; label: string }>; qty: number; available: number; picked: number }
type Call = { method: string; path: string; body: Record<string, unknown> | null }
const box = (id: string, code: string) => ({ kind: 'box' as const, id, code, label: `Короб ${code}` })
const pallet = { kind: 'pallet' as const, id: 'pallet', code: 'PAL-731', label: 'Палета PAL-731' }
function sources(): Source[] {
  const one = (cellId: string, cell: string, path: Source['path'], qty: number, product = 'p-a', picked = 0, available = qty): Source =>
    ({ product, cellId, cell, path, qty, picked, available })
  return [
    one('a1', 'А1', [box('b11', 'BOX-11')], 12, 'p-a', 4, 7),
    one('a1', 'А1', [box('b12', 'BOX-12')], 13),
    one('a1', 'А1', [], 14),
    one('a2', 'А2', [box('b21', 'BOX-21')], 15),
    one('a2', 'А2', [box('b22', 'BOX-22')], 16),
    one('a3', 'А3', [box('b31', 'BOX-31')], 17),
    one('a2', 'А2', [pallet], 18),
    one('a2', 'А2', [pallet, box('nested', 'BOX-NESTED')], 19),
    one('sorting', 'Без ячеек', [box('unlocated', 'BOX-NO-CELL')], 20),
    one('a1', 'А1', [box('b11', 'BOX-11')], 21, 'p-b'),
  ]
}
function fakeServer() {
  const calls: Call[] = []
  const unexpected: string[] = []
  const docs = new Map([A, B].map((id) => [id, {
    id, marketplace: 'wb' as 'wb' | 'ozon', seller: id === A ? 'Селлер A' : 'Селлер B',
    number: id === A ? '000731-A' : '000731-B', sources: sources(), products: structuredClone(PRODUCTS),
    failOptions: false,
  }]))
  // B имеет те же видимые адреса/номера, но иные реальные идентификаторы.
  for (const source of docs.get(B)!.sources) {
    source.cellId = `other-${source.cellId}`
    source.path = source.path.map((step) => ({ ...step, id: `other-${step.id}` }))
  }
  const options = (id: string) => {
    const doc = docs.get(id)!
    return doc.products.map((product) => {
      const productSources = doc.sources.filter((source) => source.product === product.id)
      const cellIds = [...new Set(productSources.map((source) => source.cellId))]
      return {
        product_id: product.id, sku_code: product.sku, product_name: product.name,
        seller_article: null, barcode: product.barcode, planned_qty: product.plan,
        picked_qty: productSources.reduce((sum, source) => sum + source.picked, 0),
        locations: cellIds.map((cellId) => {
          const rows = productSources.filter((source) => source.cellId === cellId)
          return {
            storage_location_id: cellId, location_code: rows[0].cell,
            quantity: rows.reduce((sum, source) => sum + source.qty, 0), reserved: 0,
            available: rows.reduce((sum, source) => sum + source.available, 0),
            picked: rows.reduce((sum, source) => sum + source.picked, 0),
            sources: rows.map((source) => ({
              quantity: source.qty, available: source.available, picked: source.picked,
              is_loose: source.path.length === 0, source_label: source.path.at(-1)?.label ?? 'Россыпью',
              container_path: source.path,
            })),
          }
        }),
      }
    })
  }
  const detail = (id: string, fbs: boolean) => {
    const doc = docs.get(id)!
    return {
      id, marketplace: doc.marketplace, display_number: doc.number, document_number: doc.number,
      name: `Документ ${doc.number}`, status: fbs ? 'picking' : 'collecting',
      seller_id: `seller-${id}`, seller_name: doc.seller, planned_shipment_date: null,
      warehouse_name: 'Склад теста', boxed_qty: 1,
      ...(fbs ? {} : { lines: options(id).map((product) => ({
        id: `line-${product.product_id}`, product_id: product.product_id,
        sku_code: product.sku_code, product_name: product.product_name,
        quantity: product.planned_qty, picked_qty: product.picked_qty,
        boxed_qty: 1, requires_honest_sign: true,
      })) }),
    }
  }
  const json = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } })
  const handle = async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = new URL(typeof input === 'string' ? input : input instanceof URL ? input.href : input.url, 'http://wms.test')
    const path = url.pathname.replace(/^\/api/, '')
    const method = (init?.method ?? 'GET').toUpperCase()
    const body = typeof init?.body === 'string' ? JSON.parse(init.body) as Record<string, unknown> : null
    calls.push({ method, path, body })
    if (path === '/products/linked-wb-catalog') return json(PRODUCTS.map((p) => ({
      id: p.id, name: p.name, sku_code: p.sku, wb_nm_id: null, wb_vendor_code: `ART-${p.sku}`,
      wb_primary_image_url: null, wb_barcodes: [p.barcode], wb_primary_barcode: p.barcode,
      wb_size: p.size, wb_color: null, wb_subject_name: null,
    })))
    const match = /^\/operations\/(marketplace-unload-requests|fbs-supplies)\/([^/]+)(.*)$/.exec(path)
    if (!match || !docs.has(match[2])) { unexpected.push(`${method} ${path}`); return json({ detail: 'unexpected request' }, 404) }
    const [, base, id, suffix] = match
    const doc = docs.get(id)!
    if (method === 'GET' && suffix === '') return json(detail(id, base === 'fbs-supplies'))
    if (method === 'GET' && suffix === '/pick-options') return doc.failOptions
      ? json({ detail: 'Не удалось загрузить места подбора' }, 503) : json(options(id))
    if (method === 'GET' && suffix === '/marking-codes') return json({ items: [] })
    if (method === 'POST' && suffix === '/pick/scan' && body) {
      const barcode = String(body.barcode)
      const cell = doc.sources.find((source) => source.cell === barcode || `LOC-${source.cell}` === barcode)
      const source = doc.sources.find((source) => source.path.at(-1)?.code === barcode)
      if (cell || source) return json({
        kind: cell ? 'location' : 'container', storage_location_id: (cell ?? source)!.cellId,
        location_code: (cell ?? source)!.cell, container_kind: source?.path.at(-1)?.kind ?? null,
        container_id: source?.path.at(-1)?.id ?? null, container_code: source?.path.at(-1)?.code ?? null,
        product_id: null, sku_code: null, product_name: null, picked_qty: null, allocation_quantity: null,
      })
      const product = doc.products.find((p) => p.barcode === barcode)
      const pickedFrom = doc.sources.find((s) => s.product === product?.id && s.cellId === body.storage_location_id &&
        (body.container_id ? s.path.at(-1)?.id === body.container_id : s.path.length === 0))
      if (!product || !pickedFrom) return json({ detail: 'В выбранном источнике нет товара' }, 422)
      pickedFrom.picked += 1
      pickedFrom.qty -= 1
      pickedFrom.available -= 1
      return json({ kind: 'product', product_id: product.id, sku_code: product.sku, product_name: product.name,
        storage_location_id: pickedFrom.cellId, location_code: pickedFrom.cell,
        picked_qty: doc.sources.filter((s) => s.product === product.id).reduce((sum, s) => sum + s.picked, 0),
        allocation_quantity: pickedFrom.picked, container_kind: pickedFrom.path.at(-1)?.kind ?? null,
        container_id: pickedFrom.path.at(-1)?.id ?? null, container_code: pickedFrom.path.at(-1)?.code ?? null,
      })
    }
    if (method === 'POST' && suffix === '/pick/set' && body) {
      const source = doc.sources.find((s) => s.product === body.product_id && s.cellId === body.storage_location_id &&
        (body.container_id ? s.path.at(-1)?.id === body.container_id : s.path.length === 0))
      if (!source) return json({ detail: 'source not found' }, 422)
      const delta = Number(body.quantity) - source.picked
      source.picked += delta; source.qty -= delta; source.available -= delta
      return json({ ok: true, unlinked_marking_codes: [] })
    }
    unexpected.push(`${method} ${path}`)
    return json({ detail: 'unexpected operation' }, 404)
  }
  return { calls, unexpected, docs, handle, options, detail }
}

let host: HTMLDivElement
let root: Root
let server: ReturnType<typeof fakeServer>
let currentId: string
let currentSource: 'fbs' | undefined
let printFrames: HTMLIFrameElement[]
let captured: string[]
let failPrint: boolean
let printed: ReturnType<typeof vi.fn>
let clockShift: number
const originalFetch = globalThis.fetch
beforeAll(() => { (globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true })
beforeEach(() => {
  server = fakeServer(); currentId = A; currentSource = undefined
  captured = []; printFrames = []; failPrint = false; clockShift = 0; printed = vi.fn()
  const now = performance.now.bind(performance)
  vi.spyOn(performance, 'now').mockImplementation(() => now() + clockShift)
  globalThis.fetch = server.handle as typeof fetch
  window.sessionStorage.clear()
  host = document.createElement('div'); document.body.appendChild(host); root = createRoot(host)
  // Оба штатных пути: popup с document.write и скрытый iframe с srcdoc.
  // Документы HTML настоящие; диалог ОС заменён отменой пользователем.
  const createElement = document.createElement.bind(document)
  vi.spyOn(document, 'createElement').mockImplementation(((tag: string, options?: ElementCreationOptions) => {
    if (tag.toLowerCase() === 'iframe' && failPrint) throw new Error('Не удалось открыть печать')
    const element = createElement(tag, options)
    if (tag.toLowerCase() === 'iframe') printFrames.push(element as HTMLIFrameElement)
    return element
  }) as typeof document.createElement)
  const appendChild = document.body.appendChild.bind(document.body)
  vi.spyOn(document.body, 'appendChild').mockImplementation(((node: Node) => {
    const added = appendChild(node)
    if (node instanceof HTMLIFrameElement && node.contentWindow) {
      const w = node.contentWindow
      // Перехват сразу при вставке, до onload: иначе jsdom успевает вызвать
      // своё неисполненное window.print до установки границы теста.
      vi.spyOn(w, 'focus').mockImplementation(() => undefined)
      vi.spyOn(w, 'print').mockImplementation(() => { printed(); w.dispatchEvent(new Event('afterprint')) })
    }
    return added
  }) as typeof document.body.appendChild)
  vi.spyOn(window, 'open').mockImplementation(() => {
    if (failPrint) return null
    const frame = createElement('iframe'); document.body.appendChild(frame); printFrames.push(frame)
    const popup = frame.contentWindow!
    return popup
  })
  vi.spyOn(window, 'print').mockImplementation(() => { printed(); window.dispatchEvent(new Event('afterprint')) })
})
afterEach(() => {
  act(() => root.unmount())
  host.remove(); printFrames.forEach((frame) => frame.remove())
  globalThis.fetch = originalFetch
  vi.restoreAllMocks()
})
const q = (id: string) => host.querySelector<HTMLElement>(`[data-testid="${id}"]`)
const text = (element: Element | null) => (element?.textContent ?? '').replace(/\s+/g, ' ').trim()
async function settle() {
  for (let i = 0; i < 6; i++) await act(async () => { await new Promise((resolve) => setTimeout(resolve, 0)) })
}
async function click(element: Element | null, reason = 'существующее действие') {
  expect(element, reason).not.toBeNull()
  await act(async () => (element as HTMLElement).click()); await settle()
}
function button(label: string | RegExp) {
  return [...host.querySelectorAll('button, [role="button"]')].find((b) => typeof label === 'string'
    ? text(b) === label || b.getAttribute('aria-label') === label || b.getAttribute('title') === label
    : label.test(text(b))) ?? null
}
async function mount(id = currentId, source = currentSource, token = 't') {
  currentId = id; currentSource = source
  await act(async () => root.render(<MemoryRouter><FfUnloadPickPage token={token} requestId={id} source={source} hideHeader /></MemoryRouter>))
  await settle()
}
async function remount() {
  await act(async () => root.render(<div>Упаковка</div>)); await settle()
  await mount()
}
async function reload() {
  // Новый React root при том же sessionStorage имитирует обновление браузерной вкладки.
  act(() => root.unmount()); root = createRoot(host); await mount()
}
async function view(kind: 'cells' | 'products') { await click(q(`pick-view-${kind}`)) }
async function expandProduct(product = 'p-a') { await click(q(`pick-table-expand-line-${product}`)) }
function cellRow(id: string) { return q(`fbs-pick-item-cell:${id}`)?.closest('tr') ?? null }
function objectRow(id: string) { return q(`fbs-pick-item-obj:${id}`)?.closest('tr') ?? null }
function productPlaceRow(label: string, product = 'p-a') {
  return [...(q(`pick-places-${product}`)?.querySelectorAll('tr') ?? [])].find((row) =>
    [...row.querySelectorAll('td')].some((td) => text(td).includes(label))) ?? null
}
function checkbox(row: Element | null) {
  expect(row, 'строка существующего дерева').not.toBeNull()
  const check = row!.querySelector<HTMLInputElement>('input[type="checkbox"]')
  expect(check, 'галка выбора строки для печати FBO').not.toBeNull()
  return check!
}
async function choose(row: Element | null, checked = true) {
  const check = checkbox(row)
  if (check.checked !== checked) await click(check)
  expect(check.checked).toBe(checked)
}
async function chooseProducts() {
  await view('products'); await expandProduct()
  await choose(productPlaceRow('BOX-11')); await choose(productPlaceRow('BOX-22'))
}
async function scan(code: string) {
  clockShift += 3000
  act(() => {
    if (document.activeElement instanceof HTMLElement) document.activeElement.blur()
    for (const key of [...code, 'Enter']) document.body.dispatchEvent(new KeyboardEvent('keydown', { key, bubbles: true, cancelable: true }))
  })
  await settle()
}
async function printSheet() {
  const start = printFrames.length
  const printsBefore = printed.mock.calls.length
  const printButton = button('Печать листа подбора')
  expect(printButton, 'R1: кнопка печати на вкладке подбора FBO').not.toBeNull()
  expect((printButton as HTMLButtonElement).disabled).toBe(false)
  await click(printButton)
  // jsdom не загружает srcdoc автоматически. Исполняем лишь событие загрузки
  // подготовленного документа, не заменяя обработчик/генератор печати.
  for (const frame of printFrames.slice(start)) {
    const w = frame.contentWindow
    if (!w) continue
    if (!vi.isMockFunction(w.print)) vi.spyOn(w, 'print').mockImplementation(() => { printed(); w.dispatchEvent(new Event('afterprint')) })
    if (!vi.isMockFunction(w.focus)) vi.spyOn(w, 'focus').mockImplementation(() => undefined)
    const html = frame.srcdoc || frame.contentDocument?.documentElement.outerHTML || ''
    captured.push(html)
    await act(async () => frame.dispatchEvent(new Event('load')))
  }
  await act(async () => { await new Promise((resolve) => setTimeout(resolve, 150)) })
  expect(printFrames.length, 'новое действие готовит собственный лист').toBeGreaterThan(start)
  const html = captured.at(-1)
  expect(html, 'печать должна подготовить настоящий HTML листа').toBeTruthy()
  const doc = new DOMParser().parseFromString(html!, 'text/html')
  expect(doc.querySelector('table'), 'лист подбора — таблица').not.toBeNull()
  expect(printed.mock.calls.length, 'подготовленный лист открывает штатную печать').toBeGreaterThan(printsBefore)
  return doc
}
// Нормализуем rowspan/colspan: контракт о данных, а не о конкретной разметке.
function tableGrid(table: HTMLTableElement) {
  const grid: string[][] = []
  Array.from(table.rows).forEach((row, r) => {
    grid[r] ??= []; let c = 0
    for (const cell of Array.from(row.cells)) {
      while (grid[r][c] !== undefined) c++
      for (let dr = 0; dr < cell.rowSpan; dr++) for (let dc = 0; dc < cell.colSpan; dc++) {
        grid[r + dr] ??= []; grid[r + dr][c + dc] = text(cell)
      }
      c += cell.colSpan
    }
  })
  return grid
}
type PrintedRow = { product: string; size: string; cell: string; container: string; qty: number; plan: number; left: number }
function rowsOf(doc: Document): PrintedRow[] {
  const result: PrintedRow[] = []
  for (const table of doc.querySelectorAll('table')) {
    const grid = tableGrid(table)
    const headers = grid[0] ?? []
    const col = (pattern: RegExp) => headers.findIndex((header) => pattern.test(header))
    const product = col(/Товар|Название|Наименование/i), cell = col(/Ячейк/i), container = col(/Короб|Тара/i)
    const qty = col(/Количество|Лежит|Остаток/i), plan = col(/^План/i), left = col(/Осталось/i), size = col(/Размер/i)
    expect([product, cell, container, qty, plan, left], 'таблица явно различает товар, адрес, тару, физическое количество, план и осталось').not.toContain(-1)
    for (const row of grid.slice(1)) {
      if (!PRODUCTS.some((p) => row[product]?.includes(p.sku)) || !/^\d+$/.test(row[qty] ?? '')) continue
      result.push({ product: row[product], size: size >= 0 ? row[size] : '', cell: row[cell], container: row[container], qty: Number(row[qty]), plan: Number(row[plan]), left: Number(row[left]) })
    }
  }
  return result
}
function key(row: PrintedRow) {
  const product = PRODUCTS.find((p) => row.product.includes(p.sku))!
  return `${product.id}|${row.cell}|${row.container}|${row.qty}`
}
function expectSources(doc: Document, selected = server.docs.get(currentId)!.sources) {
  const actual = rowsOf(doc)
  expect(actual).toHaveLength(selected.length)
  for (const source of selected) {
    const product = PRODUCTS.find((p) => p.id === source.product)!
    const found = actual.filter((row) => row.product.includes(product.sku) && row.cell.includes(source.cell) &&
      (source.path.length ? source.path.every((step) => row.container.includes(step.code)) : /Россыпью/i.test(row.container)))
    expect(found, `${product.sku}: ${source.cell}, ${source.path.map((s) => s.code).join(' → ') || 'Россыпью'}`).toHaveLength(1)
    expect(found[0].qty).toBe(source.qty)
  }
  return actual
}
function expectHeader(doc: Document, id = currentId) {
  const data = server.docs.get(id)!
  expect(text(doc.body)).toContain(data.number); expect(text(doc.body)).toContain(data.seller)
  expect(text(doc.body)).toMatch(data.marketplace === 'wb' ? /WB|Wildberries|Вайлдберриз/i : /Ozon|Озон/i)
}
const writeCalls = () => server.calls.filter((call) => !['GET', 'HEAD'].includes(call.method))

describe('WMS-731 · контракт листа подбора FBO', () => {
  it('C1 full product sheet contains shipment header and every plan source', async () => {
    await mount(); await view('products')
    const doc = await printSheet(); expectHeader(doc); expectSources(doc)
    const headers = [...doc.querySelectorAll('thead th')].map(text).join('|')
    expect(headers.indexOf('Товар')).toBeLessThan(headers.indexOf('Ячейк'))
    expect(headers.indexOf('Ячейк')).toBeLessThan(headers.search(/Короб|Тара/))
    expect(text(doc.body)).toContain('SKU-NONE'); expect(text(doc.body)).toMatch(/Нет на складе/i)
    const sameNameRows = rowsOf(doc).filter((row) => row.product.includes(NAME))
    expect(sameNameRows.some((row) => row.product.includes('SKU-A') && /\b48\b/.test(`${row.product} ${row.size}`))).toBe(true)
    expect(sameNameRows.some((row) => row.product.includes('SKU-B') && /\b50\b/.test(`${row.product} ${row.size}`))).toBe(true)
  })
  it('C2 default cell sheet preserves source set quantities and tree order', async () => {
    await mount(); expect(q('fbs-cell-pick-table')).not.toBeNull()
    const cells = await printSheet(); expectHeader(cells)
    const cellRows = expectSources(cells)
    // Порядок данных существующего дерева: адрес, затем внешний/вложенный источник.
    const at = (code: string) => cellRows.findIndex((row) => row.cell.includes(code))
    expect(at('А1')).toBeLessThan(at('А2')); expect(at('А2')).toBeLessThan(at('А3'))
    const direct = cellRows.findIndex((row) => row.container.includes('PAL-731') && !row.container.includes('BOX-NESTED'))
    const nested = cellRows.findIndex((row) => row.container.includes('BOX-NESTED'))
    expect(direct).toBeLessThan(nested)
    const headers = [...cells.querySelectorAll('thead th')].map(text).join('|')
    expect(headers.indexOf('Ячейк')).toBeLessThan(headers.search(/Короб|Тара/))
    expect(headers.search(/Короб|Тара/)).toBeLessThan(headers.indexOf('Товар'))
    await view('products'); const products = await printSheet()
    expect(rowsOf(products).map(key).sort()).toEqual(cellRows.map(key).sort())
  })
  it('C3 product checkboxes select two sources without sibling products or boxes', async () => {
    await mount(); await chooseProducts()
    expectSources(await printSheet(), server.docs.get(A)!.sources.filter((s) => s.product === 'p-a' && ['b11', 'b22'].includes(s.path.at(-1)?.id ?? '')))
  })
  it('C4 cell selects its contents and supports partial and box-only selection', async () => {
    await mount(); await choose(cellRow('a1'))
    expectSources(await printSheet(), server.docs.get(A)!.sources.filter((s) => s.cellId === 'a1'))
    await choose(objectRow('b12'), false)
    const parent = checkbox(cellRow('a1'))
    expect(parent.indeterminate || parent.getAttribute('data-indeterminate') === 'true' || parent.getAttribute('aria-checked') === 'mixed').toBe(true)
    expectSources(await printSheet(), server.docs.get(A)!.sources.filter((s) => s.cellId === 'a1' && s.path.at(-1)?.id !== 'b12'))
    // Снятие родителя после неполного состояния проверяем через полный → снятый.
    await choose(cellRow('a1')); await choose(cellRow('a1'), false)
    await choose(objectRow('b22'))
    expectSources(await printSheet(), server.docs.get(A)!.sources.filter((s) => s.path.at(-1)?.id === 'b22'))
  })
  it('C5 pallet selection deduplicates nested source and retains complete path', async () => {
    await mount(); await choose(objectRow('pallet'))
    expect(checkbox(objectRow('nested')).checked).toBe(true)
    const expected = server.docs.get(A)!.sources.filter((s) => s.path.some((step) => step.id === 'pallet'))
    expectSources(await printSheet(), expected)
    await choose(objectRow('nested'), false)
    expectSources(await printSheet(), expected.filter((s) => s.path.at(-1)?.id === 'pallet'))
    await choose(objectRow('nested')); expectSources(await printSheet(), expected)
    await choose(objectRow('pallet'), false)
    expect(checkbox(objectRow('nested')).checked).toBe(false)
    expectSources(await printSheet())
  })
  it('C6 view switches and collapsed branches preserve product-source pairs', async () => {
    await mount(); await chooseProducts()
    const expected = server.docs.get(A)!.sources.filter((s) => s.product === 'p-a' && ['b11', 'b22'].includes(s.path.at(-1)?.id ?? ''))
    expectSources(await printSheet(), expected)
    await view('cells'); expectSources(await printSheet(), expected)
    await click(q('fbs-pick-collapse-cell:a1')); await click(q('fbs-pick-collapse-cell:a2'))
    expectSources(await printSheet(), expected)
    await view('products')
    await click(q('pick-table-expand-line-p-a'))
    expectSources(await printSheet(), expected)
  })
  it('C7 collapsed branches scan source and cleared checkboxes do not filter full sheet', async () => {
    await mount(); await scan('LOC-А1'); expect(text(q('pick-source'))).toContain('А1')
    for (const id of ['a1', 'a2', 'a3', 'sorting']) await click(q(`fbs-pick-collapse-cell:${id}`))
    expectSources(await printSheet())
    for (const id of ['a1', 'a2', 'a3', 'sorting']) await choose(cellRow(id))
    for (const id of ['a1', 'a2', 'a3', 'sorting']) await choose(cellRow(id), false)
    expectSources(await printSheet())
    await view('products'); expectSources(await printSheet())
    expect(text(q('pick-source'))).toContain('А1')
  })
  it('C8 physical quantity plan and remaining use picked facts rather than boxed or available', async () => {
    await mount()
    for (const kind of ['cells', 'products'] as const) {
      await view(kind)
      const rows = expectSources(await printSheet()).filter((row) => row.product.includes('SKU-A'))
      expect(rows.every((row) => row.plan === 10 && row.left === 6)).toBe(true)
      expect(rows.find((row) => row.container.includes('BOX-11'))!.qty).toBe(12)
    }
    await expandProduct(); await choose(productPlaceRow('BOX-11'))
    const selected = expectSources(await printSheet(), [server.docs.get(A)!.sources[0]])
    expect(selected[0]).toMatchObject({ qty: 12, plan: 10, left: 6 })
  })
  it('C9 loose unlocated missing and already-picked sources retain honest quantities', async () => {
    const data = server.docs.get(A)!
    data.sources.push({ product: 'p-b', cellId: 'loose-only', cell: 'А4', path: [], qty: 22, available: 22, picked: 0 })
    data.sources.push({ product: 'p-b', cellId: 'sorting', cell: 'Без ячеек', path: [], qty: 3, available: 0, picked: 0 })
    data.sources.push({ product: 'p-b', cellId: 'empty', cell: 'А5', path: [box('empty-box', 'BOX-EMPTY')], qty: 0, available: 0, picked: 3 })
    await mount()
    const full = await printSheet(); expectSources(full)
    expect(text(full.body)).toMatch(/Уже подобрано/i)
    expect(text(full.body)).toContain('SKU-NONE'); expect(text(full.body)).toMatch(/Нет на складе/i)
    await choose(cellRow('loose-only'))
    expectSources(await printSheet(), data.sources.filter((s) => s.cellId === 'loose-only'))
    await choose(cellRow('loose-only'), false); await choose(objectRow('unlocated'))
    expectSources(await printSheet(), data.sources.filter((s) => s.path.at(-1)?.id === 'unlocated'))
    await choose(objectRow('unlocated'), false); await choose(objectRow('b12'))
    expectSources(await printSheet(), data.sources.filter((s) => s.path.at(-1)?.id === 'b12'))
    await choose(objectRow('b12'), false)
    await choose(objectRow('empty-box'))
    expectSources(await printSheet(), data.sources.filter((s) => s.path.at(-1)?.id === 'empty-box'))
  })
  it('C10 tab remount reload and other document isolate and restore selection', async () => {
    await mount(); await chooseProducts()
    const expected = server.docs.get(A)!.sources.filter((s) => s.product === 'p-a' && ['b11', 'b22'].includes(s.path.at(-1)?.id ?? ''))
    await remount(); expectSources(await printSheet(), expected)
    await reload(); expectSources(await printSheet(), expected)
    await mount(B); const other = await printSheet(); expectHeader(other, B); expectSources(other)
    expect(text(other.body)).not.toContain('Селлер A')
    expect([...host.querySelectorAll<HTMLInputElement>('input[type="checkbox"]')].some((c) => c.checked)).toBe(false)
    await mount(A); expectHeader(await printSheet(), A); expectSources(await printSheet(), expected)
  })
  it('C11 refreshed data prunes identities keeps current quantities and falls back to full', async () => {
    await mount(); await chooseProducts()
    const data = server.docs.get(A)!
    const shared = data.sources.find((s) => s.product === 'p-a' && s.path.at(-1)?.id === 'b11')!
    shared.qty = 31; shared.available = 5
    data.sources = data.sources.filter((s) => s.path.at(-1)?.id !== 'b22')
    // Тот же видимый номер у новой тары не означает тот же выбранный источник.
    data.sources.push({ product: 'p-a', cellId: 'replacement', cell: 'А2', path: [box('replacement', 'BOX-22')], qty: 32, available: 32, picked: 0 })
    await remount(); expectSources(await printSheet(), [shared])
    data.sources = data.sources.filter((s) => s.path.at(-1)?.id !== 'b11')
    await remount(); expectSources(await printSheet())
  })
  it('C12 selection print cancel and retry are read-only and keep next scan source', async () => {
    await mount(); await scan('BOX-11')
    const before = structuredClone(server.detail(A, false)); const stock = structuredClone(server.options(A))
    const start = server.calls.length
    await choose(objectRow('b22')); await printSheet(); await printSheet()
    expect(server.calls.slice(start).filter((c) => !['GET', 'HEAD'].includes(c.method))).toEqual([])
    expect(server.detail(A, false)).toEqual(before); expect(server.options(A)).toEqual(stock)
    expect(text(q('pick-source'))).toContain('BOX-11')
    await remount(); expect(text(q('pick-source'))).toContain('BOX-11')
    await scan(PRODUCTS[0].barcode)
    const writes = server.calls.slice(start).filter((c) => !['GET', 'HEAD'].includes(c.method))
    expect(writes).toHaveLength(1)
    expect(writes[0].body).toMatchObject({ barcode: PRODUCTS[0].barcode, storage_location_id: 'a1', container_id: 'b11' })
    expect(server.docs.get(A)!.sources[0].picked).toBe(5)
    expect(server.unexpected).toEqual([])
  })
  it('C13 failed print retains choice and source and retry uses latest checkboxes', async () => {
    await mount(); await scan('BOX-12'); await choose(objectRow('b11')); await choose(objectRow('b22'))
    failPrint = true
    await click(button('Печать листа подбора'), 'R1: кнопка печати на вкладке подбора FBO')
    expect(text(host)).toMatch(/Не удалось|Ошибка|заблокирован/i)
    expect(checkbox(objectRow('b11')).checked).toBe(true); expect(checkbox(objectRow('b22')).checked).toBe(true)
    expect(text(q('pick-source'))).toContain('BOX-12')
    expect(captured).toEqual([])
    await choose(objectRow('b11'), false); failPrint = false
    expectSources(await printSheet(), server.docs.get(A)!.sources.filter((s) => s.path.at(-1)?.id === 'b22'))
    expect(text(q('pick-source'))).toContain('BOX-12')
    expectSources(await printSheet(), server.docs.get(A)!.sources.filter((s) => s.path.at(-1)?.id === 'b22'))
    await mount(B); expectHeader(await printSheet(), B)
  })
  it('C14 options failure recovers without false empty success and empty plan prints header', async () => {
    server.docs.get(A)!.failOptions = true
    await mount(); expect(text(host)).toContain('Не удалось загрузить места подбора')
    expect(printFrames).toHaveLength(0)
    const action = button('Печать листа подбора')
    if (action) expect((action as HTMLButtonElement).disabled).toBe(true)
    server.docs.get(A)!.failOptions = false
    await remount(); const recovered = await printSheet(); expectHeader(recovered); expectSources(recovered)
    server.docs.get(A)!.products = []; server.docs.get(A)!.sources = []
    await remount(); const empty = await printSheet(); expectHeader(empty)
    expect(empty.querySelector('table')).not.toBeNull(); expect(rowsOf(empty)).toEqual([])
    for (const p of PRODUCTS) expect(text(empty.body)).not.toContain(p.sku)
  })
  it.each(['wb', 'ozon'] as const)('C15 %s FBO prints full and selected without new prerequisites or external operations', async (marketplace) => {
    server.docs.get(A)!.marketplace = marketplace
    await mount(); const full = await printSheet(); expectHeader(full); expectSources(full)
    await choose(objectRow('b22')); const selected = await printSheet(); expectHeader(selected)
    expectSources(selected, server.docs.get(A)!.sources.filter((s) => s.path.at(-1)?.id === 'b22'))
    // Документ не полностью подобран, КИЗ нет, пропуска/задания упаковки нет.
    expect(writeCalls()).toEqual([]); expect(server.unexpected).toEqual([])
    expect(server.calls.every((c) => c.path === '/products/linked-wb-catalog' ||
      c.path === `/operations/marketplace-unload-requests/${A}` ||
      c.path === `/operations/marketplace-unload-requests/${A}/pick-options` ||
      c.path === `/operations/marketplace-unload-requests/${A}/marking-codes`)).toBe(true)
  })
  it.each(['wb', 'ozon'] as const)('C16 %s FBS retains scan and quantity edit without FBO printing controls', async (marketplace) => {
    server.docs.get(A)!.marketplace = marketplace
    await mount(A, 'fbs')
    expect(q('fbs-cell-pick-table')).not.toBeNull()
    expect(button('Печать листа подбора')).toBeNull(); expect(q('pick-view-switch')).toBeNull()
    expect(host.querySelector('input[type="checkbox"]')).toBeNull()
    await scan('BOX-11'); await scan(PRODUCTS[0].barcode)
    const scans = writeCalls().filter((c) => c.path.endsWith('/pick/scan'))
    expect(scans).toHaveLength(2)
    expect(scans[1].path).toBe(`/operations/fbs-supplies/${A}/pick/scan`)
    expect(scans[1].body).toMatchObject({ barcode: PRODUCTS[0].barcode, container_id: 'b11', storage_location_id: 'a1' })
    const input = q('pick-place-qty-p-a-obj:b11') as HTMLInputElement
    expect(input).not.toBeNull(); expect(input.value).toBe('5')
    const setValue = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value')!.set!
    await act(async () => { setValue.call(input, '6'); input.dispatchEvent(new Event('input', { bubbles: true })) })
    await act(async () => { await new Promise((resolve) => setTimeout(resolve, 400)) }); await settle()
    const sets = writeCalls().filter((c) => c.path.endsWith('/pick/set'))
    expect(sets).toHaveLength(1)
    expect(sets[0].path).toBe(`/operations/fbs-supplies/${A}/pick/set`)
    expect(sets[0].body).toMatchObject({ product_id: 'p-a', container_id: 'b11', storage_location_id: 'a1', quantity: 6 })
    expect(server.docs.get(A)!.sources[0].picked).toBe(6)
    expect(server.unexpected).toEqual([])
    expect(server.calls.some((c) => c.path.includes('marketplace-unload-requests') || c.path.includes('marking-codes'))).toBe(false)
  })
})
