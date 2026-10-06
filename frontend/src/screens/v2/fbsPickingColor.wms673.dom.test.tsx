// @vitest-environment jsdom
import { mkdirSync, writeFileSync } from 'node:fs'
import { join } from 'node:path'
import { act } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from 'vitest'
import { FfFbsSupplyWorkspace } from './FfFbsSupplyWorkspace'
import { FfFbsSupplyAssembly } from './FfFbsSupplyAssembly'
import type { FbsWorkspace } from './fbsApi'
import { fbsBuildPickingRows, buildFbsPickingListPrintHtml } from './fbsUx'
import { fbsAssemblyPickingRows } from './fbsSupplyAssembly'
import { wms673Auth, wms673Order, wms673OzonOrder, wms673Workspace, wms673PrintMeta } from './wms673PrintFixtures'

beforeAll(() => {
  ;(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true
  Element.prototype.scrollIntoView = () => undefined
})
let host: HTMLDivElement, root: Root
let fixtures: FbsWorkspace[], requests: Array<{ path: string; method: string; auth: string | null }>
let pickFailure: boolean, waitPick: Promise<void> | null
let options: Record<string, unknown[]>
let printed: string[], closed: boolean
const originalFetch = globalThis.fetch
const printWindow = () => ({
  opener: {}, get closed() { return closed },
  document: { open: vi.fn(), close: vi.fn(), write: (html: string) => { if (html.startsWith('<!doctype')) printed.push(html) } },
})
const json = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } })
beforeEach(() => {
  fixtures = [wms673Workspace()]; requests = []; printed = []; options = {}; closed = false; pickFailure = false; waitPick = null
  window.sessionStorage.clear(); window.localStorage.clear()
  vi.spyOn(window, 'open').mockImplementation(() => printWindow() as unknown as Window)
  globalThis.fetch = async (input, init) => {
    const url = new URL(typeof input === 'string' ? input : input instanceof URL ? input.href : input.url, 'http://wms.test')
    const path = url.pathname.replace(/^\/api/, '')
    const method = init?.method ?? 'GET'
    requests.push({ path, method, auth: new Headers(init?.headers).get('Authorization') })
    if (method !== 'GET') throw new Error(`WMS-673 print must not mutate: ${method} ${path}`)
    const one = fixtures.find((f) => path.startsWith(`/operations/fbs-supplies/${f.supply.id}/`))
    if (one && path.endsWith('/workspace')) return json(one)
    if (one && path.endsWith('/pick-options')) {
      if (waitPick) await waitPick
      return pickFailure ? json({ detail: 'synthetic failure' }, 503) : json(options[one.supply.id] ?? [])
    }
    // Local read-only auxiliaries used by real picking screens when changing tabs.
    if (path.includes('/marketplace-products') || path.includes('/wb-products') || path.includes('/product-catalog')) return json({ items: [], total: 0 })
    if (path === '/warehouses') return json([])
    return json(null)
  }
  host = document.createElement('div'); document.body.appendChild(host); root = createRoot(host)
})
afterEach(async () => {
  await act(async () => root.unmount()); host.remove(); document.body.innerHTML = ''
  globalThis.fetch = originalFetch; vi.restoreAllMocks()
})
async function open(kind: 'single' | 'group') {
  await act(async () => {
    root.render(kind === 'single'
      ? <FfFbsSupplyWorkspace token="synthetic-wms673" authHeaders={wms673Auth} supplyId={fixtures[0].supply.id} open onClose={() => undefined} />
      : <FfFbsSupplyAssembly token="synthetic-wms673" authHeaders={wms673Auth} supplyIds={fixtures.map((f) => f.supply.id)} open onClose={() => undefined} />)
  })
  await act(async () => { await new Promise((r) => setTimeout(r, 15)) })
  const button = document.querySelector<HTMLButtonElement>('[data-testid="fbs-pick-list-print"]')
  expect(button, 'real print button must exist after API workspace loaded').not.toBeNull()
  expect(button!.disabled).toBe(false)
}
async function print() {
  await act(async () => document.querySelector<HTMLButtonElement>('[data-testid="fbs-pick-list-print"]')!.click())
}
function doc(html = printed.at(-1)) {
  expect(html, 'real button must generate the production print HTML').toBeTruthy()
  return new DOMParser().parseFromString(html!, 'text/html')
}
function colorCells(document: Document) {
  const headers = [...document.querySelectorAll('thead th')].map((th) => th.textContent)
  const index = headers.indexOf('Цвет')
  expect(index, 'missing business column Цвет').toBe(4)
  expect(headers.slice(3, 6)).toEqual(['Размер', 'Цвет', 'Ячейка / тара'])
  return [...document.querySelectorAll('tbody tr')].map((tr) => tr.children[index].textContent)
}
function cellsWithoutColor(document: Document) {
  const index = [...document.querySelectorAll('thead th')].findIndex((th) => th.textContent === 'Цвет')
  return [...document.querySelectorAll('tbody tr')].map((tr) => [...tr.children].filter((_td, i) => i !== index).map((td) => td.textContent?.replace(/\s+/g, ' ').trim()))
}

