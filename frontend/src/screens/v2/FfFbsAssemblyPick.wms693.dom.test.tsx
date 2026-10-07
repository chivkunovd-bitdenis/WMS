// @vitest-environment jsdom
import { act } from 'react'
import { createRoot } from 'react-dom/client'
import { beforeAll, expect, it, vi } from 'vitest'
import { FfFbsAssemblyPick } from './FfFbsAssemblyPick'

beforeAll(() => { (globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true })
function json(body: unknown, status = 200) { return new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } }) }

for (const status of [503, 409]) it(`carries a group save ${status} failure across quick close/reopen without unhandled rejection`, async () => {
  const supplyId = `review-save-${status}`
  const host = document.createElement('div'); document.body.appendChild(host)
  let root = createRoot(host)
  const posts: unknown[] = []
  let reply!: (response: Response) => void
  let serverPicked = 0
  const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input)
    if (url.includes('/pick/set')) {
      posts.push(JSON.parse(String(init?.body)))
      return new Promise<Response>((resolve) => { reply = resolve })
    }
    if (url.includes('/pick-options')) return json([{
      product_id: 'p', sku_code: 'SKU', product_name: 'Товар', seller_article: 'ART', barcode: '123456', planned_qty: 20, picked_qty: serverPicked,
      locations: [{ storage_location_id: 'c', location_code: 'C', quantity: 30, reserved: 0, available: 30 - serverPicked, picked: serverPicked,
        sources: [{ quantity: 30, available: 30 - serverPicked, is_loose: true, source_label: 'Россыпью', container_path: [], picked: serverPicked }] }],
    }])
    return json([])
  })
  vi.stubGlobal('fetch', fetchMock)
  const render = async () => act(async () => { root.render(<FfFbsAssemblyPick token="t" supplies={[{ id: supplyId, sellerId: 'seller' }]} />) })
  try {
    await render()
    await act(async () => new Promise((resolve) => setTimeout(resolve, 30)))
    const input = host.querySelector<HTMLInputElement>('input[data-testid="pick-place-qty-p-cell:c"]')!
    expect(input).toBeTruthy()
    await act(async () => {
      Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value')!.set!.call(input, '12')
      input.dispatchEvent(new Event('input', { bubbles: true }))
    })
    expect(posts).toHaveLength(0)
    await act(async () => root.unmount())
    expect(posts).toEqual([expect.objectContaining({ quantity: 12, expected_quantity: 0 })])
    root = createRoot(host)
    await render()
    expect(host.textContent).toContain('Загружаем подбор')
    serverPicked = status === 409 ? 2 : 0
    await act(async () => {
      reply(status === 409
        ? json({ detail: { code: 'pick_quantity_changed', message: 'Количество изменилось.' } }, 409)
        : json({ detail: 'Тестовый отказ сохранения' }, 503))
    })
    await act(async () => new Promise((resolve) => setTimeout(resolve, 30)))
    expect(host.textContent).toContain(status === 409 ? 'Количество товара в источнике изменилось' : 'Тестовый отказ сохранения')
    expect(host.querySelector('input[data-testid="pick-place-qty-p-cell:c"]')).toBeNull()
    expect(posts).toHaveLength(1)
  } finally {
    await act(async () => root.unmount()); host.remove(); vi.unstubAllGlobals()
  }
})
