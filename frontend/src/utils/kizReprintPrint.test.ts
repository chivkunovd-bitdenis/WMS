import { describe, expect, it, vi } from 'vitest'

import type { KizReprintRow } from './kizReprintApi'
import { printKizHistory, printScannedKiz, startAutoKizReprintPrint } from './kizReprintPrint'

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

  it('retries a save whose response was lost, then marks success only after printing starts', async () => {
    const pending = row('lost-response', KIZ_A, true)
    const started = { ...pending, print_started_at: '2026-09-21T00:00:01Z' }
    const trace: string[] = []

    const result = await startAutoKizReprintPrint(
      pending,
      'attempt-after-retry',
      async (codes) => { trace.push(`print:${codes.join(',')}`) },
      {
        claim: async () => {
          trace.push('claim')
          return { row: pending, claimed: true }
        },
        markStarted: async () => {
          trace.push('print-started')
          return started
        },
        releaseClaim: async () => { trace.push('release') },
      },
    )

    expect(trace).toEqual(['claim', `print:${KIZ_A}`, 'print-started'])
    expect(result).toEqual({ row: started, printStarted: true })
  })

  it('does not create false success when opening the print form fails', async () => {
    const pending = row('print-failure', KIZ_A)
    const markStarted = vi.fn(async () => ({ ...pending, print_started_at: 'never' }))
    const releaseClaim = vi.fn(async () => undefined)

    await expect(startAutoKizReprintPrint(
      pending,
      'failed-attempt',
      async () => { throw new Error('print_launch_failed') },
      {
        claim: async () => ({ row: pending, claimed: true }),
        markStarted,
        releaseClaim,
      },
    )).rejects.toThrow('print_launch_failed')

    expect(markStarted).not.toHaveBeenCalled()
    expect(releaseClaim).toHaveBeenCalledOnce()
  })

  it('does not print again after the server has recorded the first launch', async () => {
    const started = { ...row('already-started', KIZ_A, true), print_started_at: '2026-09-21T00:00:01Z' }
    const print = vi.fn(async () => undefined)
    const result = await startAutoKizReprintPrint(
      started,
      'duplicate-delivery',
      print,
      {
        claim: async () => ({ row: started, claimed: false }),
        markStarted: async () => started,
        releaseClaim: async () => undefined,
      },
    )
    expect(print).not.toHaveBeenCalled()
    expect(result).toEqual({ row: started, printStarted: false })
  })
})
