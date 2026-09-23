import { readFileSync } from 'node:fs'
import { describe, expect, it } from 'vitest'

const source = readFileSync(new URL('./FfFbsSupplyWorkspace.tsx', import.meta.url), 'utf8')
const sceneSource = readFileSync(
  new URL('../ff/knowledge/scenes/FbsScenes.tsx', import.meta.url),
  'utf8',
)

describe('WMS-514 mockup gating in the real FBS workspace', () => {
  it('renders exactly three added controls only behind the mockup-only config', () => {
    const scanBar = source.slice(
      source.indexOf('data-testid="fbs-kiz-scan-bar"'),
      source.indexOf('data-testid="fbs-kiz-scan-active"'),
    )
    expect(scanBar).toContain('{mockupScanPrinting ? (')
    expect(scanBar.match(/<FormControlLabel/g)).toHaveLength(3)
    expect(scanBar).toContain('label="Печатать QR"')
    expect(scanBar).toContain('label="Печатать ЧЗ"')
    expect(scanBar).toContain('label="Перепечатывать ЧЗ"')
  })

  it('keeps both CHZ modes mutually exclusive without switching either implicitly', () => {
    const scanBar = source.slice(
      source.indexOf('data-testid="fbs-kiz-scan-bar"'),
      source.indexOf('data-testid="fbs-kiz-scan-active"'),
    )
    expect(scanBar).toContain('disabled={autoReprintHonestSign}')
    expect(scanBar).toContain('disabled={autoPrintHonestSign}')
    expect(scanBar).not.toContain('if (event.target.checked)')
  })

  it('leaves the production scan path and all-off path on the baseline sticker lookup', () => {
    const mockupHandler = source.slice(
      source.indexOf('const scanStickerOrMockupPrint = useCallback'),
      source.indexOf('// WMS-403:'),
    )
    expect(mockupHandler).toContain('if (!mockupScanPrinting) return scanKizSticker(raw)')
    expect(mockupHandler).toContain('!autoPrintOrderQr && !autoPrintHonestSign && !autoReprintHonestSign')
    expect(mockupHandler).toContain('return scanKizSticker(raw)')
    expect(mockupHandler.indexOf('scanKizSticker(raw, true)'))
      .toBeLessThan(mockupHandler.indexOf('mockupScanPrinting.handleIdleScan'))
  })

  it('does not add inline reprint actions to baseline accepted fixture rows', () => {
    const markingState = sceneSource.slice(
      sceneSource.indexOf('states: [', sceneSource.indexOf('function supplyOrders')),
      sceneSource.indexOf('delivery_allowed:', sceneSource.indexOf('function supplyOrders')),
    )
    expect(markingState).toContain("status: 'accepted' as const")
    expect(markingState).not.toContain('id:')
  })
})
