// @vitest-environment jsdom
import { act } from 'react'
import { afterEach, beforeAll, beforeEach, describe, expect, it } from 'vitest'
import {
  ACCEPTED_A,
  CELLS,
  DOC_A,
  DOC_B,
  FakeSortingServer,
  OBJ,
  PRODUCTS,
  byTestId,
  cellHolder,
  click,
  docA,
  docB,
  doubleClick,
  fieldIsError,
  fieldText,
  highlightOf,
  highlighted,
  installFetch,
  mainList,
  mountPage,
  must,
  numberIn,
  placedCell,
  placedCellHeader,
  prepareDom,
  reload,
  resetStorage,
  rowIn,
  scanCode,
  scannerInput,
  settle,
  unmount,
  whereShown,
  type Mounted,
} from './wms650TestKit'

// WMS-650 · этап 2 · контракт тестов экрана «Раскладка по ячейкам» внутри
// документа приёмки: основной список — только неразложенное, панель «Ячейки
// склада» — размещённое по ячейкам, выделение скана, отказы у поля сканера.
// Проверки C7, C8, C9 (экранная часть), C10, C11, C21, C23 (экранная часть)
// документа docs/requirements/WMS-650.md. Сервер подменён (wms650TestKit).
//
// data-testid и атрибуты, которые экран обязан отдать (новые), перечислены в
// шапке wms650TestKit.ts: objects-undo, objects-placed-qty, placed-cell-<id>,
// placed-toggle-<id>, placed-minus-<ключ>, placed-out-<ключ>, data-highlight.

beforeAll(() => {
  prepareDom()
})

let restoreFetch: () => void = () => undefined
let page: Mounted | null = null

function start(server: FakeSortingServer): FakeSortingServer {
  restoreFetch = installFetch(server)
  page = mountPage()
  return server
}

beforeEach(() => {
  resetStorage()
})

afterEach(() => {
  if (page) unmount(page)
  page = null
  restoreFetch()
  document.body.innerHTML = ''
  resetStorage()
})

const K1_ON_A12 = { [DOC_A]: docA({ k1: cellHolder(CELLS.a12) }), [DOC_B]: docB() }

function labelsAround(element: Element | null): string {
  const labels: string[] = []
  for (let node = element; node && node !== document.body; node = node.parentElement) {
    for (const attribute of ['aria-label', 'title']) {
      const value = node.getAttribute(attribute)
      if (value) labels.push(value)
    }
  }
  return labels.join(' | ')
}

