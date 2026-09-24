import { describe, expect, it, vi } from 'vitest'
import { createStockDialogSession } from './fbsStockDialogSession'
import type { FbsStockDialogRow } from './fbsStockDialogLoader'

// Сеть окна «Остаток для FBS» (WMS-469) с подменным fetch: что уходит на
// сервер, что не уходит и что окно узнаёт после сбоя.

const YARTSEVO = '441c8654-b6c2-48fe-950f-65acbc921118'
const SELLER = 'e17b9df9-ae52-4054-8f8f-faa9c7e737ec'
const rowA: FbsStockDialogRow = { id: 'a', name: 'Товар А', sku_code: 'A' }
const rowB: FbsStockDialogRow = { id: 'b', name: 'Товар Б', sku_code: 'B' }

const rule = (productId: string, value: number, served = true) => ({
  product_id: productId,
  by_binding: {
    b1: {
      publish: true, mode: 'units', value, marketplace: 'wb', external_warehouse_id: '501001',
      wms_warehouse_id: YARTSEVO, served, applicable: true, on_hand: 100, reserved: 0,
      free_stock: 100, published_now: value,
    },
  },
})
const bindingsPayload = (served = true, wms = YARTSEVO) => [{
  id: 'b1', marketplace: 'wb', external_warehouse_id: null, wb_warehouse_id: 501001,
  wms_warehouse_id: wms, wms_warehouse_name: wms === YARTSEVO ? 'Ярцево' : 'Подольск',
  is_active: true, served, stock_sync_enabled: true, editable: true,
}]
const wbPayload = [{ wb_warehouse_id: 501001, served: true, wms_warehouse_id: YARTSEVO, id: 501001, name: 'E2E Seller Warehouse' }]

function json(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } })
}

type Route = (url: string, init?: RequestInit) => Response | Error | Promise<Response>
/** Подменный fetch: маршруты по подстроке адреса, журнал вызовов. */
function stub(routes: Record<string, Route>) {
  const calls: Array<{ method: string; url: string; body: unknown }> = []
  const fetchImpl = vi.fn(async (input: string | URL | Request, init?: RequestInit) => {
    const url = typeof input === 'string' ? input : input instanceof URL ? input.href : input.url
    calls.push({ method: init?.method ?? 'GET', url, body: init?.body ? JSON.parse(String(init.body)) : undefined })
    // Самый длинный подходящий ключ: '/warehouses/501001' (PUT связки) важнее '/warehouses' (список кабинета).
    const key = Object.keys(routes).filter((one) => url.includes(one)).sort((a, b) => b.length - a.length)[0]
    if (!key) throw new Error(`unexpected ${url}`)
    const answer = await routes[key]!(url, init)
    if (answer instanceof Error) throw answer
    return answer
  }) as unknown as typeof fetch
  return { fetchImpl, calls }
}

const readRoutes = (bindings = bindingsPayload(), rules = [rule('a', 30)]) => ({
  '/products/fbs-rule/bulk': () => json({ items: rules }),
  '/ozon-warehouses': () => json({ detail: 'ozon off' }, 503),
  '/warehouse-bindings': () => json(bindings),
  '/warehouses': () => json(wbPayload),
})
const session = (fetchImpl: typeof fetch) =>
  createStockDialogSession({ fetchImpl, headers: { Authorization: 'Bearer t' }, sellerId: SELLER })

