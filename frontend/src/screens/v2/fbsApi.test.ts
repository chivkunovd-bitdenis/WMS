import { afterEach, describe, expect, it, vi } from 'vitest'

import {
  assignFbsPackingBoxOrders,
  confirmFbsManualPick,
  createFbsPackingBoxes,
  createFbsSupplyFromOrders,
  deleteFbsCargoPlaces,
  deleteFbsPackingBox,
  deliverFbsSupply,
  deliverFbsSupplyWithPreflightRefresh,
  FbsApiError,
  FbsRequestTimeoutError,
  fetchFbsPackingBoxes,
  fetchFbsPrintPreviewBlobs,
  fetchFbsWorklist,
  finishFbsSupplyLocally,
  resolveFbsPickLocation,
  retryFbsSupplyQr,
  scanFbsOrderMetadata,
  scanFbsPickLocation,
  scanFbsPickProduct,
  startFbsSupplyWork,
  unassignFbsPackingBoxOrders,
  type FbsPrintAsset,
} from './fbsApi'

const authHeaders = (token: string) => ({ Authorization: `Bearer ${token}` })

afterEach(() => {
  vi.unstubAllGlobals()
  vi.useRealTimers()
})

describe('FBS API client', () => {
  const workspaceResponse = () =>
    new Response(
      JSON.stringify({
        supply: { id: 'supply-1', delivery_type: 'warehouse_sc', operator_finished_at: null },
        stage: 'packing',
        orders: [],
        packing_boxes: [],
        unassigned_order_ids: [],
      }),
      { status: 200, headers: { 'Content-Type': 'application/json' } },
    )
  it('keeps the structured FBS error envelope for the UI', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(
        new Response(
          JSON.stringify({
            detail: {
              code: 'stale_preflight',
              message: 'Чек-лист устарел — обновите preflight.',
              context: { expected_version: 'v2' },
              retryable: true,
            },
          }),
          { status: 409, headers: { 'Content-Type': 'application/json' } },
        ),
      ),
    )

    await expect(fetchFbsWorklist('token', authHeaders)).rejects.toMatchObject({
      name: 'FbsApiError',
      code: 'stale_preflight',
      context: { expected_version: 'v2' },
      retryable: true,
      status: 409,
    } satisfies Partial<FbsApiError>)
  })

  it('sends deliver preflight confirmation and returns the canonical workspace', async () => {
    const workspace = {
      supply: { id: 'supply-1', status: 'in_delivery' },
      stage: 'tracking',
      orders: [],
    }
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify(workspace), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      }),
    )
    vi.stubGlobal('fetch', fetchMock)

    const result = await deliverFbsSupply('token', authHeaders, 'supply-1', {
      idempotency_key: 'deliver-1',
      confirmed_preflight_version: 'v1',
    })

    expect(result).toEqual(workspace)
    expect(result.supply.status).toBe('in_delivery')
    expect(result.stage).toBe('tracking')

    expect(fetchMock).toHaveBeenCalledWith('/api/operations/fbs-supplies/supply-1/deliver', expect.objectContaining({
      method: 'POST',
      headers: {
        Authorization: 'Bearer token',
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        idempotency_key: 'deliver-1',
        confirmed_preflight_version: 'v1',
      }),
      signal: expect.any(AbortSignal),
    }))
  })

  it('calls retry-supply-qr without deliver body and returns workspace', async () => {
    const workspace = {
      supply: {
        id: 'supply-1',
        status: 'in_delivery',
        barcode_asset: { kind: 'supply_qr', status: 'ready', preview_url: '/qr.png' },
      },
      stage: 'tracking',
      orders: [],
    }
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify(workspace), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      }),
    )
    vi.stubGlobal('fetch', fetchMock)

    const result = await retryFbsSupplyQr('token', authHeaders, 'supply-1')

    expect(result.supply.barcode_asset?.status).toBe('ready')
    expect(fetchMock).toHaveBeenCalledWith(
      '/api/operations/fbs-supplies/supply-1/retry-supply-qr',
      expect.objectContaining({
        method: 'POST',
        headers: { Authorization: 'Bearer token' },
        signal: expect.any(AbortSignal),
      }),
    )
  })

  it('calls delete cargo-places with wb ids and idempotency key', async () => {
    const cargoPlaces = [{ id: 'place-1', wb_trbx_id: 'MOCK-TRBX-1', qr_asset: null }]
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ cargo_places: cargoPlaces }), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      }),
    )
    vi.stubGlobal('fetch', fetchMock)

    const result = await deleteFbsCargoPlaces('token', authHeaders, 'supply-1', {
      wb_trbx_ids: ['MOCK-TRBX-1'],
      idempotency_key: 'delete-1',
    })

    expect(result).toEqual(cargoPlaces)
    expect(fetchMock).toHaveBeenCalledWith('/api/operations/fbs-supplies/supply-1/cargo-places', {
      method: 'DELETE',
      headers: {
        Authorization: 'Bearer token',
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        wb_trbx_ids: ['MOCK-TRBX-1'],
        idempotency_key: 'delete-1',
      }),
    })
  })

  it('refreshes a stale delivery preflight without silently delivering again', async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(
        new Response(
          JSON.stringify({
            detail: {
              code: 'stale_preflight',
              message: 'Чек-лист устарел.',
              context: { current_version: 'v2' },
              retryable: false,
            },
          }),
          { status: 409, headers: { 'Content-Type': 'application/json' } },
        ),
      )
      .mockResolvedValueOnce(
        new Response(
          JSON.stringify({ can_deliver: true, version: 'v2', checked_at: '2026-08-05T20:00:00Z', checks: [] }),
          { status: 200, headers: { 'Content-Type': 'application/json' } },
        ),
      )
    vi.stubGlobal('fetch', fetchMock)

    const result = await deliverFbsSupplyWithPreflightRefresh('token', authHeaders, 'supply-1', {
      idempotency_key: 'deliver-1',
      confirmed_preflight_version: 'v1',
    })

    expect(result).toEqual({
      kind: 'stale_preflight',
      preflight: { can_deliver: true, version: 'v2', checked_at: '2026-08-05T20:00:00Z', checks: [] },
    })
    expect(fetchMock).toHaveBeenCalledTimes(2)
    expect(fetchMock.mock.calls[0][0]).toBe('/api/operations/fbs-supplies/supply-1/deliver')
    expect(fetchMock.mock.calls[1]).toEqual([
      '/api/operations/fbs-supplies/supply-1/delivery-preflight',
      expect.objectContaining({
        method: 'POST',
        headers: { Authorization: 'Bearer token' },
        signal: expect.any(AbortSignal),
      }),
    ])
  })

  it('returns successful delivery without an unnecessary preflight refresh', async () => {
    const workspace = { supply: { id: 'supply-1' }, stage: 'tracking', orders: [] }
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify(workspace), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      }),
    )
    vi.stubGlobal('fetch', fetchMock)

    const result = await deliverFbsSupplyWithPreflightRefresh('token', authHeaders, 'supply-1', {
      idempotency_key: 'deliver-1',
      confirmed_preflight_version: 'v1',
    })

    expect(result).toEqual({ kind: 'delivered', workspace })
    expect(fetchMock).toHaveBeenCalledTimes(1)
  })

  it('does not disguise a non-stale delivery error as a refreshed preflight', async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(
        JSON.stringify({
          detail: {
            code: 'wb_timeout',
            message: 'WB не ответил.',
            context: null,
            retryable: true,
          },
        }),
        { status: 504, headers: { 'Content-Type': 'application/json' } },
      ),
    )
    vi.stubGlobal('fetch', fetchMock)

    await expect(
      deliverFbsSupplyWithPreflightRefresh('token', authHeaders, 'supply-1', {
        idempotency_key: 'deliver-1',
        confirmed_preflight_version: 'v1',
      }),
    ).rejects.toMatchObject({ code: 'wb_timeout', retryable: true, status: 504 })
    expect(fetchMock).toHaveBeenCalledTimes(1)
  })

  it('keeps printable preview blobs when another asset fails', async () => {
    const asset = (id: string, previewUrl: string | null): FbsPrintAsset => ({
      id,
      kind: 'order_sticker',
      status: 'ready',
      preview_url: previewUrl,
      content_type: 'image/png',
      width_mm: 58,
      height_mm: 40,
      download_url: null,
      checksum: null,
      applied_at: null,
      error: null,
    })
    const assets: FbsPrintAsset[] = [
      asset('asset-ok', '/ok.png'),
      asset('asset-failed', '/failed.png'),
      asset('asset-missing', null),
    ]
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(new Response(new Blob(['png']), { status: 200 }))
      .mockResolvedValueOnce(new Response('', { status: 502 }))
    vi.stubGlobal('fetch', fetchMock)

    const result = await fetchFbsPrintPreviewBlobs('token', authHeaders, assets)

    expect(result.ready).toHaveLength(1)
    expect(result.ready[0].asset.id).toBe('asset-ok')
    expect(await result.ready[0].blob.text()).toBe('png')
    expect(result.errors.map((item) => [item.asset.id, item.message])).toEqual([
      ['asset-failed', 'Предпросмотр недоступен (502).'],
      ['asset-missing', 'У файла нет ссылки на предпросмотр.'],
    ])
    expect(fetchMock).toHaveBeenCalledTimes(2)
  })

  it('times out start-work and aborts a fetch that never settles', async () => {
    vi.useFakeTimers()
    let requestSignal: AbortSignal | undefined
    const fetchMock = vi.fn((_input: RequestInfo | URL, init?: RequestInit) => {
      requestSignal = init?.signal ?? undefined
      return new Promise<Response>(() => undefined)
    })
    vi.stubGlobal('fetch', fetchMock)
    const pending = startFbsSupplyWork('token', authHeaders, 'supply-1', { timeoutMs: 250 })
    const assertion = expect(pending).rejects.toMatchObject({
      name: 'FbsRequestTimeoutError',
      code: 'request_timeout',
      retryable: true,
      status: 0,
      timeoutMs: 250,
    } satisfies Partial<FbsRequestTimeoutError>)
    await vi.advanceTimersByTimeAsync(250)
    await assertion
    expect(requestSignal?.aborted).toBe(true)
  })

  it('keeps the existing start-work call compatible and clears its timeout after success', async () => {
    vi.useFakeTimers()
    const workspace = { supply: { id: 'supply-1' }, stage: 'picking', orders: [] }
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(
      new Response(JSON.stringify(workspace), { status: 200, headers: { 'Content-Type': 'application/json' } }),
    ))
    await expect(startFbsSupplyWork('token', authHeaders, 'supply-1')).resolves.toEqual(workspace)
    expect(vi.getTimerCount()).toBe(0)
  })

  it('times out supply creation, scanner flow and mandatory marking as retryable operations', async () => {
    vi.useFakeTimers()
    const requestSignals: AbortSignal[] = []
    const fetchMock = vi.fn((_input: RequestInfo | URL, init?: RequestInit) => {
      if (init?.signal) requestSignals.push(init.signal)
      return new Promise<Response>(() => undefined)
    })
    vi.stubGlobal('fetch', fetchMock)

    const operations: Array<() => Promise<unknown>> = [
      () => createFbsSupplyFromOrders('token', authHeaders, {
        name: 'FBS test',
        order_ids: ['order-1'],
        planned_delivery_type: 'warehouse_sc',
        planned_destination: null,
        idempotency_key: 'create-1',
      }, { timeoutMs: 75 }),
      () => scanFbsPickLocation('token', authHeaders, 'supply-1', 'A-01', { timeoutMs: 75 }),
      () => scanFbsPickProduct('token', authHeaders, 'supply-1', {
        location_id: 'location-1',
        product_barcode: '2000000000011',
        idempotency_key: 'pick-1',
      }, { timeoutMs: 75 }),
      () => scanFbsOrderMetadata('token', authHeaders, 'order-1', {
        kind: 'sgtin',
        raw_value: '010460000000000021ABC',
        idempotency_key: 'marking-1',
      }, { timeoutMs: 75 }),
    ]

    for (const operation of operations) {
      const pending = operation()
      const assertion = expect(pending).rejects.toMatchObject({
        code: 'request_timeout',
        retryable: true,
        status: 0,
        timeoutMs: 75,
      } satisfies Partial<FbsRequestTimeoutError>)
      await vi.advanceTimersByTimeAsync(75)
      await assertion
    }

    expect(fetchMock).toHaveBeenCalledTimes(operations.length)
    expect(requestSignals).toHaveLength(operations.length)
    expect(requestSignals.every((signal) => signal.aborted)).toBe(true)
  })

  it('times out a packing-box mutation and exposes it as retryable', async () => {
    vi.useFakeTimers()
    let requestSignal: AbortSignal | undefined
    vi.stubGlobal('fetch', vi.fn((_input: RequestInfo | URL, init?: RequestInit) => {
      requestSignal = init?.signal ?? undefined
      return new Promise<Response>(() => undefined)
    }))

    const pending = createFbsPackingBoxes(
      'token',
      authHeaders,
      'supply-1',
      { count: 2, idempotency_key: 'boxes-1' },
      { timeoutMs: 120 },
    )
    const assertion = expect(pending).rejects.toMatchObject({
      name: 'FbsRequestTimeoutError',
      code: 'request_timeout',
      retryable: true,
      status: 0,
      context: { timeout_ms: 120 },
      timeoutMs: 120,
    } satisfies Partial<FbsRequestTimeoutError>)

    await vi.advanceTimersByTimeAsync(120)
    await assertion
    expect(requestSignal?.aborted).toBe(true)
  })

  it('times out delivery instead of leaving the workspace permanently busy', async () => {
    vi.useFakeTimers()
    let requestSignal: AbortSignal | undefined
    vi.stubGlobal('fetch', vi.fn((_input: RequestInfo | URL, init?: RequestInit) => {
      requestSignal = init?.signal ?? undefined
      return new Promise<Response>(() => undefined)
    }))

    const pending = deliverFbsSupply(
      'token',
      authHeaders,
      'supply-1',
      { idempotency_key: 'deliver-1', confirmed_preflight_version: 'v1' },
      { timeoutMs: 180 },
    )
    const assertion = expect(pending).rejects.toMatchObject({
      name: 'FbsRequestTimeoutError',
      code: 'request_timeout',
      retryable: true,
      status: 0,
      timeoutMs: 180,
    } satisfies Partial<FbsRequestTimeoutError>)

    await vi.advanceTimersByTimeAsync(180)
    await assertion
    expect(requestSignal?.aborted).toBe(true)
  })

  it('resolves an explicitly selected pick location without requiring a scanner barcode', async () => {
    const location = { id: 'location-1', code: 'A-01', warehouse_id: 'warehouse-1', warehouse_name: 'Основной склад', expected_products: [] }
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify(location), { status: 200, headers: { 'Content-Type': 'application/json' } }),
    )
    vi.stubGlobal('fetch', fetchMock)
    await expect(resolveFbsPickLocation('token', authHeaders, 'supply-1', { location_id: 'location-1' })).resolves.toEqual(location)
    expect(fetchMock).toHaveBeenCalledWith('/api/operations/fbs-supplies/supply-1/pick/resolve-location', expect.objectContaining({
      method: 'POST',
      headers: { Authorization: 'Bearer token', 'Content-Type': 'application/json' },
      body: JSON.stringify({ location_id: 'location-1' }),
      signal: expect.any(AbortSignal),
    }))
  })

  it('confirms a manual pick by explicit location, product and order ids', async () => {
    const fetchMock = vi.fn().mockResolvedValue(workspaceResponse())
    vi.stubGlobal('fetch', fetchMock)
    const body = { location_id: 'location-1', product_id: 'product-1', order_id: 'order-1', idempotency_key: 'pick-1' }
    const result = await confirmFbsManualPick('token', authHeaders, 'supply-1', body)
    expect(result.stage).toBe('packing')
    expect(fetchMock.mock.calls[0][0]).toBe('/api/operations/fbs-supplies/supply-1/pick/confirm-product')
  })

  it('uses the canonical workspace response for packing-box list and mutations', async () => {
    const fetchMock = vi.fn().mockImplementation(() => Promise.resolve(workspaceResponse()))
    vi.stubGlobal('fetch', fetchMock)
    await fetchFbsPackingBoxes('token', authHeaders, 'supply-1')
    await createFbsPackingBoxes('token', authHeaders, 'supply-1', { count: 2, idempotency_key: 'boxes-1' })
    await assignFbsPackingBoxOrders('token', authHeaders, 'supply-1', 'box-1', { order_ids: ['order-1'], idempotency_key: 'assign-1' })
    await unassignFbsPackingBoxOrders('token', authHeaders, 'supply-1', 'box-1', { order_ids: ['order-1'], idempotency_key: 'unassign-1' })
    await deleteFbsPackingBox('token', authHeaders, 'supply-1', 'box-1', 'delete-1')
    expect(fetchMock.mock.calls.map((call) => [call[0], call[1]?.method ?? 'GET'])).toEqual([
      ['/api/operations/fbs-supplies/supply-1/packing-boxes', 'GET'],
      ['/api/operations/fbs-supplies/supply-1/packing-boxes', 'POST'],
      ['/api/operations/fbs-supplies/supply-1/packing-boxes/box-1/orders', 'PUT'],
      ['/api/operations/fbs-supplies/supply-1/packing-boxes/box-1/orders', 'DELETE'],
      ['/api/operations/fbs-supplies/supply-1/packing-boxes/box-1', 'DELETE'],
    ])
  })

  it('finishes local operator work separately from electronic WB delivery', async () => {
    const workspace = { supply: { id: 'supply-1', operator_finished_at: '2026-08-06T09:30:00Z' }, stage: 'tracking', orders: [] }
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify(workspace), { status: 200, headers: { 'Content-Type': 'application/json' } }),
    )
    vi.stubGlobal('fetch', fetchMock)
    const result = await finishFbsSupplyLocally('token', authHeaders, 'supply-1', 'finish-1')
    expect(result.stage).toBe('tracking')
    expect(fetchMock).toHaveBeenCalledWith('/api/operations/fbs-supplies/supply-1/finish', expect.objectContaining({
      method: 'POST',
      headers: { Authorization: 'Bearer token', 'Content-Type': 'application/json' },
      body: JSON.stringify({ idempotency_key: 'finish-1' }),
      signal: expect.any(AbortSignal),
    }))
  })

  it('preserves the route-specific print blocker when local finish is not ready', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ detail: { code: 'local_finish_not_ready', message: 'Сначала откройте QR.', context: { required_print: 'supply_qr', asset_id: 'asset-1' }, retryable: true } }), { status: 409, headers: { 'Content-Type': 'application/json' } }),
    ))
    await expect(finishFbsSupplyLocally('token', authHeaders, 'supply-1', 'finish-1')).rejects.toMatchObject({
      code: 'local_finish_not_ready', retryable: true, status: 409,
      context: { required_print: 'supply_qr', asset_id: 'asset-1' },
    })
  })
})
