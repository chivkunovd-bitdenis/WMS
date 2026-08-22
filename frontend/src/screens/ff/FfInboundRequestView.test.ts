import { describe, expect, it, vi } from 'vitest'
import {
  applyScannedInboundLine,
  createSerialScanQueue,
  isLatestScannedInboundLine,
  reconcileInboundScan,
} from './FfInboundRequestView'

describe('inbound scan fast path', () => {
  it('replaces the just scanned row, then moves the visible row state to the next scan', () => {
    const before = [
      { id: 'line-a', actual_qty: 1 },
      { id: 'line-b', actual_qty: 3 },
    ]

    const afterFirstScan = applyScannedInboundLine(before, { id: 'line-a', actual_qty: 2 })
    const afterSecondScan = applyScannedInboundLine(afterFirstScan, {
      id: 'line-b',
      actual_qty: 4,
    })

    expect(afterFirstScan).toEqual([
      { id: 'line-a', actual_qty: 2 },
      { id: 'line-b', actual_qty: 3 },
    ])
    expect(afterSecondScan).toEqual([
      { id: 'line-a', actual_qty: 2 },
      { id: 'line-b', actual_qty: 4 },
    ])
    expect(isLatestScannedInboundLine('line-a', 'line-a')).toBe(true)
    expect(isLatestScannedInboundLine('line-a', 'line-b')).toBe(false)
    expect(isLatestScannedInboundLine('line-b', 'line-b')).toBe(true)
  })

  it('starts reconciliation without waiting for it to finish', async () => {
    let finishReload: (() => void) | undefined
    const reload = vi.fn(
      () =>
        new Promise<void>((resolve) => {
          finishReload = resolve
        }),
    )

    reconcileInboundScan(reload)

    expect(reload).toHaveBeenCalledOnce()
    expect(finishReload).toBeDefined()
    finishReload?.()
    await Promise.resolve()
  })

  it('serializes rapid scans in their physical arrival order', async () => {
    const queue = createSerialScanQueue()
    const started: string[] = []
    let releaseFirst: (() => void) | undefined

    const first = queue(
      () =>
        new Promise<void>((resolve) => {
          started.push('first')
          releaseFirst = resolve
        }),
    )
    const second = queue(async () => {
      started.push('second')
    })

    await Promise.resolve()
    expect(started).toEqual(['first'])
    releaseFirst?.()
    await first
    await second
    expect(started).toEqual(['first', 'second'])
  })
})