describe('WMS-469 F1/F4: сохранение правила', () => {
  it('пустой набор изменений не отправляется вовсе — серверу нечего сохранять', async () => {
    const { fetchImpl, calls } = stub(readRoutes())
    const outcome = await session(fetchImpl).saveRule(['a'], {})
    expect(outcome).toEqual({ kind: 'nothing' })
    expect(calls).toHaveLength(0)
  })

  it('отправляет ровно переданные блоки вложенными в rule.by_binding и всех выбранных товаров', async () => {
    const { fetchImpl, calls } = stub({ ...readRoutes(), '/products/fbs-rule': () => json({ updated_count: 2, items: [], clamps: {} }) })
    const outcome = await session(fetchImpl).saveRule(['a', 'b'], { b1: { publish: true, mode: 'units', value: 30, units_configured: true } })
    expect(outcome).toEqual({ kind: 'saved' })
    expect(calls).toHaveLength(1)
    expect(calls[0]).toMatchObject({ method: 'PUT', url: expect.stringContaining('/products/fbs-rule') })
    expect(calls[0]!.body).toEqual({ product_ids: ['a', 'b'], rule: { by_binding: { b1: { publish: true, mode: 'units', value: 30, units_configured: true } } } })
  })

  it('обрезка сервером возвращается отдельным исходом с фактически сохранённым', async () => {
    const clamps = { b1: { requested_value: 50, saved_value: 30, limiting_product_id: 'b', limiting_product_name: 'Товар Б' } }
    const { fetchImpl } = stub({ ...readRoutes(), '/products/fbs-rule': () => json({ updated_count: 2, items: [rule('a', 30), rule('b', 30)], clamps }) })
    const outcome = await session(fetchImpl).saveRule(['a', 'b'], { b1: { publish: true, mode: 'units', value: 50, units_configured: true } })
    expect(outcome).toMatchObject({ kind: 'clamped', clamps })
    expect(outcome.kind === 'clamped' && outcome.items.map((one) => one.product_id)).toEqual(['a', 'b'])
  })

  it('R17: отказ сервера — причина и перечитанное состояние, без объявления успеха', async () => {
    const { fetchImpl, calls } = stub({ ...readRoutes(), '/products/fbs-rule': () => json({ detail: 'binding_not_found' }, 422) })
    const s = session(fetchImpl)
    await s.load([rowA])
    const outcome = await s.saveRule(['a'], { b1: { publish: true, mode: 'units', value: 30, units_configured: true } })
    expect(outcome).toMatchObject({ kind: 'error', message: 'binding_not_found' })
    expect(outcome.kind === 'error' && outcome.data?.products[0]?.id).toBe('a')
    // Открытие (4) + PUT + перечитывание (4).
    expect(calls.filter((one) => one.method === 'PUT')).toHaveLength(1)
    expect(calls).toHaveLength(9)
  })

  it('R17: потеря ответа — то же: причина и перечитанное состояние', async () => {
    const { fetchImpl } = stub({ ...readRoutes(), '/products/fbs-rule': () => new TypeError('Failed to fetch') })
    const s = session(fetchImpl)
    await s.load([rowA])
    const outcome = await s.saveRule(['a'], { b1: { publish: true, mode: 'units', value: 30, units_configured: true } })
    expect(outcome).toMatchObject({ kind: 'error', message: 'Failed to fetch' })
    expect(outcome.kind === 'error' && outcome.data).not.toBeNull()
  })
})

