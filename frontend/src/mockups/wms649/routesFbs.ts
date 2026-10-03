import type { StubRoute } from '../../screens/ff/knowledge/scenes/stubFetch'
import type { FbsWorkspace } from '../../screens/v2/fbsApi'
import {
  DEMO_SELLER,
  getDefaultCode,
  orderedCodes,
  ozonBinding,
  PRODUCTS,
  type DemoProduct,
  type Marketplace,
} from './products'
import { bodyOf, WAREHOUSE } from './routes'

/**
 * WMS-649 · подставные поставки FBS: одна у Wildberries, одна у Ozon.
 *
 * Товары — те, что на этой площадке бывают: WB — «только WB» и «микс», Ozon —
 * «только Ozon» и «микс». Площадка поставки известна из самой поставки
 * (supply.marketplace), поэтому окно печати знает её без вопросов к оператору.
 */

export type FbsStage = 'packing' | 'picking'

export function fbsSupplyId(marketplace: Marketplace, stage: FbsStage): string {
  return `sup-649-${marketplace}${stage === 'picking' ? '-pick' : ''}`
}

function parseSupplyId(id: string): { marketplace: Marketplace; stage: FbsStage } | null {
  const match = /^sup-649-(wb|ozon)(-pick)?$/.exec(id)
  if (!match) return null
  return { marketplace: match[1] as Marketplace, stage: match[2] ? 'picking' : 'packing' }
}

const PACKAGING_TASK_IDS: Record<Marketplace, string> = {
  wb: 'pt-649-wb',
  ozon: 'pt-649-ozon',
}

export function fbsProducts(marketplace: Marketplace): DemoProduct[] {
  return PRODUCTS.filter((product) =>
    marketplace === 'wb' ? product.wbCodes.length > 0 : product.ozonCodes.length > 0,
  )
}

function inHours(hours: number): string {
  return new Date(Date.now() + hours * 3_600_000).toISOString()
}

const WB_WAREHOUSE = { id: 507, name: 'Коледино' }
const ORDERS_PER_PRODUCT = 2

function orderId(marketplace: Marketplace, product: DemoProduct, unit: number): string {
  return `o649-${marketplace}-${product.kind}-${unit}`
}

function orderOf(
  marketplace: Marketplace,
  stage: FbsStage,
  product: DemoProduct,
  unit: number,
  index: number,
): FbsWorkspace['orders'][number] {
  const wbOrderId = marketplace === 'wb' ? 3941200100 + index : 7100000 + index
  const wbCode = orderedCodes(product, 'wb')[0] ?? null
  const bindings = ozonBinding(product)
  const ozonPosition =
    marketplace === 'ozon'
      ? [
          {
            id: `pos-${orderId(marketplace, product, unit)}`,
            image_url: null,
            barcode: null,
            product_id: product.id,
            marketplace_bindings: bindings,
            name: product.name,
            seller_article: product.ozon?.offerId ?? product.vendorCode,
            sku: product.ozon?.sku ?? product.sku,
            size: product.size,
            color: product.color,
            brand: product.brand,
            composition: product.composition,
            quantity: 1,
            reserved_quantity: 1,
            picked_quantity: 1,
          },
        ]
      : []
  return {
    id: orderId(marketplace, product, unit),
    marketplace,
    external_order_id: marketplace === 'ozon' ? `0${wbOrderId}-0001` : null,
    wb_order_id: wbOrderId,
    status: 'assembling',
    wb_status: 'confirm',
    supplier_status: 'confirm',
    seller: { id: DEMO_SELLER.id, name: DEMO_SELLER.name },
    wb_warehouse: WB_WAREHOUSE,
    wms_warehouse: { id: WAREHOUSE.id, name: WAREHOUSE.name },
    product: {
      id: product.id,
      name: product.name,
      image_url: null,
      seller_article: product.vendorCode,
      wb_article: product.nmId,
      // Код, который WB отдаёт вместе с заказом, — сам заказ WB знает своё.
      barcode: marketplace === 'wb' ? wbCode : null,
      sku: product.sku,
      chrt_id: 4217001,
      category: product.subject,
      color: product.color,
      brand: product.brand,
      composition: product.composition,
      size: product.size,
      marketplace_bindings: bindings,
      packaging_instructions: product.packaging,
      has_packaging_instructions: product.packaging != null,
    },
    positions: ozonPosition,
    inventory: { available_unpacked: 10, locations: [] },
    buyer_type: 'individual',
    cargo_type: 'mgt',
    can_pvz: false,
    delivery_route: marketplace === 'ozon' ? 'Ozon Логистика · Москва' : null,
    metadata: { required: [], optional: [], states: [], delivery_allowed: true, last_checked_at: null },
    sticker: { code: null, status: 'not_requested', asset_url: null, applied_at: null },
    pick:
      stage === 'picking'
        ? { status: 'pending', location_code: 'A-01-02', picked_at: null }
        : { status: 'picked', location_code: 'A-01-02', picked_at: inHours(-1) },
    pack: { status: 'pending', packed_at: null },
    created_at_wb: inHours(-8),
    deadline_at: inHours(28),
    supply_id: fbsSupplyId(marketplace, stage),
    selection_blockers: [],
    tape_order_index: index,
  }
}

