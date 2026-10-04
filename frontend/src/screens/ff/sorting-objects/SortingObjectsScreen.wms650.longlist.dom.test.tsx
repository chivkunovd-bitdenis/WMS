// @vitest-environment jsdom
import { act } from 'react'
import { afterEach, beforeAll, beforeEach, describe, expect, it } from 'vitest'
import {
  CELLS,
  DOC_A,
  FakeSortingServer,
  PRODUCTS,
  click,
  fieldIsError,
  fieldText,
  highlightOf,
  installFetch,
  mainList,
  mountPage,
  must,
  placedCellHeader,
  prepareDom,
  resetStorage,
  rowIn,
  scannerInput,
  settle,
  unmount,
  type DocState,
  type Mounted,
} from './wms650TestKit'

// WMS-650 · приёмка аналитика, C21 / R16 на длинном списке (дополнение
// разработчика к контракту). Документ из 30 коробов: «+» у короба внизу
// списка, сервер отказывает. Отказ пишется под полем сканера, и поле обязано
// оказаться в окне; прокрутка к строке, переставленной в панель ячеек, не
// должна уводить страницу (панель прилипает к верху экрана — её строки
// прокручиваются только внутри панели). После окна «Куда положить» сканер
// снова слушает: фокус в поле сканера.

beforeAll(() => {
  prepareDom()
})

let restoreFetch: () => void = () => undefined
let page: Mounted | null = null
let calls: Element[] = []
const originalScroll = Element.prototype.scrollIntoView

function thirtyBoxes(): DocState {
  const objects = Array.from({ length: 30 }, (_, index) => ({
    id: `b${index + 1}`,
    kind: 'box' as const,
    code: `КР-${String(700 + index).padStart(6, '0')}`,
    barcode: `22000000${String(700 + index).padStart(5, '0')}`,
    holder: null,
  }))
  return {
    objects,
    lines: objects.map((one) => ({ id: `l-${one.id}`, productId: PRODUCTS.t1.id, qty: 2, holder: `obj:${one.id}` })),
  }
}

beforeEach(() => {
  resetStorage()
  calls = []
  Element.prototype.scrollIntoView = function scrollIntoView(this: Element) {
    calls.push(this)
  }
})

afterEach(() => {
  if (page) unmount(page)
  page = null
  restoreFetch()
  document.body.innerHTML = ''
  resetStorage()
  Element.prototype.scrollIntoView = originalScroll
})

describe('WMS-650 · длинный список: отказ виден, страница не уезжает', () => {
  it('C21 (длинный список): отказ «+» у нижнего короба — поле с отказом в окне, строка на месте', async () => {
    const server = new FakeSortingServer({ [DOC_A]: thirtyBoxes() })
    restoreFetch = installFetch(server)
    page = mountPage()
    await settle()
    await click(placedCellHeader(CELLS.a11))
    server.reject('place', 404, 'cell_not_found')
    calls = []

    await click(must('objects-tree-place-o-b30'))
    await click(must('objects-qty-confirm'))
    await settle()

    expect(server.requests('place')).toHaveLength(1)
    expect(fieldIsError()).toBe(true)
    expect(fieldText()).toContain('КР-000729')
    // Строка вернулась в основной список и подсвечена.
    expect(highlightOf(rowIn(mainList(), 'o-b30'))).toBe('touched')
    // Ни одной прокрутки страницы к строке панели ячеек: панель прокручивается сама.
    const panel = must('objects-cells')
    expect(calls.filter((element) => panel.contains(element))).toEqual([])
    // Последняя прокрутка страницы — к полю сканера с текстом отказа.
    expect(calls.length).toBeGreaterThan(0)
    expect(calls[calls.length - 1].contains(scannerInput())).toBe(true)
  })

  it('после окна «Куда положить» фокус возвращается в поле сканера', async () => {
    const server = new FakeSortingServer({ [DOC_A]: thirtyBoxes() })
    restoreFetch = installFetch(server)
    page = mountPage()
    await settle()
    await click(placedCellHeader(CELLS.a11))
    // Оператор нажимает «+» мышью: фокус уходит из поля сканера на кнопку.
    const plus = must('objects-tree-place-o-b30')
    act(() => {
      scannerInput().focus()
      plus.focus()
    })
    expect(document.activeElement).not.toBe(scannerInput())
    await click(plus)
    await click(must('objects-qty-confirm'))
    await settle(80)

    expect(server.requests('place')).toHaveLength(1)
    expect(document.activeElement).toBe(scannerInput())
  })
})
