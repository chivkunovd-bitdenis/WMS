import { afterEach, describe, expect, it, vi } from 'vitest'
import { loadFbsStockDialog, type FbsStockDialogRow } from './fbsStockDialogLoader'

// F2 ревью Astra: отклонённый fetch справочника (нет HTTP-ответа вовсе — обрыв,
// тайм-аут) ронял открытие окна целиком, хотя правила и привязки приехали.
// Здесь исполняется настоящий загрузчик с подменным fetch: каждый из двух
// справочников отклоняется по отдельности, обязательный запрос правил —
// отдельно.

const YARTSEVO = '441c8654-b6c2-48fe-950f-65acbc921118'
const SELLER = 'e17b9df9-ae52-4054-8f8f-faa9c7e737ec'
const chosen: FbsStockDialogRow[] = [{
  id: 'product-1', seller_id: SELLER, seller_name: 'ИП Тестовый Аудит', name: 'Худи',
  sku_code: 'HD-GRY-L', wb_size: 'L', wb_primary_barcode: '4680123456796', marketplaces: ['wb', 'ozon'],
}]
const rulesPayload = { items: [{
  product_id: 'product-1', publish: true, publish_ozon: true, same_everywhere: false, percent: 0,
  by_warehouse: { 501001: 60, 1020005029603630: 40 }, units_mode: false,
  units_by_warehouse: {}, units_remaining_by_warehouse: {}, free_stock: 100, on_hand: 100,
  reserved: 0, published_now: 100,
}] }
const wbPayload = [{ wb_warehouse_id: 501001, served: true, wms_warehouse_id: YARTSEVO,
  id: 501001, name: 'E2E Seller Warehouse' }]
