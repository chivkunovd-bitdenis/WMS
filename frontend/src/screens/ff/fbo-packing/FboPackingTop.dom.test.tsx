// @vitest-environment jsdom
import { act } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from 'vitest'

const mocks = vi.hoisted(() => ({
  printPrepared: vi.fn(async (_input: { idempotencyKey: string }) => undefined),
  waybill: vi.fn(),
  soundOk: vi.fn(),
  soundError: vi.fn(),
}))

vi.mock('../../../utils/printPreparedQr', () => ({ printPreparedQr: mocks.printPrepared }))
vi.mock('../../../utils/czLabelPng', () => ({
  renderCzLabelPng: async () => 'data:image/png;base64,CZ',
  renderLabelSectionPng: async () => 'data:image/png;base64,LABEL',
}))
vi.mock('../../../utils/renderBarcodeDataUrl', () => ({ renderBarcodeDataUrl: () => 'data:image/png;base64,BC' }))
vi.mock('../../../utils/printShipmentPackagingSheet', () => ({ printShipmentPackagingSheet: mocks.waybill }))
vi.mock('../../../utils/scanFeedback', () => ({ playScanSuccess: mocks.soundOk, playScanError: mocks.soundError }))

import { FboPackingTop } from './FboPackingTop'
import type { FboMarkingCode, FboPackingDetail } from './fboPackingTypes'

beforeAll(() => {
  ;(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true
})

const TOKEN = `x.${btoa(JSON.stringify({ sub: 'u1', tenant_id: 't1' }))}.y`
const KIZ = '0104650000000011215abcdefghij1\x1d91EE06\x1d92dGVzdHNpZ25hdHVyZXRlc3RzaWduYXR1cmV0ZXN0c2lnbmF0dXJl'
const PREFIX = '/api/operations/marketplace-unload-requests/R1'

function baseDetail(overrides: Partial<FboPackingDetail> = {}): FboPackingDetail {
  return {
    id: 'R1',
    document_number: 'MP-000001',
    warehouse_name: 'Склад',
    seller_name: 'Селлер',
    marketplace: 'wb',
    status: 'collecting',
    created_at: '2026-10-09T00:00:00Z',
    lines: [
      { id: 'L1', product_id: 'p1', sku_code: 'SKU1', product_name: 'Футболка', quantity: 30, picked_qty: 20, requires_honest_sign: true },
      { id: 'L2', product_id: 'p2', sku_code: 'SKU2', product_name: 'Носки', quantity: 5, picked_qty: 5, requires_honest_sign: false },
    ],
    boxes: [
      { id: 'B1', internal_barcode: 'INB-0001', lines: [{ id: 'BL1', product_id: 'p1', sku_code: 'SKU1', product_name: 'Футболка', quantity: 20 }] },
    ],
    pick_allocations: [],
    ...overrides,
  }
}

function code(id: string, productId = 'p1'): FboMarkingCode {
  return {
    marking_code_id: id,
    cis_code: `CIS-${id}-0104650000000011215abc`,
    product_id: productId,
    line_id: 'L1',
    status: 'applied',
    intake_document_number: id === 'c1' ? '000123' : null,
    linked_at: null,
    has_label_artifact: false,
  }
}

type Call = { method: string; path: string; body: Record<string, unknown> | null }
type Handler = (body: Record<string, unknown> | null) => { status?: number; body?: unknown }

let host: HTMLDivElement
let root: Root
let calls: Call[]
let handlers: Map<string, Handler>
let serverCodes: FboMarkingCode[]
let onChanged: ReturnType<typeof vi.fn>
let onBoxBarcodeScanned: ReturnType<typeof vi.fn>

const catalog = [
  {
    id: 'p1', name: 'Футболка', sku_code: 'SKU1', wb_nm_id: 111, wb_vendor_code: 'ART-1', wb_size: 'M',
    wb_color: null, wb_primary_image_url: null, wb_barcodes: ['2000000000011'], wb_primary_barcode: '2000000000011',
    packaging_instructions: 'Сложить вдвое', marketplace_bindings: [], requires_honest_sign: true,
  },
  {
    id: 'p2', name: 'Носки', sku_code: 'SKU2', wb_nm_id: 222, wb_vendor_code: 'ART-2', wb_size: null,
    wb_color: null, wb_primary_image_url: null, wb_barcodes: ['2000000000028'], wb_primary_barcode: '2000000000028',
    packaging_instructions: null, marketplace_bindings: [], requires_honest_sign: false,
  },
]

function installFetch() {
  vi.stubGlobal('fetch', async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input)
    const method = (init?.method ?? 'GET').toUpperCase()
    const path = url.startsWith(PREFIX) ? url.slice(PREFIX.length) : url.replace('/api', '')
    const raw = typeof init?.body === 'string' ? (JSON.parse(init.body) as Record<string, unknown>) : null
    calls.push({ method, path, body: raw })
    const handler = handlers.get(`${method} ${path}`)
    if (!handler) return new Response(JSON.stringify({ detail: `no handler ${method} ${path}` }), { status: 500 })
    const answer = handler(raw)
    return new Response(answer.status === 204 ? null : JSON.stringify(answer.body ?? {}), { status: answer.status ?? 200 })
  })
}

