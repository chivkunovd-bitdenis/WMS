// WMS-710: общие фикстуры проверок листа подбора для «Империи ФФ».
//
// Рабочая область берётся из уже записанного факта WMS-662 (реальная форма
// workspace), ответы pick-options и picking-context строятся здесь по форме
// боевого API. Лист читается как есть: тесты разбирают HTML колонки
// «Поставка / ячейка / короб» и сверяют последовательность мест с явно
// написанным ожиданием, а не с вычислением самой функции.
//
// Интерфейсный контракт для разработчика (фиксируется тестами, не выбирается им):
//  - пропс рабочей области и группы: pickListTabOrder (true только для Империи ФФ);
//  - строка picking-context получает аддитивное поле date («12.10.2025») у групп
//    приёмок и line_keys: ключ места, по которому строка сопоставляется с
//    pick-options (storage_location_id + '|' + id последней тары или 'loose').
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { expect } from 'vitest'
import type { FbsWorkspace } from './fbsApi'

export const SUPPLY_ID = '86b38d6f-f161-4acb-8ce1-da8d22d8796b'
export const PRODUCT_ID = 'ac552298-9ab3-4aac-be20-3ee8a207b7d8'
export const SORTING = 'Без ячеек'

export type Doc = { kind: 'П' | 'В'; number: string; date: string; id: string }
export const DOC = {
  P96: { kind: 'П', number: '96', date: '12.10.2025', id: '0a96a96a-0000-4000-8000-000000000096' },
  P80: { kind: 'П', number: '80', date: '05.09.2025', id: '0a80a80a-0000-4000-8000-000000000080' },
  V12: { kind: 'В', number: '12', date: '03.10.2025', id: '0b12b12b-0000-4000-8000-000000000012' },
} satisfies Record<string, Doc>

export type PlaceSpec = {
  cell: string
  box?: { id: string; number: number | null; barcode: string | null; pallet?: string }
  qty: number
  picked?: number
  doc: Doc | null
}

export type Scenario = {
  planned: number
  picked: number
  receipts: Doc[]
  places: PlaceSpec[]
}

export function docHeader(doc: Doc) {
  return `${doc.kind}: ${doc.number} · ${doc.date}`
}

/** Текст строки места так, как его отдаёт picking-context (формат бэкенда). */
export function stockLine(place: PlaceSpec) {
  const container = place.box
    ? `Короб${place.box.number ? ` №${place.box.number}` : ''}${place.box.barcode ? ` · ${place.box.barcode}` : ' · ШК не указан'}`
    : 'Россыпью'
  const cellPart = place.cell === SORTING ? '' : ` · ${place.cell}`
  return `${container}${cellPart}: ${place.qty} шт.`
}

function placeKey(place: PlaceSpec) {
  return `loc:${place.cell}|${place.box?.id ?? 'loose'}`
}

function pickOptionsOf(scenario: Scenario) {
  const byCell = new Map<string, PlaceSpec[]>()
  for (const place of scenario.places) byCell.set(place.cell, [...(byCell.get(place.cell) ?? []), place])
  const locations = [...byCell].map(([cell, places]) => {
    const sources = places.map((place) => ({
      quantity: place.qty,
      available: place.qty,
      picked: place.picked ?? 0,
      is_loose: !place.box,
      source_label: place.box ? `Короб ${place.box.id}` : 'Россыпью',
      container_path: place.box
        ? [
          ...(place.box.pallet
            ? [{ kind: 'pallet', id: `pal:${place.box.pallet}`, code: place.box.pallet, label: `Палета ${place.box.pallet}` }]
            : []),
          { kind: 'box', id: place.box.id, code: place.box.id, label: `Короб ${place.box.id}` },
        ]
        : [],
    }))
    return {
      storage_location_id: `loc:${cell}`,
      location_code: cell,
      quantity: places.reduce((sum, place) => sum + place.qty, 0),
      reserved: 0,
      available: places.reduce((sum, place) => sum + place.qty, 0),
      picked: places.reduce((sum, place) => sum + (place.picked ?? 0), 0),
      sources,
    }
  })
  return [{
    product_id: PRODUCT_ID,
    sku_code: 'SKU-ea0e949b67ab43998bc8e4e6a58bd21f-0',
    product_name: 'SKU 0',
    seller_article: null,
    barcode: null,
    planned_qty: scenario.planned,
    picked_qty: scenario.picked,
    locations,
  }]
}

