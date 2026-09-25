import { afterEach, describe, expect, it, vi } from 'vitest'
import { loadFbsStockDialog, type FbsStockDialogRow } from './fbsStockDialogLoader'

// F2 ревью Astra (WMS-457): отклонённый fetch справочника (нет HTTP-ответа
// вовсе — обрыв, тайм-аут) ронял открытие окна целиком, хотя правила и
// привязки приехали. Здесь исполняется настоящий загрузчик с подменным fetch:
// каждый из двух справочников отклоняется по отдельности, обязательные запросы
// правил и привязок — отдельно. Форма данных — блоки по привязкам (WMS-469).

const YARTSEVO = '441c8654-b6c2-48fe-950f-65acbc921118'
const SELLER = 'e17b9df9-ae52-4054-8f8f-faa9c7e737ec'
const chosen: FbsStockDialogRow[] = [{ id: 'product-1', name: 'Худи', sku_code: 'HD-GRY-L', wb_size: 'L' }]
const wbRule = {
  publish: true, mode: 'units', value: 30, units_configured: true, marketplace: 'wb', external_warehouse_id: '501001',
  wms_warehouse_id: YARTSEVO, served: true, applicable: true, on_hand: 100, reserved: 0,
  free_stock: 100, published_now: 30,
}
const ozonRule = { ...wbRule, mode: 'percent', value: 40, units_configured: false, marketplace: 'ozon',
  external_warehouse_id: '1020005029603630', published_now: 40 }
const rulesPayload = { items: [{
  product_id: 'product-1', publish: true, publish_ozon: true, same_everywhere: false, percent: 0,
  by_warehouse: {}, units_mode: false, units_by_warehouse: {}, units_remaining_by_warehouse: {},
  free_stock: 100, on_hand: 100, reserved: 0, published_now: 70,
  by_binding: { b1: wbRule, b2: ozonRule },
}] }
const wbPayload = [{ wb_warehouse_id: 501001, served: true, wms_warehouse_id: YARTSEVO,
  id: 501001, name: 'E2E Seller Warehouse' }]
const bindingsPayload = [
  { id: 'b1', marketplace: 'wb', external_warehouse_id: null, wb_warehouse_id: 501001,
    wms_warehouse_id: YARTSEVO, wms_warehouse_name: 'Ярцево', is_active: true, served: true,
    stock_sync_enabled: true, editable: true },
  { id: 'b2', marketplace: 'ozon', external_warehouse_id: '1020005029603630',
    wb_warehouse_id: 1020005029603630, wms_warehouse_id: YARTSEVO, wms_warehouse_name: 'Ярцево',
    is_active: true, served: true, stock_sync_enabled: true, editable: true },
]
const ozonPayload = [{ warehouse_id: 1020005029603630, name: 'Хоругвино',
  has_entrusted_acceptance: false, is_rfbs: false, served: true, wms_warehouse_id: YARTSEVO }]
const ozonBlocked = { detail: { code: 'ozon_live_warehouses_blocked',
  message: 'Справочник складов Ozon недоступен: боевые запросы к Ozon выключены настройкой WMS_OZON_LIVE_API.',
  context: {}, retryable: false } }