describe('WMS-673 business RED contract through real buttons and API fixtures', () => {
  it('C1 WB single: separate adjacent column carries both exact product colors', async () => {
    await open('single'); expect(printed).toHaveLength(0); await print()
    expect(printed).toHaveLength(1)
    if (process.env.WMS673_EVIDENCE_DIR) {
      mkdirSync(process.env.WMS673_EVIDENCE_DIR, { recursive: true }); writeFileSync(join(process.env.WMS673_EVIDENCE_DIR, 'single.html'), printed[0])
    }
    expect(colorCells(doc())).toEqual(['Красный', 'Синий'])
  })
  it('C2 Ozon single: each position owns its color, barcode and posting identity', async () => {
    fixtures = [wms673Workspace('supply-oz', [wms673OzonOrder()], 'ozon')]
    await open('single'); await print(); const document = doc()
    expect(colorCells(document)).toEqual(['Красный', 'Синий'])
    const rows = cellsWithoutColor(document)
    expect(rows.map((row) => row[2])).toEqual([expect.stringContaining('OZ-RED'), expect.stringContaining('OZ-BLUE')])
    expect(rows.map((row) => row[5])).toEqual(['№OZ-673-POSTING', '№OZ-673-POSTING'])
    expect([...document.querySelectorAll('thead th')].map((th) => th.textContent)).toContain('Заказы Ozon')
    expect(document.body.textContent).not.toContain('WB 1673')
  })
  it('C3 mixed assembly: repeat ID aggregates; same names at distinct seller IDs stay separate', async () => {
    const repeated = wms673Order('repeat', 'red', 'Красный', 2)
    const other = wms673Order('other-seller', 'other-id', 'Зелёный', 0); other.product.name = 'Товар red'
    fixtures.push(wms673Workspace('supply-b', [repeated, other]), wms673Workspace('supply-oz', [wms673OzonOrder()], 'ozon'))
    await open('group'); await print(); const document = doc()
    expect(colorCells(document)).toEqual(['Красный', 'Синий', 'Зелёный', 'Красный', 'Синий'])
    expect(cellsWithoutColor(document).map((r) => [r[0], r[7], r[8]])).toEqual([
      ['1–2', '2', '0 / 2'], ['3', '1', '0 / 1'], ['4', '1', '0 / 1'], ['5–7', '3', '1 / 3'], ['8–9', '2', '2 / 2'],
    ])
  })
  it.each(['single', 'group'] as const)('C4 %s: group filled color survives partial empty and input reversal', async (kind) => {
    const blank = wms673Order('empty', 'same', null, 0), filled = wms673Order('filled', 'same', 'Бордовый', 1)
    const snapshot = [blank, filled].map((one) => structuredClone(one))
    for (const ordered of [snapshot, [...snapshot].reverse()]) {
      const rows = kind === 'single' ? fbsBuildPickingRows(ordered, false).rows : fbsAssemblyPickingRows([wms673Workspace('same', ordered)])
      const html = buildFbsPickingListPrintHtml({ ...wms673PrintMeta, rows })
      expect(colorCells(doc(html))).toEqual(['Бордовый']); expect(rows.map((r) => [r.required, r.picked, r.wbOrders])).toEqual([[2, 0, [673000, 673001]]])
    }
    // Also prove the real button path, not merely direct row generation.
    fixtures = [wms673Workspace('same', [blank, filled])]; await open(kind); await print(); expect(colorCells(doc())).toEqual(['Бордовый'])
  })
  it.each(['single', 'group'] as const)('C4 %s: missing/null/empty/whitespace colors all print dash', async (kind) => {
    fixtures = [wms673Workspace('blank', [undefined, null, '', '   '].map((color, i) => wms673Order(`o${i}`, `p${i}`, color, i)))]
    await open(kind); await print(); expect(colorCells(doc())).toEqual(['—', '—', '—', '—'])
  })
  it.each(['single', 'group'] as const)('C5 %s: ampersands, markup and scripts remain text in exact color cell', async (kind) => {
    const values = ['Красный & синий <образец>', '<img src=x onerror="window.__injected=true"><script>window.__injected=true</script>']
    fixtures = [wms673Workspace('escape', values.map((value, i) => wms673Order(`o${i}`, `p${i}`, value, i)))]
    await open(kind); await print(); const document = doc()
    expect(colorCells(document)).toEqual(values); expect(document.querySelectorAll('tbody img, tbody script, tbody образец')).toHaveLength(0)
    expect([...document.querySelectorAll('tbody tr')].map((tr) => tr.children.length)).toEqual([11, 11])
  })
  it('C6 empty print colspan agrees with all eleven headers', async () => {
    fixtures = [wms673Workspace('empty', [])]; await open('group'); await print(); const document = doc()
    expect(document.querySelectorAll('thead th')).toHaveLength(11)
    expect(document.querySelector('tbody td')?.getAttribute('colspan')).toBe('11')
  })
  it.each(['single', 'group'] as const)('C9 %s: option failure preserves color, fallback and explicit repeat', async (kind) => {
    pickFailure = true; fixtures[0].orders[1].inventory.locations = []
    await open(kind); await print(); const document = doc()
    expect(document.body.textContent).toContain('A-01: 9'); expect(document.body.textContent).toContain('—')
    expect(document.querySelectorAll('tbody tr')).toHaveLength(2)
    expect(document.body.textContent).toContain('0 / 1')
    expect(document.body.textContent).toContain('Товар blue')
    expect(document.body.textContent).toContain('S673')
    expect(window.document.body.textContent).toContain('Не удалось получить ячейки и тару')
    await print(); expect(printed).toHaveLength(2)
    expect(colorCells(document)).toEqual(['Красный', 'Синий'])
  })
})

