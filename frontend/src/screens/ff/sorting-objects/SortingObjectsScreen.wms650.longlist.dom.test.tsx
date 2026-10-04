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

describe('WMS-650 · узкая панель: длинный номер тары не налезает на количество', () => {
  it('C27/R20: номер тары целиком с многоточием и подсказкой, количество не сжимается', async () => {
    const code = 'INB-N98WC9V0Y3MT9C'
    const doc: DocState = {
      objects: [{ id: 'long', kind: 'box', code, barcode: '2200000099999', holder: `cell:${CELLS.a11.id}` }],
      lines: [{ id: 'l-long', productId: PRODUCTS.t1.id, qty: 7, holder: 'obj:long' }],
    }
    const server = new FakeSortingServer({ [DOC_A]: doc })
    restoreFetch = installFetch(server)
    page = mountPage()
    await settle()

    const label = must('placed-code-long')
    expect(label.textContent).toBe(code)
    expect(label.getAttribute('title')).toBe(code)
    const text = getComputedStyle(label)
    expect(text.whiteSpace).toBe('nowrap')
    expect(text.overflow).toBe('hidden')
    expect(text.textOverflow).toBe('ellipsis')
    expect(text.maxWidth).toBe('100%')
    expect(text.display).toBe('inline-block')
    // Колонка названия может сжиматься до нуля, количество и кнопка — нет.
    const nameColumn = label.closest('p')?.parentElement as HTMLElement
    expect(getComputedStyle(nameColumn).minWidth).toBe('0')
    const qty = must('placed-qty-o-long')
    expect(getComputedStyle(qty).flexShrink).toBe('0')
    expect(qty.textContent).toContain('7')
    expect(getComputedStyle(must('placed-minus-o-long').parentElement!.parentElement!).flexShrink).toBe('0')
  })
})

describe('WMS-650 · фокус после окна не отбирается у другого поля', () => {
  it('таймер возврата фокуса не забирает его у поля, где оператор уже печатает', async () => {
    const server = new FakeSortingServer({ [DOC_A]: thirtyBoxes() })
    restoreFetch = installFetch(server)
    page = mountPage()
    await settle()
    await click(placedCellHeader(CELLS.a11))
    await click(must('objects-tree-place-o-b30'))
    await click(must('objects-qty-confirm'))
    const other = document.createElement('input')
    document.body.appendChild(other)
    act(() => other.focus())
    await settle(80)
    expect(document.activeElement).toBe(other)
  })
})