function pickingContextOf(scenario: Scenario) {
  // Бэкенд отдаёт места по коду ячейки строкой и не отдаёт пустые места.
  const stock = scenario.places
    .filter((place) => place.qty > 0)
    .sort((a, b) => (a.cell < b.cell ? -1 : a.cell > b.cell ? 1 : (a.box?.number ?? 0) - (b.box?.number ?? 0)))
  const group = (key: string, title: string, date: string | null, places: PlaceSpec[]) => ({
    key,
    title,
    date,
    lines: places.map(stockLine),
    line_keys: places.map(placeKey),
  })
  const groups = scenario.receipts.map((doc) => group(
    `inbound:${doc.id}`, `${doc.kind}: ${doc.number}`, doc.date,
    stock.filter((place) => place.doc?.id === doc.id),
  ))
  const unlinked = stock.filter((place) => place.doc === null)
  if (unlinked.length) groups.push(group('unlinked', 'Без привязки к документу:', null, unlinked))
  return [{
    product_id: PRODUCT_ID,
    inbound_supplies: scenario.receipts.map((doc) => `${doc.number} · ${doc.date}`),
    locations: stock.map(stockLine),
    source_groups: groups,
  }]
}

export function jsonResponse(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } })
}

export function pickOptionsResponse(scenario: Scenario) {
  return jsonResponse(pickOptionsOf(scenario))
}

export function pickingContextResponse(scenario: Scenario) {
  return jsonResponse(pickingContextOf(scenario))
}

/** Та же поставка на площадке Ozon: позиции вместо товара заказа (C12). */
export function ozonWorkspace(): FbsWorkspace {
  const workspace = baseWorkspace()
  workspace.supply = { ...workspace.supply, marketplace: 'ozon', wb_supply_id: 'OZ-662' }
  workspace.orders = workspace.orders.map((order, index) => ({
    ...order,
    marketplace: 'ozon',
    external_order_id: `OZ-${index + 1}`,
    positions: [{
      id: `ozon-pos-${index + 1}`,
      image_url: null,
      barcode: null,
      product_id: PRODUCT_ID,
      marketplace_bindings: [],
      name: 'SKU 0',
      seller_article: null,
      sku: 'SKU-OZ-1',
      size: 'M',
      color: 'черный',
      brand: null,
      composition: null,
      quantity: 1,
      reserved_quantity: 0,
      picked_quantity: 0,
    }],
  })) as FbsWorkspace['orders']
  return workspace
}

/** Рабочая область поставки из записанного факта WMS-662, с кодами стикеров, чтобы печать не запрашивала стикеры. */
export function baseWorkspace(): FbsWorkspace {
  const proof = JSON.parse(readFileSync(resolve(
    process.cwd(), '../docs/reviews/wms662-663-priority/c19-run-37440990542/facts.json',
  ), 'utf8')) as { http: Array<{ url: string; status: number; body: unknown }> }
  const assembling = proof.http.find((entry) => entry.url.endsWith('/workspace')
    && (entry.body as FbsWorkspace).supply?.status === 'assembling')!
  const workspace = structuredClone(assembling.body as FbsWorkspace)
  workspace.orders.forEach((order, index) => {
    order.sticker = { code: `STK-${index + 1}`, status: 'ready', asset_url: null, applied_at: null } as typeof order.sticker
  })
  return workspace
}

/** Изображение печатного окна: пишет HTML в список, не открывая настоящего окна. */
export function fakePrintWindow(written: string[], onWrite?: (html: string) => void) {
  return {
    closed: false,
    opener: null as unknown,
    document: {
      open: () => undefined,
      write: (html: string) => {
        written.push(html)
        onWrite?.(html)
      },
      close: () => undefined,
    },
    close: () => undefined,
  }
}

