// @vitest-environment jsdom
import { act } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { FfInboundRequestView } from './FfInboundRequestView'

// WMS-687 R2/R4: this deliberately mounts the real shared
// FbsStockDialogContainer. A stub would not prove that the loading and saved
// state belong to the catalog's form, nor that the form blocks document scans.

vi.setConfig({ testTimeout: 20000 })

type OperationType = 'inbound' | 'return'

function documentDetail(operationType: OperationType) {
  return {
    id: `request-687-${operationType}`,
    document_number: `WMS-687-${operationType}`,
    display_number: '687',
    waybill_number: null,
    warehouse_id: 'warehouse-687',
    status: 'receiving',
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

function deferred<T>() {
  let resolve!: (value: T) => void
  const promise = new Promise<T>((next) => { resolve = next })
  return { promise, resolve }
}

let root: Root
let host: HTMLDivElement

async function flush(): Promise<void> {
  await act(async () => {
    await Promise.resolve()
    await Promise.resolve()
    await Promise.resolve()
  })
}

function testId(id: string): HTMLElement {
  const element = document.querySelector(`[data-testid="${id}"]`)
  expect(element, id).toBeTruthy()
  return element as HTMLElement
}

async function click(id: string): Promise<void> {
  await act(async () => testId(id).click())
  await flush()
}

/** Keyboard-wedge scanner: a burst followed by Enter at its current focus. */
async function scan(code: string): Promise<void> {
  const target = document.activeElement ?? document.body
  await act(async () => {
    for (const key of code) {
      target.dispatchEvent(new KeyboardEvent('keydown', {
        key,
        code: /\d/.test(key) ? `Digit${key}` : `Key${key.toUpperCase()}`,
        bubbles: true,
        cancelable: true,
      }))
    }
    target.dispatchEvent(new KeyboardEvent('keydown', {
      key: 'Enter', code: 'Enter', bubbles: true, cancelable: true,
    }))
  })
  await flush()
}

beforeEach(() => {
  ;(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true
  // jsdom does not implement the browser scrolling side effect used by the
  // document error banner; it is not part of this scanner contract.
  Object.defineProperty(HTMLElement.prototype, 'scrollIntoView', {
    configurable: true,
    value: vi.fn(),
  })
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

describe('WMS-687 real shared stock dialog', () => {
  it.each(['inbound', 'return'] as const)(
    '%s blocks receiving scans while the shared dialog loads or is open, then restores the ordinary scan after close',
    async (operationType) => {
      const current = documentDetail(operationType)
      const rules = deferred<Response>()
      const scanCalls: Array<{ url: string; body: unknown }> = []
      vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
        const url = String(input)
        if (url.endsWith(`/operations/inbound-intake-requests/${current.id}`)) return json(current)
        if (url.includes('/products/linked-wb-catalog')) return json([])
        if (url.endsWith('/marking-codes')) return json({ items: [], checking: false })
        if (url.includes('/locations?exclude_sorting_zone=true')) return json([])
        if (url.endsWith('/warehouses')) return json([{ id: 'warehouse-687', name: 'Основной', code: 'MAIN' }])
        if (url.endsWith('/products/fbs-rule/bulk')) return rules.promise
        if (url.endsWith('/operations/fbs-sellers/seller-687/warehouses')) {
          return json([{ wb_warehouse_id: 501001, name: 'Склад WB', wms_warehouse_id: 'warehouse-687', served: true }])
        }
        if (url.endsWith('/operations/fbs-sellers/seller-687/warehouse-bindings')) {
          return json([{ id: 'binding-wb', wb_warehouse_id: 501001, external_warehouse_id: '501001', marketplace: 'wb', wms_warehouse_id: 'warehouse-687', wms_warehouse_name: 'Основной', is_active: true, served: true, editable: true }])
        }
        if (url.endsWith('/operations/fbs-sellers/seller-687/ozon-warehouses')) return json([])
        if (url.endsWith(`/operations/inbound-intake-requests/${current.id}/receiving/scan`)) {
          scanCalls.push({ url, body: JSON.parse(String(init?.body)) })
          return json({ ...current.lines[0], actual_qty: 1 })
        }
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

      await click('ff-inbound-stock-select-all')
      await click('ff-inbound-set-fbs-stock')

      // The real container is mounted but its common rule request is pending.
      // A scan at this point must not mutate the document behind the modal.
      await scan('12345')
      // Resolve even on RED so React has no deliberately orphaned request at
      // teardown; the assertion still describes the state during loading.
      rules.resolve(json({
        items: current.lines.map((line) => ({
          product_id: line.product_id,
          by_binding: {
            'binding-wb': {
              publish: true, mode: 'units', value: 7, units_configured: true,
              marketplace: 'wb', external_warehouse_id: '501001', wms_warehouse_id: 'warehouse-687',
              served: true, applicable: true, on_hand: 11, reserved: 0, free_stock: 11, published_now: 7,
            },
          },
        })),
      }))
      await flush()

      // Saved catalog conditions are rendered by the real common form; all
      // rows selected in the document reached the same form, not a copy.
      expect(testId('fbs-stock-head').textContent).toContain('2 товара')
      expect((testId('fbs-stock-units-binding-wb') as HTMLInputElement).value).toBe('7')

      await scan('12345')

      await click('fbs-stock-cancel')
      await scan('12345')
      // Only the post-close scan is allowed through. Keeping the complete
      // trace makes a RED distinguish a leak while loading from one in the
      // visible dialog, without replacing either real operation by a mock.
      expect(scanCalls).toEqual([
        {
          url: `/api/operations/inbound-intake-requests/${current.id}/receiving/scan`,
          body: { barcode: '12345' },
        },
      ])
    },
  )

  it.each(['inbound', 'return'] as const)(
    '%s sends all selected document products to the real container and renders its saved conditions',
    async (operationType) => {
      const current = documentDetail(operationType)
      const bulkProductIds: string[][] = []
      vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
        const url = String(input)
        if (url.endsWith(`/operations/inbound-intake-requests/${current.id}`)) return json(current)
        if (url.includes('/products/linked-wb-catalog')) return json([])
        if (url.endsWith('/marking-codes')) return json({ items: [], checking: false })
        if (url.includes('/locations?exclude_sorting_zone=true')) return json([])
        if (url.endsWith('/warehouses')) return json([{ id: 'warehouse-687', name: 'Основной', code: 'MAIN' }])
        if (url.endsWith('/products/fbs-rule/bulk')) {
          bulkProductIds.push((JSON.parse(String(init?.body)) as { product_ids: string[] }).product_ids)
          return json({
            items: current.lines.map((line) => ({
              product_id: line.product_id,
              by_binding: {
                'binding-wb': {
                  publish: true, mode: 'units', value: 7, units_configured: true,
                  marketplace: 'wb', external_warehouse_id: '501001', wms_warehouse_id: 'warehouse-687',
                  served: true, applicable: true, on_hand: 11, reserved: 0, free_stock: 11, published_now: 7,
                },
              },
            })),
          })
        }
        if (url.endsWith('/operations/fbs-sellers/seller-687/warehouses')) {
          return json([{ wb_warehouse_id: 501001, name: 'Склад WB', wms_warehouse_id: 'warehouse-687', served: true }])
        }
        if (url.endsWith('/operations/fbs-sellers/seller-687/warehouse-bindings')) {
          return json([{ id: 'binding-wb', wb_warehouse_id: 501001, external_warehouse_id: '501001', marketplace: 'wb', wms_warehouse_id: 'warehouse-687', wms_warehouse_name: 'Основной', is_active: true, served: true, editable: true }])
        }
        if (url.endsWith('/operations/fbs-sellers/seller-687/ozon-warehouses')) return json([])
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

      await click('ff-inbound-stock-select-all')
      await click('ff-inbound-set-fbs-stock')
      await flush()

      expect(bulkProductIds).toEqual([['product-a', 'product-b']])
      expect(testId('fbs-stock-head').textContent).toContain('2 товара')
      expect((testId('fbs-stock-units-binding-wb') as HTMLInputElement).value).toBe('7')
    },
  )
})
