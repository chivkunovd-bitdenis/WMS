import type { ReactNode } from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import { describe, expect, it, vi } from 'vitest'
import { FbsStockDialog } from './FbsStockDialog'
import {
  buildSellerWarehouseRows,
  fbsWarehousesLoadError,
  readFbsErrorEnvelope,
  warehouseNameIssueHint,
  type CabinetList,
  type SavedWarehouseBinding,
} from './fbsSellerWarehouseRows'
import { toProduct, toRule, type ApiRule } from './FfProductsFbsPage'
import type { Seller } from './stub'

vi.mock('../../../ui-kit', async (original) => ({
  ...await original<object>(),
  // Only remove the portal for SSR; all fields and dialog content are real.
  AppDialog: ({ children, actions }: { children: ReactNode; actions: ReactNode }) =>
    <div>{children}{actions}</div>,
}))

const YARTSEVO = '441c8654-b6c2-48fe-950f-65acbc921118'
const wbCabinet: CabinetList = {
  received: true,
  rows: [{ wb_warehouse_id: 501001, name: 'E2E Seller Warehouse', wms_warehouse_id: YARTSEVO,
    served: true, marketplace: 'wb' }],
}
const bindings: SavedWarehouseBinding[] = [
  { wb_warehouse_id: 501001, wms_warehouse_id: YARTSEVO, is_active: true, served: true, marketplace: 'wb' },
  { wb_warehouse_id: 501999, wms_warehouse_id: YARTSEVO, is_active: true, served: false, marketplace: 'wb' },
  { wb_warehouse_id: 501998, wms_warehouse_id: YARTSEVO, is_active: false, served: false, marketplace: 'wb' },
  { wb_warehouse_id: 1020005029603630, wms_warehouse_id: YARTSEVO, is_active: true, served: true,
    marketplace: 'ozon', external_warehouse_id: '1020005029603630' },
]

