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
  it('prints the screenshot case: 12 orders, ЧЗ=0, ШК=1, QR, empty pool', async () => {
    const ctx = context()
    ctx.qtyNeedPack = 12
    ctx.fbsTape!.markingShortage = 12
    ctx.fbsTape!.orders = Array.from({ length: 12 }, (_, i) => ({ ...ctx.fbsTape!.orders[0], orderId: `order-${i}`, wbOrderId: 611 + i }))
    await render(ctx)
    const setQuantity = async (testId: string, value: string) => {
      const input = document.querySelector<HTMLInputElement>(`[data-testid="${testId}"] input`)!
      await act(async () => {
        Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value')!.set!.call(input, value)
        input.dispatchEvent(new Event('input', { bubbles: true }))
      })
    }
    await setQuantity('marking-print-wb-qty', '1')
    await setQuantity('marking-print-cz-qty', '0')
    expect(document.querySelector('[data-testid="marking-print-shortage-banner"]')).toBeNull()
    expect(document.querySelector('[data-testid="marking-print-preview-tape-count"]')?.textContent).toContain('12')
    expect(button().disabled).toBe(false)
    print.mockResolvedValue({ orders: [], order_errors: [{ message: 'test stop before physical print' }], shortage: 0 })
    await act(async () => button().click())
    expect(print.mock.calls[0][0].layout.units).toEqual([{ block: 'label', copies: 1 }])
  })
  it('builds QR plus barcode for every marked WB product when ЧЗ=0', async () => {
    const ctx = context()
    ctx.qtyNeedPack = 12
    ctx.fbsTape!.orders = Array.from({ length: 12 }, (_, i) => ({ ...ctx.fbsTape!.orders[0], orderId: `wb-${i}`, wbOrderId: 700 + i }))
    await render(ctx)
    for (const [testId, value] of [['marking-print-wb-qty', '1'], ['marking-print-cz-qty', '0']]) {
      const input = document.querySelector<HTMLInputElement>(`[data-testid="${testId}"] input`)!
      await act(async () => {
        Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value')!.set!.call(input, value)
        input.dispatchEvent(new Event('input', { bubbles: true }))
      })
    }
    print.mockResolvedValue({ orders: ctx.fbsTape!.orders.map(o => ({
      order_id: o.orderId, wb_order_id: o.wbOrderId, requires_honest_sign: true,
      printed_codes: [], qr_asset: { id: o.orderId, preview_url: '/test-qr.png', applied_at: 'already-applied' },
    })), order_errors: [], shortage: 0 })
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: true, blob: async () => new Blob(['qr'], { type: 'image/png' }) }))
    vi.mocked(printTapeSections).mockClear()
    await act(async () => button().click())
    await act(async () => { await new Promise(resolve => setTimeout(resolve, 50)) })
    expect(document.querySelector('[data-testid="marking-print-error"]')?.textContent ?? null).toBeNull()
    expect(printTapeSections).toHaveBeenCalledTimes(1)
    const sections = vi.mocked(printTapeSections).mock.calls[0][0]
    expect(sections).toHaveLength(24)
    for (let i = 0; i < 12; i++) {
      expect(sections[2 * i]).toContain('data-tape-block="wb_qr"')
      expect(sections[2 * i + 1]).toContain('data-tape-block="label"')
      expect(sections[2 * i + 1]).toContain(label.barcode)
      expect(sections[2 * i + 1]).toContain(label.product_name)
    }
  })
  it('retries only the unconfirmed QR after a successful tape dispatch', async () => {
    const ctx = context()
    const completed = vi.fn()
    const onPrinted = vi.fn()
    const close = vi.fn()
    ctx.onPrinted = onPrinted
    ctx.fbsTape!.onCompleted = completed
    ctx.fbsTape!.orders.push({ ...ctx.fbsTape!.orders[0]!, orderId: 'order-612', wbOrderId: 612 })
    ctx.fbsTape!.print = print
    const confirmQrApplied = vi.fn()
      .mockResolvedValueOnce(undefined)
      .mockRejectedValueOnce(new Error('WB QR confirmation returned 503'))
      .mockResolvedValueOnce(undefined)
    ctx.fbsTape!.confirmQrApplied = confirmQrApplied
    print.mockResolvedValue({
      orders: ctx.fbsTape!.orders.map((order) => ({
        order_id: order.orderId, wb_order_id: order.wbOrderId, requires_honest_sign: true,
        printed_codes: [], qr_asset: { id: `qr-${order.orderId}`, preview_url: `/qr/${order.orderId}.png`, applied_at: null },
      })),
      order_errors: [], shortage: 0,
    })
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: true, blob: async () => new Blob(['qr'], { type: 'image/png' }) }))
    vi.mocked(printTapeSections).mockResolvedValue(undefined)
    await render(ctx, false, close)
    await act(async () => button().click())
    await act(async () => { await new Promise(resolve => setTimeout(resolve, 20)) })

    expect(print).toHaveBeenCalledTimes(1)
    expect(printTapeSections).toHaveBeenCalledTimes(1)
    expect(confirmQrApplied.mock.calls.map(([asset]) => asset.id)).toEqual(['qr-order-611', 'qr-order-612'])
    expect(completed).not.toHaveBeenCalled()
    expect(onPrinted).not.toHaveBeenCalled()
    expect(close).not.toHaveBeenCalled()

    const retry = document.querySelector<HTMLButtonElement>('[data-testid="marking-print-retry-qr-ack"]')
    expect(retry, 'an ack-only retry must be available after the tape dispatch is accepted').not.toBeNull()
    await act(async () => retry!.click())
    await act(async () => { await new Promise(resolve => setTimeout(resolve, 20)) })
    expect(print, 'a user retry must not dispatch the already accepted tape again').toHaveBeenCalledTimes(1)
    expect(printTapeSections).toHaveBeenCalledTimes(1)
    expect(confirmQrApplied.mock.calls.map(([asset]) => asset.id)).toEqual(['qr-order-611', 'qr-order-612', 'qr-order-612'])
    expect(completed).toHaveBeenCalledTimes(1)
    expect(onPrinted).toHaveBeenCalledTimes(1)
    expect(close).toHaveBeenCalledTimes(1)
  })
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
