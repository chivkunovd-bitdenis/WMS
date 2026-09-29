import { renderToStaticMarkup } from 'react-dom/server'
import { describe, expect, it } from 'vitest'
import { ProductCardMainTab } from './ProductCardMainTab'
import type { ProductCardData } from './productCardTypes'

// WMS-490 R4–R7: разметка основной вкладки карточки товара для разных
// сочетаний площадок. Клик по строке, шапка и вкладки — в
// FfProductsCatalogScreen.rowClick.test.tsx и ProductCardDialog проверяется
// глазами в браузере (см. отчёт куска D3).

function baseData(overrides: Partial<ProductCardData> = {}): ProductCardData {
  return {
    id: 'p-1',
    seller_id: 's-1',
    seller_name: 'Селлер Один',
    name: 'Рюкзак городской, чёрный',
    sku_code: 'BAG-CITY-BLK',
    wb_nm_id: 12345,
    wb_vendor_code: 'BAG-1',
    ozon_sku: null,
    ozon_offer_id: null,
    wb_subject_name: 'Рюкзаки',
    wb_primary_image_url: null,
    marketplace_bindings: [],
    wb_barcodes: ['1234567890123'],
    wb_primary_barcode: '1234567890123',
    wb_size: 'M',
    wb_color: 'Чёрный',
    wb_brand: 'Бренд',
    wb_composition: '100% полиэстер',
    packaging_instructions: 'Упаковать в пакет',
    country_of_origin_iso_code: 'CN',
    requires_honest_sign: true,
    marketplaces: ['wb'],
    length_mm: 400,
    width_mm: 300,
    height_mm: 150,
    weight_g: 600,
    location_warehouses: [],
    ...overrides,
  }
}

function render(data: ProductCardData): string {
  return renderToStaticMarkup(<ProductCardMainTab data={data} />)
}

function tag(markup: string, testId: string): string {
  const match = markup.match(new RegExp(`<[^>]*data-testid="${testId}"[^>]*>([^<]*)</`))
  if (!match) throw new Error(`no element ${testId} in:\n${markup}`)
  return match[1]
}

function has(markup: string, testId: string): boolean {
  return markup.includes(`data-testid="${testId}"`)
}

describe('WMS-490 R4: основные поля', () => {
  it('показывает селлера, название, параметры и Честный знак «нужен»', () => {
    const markup = render(baseData())
    expect(tag(markup, 'product-card-field-seller')).toBe('Селлер Один')
    expect(tag(markup, 'product-card-field-name')).toBe('Рюкзак городской, чёрный')
    expect(tag(markup, 'product-card-field-sku')).toBe('BAG-CITY-BLK')
    expect(tag(markup, 'product-card-field-size')).toBe('M')
    expect(tag(markup, 'product-card-field-color')).toBe('Чёрный')
    expect(tag(markup, 'product-card-field-brand')).toBe('Бренд')
    expect(tag(markup, 'product-card-field-composition')).toBe('100% полиэстер')
    expect(tag(markup, 'product-card-field-category')).toBe('Рюкзаки')
    expect(tag(markup, 'product-card-field-country')).toBe('CN')
    expect(tag(markup, 'product-card-field-dimensions')).toBe('400 × 300 × 150 мм')
    expect(tag(markup, 'product-card-field-weight')).toBe('600 г')
    expect(tag(markup, 'product-card-field-honest-sign')).toBe('нужен')
    expect(tag(markup, 'product-card-field-packaging')).toBe('Упаковать в пакет')
  })

  it('пустые поля показывают тире, а Честный знак — «не нужен»', () => {
    const markup = render(
      baseData({
        seller_name: null,
        wb_size: null,
        wb_color: null,
        wb_brand: null,
        wb_composition: null,
        wb_subject_name: null,
        country_of_origin_iso_code: null,
        length_mm: null,
        width_mm: null,
        height_mm: null,
        weight_g: null,
        packaging_instructions: null,
        requires_honest_sign: false,
      }),
    )
    expect(tag(markup, 'product-card-field-seller')).toBe('—')
    expect(tag(markup, 'product-card-field-size')).toBe('—')
    expect(tag(markup, 'product-card-field-color')).toBe('—')
    expect(tag(markup, 'product-card-field-brand')).toBe('—')
    expect(tag(markup, 'product-card-field-composition')).toBe('—')
    expect(tag(markup, 'product-card-field-category')).toBe('—')
    expect(tag(markup, 'product-card-field-country')).toBe('—')
    expect(tag(markup, 'product-card-field-dimensions')).toBe('—')
    expect(tag(markup, 'product-card-field-weight')).toBe('—')
    expect(tag(markup, 'product-card-field-honest-sign')).toBe('не нужен')
    expect(tag(markup, 'product-card-field-packaging')).toBe('—')
  })
})

