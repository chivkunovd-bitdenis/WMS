import { describe, expect, it, vi } from 'vitest'
import { FfInboundRequestView } from './FfInboundRequestView'
import type { InboundRequestWorkspace, WbCatalogRow } from './FfInboundRequestView'
import {
  applyScannedInboundLine,
  createDebouncedInboundReconciler,
  createSerialScanQueue,
  isLatestScannedInboundLine,
} from './inboundReceivingRuntime'

// TC-NEW-A3-001 / TC-NEW-A3-002: this refactor may move source files, but it
// must not silently remove selectors, hide the monolith in .ts, or suppress types.
const inboundSources = import.meta.glob<string>([
  './FfInboundRequest*.ts',
  './FfInboundRequest*.tsx',
  './useFfInboundRequest*.ts',
  './useFfInboundRequest*.tsx',
  '!./*.test.ts',
  '!./*.test.tsx',
], {
  eager: true,
  import: 'default',
  query: '?raw',
})
const inboundSourceText = Object.values(inboundSources).join('\n')
const inboundSourceWithoutComments = inboundSourceText.replace(/\/\*[\s\S]*?\*\/|\/\/.*$/gm, '')
const staticTestIds = [...inboundSourceWithoutComments.matchAll(/data-testid\s*=\s*["']([^"']+)["']/g)]
  .map((match) => match[1])
  .sort()

const baselineStaticTestIds = [
  'ff-inbound-add-products',
  'ff-inbound-add-to-box',
  'ff-inbound-admin-distribution',
  'ff-inbound-box-line-name',
  'ff-inbound-box-line-qty',
  'ff-inbound-box-line-sku',
  'ff-inbound-box-row',
  'ff-inbound-boxes-panel',
  'ff-inbound-boxes-print-all',
  'ff-inbound-boxes-summary',
  'ff-inbound-cargo-place-row',
  'ff-inbound-cargo-places-create',
  'ff-inbound-cargo-places-dialog',
  'ff-inbound-cargo-places-error',
  'ff-inbound-cargo-places-print-all',
  'ff-inbound-cell-hint',
  'ff-inbound-cell-hints',
  'ff-inbound-close',
  'ff-inbound-close-confirm',
  'ff-inbound-close-confirm-dialog',
  'ff-inbound-compact-summary',
  'ff-inbound-create-cargo-places',
  'ff-inbound-dimensions-dialog',
  'ff-inbound-dimensions-error',
  'ff-inbound-dimensions-save',
  'ff-inbound-discrepancy-act',
  'ff-inbound-discrepancy-act-approve',
  'ff-inbound-discrepancy-act-line',
  'ff-inbound-discrepancy-act-lines',
  'ff-inbound-discrepancy-act-reject',
  'ff-inbound-discrepancy-act-status',
  'ff-inbound-discrepancy-acts',
  'ff-inbound-discrepancy-acts-error',
  'ff-inbound-discrepancy-acts-loading',
  'ff-inbound-discrepancy-box-summary',
  'ff-inbound-discrepancy-confirm',
  'ff-inbound-discrepancy-dialog',
  'ff-inbound-discrepancy-line',
  'ff-inbound-discrepancy-lines',
  'ff-inbound-distribute-open',
  'ff-inbound-distribution-add-row',
  'ff-inbound-distribution-complete',
  'ff-inbound-distribution-create-location',
  'ff-inbound-distribution-error',
  'ff-inbound-distribution-location',
  'ff-inbound-distribution-location-print',
  'ff-inbound-distribution-no-cell',
  'ff-inbound-distribution-no-cell-line',
  'ff-inbound-distribution-no-locations',
  'ff-inbound-distribution-product',
  'ff-inbound-distribution-remove-row',
  'ff-inbound-distribution-reopen',
  'ff-inbound-distribution-row',
  'ff-inbound-distribution-save',
  'ff-inbound-distribution-stuck-empty',
  'ff-inbound-distribution-table',
  'ff-inbound-distribution-warehouse',
  'ff-inbound-doc-error',
  'ff-inbound-doc-error',
  'ff-inbound-doc-loading',
  'ff-inbound-doc-root',
  'ff-inbound-document-number',
  'ff-inbound-import-boxes',
  'ff-inbound-import-success-snackbar',
  'ff-inbound-line-actual-display',
  'ff-inbound-line-added-by-ff',
  'ff-inbound-line-barcode',
  'ff-inbound-line-dimensions',
  'ff-inbound-line-dimensions-edit',
  'ff-inbound-line-discrepancy',
  'ff-inbound-line-expected',
  'ff-inbound-line-manual-edit',
  'ff-inbound-line-product-name',
  'ff-inbound-line-sku',
  'ff-inbound-lines-table',
  'ff-inbound-marketplace-warning',
  'ff-inbound-moved-to-sorting',
  'ff-inbound-operation-type',
  'ff-inbound-packages-accordion',
  'ff-inbound-packages-toggle',
  'ff-inbound-planned-boxes',
  'ff-inbound-print-waybill',
  'ff-inbound-received-summary',
  'ff-inbound-receiving-add-products',
  'ff-inbound-reopen-receiving',
  'ff-inbound-return-autoprint',
  'ff-inbound-save',
  'ff-inbound-save-success-snackbar',
  'ff-inbound-scan-add-product',
  'ff-inbound-scan-error-snackbar',
  'ff-inbound-seller-name',
  'ff-inbound-sorting-wait-reception',
  'ff-inbound-status-chip',
  'ff-inbound-submit-warehouse',
  'ff-inbound-submit-warehouse',
  'ff-inbound-verify-complete',
  'ff-inbound-volume-summary',
  'ff-inbound-waybill-number',
  'ff-inbound-weight-summary',
  'ff-sorting-posted-done',
]

