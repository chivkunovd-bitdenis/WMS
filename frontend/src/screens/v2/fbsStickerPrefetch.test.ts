import { beforeEach, describe, expect, it, vi } from 'vitest'
import { ensureFbsStickers } from './fbsStickerPrefetch'
import type { FbsWorkspace } from './fbsApi'

const { fetchFbsPrintBatch, fetchFbsWorkspace } = vi.hoisted(() => ({
  fetchFbsPrintBatch: vi.fn(),
  fetchFbsWorkspace: vi.fn(),
}))
vi.mock('./fbsApi', () => ({ fetchFbsPrintBatch, fetchFbsWorkspace }))

function snapshot(
  marketplace: 'wb' | 'ozon' = 'wb',
  orders: Array<{ id: string; status: string; sticker: { code: string | null } }> = [
    { id: 'order-a', status: 'assembling', sticker: { code: null } },
  ],
): FbsWorkspace {
  return {
    supply: { id: 'supply-a', marketplace },
    orders,
  } as unknown as FbsWorkspace
}

function deferred<T>() {
  let resolve!: (value: T) => void
  let reject!: (cause: Error) => void
  const promise = new Promise<T>((resolvePromise, rejectPromise) => {
    resolve = resolvePromise
    reject = rejectPromise
  })
  return { promise, resolve, reject }
}

describe('WMS-666 shared sticker preparation', () => {
  beforeEach(() => {
    fetchFbsPrintBatch.mockReset()
    fetchFbsWorkspace.mockReset()
  })

  it('coalesces a simultaneous entry and print request into one provider batch', async () => {
    const batch = deferred<{ order_errors: Array<{ message: string }> }>()
    const refreshed = snapshot('wb', [{
      id: 'order-a', status: 'assembling', sticker: { code: 'QR-1' },
    }])
    fetchFbsPrintBatch.mockReturnValue(batch.promise)
    fetchFbsWorkspace.mockResolvedValue(refreshed)

    const opening = ensureFbsStickers('token', () => ({}), snapshot())
    const printing = ensureFbsStickers('token', () => ({}), snapshot())
    expect(printing).toBe(opening)
    batch.resolve({ order_errors: [] })

    await expect(Promise.all([opening, printing])).resolves.toEqual([
      { workspace: refreshed, errorMessage: null },
      { workspace: refreshed, errorMessage: null },
    ])
    expect(fetchFbsPrintBatch).toHaveBeenCalledTimes(1)
    expect(fetchFbsPrintBatch).toHaveBeenCalledWith('token', expect.any(Function), 'supply-a', {
      kind: 'order_sticker', order_ids: ['order-a'], retry_missing: true,
    })
  })

  it('releases a failed request so the operator retry can issue a fresh batch', async () => {
    fetchFbsPrintBatch.mockRejectedValueOnce(new Error('temporary outage'))
      .mockResolvedValueOnce({ order_errors: [] })
    fetchFbsWorkspace.mockResolvedValue(snapshot('wb', [{
      id: 'order-a', status: 'assembling', sticker: { code: 'QR-1' },
    }]))

    await expect(ensureFbsStickers('token', () => ({}), snapshot())).rejects.toThrow('temporary outage')
    await expect(ensureFbsStickers('token', () => ({}), snapshot()))
      .resolves.toMatchObject({ errorMessage: null })
    expect(fetchFbsPrintBatch).toHaveBeenCalledTimes(2)
  })

  it('limits an entry prefetch to the still-unattempted order IDs', async () => {
    fetchFbsPrintBatch.mockResolvedValue({ order_errors: [] })
    fetchFbsWorkspace.mockResolvedValue(snapshot('wb', []))
    const current = snapshot('wb', [
      { id: 'already-attempted', status: 'assembling', sticker: { code: null } },
      { id: 'new-order', status: 'assembling', sticker: { code: null } },
    ])

    await ensureFbsStickers('token', () => ({}), current, ['new-order'])

    expect(fetchFbsPrintBatch).toHaveBeenCalledWith('token', expect.any(Function), 'supply-a', {
      kind: 'order_sticker', order_ids: ['new-order'], retry_missing: true,
    })
  })

  it.each([true, false])('requests newly added missing IDs after an earlier subset finishes (fresh response includes B: %s)', async (freshIncludesB) => {
    const batchA = deferred<{ order_errors: Array<{ message: string }> }>()
    fetchFbsPrintBatch.mockReturnValueOnce(batchA.promise).mockResolvedValueOnce({ order_errors: [] })
    fetchFbsWorkspace.mockResolvedValue(snapshot('wb', [
      { id: 'order-a', status: 'assembling', sticker: { code: null } },
      ...(freshIncludesB ? [{ id: 'order-b', status: 'assembling', sticker: { code: null } }] : []),
    ]))
    const current = snapshot('wb', [
      { id: 'order-a', status: 'assembling', sticker: { code: null } },
      { id: 'order-b', status: 'assembling', sticker: { code: null } },
    ])

    const first = ensureFbsStickers('token', () => ({}), current, ['order-a'])
    const second = ensureFbsStickers('token', () => ({}), current, ['order-b'])
    expect(fetchFbsPrintBatch).toHaveBeenCalledTimes(1)
    batchA.resolve({ order_errors: [] })
    await Promise.all([first, second])

    expect(fetchFbsPrintBatch).toHaveBeenCalledTimes(2)
    expect(fetchFbsPrintBatch.mock.calls.map(call => call[3].order_ids)).toEqual([['order-a'], ['order-b']])
  })

  it.each([
    ['Ozon', snapshot('ozon')],
    ['no missing stickers', snapshot('wb', [{
      id: 'order-a', status: 'assembling', sticker: { code: 'QR-1' },
    }])],
    ['cancelled orders', snapshot('wb', [{
      id: 'order-cancelled', status: 'cancelled', sticker: { code: null },
    }])],
  ])('does not request provider stickers for %s', async (_label, current) => {
    await ensureFbsStickers('token', () => ({}), current)
    expect(fetchFbsPrintBatch).not.toHaveBeenCalled()
    expect(fetchFbsWorkspace).not.toHaveBeenCalled()
  })
})
