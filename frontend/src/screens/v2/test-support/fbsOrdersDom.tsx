import { act } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { MemoryRouter } from 'react-router-dom'
import { ThemeProvider, type Theme } from '@mui/material/styles'
import { expect, vi } from 'vitest'
import { FfFbsOrdersScreen } from '../FfFbsOrdersScreen'
import type { FbsWorklistOrder } from '../fbsApi'

// These closed neighboring workspaces are outside the list operation under
// test. Keep the screen, rows, chips, photo and fbsApi HTTP adapter real.
vi.mock('../FfFbsSupplyWorkspace', () => ({ FfFbsSupplyWorkspace: () => null }))
vi.mock('../FfFbsSupplyAssembly', () => ({ FfFbsSupplyAssembly: () => null }))
vi.mock('../FbsCancelledAfterPackDialog', () => ({ FbsCancelledAfterPackDialog: () => null }))
vi.mock('../FbsSupplyCreateDialog', () => ({ FbsSupplyCreateDialog: () => null }))
vi.mock('../FbsSupplyGroupCreateDialog', () => ({ FbsSupplyGroupCreateDialog: () => null }))
vi.mock('../FbsPrintPreviewDialog', () => ({ FbsPrintPreviewDialog: () => null }))

export const SERVER_NOW = '2026-10-09T12:00:00.000Z'
export const SELLERS = [
  { id: 'seller-a', name: 'Селлер А' },
  { id: 'seller-b', name: 'Селлер Б' },
  { id: 'seller-zero', name: 'Селлер без заказов' },
]
export const AUTH_HEADERS = () => ({ Authorization: 'Bearer test-token' })

export function order(id = 'order-a'): FbsWorklistOrder {
  return {
    id, marketplace: 'wb', external_order_id: null, wb_order_id: 719001,
    status: 'new', wb_status: 'new', supplier_status: 'new',
    seller: SELLERS[0], wb_warehouse: { id: 101, name: 'Первый склад' },
    wms_warehouse: { id: 'warehouse', name: 'Фулфилмент' },
    product: {
      id: 'product', name: 'Товар WB', image_url: null, seller_article: 'ARTICLE-719',
      wb_article: 719, barcode: 'BAR-719', sku: 'DISTINCT-SKU-719', chrt_id: null,
      category: null, color: null, size: 'M',
    },
    positions: [], inventory: { available_unpacked: 10, locations: [] },
    buyer_type: 'individual', cargo_type: 'mgt', can_pvz: true, delivery_route: null,
    metadata: { required: [], optional: [], states: [], delivery_allowed: true, last_checked_at: null },
    sticker: { code: null, status: 'not_requested', asset_url: null, applied_at: null },
    pick: { status: 'pending', location_code: null, picked_at: null },
    pack: { status: 'pending', packed_at: null },
    created_at_wb: '2026-10-09T09:55:00.000Z', deadline_at: '2026-10-14T09:55:00.000Z',
    supply_id: null, selection_blockers: [],
  }
}

export function page(items: FbsWorklistOrder[], total = items.length) {
  return {
    items, total, next_cursor: null, server_now: SERVER_NOW,
    warehouse_options: [101, 202].map((id) => ({
      id: String(id), name: `Склад ${id}`, wb_warehouse: { id, name: `Склад ${id}` },
    })),
  }
}

export function json(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } })
}

export function installNetwork(read: (url: URL) => Response | Promise<Response>) {
  return vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = new URL(String(input), 'http://localhost')
    expect(init?.method ?? 'GET').toBe('GET')
    if (url.pathname.endsWith('/fbs/assembly-time')) return json({ hours: 0, orders: 0, in12: null, in24: null })
    if (url.pathname.endsWith('/operations/fbs-assembly-tasks')) return json({ items: [] })
    if (/\/operations\/fbs-sellers\/[^/]+\/warehouses$/.test(url.pathname)) return json([])
    // Neighboring list contracts do not supply a counts response. Give only
    // that new read a neutral fixture; WMS-716's explicit responses, failures
    // and delayed requests still go through the caller unchanged.
    if (url.pathname.endsWith('/fbs-orders/counts')) {
      let response: Response | Promise<Response>
      try { response = read(url) } catch (cause) {
        if (!(cause instanceof Error) || !cause.message.startsWith('Unexpected') || !cause.message.includes('/fbs-orders/counts')) throw cause
        return json({ tabs: { new: 0, active: 0, delivery: 0 }, sellers: {} })
      }
      return response
    }
    return read(url)
  })
}

