import { afterEach, describe, expect, it, vi } from 'vitest'

import { SameOriginSellerWithdrawalApi, withdrawalErrorMessage } from './sellerKizWithdrawalApi'

const emptyOperation = {
  operation_id: 'operation-id',
  state: 'auth_pending',
  attempt: 1,
  integration_gate: null,
  reauth_required: false,
  certificate_thumbprint: null,
  auth_challenge: null,
  documents: [],
  auth_error: null,
  items: [],
}

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('SameOriginSellerWithdrawalApi', () => {
  it('uses only the self registry contract and server pagination', async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ rows: [], total: 0 }), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      }),
    )
    vi.stubGlobal('fetch', fetchMock)
    const api = new SameOriginSellerWithdrawalApi('seller-token')

    await api.list({
      dateFrom: '2026-09-18',
      dateTo: '2026-09-24',
      search: 'футболка',
      productId: 'product-id',
      onlyNotWithdrawn: true,
      limit: 250,
      offset: 250,
    })

    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit]
    expect(url).toContain('/api/operations/marking-codes/self/withdrawals?')
    expect(url).toContain('product_id=product-id')
    expect(url).toContain('limit=250')
    expect(url).toContain('offset=250')
    expect(new Headers(init.headers).get('Authorization')).toBe('Bearer seller-token')
  })

  it('binds operation creation to row ids, stable request id and certificate metadata', async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify(emptyOperation), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      }),
    )
    vi.stubGlobal('fetch', fetchMock)
    const api = new SameOriginSellerWithdrawalApi('seller-token')

    await api.createOperation({
      rowIds: ['row-1'],
      clientRequestId: 'request-1',
      certificate: {
        thumbprint: 'AABB',
        expires_at: '2027-01-01T00:00:00Z',
        subject: 'CN=Seller',
      },
    })

    const [, init] = fetchMock.mock.calls[0] as [string, RequestInit]
    expect(JSON.parse(String(init.body))).toEqual({
      row_ids: ['row-1'],
      client_request_id: 'request-1',
      certificate: {
        thumbprint: 'AABB',
        expires_at: '2027-01-01T00:00:00Z',
        subject: 'CN=Seller',
      },
    })
  })

  it('sends every document signature with immutable payload hash and selected certificate', async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify(emptyOperation), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      }),
    )
    vi.stubGlobal('fetch', fetchMock)
    const api = new SameOriginSellerWithdrawalApi('seller-token')

    await api.submitDocumentSignatures({
      operationId: 'operation-id',
      documents: [{
        document_id: 'document-id',
        payload_sha256: 'a'.repeat(64),
        thumbprint: 'AABB',
        signature: 'c2lnbmF0dXJl',
      }],
    })

    const [, init] = fetchMock.mock.calls[0] as [string, RequestInit]
    expect(JSON.parse(String(init.body))).toEqual({
      documents: [{
        document_id: 'document-id',
        payload_sha256: 'a'.repeat(64),
        thumbprint: 'AABB',
        signature: 'c2lnbmF0dXJl',
      }],
    })
  })

  it('requests reauthentication for the durable operation with public certificate metadata only', async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({
        ...emptyOperation,
        reauth_required: true,
        certificate_thumbprint: 'AABB',
      }), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      }),
    )
    vi.stubGlobal('fetch', fetchMock)
    const api = new SameOriginSellerWithdrawalApi('seller-token')

    await api.requestReauthChallenge({
      operationId: 'operation-id',
      certificate: {
        thumbprint: 'AABB',
        expires_at: '2027-01-01T00:00:00Z',
        subject: 'CN=Seller',
        issuer: 'CN=Issuer',
      },
    })

    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit]
    expect(url).toContain('/operations/operation-id/reauth-challenge')
    expect(JSON.parse(String(init.body))).toEqual({
      certificate: {
        thumbprint: 'AABB',
        expires_at: '2027-01-01T00:00:00Z',
        subject: 'CN=Seller',
        issuer: 'CN=Issuer',
      },
    })
  })

  it('maps the fail-closed production-submit gate to a human message', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ detail: { code: 'WITHDRAWAL_PRODUCTION_SUBMIT_DISABLED' } }), {
        status: 409,
        headers: { 'Content-Type': 'application/json' },
      }),
    ))
    const api = new SameOriginSellerWithdrawalApi('seller-token')

    await expect(api.submitAuthSignature({
      operationId: 'operation-id',
      thumbprint: 'AABB',
      signature: 'c2lnbmF0dXJl',
      challengeUuid: 'challenge-id',
      expectedAttempt: 1,
    })).rejects.toMatchObject({
      code: 'WITHDRAWAL_PRODUCTION_SUBMIT_DISABLED',
      status: 409,
    })
  })
})

describe('withdrawalErrorMessage', () => {
  it('shows CRPT document errors and commonErrors returned by the backend', () => {
    expect(withdrawalErrorMessage({
      source: 'crpt',
      scope: 'document',
      status: 'CHECKED_NOT_OK',
      errors: [{ code: 'E42', error: 'Фактическая ошибка документа' }],
      commonErrors: ['Ошибка общая'],
    })).toBe('Фактическая ошибка документа · Ошибка общая')
  })

  it('normalizes snake-case common errors and message-shaped entries', () => {
    expect(withdrawalErrorMessage({
      errors: [{ code: 'WRONG_COST', message: 'Цена продажи не указана' }],
      common_errors: [{ code: 'DOC_REJECTED', description: 'Документ отклонён' }],
    })).toBe('Цена продажи не указана · Документ отклонён')
  })

  it('uses a provider code when no safe message was returned', () => {
    expect(withdrawalErrorMessage({ errors: [{ code: 'E42' }] })).toBe('E42')
  })

  it('shows the factual True API auth error_message', () => {
    expect(withdrawalErrorMessage({
      code: 'AUTH_403',
      error_message: 'У участника нет права на создание документа',
    })).toBe('У участника нет права на создание документа')
  })

  it('falls back to a human terminal status without exposing unknown object fields', () => {
    expect(withdrawalErrorMessage({
      status: 'PROCESSING_ERROR',
      errors: [{ authorization: 'Bearer secret-value' }],
    })).toBe('Честный знак не смог обработать документ.')
  })
})
