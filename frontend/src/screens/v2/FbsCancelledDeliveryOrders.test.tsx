// @vitest-environment jsdom
import { act } from 'react'
import { createRoot } from 'react-dom/client'
import { expect, it } from 'vitest'
import { FbsCancelledDeliveryOrders } from './FbsCancelledDeliveryOrders'

it('keeps 200 cancelled orders collapsed and reveals their product and box in a bounded list', async () => {
  ;(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true
  const host = document.createElement('div')
  document.body.append(host)
  const root = createRoot(host)
  const orders = Array.from({ length: 200 }, (_, i) => ({
    order_id: `order-${i}`, wb_order_id: 530000 + i, article: `ART-${i}`,
    product_name: `Товар ${i}`, boxes: [{ box_id: `box-${i}`, box_number: i + 1, box_barcode: `BOX-${i}` }],
  }))
  try {
    await act(async () => root.render(<FbsCancelledDeliveryOrders orders={orders} />))
    const toggle = host.querySelector<HTMLElement>('[data-testid="fbs-cancelled-delivery-toggle"]')!
    expect(toggle.textContent).toContain('Отменённые заказы')
    expect(toggle.textContent).toContain('200 заказов')
    expect(toggle.getAttribute('aria-expanded')).toBe('false')
    expect(host.querySelector('#fbs-cancelled-delivery-orders')).toBeNull()
    expect(host.textContent).not.toContain('530000')
    await act(async () => toggle.click())
    const list = host.querySelector<HTMLElement>('#fbs-cancelled-delivery-orders')!
    expect(toggle.getAttribute('aria-expanded')).toBe('true')
    expect(list.children).toHaveLength(200)
    expect(list.firstElementChild?.textContent).toContain('WB 530000 · ART-0 · Товар 0 · Короб 1 (BOX-0)')
    expect(list.lastElementChild?.textContent).toContain('WB 530199 · ART-199 · Товар 199 · Короб 200 (BOX-199)')
    expect(getComputedStyle(list).maxHeight).toBe('220px')
    expect(getComputedStyle(list).overflowY).toBe('auto')
    await act(async () => { toggle.click(); await new Promise((resolve) => setTimeout(resolve, 350)) })
    expect(toggle.getAttribute('aria-expanded')).toBe('false')
  } finally {
    await act(async () => root.unmount())
    host.remove()
  }
})
