import { describe, expect, it } from 'vitest'
import type { MarketplaceProductCatalogRow } from '../../../types/wbProductCatalog'
import { resolveProductScan } from '../../../utils/productScanResolver'
import {
  PickScanSourceError,
  pickProductScanIndex,
  resolveProductScanSource,
  scanSourceKey,
} from './pickScanSource'

const product = { id: 'can-product', sku: 'EMU-CAN-PVZ-TRUE' }
const location = {
  storage_location_id: 'FBS-VIDEO-01',
  available: 59,
  sources: [
    { available: 19, container_path: [{ kind: 'pallet' as const, id: 'pallet' }, { kind: 'cargo_place' as const, id: 'cargo' }] },
    { available: 40, container_path: [{ kind: 'pallet' as const, id: 'pallet' }, { kind: 'box' as const, id: 'box' }] },
  ],
}

describe('WMS-058 physical source selection for shared FBS and MP scans', () => {
  it('requires the existing choice for cargo and box in one cell instead of posting loose stock', () => {
    try {
      resolveProductScanSource(product, [location], null)
      expect.fail('ambiguous physical stock must not turn into a loose-stock request')
    } catch (error) {
      expect(error).toBeInstanceOf(PickScanSourceError)
      expect(error).toMatchObject({ productId: product.id })
      expect((error as Error).message).toContain('в 2 местах')
      expect((error as Error).message).not.toContain('Недостаточно')
    }
  })

  it('uses the single available leaf container even when another container has no available units', () => {
    const source = resolveProductScanSource(product, [{ ...location, sources: [
      { ...location.sources[0], available: 0 }, location.sources[1],
    ] }], null)
    expect(source).toEqual({ locationId: 'FBS-VIDEO-01', containerKind: 'box', containerId: 'box' })
    expect(scanSourceKey(source)).toBe('obj:box')
  })

  it('preserves explicit container choice without inventing another source', () => {
    const source = resolveProductScanSource(product, [location], { locationId: 'FBS-VIDEO-01', containerKind: 'cargo_place', containerId: 'cargo' })
    expect(source.containerId).toBe('cargo')
    expect(resolveProductScanSource(product, [], { locationId: 'FBS-VIDEO-01', containerKind: 'pallet', containerId: 'pallet' })).toEqual({ locationId: 'FBS-VIDEO-01', containerKind: 'pallet', containerId: 'pallet' })
  })

  it('keeps loose stock as a null-container request and supports the legacy location contract', () => {
    for (const entry of [
      { storage_location_id: 'cell', available: 1, sources: [{ available: 1, container_path: [] }] },
      { storage_location_id: 'cell', available: 1 },
    ]) {
      const source = resolveProductScanSource(product, [entry], null)
      expect(source).toEqual({ locationId: 'cell', containerKind: null, containerId: null })
      expect(scanSourceKey(source)).toBe('cell:cell')
    }
  })

  it('does not use loose stock when the selected container is exhausted', () => {
    const entry = { ...location, sources: [
      { ...location.sources[1], available: 0 }, { available: 12, container_path: [] },
    ] }
    expect(resolveProductScanSource(product, [entry], { locationId: 'FBS-VIDEO-01', containerKind: 'box', containerId: 'box' })).toEqual({ locationId: 'FBS-VIDEO-01', containerKind: 'box', containerId: 'box' })
  })

  it.each([0, 4])('keeps an explicitly scanned cell as loose stock when loose available is %s', (available) => {
    const selected = { locationId: 'FBS-VIDEO-01', containerKind: null, containerId: null }
    const entry = { ...location, sources: [
      { available, container_path: [] }, location.sources[1],
    ] }
    const source = resolveProductScanSource(product, [entry], selected)
    expect(source).toBe(selected)
    expect(source.containerKind).toBeNull()
    expect(source.containerId).toBeNull()
    expect(scanSourceKey(source)).toBe('cell:FBS-VIDEO-01')
  })

  it('counts physical sources across cells and restricts scanned cell scope', () => {
    const entries = [location, { storage_location_id: 'other-cell', available: 1, sources: [{ available: 1, container_path: [] }] }]
    expect(() => resolveProductScanSource(product, entries, null)).toThrow('в 3 местах')
    expect(resolveProductScanSource(product, entries, { locationId: 'other-cell', containerKind: null, containerId: null })).toEqual({ locationId: 'other-cell', containerKind: null, containerId: null })
  })
})

// Фикстуры — раздел 9 docs/requirements/WMS-536.md.
const WB_P = '4601234567893'
const WB_A = '4601234567886'
const OZN = 'OZN-987654'
const CYR = 'ФА_МОД8-4а/083/42'
const GS = '\x1d'
const KIZ_GS = `010460123456789321SERIAL536${GS}91ABCD${GS}92SIGNATURE536`

