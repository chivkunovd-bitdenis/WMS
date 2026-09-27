import { describe, expect, it, vi } from 'vitest'
import { createSortingScanner, emptyScanContext, type ScanContext } from './sortingScan'
import { pendingScan, rememberScan, sendScan } from './pendingScan'
import type { WarehouseObject } from './objectsStub'

const cells = [{ id: 'a', code: 'А-1', barcode: 'LOC-123' }, { id: 'b', code: 'Б-2', barcode: 'LOC-456' }]
const objects = [{ id: 'box', code: 'КР-1', barcode: 'BOX-123', kind: 'box' as const, holder: null }]
function setup(place = vi.fn(async () => {})) {
  let context = emptyScanContext
  const product = vi.fn(async (_barcode: string, _context: ScanContext) => {})
  const error = vi.fn()
  const scanner = createSortingScanner(context, {
    data: () => ({ cells, objects }), place, product,
    changed: (next) => { context = next }, notice: vi.fn(), error,
  })
  return { scanner, product, place, error, context: () => context }
}

describe('WMS-550 sorting scan workflow', () => {
  it('reopens a placed box without moving it again, including a box on a pallet', async () => {
    let currentObjects: WarehouseObject[] = objects.map((one) => ({ ...one }))
    let context = emptyScanContext
    const place = vi.fn(async (object: WarehouseObject, cellId: string) => {
      currentObjects = currentObjects.map((one) => one.id === object.id ? { ...one, holder: `cell:${cellId}` } : one)
    })
    const error = vi.fn()
    const scanner = createSortingScanner(context, {
      data: () => ({ cells, objects: currentObjects }), place, product: vi.fn(async () => {}),
      changed: (next) => { context = next }, notice: vi.fn(), error,
    })
    await scanner.scan('LOC-123')
    await Promise.all([scanner.scan('BOX-123'), scanner.scan('BOX-123'), scanner.scan('BOX-123')])
    expect(place).toHaveBeenCalledTimes(1)
    expect(context).toEqual({ cellId: 'a', objectId: 'box' })
    await scanner.scan('BOX-123')
    currentObjects = [
      { ...currentObjects[0], holder: 'obj:pallet' },
      { id: 'pallet', code: 'П-1', barcode: 'PAL-123', kind: 'pallet', holder: 'cell:a' },
    ]
    await scanner.scan('BOX-123')
    expect(place).toHaveBeenCalledTimes(1)
    expect(context).toEqual({ cellId: 'a', objectId: 'box' })
    expect(error).not.toHaveBeenCalled()
  })

  it('normalizes scanner layout/AIM and closes only the scanned context', async () => {
    const t = setup()
    await t.scanner.scan(']C0ДЩС-123')
    expect(t.context()).toEqual({ cellId: 'a', objectId: null })
    await t.scanner.scan('BOX-123')
    expect(t.context()).toEqual({ cellId: 'a', objectId: 'box' })
    await t.scanner.scan('BOX-123')
    expect(t.place).toHaveBeenCalledTimes(1)
    await t.scanner.scan('4601234567890')
    expect(t.product).toHaveBeenLastCalledWith('4601234567890', { cellId: 'a', objectId: null })
    await t.scanner.scan('BOX-123')
    await t.scanner.scan('LOC-456')
    expect(t.context()).toEqual({ cellId: 'b', objectId: null })
    await t.scanner.scan('LOC-456')
    expect(t.context()).toEqual(emptyScanContext)
  })

  it('retains all rapid scans and waits for container placement before two product requests', async () => {
    let finish!: () => void
    const t = setup(vi.fn(() => new Promise<void>((resolve) => { finish = resolve })))
    await t.scanner.scan('LOC-123')
    const box = t.scanner.scan('BOX-123')
    const first = t.scanner.scan('4601234567890')
    const second = t.scanner.scan('4601234567890')
    await Promise.resolve()
    expect(t.product).not.toHaveBeenCalled()
    finish()
    await Promise.all([box, first, second])
    expect(t.product.mock.calls).toEqual([
      ['4601234567890', { cellId: 'a', objectId: 'box' }],
      ['4601234567890', { cellId: 'a', objectId: 'box' }],
    ])
  })

  it('does not open a rejected container or send its queued products into the cell', async () => {
    const t = setup(vi.fn(async () => { throw new Error('placement rejected') }))
    await t.scanner.scan('LOC-123')
    await Promise.all([t.scanner.scan('BOX-123'), t.scanner.scan('4601234567890')])
    expect(t.context()).toEqual(emptyScanContext)
    expect(t.product).not.toHaveBeenCalled()
    expect(t.error).toHaveBeenCalledTimes(2)
  })

  it('recovers an unanswered scan with the same operation id and never creates another until resolved', async () => {
    const disk = new Map<string, string>()
    const storage = { getItem: (key: string) => disk.get(key) ?? null, setItem: (key: string, value: string) => disk.set(key, value), removeItem: (key: string) => disk.delete(key) } as unknown as Storage
    const body = { barcode: '4601234567890', cell_id: 'a', to_id: 'box', inbound_request_id: 'inbound' }
    const request = rememberScan(storage, 'key', body)
    await expect(sendScan(storage, 'key', request, async () => { throw new Error('lost reply') })).rejects.toThrow()
    expect(() => rememberScan(storage, 'key', body)).toThrow()
    const restored = pendingScan(storage, 'key')!
    expect(restored.operation_id).toBe(request.operation_id)
    await sendScan(storage, 'key', restored, async () => new Response('{}'))
    expect(pendingScan(storage, 'key')).toBeNull()
    expect(rememberScan(storage, 'key', body).operation_id).not.toBe(request.operation_id)
  })
})
