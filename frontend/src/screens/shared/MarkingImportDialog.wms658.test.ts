import { describe, expect, it } from 'vitest'

import {
  filterProductsBySearch,
  selectImportCatalogProducts,
  type ImportCatalogRow,
} from './MarkingImportDialog'

function row(
  id: string,
  sellerId: string | null,
  required: boolean,
  suffix = '',
): ImportCatalogRow {
  return {
    id,
    name: `Очень длинное название товара ${suffix}`,
    sku_code: `WMS658-${id}-${suffix}`,
    seller_id: sellerId,
    seller_name: sellerId,
    requires_honest_sign: required,
    wb_nm_id: Number(id.replace(/\D/g, '')) || null,
    wb_vendor_code: `VENDOR-${id}-${suffix}`,
    wb_subject_name: 'Предмет',
    wb_primary_image_url: null,
    wb_barcodes: [`BAR-${id}-${suffix}`],
    wb_primary_barcode: `BAR-${id}-${suffix}`,
    wb_size: `SIZE-${suffix}`,
  }
}

describe('WMS-658 C4: оба выбора товара используют прежнюю область без фильтра ЧЗ', () => {
  it('C4: показывает true, false и общую строку, но не товары чужого селлера', () => {
    const catalog = [
      row('1', 'seller-a', true),
      row('2', 'seller-a', false),
      row('3', null, false),
      row('4', 'seller-b', true),
    ]

    const preliminary = selectImportCatalogProducts(catalog, 'seller-a')
    const assignment = selectImportCatalogProducts(catalog, 'seller-a')

    expect(preliminary.map((item) => item.id)).toEqual(['1', '2', '3'])
    expect(assignment).toEqual(preliminary)
    expect(preliminary.map((item) => item.requires_honest_sign)).toEqual([true, false, false])
  })

  it('не теряет длинные данные и ищет допустимый товар по артикулу и штрихкоду', () => {
    const suffix = 'ДЛИННЫЕ-ДАННЫЕ-'.repeat(12)
    const selected = selectImportCatalogProducts(
      [row('1', 'seller-a', false, suffix), row('2', 'seller-b', false, suffix)],
      'seller-a',
    )

    expect(filterProductsBySearch(selected, `WMS658-1-${suffix}`)).toEqual(selected)
    expect(filterProductsBySearch(selected, `BAR-1-${suffix}`)).toEqual(selected)
    expect(selected[0]?.name).toContain(suffix)
    expect(selected[0]?.wb_size).toBe(`SIZE-${suffix}`)
  })
})
