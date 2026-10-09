// @vitest-environment jsdom
import { act } from 'react'
import { createRoot } from 'react-dom/client'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, beforeAll, expect, it, vi } from 'vitest'
import { FfUnloadPickPage } from './FfUnloadPickPage'
import { printFboPickHtml } from './fboPickPrint'

beforeAll(() => { (globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true })
afterEach(() => { vi.restoreAllMocks(); vi.useRealTimers() })

const json = (body: unknown) => new Response(JSON.stringify(body), { headers: { 'Content-Type': 'application/json' } })
const detail = (id: string) => ({
  id, marketplace: 'wb', display_number: id, document_number: id, seller_id: null,
  seller_name: `Селлер ${id}`, status: 'collecting', planned_shipment_date: null, lines: [],
})
async function settle() {
  for (let step = 0; step < 6; step++) await act(async () => { await new Promise((resolve) => setTimeout(resolve, 0)) })
}

it('WMS-731 R10/R14: delayed previous-document read cannot replace the newly opened shipment', async () => {
  let finishA!: (response: Response) => void
  const pendingA = new Promise<Response>((resolve) => { finishA = resolve })
  vi.spyOn(globalThis, 'fetch').mockImplementation(async (input) => {
    const path = new URL(String(input), 'http://wms.test').pathname.replace(/^\/api/, '')
    if (path === '/operations/marketplace-unload-requests/A') return pendingA
    if (path === '/operations/marketplace-unload-requests/B') return json(detail('B'))
    if (path.endsWith('/pick-options')) return json([])
    if (path.endsWith('/marking-codes')) return json({ items: [] })
    throw new Error(`Unexpected request: ${path}`)
  })
  const host = document.createElement('div')
  document.body.appendChild(host)
  const root = createRoot(host)
  try {
    await act(async () => { root.render(<MemoryRouter><FfUnloadPickPage token="t" requestId="A" /></MemoryRouter>) })
    await settle()
    await act(async () => { root.render(<MemoryRouter><FfUnloadPickPage token="t" requestId="B" /></MemoryRouter>) })
    await settle()
    expect(host.textContent).toContain('Отгрузка B')
    await act(async () => { finishA(json(detail('A'))) })
    await settle()
    expect(host.textContent).toContain('Отгрузка B')
    expect(host.textContent).not.toContain('Селлер A')
  } finally {
    act(() => root.unmount())
    host.remove()
  }
})

it('WMS-731 R12: a load error cancels the scheduled print and cannot print after failure', async () => {
  vi.useFakeTimers()
  const result = printFboPickHtml('<!doctype html><html><body><table></table></body></html>')
    .catch((error: Error) => error.message)
  const frame = document.querySelector('iframe')!
  const target = frame.contentWindow!
  const print = vi.spyOn(target, 'print').mockImplementation(() => undefined)
  vi.spyOn(target, 'focus').mockImplementation(() => undefined)
  try {
    frame.dispatchEvent(new Event('load'))
    frame.dispatchEvent(new Event('error'))
    expect(await result).toMatch(/Не удалось открыть печать/)
    await vi.advanceTimersByTimeAsync(101)
    expect(print).not.toHaveBeenCalled()
    expect(frame.isConnected).toBe(false)
  } finally {
    frame.remove()
  }
})

it('WMS-731 R8/R9: a product without locations retains actual picked quantity rather than boxed quantity', async () => {
  vi.spyOn(globalThis, 'fetch').mockImplementation(async (input) => {
    const path = new URL(String(input), 'http://wms.test').pathname.replace(/^\/api/, '')
    if (path === '/operations/marketplace-unload-requests/no-address') return json({
      ...detail('no-address'),
      lines: [{ id: 'line', product_id: 'product', sku_code: 'SKU', product_name: 'Без адресов', quantity: 10, picked_qty: 1 }],
    })
    if (path.endsWith('/pick-options')) return json([{
      product_id: 'product', sku_code: 'SKU', product_name: 'Без адресов', seller_article: null, barcode: null,
      planned_qty: 10, picked_qty: 4, boxed_qty: 1, locations: [],
    }])
    if (path.endsWith('/marking-codes')) return json({ items: [] })
    throw new Error(`Unexpected request: ${path}`)
  })
  const append = document.body.appendChild.bind(document.body)
  vi.spyOn(document.body, 'appendChild').mockImplementation(((node: Node) => {
    const added = append(node)
    if (node instanceof HTMLIFrameElement && node.contentWindow) {
      const target = node.contentWindow
      vi.spyOn(target, 'focus').mockImplementation(() => undefined)
      vi.spyOn(target, 'print').mockImplementation(() => { target.dispatchEvent(new Event('afterprint')) })
    }
    return added
  }) as typeof document.body.appendChild)
  const host = document.createElement('div')
  document.body.appendChild(host)
  const root = createRoot(host)
  let frame: HTMLIFrameElement | null = null
  try {
    await act(async () => { root.render(<MemoryRouter><FfUnloadPickPage token="t" requestId="no-address" /></MemoryRouter>) })
    await settle()
    const action = [...host.querySelectorAll('button')].find((button) => button.textContent === 'Печать листа подбора')!
    await act(async () => action.click())
    await settle()
    frame = document.querySelector('iframe')!
    const doc = new DOMParser().parseFromString(frame.srcdoc, 'text/html')
    // The missing source has no physical quantity. Plan and remaining still describe the product.
    const values = [...doc.querySelectorAll('tbody tr:first-child td')].map((cell) => cell.textContent)
    frame.dispatchEvent(new Event('load'))
    await act(async () => { await new Promise((resolve) => setTimeout(resolve, 150)) })
    expect(values.slice(-3)).toEqual(['—', '10', '6'])
    expect(doc.body.textContent).toContain('Нет на складе')
  } finally {
    act(() => root.unmount())
    host.remove()
    frame?.remove()
  }
})
