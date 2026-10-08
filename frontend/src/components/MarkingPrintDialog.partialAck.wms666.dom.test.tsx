// @vitest-environment jsdom
import { act } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { MarkingPrintDialog, type MarkingPrintContext } from './MarkingPrintDialog'
import { printTapeSections } from '../utils/printMarkingCodeLabel'
vi.mock('./MarkingLabelPreview', () => ({ MarkingLabelPreview: () => null }))
vi.mock('../utils/printMarkingCodeLabel', async (original) => ({
  ...await original<Record<string, unknown>>(), beginPrintUserGesture: vi.fn(), cancelPendingPrintWindow: vi.fn(), printTapeSections: vi.fn(),
}))
vi.mock('../utils/renderBarcodeDataUrl', () => ({ renderBarcodeDataUrl: () => 'data:image/png;base64,cHJvb2Y=' }))
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
async function render(ctx: MarkingPrintContext, busy = false, onClose = () => {}) {
  await act(async () => root.render(<MarkingPrintDialog open reprint={false} ctx={ctx} busy={busy} onBusyChange={() => {}} onClose={onClose} />))
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

describe("WMS-666 partial tape acknowledgement recovery", () => {
  it('keeps a partial tape warning after ack-only recovery without completing or closing the mixed batch', async () => {
    vi.mocked(printTapeSections).mockClear()
    const ctx = context()
    const completed = vi.fn()
    const onPrinted = vi.fn()
    const close = vi.fn()
    ctx.onPrinted = onPrinted
    ctx.fbsTape!.onCompleted = completed
    ctx.fbsTape!.orders.push({ ...ctx.fbsTape!.orders[0]!, orderId: 'order-612', wbOrderId: 612 })
    const confirmQrApplied = vi.fn()
      .mockRejectedValueOnce(new Error('WB QR confirmation returned 503'))
      .mockResolvedValueOnce(undefined)
    ctx.fbsTape!.confirmQrApplied = confirmQrApplied
    print.mockResolvedValue({
      orders: [{
        order_id: 'order-611', wb_order_id: 611, requires_honest_sign: true,
        printed_codes: [], qr_asset: { id: 'qr-order-611', preview_url: '/qr/order-611.png', applied_at: null },
      }],
      order_errors: [{ order_id: 'order-612', wb_order_id: 612, code: 'sticker_failed', message: 'QR order 612 failed' }],
      shortage: 0,
    })
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: true, blob: async () => new Blob(['qr'], { type: 'image/png' }) }))
    vi.mocked(printTapeSections).mockResolvedValue(undefined)
    await render(ctx, false, close)
    await act(async () => button().click())
    await act(async () => { await new Promise(resolve => setTimeout(resolve, 20)) })

    expect(print).toHaveBeenCalledTimes(1)
    expect(printTapeSections).toHaveBeenCalledTimes(1)
    expect(document.querySelector('[data-testid="marking-print-error"]')?.textContent).toContain('503')
    const retry = document.querySelector<HTMLButtonElement>('[data-testid="marking-print-retry-qr-ack"]')
    expect(retry).not.toBeNull()
    await act(async () => retry!.click())
    await act(async () => { await new Promise(resolve => setTimeout(resolve, 20)) })

    expect(print, 'ack recovery must not dispatch the accepted tape again').toHaveBeenCalledTimes(1)
    expect(printTapeSections).toHaveBeenCalledTimes(1)
    expect(confirmQrApplied.mock.calls.map(([asset]) => asset.id)).toEqual(['qr-order-611', 'qr-order-611'])
    expect(document.querySelector('[data-testid="marking-print-error"]')?.textContent ?? '').toContain('QR order 612 failed')
    expect(onPrinted).toHaveBeenCalledTimes(1)
    expect(completed).not.toHaveBeenCalled()
    expect(close).not.toHaveBeenCalled()
    expect(document.querySelector('[data-testid="marking-print-retry-qr-ack"]')).toBeNull()
    expect(document.querySelector('[data-testid="marking-print-confirm"]')).not.toBeNull()
  })
})