describe('WMS-650 · раскладка: поставленное уходит из списка и видно под ячейкой', () => {
  // C7 · R8, R9, R11
  it('C7: К1, поставленный сканом, уходит из основного списка и виден под «А 1.2»', async () => {
    const server = start(new FakeSortingServer())
    await settle()
    expect(rowIn(mainList(), 'o-k1')).not.toBeNull()
    expect(numberIn('objects-left-qty')).toBe(ACCEPTED_A)

    await scanCode(CELLS.a12.barcode)
    await scanCode(OBJ.k1.barcode)

    expect(server.requests('place')).toHaveLength(1)
    expect(whereShown('o-k1')).toEqual({ main: false, cells: ['А 1.2'] })
    expect(highlightOf(rowIn(placedCell(CELLS.a12), 'o-k1'))).toBe('open')
    expect(numberIn('objects-left-qty')).toBe(ACCEPTED_A - 3)
    expect(must('objects-placed-qty').textContent).toMatch(/размещено\s*3\s*шт/)
    expect(fieldText()).toMatch(new RegExp(`${OBJ.k1.code}[^.]*положен\\S* на ячейку А 1\\.2\\. Тара (\\S+ )?открыта`))

    page = await reload(page!)
    expect(whereShown('o-k1')).toEqual({ main: false, cells: ['А 1.2'] })
    expect(highlightOf(rowIn(placedCell(CELLS.a12), 'o-k1'))).toBe('open')
    expect(numberIn('objects-left-qty')).toBe(ACCEPTED_A - 3)
    expect(must('objects-placed-qty').textContent).toMatch(/размещено\s*3\s*шт/)
  })

  // C8 · R10
  it('C8: у размещённого нет «+» и перетаскивания, есть «Снять с ячейки» и «Вынуть из короба»', async () => {
    start(new FakeSortingServer(K1_ON_A12))
    await settle()
    expect(rowIn(mainList(), 'o-k1')).toBeNull()
    const group = placedCell(CELLS.a12)
    const row = rowIn(group, 'o-k1')
    expect(row).not.toBeNull()
    expect(group.querySelector('[data-testid$="-place-o-k1"]')).toBeNull()
    expect(labelsAround(group.querySelector('[aria-label="Положить в место"]'))).toBe('')
    expect(row!.matches('[draggable="true"]') || row!.querySelector('[draggable="true"]')).toBeFalsy()
    const minus = byTestId('placed-minus-o-k1')
    expect(minus).not.toBeNull()
    expect(labelsAround(minus)).toContain('Снять с ячейки')

    await click(must('placed-toggle-k1'))
    const inside = rowIn(placedCell(CELLS.a12), 'l-l-k1')
    expect(inside).not.toBeNull()
    const out = byTestId('placed-out-l-l-k1')
    expect(out).not.toBeNull()
    expect(labelsAround(out)).toContain('Вынуть из короба')
    expect(byTestId('placed-minus-l-l-k1')).toBeNull()
    expect(inside!.querySelector('[data-testid$="-place-l-l-k1"]')).toBeNull()
  })

  // C9 (экранная часть; основная проверка — backend/tests/test_wms650_placement.py) · R10
  it('C9 (экран): явный перенос К1 сканом — «перенесён с А 1.2 на Б 1.1»', async () => {
    const server = start(new FakeSortingServer(K1_ON_A12))
    await settle()
    const left = numberIn('objects-left-qty')

    await scanCode(CELLS.b11.barcode)
    await scanCode(OBJ.k1.barcode)

    expect(server.requests('place')).toHaveLength(1)
    expect(server.requests('place')[0]).toMatchObject({ id: OBJ.k1.id, cell_id: CELLS.b11.id })
    expect(fieldText()).toMatch(/перенес\S* с А 1\.2 на Б 1\.1/)
    expect(whereShown('o-k1')).toEqual({ main: false, cells: ['Б 1.1'] })
    expect(numberIn('objects-left-qty')).toBe(left)
    expect(must('objects-placed-qty').textContent).toMatch(/размещено\s*3\s*шт/)
  })

  // C10 · R10
  it('C10: повторный скан К1 на открытой ячейке только открывает и закрывает его', async () => {
    const server = start(new FakeSortingServer(K1_ON_A12))
    await settle()
    await scanCode(CELLS.a12.barcode)
    await scanCode(OBJ.k1.barcode)

    expect(highlightOf(rowIn(placedCell(CELLS.a12), 'o-k1'))).toBe('open')
    expect(server.writes()).toEqual([])

    await scanCode(OBJ.k1.barcode)
    expect(highlightOf(rowIn(placedCell(CELLS.a12), 'o-k1'))).not.toBe('open')
    expect(fieldText()).toMatch(/закрыт/)
    expect(fieldText()).toMatch(/прямо в ячейку/)
    expect(server.writes()).toEqual([])
    expect(whereShown('o-k1')).toEqual({ main: false, cells: ['А 1.2'] })
  })

  // C11 · R11
  it('C11: выделение открытой ячейки, открытой тары и только что положенного', async () => {
    start(new FakeSortingServer())
    await settle()
    expect(scannerInput().getAttribute('aria-label')).toMatch(/ячейк/)

    await scanCode(CELLS.a12.barcode)
    expect(fieldText()).toBe('Ячейка А 1.2 открыта')
    expect(highlightOf(placedCellHeader(CELLS.a12))).toBe('open')
    expect(scannerInput().getAttribute('aria-label')).toMatch(/тару или товар/)

    await scanCode(OBJ.k1.barcode)
    expect(fieldText()).toMatch(/положен\S* на ячейку А 1\.2\. Тара (\S+ )?открыта/)
    expect(highlightOf(rowIn(placedCell(CELLS.a12), 'o-k1'))).toBe('open')
    expect(scannerInput().getAttribute('aria-label')).toMatch(/товар в/)

    await scanCode(PRODUCTS.t1.barcode)
    expect(fieldText()).toMatch(/^Носки спортивные, 3 пары: \+1 шт → .+\. Россыпью осталось 1$/)
    expect(highlightOf(rowIn(placedCell(CELLS.a12), 'l-l-k1'))).toBe('touched')
    expect(highlightOf(rowIn(placedCell(CELLS.a12), 'o-k1'))).toBe('open')
    expect(highlightOf(placedCellHeader(CELLS.a12))).toBe('open')

    await scanCode(CELLS.b11.barcode)
    expect(highlighted('touched')).toEqual([])
    expect(highlightOf(placedCellHeader(CELLS.b11))).toBe('open')
  })
})

