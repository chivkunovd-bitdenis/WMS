import { describe, expect, it, vi } from 'vitest'
import { pendingPlacement, placementStorageKey, rememberPlacement, sendPlacement } from './pendingPlacement'

const body = { kind: 'product', id: 'balance', cell_id: 'cell', to_id: null, qty: 1, inbound_request_id: 'document' }
function storage(): Storage {
  const data = new Map<string, string>()
  return { getItem: (key) => data.get(key) ?? null, setItem: (key, value) => { data.set(key, value) }, removeItem: (key) => { data.delete(key) }, clear: () => data.clear(), key: (i) => [...data.keys()][i] ?? null, get length() { return data.size } }
}

describe('WMS-441 confirmed web placement', () => {
  it('replays the same body after committed response loss and browser recreation; a new scan has a new id', async () => {
    const disk = storage()
    const confirmed = rememberPlacement(disk, 'scope', body)
    const receipts = new Set<string>()
    let moved = 0
    const server = async (request: typeof confirmed) => {
      // Persistence happens BEFORE HTTP.
      expect(pendingPlacement(disk, 'scope')).toEqual(request)
      if (!receipts.has(request.operation_id)) {
        receipts.add(request.operation_id); moved += request.qty
        throw new Error('response lost AFTER commit')
      }
      return new Response('{}', { status: 200 })
    }
    await expect(sendPlacement(disk, 'scope', confirmed, server)).rejects.toThrow()
    const restored = pendingPlacement(disk, 'scope')!
    expect(restored).toEqual(confirmed)
    await sendPlacement(disk, 'scope', restored, server)
    expect(moved).toBe(1)
    expect(pendingPlacement(disk, 'scope')).toBeNull()
    expect(rememberPlacement(disk, 'scope', body).operation_id).not.toBe(confirmed.operation_id)
  })
  it('keeps ambiguous and auth responses; definitive validation rejection clears only its own receipt', async () => {
    const disk = storage()
    const confirmed = rememberPlacement(disk, 'scope', body)
    for (const status of [401, 403, 408, 429, 500, 502]) {
      await sendPlacement(disk, 'scope', confirmed, async () => new Response('', { status }))
      expect(pendingPlacement(disk, 'scope')).toEqual(confirmed)
    }
    expect(() => rememberPlacement(disk, 'scope', body)).toThrow()
    await sendPlacement(disk, 'scope', confirmed, async () => new Response('', { status: 409 }))
    expect(pendingPlacement(disk, 'scope')).toBeNull()
  })
  it('separates server user and document, retains identity when token changes', () => {
    vi.stubGlobal('location', { origin: 'http://localhost:5203' })
    const token = (sub: string, expiry = 1) => `header.${btoa(JSON.stringify({ sub, exp: expiry }))}.signature`
    const key = placementStorageKey(token('a'), '/api/place', 'one')
    expect(key).toBe(placementStorageKey(token('a', 2), '/api/place', 'one'))
    expect(key).not.toBe(placementStorageKey(token('b'), '/api/place', 'one'))
    expect(key).not.toBe(placementStorageKey(token('a'), '/api/place', 'two'))
    expect(key).not.toBe(placementStorageKey(token('a'), 'http://localhost:5204/api/place', 'one'))
    vi.unstubAllGlobals()
  })
  it('does not send when durable save fails', () => {
    const disk = storage()
    disk.setItem = () => { throw new Error('storage unavailable') }
    expect(() => rememberPlacement(disk, 'scope', body)).toThrow('storage unavailable')
  })
})
