import { act } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { expect, vi } from 'vitest'
import { PNG } from 'pngjs'
import { FfInboundRequestView } from '../screens/ff/FfInboundRequestView'

export function makeDetail(id = 'A') {
  return {
    id, document_number: 'INB-000684', display_number: '№000684', waybill_number: null,
    warehouse_id: 'warehouse-A', status: 'sorting', operation_type: 'inbound', marketplace: 'wildberries',
    marketplace_warning: null, planned_delivery_date: '2026-10-02', planned_box_count: null,
    actual_box_count: null, boxes_discrepancy: false, has_discrepancy: false, seller_id: 'seller-A',
    seller_name: 'ИП Иванов', created_by_seller_id: null, created_at: '2026-09-28T12:00:00Z',
    distribution_completed_at: null, sorting_remaining_qty: 0,
    boxes: [1, 2, 3].map(n => ({ id: `${id}-box-${n}`, box_number: n,
      internal_barcode: `INB-0000000000000${n}`, free_text: null, pallet_id: null, pallet_code: null,
      storage_location_id: null, storage_location_code: null, label_printed_at: '2026-10-01T12:00:00Z',
      intake_opened_at: null, intake_closed_at: null, is_damaged: false, lines: [] })),
    cargo_places: [{ id: 'cargo-A', place_number: 1, internal_barcode: 'CARGO-1', label_printed_at: null }],
    lines: [{ id: 'line-A', product_id: 'product-A', sku_code: '000SKU', product_name: 'Товар А',
      wb_barcode: '0460000000011', requires_honest_sign: false, length_mm: null, width_mm: null,
      height_mm: null, weight_g: null, volume_liters: null, added_by_fulfillment: false,
      expected_qty: 10, actual_qty: 8, effective_actual_qty: 8, posted_qty: 0,
      storage_location_id: null, storage_location_code: null }],
  }
}
export type Detail = ReturnType<typeof makeDetail>
export const json = (body: unknown, status = 200) => new Response(JSON.stringify(body), {
  status, headers: { 'Content-Type': 'application/json' },
})

export async function flush() {
  await act(async () => { await Promise.resolve(); await Promise.resolve() })
}
export function byId(id: string): HTMLElement {
  const element = document.querySelector(`[data-testid="${id}"]`)
  expect(element, id).toBeTruthy()
  return element as HTMLElement
}
export async function click(node: HTMLElement) {
  await act(async () => node.click())
  await flush()
}

/** jsdom lacks Canvas2D. Adapt that browser boundary, while production
 * renderBarcodeDataUrl and the actual JsBarcode CODE128 encoder run unchanged.
 * Rectangles produced by JsBarcode become a real PNG for decoder/PDF checks. */
export function installCanvas() {
  const states = new WeakMap<HTMLCanvasElement, { x: number; y: number; style: string; png: PNG }>()
  const state = (canvas: HTMLCanvasElement) => {
    let result = states.get(canvas)
    if (!result) {
      result = { x: 0, y: 0, style: '#fff', png: new PNG({ width: canvas.width, height: canvas.height }) }
      states.set(canvas, result)
    }
    return result
  }
  const context = (canvas: HTMLCanvasElement): CanvasRenderingContext2D => {
    const fill = (x: number, y: number, w: number, h: number) => {
      const s = state(canvas)
      const shade = s.style === '#111' ? 17 : s.style === '#000' ? 0 : 255
      for (let iy = Math.max(0, Math.round(y + s.y)); iy < Math.min(canvas.height, y + s.y + h); iy++) {
        for (let ix = Math.max(0, Math.round(x + s.x)); ix < Math.min(canvas.width, x + s.x + w); ix++) {
          const index = (iy * canvas.width + ix) * 4
          s.png.data[index] = s.png.data[index + 1] = s.png.data[index + 2] = shade
          s.png.data[index + 3] = 255
        }
      }
    }
    return {
      get fillStyle() { return state(canvas).style },
      set fillStyle(value: string) { state(canvas).style = value },
      save() {}, restore() {}, translate(x: number, y: number) { state(canvas).x += x; state(canvas).y += y },
      clearRect() { state(canvas).png = new PNG({ width: canvas.width, height: canvas.height }) },
      fillRect: fill,
    } as unknown as CanvasRenderingContext2D
  }
  vi.spyOn(HTMLCanvasElement.prototype, 'getContext').mockImplementation(function (this: HTMLCanvasElement) {
    return context(this)
  })
  vi.spyOn(HTMLCanvasElement.prototype, 'toDataURL').mockImplementation(function (this: HTMLCanvasElement) {
    return `data:image/png;base64,${PNG.sync.write(state(this).png).toString('base64')}`
  })
}