function ordersOf(marketplace: Marketplace, stage: FbsStage = 'packing') {
  const orders: Array<FbsWorkspace['orders'][number]> = []
  let index = 0
  for (const product of fbsProducts(marketplace)) {
    for (let unit = 1; unit <= ORDERS_PER_PRODUCT; unit += 1) {
      orders.push(orderOf(marketplace, stage, product, unit, index))
      index += 1
    }
  }
  return orders
}

function workspaceOf(marketplace: Marketplace, stage: FbsStage): FbsWorkspace {
  const orders = ordersOf(marketplace, stage)
  const picking = stage === 'picking'
  return {
    supply: {
      id: fbsSupplyId(marketplace, stage),
      marketplace,
      wb_supply_id: marketplace === 'wb' ? 'WB-GI-6490001' : null,
      source: 'wms',
      name: marketplace === 'wb' ? 'Поставка WB 000649' : 'Поставка Ozon 000650',
      status: 'assembling',
      delivery_type: 'warehouse_sc',
      seller: { id: DEMO_SELLER.id, name: DEMO_SELLER.name },
      wb_warehouse: WB_WAREHOUSE,
      wms_warehouse: { id: WAREHOUSE.id, name: WAREHOUSE.name },
      planned_destination: null,
      planned_shipment_date: new Date(Date.now() + 86_400_000).toISOString().slice(0, 10),
      nearest_deadline_at: inHours(28),
      packaging_task_id: PACKAGING_TASK_IDS[marketplace],
      barcode_asset: null,
    },
    stage,
    progress: {
      picked: picking ? 0 : orders.length,
      packed: 0,
      metadata_ready: orders.length,
      stickers_ready: 0,
      total: orders.length,
    },
    blockers: [],
    orders,
    cargo_places: [],
    boxes: [],
    delivery_preflight: null,
    last_wb_sync_at: inHours(-0.2),
    server_now: new Date().toISOString(),
  }
}

