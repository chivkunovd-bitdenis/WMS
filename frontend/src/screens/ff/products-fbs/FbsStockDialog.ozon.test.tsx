import type { ReactNode } from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import { describe, expect, it, vi } from 'vitest'
import { FbsStockDialog } from './FbsStockDialog'
import { fbsRuleBody, toProduct, toRule, type ApiRule } from './FfProductsFbsPage'
import {
  dialogShowsOzon,
  initialDraft,
  servedWarehouses,
  splitAmounts,
  visibleWarehouses,
  type Seller,
} from './stub'
import { warehouseRuleKey } from './fbsWarehouseRuleKeys'

vi.mock('../../../ui-kit', async (original) => ({
  ...await original<object>(),
  // Only remove the portal for SSR; all fields and dialog content are real.
  AppDialog: ({ children, actions }: { children: ReactNode; actions: ReactNode }) =>
    <div>{children}{actions}</div>,
}))

const wbBinding = { wb_warehouse_id: 501001, marketplace: 'wb' as const }
const ozonBinding = { wb_warehouse_id: 1020005029603630, marketplace: 'ozon' as const }
const wbRow = {
  id: warehouseRuleKey(wbBinding), name: 'E2E Seller Warehouse', marketplace: 'wb' as const,
  boundTo: 'yartsevo', fbsEnabled: true,
}
const ozonRow = {
  id: warehouseRuleKey(ozonBinding), name: 'Склад Ozon 1020005029603630',
  marketplace: 'ozon' as const, boundTo: 'yartsevo', fbsEnabled: true,
}
const sellerWithOzon: Seller = {
  id: 'seller', name: 'ИП Тестовый Аудит', warehouses: [wbRow, ozonRow],
  wbWarehouses: [{ id: 'yartsevo', name: 'Ярцево' }],
}
const sellerWbOnly: Seller = { ...sellerWithOzon, warehouses: [wbRow] }
// Унаследованный флаг Ozon: сервер отдаёт publish_ozon=true у товара без
// карточки Ozon, когда его никто не пересохранял.
const apiRule: ApiRule = {
  publish: true, publish_ozon: true, same_everywhere: true, percent: 50,
  by_warehouse: {}, units_mode: false, units_by_warehouse: {},
  units_remaining_by_warehouse: {}, on_hand: 120, reserved: 0, free_stock: 120,
  published_now: 60,
}
const OZON_TEST_IDS = [
  'data-testid="fbs-stock-publish-ozon"',
  'data-testid="fbs-stock-marketplace-ozon"',
  'data-testid="fbs-stock-served-ozon:',
  'data-testid="fbs-stock-ozon-unlinked"',
  'data-testid="fbs-stock-shared-pool"',
  'data-testid="fbs-stock-same"',
]

function render(marketplaces: string[] | undefined, seller: Seller, extra?: Partial<ApiRule>) {
  const row = { id: 'product', seller_id: seller.id, name: 'Футболка', sku_code: 'TS-WHT-M',
    wb_primary_barcode: null, marketplaces }
  const rule = { ...apiRule, ...extra }
  return renderToStaticMarkup(<FbsStockDialog open products={[toProduct(row, rule, seller.id)]}
    seller={seller} rule={toRule(row.id, rule)} onClose={() => {}}
    onSave={() => {}} onBind={() => {}} onServedChange={() => {}} />)
}

