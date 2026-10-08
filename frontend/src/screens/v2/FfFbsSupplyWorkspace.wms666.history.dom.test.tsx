// @vitest-environment jsdom
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { act } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { afterEach, beforeAll, beforeEach, expect, it, vi } from 'vitest'
import { FfFbsSupplyWorkspace } from './FfFbsSupplyWorkspace'
import type { FbsWorkspace } from './fbsApi'
import { saveFbsWorkspaceStage } from './fbsWorkspaceStage'

const proof = JSON.parse(readFileSync(resolve(
  process.cwd(), '../docs/reviews/wms662-663-priority/c19-run-37440990542/facts.json',
), 'utf8')) as { http: Array<{ url: string; status: number; body: unknown }> }
const historical = proof.http
  .filter((entry) => entry.url.endsWith('/workspace'))
  .map((entry) => entry.body as FbsWorkspace)
  .find((workspace) => workspace.supply.status === 'in_delivery')!
const supplyId = historical.supply.id
const authHeaders = () => ({ Authorization: 'Bearer wms666-history-fixture' })
const originalFetch = globalThis.fetch
let workspace: FbsWorkspace
let requests: Array<{ method: string; path: string; body?: unknown }>
let createdStickerBatches: unknown[]
let startedWork: number
let root: Root
let host: HTMLDivElement

beforeAll(() => {
  ;(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true
})

beforeEach(() => {
  workspace = structuredClone(historical)
  requests = []
  createdStickerBatches = []
  startedWork = 0
  window.sessionStorage.clear()
  window.localStorage.clear()
  saveFbsWorkspaceStage(supplyId, 'packing')
  globalThis.fetch = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = new URL(typeof input === 'string' ? input : input instanceof URL ? input.href : input.url, 'http://wms.test')
    const method = (init?.method ?? (input instanceof Request ? input.method : 'GET')).toUpperCase()
    const body = typeof init?.body === 'string' ? JSON.parse(init.body) as unknown : undefined
    requests.push({ method, path: url.pathname, body })

    if (method === 'GET') {
      if (url.pathname.endsWith('/workspace')) {
        return new Response(JSON.stringify(workspace), { status: 200, headers: { 'Content-Type': 'application/json' } })
      }
      const saved = proof.http.find((entry) => new URL(entry.url).pathname === url.pathname)
      if (saved) return new Response(JSON.stringify(saved.body), { status: saved.status, headers: { 'Content-Type': 'application/json' } })
      throw new Error(`Unexpected read: ${url.pathname}`)
    }

    if (method === 'POST' && url.pathname.endsWith('/print-assets')) {
      createdStickerBatches.push(body)
      return new Response(JSON.stringify({ orders: [], order_errors: [], shortage: 0 }), {
        status: 200, headers: { 'Content-Type': 'application/json' },
      })
    }
    if (method === 'POST' && url.pathname.endsWith('/start-work')) {
      startedWork += 1
      return new Response(JSON.stringify({ detail: 'synthetic fixture stops before task creation' }), {
        status: 503, headers: { 'Content-Type': 'application/json' },
      })
    }
    throw new Error(`Unexpected mutation: ${method} ${url.pathname}`)
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

it('does not prepare missing stickers or start work when reopening a taskless delivered supply', { timeout: 15_000 }, async () => {
  expect(historical.supply.status).toBe('in_delivery')
  expect(historical.supply.packaging_task_id).toBeNull()
  expect(historical.orders.length).toBeGreaterThan(0)
  expect(historical.orders.every((order) => order.sticker.code === null)).toBe(true)
  const immutableHistorical = JSON.stringify(historical)

  await act(async () => {
    root.render(<FfFbsSupplyWorkspace token="wms666-history-fixture" authHeaders={authHeaders}
      supplyId={supplyId} open onClose={() => undefined} />)
    await new Promise((resolve) => setTimeout(resolve, 250))
  })

  expect(document.body.textContent).toContain('Упаковка и маркировка')
  expect(requests.filter((request) => request.method === 'GET').some((request) => request.path.endsWith('/workspace'))).toBe(true)
  expect(requests.filter((request) => request.method !== 'GET')).toEqual([])
  expect(createdStickerBatches).toEqual([])
  expect(startedWork).toBe(0)
  expect(workspace.supply.packaging_task_id).toBeNull()
  expect(workspace.orders.every((order) => order.sticker.code === null)).toBe(true)
  expect(JSON.stringify(historical)).toBe(immutableHistorical)
})