async function flush() {
  for (let i = 0; i < 6; i += 1) {
    await act(async () => { await new Promise((resolve) => setTimeout(resolve, 0)) })
  }
}

async function mount(detail = baseDetail(), currentBoxId: string | null = 'B1', disabled = false) {
  await act(async () => {
    root.render(
      <FboPackingTop
        token={TOKEN}
        authHeaders={{ Authorization: 'Bearer test' }}
        detail={detail}
        currentBoxId={currentBoxId}
        onBoxBarcodeScanned={onBoxBarcodeScanned as (code: string) => Promise<void>}
        onChanged={onChanged as () => void}
        disabled={disabled}
      />,
    )
  })
  await flush()
}

const q = (id: string) => host.querySelector<HTMLElement>(`[data-testid="${id}"]`)

async function scan(value: string) {
  const input = q('fbo-packing-scan-input') as HTMLInputElement
  await act(async () => {
    Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value')!.set!.call(input, value)
    input.dispatchEvent(new Event('input', { bubbles: true }))
  })
  await act(async () => {
    input.dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter', bubbles: true, cancelable: true }))
  })
  await flush()
}

async function click(id: string) {
  const el = q(id)
  if (!el) throw new Error(`нет элемента ${id}`)
  await act(async () => { el.click() })
  await flush()
}

const posts = (path: string) => calls.filter((call) => call.method === 'POST' && call.path === path)

beforeEach(() => {
  window.localStorage.clear()
  calls = []
  handlers = new Map()
  serverCodes = []
  onChanged = vi.fn()
  onBoxBarcodeScanned = vi.fn(async () => undefined)
  mocks.printPrepared.mockReset()
  mocks.printPrepared.mockResolvedValue(undefined)
  mocks.waybill.mockReset()
  mocks.soundOk.mockReset()
  mocks.soundError.mockReset()
  handlers.set('GET /products/linked-wb-catalog', () => ({ body: catalog }))
  handlers.set('GET /marking-codes', () => ({ body: { items: serverCodes } }))
  handlers.set('POST /boxes/B1/scan', () => ({ body: { kind: 'product', product_id: 'p1', quantity: 1, picked_qty: 20 } }))
  installFetch()
  host = document.createElement('div')
  document.body.append(host)
  root = createRoot(host)
})

afterEach(() => {
  act(() => root.unmount())
  host.remove()
  vi.unstubAllGlobals()
})

