import { describe, expect, it } from 'vitest'
import type { WbProductCatalogRow } from '../../types/wbProductCatalog'
import { isInboundMarkingScan } from './inboundMarkingCodes'
import {
  buildInboundDocumentScanIndex,
  inboundCatalogScanIndex,
  resolveInboundProductScan,
} from './inboundScanLookup'

// Фикстуры — раздел 9 docs/requirements/WMS-536.md.
const WB_P = '4601234567893'
const WB_A = '4601234567886'
const OZN = 'OZN-987654'
const CYR = 'ФА_МОД8-4а/083/42'
const CYR_LAYOUT = 'AF_VJL8-4f/083/42'
const DUP = 'DUP-536'
const GS = '\x1d'
const KIZ_GS = `010460123456789321SERIAL536${GS}91ABCD${GS}92SIGNATURE536`
const KIZ_NO_GS = '010460123456789321SERIAL53691ABCD92SIGNATURE536'

function row(id: string, fields: Partial<WbProductCatalogRow> = {}): WbProductCatalogRow {
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

const P = row('P', {
  sku_code: 'AbC-42',
  wb_primary_barcode: WB_P,
  wb_barcodes: [WB_P, WB_A],
  marketplace_bindings: [
    { marketplace: 'ozon', external_sku: '987654', external_offer_id: 'offer-536', external_barcodes: [OZN] },
  ],
})
const Q = row('Q', { marketplace_bindings: [{ marketplace: 'ozon', external_barcodes: [DUP] }] })
const LAT = row('LAT', { sku_code: 'Chin-56005' })
const CYRP = row('CYRP', { sku_code: CYR })
const NUM13 = row('N13', { wb_primary_barcode: '4601234567899' })
const NUM14 = row('N14', { wb_barcodes: ['04601234567899'] })

function catalog(...rows: WbProductCatalogRow[]): Map<string, WbProductCatalogRow> {
  return new Map(rows.map((r) => [r.id, r]))
}

function line(product: WbProductCatalogRow) {
  return { product_id: product.id, sku_code: product.sku_code, wb_barcode: product.wb_primary_barcode }
}

describe('индекс товаров документа приёмки', () => {
  const byId = catalog(P, Q, LAT, CYRP, NUM13, NUM14)
  const documentIndex = buildInboundDocumentScanIndex([line(P), line(LAT)], byId)
  const send = (code: string) => resolveInboundProductScan(documentIndex, null, { code })

  it.each([
    ['основной WB', WB_P],
    ['дополнительный WB размера', WB_A],
    ['Ozon external_barcode', OZN],
    ['SKU в другом регистре', 'aBc-42'],
  ])('%s находит товар документа и отдаёт серверу подсказку', (_label, code) => {
    expect(send(code)).toEqual({ status: 'send', barcode: code, productId: 'P' })
  })

  it('external_sku и external_offer_id не становятся штрихкодом (R4)', () => {
    expect(send('987654')).toEqual({ status: 'send', barcode: '987654' })
    expect(send('offer-536')).toEqual({ status: 'send', barcode: 'offer-536' })
  })

  it('товар каталога вне документа не находится в области документа (R5)', () => {
    expect(send(CYR)).toEqual({ status: 'send', barcode: CYR })
  })

  it('строка документа без карточки каталога ищется по своим sku и wb_barcode', () => {
    const index = buildInboundDocumentScanIndex(
      [{ product_id: 'L', sku_code: 'LINE-SKU', wb_barcode: '2000000000017' }],
      new Map(),
    )
    expect(resolveInboundProductScan(index, null, { code: 'line-sku' })).toMatchObject({ productId: 'L' })
    expect(resolveInboundProductScan(index, null, { code: '2000000000017' })).toMatchObject({ productId: 'L' })
  })

  it('код двух карточек документа ничего не отправляет (R2)', () => {
    const index = buildInboundDocumentScanIndex([line(row('P2', { sku_code: DUP })), line(Q)], catalog(Q))
    expect(resolveInboundProductScan(index, null, { code: DUP })).toEqual({ status: 'ambiguous' })
  })

  it('13 и 14 знаков — разные товары, ведущий ноль не снимается (R-36)', () => {
    const index = buildInboundDocumentScanIndex([line(NUM13), line(NUM14)], byId)
    expect(resolveInboundProductScan(index, null, { code: '4601234567899' })).toMatchObject({ productId: 'N13' })
    expect(resolveInboundProductScan(index, null, { code: '04601234567899' })).toMatchObject({ productId: 'N14' })
  })
})

describe('раскладка и кириллица в скане приёмки (R7)', () => {
  const byId = catalog(P, LAT, CYRP)

  it('сканер в русской раскладке: исправленный код находит товар документа, серверу уходит он же', () => {
    const index = buildInboundDocumentScanIndex([line(LAT)], byId)
    expect(
      resolveInboundProductScan(index, null, { code: 'Chin-56005', wedgeRaw: 'Сршт-56005' }),
    ).toEqual({ status: 'send', barcode: 'Chin-56005', productId: 'LAT' })
  })

  it('ручной ввод в русской раскладке не исправляется: уходит как набран, без подсказки', () => {
    const index = buildInboundDocumentScanIndex([line(LAT)], byId)
    expect(
      resolveInboundProductScan(index, inboundCatalogScanIndex(byId), { code: 'Сршт-56005' }),
    ).toEqual({ status: 'send', barcode: 'Сршт-56005' })
  })

  it('настоящий кириллический артикул документа находится по исходным символам', () => {
    const index = buildInboundDocumentScanIndex([line(CYRP)], byId)
    expect(
      resolveInboundProductScan(index, null, { code: CYR_LAYOUT, wedgeRaw: CYR }),
    ).toEqual({ status: 'send', barcode: CYR, productId: 'CYRP' })
  })

  it('пустой документ ФФ: серверу уходит та строка сканера, которую узнал каталог селлера', () => {
    const empty = buildInboundDocumentScanIndex([], byId)
    const catalogIndex = inboundCatalogScanIndex(byId)
    // Кириллический артикул — исходными символами, а не латиницей по клавишам.
    expect(resolveInboundProductScan(empty, catalogIndex, { code: CYR_LAYOUT, wedgeRaw: CYR })).toEqual({
      status: 'send',
      barcode: CYR,
    })
    // Латинский артикул в русской раскладке — исправленным, как и до WMS-536.
    expect(
      resolveInboundProductScan(empty, catalogIndex, { code: 'Chin-56005', wedgeRaw: 'Сршт-56005' }),
    ).toEqual({ status: 'send', barcode: 'Chin-56005' })
    // Ни одна строка не узнана — уходит код сканера, как и раньше.
    expect(
      resolveInboundProductScan(empty, catalogIndex, { code: 'Hjpf-1', wedgeRaw: 'Рщзф-1' }),
    ).toEqual({ status: 'send', barcode: 'Hjpf-1' })
  })

  it('индекс каталога строится один раз на загруженный каталог', () => {
    expect(inboundCatalogScanIndex(byId)).toBe(inboundCatalogScanIndex(byId))
    expect(inboundCatalogScanIndex(new Map(byId))).not.toBe(inboundCatalogScanIndex(byId))
  })
})

describe('исходная строка во всей области раньше раскладки (R5, R7)', () => {
  // Воспроизведение из ревью: настоящий кириллический артикул P есть только в
  // каталоге селлера, а латинский артикул Q, совпадающий с его раскладкой, — в документе.
  const REAL = row('REAL', { sku_code: CYR })
  const LAYOUT = row('LAYOUT', { sku_code: CYR_LAYOUT })
  const scan = { code: CYR_LAYOUT, wedgeRaw: CYR }

  it('кириллический товар каталога вне документа не проигрывает латинскому товару документа', () => {
    const byId = catalog(REAL, LAYOUT)
    const documentIndex = buildInboundDocumentScanIndex([line(LAYOUT)], byId)
    expect(resolveInboundProductScan(documentIndex, inboundCatalogScanIndex(byId), scan)).toEqual({
      status: 'send',
      barcode: CYR,
    })
  })

  it('исходная строка неоднозначна в каталоге — раскладка не проверяется, серверу уходит исходная', () => {
    const TWIN = row('TWIN', { wb_barcodes: [CYR] })
    const byId = catalog(REAL, TWIN, LAYOUT)
    const documentIndex = buildInboundDocumentScanIndex([line(LAYOUT)], byId)
    expect(resolveInboundProductScan(documentIndex, inboundCatalogScanIndex(byId), scan)).toEqual({
      status: 'send',
      barcode: CYR,
    })
  })

  it('исходная строка не нашлась нигде — раскладка находит товар документа с подсказкой', () => {
    const byId = catalog(LAYOUT)
    const documentIndex = buildInboundDocumentScanIndex([line(LAYOUT)], byId)
    expect(resolveInboundProductScan(documentIndex, inboundCatalogScanIndex(byId), scan)).toEqual({
      status: 'send',
      barcode: CYR_LAYOUT,
      productId: 'LAYOUT',
    })
  })

  it('возвратная приёмка ищет только в документе: каталог селлера не участвует', () => {
    const byId = catalog(REAL, LAYOUT)
    const documentIndex = buildInboundDocumentScanIndex([line(LAYOUT)], byId)
    expect(resolveInboundProductScan(documentIndex, null, scan)).toEqual({
      status: 'send',
      barcode: CYR_LAYOUT,
      productId: 'LAYOUT',
    })
    expect(resolveInboundProductScan(buildInboundDocumentScanIndex([line(REAL)], byId), null, scan)).toEqual({
      status: 'send',
      barcode: CYR,
      productId: 'REAL',
    })
  })

  it('исходная строка неоднозначна в документе — раскладка не спасает, ничего не отправляется', () => {
    const TWIN = row('TWIN', { wb_barcodes: [CYR] })
    const byId = catalog(REAL, TWIN, LAYOUT)
    const documentIndex = buildInboundDocumentScanIndex([line(REAL), line(TWIN), line(LAYOUT)], byId)
    expect(resolveInboundProductScan(documentIndex, inboundCatalogScanIndex(byId), scan)).toEqual({
      status: 'ambiguous',
    })
  })
})

describe('КИЗ в приёмке не доходит до товарного поиска (R8, R9)', () => {
  it('классификатор ЧЗ забирает КИЗ с GS и без GS раньше товара', () => {
    expect(isInboundMarkingScan(KIZ_GS)).toBe(true)
    expect(isInboundMarkingScan(KIZ_NO_GS)).toBe(true)
  })

  it('даже дойдя до товарного поиска, КИЗ не совпадает с товаром и уходит без изменений', () => {
    const trap = row('T', { sku_code: KIZ_NO_GS })
    const index = buildInboundDocumentScanIndex([line(trap)], catalog(trap))
    expect(resolveInboundProductScan(index, null, { code: KIZ_GS })).toEqual({ status: 'send', barcode: KIZ_GS })
  })
})
