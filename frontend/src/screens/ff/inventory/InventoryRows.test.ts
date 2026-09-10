import { describe, expect, it } from 'vitest'
import { changedActualIds, markUncountedEmptyIn, mergeInFlightActuals, setActual } from './InventoryRows'
import type { InventoryCount } from './InventoryTypes'

// WMS-154: «Здесь пусто» — не удаление сущностей и не отдельный жизненный
// цикл, а простой обход поддерева выбранного места и установка `actual = 0`
// у непосчитанных строк. Ниже — минимальный документ, чтобы обходчик было на
// чём проверить, без всей серверной обвязки.

function baseCount(): InventoryCount {
  return {
    id: 'count-1',
    number: 'ИНВ-1',
    status: 'draft',
    warehouseId: 'wh-1',
    warehouseName: 'Склад',
    fill: { mode: 'all' },
    createdAt: '01.09.2026 10:00',
    createdBy: 'kladovshchik',
    postedAt: null,
    postedBy: null,
    comment: '',
    addressStorage: true,
    cells: [
      {
        id: 'cell-1',
        label: 'A-1',
        barcode: null,
        children: [
          {
            kind: 'box',
            id: 'box-1',
            code: 'K-1',
            barcode: null,
            children: [
              {
                kind: 'product',
                id: 'p-1',
                name: 'Товар А',
                sku: 'SKU-A',
                seller: 'Селлер',
                category: '—',
                barcode: '',
                wbVendorCode: null,
                wbBarcode: null,
                wbSize: null,
                photoUrl: null,
                expected: 5,
                actual: null,
              },
              {
                kind: 'product',
                id: 'p-2',
                name: 'Товар Б',
                sku: 'SKU-B',
                seller: 'Селлер',
                category: '—',
                barcode: '',
                wbVendorCode: null,
                wbBarcode: null,
                wbSize: null,
                photoUrl: null,
                expected: 3,
                actual: 3,
              },
            ],
          },
        ],
      },
    ],
    scannableCells: [],
    scannableContainers: [],
  }
}

describe('markUncountedEmptyIn', () => {
  it('ставит 0 только непосчитанным строкам внутри выбранной тары', () => {
    const { count, touched } = markUncountedEmptyIn(baseCount(), {
      kind: 'container',
      containerId: 'box-1',
    })
    const box = count.cells[0].children[0]
    if (box.kind !== 'box') throw new Error('short: expected a box')
    const productA = box.children.find((c) => c.kind === 'product' && c.id === 'p-1')
    const productB = box.children.find((c) => c.kind === 'product' && c.id === 'p-2')
    // p-1 был непосчитан → теперь 0; p-2 уже был 3 → не тронули.
    if (productA?.kind !== 'product' || productB?.kind !== 'product') {
      throw new Error('short: products missing')
    }
    expect(productA.actual).toBe(0)
    expect(productB.actual).toBe(3)
    expect(touched).toEqual(['p-1'])
  })

  it('ставит 0 всем непосчитанным по всей ячейке', () => {
    const { touched } = markUncountedEmptyIn(baseCount(), { kind: 'cell', cellId: 'cell-1' })
    expect(touched).toEqual(['p-1'])
  })

  it('без непосчитанных строк — не создаёт нового объекта документа', () => {
    const source = baseCount()
    // Все листы уже посчитаны — «Здесь пусто» ничего не меняет.
    const box = source.cells[0].children[0]
    if (box.kind !== 'box') throw new Error('short: expected a box')
    for (const child of box.children) {
      if (child.kind === 'product') child.actual = 0
    }
    const applied = markUncountedEmptyIn(source, { kind: 'cell', cellId: 'cell-1' })
    expect(applied.touched).toEqual([])
    expect(applied.count).toBe(source)
  })

  it('не найденное место — пустой touched, документ не меняется', () => {
    const source = baseCount()
    const applied = markUncountedEmptyIn(source, { kind: 'cell', cellId: 'unknown-cell' })
    expect(applied.touched).toEqual([])
    expect(applied.count).toBe(source)
  })
})

describe('WMS-155 concurrent edits', () => {
  it('preserves in-flight comment and quantities while accepting other server changes', () => {
    const sent = baseCount()
    const current = { ...setActual(sent, 'p-1', 7), comment: 'Entered while saving' }
    const server = { ...setActual(sent, 'p-2', 6), comment: 'Server comment' }
    const merged = mergeInFlightActuals(server, sent, current)
    expect(merged.comment).toBe('Entered while saving')
    expect(changedActualIds(merged, server)).toEqual(new Set(['p-1']))
  })
  it('does not reopen a previous document when its response arrives late', () => {
    const old = baseCount()
    const current = { ...baseCount(), id: 'another-document' }
    expect(mergeInFlightActuals(old, old, current)).toBe(current)
  })
  it('does not send untouched quantities from the map dialog', () => {
    const original = baseCount()
    expect(changedActualIds({ ...original, comment: 'Only a comment' }, original).size).toBe(0)
  })
})