describe('WMS-686 FBO упаковка · общая таблица (R26, R27)', () => {
  it('«Нужно» P, «В коробах» B, «ЧЗ» K из P; без ЧЗ — «не требуется», без красного', async () => {
    serverCodes = [code('c1'), code('c2'), code('c3'), code('c4'), code('c5')]
    await mount()
    expect(q('fbo-packing-need-p1')?.textContent).toBe('30')
    expect(q('fbo-packing-boxed-p1')?.textContent).toBe('20')
    expect(q('fbo-packing-chz-p1')?.textContent).toBe('5 из 30')
    expect(q('fbo-packing-chz-hint-p1')?.getAttribute('aria-label')).toContain('КИЗ этих единиц не сканировали')
    expect(q('ff-packaging-line-marking-incomplete')).not.toBeNull()
    expect(q('fbo-packing-chz-none-p2')?.textContent).toBe('не требуется')
    expect(q('fbo-packing-chz-hint-p2')).toBeNull()
    expect(host.textContent).toContain('Нужно')
    expect(host.textContent).toContain('В коробах')
  })

  it('K = P: счётчик обычный, значка «!» нет', async () => {
    serverCodes = Array.from({ length: 30 }, (_, i) => code(`k${i}`))
    await mount()
    expect(q('fbo-packing-chz-p1')?.textContent).toBe('30 из 30')
    expect(q('fbo-packing-chz-hint-p1')).toBeNull()
  })

  it('K = P: счётчик нейтральный (не зелёная заливка); красный только при нехватке', async () => {
    serverCodes = Array.from({ length: 30 }, (_, i) => code(`k${i}`))
    await mount()
    const full = q('fbo-packing-chz-p1')!.className
    expect(full).not.toContain('MuiChip-filled')
    expect(full).not.toContain('colorSuccess')
    expect(full).not.toContain('colorError')
    expect(q('fbo-packing-chz-none-p2')!.className).toContain('MuiChip-outlined')
    expect(full).toContain('MuiChip-outlined')
    await act(async () => { root.unmount() })
    root = createRoot(host)
    serverCodes = [code('c1')]
    await mount()
    expect(q('fbo-packing-chz-p1')!.className).toContain('colorError')
  })

  it('режим просмотра (после проведения): таблица видна, скан, печать и отвязка недоступны', async () => {
    serverCodes = [code('c1'), code('c2')]
    await mount(baseDetail({ status: 'shipped' }), 'B1', true)
    expect(q('fbo-packing-need-p1')?.textContent).toBe('30')
    expect(q('fbo-packing-chz-p1')?.textContent).toBe('2 из 30')
    expect((q('fbo-packing-scan-input') as HTMLInputElement).disabled).toBe(true)
    expect((q('ff-packaging-line-print-L1') as HTMLButtonElement).disabled).toBe(true)
    expect((q('ff-packaging-print-sheet') as HTMLButtonElement).disabled).toBe(true)
    expect(host.querySelector<HTMLInputElement>('[data-testid="fbo-scan-print-chz-toggle"] input')!.disabled).toBe(true)
    // список КИЗ раскрывается для просмотра, но отвязать и перепечатать нельзя
    await click('fbo-packing-chz-p1')
    expect(q('fbo-packing-code-c1')).not.toBeNull()
    expect((q('fbo-packing-code-unbind-c1') as HTMLButtonElement).disabled).toBe(true)
    expect((q('fbo-packing-code-reprint-c1') as HTMLButtonElement).disabled).toBe(true)
  })

  it('нажатие на число раскрывает вертикальный список кодов с номером приёмки, повторное скрывает', async () => {
    serverCodes = [code('c1'), code('c2')]
    await mount()
    expect(q('fbo-packing-codes-p1')).toBeNull()
    await click('fbo-packing-chz-p1')
    expect(q('fbo-packing-codes-p1')?.querySelectorAll('[data-testid^="fbo-packing-code-c"]').length).toBeGreaterThanOrEqual(2)
    expect(q('fbo-packing-code-c1')?.textContent).toContain('приёмка №000123')
    expect(q('fbo-packing-code-c2')?.textContent).not.toContain('приёмка')
    await click('fbo-packing-chz-p1')
    expect(q('fbo-packing-codes-p1')).toBeNull()
  })

  it('крестик отвязывает код (DELETE), «Перепечатать» печатает код новым ключом', async () => {
    serverCodes = [code('c1')]
    handlers.set('DELETE /marking-codes/c1', () => {
      serverCodes = []
      return { status: 204 }
    })
    await mount()
    await click('fbo-packing-chz-p1')
    await click('fbo-packing-code-reprint-c1')
    await click('fbo-packing-code-reprint-c1')
    const keys = mocks.printPrepared.mock.calls.map((call) => call[0].idempotencyKey)
    expect(keys).toHaveLength(2)
    expect(new Set(keys).size).toBe(2)
    expect(keys[0]).toMatch(/^fbo-chz-re:c1:/)
    await click('fbo-packing-code-unbind-c1')
    expect(calls.some((call) => call.method === 'DELETE' && call.path === '/marking-codes/c1')).toBe(true)
    expect(q('fbo-packing-chz-p1')?.textContent).toBe('0 из 30')
    expect(onChanged).toHaveBeenCalled()
  })

  it('красный ЧЗ ничего не блокирует: поле скана и кнопки доступны', async () => {
    await mount()
    expect(q('fbo-packing-chz-p1')?.textContent).toBe('0 из 30')
    expect((q('fbo-packing-scan-input') as HTMLInputElement).disabled).toBe(false)
    expect((q('ff-packaging-line-print-L1') as HTMLButtonElement).disabled).toBe(false)
    expect(host.textContent).not.toContain('Допечатать')
  })
})

