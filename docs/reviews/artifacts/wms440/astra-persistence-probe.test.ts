import { expect, it, vi } from 'vitest'
import { intakeMutation, readIntake, sendIntakeMutations } from './inboundDraftPersistence'

it('demonstrates permanently retained refused multi-line attempt', async () => {
  const disk = new Map<string, string>()
  vi.stubGlobal('localStorage', { getItem: (key: string) => disk.get(key) ?? null, setItem: (key: string, value: string) => disk.set(key, value) })
  const token = `header.${btoa(JSON.stringify({tenant_id:'review',sub:'reviewer'}))}.signature`
  const path = '/operations/inbound-intake-requests/review/lines'
  const first = intakeMutation('POST', path, {product_id:'a',expected_qty:1000000001,increment:true})
  const second = intakeMutation('POST', path, {product_id:'b',expected_qty:2,increment:true})
  vi.stubGlobal('fetch', vi.fn().mockImplementation(async () => new Response('{"detail":"invalid_qty"}', {status:422})))
  await expect(sendIntakeMutations(token,'review',[first,second])).rejects.toThrow()
  expect(readIntake(token,'review').pending).toEqual([first,second])
  await expect(sendIntakeMutations(token,'review')).rejects.toThrow()
  const corrected = intakeMutation('POST',path,{product_id:'a',expected_qty:1,increment:true})
  await expect(sendIntakeMutations(token,'review',[corrected])).rejects.toThrow('предыдущего запроса')
  expect(readIntake(token,'review').pending).toEqual([first,second])
  vi.unstubAllGlobals()
})
