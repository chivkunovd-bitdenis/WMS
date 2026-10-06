// @vitest-environment jsdom
import { act, type ComponentProps, type ComponentType } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { FfInboundRequestView } from './FfInboundRequestView'

// WMS-687: this is deliberately the real catalog container import, replaced
// only at its outer UI boundary.  A local form or local API client cannot make
// this probe visible, so the contract rejects a copy of the stock dialog.
const containerCalls = vi.hoisted(() => [] as Array<Record<string, unknown>>)

vi.mock('./products-fbs/FbsStockDialogContainer', () => ({
  FbsStockDialogContainer: (props: Record<string, unknown>) => {
    containerCalls.push(props)
    return <div data-testid="wms687-shared-fbs-stock-container" />
  },
}))

vi.setConfig({ testTimeout: 20000 })

function documentDetail(operationType: 'inbound' | 'return') {
  return {
    id: `request-687-${operationType}`,
    document_number: `WMS-687-${operationType}`,
    display_number: '687',
    waybill_number: null,
    warehouse_id: 'warehouse-687',
    status: 'draft',
    operation_type: operationType,
    marketplace: null,
    marketplace_warning: null,
    planned_delivery_date: null,
    planned_box_count: null,
    actual_box_count: null,
    boxes_discrepancy: false,
    has_discrepancy: false,
    seller_id: 'seller-687',
    seller_name: 'Селлер WMS-687',
    created_by_seller_id: 'seller-687',
    created_at: '2026-10-07T00:00:00Z',
    distribution_completed_at: null,
    sorting_remaining_qty: 0,
    boxes: [],
    cargo_places: [],
    lines: [
      {
        id: 'line-a', product_id: 'product-a', sku_code: 'SKU-A', product_name: 'Товар А',
        wb_barcode: null, requires_honest_sign: false, length_mm: null, width_mm: null,
        height_mm: null, weight_g: null, volume_liters: null, added_by_fulfillment: false,
        expected_qty: 3, actual_qty: 0, posted_qty: 0,
        storage_location_id: null, storage_location_code: null,
      },
      {
        id: 'line-b', product_id: 'product-b', sku_code: 'SKU-B', product_name: 'Товар Б',
        wb_barcode: null, requires_honest_sign: false, length_mm: null, width_mm: null,
        height_mm: null, weight_g: null, volume_liters: null, added_by_fulfillment: false,
        expected_qty: 2, actual_qty: 0, posted_qty: 0,
        storage_location_id: null, storage_location_code: null,
      },
    ],
  }
}

function json(body: unknown): Response {
  return new Response(JSON.stringify(body), { headers: { 'Content-Type': 'application/json' } })
}

let root: Root
let host: HTMLDivElement

async function flush(): Promise<void> {
  await act(async () => {
    await Promise.resolve()
    await Promise.resolve()
  })
}

async function renderDocument(operationType: 'inbound' | 'return'): Promise<void> {
  const current = documentDetail(operationType)
  vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL) => {
    const url = String(input)
    if (url.endsWith(`/operations/inbound-intake-requests/${current.id}`)) return json(current)
    if (url.includes('/products/linked-wb-catalog')) return json([])
    if (url.endsWith('/marking-codes')) return json({ items: [], checking: false })
    if (url.includes('/locations?exclude_sorting_zone=true')) return json([])
    if (url.endsWith('/warehouses')) return json([{ id: 'warehouse-687', name: 'Основной', code: 'MAIN' }])
    throw new Error(`Unexpected WMS-687 request: ${url}`)
  }))
  await act(async () => {
    root.render(
      <FfInboundRequestView
        token="wms687-token"
        requestId={current.id}
        isFulfillmentAdmin
        workspace="reception"
        onClose={() => undefined}
      />,
    )
  })
  await flush()
}

function testId(id: string): HTMLElement {
  const element = document.querySelector(`[data-testid="${id}"]`)
  expect(element, id).toBeTruthy()
  return element as HTMLElement
}

// R4: право входа совпадает с уже существующим правом настройки каталога, а
// не с более широким правом работы в приёмке. Пока production-компонент ещё
// не принимает этот prop, сужаем тип только на стороне теста: так RED
// показывает отсутствие именно нужного контракта, а не ошибку TypeScript.
const FfInboundWithCatalogPermission = FfInboundRequestView as unknown as ComponentType<
  ComponentProps<typeof FfInboundRequestView> & { canManageCatalog: boolean }
>

async function click(id: string): Promise<void> {
  await act(async () => testId(id).click())
  await flush()
}

beforeEach(() => {
  ;(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true
  containerCalls.length = 0
  host = document.createElement('div')
  document.body.append(host)
  root = createRoot(host)
})

afterEach(async () => {
  await act(async () => root.unmount())
  host.remove()
  vi.unstubAllGlobals()
  vi.restoreAllMocks()
})

describe('WMS-687 shared FBS stock dialog from an inbound document', () => {
  it.each(['inbound', 'return'] as const)(
    '%s selects only document products and opens the catalog FbsStockDialogContainer',
    async (operationType) => {
      await renderDocument(operationType)

      await click('ff-inbound-stock-select-line-line-a')
      await click('ff-inbound-set-fbs-stock')

      expect(testId('wms687-shared-fbs-stock-container')).toBeTruthy()
      expect(containerCalls).toHaveLength(1)
      expect(containerCalls[0]).toMatchObject({
        token: 'wms687-token',
        sellerId: 'seller-687',
        sellerName: 'Селлер WMS-687',
        chosen: [{ id: 'product-a', name: 'Товар А', sku_code: 'SKU-A' }],
      })
      expect((containerCalls[0]?.chosen as Array<{ id: string }>).map((row) => row.id)).toEqual(['product-a'])
    },
  )

  it('does not expose the stock entry to a reception operator without the existing catalog-settings right', async () => {
    const current = documentDetail('inbound')
    vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input)
      if (url.endsWith(`/operations/inbound-intake-requests/${current.id}`)) return json(current)
      if (url.includes('/products/linked-wb-catalog')) return json([])
      if (url.endsWith('/marking-codes')) return json({ items: [], checking: false })
      if (url.includes('/locations?exclude_sorting_zone=true')) return json([])
      if (url.endsWith('/warehouses')) return json([{ id: 'warehouse-687', name: 'Основной', code: 'MAIN' }])
      throw new Error(`Unexpected WMS-687 request: ${url}`)
    }))
    await act(async () => {
      root.render(
        <FfInboundWithCatalogPermission
          token="wms687-token"
          requestId={current.id}
          // The document itself remains operable for a reception worker.
          isFulfillmentAdmin
          canManageCatalog={false}
          workspace="reception"
          onClose={() => undefined}
        />,
      )
    })
    await flush()

    expect(document.querySelector('[data-testid="ff-inbound-stock-select-line-line-a"]')).toBeNull()
    expect(document.querySelector('[data-testid="ff-inbound-set-fbs-stock"]')).toBeNull()
    expect(containerCalls).toHaveLength(0)
  })
})