/** Последний записанный HTML листа (не заглушка «Готовим лист подбора»). */
export function sheetHtml(written: string[]) {
  return written.filter((html) => html.includes('<table>')).at(-1)
}

/** Нормализация времени печати и срока: зависят от часового пояса хоста, не от кода. */
export function normalizeSheet(html: string) {
  return html
    .replace(/<div><span>Сдать до<\/span><strong>[^<]*<\/strong><\/div>/, '<div><span>Сдать до</span><strong>{deadline}</strong></div>')
    .replace(/Сформировано WMS: [^<]*?· Актуальное/, 'Сформировано WMS: {printed} · Актуальное')
}

/** Колонка «Поставка / ячейка / короб» (первая строка товара). */
export function sourcesCell(html: string) {
  const match = html.match(/<td class="sources">([\s\S]*?)<\/td>/)
  if (!match) throw new Error('В листе нет колонки «Поставка / ячейка / короб»')
  return match[1]
}

export function withoutSources(html: string) {
  return html.replace(/<td class="sources">[\s\S]*?<\/td>/, '<td class="sources">{sources}</td>')
}

type Token = { header: string } | { line: string }

function tokensOf(cell: string): Token[] {
  return [...cell.matchAll(/<strong>([^<]*)<\/strong>|<div>([^<]*)<\/div>/g)]
    .map((match) => (match[1] !== undefined ? { header: match[1] } : { line: match[2] ?? '' }))
}

export type WalkStep = { header?: string; line: string | RegExp }

/**
 * Сверяет колонку с ожидаемым обходом: строки мест идут именно в этом порядке,
 * лишних строк нет, над каждой строкой стоит заголовок её документа. Заголовки,
 * которые печатаются без строк, тоже считаются лишними (strictHeaders).
 */
export function expectWalk(cell: string, walk: WalkStep[], options: { strictHeaders?: boolean } = {}) {
  const strictHeaders = options.strictHeaders ?? true
  const printed: Array<{ header: string | null; line: string }> = []
  const headers: string[] = []
  let header: string | null = null
  for (const token of tokensOf(cell)) {
    if ('header' in token) {
      header = token.header
      headers.push(token.header)
    } else {
      printed.push({ header, line: token.line })
    }
  }
  const context = JSON.stringify({ printed, headers }, null, 1)
  expect(printed.length, `число строк мест: ${context}`).toBe(walk.length)
  walk.forEach((step, index) => {
    const got = printed[index]
    if (typeof step.line === 'string') expect(got.line, `строка ${index}: ${context}`).toBe(step.line)
    else expect(got.line, `строка ${index}: ${context}`).toMatch(step.line)
    if (strictHeaders && step.header !== undefined) {
      expect(got.header, `заголовок над строкой ${index}: ${context}`).toBe(step.header)
    }
  })
  if (strictHeaders) {
    const expectedHeaders = walk
      .map((step) => step.header)
      .filter((value): value is string => value !== undefined)
      .filter((value, index, all) => index === 0 || all[index - 1] !== value)
    expect(headers, `заголовки документов: ${context}`).toEqual(expectedHeaders)
  }
}

export const SCENARIO_C1: Scenario = {
  planned: 2,
  picked: 0,
  receipts: [DOC.V12, DOC.P80, DOC.P96],
  places: [
    { cell: 'А 1.2', box: { id: 'box-7', number: 7, barcode: 'BC-7', pallet: 'PAL-131' }, qty: 2, doc: DOC.P96 },
    { cell: 'Ж-1-7', box: { id: 'box-3', number: 3, barcode: 'BC-3' }, qty: 5, doc: DOC.P80 },
    { cell: 'Ж-1-14', qty: 3, doc: DOC.V12 },
    { cell: SORTING, qty: 1, doc: null },
  ],
}