describe('WMS-457 C7 seller warehouse rows for the stock window', () => {
  it('names cabinet rows from the cabinet and numbers the rest with a reason', () => {
    const rows = buildSellerWarehouseRows({ wb: wbCabinet, ozon: { received: false } }, bindings)
    expect(rows.map((one) => one.id)).toEqual(['wb:501001', 'wb:501999', 'ozon:1020005029603630'])
    expect(rows[0]).toEqual({ id: 'wb:501001', name: 'E2E Seller Warehouse', boundTo: YARTSEVO,
      fbsEnabled: true, marketplace: 'wb' })
    expect(rows[0]!.nameIssue).toBeUndefined()
    expect(rows[1]).toMatchObject({ name: '№ 501999', fbsEnabled: false, boundTo: YARTSEVO,
      marketplace: 'wb', nameIssue: 'not_in_cabinet' })
    expect(rows[2]).toMatchObject({ name: '№ 1020005029603630', fbsEnabled: true,
      marketplace: 'ozon', nameIssue: 'list_unavailable' })
    expect(rows.some((one) => one.id === 'wb:501998')).toBe(false)
  })

  it('marks every saved active WB binding as unnamed when the WB list was not received', () => {
    const rows = buildSellerWarehouseRows(
      { wb: { received: false }, ozon: { received: false } }, bindings,
    )
    expect(rows.map((one) => [one.id, one.name, one.nameIssue])).toEqual([
      ['wb:501001', '№ 501001', 'list_unavailable'],
      ['wb:501999', '№ 501999', 'list_unavailable'],
      ['ozon:1020005029603630', '№ 1020005029603630', 'list_unavailable'],
    ])
  })

  it('shows an inactive binding only through its cabinet row, with the checkbox off', () => {
    const rows = buildSellerWarehouseRows(
      { wb: { received: true, rows: [{ wb_warehouse_id: 501998, name: 'Старый склад',
        wms_warehouse_id: YARTSEVO, served: false, marketplace: 'wb' }] },
        ozon: { received: false } },
      [bindings[2]!],
    )
    expect(rows).toEqual([{ id: 'wb:501998', name: 'Старый склад', boundTo: YARTSEVO,
      fbsEnabled: false, marketplace: 'wb' }])
  })

  it('C8 keeps the Ozon directory name and flags an Ozon binding missing from the directory', () => {
    const rows = buildSellerWarehouseRows(
      { wb: { received: true, rows: [] },
        ozon: { received: true, rows: [{ wb_warehouse_id: 1020005029603630, name: 'Хоругвино',
          wms_warehouse_id: YARTSEVO, served: true, marketplace: 'ozon' }] } },
      [bindings[3]!, { wb_warehouse_id: 1020005029603631, wms_warehouse_id: YARTSEVO,
        is_active: true, served: true, marketplace: 'ozon', external_warehouse_id: '1020005029603631' }],
    )
    expect(rows).toHaveLength(2)
    expect(rows[0]).toEqual({ id: 'ozon:1020005029603630', name: 'Хоругвино', boundTo: YARTSEVO,
      fbsEnabled: true, marketplace: 'ozon' })
    expect(rows[1]).toMatchObject({ id: 'ozon:1020005029603631', name: '№ 1020005029603631',
      nameIssue: 'not_in_cabinet' })
    expect(warehouseNameIssueHint('not_in_cabinet', 'ozon'))
      .toBe('В кабинете Ozon склада с таким номером нет: он удалён или принадлежит другому продавцу')
    expect(warehouseNameIssueHint('not_in_cabinet', 'wb'))
      .toBe('В кабинете Wildberries склада с таким номером нет: он удалён или принадлежит другому продавцу')
    expect(warehouseNameIssueHint('list_unavailable', 'wb'))
      .toBe('Список складов из кабинета не получен, поэтому названия нет — причина в сообщении выше')
  })

  it('renders the reason chips and hints next to the served checkbox', () => {
    const seller: Seller = {
      id: 'seller', name: 'ИП Тестовый Аудит', wbWarehouses: [{ id: YARTSEVO, name: 'Ярцево' }],
      warehouses: buildSellerWarehouseRows({ wb: wbCabinet, ozon: { received: false } }, bindings),
    }
    const apiRule: ApiRule = {
      publish: true, publish_ozon: true, same_everywhere: false, percent: 0,
      by_warehouse: { 'wb:501001': 60, 'ozon:1020005029603630': 40 }, units_mode: false,
      units_by_warehouse: {}, units_remaining_by_warehouse: {}, on_hand: 100, reserved: 0,
      free_stock: 100, published_now: 100,
    }
    const row = { id: 'product', seller_id: 'seller', name: 'Худи', sku_code: 'HD-GRY-L',
      wb_primary_barcode: null, marketplaces: ['wb', 'ozon'] }
    const markup = renderToStaticMarkup(<FbsStockDialog open
      products={[toProduct(row, apiRule, 'seller')]} seller={seller}
      rule={toRule(row.id, apiRule)} onClose={() => {}} onSave={() => {}} onBind={() => {}}
      onServedChange={() => {}} ozonWarehousesError="Справочник складов Ozon недоступен" />)
    expect(markup).toContain('Принимаем заказы продавца со склада «E2E Seller Warehouse»')
    expect(markup).not.toContain('data-testid="fbs-stock-name-issue-wb:501001"')
    expect(markup).toContain('Принимаем заказы продавца со склада «№ 501999»')
    expect(markup).toContain('data-testid="fbs-stock-name-issue-wb:501999"')
    expect(markup).toContain('нет в кабинете')
    expect(markup).toContain('заказы не принимаем')
    expect(markup).toContain('Принимаем заказы продавца со склада «№ 1020005029603630»')
    expect(markup).toContain('data-testid="fbs-stock-name-issue-ozon:1020005029603630"')
    expect(markup).toContain('название недоступно')
    expect(markup).toContain('Справочник складов Ozon недоступен')
    expect(markup).not.toContain('Склад Ozon 1020005029603630')
    expect(markup).not.toContain('Склад WB 501999')
  })

  it('keeps the Wildberries reason banner apart from the save error', () => {
    const seller: Seller = {
      id: 'seller', name: 'ИП Без ключа', wbWarehouses: [{ id: YARTSEVO, name: 'Ярцево' }],
      warehouses: buildSellerWarehouseRows(
        { wb: { received: false }, ozon: { received: false } },
        [{ wb_warehouse_id: 777001, wms_warehouse_id: YARTSEVO, is_active: true, served: true,
          marketplace: 'wb' }],
      ),
    }
    const row = { id: 'product', seller_id: 'seller', name: 'Кепка', sku_code: 'CAP-NOKEY',
      wb_primary_barcode: null, marketplaces: ['wb'] }
    const reason = fbsWarehousesLoadError({ status: 403, code: 'missing_marketplace_token',
      message: 'Нет токена WB Marketplace.' })
    const markup = renderToStaticMarkup(<FbsStockDialog open
      products={[toProduct(row, undefined, 'seller')]} seller={seller}
      rule={toRule(row.id, undefined)} onClose={() => {}} onSave={() => {}} onBind={() => {}}
      onServedChange={() => {}} wbWarehousesError={reason} saveError={null} />)
    expect(markup).toContain('data-testid="fbs-stock-wb-directory-error"')
    expect(markup).toContain('У продавца не сохранён ключ Wildberries с правами «Маркетплейс»')
    expect(markup).not.toContain('data-testid="fbs-stock-error"')
    expect(markup).toContain('Принимаем заказы продавца со склада «№ 777001»')
    expect(markup).toContain('название недоступно')
  })
})