describe('WMS-454 no Ozon in the window of a product without an Ozon card', () => {
  it('(а) hides every Ozon element for a WB-only product at a seller with an Ozon warehouse', () => {
    const markup = render(['wb'], sellerWithOzon)
    for (const testId of OZON_TEST_IDS) expect(markup).not.toContain(testId)
    expect(markup).not.toContain('Выбранный товар с карточкой Ozon не связан')
    expect(markup).not.toContain('Общий лимит долей для обеих площадок')
    expect(markup).not.toContain('Ozon')
    // Единственный видимый склад — ни галки «одинаково», ни ползунка по складу.
    expect(markup).not.toContain('data-testid="fbs-stock-percent-wb:501001"')
    expect(markup).toContain('data-testid="fbs-stock-served-wb:501001"')
  })

  it('(а) renders the WB-only product identically at a seller without Ozon warehouses', () => {
    expect(render(['wb'], sellerWithOzon)).toBe(render(['wb'], sellerWbOnly))
  })

  it('(б) keeps the Ozon checkbox, header, shared pool and Ozon row for a product with an Ozon card', () => {
    const markup = render(['wb', 'ozon'], sellerWithOzon)
    for (const testId of OZON_TEST_IDS.filter((one) => !one.includes('ozon-unlinked'))) {
      expect(markup).toContain(testId)
    }
    expect(markup).toContain('data-testid="fbs-stock-marketplace-wb"')
    expect(markup).toContain('Общий лимит долей для обеих площадок')
    expect(markup).toContain('data-testid="fbs-stock-percent-ozon:1020005029603630"')
  })

  it('(в) treats an empty marketplaces list like a WB-only product', () => {
    expect(render(undefined, sellerWithOzon)).toBe(render(['wb'], sellerWithOzon))
    expect(render([], sellerWithOzon)).toBe(render(['wb'], sellerWithOzon))
  })

  it('(г) labels the served checkbox with the seller and the effect, and the chip with orders only', () => {
    const served = render(['wb', 'ozon'], sellerWithOzon)
    expect(served).toContain('Принимаем заказы продавца со склада «E2E Seller Warehouse»')
    expect(served).toContain('Принимаем заказы продавца со склада «Склад Ozon 1020005029603630»')
    expect(served).not.toContain('Обслуживаем склад')
    expect(served).not.toContain('заказы не принимаем')
    const unserved = renderToStaticMarkup(<FbsStockDialog open
      products={[toProduct({ id: 'product', seller_id: 'seller', name: 'Футболка',
        sku_code: 'TS-WHT-M', wb_primary_barcode: null, marketplaces: ['wb'] }, apiRule, 'seller')]}
      seller={{ ...sellerWbOnly, warehouses: [{ ...wbRow, fbsEnabled: false }] }}
      rule={toRule('product', apiRule)} onClose={() => {}} onSave={() => {}} onBind={() => {}}
      onServedChange={() => {}} />)
    expect(unserved).toContain('заказы не принимаем')
    expect(unserved).not.toContain('не обслуживаем')
    expect(unserved).not.toContain('остаток на него не отправляется')
  })

  it('(д) sends publish_ozon=false for a WB-only product and keeps the touched-only rule for Ozon', () => {
    const rule = toRule('product', apiRule)
    expect(rule.publishOzon).toBe(true)
    const wbOnly = initialDraft(rule, visibleWarehouses(sellerWithOzon, false), false)
    expect(wbOnly.publishOzon).toBe(false)
    expect(fbsRuleBody(wbOnly)).toMatchObject({ publish: undefined, publish_ozon: false, percent: 50 })
    expect(JSON.parse(JSON.stringify(fbsRuleBody(wbOnly)))).not.toHaveProperty('publish')
    expect(JSON.parse(JSON.stringify(fbsRuleBody(wbOnly)))).toHaveProperty('publish_ozon', false)
    const withOzon = initialDraft(rule, visibleWarehouses(sellerWithOzon, true), true)
    expect(withOzon.publishOzon).toBe(true)
    expect(fbsRuleBody(withOzon)).toMatchObject({ publish: undefined, publish_ozon: undefined })
    const touched = { ...withOzon, publishOzon: false, changedPublication: ['ozon' as const] }
    expect(fbsRuleBody(touched)).toMatchObject({ publish: undefined, publish_ozon: false })
    // Правило без списка тронутых (старые вызовы) шлёт оба флага, как раньше.
    expect(fbsRuleBody({ ...rule, changedPublication: undefined }))
      .toMatchObject({ publish: true, publish_ozon: true })
  })

  // F1 ревью Astra: у WB-товара со старым раздельным правилом (WB 60 / Ozon 40)
  // после скрытия Ozon обслуживаемый склад остаётся один, и черновик обязан
  // унести на сервер действующую WB-долю, а не старый общий процент. Путь
  // штатный: правило из API → initialDraft → fbsRuleBody → splitAmounts (та же
  // раскладка, что split_amounts на сервере).
  describe('keeps the effective WB share when the split rule collapses to one visible warehouse', () => {
    const splitRule = (extra: Partial<ApiRule>): ApiRule => ({
      ...apiRule, same_everywhere: false,
      by_warehouse: { 'wb:501001': 60, 'ozon:1020005029603630': 40 }, ...extra,
    })
    const wbAmount = (apiRuleIn: ApiRule) => {
      const draft = initialDraft(toRule('product', apiRuleIn), visibleWarehouses(sellerWithOzon, false), false)
      const body = fbsRuleBody(draft)
      // Что уйдёт в Wildberries по отправленному правилу при 120 свободных.
      const saved = toRule('product', { ...apiRuleIn, ...body, publish: body.publish ?? apiRuleIn.publish,
        publish_ozon: body.publish_ozon ?? apiRuleIn.publish_ozon })
      const amounts = splitAmounts(saved, 120, servedWarehouses(sellerWithOzon))
      return { draft, body, wb: amounts['wb:501001'], ozon: amounts['ozon:1020005029603630'] }
    }

    it.each([
      { name: 'stale percent 0', percent: 0 },
      { name: 'stale percent 50', percent: 50 },
    ])('$name, WB share 60: the slider and the PUT carry 60', ({ percent }) => {
      const before = splitAmounts(toRule('product', splitRule({ percent })), 120, servedWarehouses(sellerWithOzon))
      expect(before['wb:501001']).toBe(72)
      const { draft, body, wb, ozon } = wbAmount(splitRule({ percent }))
      expect(draft).toMatchObject({ sameEverywhere: true, percent: 60, publishOzon: false })
      expect(body).toMatchObject({ same_everywhere: true, percent: 60, publish_ozon: false })
      expect(wb).toBe(72)
      expect(ozon).toBe(0)
      const markup = render(['wb'], sellerWithOzon, { same_everywhere: false, percent,
        by_warehouse: { 'wb:501001': 60, 'ozon:1020005029603630': 40 } })
      expect(markup).toContain('>60%<')
    })

    it('leaves a rule that already was "same everywhere" untouched', () => {
      const { draft, body, wb } = wbAmount({ ...apiRule, percent: 70 })
      expect(draft).toMatchObject({ sameEverywhere: true, percent: 70 })
      expect(body).toMatchObject({ same_everywhere: true, percent: 70 })
      expect(wb).toBe(84)
    })

    it('does not change the units of a rule in units mode', () => {
      const units = splitRule({ units_mode: true, percent: 0,
        units_by_warehouse: { 'wb:501001': 7, 'ozon:1020005029603630': 3 } })
      const before = splitAmounts(toRule('product', units), 120, servedWarehouses(sellerWithOzon))
      const { body, wb } = wbAmount(units)
      expect(body).toMatchObject({ units_mode: true, units_by_warehouse: { 'wb:501001': 7, 'ozon:1020005029603630': 3 } })
      expect(wb).toBe(before['wb:501001'])
      expect(wb).toBe(7)
    })

    it('carries the share of the only visible warehouse even while nobody serves it', () => {
      const idle = { ...sellerWbOnly, warehouses: [{ ...wbRow, fbsEnabled: false }] }
      const draft = initialDraft(toRule('product', splitRule({ percent: 0 })), visibleWarehouses(idle, false), false)
      expect(draft).toMatchObject({ sameEverywhere: true, percent: 60 })
    })

    it('keeps separate shares when two warehouses stay visible', () => {
      const draft = initialDraft(toRule('product', splitRule({ percent: 0 })), visibleWarehouses(sellerWithOzon, true), true)
      expect(draft).toMatchObject({ sameEverywhere: false, percent: 0 })
      expect(fbsRuleBody(draft)).toMatchObject({ same_everywhere: false, percent: 0,
        by_warehouse: { 'wb:501001': 60, 'ozon:1020005029603630': 40 } })
    })
  })

  it('decides Ozon by the product card, not by the seller warehouses', () => {
    expect(dialogShowsOzon([{ marketplaces: ['wb'] }])).toBe(false)
    expect(dialogShowsOzon([{ marketplaces: [] }, {}])).toBe(false)
    expect(dialogShowsOzon([{ marketplaces: ['wb'] }, { marketplaces: ['wb', 'ozon'] }])).toBe(true)
    expect(visibleWarehouses(sellerWithOzon, false)).toEqual([wbRow])
    expect(visibleWarehouses(sellerWithOzon, true)).toEqual([wbRow, ozonRow])
  })

  it('C13 keeps long warehouse and seller names inside the row markup', () => {
    const longName = 'Склад продавца с очень длинным названием, которое не помещается в одну строку окна'
    const markup = render(['wb'], {
      ...sellerWbOnly, name: 'ИП Тестовый Аудит с очень длинным наименованием продавца',
      warehouses: [{ ...wbRow, name: longName, fbsEnabled: false }],
    })
    expect(markup).toContain(`Принимаем заказы продавца со склада «${longName}»`)
    expect(markup).toContain('заказы не принимаем')
  })
})
