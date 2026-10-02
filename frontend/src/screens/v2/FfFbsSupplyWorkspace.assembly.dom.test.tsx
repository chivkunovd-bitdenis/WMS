// @vitest-environment jsdom
import { act, useState } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { afterEach, beforeAll, beforeEach, describe, expect, it } from 'vitest'
import { FfFbsSupplyWorkspace } from './FfFbsSupplyWorkspace'
import type { FbsWorkspace } from './fbsApi'
import { saveFbsScanPrintPreferences } from './fbsScanAutoPrint'

// WMS-574 · рамка поставки в окне групповой сборки — настоящая карточка
// поставки в режиме рамки. Сервер подменён через fetch, сканер — keydown.

beforeAll(() => {
  ;(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true
  Element.prototype.scrollIntoView = () => undefined
})

const SUPPLY_ID = 'sup-574'
const STICKER_KIZ = '*STICKERA1111'
const STICKER_PLAIN = '*STICKERC3333'
const STICKER_FOREIGN = '*FOREIGN9999'

type Box = FbsWorkspace['boxes'][number]

function order(id: string, wbOrderId: number, index: number, productId: string, requiresKiz: boolean) {
  return {
    id,
    marketplace: 'wb',
    external_order_id: null,
    wb_order_id: wbOrderId,
    status: 'assembling',
    wb_status: 'confirm',
    supplier_status: 'confirm',
    seller: { id: 'seller-1', name: 'ИП Тестовый' },
    wb_warehouse: { id: 507, name: 'Коледино' },
    wms_warehouse: { id: 'wh-1', name: 'Основной склад' },
    product: {
      id: productId, name: `Товар ${index + 1}`, image_url: null, seller_article: 'ART',
      wb_article: 1001, barcode: '4600000000017', sku: 'ART', chrt_id: 1, category: 'Одежда',
      color: null, size: null,
    },
    positions: [],
    inventory: { available_unpacked: 5, locations: [] },
    buyer_type: 'individual',
    cargo_type: 'mgt',
    can_pvz: false,
    metadata: {
      required: requiresKiz ? ['sgtin'] : [],
      optional: [],
      states: requiresKiz ? [{ kind: 'sgtin', status: 'missing', reason: null, source: null, value_tail: null }] : [],
      delivery_allowed: !requiresKiz,
      last_checked_at: null,
    },
    sticker: { code: `${wbOrderId} 000${index}`, status: 'print_opened', asset_url: null, applied_at: null },
    pick: { status: 'picked', location_code: 'А-01-01', picked_at: null },
    pack: { status: 'pending', packed_at: null },
    created_at_wb: new Date().toISOString(),
    deadline_at: new Date(Date.now() + 86_400_000).toISOString(),
    supply_id: SUPPLY_ID,
    selection_blockers: [],
    tape_order_index: index,
  }
}

function box(id: string, number: number, orderIds: string[], qrReady: boolean): Box {
  return {
    id,
    box_number: number,
    barcode: `BOX-${number}`,
    assigned_order_ids: orderIds,
    trbx_id: null,
    wb_trbx_id: `TRBX-${number}`,
    qr_asset: qrReady
      ? {
        id: `qr-${id}`, kind: 'cargo_place_qr', status: 'ready', content_type: 'image/png', width_mm: 58,
        height_mm: 40, preview_url: `/qr/${id}.png`, download_url: null, checksum: null, applied_at: null, error: null,
      }
      : null,
    without_distribution: false,
  } as Box
}

let boxes: Box[]
let delays: Record<string, number>
// Поставка передана в WB и какой QR всей поставки вернул сервер (F4 итогового ревью).
let transferred: { assetReady: boolean } | null
// Три одинаковые вещи без ЧЗ (очередь одинаковых кодов) и какой заказ сервер выбирает на каждый скан ШК.
let sameProductOrders: boolean
let autoPrintOrders: string[]

const wait = (ms: number) => new Promise((resolve) => setTimeout(resolve, ms))

function workspace(): FbsWorkspace {
  return {
    supply: {
      id: SUPPLY_ID, marketplace: 'wb', wb_supply_id: 'WB-GI-574', source: 'wms', name: 'FBS 29.09.2026',
      status: transferred ? 'in_delivery' : 'assembling', delivery_type: 'warehouse_sc', seller: { id: 'seller-1', name: 'ИП Тестовый' },
      wb_warehouse: { id: 507, name: 'Коледино' }, wms_warehouse: { id: 'wh-1', name: 'Основной склад' },
      planned_destination: null, planned_shipment_date: null,
      nearest_deadline_at: new Date(Date.now() + 86_400_000).toISOString(), packaging_task_id: 'pt-574',
      barcode_asset: transferred?.assetReady
        ? {
          id: 'supply-qr', kind: 'supply_qr', status: 'ready', content_type: 'image/png', width_mm: 58, height_mm: 40,
          preview_url: '/qr/supply.png', download_url: null, checksum: null, applied_at: null, error: null,
        }
        : null,
    },
    stage: transferred ? 'tracking' : 'packing',
    progress: { picked: 2, packed: 0, metadata_ready: 0, stickers_ready: 0, total: 2 },
    blockers: [],
    orders: sameProductOrders
      ? [order('order-a', 5001, 0, 'prod-plain', false), order('order-c', 5003, 1, 'prod-plain', false), order('order-d', 5004, 2, 'prod-plain', false)]
      : [order('order-a', 5001, 0, 'prod-kiz', true), order('order-c', 5003, 1, 'prod-plain', false)],
    cargo_places: [],
    boxes: boxes.map((one) => ({ ...one, assigned_order_ids: [...one.assigned_order_ids] })),
    delivery_preflight: null,
    last_wb_sync_at: null,
    server_now: new Date().toISOString(),
  } as unknown as FbsWorkspace
}

const packagingTask = {
  id: 'pt-574', document_number: '000574', display_number: '000574', status: 'in_progress', lines: [
    { id: 'l-1', product_id: 'prod-kiz', sku_code: 'ART', product_name: 'Товар 1', requires_honest_sign: true,
      packaging_instructions: '', qty_total: 1, qty_need_pack: 1, marking_available_count: 5 },
    { id: 'l-2', product_id: 'prod-plain', sku_code: 'ART', product_name: 'Товар 2', requires_honest_sign: false,
      packaging_instructions: '', qty_total: 1, qty_need_pack: 1, marking_available_count: 0 },
  ],
}

type Call = { method: string; path: string; body: unknown }
let calls: Call[]
const originalFetch = globalThis.fetch

function json(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } })
}

