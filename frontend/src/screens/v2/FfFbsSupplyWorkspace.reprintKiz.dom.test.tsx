// @vitest-environment jsdom
import { act } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from 'vitest'
import type { FbsWorkspace } from './fbsApi'

// WMS-575 R11, ночное ревью кандидата (Astra F5): круговая стрелка «Перепечатать
// ЧЗ» у кода, внесённого оператором, печатает именно этот код, даже если товару
// маркировка не обязательна. Раньше окно печати получало «ЧЗ не нужен»,
// выключало перепечатку и брало шаблон без ЧЗ. Рендерится настоящая карточка;
// подменены только сеть и хук окна печати — чтобы увидеть, с чем карточка его
// открывает, и что уходит на сервер по кнопке «Печать».

type OpenPrintCall = {
  ctx: {
    requiresHonestSign: boolean
    qtyNeedPack: number
    fbsTape?: {
      orders: Array<{ orderId: string; requiresHonestSign: boolean }>
      print: (args: { layout: unknown; allowPartial: boolean; reprint: boolean }) => Promise<unknown>
    }
  }
  options?: { reprint?: boolean }
}

const printCalls = vi.hoisted(() => [] as OpenPrintCall[])

vi.mock('../../utils/useMarkingCodePrint', () => ({
  useMarkingCodePrint: () => ({
    openPrint: (ctx: OpenPrintCall['ctx'], options?: OpenPrintCall['options']) => {
      printCalls.push({ ctx, options })
    },
    dialog: null,
  }),
}))

const { FfFbsSupplyWorkspace } = await import('./FfFbsSupplyWorkspace')

