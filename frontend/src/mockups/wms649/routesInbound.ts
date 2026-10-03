import type { StubRoute } from '../../screens/ff/knowledge/scenes/stubFetch'
import { bodyOf, WAREHOUSE } from './routes'
import { catalogFields, DEMO_SELLER, getDefaultCode, orderedCodes, PRODUCTS, productById, type DemoProduct } from './products'
import { runtime } from './runtime'

/**
 * WMS-649 · подставные документы приёмки.
 *
 * Три документа: обычная приёмка (площадка не определена), возврат WB и возврат
 * Ozon (у возврата в документе есть поле marketplace). Состав — те товары,
 * которые на этой площадке бывают.
 */

export type InboundVariant = 'recv' | 'ret-wb' | 'ret-ozon' | 'seller'

export const INBOUND_IDS: Record<InboundVariant, string> = {
  recv: 'inb-649-recv',
  'ret-wb': 'inb-649-ret-wb',
  'ret-ozon': 'inb-649-ret-ozon',
  seller: 'inb-649-seller',
}

function variantOf(id: string): InboundVariant | null {
  const found = (Object.entries(INBOUND_IDS) as Array<[InboundVariant, string]>).find(([, value]) => value === id)
  return found?.[0] ?? null
}

export function inboundProducts(variant: InboundVariant): DemoProduct[] {
  if (variant === 'ret-wb') return PRODUCTS.filter((product) => product.wbCodes.length > 0)
  if (variant === 'ret-ozon') return PRODUCTS.filter((product) => product.ozonCodes.length > 0)
  return PRODUCTS
}

export const EXPECTED_QTY = 10

const scanned = new Map<string, number>()

/**
 * Поле «wb_barcode» строки — то, что экран приёмки печатает при скане возврата.
 * Сегодня бэкенд отдаёт туда основной код WB товара (у товара «только Ozon» —
 * пусто). В предложении код строки возврата берётся по площадке документа.
 */
function printableCode(product: DemoProduct, variant: InboundVariant): string | null {
  if (runtime.mode === 'proposal') {
    if (variant === 'ret-ozon') return getDefaultCode(product, 'ozon')
    if (variant === 'ret-wb') return getDefaultCode(product, 'wb')
  }
  return product.wbCodes.length > 0 ? (orderedCodes(product, 'wb')[0] ?? null) : null
}

function lineOf(product: DemoProduct, variant: InboundVariant, index: number) {
  const draft = variant === 'seller'
  const actual = draft ? null : (scanned.get(`${variant}:${product.id}`) ?? 0)
  return {
    id: `${variant}-ln-${index + 1}`,
    product_id: product.id,
    sku_code: product.sku,
    product_name: product.name,
    wb_barcode: printableCode(product, variant),
    requires_honest_sign: false,
    length_mm: 250,
    width_mm: 200,
    height_mm: 40,
    weight_g: 300,
    volume_liters: 2,
    added_by_fulfillment: false,
    expected_qty: EXPECTED_QTY,
    actual_qty: actual,
    effective_actual_qty: actual,
    defective_qty: 0,
    posted_qty: 0,
    storage_location_id: null,
    storage_location_code: null,
  }
}

function detailOf(variant: InboundVariant) {
  const products = inboundProducts(variant)
  const isReturn = variant === 'ret-wb' || variant === 'ret-ozon'
  return {
    id: INBOUND_IDS[variant],
    document_number: isReturn ? 'ВОЗВР-26-10-03-7' : variant === 'seller' ? 'ПРИЕМ-26-10-03-9' : 'ПРИЕМ-26-10-03-5',
    display_number: isReturn ? '№000007' : variant === 'seller' ? '№000009' : '№000005',
    public_number: null,
    human_number: null,
    waybill_number: null,
    warehouse_id: WAREHOUSE.id,
    status: variant === 'seller' ? 'draft' : 'receiving',
    operation_type: isReturn ? 'return' : 'inbound',
    marketplace: variant === 'ret-wb' ? 'wildberries' : variant === 'ret-ozon' ? 'ozon' : null,
    marketplace_warning: null,
    planned_delivery_date: '2026-10-03',
    planned_box_count: null,
    actual_box_count: 0,
    boxes_discrepancy: false,
    has_discrepancy: false,
    seller_id: DEMO_SELLER.id,
    seller_name: DEMO_SELLER.name,
    created_by_seller_id: variant === 'seller' ? DEMO_SELLER.id : null,
    created_at: '2026-10-03T08:00:00Z',
    distribution_completed_at: null,
    boxes: [],
    cargo_places: [],
    lines: products.map((product, index) => lineOf(product, variant, index)),
  }
}

export const inboundRoutes: StubRoute[] = [
  {
    path: /^\/operations\/inbound-intake-requests\/([^/?]+)$/,
    handler: (match) => {
      const variant = variantOf(match[1]!)
      return variant ? detailOf(variant) : null
    },
  },
  {
    method: 'POST',
    path: /^\/operations\/inbound-intake-requests\/([^/?]+)\/receiving\/scan/,
    handler: (match, init) => {
      const variant = variantOf(match[1]!)
      if (!variant) return null
      const body = bodyOf(init)
      const code = String(body.barcode ?? '').trim()
      const products = inboundProducts(variant)
      const product =
        products.find((item) => [...item.wbCodes, ...item.ozonCodes].includes(code)) ??
        productById(String(body.product_id ?? '')) ??
        products[0]!
      const key = `${variant}:${product.id}`
      scanned.set(key, (scanned.get(key) ?? 0) + 1)
      return lineOf(product, variant, products.indexOf(product))
    },
  },
  {
    // Каталог продавца для его портала: тот же состав, что и у склада.
    path: /^\/products\/wb-catalog/,
    handler: () => PRODUCTS.map((product) => catalogFields(product)),
  },
  {
    path: /^\/operations\/inbound-intake-requests\/[^/?]+\/marking-codes$/,
    handler: () => ({ items: [], checking: false }),
  },
  { path: /^\/operations\/inbound-intake-requests\/[^/?]+\/distribution-lines/, handler: () => [] },
  { path: /^\/operations\/inbound-intake-requests\/[^/?]+\/ozon-returns\/groups/, handler: () => [] },
  { path: /^\/operations\/discrepancy-acts/, handler: () => [] },
  { path: /^\/warehouses\/[^/?]+\/locations/, handler: () => [] },
]

/** Строки листа приёмки так, как их собирает кнопка «Печать накладной». */
export function receivingSheetItems(
  barcodeOf: (product: DemoProduct) => string | null,
): Array<{
  product_name: string
  vendor_code: string
  sku_code: string
  barcode: string | null
  wb_nm_id: number | null
  photo_url: string | null
  expected_qty: number
}> {
  return PRODUCTS.map((product) => ({
    product_name: product.name,
    vendor_code: product.vendorCode,
    sku_code: product.sku,
    barcode: barcodeOf(product),
    wb_nm_id: product.nmId,
    photo_url: null,
    expected_qty: EXPECTED_QTY,
  }))
}
