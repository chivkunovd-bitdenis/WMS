// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { harness, makeDetail } from '../../test-contracts/inbound684586Harness'
import { DEFAULT_LABEL_SIZE } from '../../utils/labelSize'
import { printBarcodeLabels } from '../../utils/printBarcodeLabel'

let h: ReturnType<typeof harness>
beforeEach(() => { h = harness() })
afterEach(async () => { await h.dispose(); vi.useRealTimers() })

describe('WMS-684 review regression contract', () => {
  it('keeps the frozen internal-box layout for cargo places and shipment boxes without receipt metadata', () => {
    printBarcodeLabels([{
      title: 'Грузоместо № 1', barcode: 'CARGO-1', barcodeDataUrl: 'data:image/png;base64,AA==',
      labelSize: DEFAULT_LABEL_SIZE, layout: 'internalBox',
    }, {
      title: 'Короб поставки № 7', barcode: 'SHIPMENT-7', barcodeDataUrl: 'data:image/png;base64,AA==',
      labelSize: DEFAULT_LABEL_SIZE, layout: 'internalBox',
    }])
    const html = window.__WMS_LAST_PRINT_HTML__!
    expect(html).toContain('Грузоместо № 1')
    expect(html).toContain('Короб поставки № 7')
    expect(html).toContain('grid-template-rows: auto 1fr auto')
    expect(html).toContain('.title { font-size: 13pt; font-weight: 800; text-align: center; }')
    expect(html).toContain('.code { font-size: 9pt; text-align: center; }')
    expect(html).toContain('height: auto; max-height: none; display: block; image-rendering: pixelated;')
    expect(html).not.toContain('class="metadata"')
  })

  it('treats a timezone-less receipt timestamp as UTC before formatting its Moscow date', async () => {
    h.current.created_at = '2026-09-28T21:30:00'
    await h.render()
    for (const all of [false, true]) {
      const doc = await h.print(all)
      expect(doc.body.textContent).toContain('29.09.2026')
      expect(doc.body.textContent).not.toContain('28.09.2026')
    }
  })

  for (const [description, displayNumber, documentNumber, expected] of [
    ['missing display number', null, 'INB-000684', '№000684'],
    ['blank display number', ' ', 'INB-000684', '№000684'],
    ['invalid fallback number', null, 'broken', '—'],
  ] as const) {
    it(`uses the established human-number fallback for ${description}`, async () => {
      h.current = {
        ...makeDetail(), display_number: displayNumber, document_number: documentNumber,
      } as typeof h.current
      await h.render()
      for (const all of [false, true]) {
        const doc = await h.print(all)
        expect(doc.body.textContent).toContain(`Приёмка ${expected} от 28.09.2026`)
      }
    })
  }
})
