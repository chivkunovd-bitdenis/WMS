import { afterEach, expect, it, vi } from 'vitest'
import { createPackingScanController, makePackingScanDeps, PackingBindRejectedError } from '../../screens/v2/fbsSequentialPacking'
import type { FbsScanAutoPrintResult, FbsWorkspace } from '../../screens/v2/fbsApi'

afterEach(() => vi.unstubAllGlobals())

it.each([null, 'task-1'])('binds KIZ with initial supply preparation %s', async (initialTask) => {
  const workspace = {
    supply: { id: 'supply-1', packaging_task_id: initialTask },
    orders: [{ id: 'order-1', product: { id: 'product-1' } }], boxes: [],
  } as unknown as FbsWorkspace
  let started = Boolean(initialTask)
  const calls: string[] = []
  vi.stubGlobal('fetch', vi.fn(async (path: string) => {
    calls.push(path)
    let body: unknown = {}
    if (path.endsWith('/start-work')) {
      started = true
      body = { ...workspace, supply: { ...workspace.supply, packaging_task_id: 'task-1' } }
    } else if (path.endsWith('/kiz/commit')) {
      body = [{ order_id: 'order-1', status: started ? 'ok' : 'error', message: 'packaging_line_not_found', bound_kiz: 'kiz' }]
    } else if (path.endsWith('/task-1')) {
      body = { lines: [{ id: 'line-1', product_id: 'product-1' }] }
    }
    return new Response(JSON.stringify(body), { status: 200 })
  }))
  const bound = vi.fn()
  const deps = makePackingScanDeps('token', () => ({}), () => workspace, () => undefined, () => undefined, () => true, () => null, bound)
  const result = { scan_id: 'scan-1', order_id: 'order-1' } as FbsScanAutoPrintResult
  await deps.bind(result, 'kiz')
  await deps.pack(result, false, 'barcode', null)
  expect(bound).toHaveBeenCalledWith('order-1', 'kiz')
  expect(calls.filter((path) => path.endsWith('/start-work'))).toHaveLength(initialTask ? 0 : 1)
  if (!initialTask) expect(calls.findIndex((path) => path.endsWith('/start-work'))).toBeLessThan(calls.findIndex((path) => path.endsWith('/kiz/commit')))
  expect(calls.at(-1)).toBe('/api/operations/packaging-tasks/task-1/lines/line-1/pack')
})

function stubCommit(row: Record<string, unknown>) {
  const calls: string[] = []
  vi.stubGlobal('fetch', vi.fn(async (path: string) => {
    calls.push(path)
    const body = path.endsWith('/kiz/commit') ? [{ order_id: 'order-1', ...row }] : { ok: true, hints: [] }
    return new Response(JSON.stringify(body), { status: 200 })
  }))
  return calls
}
const ws = {
  supply: { id: 'supply-1', packaging_task_id: 'task-1' },
  orders: [{ id: 'order-1', product: { id: 'product-1' } }], boxes: [],
} as unknown as FbsWorkspace

it('WMS-635 R1: WB «pending confirmation» is a saved binding — the scan prints and packs without waiting', async () => {
  stubCommit({ status: 'error', code: 'wb_pending_confirmation', message: 'wb_pending_confirmation' })
  const bound = vi.fn()
  const deps = makePackingScanDeps('token', () => ({}), () => ws, () => undefined, () => undefined, () => true, () => null, bound)
  const selected = { scan_id: 'scan-1', order_id: 'order-1', wb_order_id: 1, requires_honest_sign: true,
    binding_target: null, reprint_recovery: null, qr_asset: null, replayed: false, codes: [],
    printed_codes: [], shortage: 0, order_errors: [] } as FbsScanAutoPrintResult
  deps.preferences = () => ({ printQr: true, printChz: false, reprintChz: false })
  deps.claim = () => ({ key: 'k', preferences: { printQr: true, printChz: false, reprintChz: false }, labelSizeId: '58x40', explicit: false })
  deps.select = vi.fn().mockResolvedValue(selected)
  deps.remember = vi.fn()
  deps.complete = vi.fn()
  deps.preload = vi.fn().mockResolvedValue('png')
  deps.print = vi.fn().mockResolvedValue(undefined)
  deps.pack = vi.fn().mockResolvedValue(undefined)
  const scanner = createPackingScanController(deps)
  await scanner.scan('barcode')
  await scanner.scan('kiz-raw')
  expect(bound).toHaveBeenCalledWith('order-1', 'kiz-raw')
  expect(deps.print).toHaveBeenCalledTimes(1)
  expect(deps.pack).toHaveBeenCalledTimes(1)
  expect(scanner.hasPending()).toBe(false)
})

