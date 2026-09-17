import type { ReactNode } from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import { describe, expect, it, vi } from 'vitest'
import { FbsStockDialog } from './FbsStockDialog'
import { fbsRuleBody, toProduct, toRule, type ApiRule } from './FfProductsFbsPage'
import { warehouseRuleKey } from './fbsWarehouseRuleKeys'
import {
  dialogShowsSharedPool,
  initialDraft,
  publishedQty,
  servedWarehouses,
  splitAmounts,
  visibleWarehouses,
  type Seller,
} from './stub'

// WMS-455, проверка C20: галка «Весь свободный остаток в Wildberries и Ozon»
// в окне «Остаток для FBS». Рендер настоящего окна через renderToStaticMarkup,
// как в FbsStockDialog.ozon.test.tsx: подменяется только портал AppDialog.

vi.mock('../../../ui-kit', async (original) => ({
  ...await original<object>(),
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
const seller: Seller = {
  id: 'seller', name: 'ИП Тестовый Аудит', warehouses: [wbRow, ozonRow],
  wbWarehouses: [{ id: 'yartsevo', name: 'Ярцево' }],
}
// Правило HD-GRY-L со стенда: раздельные доли WB 60 / Ozon 40, 100 свободных.
const apiRule: ApiRule = {
  publish: true, publish_ozon: true, same_everywhere: false, percent: 0,
  by_warehouse: { 'wb:501001': 60, 'ozon:1020005029603630': 40 }, units_mode: false,
  units_by_warehouse: {}, units_remaining_by_warehouse: {}, on_hand: 100, reserved: 0,
  free_stock: 100, published_now: 100,
}

const MODE = 'data-testid="fbs-stock-shared-pool-mode"'
const MODE_ON = 'Доли отключены: в каждый кабинет уходит весь свободный остаток, продажа на любой площадке уменьшает его на обеих'
const MODE_OFF = 'Включите, чтобы отдавать весь свободный остаток в оба кабинета без долей'
const LOCK = 'Включён весь свободный остаток в оба кабинета'
const SHARES_LIMIT = 'Общий лимит долей для обеих площадок'
const SHARED_LINE = 'На каждый склад ниже уходит весь свободный остаток товара'
const WB_SLIDER = 'data-testid="fbs-stock-percent-wb:501001"'
const OZON_SLIDER = 'data-testid="fbs-stock-percent-ozon:1020005029603630"'

function row(id: string, marketplaces: string[]) {
  return { id, seller_id: seller.id, name: 'Худи оверсайз серое', sku_code: 'HD-GRY-L',
    wb_primary_barcode: null, marketplaces }
}

function render(
  marketplaces: string[][],
  extra: Partial<ApiRule> = {},
  sellerIn: Seller = seller,
) {
  const rule = { ...apiRule, ...extra }
  const products = marketplaces.map((one, index) =>
    toProduct(row(`product-${index}`, one), rule, sellerIn.id))
  return renderToStaticMarkup(<FbsStockDialog open products={products} seller={sellerIn}
    rule={toRule('product-0', rule)} onClose={() => {}} onSave={() => {}} onBind={() => {}}
    onServedChange={() => {}} />)
}

// Подпись под галкой — FormHelperText сразу после её FormControlLabel.
function helperAfter(markup: string, label: string): string {
  const start = markup.indexOf(label)
  expect(start).toBeGreaterThan(-1)
  const tail = markup.slice(start)
  const helper = /class="[^"]*MuiFormHelperText-root[^"]*"[^>]*>([^<]*)<\/p>/.exec(tail)
  return helper?.[1] ?? ''
}

function checkboxDisabled(markup: string, label: string): boolean {
  const start = markup.indexOf(label)
  expect(start).toBeGreaterThan(-1)
  // FormControlLabel рендерит <label ...><span ...><input .../></span>...label</label>:
  // берём ближайший input перед подписью.
  const head = markup.slice(0, start)
  const input = head.lastIndexOf('<input')
  const inputTag = head.slice(input, head.indexOf('>', input) + 1)
  return inputTag.includes('disabled=""')
}

describe('WMS-455 C20 режим «весь свободный остаток» в окне остатка', () => {
  it('(а) товар на двух площадках без режима: галка выключена, доли и лимит на месте', () => {
    const markup = render([['wb', 'ozon']])
    expect(markup).toContain(MODE)
    expect(markup).toContain('Весь свободный остаток в Wildberries и Ozon')
    expect(helperAfter(markup, 'Весь свободный остаток в Wildberries и Ozon')).toBe(MODE_OFF)
    expect(checkboxDisabled(markup, 'Остаток по штукам')).toBe(false)
    expect(markup).toContain(WB_SLIDER)
    expect(markup).toContain(OZON_SLIDER)
    expect(markup).toContain(SHARES_LIMIT)
    expect(markup).toContain('data-testid="fbs-stock-rest"')
    expect(markup).not.toContain(MODE_ON)
    expect(markup).not.toContain(LOCK)
    expect(markup).not.toContain(SHARED_LINE)
    // Галка стоит после галок площадок и до «Остаток по штукам».
    expect(markup.indexOf('data-testid="fbs-stock-publish-ozon"')).toBeLessThan(markup.indexOf(MODE))
    expect(markup.indexOf(MODE)).toBeLessThan(markup.indexOf('data-testid="fbs-stock-units-mode"'))
  })

  it('(б) режим включён: доли и штуки спрятаны, соседние настройки заперты, плашки про 200% нет', () => {
    // Прежние значения самые «опасные»: одинаково 100% на два склада (200%) и
    // режим штук — ни одно из них в режиме не показывается и не запирает кнопку.
    for (const extra of [
      {},
      { same_everywhere: true, percent: 100 },
      { units_mode: true, units_by_warehouse: { 'wb:501001': 100, 'ozon:1020005029603630': 100 } },
    ] as Partial<ApiRule>[]) {
      const markup = render([['wb', 'ozon']], { ...extra, shared_pool: true })
      expect(helperAfter(markup, 'Весь свободный остаток в Wildberries и Ozon')).toBe(MODE_ON)
      expect(checkboxDisabled(markup, 'Весь свободный остаток в Wildberries и Ozon')).toBe(false)
      expect(checkboxDisabled(markup, 'Остаток по штукам')).toBe(true)
      expect(helperAfter(markup, 'Остаток по штукам')).toBe(LOCK)
      expect(checkboxDisabled(markup, 'Одинаково по всем складам')).toBe(true)
      expect(helperAfter(markup, 'Одинаково по всем складам')).toBe(LOCK)
      // Ползунок «Доля свободного остатка» заперт с той же причиной под ним.
      const slider = markup.slice(markup.indexOf('Доля свободного остатка'))
      expect(slider.slice(0, slider.indexOf('Одинаково по всем складам'))).toContain(LOCK)
      expect(markup).not.toContain(WB_SLIDER)
      expect(markup).not.toContain(OZON_SLIDER)
      expect(markup).not.toContain('data-testid="fbs-stock-units-wb:501001"')
      expect(markup).not.toContain('data-testid="fbs-stock-units-ozon:1020005029603630"')
      expect(markup).not.toContain('data-testid="fbs-stock-units-total"')
      expect(markup).not.toContain('data-testid="fbs-stock-rest"')
      expect(markup).not.toContain('data-testid="fbs-stock-over"')
      expect(markup).not.toContain('Больше 100% раздать нельзя')
      expect(markup).toContain(SHARED_LINE)
      expect(markup).not.toContain(SHARES_LIMIT)
      // Остальное окно на месте: галки площадок, заголовки, строки складов, «N шт».
      expect(markup).toContain('data-testid="fbs-stock-publish"')
      expect(markup).toContain('data-testid="fbs-stock-publish-ozon"')
      expect(markup).toContain('data-testid="fbs-stock-marketplace-wb"')
      expect(markup).toContain('data-testid="fbs-stock-marketplace-ozon"')
      expect(markup).toContain('Принимаем заказы продавца со склада «E2E Seller Warehouse»')
      expect(markup).toContain('Принимаем заказы продавца со склада «Склад Ozon 1020005029603630»')
      expect(markup).toContain('data-testid="fbs-stock-bind-wb:501001"')
      expect(markup).toContain('data-testid="fbs-stock-result">100 шт')
      // Кнопка «Сохранить» не заперта.
      const save = markup.slice(markup.indexOf('data-testid="fbs-stock-save"') - 400)
      expect(save.slice(0, save.indexOf('Сохранить'))).not.toContain('disabled=""')
    }
  })

  it('(в) товар только WB: галки нет, и сохранённый режим ничего в окне не меняет', () => {
    const markup = render([['wb']])
    expect(markup).not.toContain(MODE)
    expect(markup).not.toContain('Весь свободный остаток')
    expect(markup).not.toContain(SHARED_LINE)
    expect(markup).not.toContain(LOCK)
    // Сервер у товара без связки Ozon режим не отдаёт, но и приди он — окно то же.
    expect(render([['wb']], { shared_pool: true })).toBe(markup)
    // Только Ozon (без значка WB) — тоже без галки.
    expect(render([['ozon']])).not.toContain(MODE)
    expect(dialogShowsSharedPool([{ marketplaces: ['wb'] }, { marketplaces: ['ozon'] }])).toBe(false)
    expect(dialogShowsSharedPool([{ marketplaces: [] }, {}])).toBe(false)
  })

  it('(г) пачка с одним товаром на двух площадках показывает галку', () => {
    const markup = render([['wb'], ['wb', 'ozon']])
    expect(markup).toContain(MODE)
    expect(markup).toContain('2 товаров, ИП Тестовый Аудит')
    expect(dialogShowsSharedPool([{ marketplaces: ['wb'] }, { marketplaces: ['wb', 'ozon'] }])).toBe(true)
  })

  it('(д) shared_pool читается из правила и уходит в теле запроса', () => {
    expect(toRule('product', apiRule).sharedPool).toBe(false)
    expect(toRule('product', { ...apiRule, shared_pool: true }).sharedPool).toBe(true)
    expect(toRule('product', undefined).sharedPool).toBe(false)
    const on = toRule('product', { ...apiRule, shared_pool: true })
    const draft = initialDraft(on, visibleWarehouses(seller, true), true, true)
    expect(draft.sharedPool).toBe(true)
    expect(fbsRuleBody(draft)).toMatchObject({
      shared_pool: true, publish: undefined, publish_ozon: undefined,
      by_warehouse: { 'wb:501001': 60, 'ozon:1020005029603630': 40 },
    })
    expect(fbsRuleBody({ ...draft, sharedPool: false })).toMatchObject({ shared_pool: false })
    expect(JSON.parse(JSON.stringify(fbsRuleBody(draft)))).toHaveProperty('shared_pool', true)
    // Галки режима в окне нет — черновик её не несёт: что оператор видит (доли),
    // то и сохраняется, как у флага Ozon у WB-товара.
    expect(initialDraft(on, visibleWarehouses(seller, false), false).sharedPool).toBe(false)
    expect(initialDraft(on, visibleWarehouses(seller, true), true, false).sharedPool).toBe(false)
  })

  it('раскладка в режиме повторяет сервер: каждому публикующему направлению весь остаток', () => {
    const on = toRule('product', { ...apiRule, shared_pool: true })
    expect(splitAmounts(on, 100, servedWarehouses(seller)))
      .toEqual({ 'wb:501001': 100, 'ozon:1020005029603630': 100 })
    expect(splitAmounts({ ...on, publishOzon: false, changedPublication: ['ozon'] }, 100,
      servedWarehouses(seller))).toEqual({ 'wb:501001': 100, 'ozon:1020005029603630': 0 })
    expect(splitAmounts(on, 0, servedWarehouses(seller)))
      .toEqual({ 'wb:501001': 0, 'ozon:1020005029603630': 0 })
    const product = toProduct(row('product', ['wb', 'ozon']), { ...apiRule, shared_pool: true }, seller.id)
    // Как published_now: число, уходящее в каждое направление, а не их сумма.
    expect(publishedQty(product, on, seller)).toBe(100)
    // Без режима — прежняя раскладка 60/40.
    expect(splitAmounts(toRule('product', apiRule), 100, servedWarehouses(seller)))
      .toEqual({ 'wb:501001': 60, 'ozon:1020005029603630': 40 })
  })

  it('C22 длинное название склада в режиме остаётся в строке склада', () => {
    const longName = 'Склад продавца с очень длинным названием, которое точно не помещается в одну строку окна остатка'
    expect(longName.length).toBeGreaterThan(80)
    const markup = render([['wb', 'ozon']], { shared_pool: true },
      { ...seller, warehouses: [{ ...wbRow, name: longName }, ozonRow] })
    expect(markup).toContain(`Принимаем заказы продавца со склада «${longName}»`)
    expect(helperAfter(markup, 'Весь свободный остаток в Wildberries и Ozon')).toBe(MODE_ON)
    expect(markup).toContain(SHARED_LINE)
    expect(markup).not.toContain(WB_SLIDER)
  })
})
