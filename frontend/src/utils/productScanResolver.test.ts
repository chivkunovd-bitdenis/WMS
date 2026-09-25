import { describe, expect, it, vi } from 'vitest'
import { createScannerListener } from '../hooks/useBarcodeScanner'
import type { MarketplaceProductCatalogRow } from '../types/wbProductCatalog'
import {
  buildProductScanIndex,
  catalogProductScanIndex,
  productScanSourceFromCatalogRow,
  resolveProductScan,
  trimProductScanCode,
  type ProductScanSource,
} from './productScanResolver'

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

function catalogRow(
  id: string,
  fields: Partial<MarketplaceProductCatalogRow> = {},
): MarketplaceProductCatalogRow {
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

/** Товар P: основной и дополнительный WB-код одного размера и Ozon-код. */
const P = catalogRow('P', {
  sku_code: 'AbC-42',
  wb_primary_barcode: WB_P,
  wb_barcodes: [WB_P, WB_A],
  marketplace_bindings: [
    {
      marketplace: 'ozon',
      external_sku: '987654',
      external_offer_id: 'offer-536',
      external_barcodes: [OZN],
    },
  ],
})

describe('resolveProductScan — источники кода (R3)', () => {
  const index = catalogProductScanIndex([P, catalogRow('Q')])

  it.each([
    ['основной WB', WB_P],
    ['дополнительный WB размера', WB_A],
    ['Ozon external_barcode', OZN],
    ['sku_code', 'AbC-42'],
  ])('%s находит P', (_label, code) => {
    expect(resolveProductScan(index, code)).toEqual({
      status: 'found',
      productId: 'P',
      code,
      matchedCode: code,
      viaLayout: false,
    })
  })

  it('external_sku и external_offer_id не являются штрихкодом (R4)', () => {
    expect(resolveProductScan(index, '987654')).toEqual({ status: 'not_found', code: '987654' })
    expect(resolveProductScan(index, 'offer-536')).toEqual({ status: 'not_found', code: 'offer-536' })
  })

  it('коды не-Ozon привязки не индексируются', () => {
    const wbBinding = catalogRow('W', {
      marketplace_bindings: [{ marketplace: 'wb', external_barcodes: ['WB-LINK-1'] }],
    })
    expect(resolveProductScan(catalogProductScanIndex([wbBinding]), 'WB-LINK-1').status).toBe(
      'not_found',
    )
  })

  it('перенос R-06: SKU, основной и дополнительный WB с обрезкой краёв и без регистра', () => {
    const row = catalogRow('p1', {
      sku_code: 'sku-1',
      wb_barcodes: ['460000000001', 'ALT-code'],
      wb_primary_barcode: '460000000001',
    })
    const lookup = catalogProductScanIndex([row])
    const id = (code: string) => {
      const result = resolveProductScan(lookup, code)
      return result.status === 'found' ? result.productId : result.status
    }
    expect(id('sku-1')).toBe('p1')
    expect(id('SKU-1')).toBe('p1')
    expect(id('460000000001')).toBe('p1')
    expect(id(' alt-CODE\n')).toBe('p1')
    expect(id('missing')).toBe('not_found')
  })

  it('строка документа и строка каталога одной карточки сливаются без неоднозначности', () => {
    const sources: ProductScanSource[] = [
      { productId: 'P', skuCode: 'AbC-42', wbPrimaryBarcode: WB_P },
      productScanSourceFromCatalogRow(P),
      productScanSourceFromCatalogRow(P),
    ]
    const result = resolveProductScan(buildProductScanIndex(sources), WB_P)
    expect(result).toMatchObject({ status: 'found', productId: 'P' })
  })

  it('пустые коды и пустой ввод не находят ничего', () => {
    const index2 = buildProductScanIndex([
      { productId: 'P', skuCode: '', wbPrimaryBarcode: '  ', wbBarcodes: [null, undefined, ''] },
    ])
    expect(index2.productIdsByCode.size).toBe(0)
    expect(resolveProductScan(index2, '')).toEqual({ status: 'not_found', code: '' })
    expect(resolveProductScan(index, ' \t\r\n')).toEqual({ status: 'not_found', code: '' })
  })

  it('товар вне переданного набора не находится (область задаёт экран, R5)', () => {
    expect(resolveProductScan(catalogProductScanIndex([catalogRow('Q')]), WB_P).status).toBe(
      'not_found',
    )
  })
})

describe('resolveProductScan — неоднозначность (R2)', () => {
  it('SKU товара P и Ozon-код товара Q дают ambiguous, а не первый или последний', () => {
    const q = catalogRow('Q', {
      marketplace_bindings: [{ marketplace: 'ozon', external_barcodes: [DUP] }],
    })
    const p = catalogRow('P', { sku_code: DUP })
    for (const rows of [
      [p, q],
      [q, p],
    ]) {
      const result = resolveProductScan(catalogProductScanIndex(rows), DUP)
      expect(result.status).toBe('ambiguous')
      expect(result.status === 'ambiguous' && [...result.productIds].sort()).toEqual(['P', 'Q'])
    }
  })

  it('после удаления конфликтного кода у Q тот же код находит P', () => {
    const p = catalogRow('P', { sku_code: DUP })
    const q = catalogRow('Q', { marketplace_bindings: [{ marketplace: 'ozon', external_barcodes: [] }] })
    expect(resolveProductScan(catalogProductScanIndex([p, q]), DUP)).toMatchObject({
      status: 'found',
      productId: 'P',
    })
  })

  it('регистр может свести два товара в один ключ — тогда это ambiguous', () => {
    const index = buildProductScanIndex([
      { productId: 'P', skuCode: 'AbC-42' },
      { productId: 'Q', skuCode: 'abc-42' },
    ])
    expect(resolveProductScan(index, 'ABC-42').status).toBe('ambiguous')
  })

  it('повтор кода у одной карточки в основном и дополнительном поле — не неоднозначность', () => {
    const index = buildProductScanIndex([
      { productId: 'P', skuCode: WB_P, wbPrimaryBarcode: WB_P, wbBarcodes: [WB_P, WB_P], externalBarcodes: [WB_P] },
    ])
    expect(resolveProductScan(index, WB_P)).toMatchObject({ status: 'found', productId: 'P' })
  })
})

describe('resolveProductScan — нормализация (R6)', () => {
  const index = catalogProductScanIndex([P])

  it('снимает с краёв только пробел, TAB, CR и LF', () => {
    expect(resolveProductScan(index, `\t ${WB_P}\r\n`)).toMatchObject({
      status: 'found',
      productId: 'P',
      code: WB_P,
    })
    expect(trimProductScanCode('\u00a0X\u000b')).toBe('\u00a0X\u000b')
    expect(resolveProductScan(index, `\u00a0${WB_P}`).status).toBe('not_found')
  })

  it('внутренние символы и AIM-префикс не снимаются', () => {
    expect(resolveProductScan(index, '460123\t4567893').status).toBe('not_found')
    expect(resolveProductScan(index, `]C1${WB_P}`).status).toBe('not_found')
    expect(resolveProductScan(index, `460123${GS}4567893`).status).toBe('not_found')
  })

  it('регистр не учитывается для латиницы и кириллицы', () => {
    expect(resolveProductScan(index, 'aBc-42')).toMatchObject({ status: 'found', productId: 'P' })
    const cyr = catalogProductScanIndex([catalogRow('C', { sku_code: CYR })])
    expect(resolveProductScan(cyr, CYR)).toMatchObject({ status: 'found', productId: 'C' })
    expect(resolveProductScan(cyr, CYR.toLowerCase())).toMatchObject({ status: 'found', productId: 'C' })
    expect(resolveProductScan(cyr, CYR.toUpperCase())).toMatchObject({ status: 'found', productId: 'C' })
  })

  it('13 и 14 знаков — разные коды, ведущий ноль не снимается и не добавляется (R-36)', () => {
    const p = catalogRow('P', { wb_primary_barcode: '4601234567893' })
    const q = catalogRow('Q', { wb_barcodes: ['04601234567893'] })
    const both = catalogProductScanIndex([p, q])
    expect(resolveProductScan(both, '4601234567893')).toMatchObject({ status: 'found', productId: 'P' })
    expect(resolveProductScan(both, '04601234567893')).toMatchObject({ status: 'found', productId: 'Q' })
    const onlyP = catalogProductScanIndex([p])
    expect(resolveProductScan(onlyP, '04601234567893').status).toBe('not_found')
    const onlyQ = catalogProductScanIndex([q])
    expect(resolveProductScan(onlyQ, '4601234567893').status).toBe('not_found')
  })

  it('КИЗ с GS не превращается в код без GS', () => {
    const trap = catalogProductScanIndex([catalogRow('T', { sku_code: KIZ_NO_GS })])
    expect(resolveProductScan(trap, KIZ_GS)).toEqual({ status: 'not_found', code: KIZ_GS })
    expect(resolveProductScan(index, KIZ_GS).status).toBe('not_found')
    expect(resolveProductScan(index, KIZ_NO_GS).status).toBe('not_found')
  })
})

describe('resolveProductScan — раскладка только после промаха исходной строки (R7)', () => {
  it('RU-layout: без кандидата not_found, с кандидатом — found, в code остаётся исходный ввод', () => {
    const index = catalogProductScanIndex([catalogRow('P', { sku_code: 'Chin-56005' })])
    expect(resolveProductScan(index, 'Сршт-56005')).toEqual({ status: 'not_found', code: 'Сршт-56005' })
    expect(resolveProductScan(index, 'Сршт-56005', { layoutCandidate: 'Chin-56005' })).toEqual({
      status: 'found',
      productId: 'P',
      code: 'Сршт-56005',
      matchedCode: 'Chin-56005',
      viaLayout: true,
    })
  })

  it('кириллический SKU находится по исходной строке, латинизированный alias другого товара не проверяется', () => {
    const p = catalogRow('P', { sku_code: CYR })
    const q = catalogRow('Q', { sku_code: CYR_LAYOUT })
    expect(
      resolveProductScan(catalogProductScanIndex([p, q]), CYR, { layoutCandidate: CYR_LAYOUT }),
    ).toEqual({ status: 'found', productId: 'P', code: CYR, matchedCode: CYR, viaLayout: false })

    // Исходного alias больше нет: только теперь срабатывает layout-кандидат.
    expect(
      resolveProductScan(catalogProductScanIndex([q]), CYR, { layoutCandidate: CYR_LAYOUT }),
    ).toMatchObject({ status: 'found', productId: 'Q', viaLayout: true })
    // Без явного кандидата раскладка не исправляется.
    expect(resolveProductScan(catalogProductScanIndex([q]), CYR).status).toBe('not_found')
  })

  it('ambiguous по исходной строке не уходит в layout-кандидат', () => {
    const index = buildProductScanIndex([
      { productId: 'P', skuCode: DUP },
      { productId: 'Q', externalBarcodes: [DUP] },
      { productId: 'R', skuCode: 'LAYOUT-HIT' },
    ])
    expect(resolveProductScan(index, DUP, { layoutCandidate: 'LAYOUT-HIT' })).toMatchObject({
      status: 'ambiguous',
      viaLayout: false,
    })
  })

  it('неоднозначный layout-кандидат тоже ambiguous', () => {
    const index = buildProductScanIndex([
      { productId: 'P', skuCode: 'Chin-56005' },
      { productId: 'Q', wbBarcodes: ['chin-56005'] },
    ])
    expect(
      resolveProductScan(index, 'Сршт-56005', { layoutCandidate: 'Chin-56005' }),
    ).toMatchObject({ status: 'ambiguous', code: 'Сршт-56005', matchedCode: 'Chin-56005', viaLayout: true })
  })

  it('сквозной путь: клавиатурный сканер → поиск товара', () => {
    const index = catalogProductScanIndex([
      catalogRow('CYR', { sku_code: CYR }),
      catalogRow('LAT', { sku_code: 'Chin-56005' }),
    ])
    const results: unknown[] = []
    let now = 0
    const listener = createScannerListener({
      onScanWithRaw: (code, scan) => {
        results.push(resolveProductScan(index, scan.raw, { layoutCandidate: code }))
      },
      minLength: 5,
      maxIntervalMs: 50,
      getNow: () => now,
      getActiveElement: () => null,
    })
    const press = (key: string, code: string, shiftKey = false) => {
      listener({
        key,
        code,
        shiftKey,
        ctrlKey: false,
        metaKey: false,
        altKey: false,
        preventDefault: vi.fn(),
        stopPropagation: vi.fn(),
      })
      now += 10
    }
    const digits = (value: string) => {
      for (const ch of value) press(ch, `Digit${ch}`)
    }

    // Латинский SKU при русской раскладке.
    press('С', 'KeyC', true)
    press('р', 'KeyH')
    press('ш', 'KeyI')
    press('т', 'KeyN')
    press('-', 'Minus')
    digits('56005')
    press('Enter', 'Enter')
    // Настоящий кириллический SKU.
    press('Ф', 'KeyA', true)
    press('А', 'KeyF', true)
    press('_', 'Minus', true)
    press('М', 'KeyV', true)
    press('О', 'KeyJ', true)
    press('Д', 'KeyL', true)
    digits('8')
    press('-', 'Minus')
    digits('4')
    press('а', 'KeyF')
    press('/', 'Slash')
    digits('083')
    press('/', 'Slash')
    digits('42')
    press('Enter', 'Enter')

    expect(results).toEqual([
      { status: 'found', productId: 'LAT', code: 'Сршт-56005', matchedCode: 'Chin-56005', viaLayout: true },
      { status: 'found', productId: 'CYR', code: CYR, matchedCode: CYR, viaLayout: false },
    ])
  })
})

describe('индекс строится один раз на набор товаров (R13)', () => {
  it('тот же массив каталога — тот же индекс; новый массив — новый индекс', () => {
    const rows = [P]
    const first = catalogProductScanIndex(rows)
    expect(catalogProductScanIndex(rows)).toBe(first)
    expect(catalogProductScanIndex([...rows])).not.toBe(first)
  })

  it('10 000 карточек с тремя WB и тремя Ozon кодами: сканы — поиск по готовому индексу', () => {
    const rows: MarketplaceProductCatalogRow[] = []
    for (let i = 0; i < 10_000; i += 1) {
      const n = String(i).padStart(5, '0')
      rows.push(
        catalogRow(`id-${n}`, {
          sku_code: `SKU-${n}`,
          wb_primary_barcode: `46000000${n}`,
          wb_barcodes: [`46000000${n}`, `46100000${n}`, `46200000${n}`],
          marketplace_bindings: [
            { marketplace: 'ozon', external_barcodes: [`OZN-${n}-1`, `OZN-${n}-2`, `OZN-${n}-3`] },
          ],
        }),
      )
    }
    rows.push(catalogRow('dup', { sku_code: 'OZN-09999-3' }))

    const index = catalogProductScanIndex(rows)
    expect(index.productIdsByCode.size).toBe(10_000 * 7)

    // 100 последовательных сканов берут тот же индекс, а не перестраивают его.
    for (let i = 0; i < 100; i += 1) {
      expect(catalogProductScanIndex(rows)).toBe(index)
    }

    expect(resolveProductScan(index, '4600000000000')).toMatchObject({ status: 'found', productId: 'id-00000' })
    expect(resolveProductScan(index, 'ozn-09999-2')).toMatchObject({ status: 'found', productId: 'id-09999' })
    expect(resolveProductScan(index, 'OZN-09999-3').status).toBe('ambiguous')
  })
})