describe('WMS-673 preexisting controls (must PASS without product edits)', () => {
  it.each(['single', 'group'] as const)('C6/C10 %s: print reads only, keeps fixtures and old cell semantics including fresh options', async (kind) => {
    const before = JSON.stringify(fixtures)
    options['supply-a'] = [{ product_id: 'red', picked_qty: 1, locations: [] }, { product_id: 'blue', picked_qty: 0,
      locations: [{ storage_location_id: 'loc-b', location_code: 'A-02', available: 7,
        sources: [{ available: 7, is_loose: false, source_label: 'Короб B-02', container_path: [{ kind: 'box', id: 'b2', code: 'B-02', label: 'Короб B-02' }] }] }] }]
    await open(kind); const beforeClick = requests.length; expect(printed).toHaveLength(0); await print()
    expect(requests.slice(beforeClick).map(({ path, method }) => [method, path])).toEqual([['GET', '/operations/fbs-supplies/supply-a/pick-options']])
    expect(requests.every((r) => r.method === 'GET' && r.auth === 'Bearer synthetic-wms673')).toBe(true)
    expect(JSON.stringify(fixtures)).toBe(before)
    expect(cellsWithoutColor(doc())).toEqual([
      ['1', '—', 'Товар red ART-red · WB 1673 · WB-CODE-red', '46', 'Нет свободного остатка', '№673000', 'S673 0000', '1', '1 / 1', 'sgtin'],
      ['2', '—', 'Товар blue ART-blue · WB 1673 · WB-CODE-blue', '46', 'A-02 · Короб B-02: 7', '№673001', 'S673 0001', '1', '0 / 1', 'sgtin'],
    ])
  })
  it.each(['single', 'group'] as const)('C9 %s: blocked popup fetches no print options and allows explicit repeat', async (kind) => {
    await open(kind); const before = requests.length
    vi.mocked(window.open).mockReturnValueOnce(null); await print()
    expect(requests).toHaveLength(before); expect(printed).toHaveLength(0)
    expect(document.body.textContent).toContain('Браузер заблокировал окно печати')
    await print(); expect(printed).toHaveLength(1)
  })
  it.each(['single', 'group'] as const)('C9 %s: closed popup during request prevents document write; repeat works', async (kind) => {
    await open(kind)
    let release = () => undefined as void
    waitPick = new Promise<void>((resolve) => { release = resolve })
    await print(); closed = true
    await act(async () => release()); expect(printed).toHaveLength(0)
    waitPick = null; closed = false; await print(); expect(printed).toHaveLength(1)
  })
  it('C11 WMS610: common print stays available on composition/picking/packing/boxes, old screen quantity headers', async () => {
    await open('group')
    for (const stage of ['Состав', 'Подбор', 'Упаковка и маркировка', 'Короба']) {
      const tab = [...document.querySelectorAll<HTMLElement>('[role="tab"]')].find((node) => node.textContent === stage)
      expect(tab, stage).toBeTruthy(); await act(async () => tab!.click())
      const button = document.querySelector<HTMLButtonElement>('[data-testid="fbs-pick-list-print"]')
      expect(button?.disabled, stage).toBe(false)
      if (stage === 'Подбор') {
        const headers = [...document.querySelectorAll('thead th')].map((th) => th.textContent?.trim())
        expect(headers.slice(-3).map(value => value?.replace(/\s+/g, ''))).toEqual(['Остатоквкоробе', 'Собрать', 'Собрано'])
        expect(headers).not.toContain('Цвет')
      }
      await print()
    }
    expect(printed).toHaveLength(4)
  })
})
