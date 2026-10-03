import { useSyncExternalStore } from 'react'

/**
 * WMS-649 · данные макета: три выдуманных товара и хранилище «ШК по умолчанию».
 *
 * Товары нарочно покрывают три случая из слов владельца: только WB, только Ozon
 * и «микс» (в обороте на обеих площадках). У каждой площадки по два кода, чтобы
 * было что выбирать «по умолчанию». WB-коды выглядят как настоящие WB (2037…),
 * Ozon-коды — как коды Ozon (OZN…): на этикетке сразу видно, чей код напечатан.
 */

export type Marketplace = 'wb' | 'ozon'
export type ProductKind = 'wb' | 'ozon' | 'mix'

export type DemoSeller = { id: string; name: string }

export const DEMO_SELLER: DemoSeller = { id: 'sel-649', name: 'ООО Тест-Селлер' }

export type DemoProduct = {
  kind: ProductKind
  id: string
  sku: string
  name: string
  vendorCode: string
  nmId: number | null
  size: string
  color: string
  brand: string
  composition: string
  subject: string
  /** Коды WB в «исходном» порядке (до выбора умолчания). */
  wbCodes: string[]
  /** Коды Ozon в «исходном» порядке. */
  ozonCodes: string[]
  ozon: { offerId: string; sku: string; productId: string } | null
  honestSign: boolean
  markingCodes: number
  stock: number
  packaging: string | null
}

export const PRODUCTS: DemoProduct[] = [
  {
    kind: 'wb',
    id: 'p649-wb',
    sku: 'TS-WHT-M',
    name: 'Футболка хлопок белая, M',
    vendorCode: 'TSHIRT-WHITE',
    nmId: 178452301,
    size: 'M',
    color: 'белый',
    brand: 'Basic Cotton',
    composition: 'хлопок 92%, эластан 8%',
    subject: 'Футболки',
    wbCodes: ['2037123456789', '2037123456796'],
    ozonCodes: [],
    ozon: null,
    honestSign: false,
    markingCodes: 0,
    stock: 240,
    packaging: 'Сложить пополам, пакет 30×40.',
  },
  {
    kind: 'ozon',
    id: 'p649-ozon',
    sku: 'SN-RUN-42',
    name: 'Кроссовки беговые, 42',
    vendorCode: 'SNEAKERS-RUN',
    nmId: null,
    size: '42',
    color: 'чёрный',
    brand: 'Cityline',
    composition: 'текстиль, резина',
    subject: 'Кроссовки',
    wbCodes: [],
    ozonCodes: ['OZN1180340021', 'OZN1180340038'],
    ozon: { offerId: 'SNEAKERS-RUN-42', sku: '1180340021', productId: '1180340' },
    honestSign: false,
    markingCodes: 0,
    stock: 96,
    packaging: 'Обувная коробка в пакет 40×60.',
  },
  {
    kind: 'mix',
    id: 'p649-mix',
    sku: 'HD-GRY-L',
    name: 'Худи оверсайз серое, L',
    vendorCode: 'HOODIE-GREY',
    nmId: 191203744,
    size: 'L',
    color: 'серый',
    brand: 'Basic Cotton',
    composition: 'хлопок 80%, полиэстер 20%',
    subject: 'Худи',
    wbCodes: ['2037987654321', '2037987654338'],
    ozonCodes: ['OZN2290150011', 'OZN2290150028'],
    ozon: { offerId: 'HOODIE-GREY-L', sku: '2290150011', productId: '2290150' },
    honestSign: false,
    markingCodes: 0,
    stock: 180,
    packaging: 'Сложить втрое, курьерский пакет 24×32.',
  },
]

export function productById(id: string | null | undefined): DemoProduct | undefined {
  return PRODUCTS.find((product) => product.id === id)
}

export function productBySku(sku: string | null | undefined): DemoProduct | undefined {
  const wanted = (sku ?? '').trim()
  return PRODUCTS.find((product) => product.sku === wanted)
}

export function productByKind(kind: ProductKind): DemoProduct {
  return PRODUCTS.find((product) => product.kind === kind)!
}

export function kindLabel(kind: ProductKind): string {
  return kind === 'wb' ? 'только WB' : kind === 'ozon' ? 'только Ozon' : 'микс'
}

export function hasMarketplace(product: DemoProduct, marketplace: Marketplace): boolean {
  return marketplace === 'wb' ? product.wbCodes.length > 0 : product.ozonCodes.length > 0
}

