import { readFileSync } from 'node:fs'
import { describe, expect, it } from 'vitest'

const source = readFileSync(new URL('./FfFbsSupplyWorkspace.tsx', import.meta.url), 'utf8')

describe('WMS-514 · scan classification and silent print wiring', () => {
  it('renders exactly the three requested WB controls with mutually exclusive CHZ modes', () => {
    const scanBar = source.slice(
      source.indexOf('data-testid="fbs-kiz-scan-bar"'),
      source.indexOf('data-testid="fbs-kiz-scan-active"'),
    )
    expect(scanBar.match(/<FormControlLabel/g)).toHaveLength(3)
    expect(scanBar).toContain('label="Печатать QR"')
    expect(scanBar).toContain('label="Печатать ЧЗ"')
    expect(scanBar).toContain('label="Перепечатывать ЧЗ"')
    expect(scanBar).toContain('disabled={scanPrintPreferences.reprintChz}')
    expect(scanBar).toContain('disabled={scanPrintPreferences.printChz}')
    expect(scanBar.indexOf('data-testid="fbs-kiz-scan-input"'))
      .toBeLessThan(scanBar.indexOf('data-testid="fbs-scan-print-qr-toggle"'))
  })

  it('keeps lookup before direct KIZ reprint and product barcode selection', () => {
    const idleScan = source.slice(
      source.indexOf('const scanIdleCode = useCallback'),
      source.indexOf('const scanKizCode = useCallback'),
    )
    const orderQr = idleScan.indexOf('lookupFbsOrderBySticker(')
    const directKiz = idleScan.indexOf('saveFbsDirectKizReprint(')
    const product = idleScan.indexOf('scanFbsProductForAutoPrint(')
    expect(orderQr).toBeGreaterThan(-1)
    expect(directKiz).toBeGreaterThan(orderQr)
    expect(product).toBeGreaterThan(directKiz)
  })

  it('snapshots checkbox state and preserves QR before one-copy CHZ in the serial queue', () => {
    const enter = source.slice(
      source.indexOf('const onKizScanEnter = useCallback'),
      source.indexOf('const requestPrintBatch = async'),
    )
    expect(enter).toContain('const preferences = { ...scanPrintPreferences }')
    expect(enter).toContain('queuedPackingScansRef.current.push({ raw, preferences })')

    const idleScan = source.slice(
      source.indexOf('const scanIdleCode = useCallback'),
      source.indexOf('const scanKizCode = useCallback'),
    )
    const qrTarget = idleScan.indexOf('`${result.scan_id}:qr:')
    const chzTarget = idleScan.indexOf('`${result.scan_id}:chz:')
    expect(qrTarget).toBeGreaterThan(-1)
    expect(chzTarget).toBeGreaterThan(qrTarget)
    expect(idleScan.slice(chzTarget)).toContain("{ units: [{ block: 'cz', copies: 1 }] }")
  })

  it('keeps 000 and Ozon on the old lookup error path without product selection', () => {
    const idleScan = source.slice(
      source.indexOf('const scanIdleCode = useCallback'),
      source.indexOf('const scanKizCode = useCallback'),
    )
    const fallback = idleScan.indexOf('if (\n          isOzonSupply')
    const product = idleScan.indexOf('scanFbsProductForAutoPrint(')
    expect(fallback).toBeGreaterThan(-1)
    expect(idleScan.slice(fallback, product)).toContain('throw stickerNotFound')
    expect(product).toBeGreaterThan(fallback)
  })

  it('clears an accepted scanner payload before async work and never clears it in async finally', () => {
    const enter = source.slice(
      source.indexOf('const onKizScanEnter = useCallback'),
      source.indexOf('const requestPrintBatch = async'),
    )
    expect(enter.indexOf("setKizScanValue('')"))
      .toBeLessThan(enter.indexOf('if (kizScanBusy)'))
    const asyncScans = source.slice(
      source.indexOf('const scanIdleCode = useCallback'),
      source.indexOf('const dropKizScanActive = useCallback'),
    )
    expect(asyncScans).not.toContain("setKizScanValue('')")
    expect(enter).toContain('scanInput.blur()')
  })

  it('preserves a busy hardware prefix across busy to idle without an idle global listener', () => {
    const busyCapture = source.slice(
      source.indexOf('// The baseline scanner input is disabled while its request is running.'),
      source.indexOf("useEffect(() => {\n    if (!kizScanBusy) return"),
    )
    expect(busyCapture).toContain('useLayoutEffect(() => {')
    expect(busyCapture).toContain('&& busyHardwareCaptureEnabledRef.current')
    expect(busyCapture).toContain('if (!kizScanBusy) {')
    expect(busyCapture).toContain('mergeFbsBufferedHardwareScan(prefix, current)')
    expect(busyCapture.indexOf('if (!kizScanBusy) {'))
      .toBeLessThan(busyCapture.indexOf("document.addEventListener('keydown'"))
    expect(busyCapture).not.toContain('target !== kizScanInputRef.current')
  })

  it('routes product QR and CHZ through durable target claims in the shared queue', () => {
    const idleScan = source.slice(
      source.indexOf('const scanIdleCode = useCallback'),
      source.indexOf('const scanKizCode = useCallback'),
    )
    expect(idleScan.match(/kizAutoPrintQueueRef\.current\.enqueue/g)).toHaveLength(4)
    expect(idleScan).toContain('claimFbsScanAutoPrintTarget(')
    expect(idleScan).toContain('markFbsScanAutoPrintTargetStarted(')
    expect(idleScan).toContain('releaseFbsScanAutoPrintTargetClaim(')
  })

  it('finishes a cancelled product reprint attempt before clearing the active target', () => {
    const reset = source.slice(
      source.indexOf('const dropKizScanActive = useCallback'),
      source.indexOf('const onKizScanEnter = useCallback'),
    )
    expect(reset).toContain('completeFbsPendingProductScan(')
    expect(reset.indexOf('completeFbsPendingProductScan('))
      .toBeLessThan(reset.indexOf('activeProductScanBarcodeRef.current = null'))
  })

  it('keeps the existing replacement confirmation for a product-selected order with KIZ', () => {
    const reprintTarget = source.slice(
      source.indexOf('// Product selection must not bypass the existing replacement'),
      source.indexOf('printErrors.push(...result.order_errors'),
    )
    expect(reprintTarget).toContain('result.binding_target.needs_confirmation')
    expect(reprintTarget).toContain('setKizConfirmTarget(result.binding_target)')
    expect(reprintTarget).toContain('setKizScanActive(result.binding_target)')
    const dismiss = source.slice(
      source.indexOf('const dismissKizConfirmation = useCallback'),
      source.indexOf('const onKizScanEnter = useCallback'),
    )
    expect(dismiss).toContain('completeFbsPendingProductScan(')
  })

  it('retains a QR plus reprint attempt until both targets definitely started', () => {
    const idleScan = source.slice(
      source.indexOf('const scanIdleCode = useCallback'),
      source.indexOf('const scanKizCode = useCallback'),
    )
    expect(idleScan).toContain('let waitingForReprintKiz = plan.reprintChz && !attempt.chzStarted')
    expect(idleScan).toContain('const attemptComplete = fbsPendingProductScanComplete(attempt)')

    const kizScan = source.slice(
      source.indexOf('const scanKizCode = useCallback'),
      source.indexOf('const dropKizScanActive = useCallback'),
    )
    expect(kizScan).toContain('const pendingProductAttempt = productBarcode && workspace?.supply.id')
    expect(kizScan).toContain('const effectivePreferences = pendingProductAttempt?.preferences ?? preferences')
    expect(kizScan).toContain('boundReprintStarted = await kizAutoPrintQueueRef.current.enqueue')
    expect(kizScan).toContain('pendingProductAttempt.chzStarted = true')
    expect(kizScan).toContain('if (fbsPendingProductScanComplete(pendingProductAttempt))')
  })

  it('recovers only the durable released bound-KIZ target and keeps ordinary duplicates inert', () => {
    const idleScan = source.slice(
      source.indexOf('const scanIdleCode = useCallback'),
      source.indexOf('const scanKizCode = useCallback'),
    )
    expect(idleScan).toContain("recovery?.status === 'available'")
    expect(idleScan).toContain("recovery?.status === 'outcome_unknown'")
    expect(idleScan).toContain('claimFbsScanAutoPrintReprint(')
    expect(idleScan).toContain('printMarkingCodeLabels([claim.kiz], { duplicateCopies: 1 })')
    expect(idleScan).not.toContain('recovery.kiz')
    expect(idleScan).toContain("result.scan_id,\n                        'chz',")

    const kizScan = source.slice(
      source.indexOf('const scanKizCode = useCallback'),
      source.indexOf('const dropKizScanActive = useCallback'),
    )
    expect(kizScan).toContain('if (outcome.newly_bound === true && scan.enabled)')
    expect(kizScan).toContain('const durableScanId = pendingProductAttempt?.scanId')
    expect(kizScan).toContain('scan_auto_print_id: pendingProductAttempt.scanId')
    expect(kizScan).toContain('claimFbsScanAutoPrintReprint(')
    expect(kizScan).toContain('startClaimedAutomaticPrint<FbsScanAutoPrintReprintClaim>(')
    expect(kizScan).not.toContain('outcome.newly_bound !== false')
  })

  it('keeps the original scan-bar visibility guard and no separate reprint error node', () => {
    const scanBar = source.indexOf('data-testid="fbs-kiz-scan-bar"')
    expect(source.slice(scanBar - 500, scanBar)).toContain('{anyOrderNeedsHonestSign ? (')
    expect(source).not.toContain('fbs-kiz-auto-reprint-error')
  })
})
