// @vitest-environment jsdom
import { act } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from 'vitest'
import { FfFbsSupplyWorkspace } from './FfFbsSupplyWorkspace'
import type { FbsWorkspace } from './fbsApi'

vi.mock('../ff/unload-pick/FfUnloadPickPage', () => ({ FfUnloadPickPage: () => null }))
vi.mock('../../utils/useMarkingCodePrint', () => ({ useMarkingCodePrint: () => ({ openPrint: vi.fn(), dialog: null }) }))
vi.mock('./FbsSupplyHistoryDialog', () => ({ FbsSupplyHistoryDialog: () => null }))
vi.mock('./FbsPrintPreviewDialog', () => ({ FbsPrintPreviewDialog: () => null }))
vi.mock('./FbsTransferSupplyDialog', () => ({ FbsTransferSupplyDialog: () => null, makeFbsTransferSupplyDeps: () => ({}) }))

beforeAll(() => {
  ;(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true
  Element.prototype.scrollIntoView = () => undefined
})

type OperatorErrorGroup = {
  title: string
  orders: Array<number | null>
  message?: string
}

type DeliveryFailure = {
  code: string
  message: string
  retryable: boolean
  context: { operator_errors: OperatorErrorGroup[] }
}

const SUPPLY_A = 'supply-wms653-a'
const SUPPLY_B = 'supply-wms653-b'
const originalFetch = globalThis.fetch
const json = (body: unknown, status = 200) => new Response(JSON.stringify(body), {
  status,
  headers: { 'Content-Type': 'application/json' },
})

let deliveryResponses: Array<DeliveryFailure | 'success'>
let calls: string[]
let host: HTMLDivElement
let root: Root

function workspace(
  id = SUPPLY_A,
  persistedError: DeliveryFailure | null = null,
  delivered = false,
): FbsWorkspace {
  return {
    supply: {
      id,
      marketplace: 'wb',
      wb_supply_id: id === SUPPLY_A ? 'WB-GI-653-A' : 'WB-GI-653-B',
      source: 'wms',
      name: id === SUPPLY_A ? 'Поставка WMS-653 A' : 'Поставка WMS-653 B',
      status: delivered ? 'in_delivery' : 'packed',
      delivery_type: 'warehouse_sc',
      seller: { id: 'seller-653', name: 'ИП Тестовый' },
      wb_warehouse: { id: 507, name: 'Коледино' },
      wms_warehouse: { id: 'warehouse-653', name: 'Основной склад' },
      planned_destination: null,
      planned_shipment_date: null,
      nearest_deadline_at: '2026-10-06T12:00:00+03:00',
      packaging_task_id: null,
      barcode_asset: null,
    },
    stage: delivered ? 'tracking' : 'delivery',
    progress: { picked: 0, packed: 0, metadata_ready: 0, stickers_ready: 0, total: 0 },
    blockers: [],
    orders: [],
    cargo_places: [],
    boxes: [],
    delivery_preflight: null,
    last_wb_sync_at: null,
    server_now: '2026-10-05T12:00:00+03:00',
    // WMS-653 uses the existing durable delivery operation when a workspace is
    // opened again. The field is presentation data, not a new status or journal.
    last_delivery_error: persistedError,
  } as unknown as FbsWorkspace
}

async function server(input: RequestInfo | URL, init?: RequestInit): Promise<Response> {
  const url = new URL(typeof input === 'string' ? input : input instanceof URL ? input.href : input.url, 'http://wms.test')
  const method = (init?.method ?? 'GET').toUpperCase()
  const path = url.pathname.replace(/^\/api/, '')
  calls.push(`${method} ${path}`)

  if (path.endsWith('/delivery-preflight')) {
    return json({ can_deliver: true, version: 'wms653-v1', checked_at: '2026-10-05T12:00:00Z', checks: [] })
  }
  if (path.endsWith('/deliver')) {
    const result = deliveryResponses.shift()
    if (result === 'success') return json(workspace(SUPPLY_A, null, true))
    if (!result) throw new Error('Unexpected delivery call')
    return json({ detail: result }, 409)
  }
  if (path.endsWith('/workspace')) {
    const id = path.includes(SUPPLY_B) ? SUPPLY_B : SUPPLY_A
    return json(workspace(id))
  }
  return json(null)
}

beforeEach(() => {
  calls = []
  deliveryResponses = []
  window.sessionStorage.clear()
  globalThis.fetch = server as typeof fetch
  host = document.createElement('div')
  document.body.appendChild(host)
  root = createRoot(host)
})

afterEach(() => {
  act(() => root.unmount())
  host.remove()
  document.body.innerHTML = ''
  globalThis.fetch = originalFetch
})

async function settle(ms = 0) {
  await act(async () => { await new Promise((resolve) => setTimeout(resolve, ms)) })
}

async function renderWorkspace(snapshot = workspace()) {
  await act(async () => {
    root.render(
      <FfFbsSupplyWorkspace
        token="token-wms653"
        authHeaders={() => ({ Authorization: 'Bearer token-wms653' })}
        supplyId={snapshot.supply.id}
        initialWorkspace={snapshot}
        open
        onClose={() => undefined}
      />,
    )
  })
  await settle()
}

function byTestId(id: string) {
  return document.querySelector<HTMLElement>(`[data-testid="${id}"]`)
}

function buttonByText(label: string) {
  return [...document.querySelectorAll<HTMLButtonElement>('button')]
    .find((button) => button.textContent?.trim() === label) ?? null
}

function bodyText() {
  return document.body.textContent ?? ''
}

async function submitDelivery() {
  act(() => byTestId('fbs-deliver-open')!.click())
  await settle()
  act(() => byTestId('fbs-deliver-confirm')!.click())
  await settle()
}

const failure = (operator_errors: OperatorErrorGroup[]): DeliveryFailure => ({
  code: 'meta_validation_fail',
  message: operator_errors.length === 1 && operator_errors[0]!.orders.length === 1
    ? `${operator_errors[0]!.title}: заказ № ${operator_errors[0]!.orders[0]}`
    : 'Wildberries не принял часть заказов поставки',
  retryable: true,
  context: { operator_errors },
})

describe('WMS-653 · ошибки передачи WB FBS', () => {
  it('C6: единственная ошибка сразу остаётся отдельным красным сообщением', async () => {
    deliveryResponses = [failure([{
      title: 'Wildberries не принял КИЗы',
      orders: [7001],
      message: 'КИЗ принадлежит другому товару',
    }])]
    await renderWorkspace()

    await submitDelivery()

    expect(bodyText()).toContain('Wildberries не принял КИЗы')
    expect(bodyText()).toContain('7001')
    expect(byTestId('fbs-delivery-errors-toggle')).toBeNull()
    expect(byTestId('fbs-delivery-errors-dialog')).toBeNull()
  })

  it('C7: несколько ошибок открываются доступной кнопкой и дают раскрыть каждую группу', async () => {
    deliveryResponses = [failure([
      {
        title: 'Wildberries ещё обрабатывает КИЗы',
        orders: [7001, 7001, null],
      },
      {
        title: 'Wildberries не принял КИЗы',
        orders: [7002],
        message: 'КИЗ уже использован',
      },
    ])]
    await renderWorkspace()
    await submitDelivery()

    const toggle = byTestId('fbs-delivery-errors-toggle') as HTMLButtonElement
    expect(toggle).not.toBeNull()
    expect(toggle.tagName).toBe('BUTTON')
    expect(toggle.getAttribute('aria-label')).toBe('Показать ошибки передачи поставки')
    expect(toggle.tabIndex).toBeGreaterThanOrEqual(0)
    act(() => toggle.focus())
    expect(document.activeElement).toBe(toggle)
    act(() => toggle.click())
    await settle()

    const dialog = byTestId('fbs-delivery-errors-dialog')!
    expect(dialog.getAttribute('role') ?? dialog.closest('[role="dialog"]')?.getAttribute('role')).toBe('dialog')
    expect(dialog.textContent).toContain('Wildberries ещё обрабатывает КИЗы')
    expect(dialog.textContent).toContain('Wildberries не принял КИЗы')
    expect(dialog.textContent).toContain('КИЗ уже использован')
    const rows = [...dialog.querySelectorAll('ol li')].map((row) => row.textContent?.trim())
    expect(rows.filter((row) => row?.includes('7001'))).toHaveLength(1)
    expect(rows).toContain('Заказ не указан Wildberries')
    expect(rows.some((row) => row?.includes('7002'))).toBe(true)

    const groups = [...dialog.querySelectorAll<HTMLButtonElement>('button[aria-expanded]')]
    expect(groups).toHaveLength(2)
    expect(groups.every((button) => button.getAttribute('aria-expanded') === 'true')).toBe(true)
    act(() => groups[0]!.click())
    expect(groups[0]!.getAttribute('aria-expanded')).toBe('false')

    expect(dialog.textContent).not.toContain('0104600000000017215SECRET')
    expect(dialog.textContent).not.toContain('MetaValidationFail')
    expect(dialog.textContent).not.toContain('decision')

    act(() => buttonByText('Закрыть')!.click())
    await settle()
    expect(byTestId('fbs-delivery-errors-dialog')).toBeNull()
    act(() => {
      toggle.focus()
      toggle.dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter', bubbles: true }))
      // jsdom does not perform the browser's native Enter -> click default for
      // buttons, so fire that default action explicitly after the key event.
      toggle.click()
    })
    await settle()
    expect(byTestId('fbs-delivery-errors-dialog')).not.toBeNull()
  })

  it('C8: pending и настоящий отказ остаются разными группами со своими заказами', async () => {
    deliveryResponses = [failure([
      { title: 'Wildberries ещё обрабатывает КИЗы', orders: [7101, 7102] },
      { title: 'Wildberries не принял КИЗы', orders: [7201, 7202], message: 'КИЗ отклонён' },
    ])]
    await renderWorkspace()
    await submitDelivery()
    act(() => byTestId('fbs-delivery-errors-toggle')!.click())
    await settle()

    const dialog = byTestId('fbs-delivery-errors-dialog')!
    const groupButtons = [...dialog.querySelectorAll<HTMLButtonElement>('button[aria-expanded]')]
    const waiting = groupButtons.find((button) => button.textContent?.includes('ещё обрабатывает КИЗы'))!
    const rejected = groupButtons.find((button) => button.textContent?.includes('не принял КИЗы'))!
    const waitingText = waiting.parentElement?.textContent ?? ''
    const rejectedText = rejected.parentElement?.textContent ?? ''
    expect(waitingText).toContain('7101')
    expect(waitingText).toContain('7102')
    expect(waitingText).not.toContain('7201')
    expect(waitingText).not.toContain('7202')
    expect(rejectedText).toContain('7201')
    expect(rejectedText).toContain('7202')
    expect(rejectedText).not.toContain('7101')
    expect(rejectedText).not.toContain('7102')
    expect(dialog.querySelectorAll('ol li')).toHaveLength(4)
  })

  it('C9: каждая ручная попытка заменяет прошлый набор, успех очищает индикатор', async () => {
    deliveryResponses = [
      failure([{ title: 'Первая причина', orders: [8001, 8002] }]),
      failure([{ title: 'Вторая причина', orders: [8003, 8004] }]),
      'success',
    ]
    await renderWorkspace()
    await submitDelivery()

    expect(calls.filter((call) => call.endsWith('/deliver'))).toHaveLength(1)
    await settle(30)
    expect(calls.filter((call) => call.endsWith('/deliver'))).toHaveLength(1)
    act(() => byTestId('fbs-delivery-errors-toggle')!.click())
    await settle()
    expect(bodyText()).toContain('Первая причина')
    act(() => buttonByText('Закрыть')!.click())
    await settle()

    act(() => buttonByText('Повторить')!.click())
    await settle()
    expect(calls.filter((call) => call.endsWith('/deliver'))).toHaveLength(2)
    act(() => byTestId('fbs-delivery-errors-toggle')!.click())
    await settle()
    expect(bodyText()).toContain('Вторая причина')
    expect(bodyText()).not.toContain('Первая причина')
    act(() => buttonByText('Закрыть')!.click())
    await settle()

    act(() => buttonByText('Повторить')!.click())
    await settle()
    expect(calls.filter((call) => call.endsWith('/deliver'))).toHaveLength(3)
    expect(byTestId('fbs-delivery-errors-toggle')).toBeNull()
    expect(bodyText()).not.toContain('Первая причина')
    expect(bodyText()).not.toContain('Вторая причина')
  })

  it('C10: результат принадлежит поставке и переход сам не запускает передачу', async () => {
    const firstError = failure([{ title: 'Ошибка только поставки A', orders: [9001, 9002] }])
    deliveryResponses = [firstError]
    await renderWorkspace(workspace(SUPPLY_A))
    await submitDelivery()
    expect(calls.filter((call) => call.endsWith('/deliver'))).toHaveLength(1)

    await renderWorkspace(workspace(SUPPLY_B))
    expect(bodyText()).not.toContain('Ошибка только поставки A')
    expect(byTestId('fbs-delivery-errors-toggle')).toBeNull()
    expect(calls.filter((call) => call.endsWith('/deliver'))).toHaveLength(1)

    await renderWorkspace(workspace(SUPPLY_A, firstError))
    expect(byTestId('fbs-delivery-errors-toggle')).not.toBeNull()
    expect(calls.filter((call) => call.endsWith('/deliver'))).toHaveLength(1)
  })
})
