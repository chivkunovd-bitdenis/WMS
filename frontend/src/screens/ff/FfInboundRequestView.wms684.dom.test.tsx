// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { harness, makeDetail } from '../../test-contracts/inbound684586Harness'
import { printBarcodeLabel } from '../../utils/printBarcodeLabel'
import { renderBarcodeDataUrl } from '../../utils/renderBarcodeDataUrl'

let h: ReturnType<typeof harness>
beforeEach(() => { h = harness() })
afterEach(async () => { await h.dispose(); vi.useRealTimers() })

function labels(doc: Document) { return [...doc.querySelectorAll('section.label')] }
function assertIdentity(doc: Document, seller = 'ИП Иванов', number = '№000684', date = '28.09.2026') {
  for (const label of labels(doc)) {
    expect(label.textContent).toContain(seller)
    expect(label.textContent).toContain(number)
    expect(label.textContent).toContain(date)
  }
}

// K1-K5: exercise both real screen paths, the encoder and the HTML printer.
describe('WMS-684 acceptance box labels', () => {
  for (const numbered of [true, false]) for (const generated of [true, false]) {
    it(`single label preserves own box and metadata numbered=${numbered} generated=${generated}`, async () => {
      if (!generated) h.current.boxes[1]!.internal_barcode = 'CUSTOM-BOX-02'
      await h.render(numbered)
      const doc = await h.print()
      expect(labels(doc)).toHaveLength(1)
      const box = h.current.boxes[1]!
      expect(labels(doc)[0]!.getAttribute('data-barcode')).toBe(box.internal_barcode)
      expect(doc.body.textContent).toContain(numbered && generated ? 'Короб № 2' : `Короб ${box.internal_barcode}`)
      expect(doc.body.textContent).toMatch(/(?:№\s*2|Короб\s*2)/)
      expect(h.markCalls).toHaveLength(1)
      expect(h.markCalls[0]).toContain(box.id)
      assertIdentity(doc)
    })
  }
  it('bulk is one job with three pages in original order and no trailing break', async () => {
    await h.render()
    const before = JSON.stringify(h.current)
    const doc = await h.print(true)
    expect(document.querySelectorAll('iframe')).toHaveLength(1)
    expect(labels(doc).map(node => node.getAttribute('data-barcode'))).toEqual(h.current.boxes.map(box => box.internal_barcode))
    expect(labels(doc)).toHaveLength(3)
    expect(labels(doc).slice(0, -1).every(node => node.classList.contains('label--next'))).toBe(true)
    expect(labels(doc).at(-1)!.classList.contains('label--next')).toBe(false)
    expect(h.markCalls).toHaveLength(3)
    expect(JSON.stringify(h.current)).toBe(before)
    assertIdentity(doc)
  })
  it('refresh and navigation preserve identities without stale seller/date/box data', async () => {
    await h.render()
    const a = JSON.stringify(h.current)
    assertIdentity(await h.print())
    assertIdentity(await h.print(true))
    assertIdentity(await h.print())
    expect(JSON.stringify(h.current)).toBe(a)
    h.current = { ...makeDetail('B'), display_number: '№009999', created_at: '2026-09-20T00:00:00Z',
      seller_name: 'ООО Другой селлер', marketplace: 'ozon', boxes: makeDetail('B').boxes.map((box, i) => ({ ...box, internal_barcode: `B-CODE-${i}` })) }
    await h.render()
    for (const all of [false, true]) {
      const doc = await h.print(all)
      assertIdentity(doc, 'ООО Другой селлер', '№009999', '20.09.2026')
      expect(doc.body.textContent).not.toContain('ИП Иванов')
      expect(doc.body.textContent).not.toContain('000684')
      expect(labels(doc).map(node => node.getAttribute('data-barcode'))).toEqual(all ? ['B-CODE-0', 'B-CODE-1', 'B-CODE-2'] : ['B-CODE-1'])
    }
    expect(h.fetcher.mock.calls.filter(([, init]) => init?.method === 'POST').every(([url]) => String(url).endsWith('/mark-label-printed'))).toBe(true)
  })
  it('uses the Moscow document date and handles missing or invalid metadata without refusing print', async () => {
    vi.setSystemTime(new Date('2026-10-06T12:00:00Z'))
    h.current.created_at = '2026-09-28T21:30:00Z'
    await h.render()
    for (const all of [false, true]) {
      const doc = await h.print(all)
      assertIdentity(doc, 'ИП Иванов', '№000684', '29.09.2026')
      for (const wrong of ['28.09.2026', '02.10.2026', '06.10.2026', '01.10.2026']) expect(doc.body.textContent).not.toContain(wrong)
    }
    for (const date of ['', 'not-a-date']) {
      h.current = { ...makeDetail(), created_at: date, seller_name: '', display_number: '', document_number: '' }
      await h.remount()
      for (const all of [false, true]) {
        const doc = await h.print(all)
        expect(doc.body.textContent).toContain('—')
        expect(doc.body.textContent).not.toMatch(/Invalid Date|NaN|06\.10\.2026|ИП Иванов/)
        expect(labels(doc)).toHaveLength(all ? 3 : 1)
      }
    }
  })
  it('escapes complete long seller text in single and bulk HTML', async () => {
    const seller = 'ИП «Очень длинное кириллическое имя и фамилия» & "Компания" <script>alert(1)</script><img src=x onerror=alert(2)>'
    h.current.seller_name = seller
    await h.render()
    for (const all of [false, true]) {
      const doc = await h.print(all)
      assertIdentity(doc, seller)
      expect(doc.querySelectorAll('script,img:not(.barcode)')).toHaveLength(0)
      expect([...doc.querySelectorAll('img.barcode')].every(image => image.getAttribute('src')?.startsWith('data:image/png;base64,'))).toBe(true)
    }
  })
  for (const mode of ['http', 'lost'] as const) {
    it(`mark ${mode} failure reports error, releases busy and never reprints automatically`, async () => {
      await h.render()
      const codes = h.current.boxes.map(box => [box.id, box.box_number, box.internal_barcode])
      const lines = JSON.stringify(h.current.lines)
      h.markMode = mode
      await h.print()
      expect(document.body.textContent).toContain(mode === 'http' ? 'label mark failed' : 'label response lost after commit')
      expect(h.markCalls).toHaveLength(1)
      expect(document.querySelectorAll('iframe')).toHaveLength(1)
      expect(h.current.boxes.map(box => [box.id, box.box_number, box.internal_barcode])).toEqual(codes)
      expect(JSON.stringify(h.current.lines)).toBe(lines)
      h.markMode = 'ok'
      await h.print(false, 1)
      // A lost response can still mean that the server committed the mark.
      // The durable attempt is reconciled on the next explicit action, without
      // sending a second tape or a second mark for that already printed box.
      expect(h.markCalls).toHaveLength(mode === 'http' ? 2 : 1)
      h.current = makeDetail('B')
      await h.render()
      await h.print(false, 1)
      expect(h.markCalls).toHaveLength(mode === 'http' ? 3 : 2)
    })
  }
  it('keeps cargo, default and storageCell printing free of receipt metadata', async () => {
    await h.render()
    const cargo = await h.print(false, 1, '58x40', true)
    expect(cargo.body.textContent).toContain('Грузоместо № 1')
    expect(cargo.body.textContent).not.toMatch(/ИП Иванов|000684|28\.09\.2026/)
    for (const layout of ['default', 'storageCell'] as const) {
      printBarcodeLabel({ title: 'Other label', barcode: 'OTHER-1', barcodeDataUrl: renderBarcodeDataUrl('OTHER-1'), layout })
      const html = window.__WMS_LAST_PRINT_HTML__!
      expect(html).toContain('Other label')
      expect(html).not.toMatch(/ИП Иванов|000684|28\.09\.2026/)
    }
  })
})