describe('WMS-490 R5–R7: разделы площадок', () => {
  it('товар только WB — есть раздел Wildberries, нет Ozon и общей строки ШК', () => {
    const markup = render(baseData({ marketplaces: ['wb'] }))
    expect(has(markup, 'product-card-wb-section')).toBe(true)
    expect(has(markup, 'product-card-ozon-section')).toBe(false)
    expect(has(markup, 'product-card-barcodes-generic')).toBe(false)
    expect(tag(markup, 'product-card-wb-vendor-code')).toBe('BAG-1')
    expect(tag(markup, 'product-card-wb-nm-id')).toBe('12345')
    expect(tag(markup, 'product-card-wb-barcodes')).toBe('1234567890123')
  })

  it('товар только Ozon — есть раздел Ozon, нет Wildberries', () => {
    const markup = render(
      baseData({
        marketplaces: ['ozon'],
        wb_vendor_code: null,
        wb_nm_id: null,
        ozon_sku: 'SKU-1',
        ozon_offer_id: 'OFFER-1',
        marketplace_bindings: [
          {
            marketplace: 'ozon',
            external_product_id: 'PID-1',
            external_offer_id: 'OFFER-1',
            external_sku: 'SKU-1',
            external_barcodes: ['9990001112223'],
          },
        ],
      }),
    )
    expect(has(markup, 'product-card-wb-section')).toBe(false)
    expect(has(markup, 'product-card-ozon-section')).toBe(true)
    expect(tag(markup, 'product-card-ozon-offer')).toBe('OFFER-1')
    expect(tag(markup, 'product-card-ozon-sku')).toBe('SKU-1')
    expect(tag(markup, 'product-card-ozon-product-id')).toBe('PID-1')
    expect(tag(markup, 'product-card-ozon-barcodes')).toBe('9990001112223')
  })

  it('товар WB + Ozon — оба раздела, каждый со своими данными', () => {
    const markup = render(
      baseData({
        marketplaces: ['wb', 'ozon'],
        marketplace_bindings: [
          {
            marketplace: 'ozon',
            external_product_id: 'PID-2',
            external_offer_id: 'OFFER-2',
            external_sku: 'SKU-2',
            external_barcodes: ['1112223334445', '5556667778889'],
          },
        ],
      }),
    )
    expect(has(markup, 'product-card-wb-section')).toBe(true)
    expect(has(markup, 'product-card-ozon-section')).toBe(true)
    expect(tag(markup, 'product-card-ozon-barcodes')).toBe('1112223334445, 5556667778889')
  })

  it('ручной товар без площадки — общая строка ШК, разделов площадок нет', () => {
    const markup = render(
      baseData({
        marketplaces: [],
        wb_vendor_code: null,
        wb_nm_id: null,
        wb_barcodes: ['0001112223334'],
      }),
    )
    expect(has(markup, 'product-card-wb-section')).toBe(false)
    expect(has(markup, 'product-card-ozon-section')).toBe(false)
    expect(has(markup, 'product-card-barcodes-generic')).toBe(true)
    expect(tag(markup, 'product-card-barcodes-generic')).toBe('0001112223334')
  })

  it('12 ШК WB показаны все целиком, ни один не обрезан', () => {
    const many = Array.from({ length: 12 }, (_, i) => `770000000000${i}`)
    const markup = render(baseData({ marketplaces: ['wb'], wb_barcodes: many }))
    const value = tag(markup, 'product-card-wb-barcodes')
    for (const code of many) {
      expect(value).toContain(code)
    }
  })
})
