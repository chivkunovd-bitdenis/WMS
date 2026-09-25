import { describe, expect, it } from 'vitest'
import {
  applyScan,
  inventoryProductScanIndex,
  inventoryRowPathKeys,
  NOTHING_OPEN,
  scanCandidates,
} from './InventoryScan'
import { countFromMapRow } from './fromWarehouseMap'
import { toCount } from './inventoryCountApi'
import { PRODUCT_SCAN_AMBIGUOUS_MESSAGE } from '../../../utils/productScanResolver'
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
    scannableCells: [],
    scannableContainers: [],
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
        barcode: 'CELL-BARCODE-1',
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
    const opened = applyScan(count, 'BOX-BARCODE-1', NOTHING_OPEN)
    const scanned = applyScan(opened.count, '4601234567890', opened.open)

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
    const scanned = applyScan(count, 'sku-jacket-1', { containerId: 'box-1', cellId: null })

    expect(scanned.tone).toBe('ok')
    expect(actualOf(scanned.count)).toBe(1)
    expect(scanned.focusRowKey).toBe('product:line-1')
  })

  it('increments the same product on every repeated scan', () => {
    const count = countWithBox(product())
    const first = applyScan(count, '4601234567890', { containerId: 'box-1', cellId: null })
    const second = applyScan(first.count, '4601234567890', { containerId: 'box-1', cellId: null })

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

    const opened = applyScan(count, 'BOX-BARCODE-42', NOTHING_OPEN)
    const scanned = applyScan(opened.count, 'BARCODE-42-7', opened.open)

    expect(scanned.focusRowKey).toBe('product:line-42-7')
    expect(buildRows(scanned.count, EMPTY_FILTERS, new Set())).toHaveLength(1101)

    let rapidCount = opened.count
    const startedAt = performance.now()
    for (let scan = 0; scan < 1000; scan += 1) {
      rapidCount = applyScan(rapidCount, 'BARCODE-42-7', { containerId: 'box-42', cellId: null }).count
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
    const opened = applyScan(count, 'BOX-BARCODE-1', NOTHING_OPEN)
    expect(opened.open.containerId).toBe('box-1')

    const closed = applyScan(opened.count, 'BOX-BARCODE-1', opened.open)
    expect(closed.open.containerId).toBeNull()
    expect(closed.tone).toBe('ok')
    expect(closed.message).toContain('закрыт')
  })

  it('незнакомый код при открытой таре становится находкой в эту тару', () => {
    const count = countWithBox(product())
    const opened = applyScan(count, 'BOX-BARCODE-1', NOTHING_OPEN)
    const found = applyScan(opened.count, '9999999999999', opened.open)

    // Ячейку тары сервер возьмёт из её карточки — экран её не называет.
    expect(found.found).toEqual({
      barcodes: ['9999999999999'],
      cellId: null,
      containerKind: 'box',
      containerId: 'box-1',
    })
    // Сам скан строку не заводит: её создаёт сервер и возвращает документ.
    expect(found.count).toBe(opened.count)
  })

  it('на находку уходят оба прочтения кода: русская раскладка и латиница', () => {
    const count = countWithBox(product())
    const opened = applyScan(count, 'BOX-BARCODE-1', NOTHING_OPEN)
    const found = applyScan(opened.count, 'Сршт-56005', opened.open)

    expect(found.found?.barcodes).toEqual(['Сршт-56005', 'Chin-56005'])
  })

  it('закрытие короба оставляет его ячейку открытой — можно считать россыпь', () => {
    // Ровно тот сценарий, который назвал владелец: пикнул короб второй раз и
    // считаешь дальше россыпь. Вопрос «в какую ячейку» решается сам: в ту, где
    // этот короб стоит.
    const count = countWithBox(product())
    const opened = applyScan(count, 'BOX-BARCODE-1', NOTHING_OPEN)
    const closed = applyScan(opened.count, 'BOX-BARCODE-1', opened.open)

    expect(closed.open).toEqual({ containerId: null, cellId: 'cell-1' })

    const found = applyScan(closed.count, '9999999999999', closed.open)
    expect(found.found).toEqual({
      barcodes: ['9999999999999'],
      cellId: 'cell-1',
      containerKind: null,
      containerId: null,
    })
  })

  it('ячейку можно открыть и закрыть сканом её штрихкода', () => {
    const count = countWithBox(product())
    const opened = applyScan(count, 'CELL-BARCODE-1', NOTHING_OPEN)
    expect(opened.open).toEqual({ containerId: null, cellId: 'cell-1' })
    expect(opened.message).toContain('Ячейка A-01 открыта')

    const closed = applyScan(opened.count, 'CELL-BARCODE-1', opened.open)
    expect(closed.open).toEqual({ containerId: null, cellId: null })
  })

  it('товар из тары, посчитанный россыпью, записывается находкой и предупреждает', () => {
    // Не запрещаем: он правда может лежать россыпью. Но если оператор просто
    // забыл пикнуть короб, строка короба останется непосчитанной, и один товар
    // посчитается дважды — поэтому говорим об этом прямо.
    const count = countWithBox(product())
    const opened = applyScan(count, 'CELL-BARCODE-1', NOTHING_OPEN)
    const result = applyScan(opened.count, '4601234567890', opened.open)

    expect(result.tone).toBe('warn')
    expect(result.message).toContain('Если он лежит в таре')
    expect(result.found?.containerId).toBeNull()
    expect(result.found?.cellId).toBe('cell-1')
  })

  it('экран без доступа к серверу находок не обещает', () => {
    const count = countWithBox(product())
    const opened = applyScan(count, 'BOX-BARCODE-1', NOTHING_OPEN)
    const result = applyScan(opened.count, '9999999999999', opened.open, false)

    expect(result.found).toBeUndefined()
    expect(result.message).toContain('полном документе')
  })
})


