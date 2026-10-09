// @vitest-environment jsdom
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { act } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { afterEach, beforeAll, beforeEach, expect, it, vi } from 'vitest'
import { FfFbsSupplyWorkspace } from './FfFbsSupplyWorkspace'
import type { FbsWorkspace } from './fbsApi'
import { saveFbsWorkspaceStage } from './fbsWorkspaceStage'

// PDF printing is outside this read-only scenario; the existing shared install
// lacks pdf-lib. Observe the entry point instead of installing dependencies.
const printTape = vi.hoisted(() => vi.fn())
vi.mock('./fbsPdfPrintTape', () => ({ buildFbsPdfPrintTape: printTape }))

// R3/R12/C19: replay the already accepted HTTP evidence, not a new wire contract.
// The real workspace, composition table, history and status labels are rendered.
const proof = JSON.parse(readFileSync(resolve(
  process.cwd(), '../docs/reviews/wms662-663-priority/c19-run-37440990542/facts.json',
), 'utf8')) as { http: Array<{ url: string; status: number; body: unknown }> }
const workspaces = proof.http.filter((entry) => entry.url.endsWith('/workspace'))
const partial = workspaces.find((entry) => (entry.body as FbsWorkspace).supply.status === 'assembling')!.body as FbsWorkspace
const full = workspaces.find((entry) => (entry.body as FbsWorkspace).supply.status === 'in_delivery')!.body as FbsWorkspace
const supplyId = partial.supply.id
const authHeaders = () => ({ Authorization: 'Bearer c19-fixture' })
const originalFetch = globalThis.fetch
let current: FbsWorkspace
let requests: string[]
let stickerPrepareBodies: unknown[]
let workspaceResponses: Array<{ status: number; body: FbsWorkspace }>
let host: HTMLDivElement
let root: Root

