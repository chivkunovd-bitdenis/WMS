import { describe, expect, it, vi } from 'vitest'

import type { KizReprintRow } from './kizReprintApi'
import { printKizHistory, printScannedKiz } from './kizReprintPrint'

const GS = '\x1d'
const KIZ_A = `010460000000000121SERIAL-A${GS}91ABCD${GS}92${'A'.repeat(44)}`
const KIZ_B = `010460000000000121SERIAL-B${GS}91EFGH${GS}92${'B'.repeat(44)}`

function row(id: string, kiz: string, replayed = false): KizReprintRow {
  return { id, seller_id: 'seller', kiz, created_at: '2026-09-21T00:00:00Z', replayed }
}

describe('KIZ reprint printing', () => {
  it('automatically prints precisely the persisted scanned KIZ, including GS', async () => {
    const print = vi.fn(async () => undefined)
    await expect(printScannedKiz(row('one', KIZ_A), print)).resolves.toBe(true)
    expect(print).toHaveBeenCalledWith([KIZ_A])
  })

  it('does not auto-print a replayed request', async () => {
    const print = vi.fn(async () => undefined)
    await expect(printScannedKiz(row('one', KIZ_A, true), print)).resolves.toBe(false)
    expect(print).not.toHaveBeenCalled()
  })

  it('prints an individual row or all persisted rows without creating history', async () => {
    const print = vi.fn(async () => undefined)
    await printKizHistory([row('one', KIZ_A)], print)
    await printKizHistory([row('one', KIZ_A), row('two', KIZ_B)], print)
    expect(print).toHaveBeenNthCalledWith(1, [KIZ_A])
    expect(print).toHaveBeenNthCalledWith(2, [KIZ_A, KIZ_B])
  })
})
