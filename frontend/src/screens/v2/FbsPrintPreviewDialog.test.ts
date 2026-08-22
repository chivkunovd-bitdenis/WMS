import { describe, expect, it } from 'vitest'
import { buildFbsPrintPreviewSequence, buildFbsTapePairHtml, getFbsMarkingPrintSource } from './FbsPrintPreviewDialog'
import { getFullFbsPickingOrderIds, type FbsPrintAsset } from './fbsApi'

function asset(id: string, orderNumber: number, wbOrderId: number): FbsPrintAsset {
  return {
    id,
    kind: 'order_sticker',
    status: 'ready',
    content_type: 'image/png',
    width_mm: 40,
    height_mm: 58,
    preview_url: `/preview/${id}`,
    download_url: null,
    checksum: null,
    applied_at: null,
    error: null,
    order_number: orderNumber,
    wb_order_id: wbOrderId,
  }
}

describe('Предпросмотр полной ленты FBS', () => {
  it('TC-S03-006 отправляет полный набор ID в порядке серверного листа, не workspace.orders', () => {
    const serverPickingList = [
      { article: 'A', sku_code: null, size: 'M', product_name: 'Первый', quantity: 2, number_start: 1, number_end: 2, order_ids: ['order-2', 'order-1'] },
      { article: 'B', sku_code: null, size: null, product_name: 'Второй', quantity: 1, number_start: 3, number_end: 3, order_ids: ['order-3'] },
    ]

    expect(getFullFbsPickingOrderIds(serverPickingList)).toEqual(['order-2', 'order-1', 'order-3'])
  })

  it('TC-S03-006 сохраняет серверные номера и ставит пропуск между готовыми парами', () => {
    const sequence = buildFbsPrintPreviewSequence(
      [
        { asset: asset('third', 6, 845004), objectUrl: 'blob:third' },
        { asset: asset('first', 4, 845002), objectUrl: 'blob:first' },
      ],
      [{ order_id: 'missing', wb_order_id: 845003, order_number: 5 }],
    )

    expect(sequence.map((entry) => entry.kind === 'ready'
      ? `WMS № ${entry.preview.asset.order_number}`
      : `Заказ WB №${entry.item.wb_order_id}: стикер не получен`))
      .toEqual([
        'WMS № 4',
        'Заказ WB №845003: стикер не получен',
        'WMS № 6',
      ])
  })

  it('TC-S03-007 не перенумеровывает готовую пару после отсутствующего стикера', () => {
    const sequence = buildFbsPrintPreviewSequence(
      [{ asset: asset('ready', 12, 900002), objectUrl: 'blob:ready' }],
      [{ order_id: 'missing', wb_order_id: 900001, order_number: 11 }],
    )

    expect(sequence[1]).toMatchObject({
      kind: 'ready',
      preview: { asset: { order_number: 12 } },
    })
  })

  it('TC-S03-006 печатает сохранённый макет Честного знака, не текст КИЗ', () => {
    const source = getFbsMarkingPrintSource({
      id: 'code-artifact-1',
      cis_code: '010460123456789021FULL-SECRET-CODE',
      has_label_artifact: true,
    })

    expect(source).toEqual({ kind: 'artifact', codeId: 'code-artifact-1' })
    expect(source).not.toHaveProperty('cis')
  })

  it('TC-S03-006 строит физическую пару WB → WMS и только затем этикетку маркировки', () => {
    const html = buildFbsTapePairHtml(
      asset('order-sticker-7', 7, 12345),
      'blob:wb-sticker',
      ['data:image/png;base64,marking-artifact'],
    )

    expect(html.indexOf('blob:wb-sticker')).toBeLessThan(html.indexOf('Служебная этикетка WMS'))
    expect(html.indexOf('Служебная этикетка WMS')).toBeLessThan(html.indexOf('marking-artifact'))
    expect(html).toContain('<strong>№ 7</strong>')
  })
})
