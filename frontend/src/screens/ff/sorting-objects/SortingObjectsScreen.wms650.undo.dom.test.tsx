// @vitest-environment jsdom
import { afterEach, beforeAll, beforeEach, describe, expect, it } from 'vitest'
import {
  ACCEPTED_A,
  CELLS,
  DOC_A,
  DOC_B,
  FakeSortingServer,
  OBJ,
  PRODUCTS,
  TOKEN_1,
  TOKEN_2,
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
  json,
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
  undoButton,
  undoHint,
  unmount,
  whereShown,
  type Mounted,
} from './wms650TestKit'

// WMS-650 · этап 2 · контракт тестов стрелки «назад» на экране раскладки.
// Проверки C12 (экранная часть), C13, C14, C15 (экранная часть), C16 (экранная
// часть), C17, C28 (экранная часть) документа docs/requirements/WMS-650.md.
//
// Стрелка — data-testid="objects-undo" рядом с полем сканера (значок
// UndoOutlined, как «Отменить последний скан» упаковки FBS). Отмена — запрос
// POST /warehouses/{id}/sorting-objects/undo с inbound_request_id, своим
// operation_id и target_operation_id = operation_id отменяемого действия (того
// самого запроса place/scan, который подтвердил сервер). Коды отказа сервера:
// undo_target_moved (C15), undo_document_posted (C28).

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

function lastOp(server: FakeSortingServer, route: 'place' | 'scan'): string {
  const all = server.requests(route)
  return String(all[all.length - 1]?.operation_id ?? '')
}

function undoTargets(server: FakeSortingServer): string[] {
  return server.requests('undo').map((body) => String(body.target_operation_id))
}

