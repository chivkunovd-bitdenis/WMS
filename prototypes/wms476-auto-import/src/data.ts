export type CatalogRow = {
  id: string
  sku: string
  name: string
  size: string | null
  vendorCode: string
  barcode: string
}

export const catalog: CatalogRow[] = [
  {
    id: 'p-1001',
    sku: 'PAL-CHIFFON-OASIS-2026-LTD-EDITION',
    name: 'Палантин шифоновый «Оазис», лимитированная коллекция 2026',
    size: '90×180',
    vendorCode: 'PAL-CHF-OASIS-90180',
    barcode: '4650097654321',
  },
  {
    id: 'p-1002',
    sku: 'PAL-CHIFFON-OASIS-2026-LTD-EDITION',
    name: 'Палантин шифоновый «Оазис», лимитированная коллекция 2026',
    size: '70×140',
    vendorCode: 'PAL-CHF-OASIS-70140',
    barcode: '4650097654338',
  },
  {
    id: 'p-1003',
    sku: 'HDB-CASHMERE-CLASSIC-BURGUNDY-XL',
    name: 'Худи кашемировое «Классик», бордо',
    size: 'XL',
    vendorCode: 'HDB-CSH-CL-BG-XL',
    barcode: '4650098811234',
  },
  {
    id: 'p-1004',
    sku: 'HDB-CASHMERE-CLASSIC-BURGUNDY-L',
    name: 'Худи кашемировое «Классик», бордо',
    size: 'L',
    vendorCode: 'HDB-CSH-CL-BG-L',
    barcode: '4650098811227',
  },
  {
    id: 'p-1005',
    sku: 'HDB-CASHMERE-CLASSIC-BURGUNDY-M',
    name: 'Худи кашемировое «Классик», бордо',
    size: 'M',
    vendorCode: 'HDB-CSH-CL-BG-M',
    barcode: '4650098811210',
  },
  {
    id: 'p-1006',
    sku: 'SCR-SILK-SUNSET-70',
    name: 'Платок шёлковый «Закат»',
    size: '70×70',
    vendorCode: 'SCR-SLK-SUN-70',
    barcode: '4650097112233',
  },
  {
    id: 'p-1007',
    sku: 'SCR-SILK-SUNSET-90',
    name: 'Платок шёлковый «Закат»',
    size: '90×90',
    vendorCode: 'SCR-SLK-SUN-90',
    barcode: '4650097112240',
  },
  {
    id: 'p-1008',
    sku: 'DRS-LINEN-SUMMER-42',
    name: 'Платье льняное «Лето»',
    size: '42',
    vendorCode: 'DRS-LIN-SUM-42',
    barcode: '4650098445511',
  },
  {
    id: 'p-1009',
    sku: 'DRS-LINEN-SUMMER-44',
    name: 'Платье льняное «Лето»',
    size: '44',
    vendorCode: 'DRS-LIN-SUM-44',
    barcode: '4650098445528',
  },
  {
    id: 'p-1010',
    sku: 'ACC-BELT-LEATHER-BROWN-95',
    name: 'Ремень кожаный, коричневый',
    size: '95 см',
    vendorCode: 'ACC-BLT-LTR-BR-95',
    barcode: '4650099001122',
  },
]

export type AutoGroup = {
  key: string
  productId: string
  sku: string
  productName: string
  size: string | null
  barcode: string
  loadedCount: number
}

export const autoSuccessGroupsPartial: AutoGroup[] = [
  {
    key: 'auto-1',
    productId: 'p-1001',
    sku: 'PAL-CHIFFON-OASIS-2026-LTD-EDITION',
    productName: 'Палантин шифоновый «Оазис», лимитированная коллекция 2026',
    size: '90×180',
    barcode: '4650097654321',
    loadedCount: 128,
  },
  {
    key: 'auto-2',
    productId: 'p-1003',
    sku: 'HDB-CASHMERE-CLASSIC-BURGUNDY-XL',
    productName: 'Худи кашемировое «Классик», бордо',
    size: 'XL',
    barcode: '4650098811234',
    loadedCount: 42,
  },
  {
    key: 'auto-3',
    productId: 'p-1006',
    sku: 'SCR-SILK-SUNSET-70',
    productName: 'Платок шёлковый «Закат»',
    size: '70×70',
    barcode: '4650097112233',
    loadedCount: 24,
  },
]

