import { beforeEach, describe, expect, it, vi } from 'vitest'
import { intakeMutation, intakeStorageKey, readIntake, saveIntakeTotals, sendIntakeMutations } from './inboundDraftPersistence'

const token = (tenant = 'tenant', sub = 'operator') => `header.${btoa(JSON.stringify({ tenant_id: tenant, sub }))}.signature`
const credential = token()
const path = '/operations/inbound-intake-requests/document/lines'
let disk: Map<string, string>
beforeEach(() => {
  vi.restoreAllMocks()
  disk = new Map()
  vi.stubGlobal('localStorage', { getItem: (key: string) => disk.get(key) ?? null, setItem: (key: string, value: string) => disk.set(key, value) })
})
describe('durable FF intake attempts', () => {
  it('persists exact identity and payload before sending, and replays after lost response', async () => {
    const mutation = intakeMutation('POST', path, { product_id: 'product', expected_qty: 3, increment: true })
    const fetch = vi.fn().mockImplementationOnce(async () => {
      expect(readIntake(credential, 'document').pending).toEqual([mutation])
      throw new Error('response lost')
    }).mockResolvedValue(new Response('{}'))
    vi.stubGlobal('fetch', fetch)
    await expect(sendIntakeMutations(credential, 'document', [mutation])).rejects.toThrow('response lost')
    await sendIntakeMutations(credential, 'document')
    expect(fetch.mock.calls[0][1]).toEqual(fetch.mock.calls[1][1])
    expect(readIntake(credential, 'document').pending).toBeUndefined()
  })
  it('does not repeat completed items of a catalog addition', async () => {
    const first = intakeMutation('POST', path, { product_id: 'first', expected_qty: 1, increment: true })
    const second = intakeMutation('POST', path, { product_id: 'second', expected_qty: 2, increment: true })
    const fetch = vi.fn().mockResolvedValueOnce(new Response('{}')).mockRejectedValueOnce(new Error('lost')).mockResolvedValueOnce(new Response('{}'))
    vi.stubGlobal('fetch', fetch)
    await expect(sendIntakeMutations(credential, 'document', [first, second])).rejects.toThrow()
    expect(readIntake(credential, 'document').pending).toEqual([second])
    await sendIntakeMutations(credential, 'document')
    expect(fetch.mock.calls[1][1]).toEqual(fetch.mock.calls[2][1])
    expect(fetch).toHaveBeenCalledTimes(3)
  })
  it('keeps D6 total across a refused correction and tare edit, then clears it after applied retry', async () => {
    saveIntakeTotals(credential, 'document', { line: '2' })
    vi.stubGlobal('fetch', vi.fn().mockResolvedValueOnce(new Response('{"detail":"actual_below_container_total"}', { status: 409 })).mockResolvedValue(new Response('{}')))
    const correction = intakeMutation('PATCH', `${path}/line/expected`, { expected_qty: 2 })
    await expect(sendIntakeMutations(credential, 'document', [correction])).rejects.toThrow('actual_below_container_total')
    expect(readIntake(credential, 'document')).toEqual({ totals: { line: '2' } })
    await sendIntakeMutations(credential, 'document', [intakeMutation('PUT', '/operations/inbound-intake-requests/document/boxes/box/lines/product', { quantity: 2 })])
    expect(readIntake(credential, 'document').totals).toEqual({ line: '2' })
    await sendIntakeMutations(credential, 'document', [correction])
    expect(readIntake(credential, 'document').totals).toEqual({})
  })
  it('releases a rejected first item of a picker batch for correction without replaying its untouched tail', async () => {
    const rejected = intakeMutation('POST', path, { product_id: 'wrong', expected_qty: 1, increment: true })
    const untouched = intakeMutation('POST', path, { product_id: 'other', expected_qty: 1, increment: true })
    const corrected = intakeMutation('POST', path, { product_id: 'right', expected_qty: 1, increment: true })
    const fetch = vi.fn().mockResolvedValueOnce(new Response('{"detail":"product_not_in_seller_catalog"}', { status: 422 })).mockResolvedValueOnce(new Response('{}'))
    vi.stubGlobal('fetch', fetch)
    await expect(sendIntakeMutations(credential, 'document', [rejected, untouched])).rejects.toThrow('product_not_in_seller_catalog')
    expect(readIntake(credential, 'document').pending).toBeUndefined()
    await sendIntakeMutations(credential, 'document', [corrected])
    expect(fetch).toHaveBeenCalledTimes(2)
    expect(fetch.mock.calls[1][1]).toEqual(expect.objectContaining({ body: JSON.stringify(corrected.body) }))
  })
  it('submits only the corrected rejected item after a previous picker item was applied', async () => {
    const added = intakeMutation('POST', path, { product_id: 'added', expected_qty: 3, increment: true })
    const rejected = intakeMutation('POST', path, { product_id: 'rejected', expected_qty: 1000000001, increment: true })
    const repeatedAdded = intakeMutation('POST', path, { product_id: 'added', expected_qty: 3, increment: true })
    const corrected = intakeMutation('POST', path, { product_id: 'rejected', expected_qty: 2, increment: true })
    const fetch = vi.fn().mockResolvedValueOnce(new Response('{}')).mockResolvedValueOnce(new Response('{"detail":"invalid_qty"}', { status: 422 })).mockResolvedValueOnce(new Response('{}'))
    vi.stubGlobal('fetch', fetch)
    await expect(sendIntakeMutations(credential, 'document', [added, rejected])).rejects.toThrow('invalid_qty')
    await sendIntakeMutations(credential, 'document', [repeatedAdded, corrected])
    expect(fetch).toHaveBeenCalledTimes(3)
    expect(fetch.mock.calls.map((call) => call[1].body)).toEqual([
      JSON.stringify(added.body), JSON.stringify(rejected.body), JSON.stringify(corrected.body),
    ])
    expect(readIntake(credential, 'document').pending).toBeUndefined()
  })
  it('isolates tenant, operator and document and never sends if persistence fails', async () => {
    expect(intakeStorageKey(credential, 'document')).not.toBe(intakeStorageKey(token('other'), 'document'))
    expect(intakeStorageKey(credential, 'document')).not.toBe(intakeStorageKey(token('tenant', 'other'), 'document'))
    expect(intakeStorageKey(credential, 'document')).not.toBe(intakeStorageKey(credential, 'other'))
    vi.stubGlobal('localStorage', { getItem: () => null, setItem: () => { throw new Error('disk unavailable') } })
    const fetch = vi.fn(); vi.stubGlobal('fetch', fetch)
    await expect(sendIntakeMutations(credential, 'document', [intakeMutation('POST', path, { expected_qty: 1 })])).rejects.toThrow('disk unavailable')
    expect(fetch).not.toHaveBeenCalled()
  })
  it('keeps separate UUIDs for independent physical scans and refuses replacing an unresolved attempt', async () => {
    const first = intakeMutation('POST', path, { expected_qty: 1 })
    const second = intakeMutation('POST', path, { expected_qty: 1 })
    expect(first.body?.mutation_id).not.toBe(second.body?.mutation_id)
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new Error('lost')))
    await expect(sendIntakeMutations(credential, 'document', [first])).rejects.toThrow()
    await expect(sendIntakeMutations(credential, 'document', [second])).rejects.toThrow('предыдущего запроса')
    expect(readIntake(credential, 'document').pending).toEqual([first])
  })
})
