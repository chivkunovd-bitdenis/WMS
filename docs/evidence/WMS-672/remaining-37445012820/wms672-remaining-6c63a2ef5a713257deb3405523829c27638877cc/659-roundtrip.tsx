// @vitest-environment jsdom
import { act } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { FfInboundRequestView } from './FfInboundRequestView'

vi.setConfig({ testTimeout: 20000 })

type BoxRow = {
  id: string
  box_number: number
  internal_barcode: string
  free_text: null
  pallet_id: null
  pallet_code: null
  storage_location_id: null
  storage_location_code: null
  label_printed_at: null
  intake_opened_at: null
  intake_closed_at: null
  is_damaged: false
  lines: []
}

type Detail = ReturnType<typeof detail>

function detail(operationType: 'inbound' | 'return' = 'inbound', status = 'draft') {
  return {
    id: 'request-659',
    document_number: 'WMS-659',
    display_number: '659',
    waybill_number: null,
    warehouse_id: 'warehouse-659',
    status,
    operation_type: operationType,
    marketplace: null,
    marketplace_warning: null,
    planned_delivery_date: null,
    planned_box_count: null,
    actual_box_count: null,
    boxes_discrepancy: false,
    has_discrepancy: false,
    seller_id: null,
    seller_name: 'Империя ФФ',
    created_by_seller_id: null,
    created_at: '2026-10-05T00:00:00Z',
    distribution_completed_at: null,
    sorting_remaining_qty: 0,
    boxes: [] as BoxRow[],
    cargo_places: [],
    lines: [],
  }
}

function json(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  })
}

function box(number: number): BoxRow {
  return {
    id: `box-${number}`,
    box_number: number,
    internal_barcode: `INB-0000000000000${number}`,
    free_text: null,
    pallet_id: null,
    pallet_code: null,
    storage_location_id: null,
    storage_location_code: null,
    label_printed_at: null,
    intake_opened_at: null,
    intake_closed_at: null,
    is_damaged: false,
    lines: [],
  }
}

let root: Root
let host: HTMLDivElement
let current: Detail
let fetcher: ReturnType<typeof vi.fn>
let postMode: 'success' | 'error' | 'lost-once'
let lostOnce: boolean
const boxBodies: Array<{ quantity: number; mutation_id: string }> = []
const savedByMutation = new Map<string, BoxRow[]>()
const originalScrollIntoView = Element.prototype.scrollIntoView

async function flush(): Promise<void> {
  await act(async () => {
    await Promise.resolve()
    await Promise.resolve()
  })
}

function testId(id: string): HTMLElement {
  const node = document.querySelector(`[data-testid="${id}"]`)
  expect(node, id).toBeTruthy()
  return node as HTMLElement
}

async function click(node: HTMLElement): Promise<void> {
  await act(async () => node.click())
  await flush()
}

function dialog(): HTMLElement {
  const node = document.querySelector('[role="dialog"]')
  expect(node, 'bulk box dialog').toBeTruthy()
  return node as HTMLElement
}

function dialogButton(text: string): HTMLButtonElement {
  const node = [...dialog().querySelectorAll('button')].find(
    (candidate) => candidate.textContent?.trim() === text,
  )
  expect(node, `dialog button ${text}`).toBeTruthy()
  return node as HTMLButtonElement
}

function quantityField(): HTMLInputElement {
  const label = [...dialog().querySelectorAll('label')].find((node) =>
    node.textContent?.startsWith('Количество коробов'),
  )
  expect(label, 'Количество коробов').toBeTruthy()
  return document.getElementById(label!.htmlFor) as HTMLInputElement
}

async function fillQuantity(value: string): Promise<void> {
  await act(async () => {
    const input = quantityField()
    Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value')!.set!.call(input, value)
    input.dispatchEvent(new Event('input', { bubbles: true }))
  })
}

async function openBoxDialog(): Promise<void> {
  if (!document.querySelector('[data-testid="ff-inbound-boxes-panel"]')) {
    await click(testId('ff-inbound-packages-toggle'))
  }
  await click(testId('ff-inbound-add-to-box'))
  dialog()
}

async function render(): Promise<void> {
  await act(async () => {
    root.render(
      <FfInboundRequestView
        token="wms659-token"
        requestId="request-659"
        isFulfillmentAdmin
        workspace="reception"
        onClose={() => undefined}
      />,
    )
  })
  await flush()
}

