// @vitest-environment jsdom
// WMS-710: лист подбора одной поставки. Настоящая рабочая область печатает
// лист через кнопку «Печать листа подбора»; API подменён фикстурами, окно печати —
// заглушкой, которая запоминает HTML. Признак Империи передаётся пропсом
// pickListTabOrder (интерфейс зафиксирован в fbsPickList.wms710.fixture.ts).
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { act } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, beforeAll, beforeEach, expect, it, vi } from 'vitest'
import { FfFbsSupplyWorkspace } from './FfFbsSupplyWorkspace'
import { saveFbsWorkspaceStage } from './fbsWorkspaceStage'
import {
  DOC,
  SCENARIO_C1,
  SUPPLY_ID,
  baseWorkspace,
  docHeader,
  ozonWorkspace,
  expectWalk,
  fakePrintWindow,
  jsonResponse,
  normalizeSheet,
  pickOptionsResponse,
  pickingContextResponse,
  sheetHtml,
  sourcesCell,
  withoutSources,
  type Scenario,
} from './fbsPickList.wms710.fixture'

// Настоящие функции вызываются через обёртки, которые запоминают вызов (C19).
// Обёртки не зависят от реализации vi.fn: restoreAllMocks не сбрасывает их.
const pickRowsSpy = vi.hoisted(() => ({ cellPickRowsOf: vi.fn(), placesOf: vi.fn() }))
vi.mock('../ff/unload-pick/pickRows', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../ff/unload-pick/pickRows')>()
  return {
    ...actual,
    cellPickRowsOf: (...args: Parameters<typeof actual.cellPickRowsOf>) => {
      pickRowsSpy.cellPickRowsOf(...args)
      return actual.cellPickRowsOf(...args)
    },
    placesOf: (...args: Parameters<typeof actual.placesOf>) => {
      pickRowsSpy.placesOf(...args)
      return actual.placesOf(...args)
    },
  }
})

const proof = JSON.parse(readFileSync(resolve(
  process.cwd(), '../docs/reviews/wms662-663-priority/c19-run-37440990542/facts.json',
), 'utf8')) as { http: Array<{ url: string; status: number; body: unknown }> }
const authHeaders = () => ({ Authorization: 'Bearer wms710' })
const originalFetch = globalThis.fetch
const unexpectedReads: string[] = []
let host: HTMLDivElement
let root: Root
let requests: string[]
let scenarioState: Scenario
let pickOptionsFails: boolean
let marketplaceState: 'wb' | 'ozon' = 'wb'

/** Ожидаемый обход C1: четыре места товара, разные документы, сортировка последней. */
const WALK_C1 = [
  { header: docHeader(DOC.P96), line: 'Короб №7 · BC-7 · А 1.2: 2 шт.' },
  { header: docHeader(DOC.P80), line: 'Короб №3 · BC-3 · Ж-1-7: 5 шт.' },
  { header: docHeader(DOC.V12), line: 'Россыпью · Ж-1-14: 3 шт.' },
  { header: 'Без привязки к документу:', line: 'Россыпью: 1 шт.' },
]