describe('WMS-686 FBO упаковка · скан (R29–R31)', () => {
  it('ШК короба уходит родителю, запросов по товару нет', async () => {
    await mount()
    await scan('INB-0001')
    expect(onBoxBarcodeScanned).toHaveBeenCalledWith('INB-0001')
    expect(calls.filter((call) => call.method === 'POST')).toHaveLength(0)
    expect(mocks.soundOk).toHaveBeenCalled()
  })

  it('ШК товара без текущего короба: «Сначала отсканируйте или создайте короб», запросов нет', async () => {
    await mount(baseDetail(), null)
    await scan('2000000000011')
    expect(q('fbo-packing-scan-error')?.textContent).toBe('Сначала отсканируйте или создайте короб')
    expect(calls.filter((call) => call.method === 'POST')).toHaveLength(0)
    expect(mocks.soundError).toHaveBeenCalled()
  })

  it('ШК товара кладёт одну штуку в текущий короб тем же путём, что «Наполнить», с mutation_id; галки выключены — печати нет', async () => {
    await mount()
    await scan('2000000000011')
    const [request] = posts('/boxes/B1/scan')
    expect(request?.body).toMatchObject({ barcode: '2000000000011', quantity: 1, allow_over_plan: false, product_id: 'p1' })
    expect(typeof request?.body?.mutation_id).toBe('string')
    expect(onChanged).toHaveBeenCalled()
    expect(mocks.printPrepared).not.toHaveBeenCalled()
    expect(posts('/marking-codes/issue')).toHaveLength(0)
    expect(q('fbo-packing-scan-error')).toBeNull()
  })

  it('потеря ответа на скан штуки: один автоматический повтор тем же телом и тем же mutation_id, штука не задваивается', async () => {
    let attempts = 0
    handlers.set('POST /boxes/B1/scan', () => {
      attempts += 1
      if (attempts === 1) return { status: 503, body: { detail: 'unavailable' } }
      return { body: { kind: 'product', product_id: 'p1', quantity: 1, picked_qty: 20 } }
    })
    await mount()
    await scan('2000000000011')
    const requests = posts('/boxes/B1/scan')
    expect(requests).toHaveLength(2)
    expect(requests[0]?.body).toEqual(requests[1]?.body)
    expect(requests[0]?.body?.mutation_id).toBe(requests[1]?.body?.mutation_id)
    expect(q('fbo-packing-scan-error')).toBeNull()
    expect(onChanged).toHaveBeenCalled()
  })

  /** Сервер: штука ложится по новому mutation_id один раз; тот же ключ возвращает прежний результат. */
  function serverApplyingByKey(lostResponses: number) {
    const applied = new Set<string>()
    let answers = 0
    handlers.set('POST /boxes/B1/scan', (body) => {
      applied.add(String(body?.mutation_id))
      answers += 1
      if (answers <= lostResponses) return { status: 503, body: { detail: 'unavailable' } }
      return { body: { kind: 'product', product_id: 'p1', quantity: 1, picked_qty: 20 } }
    })
    return applied
  }

  it('два потерянных ответа подряд: ручной повтор того же скана уходит с прежним ключом, штука не задваивается', async () => {
    const applied = serverApplyingByKey(2)
    await mount()
    await scan('2000000000011')
    expect(posts('/boxes/B1/scan')).toHaveLength(2)
    expect(q('fbo-packing-scan-error')).not.toBeNull()
    await scan('2000000000011')
    const requests = posts('/boxes/B1/scan')
    expect(requests).toHaveLength(3)
    expect(requests[2]?.body).toEqual(requests[0]?.body)
    expect(requests[2]?.body?.mutation_id).toBe(requests[0]?.body?.mutation_id)
    expect(applied.size).toBe(1)
    expect(q('fbo-packing-scan-error')).toBeNull()
  })

  it('после определённого ответа операция снята: следующий скан того же кода — новый ключ', async () => {
    const applied = serverApplyingByKey(2)
    await mount()
    await scan('2000000000011')
    await scan('2000000000011')
    await scan('2000000000011')
    const requests = posts('/boxes/B1/scan')
    expect(requests).toHaveLength(4)
    expect(requests[3]?.body?.mutation_id).not.toBe(requests[0]?.body?.mutation_id)
    expect(applied.size).toBe(2)
  })

  it('ручной повтор получил отказ сервера (4xx): операция снята, следующий скан — новый ключ', async () => {
    let answers = 0
    handlers.set('POST /boxes/B1/scan', () => {
      answers += 1
      if (answers <= 2) return { status: 503, body: { detail: 'unavailable' } }
      if (answers === 3) return { status: 422, body: { detail: 'plan_limit_exceeded' } }
      return { body: { kind: 'product', product_id: 'p1', quantity: 1, picked_qty: 20 } }
    })
    await mount()
    await scan('2000000000011')
    await scan('2000000000011')
    expect(q('fbo-packing-scan-error')?.textContent).toBe('Нельзя добавить больше, чем в плане отгрузки.')
    await scan('2000000000011')
    const requests = posts('/boxes/B1/scan')
    expect(requests).toHaveLength(4)
    expect(requests[2]?.body?.mutation_id).toBe(requests[0]?.body?.mutation_id)
    expect(requests[3]?.body?.mutation_id).not.toBe(requests[0]?.body?.mutation_id)
  })

  it('другой код или другой короб не подхватывает чужую незавершённую операцию', async () => {
    handlers.set('POST /boxes/B1/scan', () => ({ status: 503, body: { detail: 'unavailable' } }))
    await mount()
    await scan('2000000000011')
    handlers.set('POST /boxes/B1/scan', () => ({ body: { kind: 'product', product_id: 'p2', quantity: 1, picked_qty: 5 } }))
    await scan('2000000000028')
    const requests = posts('/boxes/B1/scan')
    expect(requests).toHaveLength(3)
    expect(requests[2]?.body?.mutation_id).not.toBe(requests[0]?.body?.mutation_id)
  })

  it('отказ сервера по скану штуки не повторяется', async () => {
    handlers.set('POST /boxes/B1/scan', () => ({ status: 422, body: { detail: 'plan_limit_exceeded' } }))
    await mount()
    await scan('2000000000011')
    expect(posts('/boxes/B1/scan')).toHaveLength(1)
  })

  it('КИЗ сразу после ШК товара идёт с product_id этого товара; следующий КИЗ — без подсказки', async () => {
    handlers.set('POST /marking-codes/scan', () => ({ body: { marking_code_id: 'c1', product_id: 'p1', already_linked: false, kiz_count: 1 } }))
    await mount()
    await scan('2000000000011')
    await scan(KIZ)
    await scan(`${KIZ}2`)
    const kizPosts = posts('/marking-codes/scan')
    expect(kizPosts).toHaveLength(2)
    expect(kizPosts[0]?.body).toMatchObject({ code: KIZ, product_id: 'p1' })
    expect(kizPosts[1]?.body?.product_id).toBeUndefined()
  })

  it('отказ сервера по КИЗ показывается красным текстом ТЗ, звук ошибки', async () => {
    handlers.set('POST /marking-codes/scan', () => ({ status: 422, body: { detail: 'marking_quantity_exceeded' } }))
    await mount()
    await scan(KIZ)
    expect(q('fbo-packing-scan-error')?.textContent).toBe('Сначала отсканируйте ШК следующей штуки.')
    expect(mocks.soundError).toHaveBeenCalled()
  })

  it('повтор того же КИЗ — нейтральное сообщение без красного', async () => {
    handlers.set('POST /marking-codes/scan', () => ({ body: { marking_code_id: 'c1', product_id: 'p1', already_linked: true, kiz_count: 1 } }))
    await mount()
    await scan('2000000000011')
    await scan(KIZ)
    expect(q('fbo-packing-scan-error')).toBeNull()
    expect(q('fbo-packing-scan-notice')?.textContent).toBe('Этот КИЗ уже привязан к товару')
  })

  it('отказ по товару оставляет введённое руками в поле', async () => {
    handlers.set('POST /boxes/B1/scan', () => ({ status: 422, body: { detail: 'barcode_unknown' } }))
    await mount()
    await scan('999')
    expect(q('fbo-packing-scan-error')?.textContent).toBe('Штрихкод не найден. Проверьте товар.')
    expect((q('fbo-packing-scan-input') as HTMLInputElement).value).toBe('999')
  })
})