export const autoSuccessGroupsFull: AutoGroup[] = [
  {
    key: 'auto-full-1',
    productId: 'p-1001',
    sku: 'PAL-CHIFFON-OASIS-2026-LTD-EDITION',
    productName: 'Палантин шифоновый «Оазис», лимитированная коллекция 2026',
    size: '90×180',
    barcode: '4650097654321',
    loadedCount: 132,
  },
  {
    key: 'auto-full-2',
    productId: 'p-1002',
    sku: 'PAL-CHIFFON-OASIS-2026-LTD-EDITION',
    productName: 'Палантин шифоновый «Оазис», лимитированная коллекция 2026',
    size: '70×140',
    barcode: '4650097654338',
    loadedCount: 46,
  },
  {
    key: 'auto-full-3',
    productId: 'p-1003',
    sku: 'HDB-CASHMERE-CLASSIC-BURGUNDY-XL',
    productName: 'Худи кашемировое «Классик», бордо',
    size: 'XL',
    barcode: '4650098811234',
    loadedCount: 42,
  },
  {
    key: 'auto-full-4',
    productId: 'p-1006',
    sku: 'SCR-SILK-SUNSET-70',
    productName: 'Платок шёлковый «Закат»',
    size: '70×70',
    barcode: '4650097112233',
    loadedCount: 24,
  },
]

export type FailedRow = {
  key: string
  markingCode: string
  reason: string
  syntheticGtin: string
  syntheticVendorCode: string
  syntheticSize: string
}

export const autoFailedRows: FailedRow[] = [
  {
    key: 'fail-1',
    markingCode: '010461234509876521Ax4CqEz9',
    reason: 'Не найден артикул в каталоге селлера',
    syntheticGtin: '04612345098765',
    syntheticVendorCode: 'PAL-CHF-OASIS-70140',
    syntheticSize: '70×140',
  },
  {
    key: 'fail-2',
    markingCode: '010467659887654123Zp8LqMr1',
    reason: 'Совпадение неоднозначно: артикул есть, но размер не распознан',
    syntheticGtin: '04676598876541',
    syntheticVendorCode: 'HDB-CSH-CL-BG-??',
    syntheticSize: '—',
  },
  {
    key: 'fail-3',
    markingCode: '010467659887661201Bt2VkNw5',
    reason: 'Совпадение неоднозначно: два товара с одинаковым штрихкодом',
    syntheticGtin: '04676598876612',
    syntheticVendorCode: 'SCR-SLK-SUN-90',
    syntheticSize: '90×90',
  },
  {
    key: 'fail-4',
    markingCode: '010461230001122344Fs7QpWx0',
    reason: 'В файле повреждён GTIN, распознать не удалось',
    syntheticGtin: '04612300011223',
    syntheticVendorCode: 'DRS-LIN-SUM-42',
    syntheticSize: '42',
  },
]

export type SampleFile = {
  name: string
  size: number
}

export type DemoScenario = 'partial' | 'full' | 'error'

export const demoScenarios: { id: DemoScenario; label: string; hint: string }[] = [
  {
    id: 'partial',
    label: 'Частичный успех',
    hint: 'Часть КИЗ распознана, остальные попадают в блок «Не подгружено» с PDF.',
  },
  {
    id: 'full',
    label: 'Полный успех',
    hint: 'Все КИЗ распознаны, блок «Не подгружено — 0 КИЗ» показывается без действий.',
  },
  {
    id: 'error',
    label: 'Технический сбой',
    hint: 'Распознавание не завершено; повторить или выбрать другой файл.',
  },
]

export const sampleAutoFiles: SampleFile[] = [
  { name: 'КИЗ_поставка_2026-09-22.pdf', size: 384_512 },
  { name: 'chestnyy_znak_export.csv', size: 12_233 },
]

export function formatFileSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} Б`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} КБ`
  return `${(bytes / (1024 * 1024)).toFixed(2)} МБ`
}

export type PreviewGroupSeed = {
  key: string
  gtin: string
  codesCount: number
  suggestedTitle: string
  suggestedProductIds: string[]
}

export const previewGroupSeeds: PreviewGroupSeed[] = [
  {
    key: 'preview-1',
    gtin: '04650097654321',
    codesCount: 174,
    suggestedTitle: 'Палантин Оазис · 90×180 / 70×140',
    suggestedProductIds: ['p-1001', 'p-1002'],
  },
  {
    key: 'preview-2',
    gtin: '04650098811234',
    codesCount: 42,
    suggestedTitle: 'Худи Классик · бордо XL',
    suggestedProductIds: ['p-1003'],
  },
]

export const manualLoadedPerProduct: Record<string, number> = {
  'p-1001': 128,
  'p-1002': 46,
  'p-1003': 42,
  'p-1004': 38,
  'p-1005': 25,
  'p-1006': 24,
  'p-1007': 21,
  'p-1008': 18,
  'p-1009': 15,
  'p-1010': 12,
}