beforeAll(() => {
  ;(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true
})

beforeEach(() => {
  requests = []
  unexpectedReads.length = 0
  window.sessionStorage.clear()
  window.localStorage.clear()
  globalThis.fetch = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = new URL(typeof input === 'string' ? input : input instanceof URL ? input.href : input.url, 'http://wms.test')
    const method = (init?.method ?? (input instanceof Request ? input.method : 'GET')).toUpperCase()
    requests.push(`${method} ${url.pathname}`)
    if (method !== 'GET') throw new Error(`Unexpected mutation: ${method} ${url.pathname}`)
    if (url.pathname.endsWith(`/${SUPPLY_ID}/workspace`)) {
      return jsonResponse(marketplaceState === 'ozon' ? ozonWorkspace() : baseWorkspace())
    }
    if (url.pathname.endsWith('/pick-options')) {
      return pickOptionsFails ? jsonResponse({ detail: 'synthetic pick-options failure' }, 500) : pickOptionsResponse(scenarioState)
    }
    if (url.pathname.endsWith('/picking-context')) return pickingContextResponse(scenarioState)
    const saved = proof.http.find((entry) => new URL(entry.url).pathname === url.pathname && entry.status === 200)
    if (saved) return jsonResponse(saved.body)
    unexpectedReads.push(url.pathname)
    return jsonResponse({ detail: 'не подготовлено в тесте' }, 404)
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

function printButton() {
  return document.querySelector<HTMLButtonElement>('[data-testid="fbs-pick-list-print"]')
}

/**
 * Открывает поставку на вкладке «Подбор», нажимает печать и возвращает HTML листа.
 * callsAtSheetWrite — сколько раз состав мест (cellPickRowsOf/placesOf) был вызван
 * между нажатием печати и записью листа: вкладка при этом не перерисовывается.
 */
async function printSheet(options: {
  flag: boolean
  scenario: Scenario
  pickOptionsFails?: boolean
  marketplace?: 'wb' | 'ozon'
}) {
  scenarioState = options.scenario
  pickOptionsFails = options.pickOptionsFails ?? false
  marketplaceState = options.marketplace ?? 'wb'
  act(() => root.unmount())
  root = createRoot(host)
  window.sessionStorage.clear()
  saveFbsWorkspaceStage(SUPPLY_ID, 'picking')
  const written: string[] = []
  let callsAtSheetWrite = -1
  const placeCalls = () => pickRowsSpy.cellPickRowsOf.mock.calls.length + pickRowsSpy.placesOf.mock.calls.length
  vi.spyOn(window, 'open').mockReturnValue(fakePrintWindow(written, (html) => {
    if (html.includes('<table>') && callsAtSheetWrite < 0) callsAtSheetWrite = placeCalls()
  }) as unknown as Window)
  // Флаг передаётся отдельным объектом: пока пропса нет в компоненте, он просто не используется.
  const flagProps = { pickListTabOrder: options.flag }
  await act(async () => root.render(
    <MemoryRouter>
      <FfFbsSupplyWorkspace token="wms710" authHeaders={authHeaders} supplyId={SUPPLY_ID}
        open onClose={() => undefined} {...flagProps} />
    </MemoryRouter>,
  ))
  await vi.waitFor(() => {
    expect(requests.some((request) => request.endsWith(`/${SUPPLY_ID}/workspace`))).toBe(true)
    expect(printButton()).not.toBeNull()
  }, { timeout: 10_000 })
  await act(async () => { await new Promise((resolveTimer) => setTimeout(resolveTimer, 300)) })
  pickRowsSpy.cellPickRowsOf.mockClear()
  pickRowsSpy.placesOf.mockClear()
  await act(async () => printButton()!.click())
  await vi.waitFor(() => expect(sheetHtml(written)).toBeDefined(), { timeout: 15_000 })
  return { html: sheetHtml(written)!, bodyText: document.body.textContent ?? '', callsAtSheetWrite }
}

it('C1: места одного товара идут в порядке обхода вкладки (четыре места, разные документы)', { timeout: 30_000 }, async () => {
  const { html } = await printSheet({ flag: true, scenario: SCENARIO_C1 })
  expectWalk(sourcesCell(html), WALK_C1)
})

it('C12: поставка Ozon у Империи — тот же порядок мест, что у вкладки Ozon', { timeout: 30_000 }, async () => {
  const { html } = await printSheet({ flag: true, scenario: SCENARIO_C1, marketplace: 'ozon' })
  expectWalk(sourcesCell(html), WALK_C1)
})

it('C2: ячейки сравниваются по числам внутри кода: Ж-1-7 раньше Ж-1-14', { timeout: 30_000 }, async () => {
  const { html } = await printSheet({
    flag: true,
    scenario: {
      planned: 2,
      picked: 0,
      receipts: [DOC.P96],
      places: [
        { cell: 'Ж-1-14', qty: 3, doc: DOC.P96 },
        { cell: 'Ж-1-7', qty: 4, doc: DOC.P96 },
      ],
    },
  })
  expectWalk(sourcesCell(html), [
    { header: docHeader(DOC.P96), line: 'Россыпью · Ж-1-7: 4 шт.' },
    { header: docHeader(DOC.P96), line: 'Россыпью · Ж-1-14: 3 шт.' },
  ])
})

it('C3: место с нулевым остатком и снятым количеством печатается строкой «0 шт.» на своём месте', { timeout: 30_000 }, async () => {
  const { html } = await printSheet({
    flag: true,
    scenario: {
      planned: 2,
      picked: 2,
      receipts: [DOC.P96],
      places: [
        { cell: 'Ж-1-7', box: { id: 'box-3', number: 3, barcode: 'BC-3' }, qty: 0, picked: 2, doc: null },
        { cell: 'Ж-1-14', qty: 3, doc: DOC.P96 },
      ],
    },
  })
  expectWalk(sourcesCell(html), [
    { line: /^.*Ж-1-7.*: 0 шт\.$/ },
    { header: docHeader(DOC.P96), line: 'Россыпью · Ж-1-14: 3 шт.' },
  ], { strictHeaders: false })
})

it('C4: заголовок каждого документа перед его местами, с датой для приёмки и возврата', { timeout: 30_000 }, async () => {
  const { html } = await printSheet({
    flag: true,
    scenario: {
      planned: 2,
      picked: 0,
      receipts: [DOC.P96, DOC.V12],
      places: [
        { cell: 'А 1.2', box: { id: 'box-7', number: 7, barcode: 'BC-7', pallet: 'PAL-131' }, qty: 2, doc: DOC.P96 },
        { cell: 'Ж-1-14', qty: 3, doc: DOC.V12 },
        { cell: 'Без ячеек', qty: 1, doc: null },
      ],
    },
  })
  expectWalk(sourcesCell(html), [
    { header: docHeader(DOC.P96), line: 'Короб №7 · BC-7 · А 1.2: 2 шт.' },
    { header: docHeader(DOC.V12), line: 'Россыпью · Ж-1-14: 3 шт.' },
    { header: 'Без привязки к документу:', line: 'Россыпью: 1 шт.' },
  ])
})

it('C6: приёмка без мест на листе не печатается, даже с историей', { timeout: 30_000 }, async () => {
  const { html } = await printSheet({
    flag: true,
    scenario: {
      planned: 2,
      picked: 0,
      receipts: [DOC.P80, DOC.P96],
      places: [{ cell: 'Ж-1-7', box: { id: 'box-3', number: 3, barcode: 'BC-3' }, qty: 2, doc: DOC.P96 }],
    },
  })
  expectWalk(sourcesCell(html), [
    { header: docHeader(DOC.P96), line: 'Короб №3 · BC-3 · Ж-1-7: 2 шт.' },
  ])
})

it('C6 и C20(в): товар не подобран и мест с остатком нет — «Нет текущего остатка», без заголовков приёмок', { timeout: 30_000 }, async () => {
  const { html } = await printSheet({
    flag: true,
    scenario: { planned: 2, picked: 0, receipts: [DOC.P80], places: [] },
  })
  expect(sourcesCell(html).trim()).toBe('Нет текущего остатка')
})

it('C20(а): место «Уже подобрано» на сортировке на лист не попадает', { timeout: 30_000 }, async () => {
  const { html } = await printSheet({
    flag: true,
    scenario: {
      planned: 2,
      picked: 2,
      receipts: [DOC.P96, DOC.P80],
      places: [
        { cell: 'Ж-1-7', box: { id: 'box-3', number: 3, barcode: 'BC-3' }, qty: 3, picked: 2, doc: DOC.P96 },
        { cell: 'Без ячеек', qty: 1, doc: DOC.P80 },
      ],
    },
  })
  expectWalk(sourcesCell(html), [
    { header: docHeader(DOC.P96), line: 'Короб №3 · BC-3 · Ж-1-7: 3 шт.' },
  ])
})

it('C20(б): товар подобран полностью, все места ушли в «Уже подобрано» — пишется «Подобрано»', { timeout: 30_000 }, async () => {
  const { html } = await printSheet({
    flag: true,
    scenario: {
      planned: 2,
      picked: 2,
      receipts: [DOC.P96],
      places: [{ cell: 'Без ячеек', qty: 2, doc: DOC.P96 }],
    },
  })
  expect(sourcesCell(html).trim()).toBe('Подобрано')
})

it('C14: подобрано в листе берётся из ответа сервера на момент печати', { timeout: 30_000 }, async () => {
  const { html } = await printSheet({
    flag: true,
    scenario: {
      planned: 2,
      picked: 1,
      receipts: [DOC.P96],
      places: [{ cell: 'Ж-1-7', box: { id: 'box-3', number: 3, barcode: 'BC-3' }, qty: 2, picked: 1, doc: DOC.P96 }],
    },
  })
  expect(html).toMatch(/<td class="quantity">1 \/ 2<\/td>/)
})

it('C7: кроме колонки «Поставка / ячейка / короб» лист Империи совпадает с листом до изменения', { timeout: 30_000 }, async () => {
  const before = await printSheet({ flag: false, scenario: SCENARIO_C1 })
  const after = await printSheet({ flag: true, scenario: SCENARIO_C1 })
  expect(withoutSources(normalizeSheet(after.html))).toBe(withoutSources(normalizeSheet(before.html)))
})

it('C8: лист для не-Империи печатается байт в байт как раньше (WB, одиночная поставка)', { timeout: 30_000 }, async () => {
  const { html } = await printSheet({ flag: false, scenario: SCENARIO_C1 })
  await expect(normalizeSheet(html)).toMatchFileSnapshot('./wms710-snapshots/c1-flag-off.html')
})

it('C20(г): для не-Империи пустой товар печатается как раньше', { timeout: 30_000 }, async () => {
  const { html } = await printSheet({
    flag: false,
    scenario: {
      planned: 2,
      picked: 2,
      receipts: [DOC.P96],
      places: [{ cell: 'Без ячеек', qty: 2, doc: DOC.P96 }],
    },
  })
  await expect(normalizeSheet(html)).toMatchFileSnapshot('./wms710-snapshots/c20b-flag-off.html')
})

it('C13: при ошибке pick-options лист печатается прежним порядком с прежним предупреждением', { timeout: 30_000 }, async () => {
  const failing = await printSheet({ flag: true, scenario: SCENARIO_C1, pickOptionsFails: true })
  const baseline = await printSheet({ flag: false, scenario: SCENARIO_C1, pickOptionsFails: true })
  expect(normalizeSheet(failing.html)).toBe(normalizeSheet(baseline.html))
  expect(failing.bodyText).toContain('Не удалось получить ячейки и тару — лист подбора напечатан без них.')
})

it('C19: лист берёт состав и порядок мест той же функцией, что вкладка (cellPickRowsOf/placesOf)', { timeout: 30_000 }, async () => {
  const { callsAtSheetWrite } = await printSheet({ flag: true, scenario: SCENARIO_C1 })
  expect(callsAtSheetWrite).toBeGreaterThan(0)
})