describe('россыпь без ячейки', () => {
  it('ничего не открыто — находка уходит без ячейки и без тары', () => {
    // Первый пункт модели владельца: «просто сканирую товар — он падает в
    // россыпь, без ячейки». Адрес в этом случае определяет сервер: это зона
    // сортировки, а не какая-то угаданная ячейка документа.
    const count = countWithBox(product())
    const result = applyScan(count, '9999999999999', NOTHING_OPEN)

    expect(result.found).toEqual({
      barcodes: ['9999999999999'],
      cellId: null,
      containerKind: null,
      containerId: null,
    })
  })

  it('открытое место заменяется одним сканом, без выхода', () => {
    const count = countWithBox(product())
    const box = applyScan(count, 'BOX-BARCODE-1', NOTHING_OPEN)
    expect(box.open).toEqual({ containerId: 'box-1', cellId: 'cell-1' })

    // Пикнул ячейку прямо поверх открытого короба — короб закрылся сам.
    const cell = applyScan(box.count, 'CELL-BARCODE-1', box.open)
    expect(cell.open).toEqual({ containerId: null, cellId: 'cell-1' })
  })
})

describe('пустая по учёту ячейка', () => {
  it('сканер узнаёт ячейку, которой нет в дереве, и находка идёт в неё', () => {
    // «В ячейке лежит то, чего по учёту тут быть не должно» — первый случай,
    // ради которого пересчёт и делают. Раньше штрихкод такой ячейки сканер не
    // знал: уходил искать товар, не находил и предлагал записать находку со
    // штрихкодом ЯЧЕЙКИ вместо товара.
    const count: InventoryCount = {
      ...countWithBox(product()),
      scannableCells: [{ id: 'cell-empty', label: 'B-07', barcode: 'CELL-EMPTY-7' }],
    }

    const opened = applyScan(count, 'CELL-EMPTY-7', NOTHING_OPEN)
    expect(opened.open).toEqual({ containerId: null, cellId: 'cell-empty' })
    expect(opened.message).toContain('B-07')

    const found = applyScan(opened.count, '9999999999999', opened.open)
    expect(found.found).toEqual({
      barcodes: ['9999999999999'],
      cellId: 'cell-empty',
      containerKind: null,
      containerId: null,
    })
  })
})