const bindingsPayload = [
  { id: 'b1', marketplace: 'wb', external_warehouse_id: null, wb_warehouse_id: 501001,
    wms_warehouse_id: YARTSEVO, is_active: true, served: true, stock_sync_enabled: true },
  { id: 'b2', marketplace: 'ozon', external_warehouse_id: '1020005029603630',
    wb_warehouse_id: 1020005029603630, wms_warehouse_id: YARTSEVO, is_active: true,
    served: true, stock_sync_enabled: true },
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
const load = () => loadFbsStockDialog({
  headers: { Authorization: 'Bearer token' }, sellerId: SELLER, sellerName: 'ИП Тестовый Аудит',
  chosen, wmsWarehouses: [{ id: YARTSEVO, name: 'Ярцево' }],
})

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('loadFbsStockDialog', () => {
  it('names rows from both cabinets when everything answers', async () => {
    const fetchMock = stubFetch({})
    const data = await load()
    expect(fetchMock).toHaveBeenCalledTimes(4)
    expect(data.wbWarehousesError).toBeNull()
    expect(data.ozonWarehousesError).toBeNull()
    expect(data.seller.warehouses.map((one) => [one.id, one.name, one.nameIssue])).toEqual([
      ['wb:501001', 'E2E Seller Warehouse', undefined],
      ['ozon:1020005029603630', 'Хоругвино', undefined],
    ])
    expect(data.rule).toMatchObject({ sameEverywhere: false,
      byWarehouse: { 'wb:501001': 60, 'ozon:1020005029603630': 40 } })
    expect(data.products[0]).toMatchObject({ id: 'product-1', marketplaces: ['wb', 'ozon'], savedPublishedNow: 100 })
    expect(data.seller.wbWarehouses).toEqual([{ id: YARTSEVO, name: 'Ярцево' }])
  })

  it('opens the window when the WB cabinet request never gets a response', async () => {
    stubFetch({ wb: new TypeError('Failed to fetch'), ozon: json(ozonBlocked, 503) })
    const data = await load()
    expect(data.wbWarehousesError).toBe(
      'Wildberries не ответил на запрос складов: Failed to fetch. Ниже показаны сохранённые привязки без названий.',
    )
    expect(data.ozonWarehousesError).toContain('Справочник складов Ozon недоступен')
    expect(data.seller.warehouses.map((one) => [one.id, one.name, one.nameIssue])).toEqual([
      ['wb:501001', '№ 501001', 'list_unavailable'],
      ['ozon:1020005029603630', '№ 1020005029603630', 'list_unavailable'],
    ])
    expect(data.seller.warehouses.every((one) => one.fbsEnabled && one.boundTo === YARTSEVO)).toBe(true)
    expect(data.rule.byWarehouse).toEqual({ 'wb:501001': 60, 'ozon:1020005029603630': 40 })
  })

  it('opens the window when the Ozon directory request never gets a response', async () => {
    stubFetch({ ozon: new TypeError('Failed to fetch') })
    const data = await load()
    expect(data.wbWarehousesError).toBeNull()
    expect(data.ozonWarehousesError).toBe(
      'Справочник складов Ozon не получен: Failed to fetch. Ниже показаны сохранённые привязки без названий.',
    )
    expect(data.seller.warehouses.map((one) => [one.id, one.name, one.nameIssue])).toEqual([
      ['wb:501001', 'E2E Seller Warehouse', undefined],
      ['ozon:1020005029603630', '№ 1020005029603630', 'list_unavailable'],
    ])
  })

  it('opens the window when the WB cabinet response body breaks while being read', async () => {
    stubFetch({ wb: interrupted() })
    const data = await load()
    expect(data.wbWarehousesError).toBe(
      'Wildberries не ответил на запрос складов: terminated while reading response body. Ниже показаны сохранённые привязки без названий.',
    )
    expect(data.ozonWarehousesError).toBeNull()
    expect(data.seller.warehouses.map((one) => [one.id, one.name, one.nameIssue])).toEqual([
      ['ozon:1020005029603630', 'Хоругвино', undefined],
      ['wb:501001', '№ 501001', 'list_unavailable'],
    ])
    expect(data.rule.byWarehouse).toEqual({ 'wb:501001': 60, 'ozon:1020005029603630': 40 })
  })

  it('opens the window when the Ozon directory response body breaks while being read', async () => {
    stubFetch({ ozon: interrupted() })
    const data = await load()
    expect(data.wbWarehousesError).toBeNull()
    expect(data.ozonWarehousesError).toBe(
      'Справочник складов Ozon не получен: terminated while reading response body. Ниже показаны сохранённые привязки без названий.',
    )
    expect(data.seller.warehouses.map((one) => [one.id, one.name, one.nameIssue])).toEqual([
      ['wb:501001', 'E2E Seller Warehouse', undefined],
      ['ozon:1020005029603630', '№ 1020005029603630', 'list_unavailable'],
    ])
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
    // Порядок прежний: строки полученного кабинета (Ozon), затем привязки без строки.
    expect(data.seller.warehouses.map((one) => [one.id, one.name, one.nameIssue])).toEqual([
      ['ozon:1020005029603630', 'Хоругвино', undefined],
      ['wb:501001', '№ 501001', 'list_unavailable'],
    ])
  })

  it('does not open the window without the rules: the request is rejected', async () => {
    stubFetch({ rules: new TypeError('Failed to fetch') })
    await expect(load()).rejects.toThrow('Failed to fetch')
  })

  it('does not open the window without the rules: the server refuses', async () => {
    stubFetch({ rules: json({ detail: 'seller_not_found' }, 404) })
    await expect(load()).rejects.toThrow('seller_not_found')
  })
})

// Номера складов Wildberries и Ozon из разных пространств и совпадают. Площадку
// номера в правиле определяют действующие привязки — ровно те, по которым его
// собрал сервер. Справочник кабинета на эту роль не годится: отключённая
// привязка остаётся в нём сопоставленной строкой, и её номер забирал себе
// озоновский лимит.
describe('loadFbsStockDialog при совпадении номеров складов', () => {
  const collidingRules = () => json({ items: [{ ...rulesPayload.items[0]!, by_warehouse: {},
    units_mode: true, units_by_warehouse: { 777: 0 }, units_remaining_by_warehouse: { 777: 0 } }] })
  const collidingWb = () => json([{ wb_warehouse_id: 777, served: true, wms_warehouse_id: YARTSEVO,
    id: 777, name: 'Коледино' }])
  // Склада 777 в справочнике Ozon нет — его строка приходит сохранённой
  // привязкой. В кабинете Wildberries номер есть: по одному только справочнику
  // ноль выглядел бы лимитом склада Wildberries, и никакой ошибки бы не было.
  const collidingOzon = () => json([])
  const collidingBindings = () => json([
    { id: 'b1', marketplace: 'wb', external_warehouse_id: null, wb_warehouse_id: 777,
      wms_warehouse_id: YARTSEVO, is_active: false, served: true, stock_sync_enabled: true },
    { id: 'b2', marketplace: 'ozon', external_warehouse_id: '777', wb_warehouse_id: 777,
      wms_warehouse_id: YARTSEVO, is_active: true, served: true, stock_sync_enabled: true },
  ])

  it('отдаёт номер тому складу, чья привязка действует', async () => {
    stubFetch({ rules: collidingRules(), wb: collidingWb(), ozon: collidingOzon(),
      bindings: collidingBindings() })
    const data = await load()
    // Ноль оператора остаётся озоновским: строка Wildberries показывает пустое поле.
    expect(data.rule.unitsByWarehouse).toEqual({ 'ozon:777': 0 })
  })

  it('не берёт площадку из справочника кабинета, когда привязки не отдали', async () => {
    stubFetch({ rules: collidingRules(), wb: collidingWb(), ozon: collidingOzon(),
      bindings: json({ detail: 'Не удалось прочитать привязки складов продавца.' }, 500) })
    // Без привязок ноль выглядел бы лимитом склада Wildberries 777 и ушёл бы
    // туда при сохранении, поэтому окно не открывается вовсе.
    await expect(load()).rejects.toThrow('Не удалось прочитать привязки складов продавца.')
  })
})
