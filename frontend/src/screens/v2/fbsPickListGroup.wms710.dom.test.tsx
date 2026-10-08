// @vitest-environment jsdom
// WMS-710: лист групповой сборки двух поставок. Настоящий FfFbsSupplyAssembly
// грузит каждую поставку через API (здесь подменён фикстурами) и печатает лист
// через кнопку «Печать листа подбора». Признак Империи — пропсом pickListTabOrder.
import { act } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, beforeAll, beforeEach, expect, it, vi } from 'vitest'
import { FfFbsSupplyAssembly } from './FfFbsSupplyAssembly'
import type { FbsWorkspace } from './fbsApi'
import {
  DOC,
  SUPPLY_ID,
  baseWorkspace,
  docHeader,
  expectWalk,
  fakePrintWindow,
  jsonResponse,
  normalizeSheet,
  pickOptionsResponse,
  pickingContextResponse,
  sheetHtml,
  sourcesCell,
  type Scenario,
} from './fbsPickList.wms710.fixture'

const SUPPLY_B = '86b38d6f-f161-4acb-8ce1-0000000000b2'
const authHeaders = () => ({ Authorization: 'Bearer wms710-group' })
const originalFetch = globalThis.fetch
let host: HTMLDivElement
let root: Root
let requests: string[]
let scenarios: Record<string, Scenario>

/** Вторая поставка той же группы: тот же товар, свои id заказов и поставки. */
function workspaceFor(supplyId: string): FbsWorkspace {
  const workspace = baseWorkspace()
  const isA = supplyId === SUPPLY_ID
  workspace.supply = { ...workspace.supply, id: supplyId, wb_supply_id: isA ? 'WB-GI-662' : 'WB-GI-663' }
  workspace.orders = workspace.orders.map((order, index) => ({
    ...order,
    id: isA ? order.id : `b0000000-0000-4000-8000-00000000000${index}`,
    supply_id: supplyId,
  }))
  return workspace
}

beforeAll(() => {
  ;(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true
})

beforeEach(() => {
  requests = []
  globalThis.fetch = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = new URL(typeof input === 'string' ? input : input instanceof URL ? input.href : input.url, 'http://wms.test')
    const method = (init?.method ?? (input instanceof Request ? input.method : 'GET')).toUpperCase()
    requests.push(`${method} ${url.pathname}`)
    if (method !== 'GET') throw new Error(`Unexpected mutation: ${method} ${url.pathname}`)
    const match = url.pathname.match(/\/operations\/fbs-supplies\/([^/]+)\/([^/]+)$/)
    if (match) {
      const [, id, endpoint] = match
      const scenario = scenarios[id]
      if (endpoint === 'workspace') return jsonResponse(workspaceFor(id))
      if (endpoint === 'pick-options') return pickOptionsResponse(scenario)
      if (endpoint === 'picking-context') return pickingContextResponse(scenario)
    }
    return jsonResponse({ detail: `не подготовлено в тесте: ${url.pathname}` }, 404)
  }) as typeof fetch
  host = document.createElement('div')
  document.body.appendChild(host)
  root = createRoot(host)
})

afterEach(() => {
  act(() => root.unmount())
  host.remove()
  globalThis.fetch = originalFetch
  vi.restoreAllMocks()
})

/** Печатает лист группы из двух поставок и возвращает HTML листа. */
async function printGroup(options: { flag: boolean; first: Scenario; second: Scenario }) {
  scenarios = { [SUPPLY_ID]: options.first, [SUPPLY_B]: options.second }
  const written: string[] = []
  vi.spyOn(window, 'open').mockReturnValue(fakePrintWindow(written) as unknown as Window)
  const flagProps = { pickListTabOrder: options.flag }
  await act(async () => root.render(
    <MemoryRouter>
      <FfFbsSupplyAssembly token="wms710-group" authHeaders={authHeaders} supplyIds={[SUPPLY_ID, SUPPLY_B]}
        open onClose={() => undefined} {...flagProps} />
    </MemoryRouter>,
  ))
  const printButton = () => document.querySelector<HTMLButtonElement>('[data-testid="fbs-pick-list-print"]')
  await vi.waitFor(() => {
    expect(requests.filter((request) => request.endsWith('/workspace')).length).toBeGreaterThanOrEqual(2)
    expect(printButton()?.disabled).toBe(false)
  }, { timeout: 15_000 })
  await act(async () => { await new Promise((resolveTimer) => setTimeout(resolveTimer, 300)) })
  await act(async () => printButton()!.click())
  await vi.waitFor(() => expect(sheetHtml(written)).toBeDefined(), { timeout: 15_000 })
  return sheetHtml(written)!
}

const sharedPlace = { cell: 'Ж-1-7', box: { id: 'box-3', number: 3, barcode: 'BC-3' }, qty: 5, doc: DOC.P96 }

it('C10: место, общее для двух поставок группы, одной строкой; Взять и Подобрано суммируются', { timeout: 40_000 }, async () => {
  const html = await printGroup({
    flag: true,
    first: { planned: 2, picked: 1, receipts: [DOC.P96], places: [sharedPlace] },
    second: { planned: 2, picked: 0, receipts: [DOC.P96], places: [sharedPlace] },
  })
  expectWalk(sourcesCell(html), [
    { header: docHeader(DOC.P96), line: 'Короб №3 · BC-3 · Ж-1-7: 5 шт.' },
  ])
  expect(html).toMatch(/<td class="quantity">4<\/td>/)
  expect(html).toMatch(/<td class="quantity">1 \/ 4<\/td>/)
})

it('C11: два разных короба без ШК в одной приёмке дают две строки, даже с одинаковым текстом', { timeout: 40_000 }, async () => {
  const noBarcodeBox = (id: string) => ({ cell: 'Ж-1-7', box: { id, number: null, barcode: null }, qty: 5, doc: DOC.P96 })
  const html = await printGroup({
    flag: true,
    first: { planned: 2, picked: 0, receipts: [DOC.P96], places: [noBarcodeBox('box-a'), noBarcodeBox('box-b')] },
    second: { planned: 2, picked: 0, receipts: [DOC.P96], places: [] },
  })
  const line = 'Короб · ШК не указан · Ж-1-7: 5 шт.'
  expectWalk(sourcesCell(html), [
    { header: docHeader(DOC.P96), line },
    { header: docHeader(DOC.P96), line },
  ])
})

it('C8 (группа): лист групповой сборки для не-Империи печатается байт в байт как раньше', { timeout: 40_000 }, async () => {
  const html = await printGroup({
    flag: false,
    first: { planned: 2, picked: 1, receipts: [DOC.P96], places: [sharedPlace] },
    second: { planned: 2, picked: 0, receipts: [DOC.P96], places: [sharedPlace] },
  })
  await expect(normalizeSheet(html)).toMatchFileSnapshot('./wms710-snapshots/group-flag-off.html')
})