beforeAll(() => {
  ;(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true
})

beforeEach(() => {
  current = partial
  requests = []
  stickerPrepareBodies = []
  workspaceResponses = []
  window.sessionStorage.clear()
  window.localStorage.clear()
  // The operator chose packing; an assembling parent must not force picking.
  saveFbsWorkspaceStage(supplyId, 'packing')
  vi.spyOn(window, 'open').mockReturnValue(null)
  vi.spyOn(window, 'print').mockImplementation(() => undefined)
  globalThis.fetch = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = new URL(typeof input === 'string' ? input : input instanceof URL ? input.href : input.url, 'http://wms.test')
    const method = (init?.method ?? (input instanceof Request ? input.method : 'GET')).toUpperCase()
    requests.push(`${method} ${url.pathname}`)
    // Opening the historical assembling fixture may request missing stickers.
    // Stop that external operation at a synthetic 503 so this test remains
    // read-only; all other non-read operations remain fail-closed.
    if (method === 'POST' && url.pathname.endsWith('/print-assets')) {
      stickerPrepareBodies.push(typeof init?.body === 'string' ? JSON.parse(init.body) as unknown : undefined)
      return new Response(JSON.stringify({ detail: 'synthetic stop before sticker or task mutation' }), {
        status: 503, headers: { 'Content-Type': 'application/json' },
      })
    }
    if (method !== 'GET') throw new Error(`Unexpected mutation: ${method} ${url.pathname}`)
    const saved = proof.http.find((entry) => new URL(entry.url).pathname === url.pathname)
    if (!saved) throw new Error(`Unexpected read: ${url.pathname}`)
    const body = url.pathname.endsWith('/workspace') ? current : saved.body
    if (url.pathname.endsWith('/workspace')) workspaceResponses.push({ status: saved.status, body: body as FbsWorkspace })
    return new Response(JSON.stringify(body), { status: saved.status, headers: { 'Content-Type': 'application/json' } })
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

async function render(open = true) {
  await act(async () => root.render(
    <FfFbsSupplyWorkspace token="c19-fixture" authHeaders={authHeaders} supplyId={supplyId}
      open={open} onClose={() => undefined} />,
  ))
}

async function click(element: HTMLElement) {
  await act(async () => element.click())
}

function tab(label: string) {
  return [...document.querySelectorAll<HTMLElement>('[role="tab"]')]
    .find((element) => element.textContent?.startsWith(label))!
}


async function checkComposition(
  phase: 'partial' | 'full', checkpoint: string, requestStart: number, prepareStart: number, responseStart: number,
) {
  const readiness = () => ({
    requests: requests.slice(requestStart),
    workspaceResponses: workspaceResponses.slice(responseStart).map(({ status, body }) => ({
      status, supplyStatus: body.supply.status, taskId: body.supply.packaging_task_id,
      stickerCodes: body.orders.map((order) => order.sticker.code),
    })),
    activeProgress: document.querySelector('[role="progressbar"]:not([aria-valuenow])') !== null,
    orderRows: partial.orders.map((order) => Boolean(document.querySelector(`[data-order-id="${order.id}"]`))),
    savedStage: window.sessionStorage.getItem(`wms:fbs:${supplyId}:stage`),
  })
  await vi.waitFor(() => {
    expect(requests.slice(requestStart).some((request) => request === `GET /api/operations/fbs-supplies/${supplyId}/workspace`),
      JSON.stringify(readiness())).toBe(true)
    expect(document.querySelector('[role="progressbar"]:not([aria-valuenow])'), JSON.stringify(readiness())).toBeNull()
    for (const order of partial.orders) {
      expect(document.querySelector(`[data-order-id="${order.id}"]`), JSON.stringify(readiness())).not.toBeNull()
    }
  }, { timeout: 3_000 })
  const appliedResponse = workspaceResponses.slice(responseStart).at(-1)
  expect(appliedResponse?.status, `${checkpoint}: fresh workspace GET response`).toBe(200)
  expect(appliedResponse?.body.supply.status, `${checkpoint}: workspace response status`).toBe(phase === 'partial' ? 'assembling' : 'in_delivery')
  expect(tab('Упаковка и маркировка').getAttribute('aria-selected'), `${checkpoint}: no return to picking`).toBe('true')
  // This existing message describes the WHOLE supply, not preparation or picking.
  expect(document.body.textContent?.includes('Поставка уже передана в WB'), `${checkpoint}: parent completion`)
    .toBe(phase === 'full')
  // WMS-723: the «Состав» tab is gone by owner decision. The identity of every
  // order (WB order number, row, selection label) is read where the supply
  // composition is now shown: the rows of the selected «Упаковка и маркировка» tab.
  const rows = [...document.querySelectorAll<HTMLElement>('[data-order-id]')]
  expect(rows, `${checkpoint}: exactly the two supply orders`).toHaveLength(2)
  expect(tab('Состав'), `${checkpoint}: no «Состав» tab`).toBeUndefined()
  for (const orderId of [662000, 662001]) {
    const fixtureOrder = partial.orders.find((order) => order.wb_order_id === orderId)!
    expect(fixtureOrder, `${checkpoint}: fixture order ${orderId}`).toBeDefined()
    const row = rows.find((element) => element.getAttribute('data-order-id') === fixtureOrder.id)!
    expect(row, `${checkpoint}: order ${orderId} row is bound to its own order id`).toBeDefined()
    expect(row.textContent, `${checkpoint}: order ${orderId} number`).toContain(`заказ ${orderId}`)
    const otherId = orderId === 662000 ? 662001 : 662000
    expect(row.textContent, `${checkpoint}: order ${orderId} row does not carry ${otherId}`).not.toContain(`заказ ${otherId}`)
    expect(row.querySelector(`input[aria-label="Выбрать заказ ${orderId}"]`), `${checkpoint}: order ${orderId} selection control`).not.toBeNull()
  }
  // Picking stays independent of the parent supply status: what the operator sees
  // on «Подбор» is the real picking screen, and both orders are still to be picked
  // (2 of 2 left, nothing taken) in the partial and in the full phase, after open,
  // reopen and page refresh.
  await click(tab('Подбор'))
  await vi.waitFor(() => {
    expect(document.querySelector('[data-testid="fbs-pick-unified"]')?.textContent ?? '', `${checkpoint}: picking screen`)
      .toMatch(/осталось снять из 2 по плану/)
  }, { timeout: 3_000 })
  const pickingText = document.querySelector('[data-testid="fbs-pick-unified"]')!.textContent ?? ''
  expect(pickingText, `${checkpoint}: both orders still wait for picking`).toMatch(/2\s*штук осталось снять из 2 по плану/)
  expect(pickingText, `${checkpoint}: picking is not shown as finished`).not.toMatch(/Все товары подобраны|0\s*штук осталось/)
  await click(tab('Упаковка и маркировка'))
  expect(tab('Упаковка и маркировка').getAttribute('aria-selected'), `${checkpoint}: back on packing`).toBe('true')
  // Reuse the real history with its saved creation event, without inventing events.
  await click(document.querySelector<HTMLElement>('[data-testid="fbs-supply-history-open"]')!)
  expect(document.querySelector('[data-testid="fbs-supply-history-timeline"]')?.textContent).toContain('Поставка создана')
  const history = document.querySelector<HTMLElement>('[data-testid="fbs-supply-history"]')!
  await click([...history.querySelectorAll<HTMLElement>('button')].find((element) => element.textContent === 'Закрыть')!)
  await act(async () => { await new Promise((resolve) => setTimeout(resolve, 250)) })
  await click(tab('Упаковка и маркировка'))
  const writes = requests.slice(requestStart).filter((request) => !request.startsWith('GET '))
  if (phase === 'partial') {
    expect(writes).toEqual([
      `POST /api/operations/fbs-supplies/${supplyId}/print-assets`,
    ])
    expect(stickerPrepareBodies.slice(prepareStart)).toEqual([{
      kind: 'order_sticker', order_ids: partial.orders.map((order) => order.id), retry_missing: true,
    }])
  } else {
    expect(writes).toEqual([])
  }
  expect(requests.slice(requestStart).some((request) => /deliver|ship|order-print-tape|print-direct|stock|inventory|pick-commit/.test(request))).toBe(false)
  expect(window.open).not.toHaveBeenCalled()
  expect(window.print).not.toHaveBeenCalled()
  expect(printTape).not.toHaveBeenCalled()
}

it('C19: partial → full remains order-specific after reopen/page refresh; picking and reads stay unchanged', { timeout: 60_000 }, async () => {
  const immutableProof = JSON.stringify(proof)
  for (const phase of ['partial', 'full'] as const) {
    current = phase === 'partial' ? partial : full
    // Both states come from the same real document; no fixture state is inferred from picking.
    expect(current.supply.id).toBe(supplyId)
    expect(current.orders.map((order) => order.pick.status)).toEqual(['pending', 'pending'])
    const openRequestStart = requests.length
    const openPrepareStart = stickerPrepareBodies.length
    const openResponseStart = workspaceResponses.length
    await render(false)
    await render()
    await checkComposition(phase, `${phase}: open`, openRequestStart, openPrepareStart, openResponseStart)
    const beforeReopen = requests.filter((request) => request.endsWith('/workspace')).length
    const reopenRequestStart = requests.length
    const reopenPrepareStart = stickerPrepareBodies.length
    const reopenResponseStart = workspaceResponses.length
    await render(false)
    await render()
    expect(requests.filter((request) => request.endsWith('/workspace')).length).toBeGreaterThan(beforeReopen)
    await checkComposition(phase, `${phase}: reopen`, reopenRequestStart, reopenPrepareStart, reopenResponseStart)
    // Page refresh: discard all React state, retain the existing browser session storage,
    // and GET the saved server result again. No Mac browser or local API is used.
    act(() => root.unmount())
    root = createRoot(host)
    const beforeRefresh = requests.filter((request) => request.endsWith('/workspace')).length
    const refreshRequestStart = requests.length
    const refreshPrepareStart = stickerPrepareBodies.length
    const refreshResponseStart = workspaceResponses.length
    await render()
    expect(requests.filter((request) => request.endsWith('/workspace')).length).toBeGreaterThan(beforeRefresh)
    await checkComposition(phase, `${phase}: page refresh`, refreshRequestStart, refreshPrepareStart, refreshResponseStart)
  }
  expect(JSON.stringify(proof)).toBe(immutableProof)
})