describe('WMS-457 C6 reason of a failed Wildberries warehouse list by envelope code', () => {
  it.each([
    { code: 'missing_marketplace_token', status: 403, message: 'Нет токена WB Marketplace.',
      expected: 'У продавца не сохранён ключ Wildberries с правами «Маркетплейс». Без него названия складов, заказы и остатки FBS не приходят.' },
    { code: 'wb_upstream_error_401', status: 502, message: 'Ошибка Wildberries.',
      expected: 'Wildberries не принял ключ продавца — он отозван или недействителен. Пока ключ не заменят, названия складов, заказы и остатки FBS этого продавца не приходят.' },
    { code: 'wb_upstream_error_403', status: 502, message: 'Ошибка Wildberries.',
      expected: 'У ключа Wildberries продавца нет прав «Маркетплейс». Нужен ключ с этой категорией.' },
    { code: 'wb_transport_error', status: 502, message: 'Ошибка Wildberries.',
      expected: 'Wildberries не ответил на запрос складов: Ошибка Wildberries.. Ниже показаны сохранённые привязки без названий.' },
    { code: 'wb_upstream_error_500', status: 502, message: 'Ошибка Wildberries.',
      expected: 'Wildberries не ответил на запрос складов: Ошибка Wildberries.. Ниже показаны сохранённые привязки без названий.' },
  ])('$code/$status', ({ code, status, message, expected }) => {
    const text = fbsWarehousesLoadError({ status, code, message })
    expect(text).toBe(expected)
    if (code === 'wb_upstream_error_401') expect(text.toLowerCase()).not.toContain('прав')
  })

  it('keeps the generic text for responses without an FBS envelope', () => {
    expect(fbsWarehousesLoadError({ status: 403, code: null, message: 'Нет доступа' }))
      .toBe('Не удалось загрузить склады Wildberries: Нет доступа')
    expect(fbsWarehousesLoadError({ status: 404, code: 'seller_not_found', message: 'Селлер не найден.' }))
      .toBe('Не удалось загрузить склады Wildberries: Селлер не найден.')
  })

  it('reads the code and the message from the server envelope', async () => {
    const envelope = await readFbsErrorEnvelope(new Response(JSON.stringify({
      detail: { code: 'wb_upstream_error_401', message: 'Ошибка Wildberries.', context: {}, retryable: true },
    }), { status: 502 }))
    expect(envelope).toEqual({ status: 502, code: 'wb_upstream_error_401', message: 'Ошибка Wildberries.' })
    expect(await readFbsErrorEnvelope(new Response(JSON.stringify({ detail: 'forbidden' }), { status: 403 })))
      .toEqual({ status: 403, code: null, message: 'forbidden' })
    expect(await readFbsErrorEnvelope(new Response('', { status: 502 })))
      .toEqual({ status: 502, code: null, message: 'Ошибка 502' })
  })
})