beforeAll(() => {
  ;(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true
  Element.prototype.scrollIntoView = () => undefined
})

const SUPPLY_ID = 'sup-r11'
const MARKING_ID = 'mark-operator-1'

/** Заказ WB, у товара которого ЧЗ не обязателен, но оператор уже внёс код. */
function workspace(): FbsWorkspace {
  return {
    supply: {
      id: SUPPLY_ID, marketplace: 'wb', wb_supply_id: 'WB-GI-R11', source: 'wms', name: 'Поставка R11',
      status: 'assembling', delivery_type: 'warehouse_sc', seller: { id: 'seller-1', name: 'ИП Тестовый' },
      wb_warehouse: { id: 507, name: 'Коледино' }, wms_warehouse: { id: 'wh-1', name: 'Основной склад' },
      planned_destination: null, planned_shipment_date: null,
      nearest_deadline_at: new Date(Date.now() + 86_400_000).toISOString(), packaging_task_id: 'pt-r11',
      barcode_asset: null,
    },
    stage: 'packing',
    progress: { picked: 1, packed: 0, metadata_ready: 0, stickers_ready: 0, total: 1 },
    blockers: [],
    orders: [{
      id: 'order-r11', marketplace: 'wb', external_order_id: null, wb_order_id: 7001,
      status: 'assembling', wb_status: 'confirm', supplier_status: 'confirm',
      seller: { id: 'seller-1', name: 'ИП Тестовый' },
      wb_warehouse: { id: 507, name: 'Коледино' }, wms_warehouse: { id: 'wh-1', name: 'Основной склад' },
      product: {
        id: 'prod-plain', name: 'Кроссовки', image_url: null, seller_article: 'SNK-01', wb_article: 2001,
        barcode: '4600000000024', sku: 'SNK-01', chrt_id: 2, category: 'Обувь', color: null, size: null,
      },
      positions: [],
      inventory: { available_unpacked: 5, locations: [] },
      buyer_type: 'individual', cargo_type: 'mgt', can_pvz: false,
      metadata: {
        required: [], optional: [],
        states: [{ id: MARKING_ID, kind: 'sgtin', status: 'pending', reason: null, source: 'operator', value_tail: 'OPER5751' }],
        delivery_allowed: false, last_checked_at: null,
      },
      sticker: { code: '7001 0001', status: 'print_opened', asset_url: null, applied_at: null },
      pick: { status: 'picked', location_code: 'А-01-04', picked_at: null },
      pack: { status: 'pending', packed_at: null },
      created_at_wb: new Date().toISOString(),
      deadline_at: new Date(Date.now() + 86_400_000).toISOString(),
      supply_id: SUPPLY_ID, selection_blockers: [], tape_order_index: 0,
    }],
    cargo_places: [], boxes: [], delivery_preflight: null, last_wb_sync_at: null,
    server_now: new Date().toISOString(),
  } as unknown as FbsWorkspace
}

const packagingTask = {
  id: 'pt-r11', document_number: '000R11', display_number: '000R11', status: 'in_progress', lines: [{
    id: 'ptl-r11', product_id: 'prod-plain', sku_code: 'SNK-01', product_name: 'Кроссовки',
    requires_honest_sign: false, packaging_instructions: '', qty_total: 1, qty_need_pack: 1,
    marking_available_count: 0,
  }],
}

let tapeRequests: unknown[]
const originalFetch = globalThis.fetch

async function server(input: RequestInfo | URL, init?: RequestInit): Promise<Response> {
  const url = new URL(typeof input === 'string' ? input : input instanceof URL ? input.href : input.url, 'http://wms.test')
  const path = url.pathname.replace(/^\/api/, '')
  const json = (body: unknown) => new Response(JSON.stringify(body), { status: 200, headers: { 'Content-Type': 'application/json' } })
  if (path.startsWith('/operations/packaging-tasks/')) return json(packagingTask)
  if (path === `/operations/fbs-supplies/${SUPPLY_ID}/order-print-tape`) {
    tapeRequests.push(typeof init?.body === 'string' ? JSON.parse(init.body) : null)
    return json({ orders: [], print_batch: null, order_errors: [], shortage: 0 })
  }
  if (path === `/operations/fbs-supplies/${SUPPLY_ID}/workspace`) return json(workspace())
  return json(null)
}

let host: HTMLDivElement
let root: Root

beforeEach(() => {
  printCalls.length = 0
  tapeRequests = []
  window.sessionStorage.clear()
  window.localStorage.clear()
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

async function openCard() {
  await act(async () => {
    root.render(
      <FfFbsSupplyWorkspace
        token="t-r11"
        authHeaders={() => ({ Authorization: 'Bearer t-r11' })}
        supplyId={SUPPLY_ID}
        initialWorkspace={workspace()}
        open
        onClose={() => undefined}
      />,
    )
  })
  for (let step = 0; step < 5; step += 1) {
    await act(async () => { await new Promise((resolve) => setTimeout(resolve, 10)) })
  }
}

describe('WMS-575 R11 · «Перепечатать ЧЗ» у кода оператора на товаре без обязательной маркировки', () => {
  it('стрелка открывает печать именно этого ЧЗ: перепечатка, шаблон с ЧЗ, id кода на сервер', async () => {
    await openCard()
    const arrow = document.querySelector<HTMLButtonElement>('[data-order-id="order-r11"] [data-testid="fbs-kiz-reprint-inline"]')
    expect(arrow).not.toBeNull()
    await act(async () => arrow!.click())

    expect(printCalls).toHaveLength(1)
    const [{ ctx, options }] = printCalls
    expect(options?.reprint).toBe(true)
    // Окно печати включает перепечатку и шаблон ЧЗ только при requiresHonestSign.
    expect(ctx.requiresHonestSign).toBe(true)
    expect(ctx.qtyNeedPack).toBe(1)
    expect(ctx.fbsTape?.orders).toEqual([expect.objectContaining({ orderId: 'order-r11', requiresHonestSign: true })])
    expect(ctx.fbsTape?.reprintMarkingIds).toEqual([MARKING_ID])

    await act(async () => {
      await ctx.fbsTape!.print({ layout: { units: [{ block: 'cz', copies: 1 }] }, allowPartial: false, reprint: true })
    })
    expect(tapeRequests).toEqual([expect.objectContaining({
      order_ids: ['order-r11'],
      reprint: true,
      reprint_marking_ids: [MARKING_ID],
    })])
  })

  it('обычная печать ЧЗ и ШК того же заказа не меняется: товар без обязательной маркировки — без ЧЗ', async () => {
    await openCard()
    const printer = document.querySelector<HTMLButtonElement>('[data-order-id="order-r11"] [aria-label="Печать ЧЗ и ШК"]')
    expect(printer).not.toBeNull()
    await act(async () => printer!.click())

    expect(printCalls).toHaveLength(1)
    expect(printCalls[0].options?.reprint).toBe(false)
    expect(printCalls[0].ctx.requiresHonestSign).toBe(false)
    expect(printCalls[0].ctx.qtyNeedPack).toBe(0)
  })
})
