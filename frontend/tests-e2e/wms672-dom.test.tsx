// INCOMPLETE DRAFT: resource-stopped before any business verdict; see WMS-672 evidence.
import React, { act } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { afterEach, beforeEach, expect, test, vi } from 'vitest'
import { PNG } from 'pngjs'
import { FfInboundRequestView } from '../src/screens/ff/FfInboundRequestView'

// Real screen, batch builder, print utility and JsBarcode. Only platform boundaries
// are replaced: synthetic HTTP, canvas raster surface and image decode/print.
// This does NOT claim browser layout, PDF pagination, reload or physical paper proof.
let root: Root
let host: HTMLDivElement
let calls: string[]
let frames: HTMLIFrameElement[]
let transfers: string[]
let failMark: boolean
let decoded: number
let failDecode: boolean
let release: () => void
let gate: Promise<void>
let loadFrames: () => void
const pause = () => new Promise(r => setTimeout(r, 10))
async function until(check: () => boolean) {
  for (let i = 0; i < 200; i++) {
    if (check()) return
    await act(async () => { await pause() })
  }
  throw new Error('fixture did not reach expected action boundary')
}
function button(id: string): HTMLButtonElement {
  const b = document.querySelector<HTMLButtonElement>(`[data-testid="${id}"]`)
  if (!b) throw new Error(`missing real action ${id}`)
  return b
}
async function click(id: string) { await act(async () => { button(id).click() }) }

