import { describe, expect, it } from 'vitest'
import { buildInventorySheetHtml } from './printInventorySheet'
import type { ApiPrintSheet } from './inventoryCountApi'

// R2/R6/R9/R10: лист печатает ровно шапку и таблицу с зеброй, «Факт» всегда
// пуст, ничего лишнего (комментарий, статус, подписи, итоги) не появляется.
// Проверяем сборку HTML напрямую — так же, как принят лист приёмки
// (printInboundReceivingSheet.test.ts): тест не зависит от DOM и iframe-печати.

function sheet(overrides: Partial<ApiPrintSheet> = {}): ApiPrintSheet {
  return {
    number: 'ИНВ-1F69E69A',
    created_at: '2026-09-27T10:20:00+00:00',
    created_by: 'Смирнова Ольга',
    filters: {
      object: false,
      warehouse_name: 'Основной',
      seller_name: 'ООО Ловиана',
      category: 'Платья',
      product_articles: ['W497-DRESS', 'W497-OZ'],
    },
    rows: [
      {
        product_id: 'p1',
        barcode: '2000000000011',
        article: 'W497-DRESS',
        name: 'Платье миди',
        total: 20,
        reserved: 3,
      },
    ],
    ...overrides,
  }
}

describe('buildInventorySheetHtml', () => {
  it('печатает шапку: номер, создателя и дату в человеческом виде', () => {
    const html = buildInventorySheetHtml(sheet())
    expect(html).toContain('size: A4')
    expect(html).toContain('ИНВ-1F69E69A')
    expect(html).toContain('Создал: Смирнова Ольга')
    // humanMoment переводит ISO в «дд.мм.гггг чч:мм» в текущем часовом поясе —
    // не завязываемся на конкретное смещение, только на формат с точками.
    expect(html).toMatch(/\d{2}\.\d{2}\.2026 \d{2}:\d{2}/)
  })

  it('печатает строки отбора только для заданных параметров, в порядке Склад/Селлер/Категория/Товары', () => {
    const html = buildInventorySheetHtml(sheet())
    const order = ['Склад: Основной', 'Селлер: ООО Ловиана', 'Категория: Платья', 'Товары: W497-DRESS, W497-OZ']
    let lastIndex = -1
    for (const marker of order) {
      const idx = html.indexOf(marker)
      expect(idx).toBeGreaterThan(lastIndex)
      lastIndex = idx
    }
  })

  it('не печатает строку незаданного параметра отбора (без "Селлер: все")', () => {
    const html = buildInventorySheetHtml(
      sheet({ filters: { object: false, warehouse_name: 'Основной', seller_name: null, category: null, product_articles: null } }),
    )
    expect(html).toContain('Склад: Основной')
    expect(html).not.toContain('Селлер')
    expect(html).not.toContain('Категория')
    expect(html).not.toContain('Товары')
  })

  it('документ «по объекту» печатает только строку «По объекту», остальные поля отбора не выводит', () => {
    const html = buildInventorySheetHtml(
      sheet({
        filters: {
          object: true,
          warehouse_name: 'Основной',
          seller_name: 'ООО Ловиана',
          category: 'Платья',
          product_articles: ['W497-DRESS'],
        },
      }),
    )
    expect(html).toContain('По объекту')
    expect(html).not.toContain('Склад:')
    expect(html).not.toContain('Селлер:')
    expect(html).not.toContain('Категория:')
    expect(html).not.toContain('Товары:')
  })

  it('колонки в порядке ШК, Артикул, Название, Всего, В резерве, Факт', () => {
    const html = buildInventorySheetHtml(sheet())
    const headOrder = ['<th>ШК</th>', '<th>Артикул</th>', '<th>Название</th>', 'Всего', 'В резерве', 'Факт']
    let lastIndex = -1
    for (const marker of headOrder) {
      const idx = html.indexOf(marker)
      expect(idx).toBeGreaterThan(lastIndex)
      lastIndex = idx
    }
  })

  it('«Факт» всегда пуст — ни нуля, ни числа, ни плейсхолдера', () => {
    const html = buildInventorySheetHtml(sheet())
    expect(html).toContain('<td class="num fact" data-testid="inv-sheet-fact"></td>')
    expect(html).not.toMatch(/data-testid="inv-sheet-fact">[^<]+</)
  })

  it('строка «—» для отсутствующего ШК или артикула (R7)', () => {
    const html = buildInventorySheetHtml(
      sheet({ rows: [{ product_id: 'p3', barcode: null, article: null, name: 'Товар без кодов', total: 4, reserved: 0 }] }),
    )
    expect(html).toContain('<td class="barcode">—</td>')
    expect(html).toContain('<td class="article">—</td>')
  })

  it('отрицательный остаток печатается со знаком минус', () => {
    const html = buildInventorySheetHtml(
      sheet({ rows: [{ product_id: 'p5', barcode: '123', article: 'A5', name: 'Товар с недостачей', total: -2, reserved: 0 }] }),
    )
    expect(html).toContain('<td class="num total">-2</td>')
  })

  it('зебра: строки чередуют классы odd/even', () => {
    const html = buildInventorySheetHtml(
      sheet({
        rows: [
          { product_id: 'p1', barcode: '1', article: 'A1', name: 'Товар 1', total: 1, reserved: 0 },
          { product_id: 'p2', barcode: '2', article: 'A2', name: 'Товар 2', total: 2, reserved: 0 },
        ],
      }),
    )
    expect(html).toContain('<tr class="even"')
    expect(html).toContain('<tr class="odd"')
  })

  it('экранирует HTML в названии товара', () => {
    const html = buildInventorySheetHtml(
      sheet({ rows: [{ product_id: 'p1', barcode: '1', article: 'A1', name: '<script>alert(1)</script>', total: 1, reserved: 0 }] }),
    )
    expect(html).not.toContain('<script>alert(1)</script>')
    expect(html).toContain('&lt;script&gt;')
  })

  it('на листе нет ничего лишнего: комментария, статуса, подписи, итогов, номеров страниц', () => {
    // Смотрим только на видимую разметку внутри <body> — служебные комментарии
    // разработчика внутри <style> (не рендерятся и не печатаются) в счёт не идут.
    const html = buildInventorySheetHtml(sheet())
    const body = html.match(/<body>([\s\S]*)<\/body>/)?.[1] ?? html
    expect(body).not.toMatch(/коммент/i)
    expect(body).not.toMatch(/статус/i)
    expect(body).not.toMatch(/считал/i)
    expect(body).not.toMatch(/подпис/i)
    expect(body).not.toMatch(/итого/i)
    expect(body).not.toMatch(/страница/i)
  })

  it('заголовок таблицы повторяется на страницах, а шапка документа — нет (thead + не повторяющийся блок head)', () => {
    const html = buildInventorySheetHtml(sheet())
    expect(html).toContain('thead { display: table-header-group; }')
    // Шапка документа лежит в обычном div вне table — печатается один раз.
    expect(html.match(/<div class="head">/g)?.length).toBe(1)
  })
})
