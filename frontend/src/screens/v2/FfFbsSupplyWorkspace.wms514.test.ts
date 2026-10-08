import { readFileSync } from 'node:fs'
import { describe, expect, it } from 'vitest'

const source = readFileSync(new URL('./FfFbsSupplyWorkspace.tsx', import.meta.url), 'utf8')
const printSource = readFileSync(new URL('../../utils/printMarkingCodeLabel.ts', import.meta.url), 'utf8')

describe('WMS-514 · scan classification and silent print wiring', () => {
  it('renders exactly the three requested WB controls with mutually exclusive CHZ modes', () => {
    const scanBar = readFileSync(new URL('./FbsPackingScanBar.tsx', import.meta.url), 'utf8')
    // WMS-631 R1: the same component renders the checkboxes in the supply and the assembly.
    const toggles = readFileSync(new URL('./FbsScanPrintToggles.tsx', import.meta.url), 'utf8')
    expect(toggles.match(/<FormControlLabel/g)).toHaveLength(3)
    expect(toggles).toContain('label="Печатать QR"')
    expect(toggles).toContain('label="Печатать ЧЗ"')
    expect(toggles).toContain('label="Перепечатывать ЧЗ"')
    expect(toggles).toContain('disabled={value.reprintChz}')
    expect(toggles).toContain('disabled={value.printChz}')
    const inputIndex = scanBar.indexOf('<TextField')
    const togglesIndex = scanBar.indexOf('<FbsScanPrintToggles')
    expect(inputIndex).toBeGreaterThan(-1)
    expect(togglesIndex).toBeGreaterThan(-1)
    expect(inputIndex).toBeLessThan(togglesIndex)
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

  it('WMS-666 P1 passes exact claimed binding validation to the final scan print dispatch', () => {
    const idleScan = source.slice(
      source.indexOf('const scanIdleCode = useCallback'),
      source.indexOf('const scanKizCode = useCallback'),
    )
    const chzStart = idleScan.indexOf('if (plan.printChz && !result.requires_honest_sign)')
    const reprintStart = idleScan.indexOf('if (waitingForReprintKiz)', chzStart)
    const chzDispatch = idleScan.slice(chzStart, reprintStart)
    const tapePrinter = printSource.slice(printSource.indexOf('export async function printMarkingCodeTape('))

    expect(chzStart).toBeGreaterThan(-1)
    expect(reprintStart).toBeGreaterThan(chzStart)
    expect(chzDispatch).toContain('const validateCurrentBinding = async () => validateFbsPrintBindings(token, [{')
    expect(chzDispatch).toContain('beforeDispatch: validateCurrentBinding')
    expect(chzDispatch).toContain('order_id: result.order_id')
    expect(chzDispatch).toContain('supply_id: printed.supply_id')
    expect(chzDispatch).toContain('marking_id: printed.marking_id')
    expect(chzDispatch).toContain('cis_code: kiz')
    expect(tapePrinter).toContain('await buildMarkingTapeSections(')
    expect(tapePrinter).toContain('printTapeSections(sections, options?.labelSize, options?.beforeDispatch)')
  })

  it('WMS-666 prepares a bare WB assembly group before the first scan and uses product KIZ requirements', () => {
    const preparation = source.slice(
      source.indexOf('// WMS-666: prepare missing WB stickers on picking and packing entry.'),
      source.indexOf('const openAddOrders = async () =>'),
    )
    expect(preparation).toContain('assemblyFrame?.visible')
    expect(preparation).toContain('registerSequentialScanner')
    expect(preparation).not.toContain('const prepare = !assemblyFrame &&')
    expect(source).toContain('order.product.requires_honest_sign')
  })

  it('WMS-666 offers an explicit same-workspace retry after prepare sticker request failure', () => {
    const preparation = source.slice(
      source.indexOf('// WMS-666: prepare missing WB stickers on picking and packing entry.'),
      source.indexOf('const openAddOrders = async () =>'),
    )
    expect(preparation).toContain('ensureFbsStickers(token, authHeaders, workspace, missing.map((order) => order.id))')
    expect(preparation).toContain('setRetryAction(() => () =>')
    expect(preparation).toContain('if (write.isCurrent()) void run(retryOperation, \'\', undefined, onRetrySuccess)')
    expect(preparation).toContain('const current = await fetchFbsWorkspace(token, authHeaders, supplyIdAtStart)')
    expect(preparation).toContain('.filter((order) => !order.sticker.code && order.status !== \'cancelled\')')
  })

  it('WMS-666 includes refreshed sticker codes in an ordinary picking-list print when available', () => {
    const print = source.slice(source.indexOf('const printPickingList = async () =>'), source.indexOf('const packLineByProduct = useMemo'))
    expect(print).toContain('ensureFbsStickers(token, authHeaders, workspace)')
    expect(print).toContain('printWorkspace = result.workspace')
    expect(print).toContain('fbsBuildPickingRows(\n      printWorkspace.orders')
    expect(print).toContain('historicalReadOnly')
    expect(print).toContain('const write = beginWorkspaceWrite()')
    expect(print).toContain('const isCurrentPrint = () => isWorkspaceWriteScreenCurrent(write, shownSupplyId.current, targetSupplyId)')
    expect(print).toContain('!isCurrentPrint()')
    expect(print).toContain('write.matchesShownSupply(result.workspace)')
    expect(print).toContain('if (isCurrentPrint() && write.isLatest()')
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

  it('keeps one editable standalone scan bar and no separate reprint error node', () => {
    // WMS-666 moved the same scan controls into the shared standalone/assembly bar.
    const panel = source.slice(source.indexOf('const packingPanel = workspace ? ('), source.indexOf('data-testid="fbs-kiz-scan-bar"'))
    expect(panel).toContain('{!assemblyFrame ? (')
    expect(panel).toContain('<FbsPackingScanBar')
    expect(panel).toContain("enabled={open && stage === 'packing' && packagingEditable && Boolean(sequentialScanner || ozonPackingScanner)}")
    const legacyIntake = source.slice(source.indexOf('const packingScanIntake = useScanIntake({'), source.indexOf('packingScanListeningRef.current = packingScanIntake.listening'))
    expect(legacyIntake).toContain('enabled: false,')
    expect(source).toContain('{packingScanIntake.listening ? (')
    expect(source).not.toContain('fbs-kiz-auto-reprint-error')
  })
})