type Answer = Response | Error
function json(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } })
}
// Ответ 200 пришёл, а поток тела оборвался: fetch выполнился, json() отклоняется.
function interrupted(): Response {
  return new Response(new ReadableStream({
    start(controller) {
      controller.enqueue(new TextEncoder().encode('[{"name":'))
      controller.error(new TypeError('terminated while reading response body'))
    },
  }), { status: 200, headers: { 'Content-Type': 'application/json' } })
}
function stubFetch(answers: { rules?: Answer; wb?: Answer; bindings?: Answer; ozon?: Answer }) {
  const fetchMock = vi.fn(async (input: string | URL | Request) => {
    const url = typeof input === 'string' ? input : input instanceof URL ? input.href : input.url
    const pick = url.includes('/fbs-rule/bulk') ? answers.rules ?? json(rulesPayload)
      : url.endsWith('/ozon-warehouses') ? answers.ozon ?? json(ozonPayload)
      : url.endsWith('/warehouse-bindings') ? answers.bindings ?? json(bindingsPayload)
      : url.endsWith('/warehouses') ? answers.wb ?? json(wbPayload)
      : new Error(`unexpected ${url}`)
    if (pick instanceof Error) throw pick
    return pick
  })
  vi.stubGlobal('fetch', fetchMock)
  return fetchMock
}
const load = () => loadFbsStockDialog({ headers: { Authorization: 'Bearer token' }, sellerId: SELLER, chosen })
const named = (data: Awaited<ReturnType<typeof load>>) =>
  data.bindings.map((one) => [one.id, one.name, one.nameIssue])

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('loadFbsStockDialog', () => {
  it('names blocks from both cabinets when everything answers', async () => {
    const fetchMock = stubFetch({})
    const data = await load()
    expect(fetchMock).toHaveBeenCalledTimes(4)
    expect(data.wbWarehousesError).toBeNull()
    expect(data.ozonWarehousesError).toBeNull()
    expect(named(data)).toEqual([['b1', 'E2E Seller Warehouse', undefined], ['b2', 'Хоругвино', undefined]])
    expect(data.bindings[0]).toMatchObject({ marketplace: 'wb', externalId: '501001', wmsWarehouseId: YARTSEVO,
      wmsWarehouseName: 'Ярцево', served: true, editable: true })
    expect(data.products[0]).toMatchObject({ id: 'product-1', name: 'Худи', sku: 'HD-GRY-L', size: 'L' })
    expect(data.products[0]!.byBinding).toEqual({
      b1: { publish: true, mode: 'units', value: 30, unitsConfigured: true, applicable: true, onHand: 100, reserved: 0, freeStock: 100 },
      b2: { publish: true, mode: 'percent', value: 40, unitsConfigured: false, applicable: true, onHand: 100, reserved: 0, freeStock: 100 },
    })
    expect(data.cabinets.wb).toMatchObject({ received: true })
    expect(data.cabinets.ozon).toMatchObject({ received: true })
  })

  it('opens the window when the WB cabinet request never gets a response', async () => {
    stubFetch({ wb: new TypeError('Failed to fetch'), ozon: json(ozonBlocked, 503) })
    const data = await load()
    expect(data.wbWarehousesError).toBe(
      'Wildberries не ответил на запрос складов: Failed to fetch. Ниже показаны сохранённые привязки без названий.',
    )
    expect(data.ozonWarehousesError).toContain('Справочник складов Ozon недоступен')
    expect(named(data)).toEqual([
      ['b1', '№ 501001', 'list_unavailable'],
      ['b2', '№ 1020005029603630', 'list_unavailable'],
    ])
    expect(data.bindings.every((one) => one.served && one.wmsWarehouseId === YARTSEVO)).toBe(true)
    // Правила по привязкам приехали — блокам есть из чего строиться.
    expect(Object.keys(data.products[0]!.byBinding)).toEqual(['b1', 'b2'])
    expect(data.cabinets).toEqual({ wb: { received: false }, ozon: { received: false } })
  })

  it('opens the window when the Ozon directory request never gets a response', async () => {
    stubFetch({ ozon: new TypeError('Failed to fetch') })
    const data = await load()
    expect(data.wbWarehousesError).toBeNull()
    expect(data.ozonWarehousesError).toBe(
      'Справочник складов Ozon не получен: Failed to fetch. Ниже показаны сохранённые привязки без названий.',
    )
    expect(named(data)).toEqual([['b1', 'E2E Seller Warehouse', undefined], ['b2', '№ 1020005029603630', 'list_unavailable']])
  })

  it('opens the window when the WB cabinet response body breaks while being read', async () => {
    stubFetch({ wb: interrupted() })
    const data = await load()
    expect(data.wbWarehousesError).toBe(
      'Wildberries не ответил на запрос складов: terminated while reading response body. Ниже показаны сохранённые привязки без названий.',
    )
    expect(data.ozonWarehousesError).toBeNull()
    expect(named(data)).toEqual([['b1', '№ 501001', 'list_unavailable'], ['b2', 'Хоругвино', undefined]])
  })

  it('opens the window when the Ozon directory response body breaks while being read', async () => {
    stubFetch({ ozon: interrupted() })
    const data = await load()
    expect(data.wbWarehousesError).toBeNull()
    expect(data.ozonWarehousesError).toBe(
      'Справочник складов Ozon не получен: terminated while reading response body. Ниже показаны сохранённые привязки без названий.',
    )
    expect(named(data)).toEqual([['b1', 'E2E Seller Warehouse', undefined], ['b2', '№ 1020005029603630', 'list_unavailable']])
  })

  it('does not open the window when the rules response body breaks while being read', async () => {
    stubFetch({ rules: interrupted() })
    await expect(load()).rejects.toThrow('terminated while reading response body')
  })

  it('still reads the reason from an HTTP error envelope of the WB cabinet', async () => {
    stubFetch({ wb: json({ detail: { code: 'wb_upstream_error_401', message: 'Ошибка Wildberries.',
      context: {}, retryable: true } }, 502) })
    const data = await load()
    expect(data.wbWarehousesError).toBe(
      'Wildberries не принял ключ продавца — он отозван или недействителен. Пока ключ не заменят, названия складов, заказы и остатки FBS этого продавца не приходят.',
    )
    // Порядок — порядок сервера по привязкам, а не по кабинетам.
    expect(named(data)).toEqual([['b1', '№ 501001', 'list_unavailable'], ['b2', 'Хоругвино', undefined]])
  })

  it('does not open the window without the rules: the request is rejected', async () => {
    stubFetch({ rules: new TypeError('Failed to fetch') })
    await expect(load()).rejects.toThrow('Failed to fetch')
  })

  it('does not open the window without the rules: the server refuses', async () => {
    stubFetch({ rules: json({ detail: 'seller_not_found' }, 404) })
    await expect(load()).rejects.toThrow('seller_not_found')
  })

  it('does not open the window without the bindings: blocks have nothing to be built from', async () => {
    stubFetch({ bindings: json({ detail: 'forbidden' }, 403) })
    await expect(load()).rejects.toThrow('forbidden')
  })

  it('keeps a product without a rule entry with empty by_binding instead of inventing numbers', async () => {
    stubFetch({ rules: json({ items: [] }) })
    const data = await load()
    expect(data.products[0]!.byBinding).toEqual({})
  })

  it('WMS-483 keeps an unset units limit distinct from an explicit zero', async () => {
    const unset = { ...wbRule, value: 0, units_configured: false }
    stubFetch({ rules: json({ items: [{ ...rulesPayload.items[0], by_binding: { b1: unset } }] }) })
    const data = await load()
    expect(data.products[0]!.byBinding.b1).toMatchObject({
      mode: 'units', value: 0, unitsConfigured: false,
    })
  })
})