describe('WMS-650 · «назад» на экране раскладки', () => {
  // C12 (экранная часть; основная проверка — backend/tests/test_wms650_undo.py) · R12
  it('C12 (экран): «назад» после постановки К2 сканом возвращает его в основной список', async () => {
    const server = start(new FakeSortingServer())
    await settle()
    expect(undoButton().disabled).toBe(true)
    await scanCode(CELLS.a11.barcode)
    await scanCode(OBJ.k2.barcode)
    const placed = lastOp(server, 'place')
    expect(whereShown('o-k2')).toEqual({ main: false, cells: ['А 1.1'] })
    expect(undoButton().disabled).toBe(false)
    expect(await undoHint()).toMatch(new RegExp(`Отменить: [^|]*${OBJ.k2.code}`))

    await click(undoButton())

    expect(server.requests('undo')).toHaveLength(1)
    expect(server.requests('undo')[0]).toMatchObject({ inbound_request_id: DOC_A, target_operation_id: placed })
    expect(String(server.requests('undo')[0].operation_id)).not.toBe(placed)
    expect(whereShown('o-k2')).toEqual({ main: true, cells: [] })
    expect(highlightOf(rowIn(mainList(), 'o-k2'))).toBe('touched')
    expect(fieldText()).toMatch(new RegExp(`^Отменено: .*${OBJ.k2.code}`))
    expect(highlightOf(placedCellHeader(CELLS.a11))).toBe('open')
    expect(highlighted('open')).toHaveLength(1)
    expect(numberIn('objects-left-qty')).toBe(ACCEPTED_A)

    page = await reload(page!)
    expect(whereShown('o-k2')).toEqual({ main: true, cells: [] })
    expect(numberIn('objects-left-qty')).toBe(ACCEPTED_A)
  })

  // C13 · R12
  it('C13: три «назад» подряд отменяют в обратном порядке до пустой истории', async () => {
    const server = start(new FakeSortingServer(K1_ON_A12))
    await settle()
    const left = numberIn('objects-left-qty')
    await scanCode(CELLS.a11.barcode)
    await scanCode(OBJ.k2.barcode)
    const op1 = lastOp(server, 'place')
    await scanCode(PRODUCTS.t1.barcode)
    const op2 = lastOp(server, 'scan')
    await click(must('placed-minus-o-k1'))
    const op3 = lastOp(server, 'place')
    expect(new Set([op1, op2, op3]).size).toBe(3)
    expect(whereShown('o-k1')).toEqual({ main: true, cells: [] })

    await click(undoButton())
    expect(document.querySelector('[role="dialog"]')).toBeNull()
    expect(undoTargets(server)).toEqual([op3])
    expect(document.activeElement).toBe(scannerInput())
    await click(undoButton())
    await click(undoButton())

    expect(undoTargets(server)).toEqual([op3, op2, op1])
    expect(whereShown('o-k1')).toEqual({ main: false, cells: ['А 1.2'] })
    expect(whereShown('o-k2')).toEqual({ main: true, cells: [] })
    expect(numberIn('objects-left-qty')).toBe(left)
    expect(undoButton().disabled).toBe(true)
    expect(await undoHint()).toContain('Отменять нечего')
    expect(document.querySelector('[role="dialog"]')).toBeNull()
    expect(document.activeElement).toBe(scannerInput())
  })

  // C14 · R13, Д1
  it('C14: история «назад» переживает обновление и принадлежит документу и сотруднику', async () => {
    const server = start(new FakeSortingServer())
    await settle()
    await scanCode(CELLS.a11.barcode)
    await scanCode(OBJ.k2.barcode)
    await scanCode(OBJ.k3.barcode)
    const op2 = lastOp(server, 'place')
    expect(whereShown('o-k3')).toEqual({ main: false, cells: ['А 1.1'] })

    page = await reload(page!)
    expect(undoButton().disabled).toBe(false)
    expect(await undoHint()).toContain(OBJ.k3.code)
    await click(undoButton())
    expect(undoTargets(server)).toEqual([op2])
    expect(whereShown('o-k3')).toEqual({ main: true, cells: [] })

    page = await reload(page!, { doc: DOC_B })
    expect(undoButton().disabled).toBe(true)
    page = await reload(page!, { doc: DOC_A, token: TOKEN_2 })
    expect(undoButton().disabled).toBe(true)
    page = await reload(page!, { doc: DOC_A, token: TOKEN_1 })
    expect(undoButton().disabled).toBe(false)
    expect(await undoHint()).toContain(OBJ.k2.code)

    // Вкладку закрыли: sessionStorage пуст, localStorage остался.
    sessionStorage.clear()
    page = await reload(page!, { doc: DOC_A, token: TOKEN_1 })
    expect(undoButton().disabled).toBe(true)
  })

  // C15 (экранная часть; основная проверка — backend/tests/test_wms650_undo.py) · R13, Д4
  it('C15 (экран): отказ undo_target_moved — причина под полем, шаг снят', async () => {
    const server = start(new FakeSortingServer())
    await settle()
    await scanCode(CELLS.a12.barcode)
    await scanCode(OBJ.k1.barcode)
    const op0 = lastOp(server, 'place')
    await scanCode(CELLS.a11.barcode)
    await scanCode(OBJ.k2.barcode)
    const op1 = lastOp(server, 'place')
    server.reject('undo', 409, 'undo_target_moved')

    await click(undoButton())
    expect(undoTargets(server)).toEqual([op1])
    expect(fieldIsError()).toBe(true)
    expect(fieldText()).toContain(OBJ.k2.code)
    expect(fieldText()).toMatch(/уже перемещ\S* после этого действия/)
    expect(fieldText()).toMatch(/отменить нельзя/)
    expect(whereShown('o-k2')).toEqual({ main: false, cells: ['А 1.1'] })
    expect(undoButton().disabled).toBe(false)
    expect(await undoHint()).toContain(OBJ.k1.code)

    await click(undoButton())
    expect(undoTargets(server)).toEqual([op1, op0])
    expect(whereShown('o-k1')).toEqual({ main: true, cells: [] })
  })

  // C16 (экранная часть; основная проверка — backend/tests/test_wms650_undo.py) · R13, R17
  it('C16 (экран): сбой отмены — шаг остаётся, повтор с тем же operation_id, двойной клик — один запрос', async () => {
    const server = start(new FakeSortingServer())
    await settle()
    await scanCode(CELLS.a11.barcode)
    await scanCode(OBJ.k2.barcode)
    const op1 = lastOp(server, 'place')
    server.once('undo', () => json({ detail: 'Internal Server Error' }, 500))

    await click(undoButton())
    expect(fieldIsError()).toBe(true)
    expect(whereShown('o-k2')).toEqual({ main: false, cells: ['А 1.1'] })
    expect(undoButton().disabled).toBe(false)
    expect(await undoHint()).toContain(OBJ.k2.code)

    await click(undoButton())
    const [first, second] = server.requests('undo')
    expect(second).toMatchObject({ target_operation_id: op1, operation_id: first.operation_id })
    expect(whereShown('o-k2')).toEqual({ main: true, cells: [] })

    await scanCode(OBJ.k3.barcode)
    expect(whereShown('o-k3')).toEqual({ main: false, cells: ['А 1.1'] })
    await doubleClick(undoButton())
    expect(server.requests('undo')).toHaveLength(3)
    expect(whereShown('o-k3')).toEqual({ main: true, cells: [] })
  })

  // C17 · R13
  it('C17: «назад» до подтверждения постановки встаёт в очередь после неё', async () => {
    const server = start(new FakeSortingServer())
    await settle()
    await scanCode(CELLS.a12.barcode)
    const release = server.hold('place')
    await scanCode(OBJ.k3.barcode)
    await click(undoButton())
    expect(server.requests('undo')).toHaveLength(0)

    release()
    await settle()
    const placed = lastOp(server, 'place')
    expect(undoTargets(server)).toEqual([placed])
    const order = server.log.map((one) => one.path.split('/').pop())
    expect(order.lastIndexOf('place')).toBeLessThan(order.lastIndexOf('undo'))
    expect(whereShown('o-k3')).toEqual({ main: true, cells: [] })
    expect(server.requests('place')).toHaveLength(1)
    expect(server.requests('undo')).toHaveLength(1)

    server.reject('place', 409, 'nothing_to_move')
    await scanCode(OBJ.k1.barcode)
    expect(fieldIsError()).toBe(true)
    expect(undoButton().disabled).toBe(true)
    expect(await undoHint()).toContain('Отменять нечего')
  })

  // C28 (экранная часть; основная проверка — backend/tests/test_wms650_undo.py) · R12, R13, Д5
  it('C28 (экран): отказ undo_document_posted — причина Д5 под полем, шаг снят', async () => {
    const server = start(new FakeSortingServer())
    await settle()
    await scanCode(CELLS.a11.barcode)
    await scanCode(OBJ.k2.barcode)
    server.reject('undo', 409, 'undo_document_posted')

    await click(undoButton())
    expect(fieldIsError()).toBe(true)
    expect(fieldText()).toMatch(/Приёмка уже оприходована этим действием — отменить нельзя; переставьте тару сканом в нужную ячейку/)
    expect(whereShown('o-k2')).toEqual({ main: false, cells: ['А 1.1'] })
    expect(rowIn(placedCell(CELLS.a11), 'o-k2')).not.toBeNull()
    expect(undoButton().disabled).toBe(true)
    expect(await undoHint()).toContain('Отменять нечего')
  })
})