beforeEach(() => {
  ;(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true
  current = detail()
  postMode = 'success'
  lostOnce = false
  boxBodies.length = 0
  savedByMutation.clear()
  host = document.createElement('div')
  document.body.append(host)
  root = createRoot(host)
  Element.prototype.scrollIntoView = () => undefined
  fetcher = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input)
    const method = init?.method ?? 'GET'
    if (url.endsWith(`${'/operations/inbound-intake-requests/request-659'}`) && method === 'GET') {
      return json(current)
    }
    if (url.includes('/products/linked-wb-catalog')) return json([])
    if (url.endsWith('/operations/inbound-intake-requests/request-659/marking-codes')) {
      return json({ items: [], checking: false })
    }
    if (url.includes('/locations?exclude_sorting_zone=true')) return json([])
    if (url.endsWith('/warehouses')) return json([{ id: 'warehouse-659', name: 'Основной' }])
    if (url.endsWith('/operations/inbound-intake-requests/request-659/boxes') && method === 'POST') {
      const body = JSON.parse(String(init?.body)) as { quantity: number; mutation_id: string }
      boxBodies.push(body)
      const saved = savedByMutation.get(body.mutation_id)
      if (saved) return json(saved, 201)
      if (postMode === 'error') return json({ detail: 'controlled failure' }, 503)
      const first = current.boxes.length + 1
      const created = Array.from({ length: body.quantity }, (_, index) => box(first + index))
      current = { ...current, boxes: [...current.boxes, ...created] }
      savedByMutation.set(body.mutation_id, created)
      if (postMode === 'lost-once' && !lostOnce) {
        lostOnce = true
        throw new TypeError('response lost after commit')
      }
      return json(created, 201)
    }
    throw new Error(`Unexpected WMS-659 request: ${method} ${url}`)
  })
  vi.stubGlobal('fetch', fetcher)
})

afterEach(async () => {
  await act(async () => root.unmount())
  host.remove()
  vi.unstubAllGlobals()
  Element.prototype.scrollIntoView = originalScrollIntoView
  vi.restoreAllMocks()
})

describe('WMS-659 bulk inbound boxes', () => {
  it('validates positive integers, recovers from API failure and refreshes the box list', async () => {
    await render()
    await openBoxDialog()

    for (const invalid of ['', '0', '-1', '1.5']) {
      await fillQuantity(invalid)
      await click(dialogButton('Создать'))
      expect(dialog().textContent).toMatch(/целое|количество/i)
    }
    expect(boxBodies).toHaveLength(0)

    await fillQuantity('3')
    postMode = 'error'
    await click(dialogButton('Создать'))
    expect(dialog().textContent).toContain('controlled failure')
    expect(dialogButton('Создать').disabled).toBe(false)
    expect(document.querySelectorAll('[data-testid="ff-inbound-box-row"]')).toHaveLength(0)

    postMode = 'success'
    await click(dialogButton('Создать'))
    expect(document.querySelector('[role="dialog"]')).toBeNull()
    expect(document.querySelectorAll('[data-testid="ff-inbound-box-row"]')).toHaveLength(3)
    expect(document.body.textContent).toContain('Короба: 3')
  })

  it('reuses one mutation after a lost response and gives the next intentional batch a new one', async () => {
    await render()
    await openBoxDialog()
    await fillQuantity('3')
    postMode = 'lost-once'

    await click(dialogButton('Создать'))
    expect(dialog().textContent).toContain('response lost after commit')
    await click(dialogButton('Создать'))

    expect(boxBodies).toHaveLength(2)
    expect(boxBodies[0]!.mutation_id).toBe(boxBodies[1]!.mutation_id)
    expect(document.querySelectorAll('[data-testid="ff-inbound-box-row"]')).toHaveLength(3)

    postMode = 'success'
    await openBoxDialog()
    await fillQuantity('3')
    await click(dialogButton('Создать'))
    expect(boxBodies[2]!.mutation_id).not.toBe(boxBodies[0]!.mutation_id)
    expect(document.querySelectorAll('[data-testid="ff-inbound-box-row"]')).toHaveLength(6)
  })

  it('offers the same enabled bulk action in an editable return', async () => {
    current = detail('return')
    await render()
    await click(testId('ff-inbound-packages-toggle'))

    const create = testId('ff-inbound-add-to-box') as HTMLButtonElement
    expect(create.disabled).toBe(false)
    await click(create)
    expect(dialog().textContent).toContain('Количество коробов')
  })

  it('keeps the bulk action disabled in completed inbound and return documents', async () => {
    for (const operationType of ['inbound', 'return'] as const) {
      current = detail(operationType, 'done')
      await render()
      await click(testId('ff-inbound-packages-toggle'))

      expect((testId('ff-inbound-add-to-box') as HTMLButtonElement).disabled).toBe(true)
      expect(boxBodies).toHaveLength(0)
      if (operationType === 'inbound') {
        await act(async () => root.unmount())
        root = createRoot(host)
      }
    }
  })
})