/* ───────────── хранилище «ШК по умолчанию» (на площадку) ───────────── */

type Defaults = Record<string, { wb: string | null; ozon: string | null }>

let defaults: Defaults = Object.fromEntries(
  PRODUCTS.map((product) => [
    product.id,
    { wb: product.wbCodes[0] ?? null, ozon: product.ozonCodes[0] ?? null },
  ]),
)
const listeners = new Set<() => void>()

function emit() {
  listeners.forEach((listener) => listener())
}

export function setDefaultCode(productId: string, marketplace: Marketplace, code: string): void {
  const current = defaults[productId]
  if (!current) return
  defaults = { ...defaults, [productId]: { ...current, [marketplace]: code } }
  emit()
}

export function useDefaults(): Defaults {
  return useSyncExternalStore(
    (listener) => {
      listeners.add(listener)
      return () => listeners.delete(listener)
    },
    () => defaults,
  )
}

export function getDefaultCode(product: DemoProduct, marketplace: Marketplace): string | null {
  const stored = defaults[product.id]?.[marketplace]
  return stored ?? (marketplace === 'wb' ? product.wbCodes[0] : product.ozonCodes[0]) ?? null
}

/**
 * Коды площадки, умолчание — первым. Именно так сегодня работает продукт:
 * «основной» код — первый в списке, поэтому макет эмулирует хранимое умолчание
 * перестановкой порядка в ответах подставного сервера.
 */
export function orderedCodes(product: DemoProduct, marketplace: Marketplace): string[] {
  const codes = marketplace === 'wb' ? product.wbCodes : product.ozonCodes
  const chosen = getDefaultCode(product, marketplace)
  if (!chosen || !codes.includes(chosen)) return [...codes]
  return [chosen, ...codes.filter((code) => code !== chosen)]
}

/* ───────────── то, что отдаёт бэкенд (формы ответов) ───────────── */

export function ozonBinding(product: DemoProduct) {
  if (!product.ozon) return []
  return [
    {
      marketplace: 'ozon' as const,
      external_product_id: product.ozon.productId,
      external_offer_id: product.ozon.offerId,
      external_sku: product.ozon.sku,
      external_barcodes: orderedCodes(product, 'ozon'),
    },
  ]
}

/** Поля, общие для строки каталога, карточки товара и «linked-wb-catalog». */
export function catalogFields(product: DemoProduct) {
  const wb = orderedCodes(product, 'wb')
  const marketplaces: Marketplace[] = []
  if (product.wbCodes.length > 0) marketplaces.push('wb')
  if (product.ozonCodes.length > 0) marketplaces.push('ozon')
  return {
    id: product.id,
    seller_id: DEMO_SELLER.id,
    seller_name: DEMO_SELLER.name,
    name: product.name,
    sku_code: product.sku,
    wb_nm_id: product.nmId,
    wb_vendor_code: product.wbCodes.length > 0 ? product.vendorCode : null,
    ozon_sku: product.ozon?.sku ?? null,
    ozon_offer_id: product.ozon?.offerId ?? null,
    wb_subject_name: product.subject,
    wb_primary_image_url: null,
    marketplace_bindings: ozonBinding(product),
    wb_barcodes: wb,
    wb_primary_barcode: wb[0] ?? null,
    wb_size: product.size,
    wb_color: product.color,
    wb_brand: product.brand,
    wb_composition: product.composition,
    packaging_instructions: product.packaging,
    country_of_origin_iso_code: null,
    requires_honest_sign: product.honestSign,
    marketplaces,
  }
}

export function catalogRow(product: DemoProduct) {
  return {
    ...catalogFields(product),
    has_packaging_instructions: product.packaging != null,
    marking_available_count: product.markingCodes,
    fbs_stock_sync_enabled: false,
    fbs_stock_limit: null,
    fbs_published_amount: null,
    fbs_percent: null,
    fbs_same_everywhere: true,
    fbs_sync_status: null,
  }
}

export function stockRow(product: DemoProduct) {
  return {
    product_id: product.id,
    sku_code: product.sku,
    product_name: product.name,
    quantity: product.stock,
    quantity_in_sorting: 0,
    quantity_in_storage: product.stock,
    reserved: 0,
    available: product.stock,
    quantity_fbs: 0,
    quantity_reserved_directions: 0,
    quantity_free_fbo: product.stock,
  }
}