describe('WMS-469 F5: немедленные действия со связкой', () => {
  it('успех: PUT с площадкой и телом, затем перечитанное состояние', async () => {
    let served = true
    const { fetchImpl, calls } = stub({
      ...readRoutes(),
      '/warehouse-bindings': () => json(bindingsPayload(served)),
      '/warehouses/501001': (_url, init) => { served = (JSON.parse(String(init?.body)) as { served: boolean }).served; return json({ wb_warehouse_id: 501001, served }) },
    })
    const s = session(fetchImpl)
    await s.load([rowA])
    const outcome = await s.putBinding('wb', '501001', { wms_warehouse_id: YARTSEVO, served: false })
    expect(outcome.ok).toBe(true)
    expect(outcome.data?.bindings[0]).toMatchObject({ id: 'b1', served: false })
    const put = calls.find((one) => one.method === 'PUT')
    expect(put).toMatchObject({ url: expect.stringContaining(`/fbs-sellers/${SELLER}/warehouses/501001`) })
    expect(put!.body).toEqual({ marketplace: 'wb', wms_warehouse_id: YARTSEVO, served: false })
  })

  it('B02/B09: ответ потерян после записи — окно перечитывает и держит фактический склад', async () => {
    const PODOLSK = '22a638eb-9f3a-4555-aedd-b8ba9cb4456d'
    let wms = YARTSEVO
    const { fetchImpl } = stub({
      ...readRoutes(),
      '/warehouse-bindings': () => json(bindingsPayload(true, wms)),
      // Сервер записал, а ответ до окна не дошёл.
      '/warehouses/501001': (_url, init) => { wms = (JSON.parse(String(init?.body)) as { wms_warehouse_id: string }).wms_warehouse_id; return new TypeError('Failed to fetch') },
    })
    const s = session(fetchImpl)
    await s.load([rowA])
    const outcome = await s.putBinding('wb', '501001', { wms_warehouse_id: PODOLSK, served: true })
    expect(outcome.ok).toBe(false)
    expect(outcome).toMatchObject({ message: 'Failed to fetch' })
    expect(outcome.data?.bindings[0]).toMatchObject({ wmsWarehouseId: PODOLSK, wmsWarehouseName: 'Подольск' })
  })

  it('отказ сервера с причиной: причина из конверта, состояние перечитано', async () => {
    const { fetchImpl } = stub({ ...readRoutes(), '/warehouses/501001': () => json({ detail: 'forbidden' }, 403) })
    const s = session(fetchImpl)
    await s.load([rowA])
    const outcome = await s.putBinding('wb', '501001', { wms_warehouse_id: YARTSEVO, served: false })
    expect(outcome).toMatchObject({ ok: false, message: 'forbidden' })
    expect(outcome.data?.bindings[0]).toMatchObject({ served: true })
  })

  it('если после отказа и перечитать не удалось — данных нет, окно оставит прежние', async () => {
    let failReads = false
    const { fetchImpl } = stub({
      '/products/fbs-rule/bulk': () => (failReads ? new TypeError('offline') : json({ items: [rule('a', 30)] })),
      '/ozon-warehouses': () => json({}, 503),
      '/warehouse-bindings': () => json(bindingsPayload()),
      '/warehouses': () => json(wbPayload),
      '/warehouses/501001': () => { failReads = true; return new TypeError('offline') },
    })
    const s = session(fetchImpl)
    await s.load([rowA])
    const outcome = await s.putBinding('wb', '501001', { wms_warehouse_id: YARTSEVO, served: false })
    expect(outcome).toEqual({ ok: false, message: 'offline', data: null })
  })
})

describe('WMS-469 F3: смена выбора во время загрузки', () => {
  it('ответ прежней загрузки отбрасывается, окно получает данные последнего выбора', async () => {
    const waiters: Array<() => void> = []
    const { fetchImpl } = stub({
      // Правила отвечают по команде теста — в порядке, обратном запросам.
      '/products/fbs-rule/bulk': (_url, init) => new Promise((resolve) => {
        const ids = (JSON.parse(String(init?.body)) as { product_ids: string[] }).product_ids
        waiters.push(() => resolve(json({ items: ids.map((id) => rule(id, 30)) })))
      }),
      '/ozon-warehouses': () => json({}, 503),
      '/warehouse-bindings': () => json(bindingsPayload()),
      '/warehouses': () => json(wbPayload),
    })
    const s = session(fetchImpl)
    const first = s.load([rowA])
    const second = s.load([rowB])
    expect(waiters).toHaveLength(2)
    waiters[0]!()
    await expect(first).resolves.toBeNull()
    waiters[1]!()
    const data = await second
    expect(data?.products.map((one) => one.id)).toEqual(['b'])
  })

  it('перечитывание после действия идёт по последнему выбору', async () => {
    const { fetchImpl, calls } = stub({ ...readRoutes(), '/warehouses/501001': () => json({ wb_warehouse_id: 501001, served: true }) })
    const s = session(fetchImpl)
    await s.load([rowA])
    await s.load([rowB])
    await s.putBinding('wb', '501001', { wms_warehouse_id: YARTSEVO, served: true })
    const reads = calls.filter((one) => one.url.includes('/fbs-rule/bulk')).map((one) => (one.body as { product_ids: string[] }).product_ids)
    expect(reads).toEqual([['a'], ['b'], ['b']])
  })
})