async function server(input: RequestInfo | URL, init?: RequestInit): Promise<Response> {
  const url = new URL(typeof input === 'string' ? input : input instanceof URL ? input.href : input.url, 'http://wms.test')
  const method = (init?.method ?? 'GET').toUpperCase()
  const body = typeof init?.body === 'string' ? JSON.parse(init.body) : null
  const path = url.pathname.replace(/^\/api/, '')
  calls.push({ method, path: `${path}${url.search}`, body })
  if (path.endsWith('/scan-auto-print')) {
    const number = calls.filter((call) => call.path.endsWith('/scan-auto-print')).length
    await wait(delays.autoPrint ?? 0)
    return json({
      scan_id: `scan-${number}`, order_id: autoPrintOrders[number - 1], wb_order_id: 5000 + number,
      requires_honest_sign: false, qr_asset: null, printed_codes: [], order_errors: [], shortage: 0,
    })
  }
  if (path.startsWith('/operations/packaging-tasks/')) return json(packagingTask)
  if (path === '/operations/fbs-orders/kiz/lookup') {
    await wait(delays.lookup ?? 0)
    const sticker = url.searchParams.get('sticker')
    const orderId = sticker === STICKER_KIZ ? 'order-a' : sticker === STICKER_PLAIN ? 'order-c' : null
    if (!orderId) return json({ detail: { code: 'sticker_not_found', message: 'Стикер не найден в этой поставке.' } }, 404)
    return json({
      order_id: orderId, wb_order_id: orderId === 'order-a' ? 5001 : 5003,
      product: { name: 'Товар', image_url: null, barcode: null, seller_article: null },
      current_kiz: null, needs_confirmation: false, can_bind: true, block_reason: null,
      requires_honest_sign: orderId === 'order-a',
    })
  }
  const assign = path.match(new RegExp(`^/operations/fbs-supplies/${SUPPLY_ID}/boxes/([^/]+)/orders$`))
  if (assign && method === 'POST') {
    const target = boxes.find((one) => one.id === assign[1])!
    target.assigned_order_ids.push(...(body as { order_ids: string[] }).order_ids)
    return json(workspace())
  }
  if (path === `/operations/fbs-supplies/${SUPPLY_ID}/boxes` && method === 'POST') {
    boxes.push(box(`box-${boxes.length + 1}`, boxes.length + 1, [], false))
    return json(workspace())
  }
  if (path.endsWith('/retry-qr')) return json(workspace())
  if (path === `/operations/fbs-supplies/${SUPPLY_ID}/workspace`) return json(workspace())
  return json(null)
}

