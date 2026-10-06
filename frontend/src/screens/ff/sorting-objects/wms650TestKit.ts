// WMS-650 · общий стенд DOM-тестов раскладки (контракт тестов, не продукт).
//
// Настоящий FfSortingObjectsPage с настоящим SortingObjectsScreen в jsdom.
// Подменена только внешняя граница — сервер (fetch): подставной сервер хранит
// состав документа и отвечает так же, как ручки `…/sorting-objects`,
// `…/sorting-objects/place`, `…/sorting-objects/scan` и новая
// `…/sorting-objects/undo` (контракт из docs/requirements/WMS-650.md и
// backend/tests/wms650_sorting_seed.py).
//
// Что экран обязан отдать в DOM, чтобы тесты могли его прочитать (новое, кроме
// уже существующих objects-scan, objects-tree, objects-left-qty, objects-cells):
// - objects-undo — стрелка «назад» (IconButton, UndoOutlined) у поля сканера;
//   подсказка (Tooltip) «Отменить: <что>» / «Отменять нечего»;
// - objects-placed-qty — «размещено N шт» в шапке панели «Ячейки склада»;
// - placed-cell-<cellId> — группа ячейки в панели; её заголовок — первый
//   элемент role="button" внутри группы (клик открывает ячейку, как скан);
// - строки панели и основного списка — data-row-key="o-<id тары>" / "l-<id строки>"
//   (как уже делает DataTable/макет);
// - placed-toggle-<id тары>, placed-minus-<ключ строки> («Снять с ячейки»),
//   placed-out-<ключ строки> («Вынуть из короба/палеты/грузоместа») — как в макете;
// - data-highlight="open" — на заголовке открытой ячейки и на строке открытой
//   тары; data-highlight="touched" — на строке, которой коснулось последнее
//   действие или «назад». Атрибут ставится на саму строку (элемент с
//   data-row-key) или на любой её потомок.

import { createElement } from 'react'
import { act } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { MemoryRouter } from 'react-router-dom'
import { FfSortingObjectsPage } from './FfSortingObjectsPage'
import type { Cell, GoodsLine, Holder, ObjKind, Product, WarehouseObject } from './objectsStub'

export const WAREHOUSE_ID = 'wh-650'
export const DOC_A = 'doc-a-650'
export const DOC_B = 'doc-b-650'

export const CELLS = {
  a11: { id: 'c-a11', code: 'А 1.1', barcode: '2000000000114' },
  a12: { id: 'c-a12', code: 'А 1.2', barcode: '2000000000121' },
  b11: { id: 'c-b11', code: 'Б 1.1', barcode: '2000000000411' },
} satisfies Record<string, Cell>

type Obj = { id: string; kind: ObjKind; code: string; barcode: string }
export const OBJ = {
  k1: { id: 'k1', kind: 'box', code: 'КР-000481', barcode: '2200000004814' },
  k2: { id: 'k2', kind: 'box', code: 'КР-000482', barcode: '2200000004821' },
  k3: { id: 'k3', kind: 'box', code: 'КР-000483', barcode: '2200000004838' },
  g1: { id: 'g1', kind: 'cargo_place', code: 'ГМ-000318', barcode: '2300000003185' },
  p1: { id: 'p1', kind: 'pallet', code: 'П-000131', barcode: '2100000001311' },
} satisfies Record<string, Obj>

export const LONG_T3 =
  'Термокружка из нержавеющей стали с двойными стенками и герметичной крышкой-поилкой, 450 мл, цвет графитовый матовый'

function product(id: string, name: string, barcode: string): Product {
  return { id, name, sku: id.toUpperCase(), seller: 'ИП Раскладка', barcode, photo: '', size: null, alreadyAt: [] }
}

export const PRODUCTS = {
  t1: product('p-t1', 'Носки спортивные, 3 пары', '4600987654338'),
  t2: product('p-t2', 'Ремень кожаный, 110 см', '4601122334462'),
  t3: product('p-t3', LONG_T3, '4601122334455'),
}

export type DocState = { objects: WarehouseObject[]; lines: GoodsLine[] }

export const cellHolder = (cell: { id: string }) => `cell:${cell.id}`
export const objHolder = (obj: { id: string }) => `obj:${obj.id}`

