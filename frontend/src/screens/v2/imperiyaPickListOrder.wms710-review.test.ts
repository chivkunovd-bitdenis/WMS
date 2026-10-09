import { expect, it } from 'vitest'
import type { FbsPickOptionProduct, FbsPickingContext } from './fbsApi'
import {
  buildFbsPickingListPrintHtml,
  type FbsPickingListPrintRow,
} from './fbsUx'
import { imperiyaWalkRows } from './imperiyaPickListOrder'

type PrintRow = FbsPickingListPrintRow & { key: string }
type Source = {
  quantity: number
  available: number
  picked?: number
  is_loose: boolean
  source_label: string
  container_path: Array<{ kind: string; id: string; code: string; label: string }>
}
type Location = {
  storage_location_id: string
  location_code: string
  quantity: number
  reserved: number
  available: number
  picked: number
  sources: Source[]
}
type SourceGroup = {
  key: string
  title: string
  date?: string | null
  lines: string[]
  line_keys: string[]
}

function printRow(key: string, name: string, required: number, picked: number): PrintRow {
  return {
    key,
    name,
    size: 'S',
    color: null,
    article: `ART-${key}`,
    imageUrl: null,
    identifiers: [],
    locations: [],
    inboundSupplies: [],
    required,
    picked,
    wbOrders: [`ORDER-${key}`],
    stickerCodes: [`STICKER-${key}`],
    marking: `MARK-${key}`,
  }
}

function looseLocation(id: string, code: string, quantity: number): Location {
  return {
    storage_location_id: id,
    location_code: code,
    quantity,
    reserved: 0,
    available: quantity,
    picked: 0,
    sources: [{
      quantity,
      available: quantity,
      picked: 0,
      is_loose: true,
      source_label: 'Россыпью',
      container_path: [],
    }],
  }
}

function boxSource(id: string, quantity: number): Source {
  return {
    quantity,
    available: quantity,
    picked: 0,
    is_loose: false,
    source_label: 'Короб №3',
    container_path: [{ kind: 'box', id, code: '3', label: 'Короб №3' }],
  }
}

function option(
  productId: string,
  planned: number,
  picked: number,
  locations: Location[],
): FbsPickOptionProduct {
  return {
    product_id: productId,
    sku_code: `SKU-${productId}`,
    planned_qty: planned,
    picked_qty: picked,
    locations,
  } as unknown as FbsPickOptionProduct
}

function context(productId: string, groups: SourceGroup[]): FbsPickingContext {
  return {
    product_id: productId,
    inbound_supplies: groups.map((group) => group.title),
    locations: groups.flatMap((group) => group.lines),
    source_groups: groups,
  } as unknown as FbsPickingContext
}

function sheet(rows: FbsPickingListPrintRow[]): string {
  return buildFbsPickingListPrintHtml({
    supplyName: 'Проверочная поставка',
    wbSupplyId: 'WB-710',
    marketplace: 'wb',
    sellerName: 'Проверочный селлер',
    wmsWarehouseName: 'Проверочный склад',
    routeLabel: 'Склад / СЦ',
    deadlineLabel: '09.10.2026',
    printedAtLabel: '09.10.2026 12:00',
    rows,
  })
}

function tbodyRows(html: string): string[] {
  const body = html.match(/<tbody>([\s\S]*?)<\/tbody>/)?.[1]
  if (!body) throw new Error('В листе подбора нет tbody')
  return [...body.matchAll(/<tr>([\s\S]*?)<\/tr>/g)].map((match) => match[1])
}

function sourcesCell(row: string): string {
  const cell = row.match(/<td class="sources">([\s\S]*?)<\/td>/)?.[1]
  if (!cell) throw new Error('В строке нет колонки «Поставка / ячейка / короб»')
  return cell
}

it('C22: три места товара не создают повторные строки, количества и исходный порядок товаров', () => {
  const rows = [printRow('shirt', 'Товар A', 2, 1), printRow('cap', 'Товар B', 1, 0)]
  const options = [
    option('shirt', 2, 1, [
      looseLocation('loc-shirt-j14', 'Ж-1-14', 1),
      looseLocation('loc-shirt-a12', 'А 1.2', 1),
      looseLocation('loc-shirt-j7', 'Ж-1-7', 1),
    ]),
    option('cap', 1, 0, [looseLocation('loc-cap-a11', 'А 1.1', 1)]),
  ]

  const printed = imperiyaWalkRows(rows, options, []).map(({ key: _key, ...row }) => row)
  const html = sheet(printed)
  const outputRows = tbodyRows(html)

  expect(outputRows).toHaveLength(2)
  expect(outputRows.map((row) => row.match(/<strong>([^<]+)<\/strong>/)?.[1])).toEqual(['Товар A', 'Товар B'])
  expect(outputRows[0].match(/<td class="quantity">2<\/td>/g)).toHaveLength(1)
  const source = sourcesCell(outputRows[0])
  expect(source.indexOf('А 1.2')).toBeLessThan(source.indexOf('Ж-1-7'))
  expect(source.indexOf('Ж-1-7')).toBeLessThan(source.indexOf('Ж-1-14'))
})

