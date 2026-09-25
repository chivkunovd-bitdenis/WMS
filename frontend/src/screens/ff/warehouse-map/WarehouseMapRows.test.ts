import { describe, expect, it } from 'vitest'
import { EMPTY_FILTERS, buildRows, findByBarcode } from './WarehouseMapRows'
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

// WMS-536: скан на карте склада. Сначала ячейка и тара по их штрихкоду, потом
// товар единым поиском по карточкам склада. Фикстуры — раздел 9 постановки.
describe('WMS-536: поиск сканером на карте склада', () => {
  const WB_P = '4601234567893'
  const WB_A = '4601234567886'
  const OZN = 'OZN-987654'
  const CYR = 'ФА_МОД8-4а/083/42'

  type Product = Extract<WarehouseMapData['unassigned'][number], { kind: 'product' }>

  function productNode(overrides: Partial<Product> = {}): Product {
    return {
      kind: 'product',
      id: 'balance-p',
      product_id: 'prod-p',
      name: 'Товар P',
      seller_name: 'ИП',
      category: null,
      seller_article: 'ART-P',
      barcode: WB_P,
      scan_codes: [WB_P, WB_A, OZN],
      sku_code: 'AbC-42',
      photo_url: null,
      qty: 3,
      ...overrides,
    }
  }

  /** «Без ячеек» с `unassigned`, ячейка А-01 с коробом КР-1 и россыпью `loose`. */
  function map(
    inBox: Product[],
    loose: Product[] = [],
    unassigned: WarehouseMapData['unassigned'] = [],
  ): WarehouseMapData {
    return {
      warehouses: [],
      sellers: [],
      categories: [],
      journal: [],
      unassigned,
      cells: [
        {
          id: 'c1',
          code: 'А-01',
          barcode: 'LOC-A01',
          qty: 5,
          children: [
            {
              kind: 'box',
              id: 'b1',
              code: 'КР-1',
              barcode: 'BOX-1',
              seller_name: null,
              qty: 3,
              children: inBox,
            },
            ...loose,
          ],
        },
      ],
    }
  }

  function foundKey(data: WarehouseMapData, code: string): string | null {
    const result = findByBarcode(data, code)
    return result.status === 'found' ? result.target.key : null
  }

  it.each([
    ['основной WB-ШК', WB_P],
    ['дополнительный WB-ШК размера', WB_A],
    ['Ozon-штрихкод', OZN],
    ['SKU в другом регистре', 'aBc-42'],
    ['код с пробелами по краям', `  ${WB_P}\t`],
  ])('%s находит строку товара', (_label, code) => {
    const result = findByBarcode(map([productNode()]), code)
    expect(result).toEqual({
      status: 'found',
      target: {
        key: 'c1/b1/balance-p',
        ancestorKeys: ['c1', 'c1/b1'],
        title: 'Товар P',
        placeLabel: 'Короб КР-1',
      },
    })
  })

  it('кириллический артикул находится как есть', () => {
    expect(foundKey(map([productNode({ sku_code: CYR })]), CYR)).toBe('c1/b1/balance-p')
  })

  it('русская раскладка на карте не исправляется: поле ручное', () => {
    const data = map([productNode({ sku_code: 'Chin-56005' })])
    expect(findByBarcode(data, 'Сршт-56005')).toEqual({ status: 'not_found' })
  })

  it('код двух разных карточек — неоднозначность, ничего не подсвечивается', () => {
    const data = map(
      [productNode({ sku_code: 'DUP-536' })],
      [productNode({ id: 'balance-q', product_id: 'prod-q', barcode: '4609999999990', scan_codes: ['DUP-536'], sku_code: 'Q' })],
    )
    expect(findByBarcode(data, 'DUP-536')).toEqual({ status: 'ambiguous' })
  })

  it('одна карточка в двух местах — не неоднозначность: подсвечивается первая по дереву', () => {
    const data = map([productNode()], [productNode({ id: 'balance-p-loose', qty: 2 })])
    expect(foundKey(data, WB_A)).toBe('c1/b1/balance-p')
  })

  it('код ячейки и короба важнее кода товара — даже товара в «Без ячеек»', () => {
    const product = productNode({ scan_codes: [WB_P, 'LOC-A01', 'BOX-1'] })
    const data = map([], [], [product])
    expect(foundKey(data, 'LOC-A01')).toBe('c1')
    expect(foundKey(data, 'BOX-1')).toBe('c1/b1')
    // Сам товар по-прежнему находится своим кодом.
    expect(foundKey(data, WB_P)).toBe('unassigned/balance-p')
  })

  it('КИЗ с GS и без GS товаром не считается', () => {
    const data = map([productNode()])
    expect(findByBarcode(data, '010460123456789321SERIAL536\x1d91ABCD\x1d92SIGNATURE536')).toEqual({
      status: 'not_found',
    })
    expect(findByBarcode(data, '010460123456789321SERIAL53691ABCD92SIGNATURE536')).toEqual({
      status: 'not_found',
    })
  })

  it('13 и 14 знаков — разные коды', () => {
    const data = map(
      [productNode({ scan_codes: ['4601234567893'], barcode: '4601234567893' })],
      [productNode({ id: 'balance-q', product_id: 'prod-q', barcode: '04601234567893', scan_codes: ['04601234567893'], sku_code: 'Q' })],
    )
    expect(foundKey(data, '4601234567893')).toBe('c1/b1/balance-p')
    expect(foundKey(data, '04601234567893')).toBe('c1/balance-q')

    const onlyP = map([productNode({ scan_codes: ['4601234567893'], barcode: '4601234567893' })])
    expect(findByBarcode(onlyP, '04601234567893')).toEqual({ status: 'not_found' })
  })

  it('сервер без scan_codes и sku_code: товар находится по barcode, как раньше', () => {
    const legacy = productNode({ scan_codes: undefined, sku_code: undefined })
    const data = map([legacy])
    expect(foundKey(data, WB_P)).toBe('c1/b1/balance-p')
    expect(findByBarcode(data, WB_A)).toEqual({ status: 'not_found' })
  })

  it('палета и грузоместо по-прежнему находятся по своему штрихкоду', () => {
    const data = dataWithPallet()
    expect(foundKey(data, 'plt-4')).toBe('c1/p1')
    expect(foundKey(data, '4680000000001')).toBe('c1/p1/b1')
    expect(findByBarcode(data, '')).toEqual({ status: 'not_found' })
  })
})