/** Документ A: К1 (Т1×3), К2 (Т1×2), К3 (Т2×4), Г1 (Т2×2), П1 пустая, россыпь Т1×2 и Т3×10. */
export function docA(holders: Partial<Record<keyof typeof OBJ, Holder>> = {}): DocState {
  const objects = (Object.keys(OBJ) as Array<keyof typeof OBJ>).map((key) => ({
    ...OBJ[key],
    holder: holders[key] ?? null,
  }))
  return {
    objects,
    lines: [
      { id: 'l-k1', productId: PRODUCTS.t1.id, qty: 3, holder: objHolder(OBJ.k1) },
      { id: 'l-k2', productId: PRODUCTS.t1.id, qty: 2, holder: objHolder(OBJ.k2) },
      { id: 'l-k3', productId: PRODUCTS.t2.id, qty: 4, holder: objHolder(OBJ.k3) },
      { id: 'l-g1', productId: PRODUCTS.t2.id, qty: 2, holder: objHolder(OBJ.g1) },
      { id: 'l-t1', productId: PRODUCTS.t1.id, qty: 2, holder: null },
      { id: 'l-t3', productId: PRODUCTS.t3.id, qty: 10, holder: null },
    ],
  }
}

/** Документ B того же селлера: отдельный состав, своя история «назад». */
export function docB(): DocState {
  return {
    objects: [{ id: 'kb1', kind: 'box', code: 'КР-000901', barcode: '2200000009017', holder: null }],
    lines: [{ id: 'l-kb1', productId: PRODUCTS.t1.id, qty: 2, holder: 'obj:kb1' }],
  }
}

export const ACCEPTED_A = 23

/** JWT-подобный токен: экран определяет сотрудника по `sub`. */
export function makeToken(sub: string): string {
  const encode = (value: object) => btoa(JSON.stringify(value)).replace(/=+$/, '').replace(/\+/g, '-').replace(/\//g, '_')
  return `${encode({ alg: 'none', typ: 'JWT' })}.${encode({ sub, tenant_id: 'tenant-650', role: 'fulfillment_admin' })}.sig`
}

export const TOKEN_1 = makeToken('user-650-1')
export const TOKEN_2 = makeToken('user-650-2')

type Json = Record<string, unknown>
export type Logged = { method: string; path: string; body: Json | null }
type Handler = (body: Json) => Response | null | undefined | Promise<Response | null | undefined>

export function json(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } })
}

function clone<T>(value: T): T {
  return JSON.parse(JSON.stringify(value)) as T
}

/** Подставной сервер раскладки: тот же состав, те же ответы, что у настоящих ручек. */
export class FakeSortingServer {
  docs: Record<string, DocState>
  log: Logged[] = []
  /** Квитанции действий: operation_id → документ и состав «до». */
  private receipts = new Map<string, { doc: string; before: DocState; response: Json }>()
  private undone = new Map<string, Json>()
  private seq = 0
  /** Разовые подмены ответа: первая подходящая срабатывает и снимается. */
  private overrides: Array<{ route: 'place' | 'scan' | 'undo'; handler: Handler }> = []

  constructor(docs: Record<string, DocState> = { [DOC_A]: docA(), [DOC_B]: docB() }) {
    this.docs = clone(docs)
  }

  /** Следующий запрос на ручку обработать так (null/undefined — обычный ответ). */
  once(route: 'place' | 'scan' | 'undo', handler: Handler) {
    this.overrides.push({ route, handler })
  }

  /** Следующий запрос на ручку ждёт release(). */
  hold(route: 'place' | 'scan' | 'undo'): () => void {
    let release!: () => void
    const gate = new Promise<void>((resolve) => { release = resolve })
    this.once(route, async () => {
      await gate
      return null
    })
    return () => release()
  }

  reject(route: 'place' | 'scan' | 'undo', status: number, detail: string) {
    this.once(route, () => json({ detail }, status))
  }

  requests(route: 'place' | 'scan' | 'undo'): Json[] {
    return this.log
      .filter((one) => one.method === 'POST' && one.path === `/warehouses/${WAREHOUSE_ID}/sorting-objects/${route}`)
      .map((one) => one.body ?? {})
  }