let host: HTMLDivElement
let root: Root

beforeEach(() => {
  calls = []
  boxes = []
  delays = {}
  transferred = null
  sameProductOrders = false
  autoPrintOrders = []
  window.sessionStorage.clear()
  window.localStorage.clear()
  // WMS-631 Д2 made «Печатать QR» the unsaved default; these scenarios are the all-off path.
  saveFbsScanPrintPreferences('t-574', { printQr: false, printChz: false, reprintChz: false })
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
  const steps = Math.max(1, Math.ceil(ms / 10))
  for (let step = 0; step < steps; step += 1) {
    await act(async () => {
      await new Promise((resolve) => setTimeout(resolve, Math.min(ms, 10)))
    })
  }
}

function scan(code: string) {
  const target = document.activeElement ?? document.body
  act(() => {
    for (const key of code) {
      target.dispatchEvent(new KeyboardEvent('keydown', { key, code: 'KeyA', bubbles: true, cancelable: true }))
    }
    target.dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter', code: 'Enter', bubbles: true, cancelable: true }))
  })
}

function Frame({ alwaysExpanded = false }: { alwaysExpanded?: boolean }) {
  const [active, setActive] = useState(false)
  return (
    <FfFbsSupplyWorkspace
      token="t-574"
      authHeaders={() => ({ Authorization: 'Bearer t-574' })}
      supplyId={SUPPLY_ID}
      initialWorkspace={workspace()}
      open
      onClose={() => undefined}
      assemblyFrame={{
        active,
        expanded: alwaysExpanded || active,
        visible: true,
        onToggleExpanded: () => undefined,
        onActivate: () => setActive(true),
        onDeactivate: () => setActive(false),
        onWorkspaceChange: () => undefined,
        registerEscape: () => undefined,
      }}
    />
  )
}

async function startFrame() {
  await act(async () => {
    root.render(<Frame />)
  })
  await settle(30)
  const start = document.querySelector<HTMLButtonElement>(`[data-testid="fbs-assembly-supply-start-${SUPPLY_ID}"]`)!
  await act(async () => start.click())
  await settle(80)
  expect(document.querySelector('[data-testid="fbs-kiz-scan-bar"]')).not.toBeNull()
  act(() => (document.activeElement as HTMLElement | null)?.blur())
}

const boxLine = (number: number) => Array.from(document.querySelectorAll(`[data-testid="fbs-assembly-boxes-${SUPPLY_ID}"] p`))
  .map((node) => node.textContent ?? '')
  .find((text) => text.startsWith(`Короб ${number}`)) ?? ''
const assignCalls = () => calls.filter((call) => /\/boxes\/[^/]+\/orders$/.test(call.path))
const scanMessage = () => document.querySelector('[data-testid="fbs-kiz-scan-message"]')?.textContent ?? ''

describe('WMS-574 · скан в активной рамке окна сборки', () => {
  it('R17: «Начать работу» открывает последний короб без создания нового и без start-work', async () => {
    boxes = [box('box-1', 1, [], true), box('box-2', 2, [], true)]
    await startFrame()
    expect(calls.some((call) => call.path.endsWith('/start-work'))).toBe(false)
    expect(calls.some((call) => call.method === 'POST' && call.path.endsWith('/boxes'))).toBe(false)
    expect(boxLine(2)).toContain('открыт — сканы идут сюда')
    expect(boxLine(1)).not.toContain('открыт')
  })

  it('Д8, Д9: стикер заказа без ЧЗ — заказ в открытом коробе, ожидание ЧЗ снято; с ЧЗ — ожидание остаётся', async () => {
    boxes = [box('box-1', 1, [], true)]
    await startFrame()

    scan(STICKER_PLAIN)
    await settle(80)
    expect(assignCalls().map((call) => [call.path, call.body])).toEqual([
      [`/operations/fbs-supplies/${SUPPLY_ID}/boxes/box-1/orders`, { order_ids: ['order-c'] }],
    ])
    expect(scanMessage()).not.toContain('активен')
    expect(boxLine(1)).toContain('1 шт')

    scan(STICKER_KIZ)
    await settle(80)
    expect(assignCalls()).toHaveLength(2)
    expect(assignCalls()[1]!.body).toEqual({ order_ids: ['order-a'] })
    expect(scanMessage()).toContain('активен')
  })

  it('Д8: заказ, уже лежащий в коробе, не перекладывается в открытый', async () => {
    boxes = [box('box-1', 1, ['order-c'], true), box('box-2', 2, [], true)]
    await startFrame()
    scan(STICKER_PLAIN)
    await settle(80)
    expect(assignCalls()).toHaveLength(0)
    expect(boxLine(1)).toContain('1 шт')
  })

  it('R16: код не из этой поставки — «Этого товара нет в поставке {номер WB}»', async () => {
    boxes = [box('box-1', 1, [], true)]
    await startFrame()
    scan(STICKER_FOREIGN)
    await settle(80)
    expect(document.querySelector('[data-testid="fbs-kiz-scan-error"]')?.textContent).toBe('Этого товара нет в поставке WB-GI-574')
    expect(assignCalls()).toHaveLength(0)
  })

  it('Д11: нет открытого короба — скан выполняется, заказ не кладётся, подсказка «Откройте или создайте короб.»', async () => {
    boxes = [box('box-1', 1, [], true)]
    await startFrame()
    const close = document.querySelector<HTMLButtonElement>('[data-testid="fbs-assembly-box-toggle-box-1"]')!
    await act(async () => close.click())
    scan(STICKER_KIZ)
    await settle(80)
    expect(calls.some((call) => call.path.startsWith('/operations/fbs-orders/kiz/lookup'))).toBe(true)
    expect(assignCalls()).toHaveLength(0)
    expect(document.querySelector('[data-testid="fbs-assembly-box-hint"]')?.textContent).toBe('Откройте или создайте короб.')
    expect(scanMessage()).toContain('активен')
  })

  it('WMS-589: «Начать работу» без коробов создаёт и открывает один короб, но не запрашивает и не печатает QR', async () => {
    boxes = []
    await startFrame()
    const created = calls.filter((call) => call.method === 'POST' && call.path === `/operations/fbs-supplies/${SUPPLY_ID}/boxes`)
    expect(created).toHaveLength(1)
    expect(created[0]!.body).toMatchObject({ count: 1, without_distribution: false })
    expect(calls.filter((call) => call.path.endsWith('/retry-qr'))).toHaveLength(0)
    expect(boxLine(1)).toContain('открыт — сканы идут сюда')
  })

  it('WMS-589: «Создать короб» создаёт и открывает короб без печати QR', async () => {
    boxes = [box('box-1', 1, [], true)]
    await startFrame()
    const create = document.querySelector<HTMLButtonElement>(`[data-testid="fbs-assembly-create-box-${SUPPLY_ID}"]`)!
    await act(async () => create.click())
    await settle(80)

    expect(calls.filter((call) => call.method === 'POST' && call.path === `/operations/fbs-supplies/${SUPPLY_ID}/boxes`)).toHaveLength(1)
    expect(calls.filter((call) => call.path.endsWith('/retry-qr'))).toHaveLength(0)
    expect(boxLine(2)).toContain('открыт — сканы идут сюда')
  })

  it('WMS-589: завершение работы и переключатель рамки не открывают печать', async () => {
    boxes = [box('box-1', 1, [], true)]
    await startFrame()
    calls = []

    const finish = document.querySelector<HTMLButtonElement>(`[data-testid="fbs-assembly-supply-finish-${SUPPLY_ID}"]`)!
    await act(async () => finish.click())
    const toggle = document.querySelector<HTMLButtonElement>(`[data-testid="fbs-assembly-supply-toggle-${SUPPLY_ID}"]`)!
    await act(async () => toggle.click())
    await settle(20)

    expect(calls.filter((call) => call.path.endsWith('/retry-qr'))).toHaveLength(0)
    expect(document.body.textContent).not.toContain('Проверка перед печатью')
  })

  it('WMS-589: явная кнопка «QR» короба по-прежнему открывает предпросмотр печати', async () => {
    boxes = [box('box-1', 1, [], true)]
    await startFrame()
    const boxesRoot = document.querySelector(`[data-testid="fbs-assembly-boxes-${SUPPLY_ID}"]`)!
    const qr = Array.from(boxesRoot.querySelectorAll('button')).find((button) => button.textContent === 'QR') as HTMLButtonElement
    await act(async () => qr.click())

    expect(document.body.textContent).toContain('Проверка перед печатью')
  })
})

describe('WMS-574 · итоговое ревью', () => {
  it('R22 (F1): оператор открыл другой короб, пока шёл поиск стикера, — заказ ложится в короб, открытый при скане', async () => {
    boxes = [box('box-1', 1, [], true), box('box-2', 2, [], true)]
    delays = { lookup: 160 }
    await startFrame()
    expect(boxLine(2)).toContain('открыт — сканы идут сюда')

    scan(STICKER_PLAIN)
    await settle(30)
    const openFirst = document.querySelector<HTMLButtonElement>('[data-testid="fbs-assembly-box-toggle-box-1"]')!
    await act(async () => openFirst.click())
    expect(boxLine(1)).toContain('открыт — сканы идут сюда')
    await settle(250)

    expect(assignCalls().map((call) => call.path)).toEqual([`/operations/fbs-supplies/${SUPPLY_ID}/boxes/box-2/orders`])
  })

  it('R22 (F1): оператор завершил работу с поставкой, пока шёл поиск стикера, — заказ всё равно ложится в короб, открытый при скане', async () => {
    boxes = [box('box-1', 1, [], true)]
    delays = { lookup: 160 }
    await startFrame()

    scan(STICKER_PLAIN)
    await settle(30)
    const finish = document.querySelector<HTMLButtonElement>(`[data-testid="fbs-assembly-supply-finish-${SUPPLY_ID}"]`)!
    await act(async () => finish.click())
    await settle(250)

    expect(assignCalls().map((call) => [call.path, call.body])).toEqual([
      [`/operations/fbs-supplies/${SUPPLY_ID}/boxes/box-1/orders`, { order_ids: ['order-c'] }],
    ])
  })

  it('R22: три одинаковых ШК подряд, короб переключён между вторым и третьим, — короба 2, 2, 1 по порядку прихода', async () => {
    // «Печатать ЧЗ» включена: ШК товара выбирает заказ (scan-auto-print).
    window.localStorage.setItem('wms:fbs:scan-auto-print:unknown-tenant:unknown-user', JSON.stringify({ printQr: false, printChz: true, reprintChz: false }))
    sameProductOrders = true
    autoPrintOrders = ['order-c', 'order-a', 'order-d']
    boxes = [box('box-1', 1, [], true), box('box-2', 2, [], true)]
    delays = { lookup: 150, autoPrint: 150 }
    await startFrame()
    expect(boxLine(2)).toContain('открыт — сканы идут сюда')

    scan('4600000000017')
    await settle(20)
    scan('4600000000017')
    await settle(20)
    const openFirst = document.querySelector<HTMLButtonElement>('[data-testid="fbs-assembly-box-toggle-box-1"]')!
    await act(async () => openFirst.click())
    scan('4600000000017')
    await settle(1200)

    const productRequests = calls.filter((call) => call.path.endsWith('/scan-auto-print'))
    expect(productRequests).toHaveLength(3)
    expect(assignCalls().map((call) => [call.path, call.body])).toEqual([
      [`/operations/fbs-supplies/${SUPPLY_ID}/boxes/box-2/orders`, { order_ids: ['order-c'] }],
      [`/operations/fbs-supplies/${SUPPLY_ID}/boxes/box-2/orders`, { order_ids: ['order-a'] }],
      [`/operations/fbs-supplies/${SUPPLY_ID}/boxes/box-1/orders`, { order_ids: ['order-d'] }],
    ])
  })

  it('Д19: ШК товара этой поставки при выключенных галках — прежний текст карточки, чужой код — «Этого товара нет…»', async () => {
    boxes = [box('box-1', 1, [], true)]
    await startFrame()
    const errorText = () => document.querySelector('[data-testid="fbs-kiz-scan-error"]')?.textContent

    scan('4600000000017')
    await settle(80)
    expect(errorText()).toBe('Номер или стикер заказа не найден в этой поставке')

    // ЧЗ товара этой поставки: GTIN 04600000000017 совпадает с ШК товара заказа.
    scan('0104600000000017215AbCdEfGh1234')
    await settle(80)
    expect(errorText()).toBe('Номер или стикер заказа не найден в этой поставке')

    scan('4600000099999')
    await settle(80)
    expect(errorText()).toBe('Этого товара нет в поставке WB-GI-574')
  })

  it('F4: после передачи в рамке — печать QR всей поставки, как на вкладке «Короба» карточки', async () => {
    transferred = { assetReady: true }
    boxes = [box('box-1', 1, ['order-a'], true)]
    await act(async () => {
      root.render(<Frame alwaysExpanded />)
    })
    await settle(50)
    expect(document.querySelector('[data-testid="fbs-supply-qr"]')).not.toBeNull()
    expect(document.body.textContent).toContain('Печать QR поставки')
  })

  it('F4: после передачи без полученного QR — «Получить QR повторно», как в карточке', async () => {
    transferred = { assetReady: false }
    boxes = [box('box-1', 1, ['order-a'], true)]
    await act(async () => {
      root.render(<Frame alwaysExpanded />)
    })
    await settle(50)
    expect(document.querySelector('[data-testid="fbs-supply-qr-retry"]')).not.toBeNull()
    expect(document.body.textContent).toContain('Поставка передана, QR получить не удалось')
  })
})

describe('WMS-574 · обычная карточка поставки не меняется', () => {
  it('скан стикера в карточке не кладёт заказ в короб и не снимает ожидание ЧЗ', async () => {
    boxes = [box('box-1', 1, [], true)]
    window.sessionStorage.setItem(`wms:fbs:${SUPPLY_ID}:stage`, 'packing')
    await act(async () => {
      root.render(
        <FfFbsSupplyWorkspace
          token="t-574"
          authHeaders={() => ({ Authorization: 'Bearer t-574' })}
          supplyId={SUPPLY_ID}
          initialWorkspace={workspace()}
          open
          onClose={() => undefined}
        />,
      )
    })
    await settle(50)
    act(() => (document.activeElement as HTMLElement | null)?.blur())
    scan(STICKER_PLAIN)
    await settle(80)
    expect(assignCalls()).toHaveLength(0)
    // WMS-631 M9: a sticker of an order without KIZ is packed at once — nothing waits.
    expect(scanMessage()).not.toContain('активен')
    expect(document.body.textContent).not.toContain('Создать короб')
    expect(document.body.textContent).toContain('Внесение КИЗ со стикера — только если Честный знак уже наклеен селлером')
  })

  it('WMS-589: явная кнопка «QR» обычной поставки по-прежнему открывает предпросмотр', async () => {
    transferred = { assetReady: true }
    boxes = [box('box-1', 1, ['order-c'], true)]
    window.sessionStorage.setItem(`wms:fbs:${SUPPLY_ID}:stage`, 'boxes')
    await act(async () => {
      root.render(
        <FfFbsSupplyWorkspace
          token="t-574"
          authHeaders={() => ({ Authorization: 'Bearer t-574' })}
          supplyId={SUPPLY_ID}
          initialWorkspace={workspace()}
          open
          onClose={() => undefined}
        />,
      )
    })
    await settle(50)
    const boxesRoot = document.querySelector('[data-testid="fbs-boxes"]')!
    const qr = Array.from(boxesRoot.querySelectorAll('button')).find((button) => button.textContent === 'QR') as HTMLButtonElement
    await act(async () => qr.click())

    expect(document.body.textContent).toContain('Проверка перед печатью')
  })
})

// WMS-575, P1 ревью ночного кандидата: при русской раскладке ЧЗ со знаками
// «/», «?», «&» уходил на сервер искажённым — клиент переводил только буквы,
// и серверный ремонт раскладки не включался. Теперь рамка, как и карточка,
// отдаёт серверу сырую пачку — ровно то, что легло бы в поле скана.
describe('WMS-575 · ЧЗ в русской раскладке в активной рамке', () => {
  const LAT = "qwertyuiop[]asdfghjkl;'zxcvbnm,./"
  const RUS = 'йцукенгшщзхъфывапролджэячсмитьбю.'
  const ruKey = (ch: string): { key: string; code: string; shiftKey: boolean } => {
    if (/[0-9]/.test(ch)) return { key: ch, code: `Digit${ch}`, shiftKey: false }
    if (ch === '/') return { key: '.', code: 'Slash', shiftKey: false }
    if (ch === '?') return { key: ',', code: 'Slash', shiftKey: true }
    if (ch === '&') return { key: '?', code: 'Digit7', shiftKey: true }
    const lower = ch.toLowerCase()
    const ru = RUS[LAT.indexOf(lower)]
    return { key: ch === lower ? ru : ru.toUpperCase(), code: `Key${lower.toUpperCase()}`, shiftKey: ch !== lower }
  }
  const scanRu = (code: string) => {
    const target = document.activeElement ?? document.body
    act(() => {
      for (const ch of code) {
        const k = ruKey(ch)
        target.dispatchEvent(new KeyboardEvent('keydown', { key: k.key, code: k.code, shiftKey: k.shiftKey, bubbles: true, cancelable: true }))
      }
      target.dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter', code: 'Enter', bubbles: true, cancelable: true }))
    })
  }

  it('«/», «?», «&» уходят на validate сырыми, как из поля скана, — их чинит сервер', async () => {
    boxes = [box('box-1', 1, [], true)]
    await startFrame()
    scan(STICKER_KIZ)
    await settle(80)
    scanRu('0104600000000017215Ab/c?d&Ef9GhJ')
    await settle(80)
    const validate = calls.find((call) => call.path.includes('/kiz/validate'))
    expect(validate?.body).toMatchObject({ order_id: 'order-a', value: '0104600000000017215Фи.с,в?Уа9ПрО' })
  })
})
