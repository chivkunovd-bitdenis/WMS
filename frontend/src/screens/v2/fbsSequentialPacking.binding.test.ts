import { afterEach, expect, it, vi } from 'vitest'
import { makePackingScanDeps } from './fbsSequentialPacking'
import type { FbsScanAutoPrintResult, FbsWorkspace } from './fbsApi'

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
  await deps.pack(result, false, 'barcode')
  expect(bound).toHaveBeenCalledWith('order-1', 'kiz')
  expect(calls.filter((path) => path.endsWith('/start-work'))).toHaveLength(initialTask ? 0 : 1)
  if (!initialTask) expect(calls.findIndex((path) => path.endsWith('/start-work'))).toBeLessThan(calls.findIndex((path) => path.endsWith('/kiz/commit')))
  expect(calls.at(-1)).toBe('/api/operations/packaging-tasks/task-1/lines/line-1/pack')
})
