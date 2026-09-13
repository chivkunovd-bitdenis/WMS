import { describe, expect, it } from 'vitest'
import { previewMatchesContext, releasePrinterBusyRequest, type PrinterPreview } from './WarehousePrinterDialog'

describe('printer pairing preview', () => {
  const preview: PrinterPreview = {
    connection_id: 'connection-a', queue_name: 'Queue A', platform: 'darwin', pairingCode: 'A', warehouseId: 'warehouse-a',
  }

  it('does not allow a delayed preview for A to confirm changed code B', () => {
    expect(previewMatchesContext(preview, 'B', 'warehouse-a')).toBe(false)
    expect(previewMatchesContext(preview, 'A', 'warehouse-a')).toBe(true)
  })

  it('does not allow a preview from another warehouse to confirm', () => {
    expect(previewMatchesContext(preview, 'A', 'warehouse-b')).toBe(false)
  })

  it('releases invalidated preview A, while an old completion cannot release new preview B', () => {
    const previewA = 1
    const previewB = 3
    expect(releasePrinterBusyRequest(previewA, previewA)).toBeNull()
    expect(releasePrinterBusyRequest(previewB, previewA)).toBe(previewB)
    expect(releasePrinterBusyRequest(previewB, previewB)).toBeNull()
  })
})