beforeEach(() => {
  Object.assign(globalThis, { IS_REACT_ACT_ENVIRONMENT: true })
  localStorage.clear(); sessionStorage.clear()
  calls = []; frames = []; transfers = []; failMark = false; decoded = 0; failDecode = false
  gate = new Promise(r => { release = r })
  // Minimal raster canvas for real CODE128 bars (no replacement of barcode strings).
  // JsBarcode uses fillRect, save/restore and translate with displayValue=false.
  const contexts = new WeakMap<HTMLCanvasElement, any>()
  vi.spyOn(HTMLCanvasElement.prototype, 'getContext').mockImplementation(function (this: HTMLCanvasElement) {
    if (!contexts.has(this)) {
      let offset = 0
      let pixels: Buffer
      let dims = ''
      const canvas = this
      const ctx = { fillStyle: '#fff', save() {}, restore() { offset = 0 },
        translate(x: number) { offset += x }, clearRect() { pixels = undefined! },
        fillRect(x: number, y: number, w: number, h: number) {
          const key = `${canvas.width}:${canvas.height}`
          if (!pixels || key !== dims) { pixels = Buffer.alloc(canvas.width * canvas.height * 4, 255); dims = key }
          const c = ctx.fillStyle === '#111' ? 17 : 255
          for (let yy = Math.max(0, y); yy < Math.min(canvas.height, y + h); yy++)
            for (let xx = Math.max(0, x + offset); xx < Math.min(canvas.width, x + offset + w); xx++) {
              const i = (yy * canvas.width + xx) * 4
              pixels[i] = pixels[i + 1] = pixels[i + 2] = c
            }
        }, bytes() { return pixels } }
      contexts.set(this, ctx)
    }
    return contexts.get(this)
  } as any)
  vi.spyOn(HTMLCanvasElement.prototype, 'toDataURL').mockImplementation(function (this: HTMLCanvasElement) {
    const png = new PNG({ width: this.width, height: this.height })
    png.data = contexts.get(this).bytes()
    return `data:image/png;base64,${PNG.sync.write(png).toString('base64')}`
  })
  const append = document.body.appendChild.bind(document.body)
  vi.spyOn(document.body, 'appendChild').mockImplementation(((node: Node) => {
    const result = append(node)
    if (node instanceof HTMLIFrameElement) frames.push(node)
    return result
  }) as any)
  loadFrames = () => {
    for (const frame of frames.filter(f => !f.dataset.loaded)) {
      frame.dataset.loaded = 'yes'
      // jsdom does not navigate srcdoc: supply the utility's own complete HTML.
      frame.contentDocument!.open(); frame.contentDocument!.write(frame.srcdoc); frame.contentDocument!.close()
      const win = frame.contentWindow!
      Object.defineProperty(win.HTMLImageElement.prototype, 'decode', { configurable: true,
        value: async function () {
          const index = ++decoded
          await gate
          if (failDecode && index === 150) throw new Error('WMS672 decode failed at 150')
        } })
      win.focus = () => {}
      win.print = () => { transfers.push(frame.srcdoc) }
      frame.onload!(new Event('load') as any)
    }
  }
  host = document.createElement('div'); document.body.append(host); root = createRoot(host)
})
afterEach(async () => {
  release()
  await act(async () => { await new Promise(r => setTimeout(r, 150)); root.unmount() })
  vi.restoreAllMocks(); vi.unstubAllGlobals(); document.body.replaceChildren()
})
async function fixture(n = 300, operation = 'inbound') {
  const data = { id: '672-document', warehouse_id: '672-warehouse', seller_id: '672-seller',
    seller_name: 'Синтетический селлер', document_number: '672', display_number: '672',
    status: 'receiving', operation_type: operation, marketplace: 'wildberries',
    planned_box_count: n, actual_box_count: n, lines: [], cargo_places: [],
    boxes: Array.from({ length: n }, (_, i) => ({ id: `672-box-${i + 1}`, box_number: i + 1,
      internal_barcode: `INB-${String(i + 1).padStart(12, '0')}`, label_printed_at: null,
      intake_opened_at: null, intake_closed_at: null, is_open: false, lines: [] })) }
  vi.stubGlobal('fetch', vi.fn(async (url: string, init?: RequestInit) => {
    const path = String(url)
    if (init?.method && init.method !== 'GET') {
      calls.push(path)
      if (failMark && calls.length === 150) throw new Error('accepted mark response lost')
      return new Response('{}', { headers: { 'Content-Type': 'application/json' } })
    }
    const body = path.endsWith('/inbound-intake-requests/672-document') ? data
      : path.endsWith('/marking-codes') ? { items: [], checking: false } : []
    return new Response(JSON.stringify(body), { headers: { 'Content-Type': 'application/json' } })
  }))
  await act(async () => { root.render(<FfInboundRequestView token={`synthetic.${btoa(JSON.stringify({tenant_id: "672-tenant", sub: "672-user"}))}.synthetic`} requestId="672-document"
    isFulfillmentAdmin numberedInboundBoxLabels onClose={() => {}} />) })
  await until(() => !!document.querySelector('[data-testid="ff-inbound-packages-toggle"]'))
  await click('ff-inbound-packages-toggle')
  await until(() => !!document.querySelector('[data-testid="ff-inbound-boxes-print-all"]'))
  expect(calls).toEqual([]); expect(frames).toHaveLength(0)
  return data
}
async function confirm() {
  await click('ff-inbound-boxes-print-all')
  await click('ff-inbound-box-print-dialog-confirm')
  expect(frames.length).toBeGreaterThan(0) // proves real batch builder executed
  loadFrames()
}
for (const operation of ['inbound', 'return']) for (const n of [200, 300]) {
  test(`C1 ${operation} ${n}: one complete ordered tape, no box creation`, async () => {
    const data = await fixture(n, operation)
    await confirm(); release()
    await until(() => transfers.length > 0)
    expect(transfers).toHaveLength(1)
    const doc = new DOMParser().parseFromString(transfers[0], 'text/html')
    expect([...doc.querySelectorAll('.label')].map(l => l.getAttribute('data-barcode')))
      .toEqual(data.boxes.map(b => b.internal_barcode))
    expect(doc.querySelectorAll('.label--next')).toHaveLength(n - 1)
    expect(doc.querySelector('style')!.textContent).toContain('size: 58mm 40mm')
    expect(calls.every(p => p.endsWith('/mark-label-printed'))).toBe(true)
  })
}
test('C5 300 labels: decode failure at 150 cannot write successful marks before transfer', async () => {
  await fixture(); failDecode = true; await confirm()
  expect(decoded).toBeGreaterThan(1) // actual first parallel group is held
  expect(transfers).toHaveLength(0)
  const earlyMarks = [...calls]
  release(); await until(() => document.querySelector('[role="alert"]')?.textContent?.includes('decode failed') === true && !button('ff-inbound-boxes-print-all').disabled)
  expect(transfers).toHaveLength(0)
  expect(earlyMarks, 'no successful marks while decode is still pending').toEqual([])
  expect(calls, 'failed preparation must not mark boxes printed').toEqual([])
  expect(document.querySelector('[role="alert"]')?.textContent).toContain('decode failed')
  expect(button('ff-inbound-boxes-print-all').disabled).toBe(false)
})
test('C8 300 labels: lost mark response retry cannot silently send a second tape', async () => {
  await fixture(); failMark = true; await confirm(); release()
  await until(() => transfers.length === 1)
  await until(() => !!document.querySelector('[role="alert"]'))
  expect(calls).toHaveLength(150)
  expect(document.querySelector('[role="alert"]')!.textContent).toContain('response lost')
  failMark = false
  await confirm()
  await act(async () => { await new Promise(r => setTimeout(r, 250)) })
  expect(transfers, 'recover original attempt before an explicitly new reprint').toHaveLength(1)
})
