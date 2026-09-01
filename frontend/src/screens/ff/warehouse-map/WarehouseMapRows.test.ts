import { describe, expect, it } from 'vitest'
import { EMPTY_FILTERS, buildRows } from './WarehouseMapRows'
import type { WarehouseMapData } from './WarehouseMapTypes'

// TC-NEW-218 — чип «Пустая» на карте склада не должен врать при поиске.
// Владелец: «паллета пустая если на ней ничего нет». Признак пустоты считается
// по количеству внутри, а не по длине списка детей: при поиске контейнер,
// совпавший по собственному коду, намеренно остаётся без детей, и раньше
// получал чип «Пустая», имея внутри товар.
function dataWithPallet(): WarehouseMapData {
  return {
    warehouses: [{ id: 'w1', name: 'Подольск', code: 'podolsk' }],
    sellers: [],
    categories: [],
    journal: [],
    cells: [
      {
        id: 'c1',
        code: 'А 1.1',
        barcode: 'LOC-A11',
        qty: 67,
        children: [
          {
            kind: 'pallet',
            id: 'p1',
            code: 'П-001004',
            barcode: 'PLT-4',
            seller_name: 'Denmarcs',
            qty: 67,
            children: [
              {
                kind: 'product',
                id: 'b1',
                product_id: 'prod-1',
                name: 'Куртка',
                seller_name: 'Denmarcs',
                category: null,
                seller_article: 'SELLER-JACKET-42',
                barcode: '4680000000001',
                photo_url: null,
                qty: 67,
              },
            ],
          },
        ],
      },
    ],
    unassigned: [],
  } as unknown as WarehouseMapData
}

function palletRow(data: WarehouseMapData, query: string) {
  // Без поиска ячейки свёрнуты, и строки палеты в списке нет. Поэтому сначала
  // узнаём ключ ячейки, раскрываем её и строим список заново.
  const filters = { ...EMPTY_FILTERS, query }
  const collapsed = buildRows(data, { expandedKeys: new Set<string>(), filters })
  const expandedKeys = new Set(collapsed.filter((r) => r.expandable).map((r) => r.key))
  const rows = buildRows(data, { expandedKeys, filters })
  return rows.find((row) => row.kind === 'pallet')
}

describe('карта склада: признак пустоты', () => {
  it('без поиска непустая палета не помечена пустой', () => {
    const row = palletRow(dataWithPallet(), '')
    expect(row).toBeDefined()
    expect(row?.qty).toBe(67)
    expect(row?.empty).toBe(false)
  })

  it('при поиске по коду палеты чип «Пустая» не появляется — внутри 67 штук', () => {
    // Поиск по коду самой палеты обрезает её детей: оператор искал тару, а не
    // содержимое. Количество при этом остаётся настоящим, и врать нельзя.
    const row = palletRow(dataWithPallet(), 'П-001004')
    expect(row).toBeDefined()
    expect(row?.qty).toBe(67)
    expect(row?.empty).toBe(false)
  })

  it('по-настоящему пустая палета помечается пустой', () => {
    const data = dataWithPallet()
    const pallet = data.cells[0].children[0] as { qty: number; children: unknown[] }
    pallet.qty = 0
    pallet.children = []
    data.cells[0].qty = 0
    const row = palletRow(data, '')
    expect(row?.empty).toBe(true)
  })
})

describe('карта склада: идентификаторы товара', () => {
  it.each(['SELLER-JACKET-42', '4680000000001'])(
    'находит товар по значению %s',
    (query) => {
      const rows = buildRows(dataWithPallet(), {
        expandedKeys: new Set<string>(),
        filters: { ...EMPTY_FILTERS, query },
      })
      const product = rows.find((row) => row.kind === 'product')
      expect(product?.sellerArticle).toBe('SELLER-JACKET-42')
      expect(product?.barcode).toBe('4680000000001')
    },
  )
})