describe('WMS-686 FBO упаковка · галки печати (R25)', () => {
  const toggle = (id: string) => host.querySelector<HTMLInputElement>(`[data-testid="${id}"] input`)!

  it('две галки, выкл. по умолчанию, хранятся под ключом FBO', async () => {
    await mount()
    expect(host.textContent).toContain('Печатать ШК')
    expect(host.textContent).toContain('Печатать ЧЗ')
    expect(host.textContent).not.toContain('Печатать QR')
    expect(toggle('fbo-scan-print-barcode-toggle').checked).toBe(false)
    expect(toggle('fbo-scan-print-chz-toggle').checked).toBe(false)
    await act(async () => { toggle('fbo-scan-print-chz-toggle').click() })
    expect(window.localStorage.getItem('wms:fbo:scan-auto-print:t1:u1')).toContain('"printChz":true')
  })

  it('обе включены: на скан штуки печатается ШК и выдаётся и печатается один код ЧЗ (quantity=1, свой mutation_id)', async () => {
    const issued = code('n1')
    handlers.set('POST /marking-codes/issue', () => {
      serverCodes = [issued]
      return { body: { items: [issued], shortage: 0 } }
    })
    await mount()
    await act(async () => { toggle('fbo-scan-print-barcode-toggle').click() })
    await act(async () => { toggle('fbo-scan-print-chz-toggle').click() })
    await scan('2000000000011')
    await scan('2000000000011')
    const issues = posts('/marking-codes/issue')
    expect(issues).toHaveLength(2)
    expect(issues[0]?.body).toMatchObject({ product_id: 'p1', quantity: 1 })
    expect(issues[0]?.body?.mutation_id).not.toBe(issues[1]?.body?.mutation_id)
    const keys = mocks.printPrepared.mock.calls.map((call) => call[0].idempotencyKey)
    expect(keys.filter((key) => key.startsWith('fbo-bc:R1:'))).toHaveLength(2)
    expect(keys.filter((key) => key === 'fbo-chz:n1')).toHaveLength(2)
  })

  it('потеря ответа на выдачу ЧЗ со скана: один повтор тем же mutation_id, код выдан и напечатан один раз', async () => {
    const issued = code('n1')
    let attempts = 0
    handlers.set('POST /marking-codes/issue', () => {
      attempts += 1
      if (attempts === 1) return { status: 503, body: { detail: 'unavailable' } }
      serverCodes = [issued]
      return { body: { items: [issued], shortage: 0 } }
    })
    await mount()
    await act(async () => { toggle('fbo-scan-print-chz-toggle').click() })
    await scan('2000000000011')
    const issues = posts('/marking-codes/issue')
    expect(issues).toHaveLength(2)
    expect(issues[0]?.body?.mutation_id).toBe(issues[1]?.body?.mutation_id)
    expect(issues[0]?.body).toEqual(issues[1]?.body)
    expect(q('fbo-packing-scan-error')).toBeNull()
    const keys = mocks.printPrepared.mock.calls.map((call) => call[0].idempotencyKey)
    expect(keys.filter((key) => key === 'fbo-chz:n1')).toHaveLength(1)
  })

  it('два потерянных ответа на выдачу ЧЗ: ручной повтор скана уходит с прежними ключами добавления и выдачи, код выдан и напечатан один раз', async () => {
    const issued = code('n1')
    const issuedKeys = new Set<string>()
    let answers = 0
    handlers.set('POST /marking-codes/issue', (body) => {
      issuedKeys.add(String(body?.mutation_id))
      answers += 1
      if (answers <= 2) return { status: 503, body: { detail: 'unavailable' } }
      serverCodes = [issued]
      return { body: { items: [issued], shortage: 0 } }
    })
    await mount()
    await act(async () => { toggle('fbo-scan-print-chz-toggle').click() })
    await scan('2000000000011')
    expect(posts('/marking-codes/issue')).toHaveLength(2)
    expect(q('fbo-packing-scan-error')?.textContent).toContain('Штука уложена в короб.')
    expect(mocks.printPrepared).not.toHaveBeenCalled()
    await scan('2000000000011')
    const adds = posts('/boxes/B1/scan')
    const issues = posts('/marking-codes/issue')
    expect(adds).toHaveLength(2)
    expect(adds[1]?.body?.mutation_id).toBe(adds[0]?.body?.mutation_id)
    expect(issues).toHaveLength(3)
    expect(issues[2]?.body?.mutation_id).toBe(issues[0]?.body?.mutation_id)
    expect(issuedKeys.size).toBe(1)
    expect(q('fbo-packing-scan-error')).toBeNull()
    const keys = mocks.printPrepared.mock.calls.map((call) => call[0].idempotencyKey)
    expect(keys.filter((key) => key === 'fbo-chz:n1')).toHaveLength(1)
    // Операция завершена определённым ответом: следующий скан берёт новые ключи.
    await scan('2000000000011')
    const nextAdd = posts('/boxes/B1/scan')[2]
    const nextIssue = posts('/marking-codes/issue')[3]
    expect(nextAdd?.body?.mutation_id).not.toBe(adds[0]?.body?.mutation_id)
    expect(nextIssue?.body?.mutation_id).not.toBe(issues[0]?.body?.mutation_id)
  })

  it('пустой пул при скане: штука остаётся уложенной, красное сообщение, ложного успеха нет', async () => {
    handlers.set('POST /marking-codes/issue', () => ({ status: 422, body: { detail: 'marking_pool_empty' } }))
    await mount()
    await act(async () => { toggle('fbo-scan-print-chz-toggle').click() })
    await scan('2000000000011')
    expect(posts('/boxes/B1/scan')).toHaveLength(1)
    expect(q('fbo-packing-scan-error')?.textContent).toContain('Штука уложена в короб.')
    expect(q('fbo-packing-scan-error')?.textContent).toContain('В пуле нет свободных КИЗ этого товара.')
    expect(mocks.printPrepared).not.toHaveBeenCalled()
  })

  it('товар без ЧЗ: «Печатать ЧЗ» код не выдаёт', async () => {
    handlers.set('POST /boxes/B1/scan', () => ({ body: { kind: 'product', product_id: 'p2', quantity: 1, picked_qty: 5 } }))
    await mount()
    await act(async () => { toggle('fbo-scan-print-chz-toggle').click() })
    await scan('2000000000028')
    expect(posts('/marking-codes/issue')).toHaveLength(0)
  })
})