it('WMS-635 R1: any other refusal still saves nothing and keeps the order waiting', async () => {
  stubCommit({ status: 'error', code: 'meta_validation_fail', message: 'WB не принял ЧЗ' })
  const deps = makePackingScanDeps('token', () => ({}), () => ws, () => undefined, () => undefined)
  await expect(deps.bind({ scan_id: 'scan-1', order_id: 'order-1' } as FbsScanAutoPrintResult, 'kiz'))
    .rejects.toBeInstanceOf(PackingBindRejectedError)
})

it('WMS-635 R4: a KIZ WB refused stays bound — QR printed, order packed, no exact copy', async () => {
  stubCommit({ status: 'error', code: 'wb_rejected_kept', message: 'WB не принял ЧЗ: КИЗ не введён в оборот' })
  const bound = vi.fn()
  const deps = makePackingScanDeps('token', () => ({}), () => ws, () => undefined, () => undefined, () => true, () => null, bound)
  const selected = { scan_id: 'scan-1', order_id: 'order-1', wb_order_id: 1, requires_honest_sign: true,
    binding_target: null, reprint_recovery: null, qr_asset: null, replayed: false, codes: [],
    printed_codes: [], shortage: 0, order_errors: [] } as FbsScanAutoPrintResult
  const both = { printQr: true, printChz: false, reprintChz: true }
  deps.preferences = () => both
  deps.claim = () => ({ key: 'k', preferences: both, labelSizeId: '58x40', explicit: false })
  deps.select = vi.fn().mockResolvedValue(selected)
  deps.remember = vi.fn()
  deps.complete = vi.fn()
  deps.preload = vi.fn().mockResolvedValue('png')
  deps.print = vi.fn().mockResolvedValue(undefined)
  deps.printCopy = vi.fn().mockResolvedValue(undefined)
  deps.pack = vi.fn().mockResolvedValue(undefined)
  const scanner = createPackingScanController(deps)
  await scanner.scan('barcode')
  await scanner.scan('kiz-raw')
  expect(bound).toHaveBeenCalledWith('order-1', 'kiz-raw')
  expect(deps.print).toHaveBeenCalledTimes(1)
  expect(deps.printCopy).not.toHaveBeenCalled()
  expect(deps.pack).toHaveBeenCalledTimes(1)
})

it('WMS-635 Q1: the packing scan asks the server not to wait long for WB', async () => {
  const bodies: unknown[] = []
  vi.stubGlobal('fetch', vi.fn(async (path: string, init?: RequestInit) => {
    if (path.endsWith('/kiz/commit')) bodies.push(JSON.parse(String(init?.body)))
    const body = path.endsWith('/kiz/commit') ? [{ order_id: 'order-1', status: 'ok', code: 'ok', bound_kiz: 'kiz' }] : { ok: true, hints: [] }
    return new Response(JSON.stringify(body), { status: 200 })
  }))
  const deps = makePackingScanDeps('token', () => ({}), () => ws, () => undefined, () => undefined)
  await deps.bind({ scan_id: 'scan-1', order_id: 'order-1' } as FbsScanAutoPrintResult, 'kiz')
  expect(bodies).toEqual([expect.objectContaining({ scan_no_wb_wait: true })])
})