function catalogRow(id: string, fields: Partial<MarketplaceProductCatalogRow> = {}): MarketplaceProductCatalogRow {
  return {
    id,
    name: `Товар ${id}`,
    sku_code: `SKU-${id}`,
    wb_nm_id: null,
    wb_vendor_code: null,
    wb_subject_name: null,
    wb_primary_image_url: null,
    wb_barcodes: [],
    wb_primary_barcode: null,
    wb_size: null,
    wb_color: null,
    ...fields,
  }
}

/** Карточка P в каталоге селлера: SKU, основной и дополнительный WB-код, Ozon-код. */
const catalogP = catalogRow('P', {
  sku_code: 'AbC-42',
  wb_primary_barcode: WB_P,
  wb_barcodes: [WB_P, WB_A],
  marketplace_bindings: [
    { marketplace: 'ozon', external_sku: '987654', external_offer_id: 'offer-536', external_barcodes: [OZN] },
  ],
})

/** Товары плана так, как их собирает FfUnloadPickPage для WB/отгрузки. */
const planP = { id: 'P', sku: 'AbC-42', barcode: WB_P }
const planQ = { id: 'Q', sku: 'SKU-Q', barcode: '' }

function found(index: ReturnType<typeof pickProductScanIndex>, code: string) {
  const result = resolveProductScan(index, code)
  return result.status === 'found' ? result.productId : result.status
}

describe('WMS-536 · S-OUT-01 единый поиск товара в подборе', () => {
  const catalog = new Map([
    ['P', catalogP],
    ['Q', catalogRow('Q')],
  ])
  const index = pickProductScanIndex([planP, planQ], catalog, [])

  it('находит товар плана по всем кодам карточки одновременно (R3)', () => {
    expect(found(index, WB_P)).toBe('P')
    expect(found(index, WB_A)).toBe('P')
    expect(found(index, OZN)).toBe('P')
    expect(found(index, 'aBc-42')).toBe('P')
    expect(found(index, '  4601234567886\r\n')).toBe('P')
  })

  it('Ozon SKU и offer_id из каталога не становятся кодом товара (R4)', () => {
    expect(found(index, '987654')).toBe('not_found')
    expect(found(index, 'offer-536')).toBe('not_found')
  })

  it('кириллический SKU ищется как есть, раскладку поле подбора не исправляет (R6, R7)', () => {
    const cyrIndex = pickProductScanIndex([{ id: 'P', sku: CYR, barcode: '' }], new Map(), [])
    expect(found(cyrIndex, CYR)).toBe('P')
    const latin = pickProductScanIndex([{ id: 'P', sku: 'Chin-56005', barcode: '' }], new Map(), [])
    expect(found(latin, 'Сршт-56005')).toBe('not_found')
  })

  it('код у двух товаров плана — неоднозначность, а не первый товар (R2)', () => {
    const dup = pickProductScanIndex(
      [planP, planQ],
      new Map([
        ['P', catalogRow('P', { sku_code: 'DUP-536' })],
        ['Q', catalogRow('Q', { marketplace_bindings: [{ marketplace: 'ozon', external_barcodes: ['DUP-536'] }] })],
      ]),
      [],
    )
    const result = resolveProductScan(dup, 'DUP-536')
    expect(result.status).toBe('ambiguous')
    expect(result.status === 'ambiguous' ? [...result.productIds].sort() : []).toEqual(['P', 'Q'])
  })

  it('ищет только в товарах плана: карточка селлера вне плана не находится (R5)', () => {
    const outside = pickProductScanIndex([planQ], catalog, [])
    expect(found(outside, WB_A)).toBe('not_found')
    expect(found(outside, 'SKU-Q')).toBe('Q')
  })

  it('13 и 14 знаков — разные коды, КИЗ с GS товаром не становится (R6, R-36)', () => {
    expect(found(index, `0${WB_P}`)).toBe('not_found')
    expect(found(index, KIZ_GS)).toBe('not_found')
  })

  it('Ozon-поставка без каталога: коды строки плана и scan_codes, если сервер их отдал', () => {
    // В Ozon-подборе сервер кладёт в SKU строки Ozon SKU, в ШК — первый Ozon-код.
    const ozonPlan = [{ id: 'P', sku: '987654', barcode: OZN }]
    const withoutCodes = pickProductScanIndex(ozonPlan, new Map(), [{ product_id: 'P' }])
    expect(found(withoutCodes, '987654')).toBe('P')
    expect(found(withoutCodes, OZN)).toBe('P')
    expect(found(withoutCodes, 'OZN-SECOND')).toBe('not_found')

    const withCodes = pickProductScanIndex(ozonPlan, new Map(), [
      { product_id: 'P', scan_codes: [OZN, 'OZN-SECOND', WB_A] },
      { product_id: 'NOT-IN-PLAN', scan_codes: ['FOREIGN-1'] },
    ])
    expect(found(withCodes, 'OZN-SECOND')).toBe('P')
    expect(found(withCodes, WB_A)).toBe('P')
    expect(found(withCodes, 'FOREIGN-1')).toBe('not_found')
  })
})