type Rejection = 'plus' | 'drag' | 'minus' | 'out'

function dataTransfer() {
  const data = new Map<string, string>()
  return {
    setData: (type: string, value: string) => { data.set(type, value) },
    getData: (type: string) => data.get(type) ?? '',
    clearData: () => data.clear(),
    effectAllowed: 'move',
    dropEffect: 'move',
    types: [] as string[],
    files: [] as unknown[],
    items: [] as unknown[],
  }
}

function drag(type: string, target: Element, transfer: ReturnType<typeof dataTransfer>) {
  const event = new Event(type, { bubbles: true, cancelable: true })
  Object.defineProperty(event, 'dataTransfer', { value: transfer })
  act(() => {
    target.dispatchEvent(event)
  })
}

describe('WMS-650 · отказ сервера виден у поля сканера, строка возвращается', () => {
  // C21 · R16
  it.each<Rejection>(['plus', 'drag', 'minus', 'out'])('C21: отказ сервера (%s) виден под полем сканера, строка возвращается', async (variant) => {
    const onCell = variant === 'minus' || variant === 'out'
    const server = start(new FakeSortingServer(onCell ? K1_ON_A12 : undefined))
    await settle()
    const left = numberIn('objects-left-qty')
    await click(placedCellHeader(CELLS.a11))
    server.reject('place', 404, 'cell_not_found')

    let name: string
    let key: string
    if (variant === 'plus') {
      name = OBJ.k3.code
      key = 'o-k3'
      await click(must('objects-tree-place-o-k3'))
      await click(must('objects-qty-confirm'))
    } else if (variant === 'drag') {
      name = OBJ.k3.code
      key = 'o-k3'
      const transfer = dataTransfer()
      drag('dragstart', rowIn(mainList(), 'o-k3')!, transfer)
      drag('dragover', placedCellHeader(CELLS.a11), transfer)
      drag('drop', placedCellHeader(CELLS.a11), transfer)
      drag('dragend', rowIn(mainList(), 'o-k3') ?? document.body, transfer)
      await settle()
      expect(server.requests('place')).toHaveLength(1)
    } else if (variant === 'minus') {
      name = OBJ.k1.code
      key = 'o-k1'
      await click(must('placed-minus-o-k1'))
    } else {
      name = PRODUCTS.t1.name
      key = 'l-l-k1'
      await click(must('placed-toggle-k1'))
      await click(must('placed-out-l-l-k1'))
      await click(must('objects-qty-confirm'))
    }
    await settle()

    expect(server.requests('place')).toHaveLength(1)
    expect(fieldIsError()).toBe(true)
    expect(fieldText()).toContain(name)
    expect(fieldText()).not.toContain('cell_not_found')
    expect(fieldText()).toMatch(/[А-Яа-яЁё]{4,}/)
    if (onCell) {
      expect(whereShown(key)).toEqual({ main: false, cells: ['А 1.2'] })
      expect(highlightOf(rowIn(placedCell(CELLS.a12), key))).toBe('touched')
    } else {
      expect(whereShown(key)).toEqual({ main: true, cells: [] })
      expect(highlightOf(rowIn(mainList(), key))).toBe('touched')
    }
    expect(numberIn('objects-left-qty')).toBe(left)

    await click(placedCellHeader(CELLS.a11))
    await scanCode(OBJ.k2.barcode)
    expect(server.requests('place')).toHaveLength(2)
    expect(whereShown('o-k2')).toEqual({ main: false, cells: ['А 1.1'] })
    expect(fieldIsError()).toBe(false)
  })
})

describe('WMS-650 · двойной клик — одно действие (экранная часть C23)', () => {
  // C23 (экранная часть; основная проверка — backend/tests/test_wms650_placement.py) · R17
  it('C23 (экран): двойной клик «Положить» и «Снять с ячейки» — один запрос', async () => {
    const server = start(new FakeSortingServer(K1_ON_A12))
    await settle()
    await click(placedCellHeader(CELLS.a11))
    await click(must('objects-tree-place-o-k3'))
    await doubleClick(must('objects-qty-confirm'))
    expect(server.requests('place')).toHaveLength(1)

    await doubleClick(must('placed-minus-o-k1'))
    expect(server.requests('place')).toHaveLength(2)
  })
})