  /** Все записи «изменения склада»: что экран отправил на сервер. */
  writes(): Logged[] {
    return this.log.filter((one) => one.method !== 'GET')
  }

  fetch = async (input: RequestInfo | URL, init?: RequestInit): Promise<Response> => {
    const raw = typeof input === 'string' ? input : input instanceof URL ? input.href : input.url
    const url = new URL(raw, 'http://wms.test')
    const path = url.pathname.replace(/^\/api/, '')
    const method = (init?.method ?? 'GET').toUpperCase()
    const body = init?.body ? (JSON.parse(String(init.body)) as Json) : null
    this.log.push({ method, path, body })
    const base = `/warehouses/${WAREHOUSE_ID}/sorting-objects`
    if (method === 'GET' && path === base) {
      const doc = url.searchParams.get('inbound_request_id') ?? ''
      const state = this.docs[doc]
      if (!state) return json({ detail: 'inbound_request_not_found' }, 404)
      return json({
        ...clone(state),
        products: Object.values(PRODUCTS),
        cells: Object.values(CELLS),
      })
    }
    const route = path === `${base}/place` ? 'place' : path === `${base}/scan` ? 'scan' : path === `${base}/undo` ? 'undo' : null
    if (method !== 'POST' || !route || !body) return json({ detail: `unexpected ${method} ${path}` }, 404)
    const index = this.overrides.findIndex((one) => one.route === route)
    if (index >= 0) {
      const [override] = this.overrides.splice(index, 1)
      const answer = await override.handler(body)
      if (answer) return answer
    }
    if (route === 'place') return this.place(body)
    if (route === 'scan') return this.scan(body)
    return this.undo(body)
  }

  private doc(body: Json): DocState {
    const state = this.docs[String(body.inbound_request_id ?? '')]
    if (!state) throw new Error(`нет документа ${String(body.inbound_request_id)}`)
    return state
  }

  private target(body: Json): Holder {
    if (body.cell_id) return `cell:${String(body.cell_id)}`
    if (body.to_id) return `obj:${String(body.to_id)}`
    return null
  }

  private moveLine(state: DocState, line: GoodsLine, qty: number, target: Holder): GoodsLine {
    const twin = state.lines.find((one) => one !== line && one.productId === line.productId && one.holder === target)
    let moved: GoodsLine
    if (twin) {
      twin.qty += qty
      moved = twin
    } else {
      moved = { id: `${line.id}-m${++this.seq}`, productId: line.productId, qty, holder: target }
      state.lines.push(moved)
    }
    line.qty -= qty
    state.lines = state.lines.filter((one) => one.qty > 0)
    return moved
  }

  private place(body: Json): Response {
    const op = String(body.operation_id ?? '')
    const known = this.receipts.get(op)
    if (known) return json(known.response)
    const state = this.doc(body)
    const before = clone(state)
    const target = this.target(body)
    let response: Json
    if (body.kind === 'product') {
      const line = state.lines.find((one) => one.id === body.id)
      if (!line) return json({ detail: 'object_not_found' }, 404)
      const qty = Math.min(Number(body.qty ?? line.qty), line.qty)
      this.moveLine(state, line, qty, target)
      response = { id: op, moved_qty: qty }
    } else {
      const object = state.objects.find((one) => one.id === body.id)
      if (!object) return json({ detail: 'object_not_found' }, 404)
      if (object.holder === target) return json({ detail: 'nothing_to_move' }, 409)
      object.holder = target
      response = { id: op, moved_qty: 1 }
    }
    this.receipts.set(op, { doc: String(body.inbound_request_id), before, response })
    return json(response)
  }