describe('WMS-686 FBO упаковка · «ШК + ЧЗ» (R51); «Допечатать» убрана', () => {
  const lineOf = (quantity: number, picked: number, requires = true) =>
    baseDetail({
      lines: [{ id: 'L1', product_id: 'p1', sku_code: 'SKU1', product_name: 'Футболка', quantity, picked_qty: picked, requires_honest_sign: requires }],
    })
  const printKeys = () => mocks.printPrepared.mock.calls.map((call) => call[0].idempotencyKey)
  const barcodeKeys = () => printKeys().filter((key) => key.startsWith('fbo-bc:R1:'))
  const chzKeys = () => printKeys().filter((key) => key.startsWith('fbo-chz'))

  it('кнопки «Допечатать» нигде нет', async () => {
    serverCodes = [code('c1')]
    await mount()
    expect(host.textContent).not.toContain('Допечатать')
    expect(host.querySelector('[data-testid^="fbo-packing-reissue"]')).toBeNull()
  })

  it('S = 0: кнопка активна, ШК × P, выдаются только недостающие N − K, печатаются только выданные', async () => {
    serverCodes = [code('c1')]
    handlers.set('POST /marking-codes/issue', () => {
      const added = [code('n1'), code('n2')]
      serverCodes = [...serverCodes, ...added]
      return { body: { items: added, shortage: 0 } }
    })
    await mount(lineOf(3, 0))
    expect((q('ff-packaging-line-print-L1') as HTMLButtonElement).disabled).toBe(false)
    await click('ff-packaging-line-print-L1')
    const [issue] = posts('/marking-codes/issue')
    expect(issue?.body).toMatchObject({ product_id: 'p1', quantity: 2 })
    expect(typeof issue?.body?.mutation_id).toBe('string')
    expect(barcodeKeys()).toHaveLength(3)
    expect(chzKeys()).toEqual(['fbo-chz:n1', 'fbo-chz:n2'])
    expect(q('fbo-packing-chz-p1')?.textContent).toBe('3 из 3')
  })

  it('S > 0: N = подобрано, quantity = N − K', async () => {
    serverCodes = [code('c1'), code('c2')]
    handlers.set('POST /marking-codes/issue', () => ({ body: { items: [], shortage: 0 } }))
    await mount(lineOf(30, 10))
    await click('ff-packaging-line-print-L1')
    expect(posts('/marking-codes/issue')[0]?.body).toMatchObject({ product_id: 'p1', quantity: 8 })
    expect(barcodeKeys()).toHaveLength(10)
  })

  it('нехватка в пуле: «Выдано N из M: в пуле не хватает КИЗ», ШК напечатаны', async () => {
    handlers.set('POST /marking-codes/issue', () => ({ body: { items: [code('n1'), code('n2'), code('n3')], shortage: 2 } }))
    await mount(lineOf(10, 10))
    await click('ff-packaging-line-print-L1')
    expect(q('fbo-packing-row-message-p1')?.textContent).toBe('Выдано 3 из 5: в пуле не хватает КИЗ')
    expect(barcodeKeys()).toHaveLength(10)
    expect(chzKeys()).toHaveLength(3)
  })

  it('выдавать нечего (K ≥ N): печатаются одни ШК, выдача не вызывается, ошибки нет', async () => {
    serverCodes = [code('c1'), code('c2'), code('c3'), code('c4')]
    await mount(lineOf(10, 4))
    await click('ff-packaging-line-print-L1')
    expect(posts('/marking-codes/issue')).toHaveLength(0)
    expect(barcodeKeys()).toHaveLength(4)
    expect(chzKeys()).toHaveLength(0)
    expect(q('fbo-packing-row-message-p1')).toBeNull()
  })

  it('сервер ответил nothing_to_issue: не ошибка, ШК напечатаны', async () => {
    handlers.set('POST /marking-codes/issue', () => ({ status: 422, body: { detail: 'nothing_to_issue' } }))
    await mount(lineOf(3, 3))
    await click('ff-packaging-line-print-L1')
    expect(barcodeKeys()).toHaveLength(3)
    expect(q('fbo-packing-row-message-p1')).toBeNull()
  })

  it('пустой пул: ШК печатаются, понятное сообщение, привязанные коды не перепечатываются', async () => {
    serverCodes = [code('c1')]
    handlers.set('POST /marking-codes/issue', () => ({ status: 422, body: { detail: 'marking_pool_empty' } }))
    await mount(lineOf(3, 2))
    await click('ff-packaging-line-print-L1')
    expect(barcodeKeys()).toHaveLength(2)
    expect(chzKeys()).toHaveLength(0)
    expect(q('fbo-packing-row-message-p1')?.textContent).toBe('В пуле нет свободных КИЗ этого товара.')
  })

  it('товар без ЧЗ: печатается только ШК', async () => {
    await mount()
    await click('ff-packaging-line-print-L2')
    expect(barcodeKeys()).toHaveLength(5)
    expect(chzKeys()).toHaveLength(0)
    expect(posts('/marking-codes/issue')).toHaveLength(0)
  })

  it('сбой печати выданного кода: код остаётся привязанным, повтор печатает тот же код тем же ключом и новых не выдаёт', async () => {
    let failed = false
    mocks.printPrepared.mockImplementation(async (input: { idempotencyKey: string }) => {
      if (input.idempotencyKey === 'fbo-chz:n1' && !failed) {
        failed = true
        throw new Error('Нет ответа WMS Print.')
      }
    })
    handlers.set('POST /marking-codes/issue', () => {
      serverCodes = [code('n1')]
      return { body: { items: [code('n1')], shortage: 0 } }
    })
    await mount(lineOf(1, 1))
    await click('ff-packaging-line-print-L1')
    expect(q('fbo-packing-row-message-p1')?.textContent).toContain('Нет ответа WMS Print.')
    await click('ff-packaging-line-print-L1')
    expect(posts('/marking-codes/issue')).toHaveLength(1)
    expect(chzKeys()).toEqual(['fbo-chz:n1', 'fbo-chz:n1'])
    expect(q('fbo-packing-row-message-p1')).toBeNull()
  })

  it('потеря ответа на выдачу: повтор идёт с тем же mutation_id', async () => {
    let attempts = 0
    handlers.set('POST /marking-codes/issue', () => {
      attempts += 1
      if (attempts === 1) return { status: 503, body: { detail: 'unavailable' } }
      return { body: { items: [code('n1')], shortage: 0 } }
    })
    await mount(lineOf(4, 4))
    await click('ff-packaging-line-print-L1')
    expect(q('fbo-packing-row-message-p1')).not.toBeNull()
    await click('ff-packaging-line-print-L1')
    const issues = posts('/marking-codes/issue')
    expect(issues).toHaveLength(2)
    expect(issues[0]?.body?.mutation_id).toBe(issues[1]?.body?.mutation_id)
    expect(issues[0]?.body?.quantity).toBe(4)
  })

  it('«Печать накладной» передаёт план товаров отгрузки', async () => {
    await mount()
    await click('ff-packaging-print-sheet')
    expect(mocks.waybill).toHaveBeenCalledTimes(1)
    const sheet = mocks.waybill.mock.calls[0]![0] as { items: { quantity: number; product_name: string }[]; documentType: string }
    expect(sheet.documentType).toBe('Отгрузка на маркетплейс')
    expect(sheet.items.map((item) => item.quantity)).toEqual([30, 5])
  })
})
