// @vitest-environment jsdom
import { act, useState, type ReactElement } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { afterEach, beforeAll, describe, expect, it, vi } from 'vitest'
import { ProductCardFbsStockTab } from './ProductCardFbsStockTab'
import { FbsStockDialogContainer } from '../../ff/products-fbs/FbsStockDialogContainer'

// Actual card tab and the exact container mounted by FfProductsCatalogScreen.
// Only HTTP is replaced: the loader, session, form and save handlers remain real.
const warehouses = [
  { id: 'w1', name: 'Склад 1', code: 'ONE', is_operational: true },
  { id: 'w2', name: 'Склад 2', code: 'TWO', is_operational: true },
]
const json = (body: unknown, status = 200) => new Response(JSON.stringify(body), {
  status, headers: { 'Content-Type': 'application/json' },
})
function server() {
  const rules = {
    wb: { publish: true, mode: 'units', value: 10, units_configured: true },
    ozon: { publish: true, mode: 'units', value: 20, units_configured: true },
  }
  const bindings = [
    { id: 'wb', marketplace: 'wb', external_warehouse_id: null, wb_warehouse_id: 101,
      wms_warehouse_id: 'w1', wms_warehouse_name: 'Склад 1', is_active: true, served: true, stock_sync_enabled: true, editable: true },
    { id: 'ozon', marketplace: 'ozon', external_warehouse_id: '202', wb_warehouse_id: null,
      wms_warehouse_id: 'w1', wms_warehouse_name: 'Склад 1', is_active: true, served: true, stock_sync_enabled: true, editable: true },
  ]
  const state = { free: 100, rejectSave: false, reads: 0, writes: [] as Array<{ url: string; body: unknown }> }
  vi.stubGlobal('fetch', vi.fn(async (url: string, init?: RequestInit) => {
    if (url.endsWith('/products/fbs-rule/bulk')) {
      state.reads++
      return json({ items: [{ product_id: 'p', by_binding: Object.fromEntries(bindings.map(b => [b.id, {
        ...rules[b.id as keyof typeof rules], marketplace: b.marketplace,
        external_warehouse_id: String(b.wb_warehouse_id ?? b.external_warehouse_id),
        wms_warehouse_id: b.wms_warehouse_id, served: b.served, applicable: true,
        on_hand: state.free, reserved: 0, free_stock: state.free, published_now: 0,
      }])) }] })
    }
    if (url.endsWith('/warehouse-bindings')) return json(bindings)
    if (url.endsWith('/ozon-warehouses')) return json([{ warehouse_id: 202, name: 'Ozon склад', served: true, wms_warehouse_id: bindings[1].wms_warehouse_id }])
    if (url.endsWith('/warehouses')) return json([{ wb_warehouse_id: 101, name: 'WB склад', served: true, wms_warehouse_id: bindings[0].wms_warehouse_id }])
    const body = JSON.parse(String(init?.body))
    state.writes.push({ url, body })
    if (url.endsWith('/products/fbs-rule')) {
      if (state.rejectSave) return json({ detail: 'Сохранение отклонено' }, 409)
      for (const [id, value] of Object.entries(body.rule.by_binding)) Object.assign(rules[id as keyof typeof rules], value)
      return json({ items: [], clamps: {} })
    }
    if (url.includes('/fbs-sellers/s/warehouses/')) {
      const binding = bindings.find(b => b.marketplace === body.marketplace)!
      Object.assign(binding, body)
      binding.wms_warehouse_name = warehouses.find(w => w.id === binding.wms_warehouse_id)!.name
      return json(binding)
    }
    throw new Error(`Unexpected request: ${url}`)
  }))
  return { state, rules, bindings }
}

