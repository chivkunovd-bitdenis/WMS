// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { makePackingScanDeps } from './fbsSequentialPacking'
import type { FbsScanAutoPrintResult, FbsWorkspace } from './fbsApi'

const QR = { printQr: true, printChz: false, reprintChz: false }

beforeEach(() => window.localStorage.clear())
afterEach(() => vi.unstubAllGlobals())

describe('WMS-604 original packing box survives recovery', () => {
  it.each(['selection', 'pack'])('preserves the original box after a lost %s response and remount', async (failure) => {
    const result = { scan_id: 'scan-1', order_id: 'order-1', requires_honest_sign: false } as FbsScanAutoPrintResult
    const workspace = {
      supply: { id: 'supply-1', packaging_task_id: 'task-1' },
      orders: [{ id: 'order-1', product: { id: 'product-1' } }], boxes: [],
    } as unknown as FbsWorkspace
    const calls: string[] = []
    let failed = false
    vi.stubGlobal('fetch', vi.fn(async (input: string) => {
      calls.push(input)
      if (!failed && ((failure === 'selection' && input.endsWith('/scan-auto-print')) || (failure === 'pack' && input.endsWith('/pack')))) {
        failed = true
        throw new Error('response lost')
      }
      const body = input.endsWith('/scan-auto-print') ? result
        : input.endsWith('/task-1') ? { lines: [{ id: 'line-1', product_id: 'product-1' }] } : workspace
      return new Response(JSON.stringify(body), { status: 200, headers: { 'Content-Type': 'application/json' } })
    }))
    const make = (box: string | null) => makePackingScanDeps('token', () => ({}), () => workspace, () => undefined, () => undefined, () => true, () => box)
    const first = make('original-box')
    const key = first.claim('barcode', QR).key
    if (failure === 'selection') await expect(first.select('barcode', key, QR)).rejects.toThrow('response lost')
    else {
      const selected = await first.select('barcode', key, QR)
      first.remember('barcode', selected)
      await expect(first.pack(selected, false, 'barcode', null)).rejects.toThrow('response lost')
    }
    const resumed = make('different-box-after-reload')
    expect(resumed.claim('barcode', QR).key).toBe(key)
    const selected = await resumed.select('barcode', key, QR)
    resumed.remember('barcode', selected)
    await resumed.pack(selected, false, 'barcode', null)
    expect(calls.filter((path) => path.includes('/boxes/'))).toEqual(['/api/operations/fbs-supplies/supply-1/boxes/original-box/orders'])
  })
  it('keeps an explicit no-box selection instead of capturing a newly opened box on retry', async () => {
    const result = { scan_id: 'scan-1', order_id: 'order-1' } as FbsScanAutoPrintResult
    const workspace = { supply: { id: 'supply-1', packaging_task_id: 'task-1' }, orders: [{ id: 'order-1', product: { id: 'product-1' } }], boxes: [] } as unknown as FbsWorkspace
    const fetcher = vi.fn(async (input: string) => new Response(JSON.stringify(input.endsWith('/scan-auto-print') ? result : input.endsWith('/task-1') ? { lines: [{ id: 'line-1', product_id: 'product-1' }] } : workspace), { status: 200 }))
    vi.stubGlobal('fetch', fetcher)
    const make = (box: string | null) => makePackingScanDeps('token', () => ({}), () => workspace, () => undefined, () => undefined, () => true, () => box)
    const first = make(null)
    const key = first.claim('barcode', QR).key
    first.remember('barcode', await first.select('barcode', key, QR))
    const resumed = make('new-box')
    expect(resumed.claim('barcode', QR).key).toBe(key)
    await resumed.pack(await resumed.select('barcode', key, QR), false, 'barcode', null)
    expect(fetcher.mock.calls.some(([path]) => path.includes('/boxes/'))).toBe(false)
  })
})