describe('inbound view split public and source contracts', () => {
  it('keeps the public component and type exports used by the FF routes', () => {
    const workspace: InboundRequestWorkspace = 'reception'
    const catalogRow: WbCatalogRow | null = null

    expect(FfInboundRequestView).toBeTypeOf('function')
    expect(workspace).toBe('reception')
    expect(catalogRow).toBeNull()
  })

  it('preserves the complete static data-testid multiset from the baseline screen', () => {
    expect(staticTestIds).toEqual(baselineStaticTestIds)
  })

  it('preserves dynamic row, box, cargo-place and child selector contracts', () => {
    for (const selectorPrefix of [
      'ff-inbound-line-row-',
      'ff-inbound-box-header-',
      'ff-inbound-box-fill-',
      'ff-inbound-box-delete-',
      'ff-inbound-box-print-',
      'ff-inbound-cargo-place-print-',
      'ff-inbound-line-photo',
      'ff-inbound-box-line-photo',
      'ff-inbound-marketplace-chip',
      'ff-inbound-planned-date',
      'ff-inbound-picker',
      'ff-inbound-box-import',
      'ff-inbound-box-print-dialog',
    ]) {
      expect(inboundSourceText).toContain(selectorPrefix)
    }
  })

  it('does not create an A-3 source module larger than the 600-line monolith limit', () => {
    for (const [path, source] of Object.entries(inboundSources)) {
      expect(source.split('\n').length, path).toBeLessThanOrEqual(600)
    }
  })

  it('does not suppress TypeScript or ESLint checks in a created A-3 module', () => {
    expect(inboundSourceText).not.toMatch(/@ts-(?:nocheck|ignore|expect-error)|eslint-disable/)
  })

  it('does not introduce an unsafe any contract in a created A-3 module', () => {
    expect(inboundSourceText).not.toMatch(/\bany\b/)
  })
})

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

  it('coalesces repeated reconciliation until scanning pauses', async () => {
    vi.useFakeTimers()
    const reload = vi.fn(async () => undefined)
    const reconciler = createDebouncedInboundReconciler(reload, 2500)

    reconciler.schedule()
    await vi.advanceTimersByTimeAsync(2000)
    reconciler.schedule()
    await vi.advanceTimersByTimeAsync(2499)
    expect(reload).not.toHaveBeenCalled()

    await vi.advanceTimersByTimeAsync(1)
    expect(reload).toHaveBeenCalledOnce()
    reconciler.cancel()
    vi.useRealTimers()
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