let root: Root | null = null
let host: HTMLDivElement | null = null
beforeAll(() => { (globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true })
afterEach(async () => {
  if (root) await act(async () => root!.unmount())
  root = null
  host?.remove()
  host = null
  document.body.innerHTML = ''
  vi.unstubAllGlobals()
})
async function render(element: ReactElement, reopen = false) {
  if (reopen && root) {
    await act(async () => root!.unmount())
    host!.remove()
    root = null
  }
  if (!root) {
    host = document.createElement('div')
    document.body.append(host)
    root = createRoot(host)
  }
  await act(async () => root!.render(element))
}
function el<T extends HTMLElement = HTMLElement>(id: string) {
  const found = document.querySelector<T>(`[data-testid="${id}"]`)
  if (!found) throw new Error(`Missing ${id}`)
  return found
}
async function click(id: string) { await act(async () => el(id).click()) }
async function type(id: string, value: string) {
  await act(async () => {
    const input = el<HTMLInputElement>(id)
    Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value')!.set!.call(input, value)
    input.dispatchEvent(new Event('input', { bubbles: true }))
  })
}
async function select(id: string, value: string) {
  await act(async () => {
    const input = el<HTMLSelectElement>(id)
    input.value = value
    input.dispatchEvent(new Event('change', { bubbles: true }))
  })
}
const noop = () => {}
function card(stockVersion = 0, active = true, onChanged = noop) {
  return <ProductCardFbsStockTab productId="p" productName="Товар" productSku="P" productSize={null}
    sellerId="s" sellerName="Селлер" token="t" warehouses={warehouses} canEditBindings
    footerSlotEl={document.body} onCardClose={noop} onBusyChange={noop} onChanged={onChanged}
    stockVersion={stockVersion} active={active} onErrorChange={noop} />
}
function catalog() {
  return <FbsStockDialogContainer token="t" sellerId="s" sellerName="Селлер" chosen={[{ id: 'p', name: 'Товар', sku_code: 'P' }]}
    warehouses={warehouses} canEditBindings onClose={noop} onLoadError={noop} />
}

describe('WMS-596 same persisted stock rule from card and catalog', () => {
  it.each(['card-to-catalog', 'catalog-to-card'])('%s: units, percent, publish and warehouse binding survive reopening', async direction => {
    const { state, rules } = server()
    const first = direction === 'card-to-catalog' ? card : catalog
    const second = direction === 'card-to-catalog' ? catalog : card
    await render(first())
    await type('fbs-stock-units-wb', '17')
    await click('fbs-stock-by-percent-ozon')
    await select('fbs-stock-bind-wb', 'w2')
    expect(el<HTMLInputElement>('fbs-stock-units-wb').value).toBe('17')
    await click('fbs-stock-save')
    expect(rules.wb.value).toBe(17)
    expect(rules.ozon.mode).toBe('percent')
    await render(second(), true)
    expect(el<HTMLInputElement>('fbs-stock-units-wb').value).toBe('17')
    expect(el<HTMLSelectElement>('fbs-stock-bind-wb').value).toBe('w2')
    expect(el<HTMLInputElement>('fbs-stock-units-ozon').readOnly).toBe(true)
    expect(el('fbs-stock-pct-ozon').textContent).toBe(`${rules.ozon.value} %`)
    await select('fbs-stock-bind-ozon', 'w2')
    await click('fbs-stock-publish-wb')
    await click('fbs-stock-save')
    await render(first(), true)
    expect(el<HTMLInputElement>('fbs-stock-publish-wb').checked).toBe(false)
    expect(el<HTMLInputElement>('fbs-stock-publish-ozon').checked).toBe(true)
    expect(el<HTMLSelectElement>('fbs-stock-bind-ozon').value).toBe('w2')
    await click('fbs-stock-publish-wb')
    await click('fbs-stock-save')
    await render(second(), true)
    expect(el<HTMLInputElement>('fbs-stock-publish-wb').checked).toBe(true)
    expect(el<HTMLInputElement>('fbs-stock-units-wb').value).toBe('17')
    expect(state.writes.filter(w => w.url.endsWith('/products/fbs-rule'))).toHaveLength(3)
  }, 10000)

  it.each(['card', 'catalog'])('%s: rejected save keeps draft; other entry reads unchanged server value', async entry => {
    const { state, rules } = server()
    state.rejectSave = true
    await render(entry === 'card' ? card() : catalog())
    await type('fbs-stock-units-wb', '31')
    await click('fbs-stock-save')
    expect(document.body.textContent).toContain('Сохранение отклонено')
    expect(el<HTMLInputElement>('fbs-stock-units-wb').value).toBe('31')
    expect(rules.wb.value).toBe(10)
    await render(entry === 'card' ? catalog() : card(), true)
    expect(el<HTMLInputElement>('fbs-stock-units-wb').value).toBe('10')
  })

  it('recount on another tab refreshes available stock without discarding the typed limit', async () => {
    const { state } = server()
    await render(card())
    await type('fbs-stock-units-wb', '17')
    expect(el('fbs-stock-totals-wb').textContent).toContain('100')
    await render(card(0, false))
    state.free = 40
    await render(card(1, false))
    await render(card(1, true))
    expect(el('fbs-stock-totals-wb').textContent).toContain('доступно 40')
    expect(el<HTMLInputElement>('fbs-stock-units-wb').value).toBe('17')
    expect(state.reads).toBeGreaterThan(1)
  })

  it('its own immediate warehouse write bumps stockVersion without losing an unsaved rule', async () => {
    const { rules } = server()
    function CardOwner() {
      const [version, setVersion] = useState(0)
      return card(version, true, () => setVersion(v => v + 1))
    }
    await render(<CardOwner />)
    await type('fbs-stock-units-wb', '17')
    await select('fbs-stock-bind-wb', 'w2')
    expect(el<HTMLSelectElement>('fbs-stock-bind-wb').value).toBe('w2')
    expect(el<HTMLInputElement>('fbs-stock-units-wb').value).toBe('17')
    await click('fbs-stock-save')
    expect(rules.wb.value).toBe(17)
  })
})