export function harness() {
  ;(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true
  const host = document.createElement('div')
  document.body.append(host)
  let root: Root = createRoot(host)
  let current = makeDetail()
  let markMode: 'ok' | 'http' | 'lost' = 'ok'
  let fileMode: 'ok' | 'network' | 'blob' | 404 | 409 | 500 = 'ok'
  const downloads: Array<{ name: string; blob: Blob }> = []
  let blob: Blob
  const markCalls: string[] = []
  const fileCalls: string[] = []
  const fetcher = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input), method = init?.method ?? 'GET'
    if (url.endsWith(`/operations/inbound-intake-requests/${current.id}`) && method === 'GET') return json(current)
    if (url.includes('/products/linked-wb-catalog')) return json([])
    if (url.endsWith('/marking-codes')) return json({ items: [], checking: false })
    if (url.includes('/locations?exclude_sorting_zone=true')) return json([])
    if (url.endsWith('/warehouses')) return json([{ id: 'warehouse-A', name: 'Склад' }])
    if (url.endsWith('/mark-label-printed') && method === 'POST') {
      markCalls.push(url)
      if (markMode === 'http') return json({ detail: 'label mark failed' }, 503)
      if (markMode === 'lost') {
        current.boxes = current.boxes.map(box => url.includes(box.id) ? { ...box, label_printed_at: '2026-10-06T12:00:00Z' } : box)
        throw new TypeError('label response lost after commit')
      }
      return json({})
    }
    if (/\/acceptance-act\.(pdf|xlsx)$/.test(url)) {
      fileCalls.push(url)
      if (typeof fileMode === 'number') return json({ detail: `act failure ${fileMode}` }, fileMode)
      if (fileMode === 'network') throw new TypeError('act network failure')
      const format = url.endsWith('.pdf') ? 'pdf' : 'xlsx'
      const name = `Акт приёмки ${current.display_number} от ${current.id === 'A' ? '28.09.2026' : '20.09.2026'}.${format}`
      const response = new Response(format === 'pdf' ? '%PDF-fixture' : 'xlsx-fixture', {
        headers: { 'Content-Type': format === 'pdf' ? 'application/pdf' : 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
          'Content-Disposition': `attachment; filename*=UTF-8''${encodeURIComponent(name)}` },
      })
      if (fileMode === 'blob') response.blob = async () => { throw new Error('act blob read failure') }
      return response
    }
    throw new Error(`Unexpected request: ${method} ${url}`)
  })
  vi.stubGlobal('fetch', fetcher)
  window.__WMS_CAPTURE_PRINT_HTML__ = true
  window.__WMS_LAST_PRINT_HTML__ = undefined
  const oldScroll = Element.prototype.scrollIntoView
  Element.prototype.scrollIntoView = () => undefined
  vi.stubGlobal('URL', class extends URL {
    static createObjectURL(value: Blob) { blob = value; return 'blob:contract' }
    static revokeObjectURL() {}
  })
  vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(function (this: HTMLAnchorElement) {
    downloads.push({ name: this.download, blob })
  })
  installCanvas()
  return {
    get current() { return current }, set current(value: Detail) { current = value },
    set markMode(value: typeof markMode) { markMode = value }, set fileMode(value: typeof fileMode) { fileMode = value },
    fetcher, downloads, markCalls, fileCalls,
    async render(numbered = true) {
      await act(async () => root.render(<FfInboundRequestView token="contract" requestId={current.id}
        isFulfillmentAdmin workspace="reception" numberedInboundBoxLabels={numbered} onClose={() => undefined} />))
      await flush()
    },
    async remount(numbered = true) {
      await act(async () => root.unmount())
      root = createRoot(host)
      await this.render(numbered)
    },
    async print(all = false, index = 2, size = '58x40', cargo = false) {
      window.localStorage.setItem('wms.print.labelSizeId', size)
      if (!document.querySelector('[data-testid="ff-inbound-boxes-panel"]')) await click(byId('ff-inbound-packages-toggle'))
      await click(byId(cargo ? 'ff-inbound-cargo-place-print-cargo-A' : all ? 'ff-inbound-boxes-print-all' : `ff-inbound-box-print-${current.id}-box-${index}`))
      await click(byId('ff-inbound-box-print-dialog-confirm'))
      const html = window.__WMS_LAST_PRINT_HTML__
      expect(html, 'production printBarcodeLabels must produce HTML').toBeTruthy()
      return new DOMParser().parseFromString(html!, 'text/html')
    },
    async dispose() {
      await act(async () => root.unmount())
      host.remove()
      document.querySelectorAll('iframe').forEach(node => node.remove())
      Element.prototype.scrollIntoView = oldScroll
      vi.unstubAllGlobals()
      vi.restoreAllMocks()
      window.localStorage.clear()
    },
  }
}

/** Accept an existing button/menu/select choice; do not prescribe a new UI. */
export async function chooseAct(format: 'pdf' | 'xlsx') {
  const callsBefore = vi.mocked(fetch).mock.calls.length
  const pattern = format === 'pdf' ? /PDF/i : /Excel|XLSX/i
  const candidates = () => [...document.querySelectorAll<HTMLElement>('button,[role="menuitem"],[role="option"],option')]
    .filter(node => node.textContent?.match(pattern))
  let target = candidates()[0]
  if (!target) {
    const combo = [...document.querySelectorAll<HTMLElement>('[role="combobox"]')]
      .find(node => node.textContent?.match(/PDF|Excel|XLSX/i))
    await click(combo ?? byId('ff-inbound-acceptance-act'))
    target = candidates()[0]
    // The legacy action can remain the direct Excel action.
    if (!target && format === 'xlsx') return
  }
  expect(target, `visible ${format} choice in existing act context`).toBeTruthy()
  if (target!.tagName === 'OPTION') {
    const select = target!.parentElement as HTMLSelectElement
    await act(async () => { select.value = (target as HTMLOptionElement).value; select.dispatchEvent(new Event('change', { bubbles: true })) })
    await click(byId('ff-inbound-acceptance-act'))
  } else {
    await click(target!)
    const requested = vi.mocked(fetch).mock.calls.slice(callsBefore).some(([input]) =>
      String(input).endsWith(`/acceptance-act.${format}`),
    )
    // A format menu item may download directly; a select/toggle may merely
    // choose a format. Exercise the existing act button only in the latter case.
    if (!requested) await click(byId('ff-inbound-acceptance-act'))
  }
}