describe('короб узнаётся и по видимому номеру', () => {
  it('открывается и по штрихкоду, и по номеру на ярлыке', () => {
    // У приёмочного короба штрихкод внутренний — INB-…, — а человек читает на
    // ярлыке «BOX-1». Если системный ярлык не наклеен, открыть короб внутренним
    // кодом нечем, и содержимое посчитать нельзя вовсе.
    const count = countWithBox(product())

    const byBarcode = applyScan(count, 'BOX-BARCODE-1', NOTHING_OPEN)
    expect(byBarcode.open.containerId).toBe('box-1')

    const byCode = applyScan(count, 'BOX-1', NOTHING_OPEN)
    expect(byCode.open.containerId).toBe('box-1')
    expect(byCode.message).toContain('открыт')
  })

  it('ячейка открывается и по своей подписи', () => {
    const count = countWithBox(product())
    const byLabel = applyScan(count, 'A-01', NOTHING_OPEN)
    expect(byLabel.open).toEqual({ containerId: null, cellId: 'cell-1' })
  })
})

describe('пустая по документу тара выброшена из дерева, но пикается', () => {
  // В пересчёте «Империи ФФ» из 420 коробов товар лежал в 113. Остальные 307
  // висели строками «0 из 0»: документ вырастал до сорока тысяч пикселей, и
  // найти в нём свой короб глазами было нельзя. Строки убрали — но подойти к
  // такому коробу и посчитать то, что в нём лежит, оператор обязан.
  const dropped = {
    kind: 'box' as const,
    id: 'box-empty',
    code: 'КР-000108',
    barcode: 'INB-1B7EE88D369F',
    cellId: 'cell-1',
  }

  it('открывается по штрихкоду и по видимому номеру', () => {
    const count: InventoryCount = {
      ...countWithBox(product()),
      scannableContainers: [dropped],
    }

    const byBarcode = applyScan(count, 'INB-1B7EE88D369F', NOTHING_OPEN)
    expect(byBarcode.open).toEqual({ containerId: 'box-empty', cellId: 'cell-1' })
    expect(byBarcode.message).toContain('КР-000108')

    const byCode = applyScan(count, 'КР-000108', NOTHING_OPEN)
    expect(byCode.open.containerId).toBe('box-empty')
  })

  it('находка ложится именно в него, а не в ячейку рядом', () => {
    const count: InventoryCount = {
      ...countWithBox(product()),
      scannableContainers: [dropped],
    }

    const opened = applyScan(count, 'INB-1B7EE88D369F', NOTHING_OPEN)
    const found = applyScan(opened.count, '9999999999999', opened.open)

    expect(found.found).toEqual({
      barcodes: ['9999999999999'],
      cellId: null,
      containerKind: 'box',
      containerId: 'box-empty',
    })
    expect(found.message).toContain('записываем находку')
  })

  it('тара из дерева важнее выброшенной: строку не теряем', () => {
    const count: InventoryCount = {
      ...countWithBox(product()),
      scannableContainers: [{ ...dropped, id: 'box-empty', barcode: 'BOX-BARCODE-1' }],
    }

    const scanned = applyScan(count, 'BOX-BARCODE-1', NOTHING_OPEN)
    expect(scanned.open.containerId).toBe('box-1')
    expect(scanned.focusPathKeys).toBeDefined()
  })
})