it('C23: короба с одинаковым номером в одной ячейке сохраняют порядок приёмок вкладки', () => {
  const productId = 'same-number-boxes'
  const optionList = [option(productId, 2, 0, [{
    storage_location_id: 'loc-shared',
    location_code: 'Ж-1-7',
    quantity: 2,
    reserved: 0,
    available: 2,
    picked: 0,
    sources: [boxSource('box-p96', 1), boxSource('box-p80', 1)],
  }])]
  const contexts = [context(productId, [
    {
      key: 'inbound:p96', title: 'П: 96', date: '12.10.2025',
      lines: ['Короб №3 · BC-96 · Ж-1-7: 1 шт.'], line_keys: ['loc-shared|box-p96'],
    },
    {
      key: 'inbound:p80', title: 'П: 80', date: '05.09.2025',
      lines: ['Короб №3 · BC-80 · Ж-1-7: 1 шт.'], line_keys: ['loc-shared|box-p80'],
    },
  ])]

  const printed = imperiyaWalkRows([printRow(productId, 'Короба №3', 2, 0)], optionList, contexts)
  const source = tbodyRows(sheet(printed)).map(sourcesCell).join('')

  expect(source).toContain('П: 80 от 05.09.2025')
  expect(source).toContain('П: 96 от 12.10.2025')
  expect(source).toContain('BC-80')
  expect(source).toContain('BC-96')
  expect(source.indexOf('П: 80 от 05.09.2025')).toBeLessThan(source.indexOf('П: 96 от 12.10.2025'))
  expect(source.indexOf('BC-80')).toBeLessThan(source.indexOf('BC-96'))
})

it('C24: полностью подобранный товар без текущих мест печатает «Подобрано»', () => {
  const printed = imperiyaWalkRows(
    [printRow('picked-shirt', 'Товар уже подобран', 2, 2)],
    [option('picked-shirt', 2, 2, [])],
    [],
  )
  const source = sourcesCell(tbodyRows(sheet(printed))[0])

  expect(source.replace(/<[^>]*>/g, '').trim()).toBe('Подобрано')
})

it('C25: общий шаблон листа оставляет колонке «Размер» ширину 13 мм для короткого размера', () => {
  const html = sheet([printRow('short-size', 'Товар с коротким размером', 1, 0)])
  const widths = [...html.matchAll(/<col style="width:([\d.]+)%" \/>/g)].map((match) => match[1])

  // До hotfix компактная ширина считалась с обычным размером шрифта заголовка: 13 / 277 мм.
  expect(widths[4]).toBe('4.6931')
})

it('C28: unlinked сохраняет заголовок «Без привязки к документу:» над прежней строкой места', () => {
  const productId = 'unlinked-loose'
  const unlinkedLine = 'Россыпью: 5 шт.'
  const optionList = [option(productId, 2, 0, [
    {
      ...looseLocation('loc-inbound', 'Ж-1-7', 1),
      sources: [boxSource('box-p96', 1)],
    },
    looseLocation('loc-return', 'Ж-1-14', 1),
    looseLocation('loc-unlinked', 'Без ячеек', 5),
  ])]
  const contexts = [context(productId, [
    {
      key: 'inbound:p96', title: 'П: 96', date: '12.10.2025',
      lines: ['Короб №3 · BC-96 · Ж-1-7: 1 шт.'], line_keys: ['loc-inbound|box-p96'],
    },
    {
      key: 'inbound:return12', title: 'В: 12', date: '13.10.2025',
      lines: ['Россыпью · Ж-1-14: 1 шт.'], line_keys: ['loc-return|loose'],
    },
    {
      key: 'unlinked', title: 'Без привязки к документу:',
      lines: [unlinkedLine], line_keys: ['loc-unlinked|loose'],
    },
  ])]

  // Проверяем готовый HTML реального маршрутизатора и генератора печати, как в C4.
  const printed = imperiyaWalkRows([printRow(productId, 'Товар с россыпью без документа', 2, 0)], optionList, contexts)
  const outputRows = tbodyRows(sheet(printed))
  expect(outputRows).toHaveLength(1)
  const source = sourcesCell(outputRows[0])
  const groups = source.match(/<div class="source-group">[\s\S]*?<\/div><\/div>/g) ?? []
  const unlinkedGroup = groups.find((group) => group.includes(`<div>${unlinkedLine}</div>`))

  expect(unlinkedGroup).toBe(`<div class="source-group"><strong>Без привязки к документу:</strong><div>${unlinkedLine}</div></div>`)
})

it('C26/R5: шаблон листа Империи сохраняет ширину 13 мм для короткого размера S', () => {
  const html = buildFbsPickingListPrintHtml({
    supplyName: 'Проверочная поставка',
    wbSupplyId: 'WB-710',
    marketplace: 'wb',
    sellerName: 'Проверочный селлер',
    wmsWarehouseName: 'Проверочный склад',
    routeLabel: 'Склад / СЦ',
    deadlineLabel: '09.10.2026',
    printedAtLabel: '09.10.2026 12:00',
    imperiyaPickList: true,
    rows: [printRow('imperiya-short-size', 'Товар Империи с коротким размером', 1, 0)],
  })
  const colgroup = html.match(/<colgroup>([\s\S]*?)<\/colgroup>/)?.[1] ?? ''
  const widths = [...colgroup.matchAll(/width:([\d.]+)%/g)].map((match) => match[1])

  // Империи разрешено менять маршрут мест, но не ширину колонки «Размер»: после WMS-725 колонки «№» нет, «Размер» стоит в позиции 4.
  expect(widths[4]).toBe('4.6931')
})
