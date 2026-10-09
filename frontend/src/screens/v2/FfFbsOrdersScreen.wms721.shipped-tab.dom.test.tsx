// @vitest-environment jsdom
// WMS-721 C2, дефект ручной проверки 09.10.2026: вкладка «Отгруженные» должна показывать
// поставки из списка поставок. Экран для групп поставок параллельно запрашивал список
// заказов с status_group=shipped; бэкенд такую группу для заказов не знает и отвечает
// 400 invalid_status_group. Из-за общего Promise.all список поставок не обновлялся и
// в таблице оставались строки предыдущей вкладки.
// Граница — fetch: реальный fbsApi строит URL, ответы повторяют контракт бэкенда
// (список поставок знает shipped, список заказов — нет). Playwright и живой Ozon не участвуют.
import { act } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, beforeAll, beforeEach, expect, it, vi } from 'vitest'
import { FfFbsOrdersScreen } from './FfFbsOrdersScreen'

const SERVER_NOW = '2026-10-09T08:00:00Z'
const authHeaders = () => ({ Authorization: 'Bearer wms721-shipped-fixture' })
const originalFetch = globalThis.fetch

let root: Root
let host: HTMLDivElement
let requests: string[]

function supply(id: string, name: string, status: string) {
  return {
    id, marketplace: 'ozon', wb_supply_id: null, name, status,
    seller: { id: 'seller-721', name: 'Селлер 721' },
    wb_warehouse: { id: 11, name: 'Ozon Логистика' },
    wms_warehouse: { id: 'warehouse-721', name: 'Основной склад' },
    orders_count: 2, units_count: 2, picked_units_count: 2, boxes_count: 1,
    planned_shipment_date: null, can_add_orders: false,
  }
}

function json(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } })
}

// Ответы повторяют бэкенд: список поставок принимает shipped, список заказов отклоняет
// группу shipped кодом invalid_status_group (backend/app/services/fbs_worklist_service.py).
function backendFetch(input: RequestInfo | URL): Response | Promise<Response> {
  const href = input instanceof URL ? input.href : typeof input === 'string' ? input : input.url
  const url = new URL(href, 'http://wms.test')
  requests.push(`${url.pathname}${url.search}`)
  const group = url.searchParams.get('status_group')
  if (url.pathname.endsWith('/operations/fbs-supplies/worklist')) {
    const items = group === 'done'
      ? [supply('supply-721-done', 'Поставка Ozon 721 завершена', 'done')]
      : group === 'shipped'
        ? [supply('supply-721-shipped', 'Поставка Ozon 721 отгружена', 'shipped')]
        : []
    return json({ items, total: items.length, server_now: SERVER_NOW })
  }
  if (url.pathname.endsWith('/operations/fbs-orders/worklist')) {
    if (group === 'shipped') {
      return json({
        detail: { code: 'invalid_status_group', message: 'Некорректная группа статусов.', context: {}, retryable: false },
      }, 400)
    }
    return json({ total: 0, items: [], next_cursor: null, warehouse_options: [], server_now: SERVER_NOW })
  }
  if (url.pathname.endsWith('/warehouses')) return json([])
  if (url.pathname.endsWith('/operations/fbs-assembly-tasks')) return json({ items: [] })
  return json({ hours: 0, orders: 0, in12: 0, in24: 0, items: [], total: 0 })
}

beforeAll(() => {
  ;(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true
  Element.prototype.scrollIntoView = () => undefined
})
beforeEach(() => {
  window.localStorage.clear()
  window.sessionStorage.clear()
  requests = []
  host = document.createElement('div')
  document.body.appendChild(host)
  root = createRoot(host)
  globalThis.fetch = vi.fn(async (input: RequestInfo | URL) => backendFetch(input))
})
afterEach(async () => {
  await act(async () => { root.unmount() })
  host.remove()
  document.body.innerHTML = ''
  globalThis.fetch = originalFetch
})

async function mountScreen() {
  await act(async () => {
    root.render(<MemoryRouter><FfFbsOrdersScreen token="wms721" authHeaders={authHeaders}
      sellers={[{ id: 'seller-721', name: 'Селлер 721' }]} /></MemoryRouter>)
  })
}

const tabs = () => {
  const list = [...host.querySelectorAll<HTMLElement>('[role="tablist"]')]
    .find((node) => node.textContent?.includes('Новые'))!
  return [...list.querySelectorAll<HTMLElement>('[role="tab"]')]
}

async function clickTab(label: string) {
  await act(async () => { tabs().find((tab) => tab.textContent === label)!.click() })
}

// Ждём ответов fetch и перерисовки: каждый шаг идёт внутри act, как в соседних тестах.
async function settle(check: () => void, timeoutMs = 3_000) {
  const deadline = Date.now() + timeoutMs
  for (;;) {
    await act(async () => { await new Promise((resolve) => setTimeout(resolve, 20)) })
    try {
      check()
      return
    } catch (error) {
      if (Date.now() > deadline) throw error
    }
  }
}

const supplyRowIds = () => [...host.querySelectorAll<HTMLElement>('tbody tr[data-testid^="fbs-18-supply-"]')]
  .map((row) => row.dataset.testid!.replace('fbs-18-supply-', ''))

it('test_c2_shipped_tab_replaces_done_supplies_with_shipped_supply', async () => {
  await mountScreen()
  await clickTab('Завершённые')
  await settle(() => expect(supplyRowIds()).toEqual(['supply-721-done']))
  await clickTab('Отгруженные')
  await settle(() => expect(supplyRowIds()).toEqual(['supply-721-shipped']))
  const row = host.querySelector<HTMLElement>('[data-testid="fbs-18-supply-supply-721-shipped"]')!
  expect(row.querySelector('[data-testid="fbs-18-supply-status"]')?.textContent).toBe('Отгружена')
  expect(host.textContent).not.toContain('Отгруженных поставок нет')
})

it('test_c2_shipped_tab_sends_no_orders_worklist_request', async () => {
  await mountScreen()
  await clickTab('Отгруженные')
  await settle(() => expect(requests.some((request) => request.startsWith('/api/operations/fbs-supplies/worklist')
    && request.includes('status_group=shipped'))).toBe(true))
  expect(requests.filter((request) => request.startsWith('/api/operations/fbs-orders/worklist')
    && request.includes('status_group=shipped'))).toEqual([])
})