// WMS-536: товар на пересчёте ищется единым поиском по карточкам документа.
// Фикстуры — раздел 9 постановки: реальные строки, а не «какой-нибудь код».
describe('WMS-536: единый поиск товара на пересчёте', () => {
  const WB_P = '4601234567893'
  const WB_A = '4601234567886'
  const OZN = 'OZN-987654'
  const CYR = 'ФА_МОД8-4а/083/42'
  const KIZ_GS = '010460123456789321SERIAL536\x1d91ABCD\x1d92SIGNATURE536'
  const KIZ_NO_GS = '010460123456789321SERIAL53691ABCD92SIGNATURE536'

  function productP(overrides: Partial<ProductNode> = {}): ProductNode {
    return product({
      id: 'line-p',
      productId: 'prod-p',
      name: 'Товар P',
      sku: 'AbC-42',
      barcode: WB_P,
      wbBarcode: WB_P,
      scanCodes: [WB_P, WB_A, OZN],
      ...overrides,
    })
  }

  function productQ(overrides: Partial<ProductNode> = {}): ProductNode {
    return product({
      id: 'line-q',
      productId: 'prod-q',
      name: 'Товар Q',
      sku: 'Q-SKU',
      barcode: '4609999999990',
      wbBarcode: '4609999999990',
      scanCodes: ['4609999999990'],
      ...overrides,
    })
  }

  /** Ячейка A-01: короб BOX-1 с товаром из `inBox` и россыпь `loose`. */
  function doc(inBox: ProductNode[], loose: ProductNode[] = []): InventoryCount {
    const base = countWithBox(product())
    return {
      ...base,
      cells: [
        {
          id: 'cell-1',
          label: 'A-01',
          barcode: 'CELL-BARCODE-1',
          children: [
            { kind: 'box', id: 'box-1', code: 'BOX-1', barcode: 'BOX-BARCODE-1', children: inBox },
            ...loose,
          ],
        },
      ],
    }
  }

  function actualOfLine(count: InventoryCount, lineId: string): number | null {
    let actual: number | null | undefined
    function walk(nodes: InventoryCount['cells'][number]['children']) {
      for (const node of nodes) {
        if (node.kind === 'product') {
          if (node.id === lineId) actual = node.actual
        } else {
          walk(node.children)
        }
      }
    }
    for (const cell of count.cells) walk(cell.children)
    if (actual === undefined) throw new Error(`no line ${lineId}`)
    return actual
  }

  const IN_BOX = { containerId: 'box-1', cellId: 'cell-1' }

  it.each([
    ['основной WB-ШК', WB_P],
    ['дополнительный WB-ШК размера', WB_A],
    ['Ozon-штрихкод', OZN],
    ['SKU в другом регистре', 'aBc-42'],
    ['код с пробелами и переводом строки по краям', `\t ${WB_P}\r\n`],
  ])('%s находит карточку и прибавляет штуку в открытом коробе', (_label, code) => {
    const count = doc([productP()])
    const scanned = applyScan(count, code, IN_BOX)

    expect(scanned.tone).toBe('ok')
    expect(actualOfLine(scanned.count, 'line-p')).toBe(1)
    expect(scanned.focusRowKey).toBe('product:line-p')
    expect(scanned.found).toBeUndefined()
  })

  it('кириллический артикул находится как есть — и с клавиатурного сканера, и руками', () => {
    const count = doc([productP({ sku: CYR })])
    // Клавиатурный сканер отдаёт исходные символы и свой латинский перевод.
    const viaWedge = applyScan(count, CYR, IN_BOX, true, 'AF_VJL8-4f/083/42')
    expect(actualOfLine(viaWedge.count, 'line-p')).toBe(1)

    const viaField = applyScan(count, CYR, IN_BOX)
    expect(actualOfLine(viaField.count, 'line-p')).toBe(1)
  })

  it('исходная кириллица важнее перевода раскладки: второй товар не проверяется', () => {
    const translated = scanCandidates(CYR)[1]
    expect(translated).toBeDefined()
    const count = doc([productP({ sku: CYR }), productQ({ sku: translated })])

    const scanned = applyScan(count, CYR, IN_BOX)
    expect(scanned.tone).toBe('ok')
    expect(actualOfLine(scanned.count, 'line-p')).toBe(1)
    expect(actualOfLine(scanned.count, 'line-q')).toBeNull()
  })

  it('код, пикнутый в русской раскладке, находится по переводу — со сканера и руками', () => {
    const count = doc([productP({ sku: 'Chin-56005' })])

    const viaWedge = applyScan(count, 'Сршт-56005', IN_BOX, true, 'Chin-56005')
    expect(actualOfLine(viaWedge.count, 'line-p')).toBe(1)

    const viaField = applyScan(count, 'Сршт-56005', IN_BOX)
    expect(actualOfLine(viaField.count, 'line-p')).toBe(1)
  })

  it('код двух карточек не выбирает строку — даже ту, что лежит в открытом коробе', () => {
    // До WMS-536 побеждала строка открытого короба. Теперь известная коллизия
    // останавливает скан: факт, находка и открытое место не меняются (R2).
    const count = doc([productP({ sku: 'DUP-536' })], [productQ({ scanCodes: ['DUP-536'] })])
    const scanned = applyScan(count, 'DUP-536', IN_BOX)

    expect(scanned.tone).toBe('error')
    expect(scanned.message).toBe(PRODUCT_SCAN_AMBIGUOUS_MESSAGE)
    expect(scanned.count).toBe(count)
    expect(scanned.open).toBe(IN_BOX)
    expect(scanned.found).toBeUndefined()
    expect(scanned.focusRowKey).toBeUndefined()
  })

  it('неоднозначность не превращается в находку и без открытого места, и в диалоге с карты', () => {
    const count = doc([productP({ sku: 'DUP-536' })], [productQ({ scanCodes: ['DUP-536'] })])

    const nothingOpen = applyScan(count, 'DUP-536', NOTHING_OPEN)
    expect(nothingOpen.message).toBe(PRODUCT_SCAN_AMBIGUOUS_MESSAGE)
    expect(nothingOpen.found).toBeUndefined()

    const dialog = applyScan(count, 'DUP-536', IN_BOX, false)
    expect(dialog.message).toBe(PRODUCT_SCAN_AMBIGUOUS_MESSAGE)
    expect(dialog.count).toBe(count)
  })

  it('одна карточка в двух местах — не неоднозначность: пик идёт в открытое место', () => {
    const inBox = productP()
    const loose = productP({ id: 'line-p-loose' })
    const count = doc([inBox], [loose])

    const boxScan = applyScan(count, WB_A, IN_BOX)
    expect(actualOfLine(boxScan.count, 'line-p')).toBe(1)
    expect(actualOfLine(boxScan.count, 'line-p-loose')).toBeNull()

    const looseScan = applyScan(count, WB_A, { containerId: null, cellId: 'cell-1' })
    expect(actualOfLine(looseScan.count, 'line-p-loose')).toBe(1)
    expect(actualOfLine(looseScan.count, 'line-p')).toBeNull()
  })

  it('код ячейки и тары важнее кода товара', () => {
    const count: InventoryCount = {
      ...doc([productP({ scanCodes: [WB_P, 'CELL-PROD-536', 'BOX-PROD-536'] })]),
    }
    count.cells[0] = { ...count.cells[0], barcode: 'CELL-PROD-536' }
    const box = count.cells[0].children[0]
    if (box.kind === 'product') throw new Error('expected box')
    count.cells[0].children[0] = { ...box, barcode: 'BOX-PROD-536' }

    const cell = applyScan(count, 'CELL-PROD-536', NOTHING_OPEN)
    expect(cell.open).toEqual({ containerId: null, cellId: 'cell-1' })
    expect(cell.count).toBe(count)

    const opened = applyScan(count, 'BOX-PROD-536', NOTHING_OPEN)
    expect(opened.open.containerId).toBe('box-1')
    expect(opened.count).toBe(count)
  })

  it('КИЗ с GS и без GS товаром не считается, GS уходит на сервер нетронутым', () => {
    const count = doc([productP()])

    const withGs = applyScan(count, KIZ_GS, IN_BOX)
    expect(withGs.count).toBe(count)
    expect(withGs.found?.barcodes).toEqual([KIZ_GS])

    const withoutGs = applyScan(count, KIZ_NO_GS, IN_BOX)
    expect(withoutGs.count).toBe(count)
    expect(withoutGs.found?.barcodes).toEqual([KIZ_NO_GS])
  })

  it('13 и 14 знаков — разные коды: ведущий ноль не снимается', () => {
    const count = doc(
      [productP({ scanCodes: ['4601234567893'] })],
      [productQ({ scanCodes: ['04601234567893'] })],
    )
    const p = applyScan(count, '4601234567893', IN_BOX)
    expect(actualOfLine(p.count, 'line-p')).toBe(1)
    expect(actualOfLine(p.count, 'line-q')).toBeNull()

    const q = applyScan(count, '04601234567893', { containerId: null, cellId: 'cell-1' })
    expect(actualOfLine(q.count, 'line-q')).toBe(1)
    expect(actualOfLine(q.count, 'line-p')).toBeNull()

    const onlyP = doc([productP({ scanCodes: ['4601234567893'] })])
    const miss = applyScan(onlyP, '04601234567893', IN_BOX)
    expect(miss.count).toBe(onlyP)
    expect(miss.found?.barcodes).toEqual(['04601234567893'])
  })

  it('знакомый товар в чужом месте уходит находкой по тому прочтению, по которому узнан', () => {
    const count = doc([productP({ sku: 'Chin-56005' })])
    const cellOpen = { containerId: null, cellId: 'cell-1' }

    const layout = applyScan(count, 'Сршт-56005', cellOpen, true, 'Chin-56005')
    expect(layout.found?.barcodes).toEqual(['Chin-56005'])

    const direct = applyScan(count, WB_A, cellOpen)
    expect(direct.found?.barcodes).toEqual([WB_A])
    expect(direct.message).toContain('Товар P')

    // Незнакомый код — оба прочтения, сервер проверит их по порядку.
    const unknown = applyScan(count, 'Сршт-99999', cellOpen, true, 'Chin-99999')
    expect(unknown.found?.barcodes).toEqual(['Сршт-99999', 'Chin-99999'])
  })

  it('сервер без scan_codes: поиск по barcode, wbBarcode и sku, как раньше', () => {
    const count = doc([productP({ scanCodes: undefined, productId: undefined })])
    expect(actualOfLine(applyScan(count, WB_P, IN_BOX).count, 'line-p')).toBe(1)
    expect(actualOfLine(applyScan(count, 'abc-42', IN_BOX).count, 'line-p')).toBe(1)
    expect(applyScan(count, WB_A, IN_BOX).found?.barcodes).toEqual([WB_A])
  })

  function apiLine(overrides: Record<string, unknown> = {}) {
    return {
      kind: 'product' as const,
      id: 'line-p',
      product_id: 'prod-p',
      scan_codes: [WB_P, WB_A, OZN],
      name: 'Товар P',
      sku: 'AbC-42',
      seller: 'ИП',
      category: null,
      barcode: WB_P,
      wb_vendor_code: null,
      wb_barcode: WB_P,
      wb_size: null,
      photo_url: null,
      expected: 1,
      actual: null,
      expected_now: null,
      ...overrides,
    }
  }

  function apiDetail(children: ReturnType<typeof apiLine>[]) {
    return {
      id: 'count-1',
      number: 'ИНВ-1',
      status: 'draft',
      warehouse_id: null,
      warehouse_name: 'Склад',
      fill: { mode: 'object' as const, seller_id: null, category: null, object_label: 'Ячейка A-01' },
      created_at: '',
      created_by: '',
      posted_at: null,
      posted_by: null,
      comment: '',
      address_storage: true,
      cells: [{ id: 'cell-1', label: 'A-01', barcode: null, children }],
    }
  }

  it('ответ сервера переносит карточку и все её коды в строку документа', () => {
    const count = toCount(apiDetail([apiLine()]))
    const line = count.cells[0].children[0]
    if (line.kind !== 'product') throw new Error('expected product')
    expect(line.productId).toBe('prod-p')
    expect(line.scanCodes).toEqual([WB_P, WB_A, OZN])

    const scanned = applyScan(count, OZN, { containerId: null, cellId: 'cell-1' })
    expect(actualOfLine(scanned.count, 'line-p')).toBe(1)

    // Старый сервер без новых полей: строка без карточки и без списка кодов.
    const legacy = toCount(apiDetail([apiLine({ product_id: undefined, scan_codes: undefined })]))
    const legacyLine = legacy.cells[0].children[0]
    if (legacyLine.kind !== 'product') throw new Error('expected product')
    expect(legacyLine.productId).toBeUndefined()
    expect(legacyLine.scanCodes).toBeUndefined()
  })

  it('быстрый пересчёт с карты: все коды карточки, неоднозначность, находок нет', () => {
    // Диалог с карты получает документ от сервера (createObjectCount → toCount)
    // и считает без записи находок (allowFound=false).
    const count = toCount(
      apiDetail([
        apiLine(),
        apiLine({
          id: 'line-q',
          product_id: 'prod-q',
          name: 'Товар Q',
          sku: 'Q-SKU',
          barcode: '4609999999990',
          wb_barcode: '4609999999990',
          scan_codes: ['4609999999990', 'DUP-536'],
        }),
        apiLine({ id: 'line-p2', scan_codes: [WB_P, WB_A, OZN, 'DUP-536'] }),
      ]),
    )
    const cellOpen = { containerId: null, cellId: 'cell-1' }

    for (const code of [WB_P, WB_A, OZN, 'aBc-42']) {
      const scanned = applyScan(count, code, cellOpen, false)
      expect(scanned.tone).toBe('ok')
      expect(actualOfLine(scanned.count, 'line-p')).toBe(1)
    }

    const ambiguous = applyScan(count, 'DUP-536', cellOpen, false)
    expect(ambiguous.message).toBe(PRODUCT_SCAN_AMBIGUOUS_MESSAGE)
    expect(ambiguous.count).toBe(count)

    const unknown = applyScan(count, '9999999999999', cellOpen, false)
    expect(unknown.found).toBeUndefined()
    expect(unknown.count).toBe(count)
    expect(unknown.message).toContain('полном документе')
  })

  it('превью диалога с карты: одна карточка в двух строках карты — не неоднозначность', () => {
    const shared = {
      kind: 'product' as const,
      product_id: 'prod-p',
      name: 'Товар P',
      seller_name: null,
      category: null,
      seller_article: null,
      barcode: WB_P,
      scan_codes: [WB_P, WB_A],
      photo_url: null,
    }
    const map = {
      warehouses: [],
      sellers: [],
      categories: [],
      journal: [],
      unassigned: [],
      cells: [
        {
          id: 'cell-1',
          code: 'A-01',
          barcode: 'CELL-BARCODE-1',
          qty: 3,
          children: [
            { ...shared, id: 'balance-loose', qty: 2 },
            {
              kind: 'box' as const,
              id: 'box-1',
              code: 'BOX-1',
              barcode: 'BOX-BARCODE-1',
              seller_name: null,
              qty: 1,
              children: [{ ...shared, id: 'balance-box', qty: 1 }],
            },
          ],
        },
      ],
    }
    const count = countFromMapRow(map, { kind: 'cell', id: 'cell-1', title: 'Ячейка A-01' }, 'Склад', true)
    if (!count) throw new Error('expected count')

    const scanned = applyScan(count, WB_A, { containerId: 'box-1', cellId: 'cell-1' }, false)
    expect(scanned.tone).toBe('ok')
    expect(actualOfLine(scanned.count, 'balance-box')).toBe(1)
    expect(actualOfLine(scanned.count, 'balance-loose')).toBeNull()
  })

  it('10 000 карточек со всеми кодами: индекс строится один раз, сто сканов подряд быстрые', () => {
    const boxes = Array.from({ length: 1000 }, (_, boxIndex) => ({
      kind: 'box' as const,
      id: `box-${boxIndex}`,
      code: `BOX-${boxIndex}`,
      barcode: `BOX-BARCODE-${boxIndex}`,
      children: Array.from({ length: 10 }, (_, productIndex) => {
        const n = boxIndex * 10 + productIndex
        return product({
          id: `line-${n}`,
          productId: `prod-${n}`,
          sku: `SKU-${n}`,
          barcode: `WB-${n}`,
          wbBarcode: `WB-${n}`,
          scanCodes: [`WB-${n}`, `WB-A-${n}`, `WB-B-${n}`, `OZN-${n}`],
        })
      }),
    }))
    const count: InventoryCount = {
      ...countWithBox(product()),
      cells: [{ id: 'cell-1', label: 'A-01', children: boxes }],
    }

    const index = inventoryProductScanIndex(count)
    const opened = applyScan(count, 'BOX-BARCODE-999', NOTHING_OPEN)
    let current = opened.count
    const startedAt = performance.now()
    for (let scan = 0; scan < 100; scan += 1) {
      current = applyScan(current, 'OZN-9997', opened.open).count
    }
    const elapsedMs = performance.now() - startedAt

    expect(actualOfLine(current, 'line-9997')).toBe(100)
    // Пик переносит индекс на новый снимок: на сотом скане он всё тот же.
    expect(inventoryProductScanIndex(current)).toBe(index)
    expect(elapsedMs).toBeLessThan(2000)
  })
})
