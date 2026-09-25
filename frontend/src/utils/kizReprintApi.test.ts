import { afterEach, describe, expect, it, vi } from 'vitest'

import {
  kizReprintErrorMessage,
  loadKizReprints,
  mergeKizReprintRow,
  saveKizReprint,
  type KizReprintRow,
} from './kizReprintApi'

const GS = '\x1d'
const KIZ = `010460000000000121SERIAL${GS}91ABCD${GS}92${'X'.repeat(44)}`

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('KIZ reprint history API', () => {
  it('loads the selected seller history without rewriting a KIZ with GS', async () => {
    const row: KizReprintRow = { id: 'r-1', seller_id: 'seller 1', kiz: KIZ, created_at: '2026-09-21T00:00:00Z' }
    const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify({ rows: [row] }), { status: 200 }))
    vi.stubGlobal('fetch', fetchMock)

    await expect(loadKizReprints('token', 'seller 1')).resolves.toEqual([row])
    expect(fetchMock).toHaveBeenCalledWith(
      '/api/operations/kiz-reprints?seller_id=seller%201',
      { headers: { Authorization: 'Bearer token' } },
    )
  })

  it('sends the exact KIZ and an idempotency key when scanning', async () => {
    const row: KizReprintRow = { id: 'r-2', seller_id: 'seller-1', kiz: KIZ, created_at: '2026-09-21T00:00:00Z', replayed: false }
    const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify(row), { status: 201 }))
    vi.stubGlobal('fetch', fetchMock)

    await expect(saveKizReprint('token', { sellerId: 'seller-1', kiz: KIZ, idempotencyKey: 'scan-1' })).resolves.toEqual(row)
    const request = fetchMock.mock.calls[0]?.[1] as RequestInit
    expect(JSON.parse(String(request.body))).toEqual({
      seller_id: 'seller-1', kiz: KIZ, idempotency_key: 'scan-1',
    })
  })

  it('keeps persisted history stable on a replay and turns API errors into an operator action', () => {
    const row: KizReprintRow = { id: 'r-3', seller_id: 'seller-1', kiz: KIZ, created_at: '2026-09-21T00:00:00Z', replayed: true }
    expect(mergeKizReprintRow([row], row)).toEqual([row])
    expect(kizReprintErrorMessage('not_a_kiz')).toContain('Отсканируйте')
    expect(kizReprintErrorMessage('forbidden')).toContain('Нет доступа')
  })
})