  private scan(body: Json): Response {
    const op = String(body.operation_id ?? '')
    const known = this.receipts.get(op)
    if (known) return json({ ...known.response, reload: true })
    const state = this.doc(body)
    const before = clone(state)
    const item = Object.values(PRODUCTS).find((one) => one.barcode === body.barcode)
    if (!item) return json({ detail: 'product_not_on_request' }, 409)
    const source = state.lines.find((one) => one.productId === item.id && one.holder === null && one.qty > 0)
    if (!source) return json({ detail: 'nothing_to_move' }, 409)
    const sourceId = source.id
    const targetHolder = body.to_id ? `obj:${String(body.to_id)}` : `cell:${String(body.cell_id)}`
    const moved = this.moveLine(state, source, 1, targetHolder)
    const response = {
      id: op,
      moved_qty: 1,
      reload: false,
      remaining_qty: remainingQty(state),
      source_id: sourceId,
      target_id: moved.id,
      product_id: item.id,
      target_holder: targetHolder,
    }
    this.receipts.set(op, { doc: String(body.inbound_request_id), before, response })
    return json(response)
  }

  private undo(body: Json): Response {
    const op = String(body.operation_id ?? '')
    const done = this.undone.get(op)
    if (done) return json(done)
    const target = String(body.target_operation_id ?? '')
    const receipt = this.receipts.get(target)
    if (!receipt || receipt.doc !== body.inbound_request_id) return json({ detail: 'undo_target_not_found' }, 404)
    this.docs[receipt.doc] = clone(receipt.before)
    this.receipts.delete(target)
    const response = { id: op, target_operation_id: target }
    this.undone.set(op, response)
    return json(response)
  }
}

/** Сколько штук ещё не стоит на ячейке (через цепочку держателей). */
export function remainingQty(state: DocState): number {
  const byId = new Map(state.objects.map((one) => [one.id, one]))
  const onCell = (holder: Holder): boolean => {
    let cursor = holder
    for (let step = 0; cursor && step < 20; step += 1) {
      if (cursor.startsWith('cell:')) return true
      cursor = byId.get(cursor.slice(4))?.holder ?? null
    }
    return false
  }
  return state.lines.filter((line) => !onCell(line.holder)).reduce((sum, line) => sum + line.qty, 0)
}

// ── Рендер и действия оператора ─────────────────────────────────────────────

export type Mounted = { root: Root; host: HTMLDivElement }

export function mountPage(options: { token?: string; doc?: string } = {}): Mounted {
  const host = document.createElement('div')
  document.body.appendChild(host)
  const root = createRoot(host)
  act(() => {
    root.render(
      createElement(
        MemoryRouter,
        null,
        createElement(FfSortingObjectsPage, {
          token: options.token ?? TOKEN_1,
          warehouses: [{ id: WAREHOUSE_ID, name: 'Ярцево' }],
          embedded: true,
          inboundRequestId: options.doc ?? DOC_A,
          onPlaced: async () => undefined,
        }),
      ),
    )
  })
  return { root, host }
}

export function unmount(mounted: Mounted) {
  act(() => mounted.root.unmount())
  mounted.host.remove()
}

/** «Обновить страницу»: снять экран и открыть заново в той же вкладке. */
export async function reload(mounted: Mounted, options: { token?: string; doc?: string } = {}): Promise<Mounted> {
  unmount(mounted)
  const next = mountPage(options)
  await settle()
  return next
}

export async function settle(rounds = 8) {
  for (let step = 0; step < rounds; step += 1) {
    await act(async () => {
      await new Promise((resolve) => setTimeout(resolve, 5))
    })
  }
}

export function byTestId(testId: string): HTMLElement | null {
  return document.querySelector<HTMLElement>(`[data-testid="${testId}"]`)
}

export function must(testId: string): HTMLElement {
  const element = byTestId(testId)
  if (!element) throw new Error(`на экране нет data-testid="${testId}"`)
  return element
}

export function scannerInput(): HTMLInputElement {
  const input = document.querySelector<HTMLInputElement>('input[data-testid="objects-scan"]')
  if (!input) throw new Error('нет поля сканера objects-scan')
  return input
}

/** Сканер-клавиатура: код в поле сканера и Enter. */
export async function scanCode(code: string) {
  const input = scannerInput()
  act(() => {
    input.focus()
    input.value = code
    input.dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter', bubbles: true, cancelable: true }))
  })
  await settle()
}

/** Строка под полем сканера: результат последнего скана, «Отменено: …» или отказ. */
export function fieldText(): string {
  const control = scannerInput().closest('.MuiFormControl-root')
  return control?.querySelector('.MuiFormHelperText-root')?.textContent ?? ''
}

