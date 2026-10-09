// @vitest-environment jsdom
import { afterEach, describe, expect, it } from 'vitest'
import { buildFbsPickingListPrintHtml, type FbsPickingListPrintInput, type FbsPickingListPrintRow } from './fbsUx'

const row = (patch: Partial<FbsPickingListPrintRow> = {}): FbsPickingListPrintRow => ({
  name: 'Товар', article: 'ART', color: 'Синий', size: 'Универсальный', imageUrl: null,
  identifiers: ['ART', 'WB 123'], locations: ['Я-7 · Короб BOX-725: 3'],
  inboundSupplies: ['Приёмка IN-725'], required: 3, picked: 1,
  wbOrders: [725001], stickerCodes: ['725123456'], marking: 'sgtin', ...patch,
})
const input = (rows: FbsPickingListPrintRow[], patch: Partial<FbsPickingListPrintInput> = {}): FbsPickingListPrintInput => ({
  supplyName: 'Поставка 725', wbSupplyId: 'WB-GI-725', marketplace: 'wb', sellerName: 'Селлер 725',
  wmsWarehouseName: 'Склад 725', routeLabel: 'Маршрут 725', deadlineLabel: '10.10.2026',
  printedAtLabel: '09.10.2026', rows, ...patch,
})
function render(value: FbsPickingListPrintInput) {
  const html = buildFbsPickingListPrintHtml(value)
  // Scripts are deliberately not executed: this contract inspects the real printable DOM/CSS.
  document.documentElement.innerHTML = html.replace(/<script>[\s\S]*?<\/script>/g, '')
  return html
}
const headers = () => Array.from(document.querySelectorAll('th'), el => el.textContent?.trim())
const bodyRows = () => Array.from(document.querySelectorAll('tbody tr'))
const cell = (tr: Element, label: string) => tr.querySelectorAll('td')[headers().indexOf(label)] as HTMLElement
function total(expected: number) {
  const matches = document.body.textContent?.match(/Общее количество:\s*\d+\s*шт\./g) ?? []
  expect(matches).toEqual([`Общее количество: ${expected} шт.`])
  const summary = [...document.body.querySelectorAll('*')].find(el => el.childElementCount === 0 && el.textContent?.trim() === matches[0])
    ?? [...document.body.querySelectorAll('*')].find(el => el.textContent?.trim() === matches[0])
  expect(summary).toBeDefined()
  expect(document.querySelector('table')!.compareDocumentPosition(summary!) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy()
  expect(summary!.compareDocumentPosition(document.querySelector('.footer')!) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy()
}
afterEach(() => { document.head.innerHTML = ''; document.body.innerHTML = '' })

describe('WMS-725 · контракт печатного листа', () => {
  it('c1_removes_position_column_preserves_document_ids_and_empty_colspan', () => {
    render(input([row({ required: 1 }), row({ required: 3, wbOrders: [725002] })]))
    expect(headers()).not.toContain('№')
    expect(document.querySelectorAll('td.number')).toHaveLength(0)
    expect(document.querySelector('tbody')!.textContent).not.toContain('2–4')
    for (const id of ['WB-GI-725', '725001', '725002', 'BOX-725', 'IN-725']) expect(document.body.textContent).toContain(id)
    for (const tr of bodyRows()) expect(tr.querySelectorAll('td')).toHaveLength(headers().length)
    expect(document.querySelectorAll('col')).toHaveLength(headers().length)
    render(input([]))
    expect(Number(document.querySelector('tbody td')!.getAttribute('colspan'))).toBe(headers().length)
  })
  it('c2_photo_is_84px_contained_missing_photo_and_input_are_preserved', () => {
    const value = input([row({ imageUrl: 'https://example.test/photo.png' }), row()])
    const before = JSON.stringify(value)
    const first = render(value)
    const style = getComputedStyle(document.querySelector('td img')!)
    expect(style.width).toBe('84px'); expect(style.height).toBe('84px'); expect(style.objectFit).toBe('contain')
    const imageCell = cell(bodyRows()[0]!, 'Фото')
    // Fixed pixel width, when supplied, must include the image and both cell paddings.
    const width = getComputedStyle(imageCell).width
    if (/px$/.test(width)) expect(parseFloat(width)).toBeGreaterThanOrEqual(84 + 2 * parseFloat(getComputedStyle(imageCell).paddingLeft))
    expect(cell(bodyRows()[1]!, 'Фото').textContent?.trim()).toBe('—')
    expect(render(value)).toBe(first); expect(JSON.stringify(value)).toBe(before)
    expect(first).toMatch(/@page\s*\{[^}]*size:\s*A4 landscape;[^}]*margin:\s*10mm/)
  })
  it('c3_picked_cells_stay_blank_and_bordered_without_changing_picked', () => {
    const value = input([0, 1, 3].map(picked => row({ picked })))
    const before = JSON.stringify(value)
    const first = render(value)
    expect(headers()).toContain('Подобрано')
    for (const tr of bodyRows()) {
      expect(cell(tr, 'Подобрано').textContent?.trim()).toBe('')
      expect(getComputedStyle(cell(tr, 'Подобрано')).borderTopStyle).toBe('solid')
      expect(cell(tr, 'Взять').textContent?.trim()).toBe('3')
    }
    expect(render(value)).toBe(first); expect(JSON.stringify(value)).toBe(before)
  })
  it('c4_total_counts_full_plan_once_for_single_group_ozon_and_empty_sheet', () => {
    for (const value of [input([row({ required: 1 }), row()]), input([row({ required: 7, picked: 6 })], { supplyName: 'Сборка · 2 поставки', marketplace: 'mixed' }), input([row({ required: 5, picked: 4, wbOrders: ['POSTING-1'] })], { marketplace: 'ozon' }), input(Array.from({ length: 80 }, () => row({ required: 3, picked: 3 })))]) {
      render(value); total(value.rows.reduce((sum, item) => sum + item.required, 0))
    }
    render(input([])); total(0)
    expect(document.body.textContent).toContain('В поставке нет товаров для подбора.')
  })
  it('wms710_imperiya_total_counts_product_plan_once_without_changing_place_rows', () => {
    const withPlanTotal = (rows: FbsPickingListPrintRow[], totalQuantity: number, patch: Partial<FbsPickingListPrintInput> = {}) => input(rows, {
      ...patch,
      totalQuantity,
    })

    // Империя печатает одну строку товара на каждое место, повторяя в колонке «Взять» полный план.
    const single = withPlanTotal([row({ required: 4 }), row({ required: 1 }), row({ required: 2 }), row({ required: 4 })], 7)
    render(single)
    total(7)
    expect(bodyRows()).toHaveLength(4)
    expect(bodyRows().map(tr => cell(tr, 'Взять').textContent?.trim())).toEqual(['4', '1', '2', '4'])

    const group = withPlanTotal([row({ required: 6 }), row({ required: 2 }), row({ required: 6 }), row({ required: 2 }), row({ required: 1 })], 11, {
      supplyName: 'Сборка · 2 поставки', marketplace: 'mixed',
    })
    render(group)
    total(11)
    expect(bodyRows()).toHaveLength(5)
    expect(bodyRows().map(tr => cell(tr, 'Взять').textContent?.trim())).toEqual(['6', '2', '6', '2', '1'])

    // Обычная печать уже содержит одну строку на товар и сохраняет прежний расчёт.
    render(input([row({ required: 4 }), row({ required: 1 }), row({ required: 2 })]))
    total(7)
  })
  it('c5_reference_and_four_meta_boxes_share_horizontal_row_with_full_values', () => {
    for (const long of [false, true]) for (const hasNumber of [false, true]) {
      const repeat = long ? 12 : 1
      const value = input([], { supplyName: 'Название '.repeat(repeat), wbSupplyId: hasNumber ? 'ID-725-'.repeat(repeat) : null, sellerName: 'Селлер '.repeat(repeat), wmsWarehouseName: 'Склад '.repeat(repeat), routeLabel: 'Маршрут '.repeat(repeat), deadlineLabel: 'Срок '.repeat(repeat) })
      render(value)
      const titleBlock = [...document.body.querySelectorAll('*')].find(el => el.childElementCount === 0 && el.textContent?.includes(value.supplyName.trim()))!
      expect(titleBlock).toBeDefined()
      const container = titleBlock.parentElement!
      expect(container).not.toBe(document.body)
      for (const label of ['Селлер', 'Склад WMS', 'Маршрут', 'Сдать до']) expect(container.textContent).toContain(label)
      expect(['flex', 'grid']).toContain(getComputedStyle(container).display)
      if (getComputedStyle(container).display === 'flex') expect(getComputedStyle(container).flexDirection).not.toBe('column')
      for (const valueText of [value.supplyName, value.sellerName, value.wmsWarehouseName, value.routeLabel, value.deadlineLabel]) expect(container.textContent).toContain(valueText.trim())
      if (hasNumber) expect(container.textContent).toContain(value.wbSupplyId)
      else expect(container.textContent).not.toMatch(/№\s*(WB|Ozon)/)
      expect(document.querySelector('h1')!.compareDocumentPosition(container) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy()
      expect(container.compareDocumentPosition(document.querySelector('table')!) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy()
    }
  })
})
