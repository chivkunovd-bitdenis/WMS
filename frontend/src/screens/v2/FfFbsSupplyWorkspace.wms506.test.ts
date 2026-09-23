import { readFileSync } from 'node:fs'
import { describe, expect, it } from 'vitest'

const source = readFileSync(new URL('./FfFbsSupplyWorkspace.tsx', import.meta.url), 'utf8')

describe('WMS-506 · automatic duplicate in FBS packing scan', () => {
  it('keeps the compact switch in the existing scan bar', () => {
    const scanBar = source.slice(source.indexOf('data-testid="fbs-kiz-scan-bar"'))
    expect(scanBar).toContain('Перепечатывать ЧЗ')
    expect(scanBar).toContain('data-testid="fbs-kiz-auto-reprint-toggle"')
  })

  it('queues one full KIZ only after a new successful bind and before refresh', () => {
    const failureBranch = source.indexOf("if (outcome.status !== 'ok')")
    const print = source.indexOf('printMarkingCodeLabels([kiz], { duplicateCopies: 1 })')
    const refresh = source.indexOf('const refreshed = await load(true)')
    expect(failureBranch).toBeGreaterThan(-1)
    expect(print).toBeGreaterThan(failureBranch)
    expect(refresh).toBeGreaterThan(print)
    expect(source.slice(failureBranch, print)).toContain('outcome.newly_bound === true')
    expect(source.slice(failureBranch, print)).toContain('!outcome.bound_kiz')
    expect(source.slice(failureBranch, print)).toContain('{ ...scan, kiz: outcome.bound_kiz }')
    expect(source.slice(source.indexOf('const scan ='), failureBranch)).not.toContain('kiz: raw')
  })

  it('does not schedule an error or pending_confirmation outcome', () => {
    const failureStart = source.indexOf("if (outcome.status !== 'ok')")
    const failureBranch = source.slice(
      failureStart,
      source.indexOf('await kizAutoPrintQueueRef.current.enqueue', failureStart),
    )
    expect(failureBranch).toContain("outcome.code === 'needs_confirmation'")
    expect(failureBranch).toContain('return')
  })
})
