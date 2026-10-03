import type { StubRoute } from '../../screens/ff/knowledge/scenes/stubFetch'
import { DEMO_SELLER, PRODUCTS, type DemoProduct, type Marketplace } from './products'
import { WAREHOUSE } from './routes'

/**
 * WMS-649 · подставные задания упаковки отгрузки на маркетплейс.
 *
 * Задание упаковки сегодня не знает площадку отгрузки: в типе задания нет поля
 * marketplace (оно есть только у документа отгрузки, на который задание ссылается).
 * Макет по переключателю «Документ WB | Ozon» берёт товары, которые бывают на этой
 * площадке: WB — «только WB» и «микс», Ozon — «только Ozon» и «микс».
 */

export const PACKAGING_IDS: Record<Marketplace, string> = {
  wb: 'pk-649-wb',
  ozon: 'pk-649-ozon',
}

export const PACKAGING_QTY = 10

export function packagingProducts(marketplace: Marketplace): DemoProduct[] {
  return PRODUCTS.filter((product) =>
    marketplace === 'wb' ? product.wbCodes.length > 0 : product.ozonCodes.length > 0,
  )
}

function marketplaceOf(id: string): Marketplace | null {
  if (id === PACKAGING_IDS.wb) return 'wb'
  if (id === PACKAGING_IDS.ozon) return 'ozon'
  return null
}

function taskOf(marketplace: Marketplace) {
  const products = packagingProducts(marketplace)
  return {
    id: PACKAGING_IDS[marketplace],
    document_number: marketplace === 'wb' ? 'Упаковка № 000051' : 'Упаковка № 000052',
    display_number: marketplace === 'wb' ? '№000051' : '№000052',
    warehouse_id: WAREHOUSE.id,
    warehouse_name: WAREHOUSE.name,
    warehouse_code: WAREHOUSE.code,
    seller_id: DEMO_SELLER.id,
    seller_name: DEMO_SELLER.name,
    status: 'in_progress',
    marketplace_unload_request_id: `mpu-649-${marketplace}`,
    inbound_intake_request_id: null,
    is_complete: false,
    created_at: '2026-10-03T08:10:00Z',
    updated_at: '2026-10-03T09:00:00Z',
    lines: products.map((product, index) => ({
      id: `${marketplace}-pl-${index + 1}`,
      product_id: product.id,
      seller_id: DEMO_SELLER.id,
      seller_name: DEMO_SELLER.name,
      sku_code: product.sku,
      product_name: product.name,
      storage_location_id: 'loc-649',
      storage_location_code: 'A-01-02',
      packaging_instructions: product.packaging,
      requires_honest_sign: false,
      qty_total: PACKAGING_QTY,
      qty_suggested_packed: 0,
      qty_confirmed_packed: 0,
      qty_need_pack: PACKAGING_QTY,
      qty_packed_in_task: 0,
      qty_done: 0,
      qty_marking_printed: 0,
      qty_marking_external: 0,
      qty_product_label_printed: 0,
      marking_available_count: 0,
      is_complete: false,
    })),
    events: [],
  }
}

export const packagingRoutes: StubRoute[] = [
  {
    path: /^\/operations\/packaging-tasks\/(pk-649-[^/?]+)$/,
    handler: (match) => {
      const marketplace = marketplaceOf(match[1]!)
      return marketplace ? taskOf(marketplace) : null
    },
  },
  {
    path: /^\/operations\/packaging-tasks\?/,
    handler: () => [taskOf('wb'), taskOf('ozon')],
  },
  { path: /^\/operations\/marking-codes\/pending-marking/, handler: () => ({ rows: [], total: 0 }) },
]
