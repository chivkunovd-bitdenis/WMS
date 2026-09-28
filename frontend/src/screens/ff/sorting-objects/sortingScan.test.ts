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
  it('resolves all 882 CSV cell barcodes before names in either keyboard layout, with AIM and repeat scans', async () => {
    const grid = [
      ['А', 'A', 5, 21], ['Б', 'B', 5, 21], ['В', 'V', 5, 21],
      ['Г', 'G', 5, 21], ['Д', 'D', 5, 21], ['Е', 'E', 5, 21],
      ['Ж', 'J', 5, 28], ['К', 'K', 3, 9], ['Л', 'L', 3, 9],
      ['М', 'M', 2, 17], ['Н', 'N', 2, 9],
    ] as const
    const allCells = grid.flatMap(([name, barcode, rows, columns]) =>
      Array.from({ length: rows }, (_, row) => Array.from({ length: columns }, (_, column) => ({
        id: `${name}-${row + 1}-${column + 1}`, code: `${name}-${row + 1}-${column + 1}`,
        barcode: `${barcode}-${row + 1}-${column + 1}`,
      }))).flat(),
    ).concat([...'АБВГДЕ'].map((name, index) => ({
      id: `${name}-5-22`, code: `${name}-5-22`, barcode: `${['A', 'B', 'V', 'G', 'D', 'E'][index]}-5-22`,
    }))).reverse() // М precedes В: V must still select the authoritative barcode В.
    expect(allCells).toHaveLength(882)
    const keyboard = Object.fromEntries([...'QWERTYUIOP[]ASDFGHJKL;\'ZXCVBNM,.'].map((char, index) =>
      [char, [...'ЙЦУКЕНГШЩЗХЪФЫВАПРОЛДЖЭЯЧСМИТЬБЮ'][index]],
    ))
    const russianLayout = (value: string) => [...value].map((char) => keyboard[char] ?? char).join('')
    let context = emptyScanContext
    const place = vi.fn(async () => {})
    const product = vi.fn(async () => {})
    const error = vi.fn()
    const scanner = createSortingScanner(context, {
      data: () => ({ cells: allCells, objects: [] }), place, product,
      changed: (next) => { context = next }, notice: vi.fn(), error,
    })
    for (const cell of allCells) {
      for (const code of [cell.barcode, russianLayout(cell.barcode), `]Q3${cell.barcode}`, russianLayout(`]Q3${cell.barcode}`)]) {
        await scanner.scan(code)
        expect(context, code).toEqual({ cellId: cell.id, objectId: null })
        await scanner.scan(code)
        expect(context, code).toEqual(emptyScanContext)
      }
    }
    expect(place).not.toHaveBeenCalled()
    expect(product).not.toHaveBeenCalled()
    expect(error).not.toHaveBeenCalled()
  })

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
    expect(t.product).toHaveBeenLastCalledWith('4601234567890', { cellId: 'a', objectId: null }, expect.any(String))
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
      ['4601234567890', { cellId: 'a', objectId: 'box' }, expect.any(String)],
      ['4601234567890', { cellId: 'a', objectId: 'box' }, expect.any(String)],
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
