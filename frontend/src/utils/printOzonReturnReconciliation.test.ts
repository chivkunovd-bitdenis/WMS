import { describe, expect, it } from 'vitest'
import { buildOzonReturnReconciliationHtml } from './printOzonReturnReconciliation'

describe('buildOzonReturnReconciliationHtml', () => {
  it('keeps route order and separates each pickup point with only its items', () => {
    const html = buildOzonReturnReconciliationHtml({
      documentNumber: 'RET-10',
      sellerName: 'Селлер',
      groups: [
        {
          giveout_id: 1,
          giveout_status: 'Одобрена',
          warehouse_name: 'Первая точка',
          warehouse_address: 'Адрес 1',
          items: [
            {
              offer_id: 'A-1',
              ozon_sku: 11,
              product_name: 'Товар 1',
              return_reason_name: 'Причина 1',
              quantity: 2,
              return_barcode: 'BAR-1',
            },
          ],
        },
        {
          giveout_id: 2,
          giveout_status: 'Создана',
          warehouse_name: 'Вторая точка',
          warehouse_address: 'Адрес 2',
          items: [
            {
              offer_id: 'A-2',
              ozon_sku: 22,
              product_name: 'Товар 2',
              return_reason_name: null,
              quantity: 1,
              return_barcode: 'BAR-2',
            },
          ],
        },
      ],
    })
    expect(html.indexOf('Первая точка')).toBeLessThan(html.indexOf('Вторая точка'))
    expect(html).toContain('data-testid="ozon-return-reconciliation-group"')
    expect(html).toContain('BAR-1')
    expect(html).toContain('BAR-2')
  })

  it('escapes document, point and product text', () => {
    const html = buildOzonReturnReconciliationHtml({
      documentNumber: '<doc>',
      sellerName: 'A & B',
      groups: [
        {
          giveout_id: 1,
          giveout_status: '<status>',
          warehouse_name: '<point>',
          warehouse_address: '"address"',
          items: [
            {
              offer_id: null,
              ozon_sku: null,
              product_name: '<script>x</script>',
              return_reason_name: null,
              quantity: 1,
              return_barcode: null,
            },
          ],
        },
      ],
    })
    expect(html).toContain('&lt;doc&gt;')
    expect(html).toContain('A &amp; B')
    expect(html).toContain('&lt;script&gt;x&lt;/script&gt;')
    expect(html).not.toContain('<script>x</script>')
  })
})