export async function flush() {
  await act(async () => { for (let n = 0; n < 8; n += 1) await Promise.resolve() })
}

export async function mount(network: ReturnType<typeof installNetwork>, theme?: Theme) {
  ;(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true
  Object.defineProperty(HTMLElement.prototype, 'scrollIntoView', { configurable: true, value: vi.fn() })
  vi.stubGlobal('fetch', network)
  const host = document.createElement('div')
  document.body.append(host)
  const root: Root = createRoot(host)
  const screen = <MemoryRouter><FfFbsOrdersScreen token="test-token" authHeaders={AUTH_HEADERS} sellers={SELLERS} /></MemoryRouter>
  await act(async () => root.render(theme ? <ThemeProvider theme={theme}>{screen}</ThemeProvider> : screen))
  await flush()
  return async () => { await act(async () => root.unmount()); host.remove() }
}

export function headers(): string[] {
  return Array.from(document.querySelectorAll('thead th'), (cell) => cell.textContent?.trim() ?? '')
}

export function row(id = 'order-a'): HTMLTableRowElement {
  const element = document.querySelector(`[data-testid="fbs-order-${id}"]`)
  expect(element, `order ${id} is rendered`).toBeTruthy()
  return element as HTMLTableRowElement
}

export async function click(element: Element | null) {
  expect(element).toBeTruthy()
  await act(async () => (element as HTMLElement).click())
  await flush()
}

export async function tab(label: string) {
  const element = Array.from(document.querySelectorAll('[role="tab"]')).find((node) => node.textContent?.startsWith(label))
  await click(element ?? null)
}

export async function select(label: string, option: string) {
  const control = Array.from(document.querySelectorAll('[role="combobox"]')).find((node) => {
    const ids = node.getAttribute('aria-labelledby')?.split(' ') ?? []
    return ids.some((id) => document.getElementById(id)?.textContent === label)
  })
  expect(control, `filter ${label}`).toBeTruthy()
  await act(async () => control!.dispatchEvent(new MouseEvent('mousedown', { bubbles: true, button: 0 })))
  await flush()
  const item = Array.from(document.querySelectorAll('[role="option"]')).find((node) => node.textContent?.startsWith(option))
  await click(item ?? null)
}

export async function search(value: string) {
  const input = document.querySelector('[data-testid="fbs-worklist-search"] input') as HTMLInputElement
  await act(async () => {
    Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value')!.set!.call(input, value)
    input.dispatchEvent(new Event('input', { bubbles: true }))
  })
  await act(async () => input.dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter', bubbles: true })))
  await flush()
}

export async function refresh() {
  await click(Array.from(document.querySelectorAll('button')).find((node) => node.textContent === 'Обновить') ?? null)
}

/**
 * Значение свойства, которое выигрывает в браузере для узла. jsdom при getComputedStyle берёт
 * последнее совпавшее правило и не учитывает специфичность селектора, а в браузере выигрывает
 * правило с большей специфичностью (WMS-756: правило обёртки «фото img» 0,1,1 против правила
 * MUI Avatar 0,1,0). Здесь правила сравниваются по специфичности, при равенстве побеждает последнее.
 */
export function cascadedValue(node: Element, property: string): string {
  let best: { value: string; specificity: number; order: number } | null = null
  let order = 0
  for (const sheet of Array.from(document.styleSheets)) {
    for (const rule of Array.from(sheet.cssRules)) {
      order += 1
      const styled = rule as CSSStyleRule
      const value = styled.style?.getPropertyValue(property)
      if (typeof styled.selectorText !== 'string' || !value) continue
      for (const part of styled.selectorText.split(',')) {
        const selector = part.trim()
        let matches = false
        try { matches = node.matches(selector) } catch { matches = false }
        if (!matches) continue
        const specificity = specificityOf(selector)
        if (!best || specificity > best.specificity || (specificity === best.specificity && order > best.order)) {
          best = { value, specificity, order }
        }
      }
    }
  }
  return best?.value ?? ''
}

function specificityOf(selector: string): number {
  const ids = (selector.match(/#[\w-]+/g) ?? []).length
  const classes = (selector.match(/\.[\w-]+|\[[^\]]*\]|::?[\w-]+/g) ?? []).length
  const elements = (selector.replace(/\[[^\]]*\]/g, '').match(/(^|[\s>+~])[a-zA-Z][\w-]*/g) ?? []).length
  return ids * 10000 + classes * 100 + elements
}
