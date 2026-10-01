// @vitest-environment jsdom
import { act } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { MarkingPrintDialog, type MarkingPrintContext } from './MarkingPrintDialog'
vi.mock('./MarkingLabelPreview', () => ({ MarkingLabelPreview: () => null }))
vi.mock('../utils/printMarkingCodeLabel', async (original) => ({
  ...await original<Record<string, unknown>>(), beginPrintUserGesture: vi.fn(), cancelPendingPrintWindow: vi.fn(),
}))
let root: Root
let host: HTMLDivElement
const print = vi.fn()
const label = { product_name: 'Куртка зимняя больших размеров с мехом и капюшоном', sku_code: 'FBS-611', barcode: '4600000000024', wb_size: '54' }
function context(): MarkingPrintContext {
  return {
    token: 'test', productId: 'product-611', documentNumber: 'FBS 30.09.2026', qtyNeedPack: 1,
    markingAvailable: 0, qtyMarkingPrinted: 0, requiresHonestSign: true, skuCode: 'FBS-611',
    productName: label.product_name, productLabel: label, onPrinted: vi.fn(),
    fbsTape: {
      orders: [{ orderId: 'order-611', wbOrderId: 611, marketplace: 'wb', requiresHonestSign: true, productLabel: label }],
      markingShortage: 1, includeOrderQr: true, print, confirmQrApplied: vi.fn(),
    },
  }
}
async function render(ctx: MarkingPrintContext, busy = false) {
  await act(async () => root.render(<MarkingPrintDialog open reprint={false} ctx={ctx} busy={busy} onBusyChange={() => {}} onClose={() => {}} />))
}
const button = () => document.querySelector<HTMLButtonElement>('[data-testid="marking-print-confirm"]')!
beforeEach(() => {
  ;(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true
  window.localStorage.clear()
  vi.stubGlobal('fetch', vi.fn().mockImplementation(async () => new Response('{}', { status: 404 })))
  print.mockReset()
  host = document.createElement('div')
  document.body.appendChild(host)
  root = createRoot(host)
})
afterEach(() => { act(() => root.unmount()); host.remove(); vi.unstubAllGlobals() })
describe('WMS-611 FBS print availability', () => {
  it('submits despite a stale empty pool and shows the current server shortage', async () => {
    print.mockResolvedValue({ orders: [], order_errors: [], shortage: 2 })
    await render(context())
    expect(button().disabled).toBe(false)
    await act(async () => button().click())
    expect(print).toHaveBeenCalledTimes(1)
    expect(print.mock.calls[0][0].allowPartial).toBe(false)
    expect(document.querySelector('[data-testid="marking-print-error"]')?.textContent).toContain('Не хватает 2 КМ')
    expect(button().disabled).toBe(false)
  })
  it('allows an assigned-code batch even when no free codes remain', async () => {
    const ctx = context(); ctx.fbsTape!.markingShortage = 0
    await render(ctx)
    expect(button().disabled).toBe(false)
  })
  it('preserves busy and empty-selection protection', async () => {
    const ctx = context(); await render(ctx, true)
    expect(button().disabled).toBe(true)
    ctx.fbsTape!.orders = []; await render({ ...ctx })
    expect(button().disabled).toBe(true)
  })
  it('preserves pool validation outside FBS', async () => {
    const ctx = context(); delete ctx.fbsTape
    await render(ctx)
    expect(button().disabled).toBe(true)
  })
})