export function fieldIsError(): boolean {
  const control = scannerInput().closest('.MuiFormControl-root')
  return Boolean(control?.querySelector('.MuiFormHelperText-root.Mui-error'))
}

export function mainList(): HTMLElement {
  return must('objects-tree')
}

export function placedCell(cell: { id: string }): HTMLElement {
  return must(`placed-cell-${cell.id}`)
}

export function placedCellHeader(cell: { id: string }): HTMLElement {
  const header = placedCell(cell).querySelector<HTMLElement>('[role="button"]')
  if (!header) throw new Error(`у ячейки ${cell.id} в панели нет заголовка role="button"`)
  return header
}

export function rowIn(container: Element, key: string): HTMLElement | null {
  return container.querySelector<HTMLElement>(`[data-row-key="${key}"]`)
}

/** Где на экране стоит строка: в основном списке и/или под какими ячейками панели. */
export function whereShown(key: string): { main: boolean; cells: string[] } {
  const cells = Object.values(CELLS)
    .filter((cell) => byTestId(`placed-cell-${cell.id}`) && rowIn(placedCell(cell), key))
    .map((cell) => cell.code)
  return { main: Boolean(rowIn(mainList(), key)), cells }
}

export function highlightOf(element: Element | null): string | null {
  if (!element) return null
  return element.getAttribute('data-highlight') ?? element.querySelector('[data-highlight]')?.getAttribute('data-highlight') ?? null
}

export function highlighted(value: string): HTMLElement[] {
  return Array.from(document.querySelectorAll<HTMLElement>(`[data-highlight="${value}"]`))
}

export function numberIn(testId: string): number {
  return Number((must(testId).textContent ?? '').replace(/[^\d]/g, ''))
}

export function undoButton(): HTMLButtonElement {
  const button = byTestId('objects-undo')
  if (!button) throw new Error('у поля сканера нет стрелки «назад» (data-testid="objects-undo")')
  return button as HTMLButtonElement
}

/** Подсказка стрелки «назад»: aria-label обёртки Tooltip или всплывающий текст при наведении. */
export async function undoHint(): Promise<string> {
  const button = undoButton()
  const labels: string[] = []
  for (let node: Element | null = button; node && node !== document.body; node = node.parentElement) {
    const label = node.getAttribute('aria-label')
    if (label) labels.push(label)
    const title = node.getAttribute('title')
    if (title) labels.push(title)
  }
  const target = button.parentElement ?? button
  act(() => {
    target.dispatchEvent(new MouseEvent('mouseover', { bubbles: true }))
  })
  await settle(30)
  const tooltip = document.querySelector('[role="tooltip"]')?.textContent
  if (tooltip) labels.push(tooltip)
  act(() => {
    target.dispatchEvent(new MouseEvent('mouseout', { bubbles: true }))
  })
  return labels.join(' | ')
}

export async function click(element: Element) {
  act(() => {
    element.dispatchEvent(new MouseEvent('mousedown', { bubbles: true, cancelable: true }))
    element.dispatchEvent(new MouseEvent('mouseup', { bubbles: true, cancelable: true }))
    element.dispatchEvent(new MouseEvent('click', { bubbles: true, cancelable: true }))
  })
  await settle()
}

/** Два клика подряд без паузы на перерисовку — быстрый двойной клик. */
export async function doubleClick(element: Element) {
  act(() => {
    element.dispatchEvent(new MouseEvent('click', { bubbles: true, cancelable: true }))
    element.dispatchEvent(new MouseEvent('click', { bubbles: true, cancelable: true }))
  })
  await settle()
}

export function installFetch(server: FakeSortingServer): () => void {
  const original = globalThis.fetch
  globalThis.fetch = server.fetch as typeof fetch
  return () => {
    globalThis.fetch = original
  }
}

export function resetStorage() {
  try { localStorage.clear() } catch { /* jsdom */ }
  try { sessionStorage.clear() } catch { /* jsdom */ }
}

/** jsdom не умеет прокручивать: экран вправе звать scrollIntoView у строки. */
export function prepareDom() {
  ;(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true
  if (typeof Element.prototype.scrollIntoView !== 'function') {
    Element.prototype.scrollIntoView = function scrollIntoView() {}
  }
}
