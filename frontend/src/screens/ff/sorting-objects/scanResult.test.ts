import { describe, expect, it, vi } from 'vitest'
import { applyScanResult } from './scanResult'
import { createSortingScanner, emptyScanContext, RejectedScan } from './sortingScan'

const cells = [{ id: 'a', code: 'A', barcode: 'A' }, { id: 'b', code: 'B', barcode: 'B' }]
const objects = [{ id: 'box', code: 'BOX', barcode: 'BOX', kind: 'box' as const, holder: 'cell:a' }]
const disk = () => {
  const data = new Map<string, string>()
  return { getItem: (key: string) => data.get(key) ?? null, setItem: (key: string, value: string) => { data.set(key, value) } } as Storage
}

describe('WMS-554 quick confirmation and durable queue', () => {
  it('updates only confirmed unit, retaining real balance IDs and total', () => {
    const result = { reload: false, source_id: 's', target_id: 't', product_id: 'p', target_holder: 'obj:box' }
    const initial = [{ id: 's', productId: 'p', qty: 2, holder: null }]
    const one = applyScanResult(initial, result)!
    expect(one.map((line) => line.qty)).toEqual([1, 1])
    expect(applyScanResult(one, result)).toEqual([{ id: 't', productId: 'p', qty: 2, holder: 'obj:box' }])
    expect(applyScanResult(one, { ...result, reload: true })).toBeNull()
    expect(initial[0].qty).toBe(2)
  })

  it('persists an entire burst before sending and restores the same operation/target after lost reply', async () => {
    const storage = disk()
    const product = vi.fn(async () => { throw new Error('lost reply') })
    const deps = { data: () => ({ cells, objects }), place: vi.fn(async () => {}), product, changed: vi.fn(), notice: vi.fn(), error: vi.fn(), storage: { storage, key: 'queue' } }
    const scanner = createSortingScanner(emptyScanContext, deps)
    await scanner.scan('A')
    await scanner.scan('BOX')
    const first = scanner.scan('SKU')
    const second = scanner.scan('SKU')
    const close = scanner.scan('BOX')
    const next = scanner.scan('B')
    expect(JSON.parse(storage.getItem('queue')!).commands).toHaveLength(4)
    await Promise.all([first, second, close, next])
    expect(product).toHaveBeenCalledTimes(1)
    const saved = JSON.parse(storage.getItem('queue')!)
    expect(saved.commands).toHaveLength(4)
    const accepted = vi.fn(async () => {})
    const restored = createSortingScanner(emptyScanContext, { ...deps, product: accepted })
    await restored.resume()
    expect(accepted.mock.calls).toEqual([
      ['SKU', { cellId: 'a', objectId: 'box' }, saved.commands[0].id],
      ['SKU', { cellId: 'a', objectId: 'box' }, saved.commands[1].id],
    ])
    expect(JSON.parse(storage.getItem('queue')!)).toEqual({ context: { cellId: 'b', objectId: null }, commands: [] })
  })

  it('keeps box open on same-cell click and pauses queued products on rejected box', async () => {
    const changed = vi.fn()
    const product = vi.fn(async () => {})
    const scanner = createSortingScanner({ cellId: 'a', objectId: 'box' }, {
      data: () => ({ cells, objects }), changed, product,
      place: async () => { throw new RejectedScan('rejected') }, notice: vi.fn(), error: vi.fn(),
      storage: { storage: disk(), key: 'queue' },
    })
    await scanner.selectCell('a')
    await scanner.scan('SKU')
    expect(product).toHaveBeenLastCalledWith('SKU', { cellId: 'a', objectId: 'box' }, expect.any(String))
    await scanner.scan('B')
    await Promise.all([scanner.scan('BOX'), scanner.scan('SKU')])
    expect(product).toHaveBeenCalledTimes(1)
    expect(changed).toHaveBeenLastCalledWith(emptyScanContext)
  })
})
