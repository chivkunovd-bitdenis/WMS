import { beforeEach, describe, expect, it, vi } from 'vitest'

const hookRuntime = vi.hoisted(() => ({
  effects: [] as Array<() => void | (() => void)>,
}))

vi.mock('react', () => ({
  useCallback: <T>(callback: T) => callback,
  useEffect: (effect: () => void | (() => void)) => {
    hookRuntime.effects.push(effect)
  },
  useMemo: <T>(factory: () => T) => factory(),
}))

vi.mock('./useOzonReturnWorkflow', () => ({
  useOzonReturnWorkflow: () => ({}),
}))

import { useFfInboundRequestData, type FfInboundRequestDataContext } from './useFfInboundRequestData'

type MockResponseBody = Record<string, unknown> | unknown[]

function okJson(body: MockResponseBody): Response {
  return {
    ok: true,
    json: async () => body,
  } as Response
}

function makeDataContext(): FfInboundRequestDataContext {
  const noOp = () => undefined
  const values = {
    token: 'token',
    requestId: 'request-1',
    isFulfillmentAdmin: true,
    workspace: 'full' as const,
    addressStorageEnabled: true,
    onClose: noOp,
    authHeaders: { Authorization: 'Bearer token' },
    detail: {
      id: 'request-1',
      document_number: 'PRI-1',
      warehouse_id: 'warehouse-1',
      status: 'sorting',
      operation_type: 'inbound' as const,
      planned_delivery_date: null,
      planned_box_count: null,
      actual_box_count: null,
      boxes_discrepancy: false,
      has_discrepancy: false,
      distribution_completed_at: null,
      boxes: [],
      cargo_places: [],
      lines: [],
    },
    locations: [],
    newLocationCode: 'CELL-1',
    catalog: null,
    distLines: [],
    defaultPutawayBoxId: '',
    isOzonReturn: false,
    displayDocumentNumber: 'ПРИЕМ-1',
    actualInputRefs: { current: {} },
    loadDetailSeq: { current: 0 },
    actualDraftRef: { current: {} },
  }

  return new Proxy(values, {
    get(target, property, receiver) {
      if (Reflect.has(target, property)) return Reflect.get(target, property, receiver)
      if (typeof property === 'string' && property.startsWith('set')) return noOp
      return undefined
    },
  }) as unknown as FfInboundRequestDataContext
}

describe('TC-NEW-A3-003 inbound data runtime network parity', () => {
  beforeEach(() => {
    hookRuntime.effects.length = 0
  })

  it('executes the baseline locations load, location create, reload and cell-hints routes exactly', async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(okJson([]))
      .mockResolvedValueOnce(okJson({ id: 'location-1', code: 'CELL-1', warehouse_id: 'warehouse-1', barcode: 'L-1' }))
      .mockResolvedValueOnce(okJson([]))
      .mockResolvedValueOnce(okJson([]))
    vi.stubGlobal('fetch', fetchMock)

    const data = useFfInboundRequestData(makeDataContext())
    await data.loadLocations('warehouse-1')
    await data.createWarehouseLocation()
    await data.loadCellHints('product-1')

    expect(fetchMock).toHaveBeenCalledTimes(4)
    expect(fetchMock.mock.calls.map(([url, init]) => ({ url, method: init?.method ?? 'GET' }))).toEqual([
      {
        url: '/api/warehouses/warehouse-1/locations?exclude_sorting_zone=true',
        method: 'GET',
      },
      { url: '/api/warehouses/warehouse-1/locations', method: 'POST' },
      {
        url: '/api/warehouses/warehouse-1/locations?exclude_sorting_zone=true',
        method: 'GET',
      },
      {
        url: '/api/operations/inventory-balances/locations-by-product?product_id=product-1&warehouse_id=warehouse-1',
        method: 'GET',
      },
    ])
    expect(fetchMock.mock.calls.some(([url]) => String(url).includes('/ctx.'))).toBe(false)
  })
})