function packagingTaskOf(marketplace: Marketplace) {
  const products = fbsProducts(marketplace)
  return {
    id: PACKAGING_TASK_IDS[marketplace],
    document_number: marketplace === 'wb' ? '000649' : '000650',
    display_number: marketplace === 'wb' ? '000649' : '000650',
    warehouse_id: WAREHOUSE.id,
    warehouse_name: WAREHOUSE.name,
    seller_id: DEMO_SELLER.id,
    seller_name: DEMO_SELLER.name,
    status: 'in_progress',
    marketplace_unload_request_id: null,
    inbound_intake_request_id: null,
    is_complete: false,
    created_at: inHours(-2),
    updated_at: inHours(-0.3),
    lines: products.map((product, index) => ({
      id: `${marketplace}-fl-${index + 1}`,
      product_id: product.id,
      seller_id: DEMO_SELLER.id,
      seller_name: DEMO_SELLER.name,
      sku_code: product.sku,
      product_name: product.name,
      storage_location_id: 'loc-649',
      storage_location_code: 'A-01-02',
      packaging_instructions: product.packaging,
      requires_honest_sign: false,
      qty_total: ORDERS_PER_PRODUCT,
      qty_suggested_packed: ORDERS_PER_PRODUCT,
      qty_confirmed_packed: 0,
      qty_need_pack: ORDERS_PER_PRODUCT,
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

export const fbsRoutes: StubRoute[] = [
  {
    path: /^\/operations\/fbs-supplies\/([^/?]+)\/workspace/,
    handler: (match) => {
      const parsed = parseSupplyId(match[1]!)
      return parsed ? workspaceOf(parsed.marketplace, parsed.stage) : null
    },
  },
  {
    path: /^\/operations\/fbs-supplies\/([^/?]+)\/pick-options/,
    handler: (match) => {
      const parsed = parseSupplyId(match[1]!)
      if (!parsed) return []
      return fbsProducts(parsed.marketplace).map((product) => ({
        product_id: product.id,
        sku_code: product.sku,
        product_name: product.name,
        planned_qty: ORDERS_PER_PRODUCT,
        picked_qty: 0,
        locations: [
          {
            storage_location_id: 'loc-649',
            location_code: 'A-01-02',
            quantity: 20,
            reserved: ORDERS_PER_PRODUCT,
            available: 20,
            picked: 0,
            sources: [
              { quantity: 20, is_loose: true, source_label: 'Россыпью', container_path: [], picked: 0 },
            ],
          },
        ],
      }))
    },
  },
  {
    method: 'POST',
    path: /^\/operations\/fbs-supplies\/([^/?]+)\/order-print-tape/,
    handler: (match, init) => {
      const marketplace = parseSupplyId(match[1]!)?.marketplace
      const body = bodyOf(init) as { order_ids?: string[]; include_order_qr?: boolean }
      const wanted = new Set(body.order_ids ?? [])
      const orders = marketplace ? ordersOf(marketplace).filter((order) => wanted.has(order.id)) : []
      return {
        orders: orders.map((order) => ({
          order_id: order.id,
          wb_order_id: order.wb_order_id,
          requires_honest_sign: false,
          qr_asset: body.include_order_qr
            ? {
                id: `qr-${order.id}`,
                kind: 'order_sticker',
                status: 'ready',
                content_type: 'image/svg+xml',
                width_mm: 58,
                height_mm: 40,
                preview_url: `/operations/fbs-print-assets/qr-${order.id}/preview`,
                download_url: null,
                checksum: null,
                applied_at: null,
                error: null,
              }
            : null,
          codes: [],
          printed_codes: [],
          shortage: null,
        })),
        requested: orders.length,
        ready: orders.length,
        missing: 0,
        failed: 0,
        order_errors: [],
        shortage: 0,
      }
    },
  },
  {
    path: /^\/operations\/fbs-supplies\/([^/?]+)(?:\?|$)/,
    handler: (match) => {
      const parsed = parseSupplyId(match[1]!)
      if (!parsed) return null
      const { marketplace, stage } = parsed
      return {
        id: fbsSupplyId(marketplace, stage),
        name: marketplace === 'wb' ? 'Поставка WB 000649' : 'Поставка Ozon 000650',
        wb_supply_id: marketplace === 'wb' ? 'WB-GI-6490001' : null,
        document_number: marketplace === 'wb' ? '000649' : '000650',
        display_number: marketplace === 'wb' ? '000649' : '000650',
        warehouse_name: WAREHOUSE.name,
        status: 'assembling',
        seller_id: DEMO_SELLER.id,
        seller_name: DEMO_SELLER.name,
        planned_shipment_date: new Date(Date.now() + 86_400_000).toISOString().slice(0, 10),
      }
    },
  },
  {
    path: /^\/operations\/packaging-tasks\/(pt-649-(?:wb|ozon))/,
    handler: (match) => packagingTaskOf(match[1] === PACKAGING_TASK_IDS.wb ? 'wb' : 'ozon'),
  },
]

/** Строки листа подбора и их коды: WB берёт код заказа, Ozon — код Ozon из привязки. */
export function pickingCode(product: DemoProduct, marketplace: Marketplace): string | null {
  return getDefaultCode(product, marketplace)
}
