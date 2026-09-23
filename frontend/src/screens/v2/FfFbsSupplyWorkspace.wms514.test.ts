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
    const qrTarget = idleScan.indexOf('`${result.scan_id}:qr`')
    const chzTarget = idleScan.indexOf('`${result.scan_id}:chz`')
    expect(qrTarget).toBeGreaterThan(-1)
    expect(chzTarget).toBeGreaterThan(qrTarget)
    expect(idleScan.slice(chzTarget)).toContain("{ units: [{ block: 'cz', copies: 1 }] }")
  })
})
