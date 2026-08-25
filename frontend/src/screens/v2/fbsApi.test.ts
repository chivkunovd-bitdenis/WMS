import { afterEach, describe, expect, it, vi } from 'vitest'

import {
  deleteFbsCargoPlaces,
  deliverFbsSupply,
  FbsApiError,
  fetchFbsWorklist,
  retryFbsSupplyQr,
  runFbsOrdersSync,
  validateFbsKiz,
} from './fbsApi'
import { orderStatusForChip } from './fbsUx'

const authHeaders = (token: string) => ({ Authorization: `Bearer ${token}` })

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('FBS API client', () => {
  it('keeps the original unknown Ozon status in the existing status chip', () => {
    expect(
      orderStatusForChip({
        marketplace: 'ozon',
        status: 'external_processing',
        wb_status: 'awaiting_registration',
      }),
    ).toBe('awaiting_registration')
    expect(
      orderStatusForChip({ marketplace: 'wb', status: 'external_processing', wb_status: 'waiting' }),
    ).toBe('external_processing')
  })

  it('sends marketplace identity and treats an unconnected provider as skipped', async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ id: '', status: 'skipped' }), {
        status: 202,
        headers: { 'Content-Type': 'application/json' },
      }),
    )
    vi.stubGlobal('fetch', fetchMock)

    await expect(runFbsOrdersSync('token', authHeaders, 'seller-1', 'ozon')).resolves.toMatchObject({
      skipped: true,
      ordersReceived: 0,
    })
    expect(fetchMock).toHaveBeenCalledWith('/api/operations/fbs-orders/sync', {
      method: 'POST',
      headers: {
        Authorization: 'Bearer token',
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({ seller_id: 'seller-1', marketplace: 'ozon' }),
    })
  })

  it('returns scanner normalization hints from KIZ validation', async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(
        JSON.stringify({ ok: true, hints: ['keyboard_layout', 'gs_substitute'] }),
        { status: 200, headers: { 'Content-Type': 'application/json' } },
      ),
    )
    vi.stubGlobal('fetch', fetchMock)

    const result = await validateFbsKiz('token', authHeaders, 'order-1', 'raw-scan')

    expect(result).toEqual({ ok: true, hints: ['keyboard_layout', 'gs_substitute'] })
    expect(fetchMock).toHaveBeenCalledWith('/api/operations/fbs-orders/kiz/validate', {
      method: 'POST',
      headers: {
        Authorization: 'Bearer token',
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({ order_id: 'order-1', value: 'raw-scan' }),
    })
  })

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

  it('sends direct deliver request and returns the canonical workspace', async () => {
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
    })

    expect(result).toEqual(workspace)
    expect(result.supply.status).toBe('in_delivery')
    expect(result.stage).toBe('tracking')

    expect(fetchMock).toHaveBeenCalledWith('/api/operations/fbs-supplies/supply-1/deliver', {
      method: 'POST',
      headers: {
        Authorization: 'Bearer token',
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        idempotency_key: 'deliver-1',
      }),
    })
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
      {
        method: 'POST',
        headers: { Authorization: 'Bearer token' },
      },
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
})
