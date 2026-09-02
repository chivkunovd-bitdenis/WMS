import { describe, expect, it } from 'vitest'
import { applyScan, inventoryRowPathKeys } from './InventoryScan'
import { buildRows, EMPTY_FILTERS } from './InventoryRows'
import type { InventoryCount, ProductNode } from './InventoryTypes'

function product(overrides: Partial<ProductNode> = {}): ProductNode {
  return {
    kind: 'product',
    id: 'line-1',
    name: 'Куртка',
    sku: 'SKU-JACKET-1',
    seller: 'ИП Тест',
    category: 'Одежда',
    barcode: '4601234567890',
    wbBarcode: '4601234567890',
    photoUrl: null,
    expected: 3,
    actual: null,
    ...overrides,
  }
}

function countWithBox(item: ProductNode): InventoryCount {
  return {
    id: 'count-1',
    number: 'ИНВ-1',
    status: 'draft',
    warehouseName: 'Склад',
    fill: { mode: 'all' },
    createdAt: '',
    createdBy: '',
    postedAt: null,
    postedBy: null,
    comment: '',
    addressStorage: true,
    cells: [
      {
        id: 'cell-1',
        label: 'A-01',
        children: [
          {
            kind: 'box',
            id: 'box-1',
            code: 'BOX-1',
            barcode: 'BOX-BARCODE-1',
            children: [item],
          },
        ],
      },
    ],
  }
}

function actualOf(count: InventoryCount): number | null {
  const box = count.cells[0].children[0]
  if (box.kind === 'product') throw new Error('expected box')
  const item = box.children[0]
  if (item.kind !== 'product') throw new Error('expected product')
  return item.actual
}

describe('inventory product scan', () => {
  it('increments and focuses the product after its box was opened', () => {
    const count = countWithBox(product())
    const opened = applyScan(count, 'BOX-BARCODE-1', null)
    const scanned = applyScan(opened.count, '4601234567890', opened.activeContainerId)

    expect(scanned.tone).toBe('ok')
    expect(actualOf(scanned.count)).toBe(1)
    expect(scanned.focusRowKey).toBe('product:line-1')
    expect(scanned.focusPathKeys).toEqual([
      'cell:cell-1',
      'box:box-1',
      'product:line-1',
    ])
    expect(inventoryRowPathKeys(scanned.count, scanned.focusRowKey!)).toEqual([
      'cell:cell-1',
      'box:box-1',
      'product:line-1',
    ])
  })

  it('accepts the SKU printed as the fallback product barcode', () => {
    const count = countWithBox(product({ barcode: '', wbBarcode: null }))
    const scanned = applyScan(count, 'sku-jacket-1', 'box-1')

    expect(scanned.tone).toBe('ok')
    expect(actualOf(scanned.count)).toBe(1)
    expect(scanned.focusRowKey).toBe('product:line-1')
  })

  it('increments the same product on every repeated scan', () => {
    const count = countWithBox(product())
    const first = applyScan(count, '4601234567890', 'box-1')
    const second = applyScan(first.count, '4601234567890', 'box-1')

    expect(actualOf(second.count)).toBe(2)
    expect(second.message).toContain('2 из 3')
  })

  it('processes repeated scans with 1000 product rows still expanded', () => {
    const boxes = Array.from({ length: 100 }, (_, boxIndex) => ({
      kind: 'box' as const,
      id: `box-${boxIndex}`,
      code: `BOX-${boxIndex}`,
      barcode: `BOX-BARCODE-${boxIndex}`,
      children: Array.from({ length: 10 }, (_, productIndex) => product({
        id: `line-${boxIndex}-${productIndex}`,
        sku: `SKU-${boxIndex}-${productIndex}`,
        barcode: `BARCODE-${boxIndex}-${productIndex}`,
        wbBarcode: `BARCODE-${boxIndex}-${productIndex}`,
      })),
    }))
    const count: InventoryCount = {
      ...countWithBox(product()),
      cells: [{ id: 'cell-1', label: 'A-01', children: boxes }],
    }
    expect(buildRows(count, EMPTY_FILTERS, new Set())).toHaveLength(1101)

    const opened = applyScan(count, 'BOX-BARCODE-42', null)
    const scanned = applyScan(opened.count, 'BARCODE-42-7', opened.activeContainerId)

    expect(scanned.focusRowKey).toBe('product:line-42-7')
    expect(buildRows(scanned.count, EMPTY_FILTERS, new Set())).toHaveLength(1101)

    let rapidCount = opened.count
    const startedAt = performance.now()
    for (let scan = 0; scan < 1000; scan += 1) {
      rapidCount = applyScan(rapidCount, 'BARCODE-42-7', 'box-42').count
    }
    const elapsedMs = performance.now() - startedAt
    const targetBox = rapidCount.cells[0].children[42]
    if (targetBox.kind === 'product') throw new Error('expected box')
    const targetProduct = targetBox.children[7]
    if (targetProduct.kind !== 'product') throw new Error('expected product')

    expect(targetProduct.actual).toBe(1000)
    expect(elapsedMs).toBeLessThan(1000)
  })
})

describe('закрытие тары и находки', () => {
  it('повторный скан той же тары закрывает её', () => {
    const count = countWithBox(product())
    const opened = applyScan(count, 'BOX-BARCODE-1', null)
    expect(opened.activeContainerId).toBe('box-1')

    const closed = applyScan(opened.count, 'BOX-BARCODE-1', opened.activeContainerId)
    expect(closed.activeContainerId).toBeNull()
    expect(closed.tone).toBe('ok')
    expect(closed.message).toContain('закрыт')
  })

  it('незнакомый код при открытой таре становится находкой в эту тару', () => {
    const count = countWithBox(product())
    const opened = applyScan(count, 'BOX-BARCODE-1', null)
    const found = applyScan(opened.count, '9999999999999', opened.activeContainerId)

    expect(found.found).toEqual({
      barcodes: ['9999999999999'],
      storageLocationId: 'cell-1',
      containerKind: 'box',
      containerId: 'box-1',
    })
    // Сам скан строку не заводит: её создаёт сервер и возвращает документ.
    expect(found.count).toBe(opened.count)
  })

  it('на находку уходят оба прочтения кода: русская раскладка и латиница', () => {
    const count = countWithBox(product())
    const opened = applyScan(count, 'BOX-BARCODE-1', null)
    const found = applyScan(opened.count, 'Сршт-56005', opened.activeContainerId)

    expect(found.found?.barcodes).toEqual(['Сршт-56005', 'Chin-56005'])
  })

  it('товар, который числится в таре, россыпью не записывается', () => {
    // Оператор забыл пикнуть короб. Записать это находкой значит посчитать одну
    // и ту же вещь дважды: строка короба останется непосчитанной, а рядом
    // добавится россыпь на то же количество.
    const count = countWithBox(product())
    const result = applyScan(count, '4601234567890', null)

    expect(result.found).toBeUndefined()
    expect(result.tone).toBe('warn')
    expect(result.message).toContain('Отсканируйте тару')
  })

  it('экран без доступа к серверу находок не обещает', () => {
    const count = countWithBox(product())
    const opened = applyScan(count, 'BOX-BARCODE-1', null)
    const result = applyScan(opened.count, '9999999999999', opened.activeContainerId, false)

    expect(result.found).toBeUndefined()
    expect(result.message).toContain('полном документе')
  })
})
