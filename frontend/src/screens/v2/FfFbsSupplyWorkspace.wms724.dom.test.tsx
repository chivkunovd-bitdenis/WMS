// @vitest-environment jsdom
import { act } from 'react'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { CardFixture, authHeaders, button, click, input, json, settle, workspace } from './fbsSupplyCard.contract-fixture'
import { FfDashboard } from '../ff/FfDashboard'
import { FfFbsOrdersScreen } from './FfFbsOrdersScreen'
vi.mock('../ff/FfPackagingPage', () => ({}))
vi.mock('../ff/unload-pick/FfUnloadPickPage', () => ({ FfUnloadPickPage: () => null }))
let f: CardFixture
beforeEach(() => { f = new CardFixture(); vi.spyOn(window, 'confirm').mockReturnValue(false) })
afterEach(() => { f.dispose(); vi.restoreAllMocks() })

it.each(['wb', 'ozon'].flatMap(m => [null, '2026-10-09'].map(date => [m, date])))('C1 %s date=%s has no editor or ghost dirty state but guards real box drafts', async (marketplace, date) => {
  f.current = workspace(marketplace as 'wb' | 'ozon')
  f.current.supply.planned_shipment_date = date
  await f.render('boxes')
  expect(document.querySelector('input[type="date"]')).toBeNull()
  expect(document.body.textContent).not.toContain('Дата отгрузки')
  expect(document.querySelector('[data-testid="cal-02-fbs-shipment-date-save"]')).toBeNull()
  expect(document.querySelector('[data-testid="cal-02-fbs-shipment-date-clear"]')).toBeNull()
  await click(document.querySelector('[aria-label="Закрыть"]'))
  expect(f.close).toHaveBeenCalledTimes(1); expect(window.confirm).not.toHaveBeenCalled()
  await input(document.querySelector<HTMLInputElement>('input[type="number"]')!, '2')
  await click(document.querySelector('[aria-label="Закрыть"]'))
  expect(window.confirm).toHaveBeenCalled(); expect(f.close).toHaveBeenCalledTimes(1)
  expect(f.calls.some(c => c.path.endsWith('/planned-shipment-date'))).toBe(false)
})

it.each(['В работе', 'В доставке', 'Завершённые'].flatMap(group => [true, false].map(empty => [group, empty])))('C2 %s empty=%s keeps aligned supply rows without planned date', async (group, empty) => {
  const supply = { id: 'supply-a', marketplace: 'wb', wb_supply_id: 'WB-TEST', name: 'Поставка A', status: 'assembling',
    seller: { id: 'seller', name: 'Селлер' }, wb_warehouse: { id: 507, name: 'Коледино' }, wms_warehouse: { id: 'wh', name: 'Склад' },
    orders_count: 1, units_count: 1, picked_units_count: 0, boxes_count: 1, planned_shipment_date: '2037-12-23', can_add_orders: true }
  f.hook = async c => {
    if (c.path.endsWith('/fbs-supplies/worklist')) return json({ items: empty ? [] : [supply], total: empty ? 0 : 1 })
    if (c.path.endsWith('/fbs-assembly-tasks')) return json({ items: empty ? [] : [{ id: 'assembly', number: '123', created_at: '2026-10-09T08:00:00Z', created_by: null, supplies: [{ ...supply, picked_count: 0, packed_count: 0 }] }], total: empty ? 0 : 1 })
    if (c.path.endsWith('/seller-warehouses')) return json([])
    return undefined
  }
  await act(async () => f.root.render(<MemoryRouter><FfFbsOrdersScreen token="contract-test" authHeaders={authHeaders} sellers={[{ id: 'seller', name: 'Селлер' }]} /></MemoryRouter>))
  await settle(); await click(button(group as string))
  const table = document.querySelector('[data-testid="fbs-18-supplies-table"]')!
  expect(table).toBeTruthy(); expect(table.textContent).not.toContain('Дата отгрузки')
  const count = table.querySelectorAll('thead th').length
  expect(count).toBe(7)
  for (const row of table.querySelectorAll('tbody tr')) expect([...row.querySelectorAll<HTMLTableCellElement>('td')].reduce((sum, c) => sum + c.colSpan, 0)).toBe(count)
  expect(table.textContent).not.toContain('23.12.37')
})

const opens = { outbound: vi.fn(), mp: vi.fn(), fbs: vi.fn() }
async function dashboard(withNeighbors: boolean) {
  const now = new Date(); const date = `${now.getFullYear()}-${String(now.getMonth()+1).padStart(2, '0')}-09`
  f.hook = async c => c.path.endsWith('/calendar') ? json([{ id: 'fbs-old', date, direction: 'Старое FBS', boxes_count: 1, shipment_type: 'FBS', title: 'FBS' }]) : undefined
  await act(async () => f.root.render(<FfDashboard token="contract-test" authHeaders={authHeaders}
    me={{ email: null, display_name: 'Оператор', organization_name: 'Склад', role: 'admin' }} isFulfillmentAdmin
    inboundSummaries={[]} outboundSummaries={withNeighbors ? [{ id: 'fbo', status: 'submitted', line_count: 2, planned_shipment_date: date, warehouse_name: 'Направление FBO' }] : []}
    mpUnloadSummaries={withNeighbors ? [{ id: 'mp', status: 'submitted', line_count: 3, planned_shipment_date: date, warehouse_name: 'Направление МП', marketplace_label: 'WB' }] : []}
    onOpenInbound={() => undefined} onOpenOutbound={opens.outbound} onOpenMarketplaceUnload={opens.mp} onOpenFbsSupply={opens.fbs} />))
  await settle()
}

it('C3 removes FBS calendar requests across months while retaining FBO and MP links', async () => {
  await dashboard(true)
  expect(f.calls.some(c => c.path === '/operations/fbs-supplies/calendar')).toBe(false)
  const rows = [...document.querySelectorAll<HTMLElement>('[data-testid="cal-01-shipment-row"]')]
  expect(rows).toHaveLength(2); expect(document.body.textContent).not.toContain('Старое FBS')
  await click(rows.find(r => r.textContent?.includes('Направление FBO')))
  await click(rows.find(r => r.textContent?.includes('Направление МП')))
  expect(opens.outbound).toHaveBeenCalledWith('fbo'); expect(opens.mp).toHaveBeenCalledWith('mp'); expect(opens.fbs).not.toHaveBeenCalled()
  await click(document.querySelector('[data-testid="cal-01-next-month"]'))
  expect(f.calls.some(c => c.path === '/operations/fbs-supplies/calendar')).toBe(false)
  expect(document.querySelector('[data-testid="cal-01-fbs-load-error"]')).toBeNull()
  expect(document.querySelector('[data-testid="cal-01-loading"]')).toBeNull()
})

it('C4 FBS-only and empty month keep the ordinary calendar grid without an FBS loader', async () => {
  await dashboard(false)
  expect(document.querySelector('[data-testid="cal-01-grid"]')).toBeTruthy()
  expect(document.querySelectorAll('[data-testid="cal-01-shipment-row"]')).toHaveLength(0)
  expect(document.querySelector('[data-testid="cal-01-loading"]')).toBeNull()
  await click(document.querySelector('[data-testid="cal-01-next-month"]'))
  expect(document.querySelectorAll('[data-testid="cal-01-day-number"]').length).toBeGreaterThanOrEqual(28)
  expect(f.calls.some(c => c.path.endsWith('/calendar'))).toBe(false)
})

it('C5 opening adding and switching stages never clears stored date deadlines or order facts', async () => {
  f.current.supply.planned_shipment_date = '2026-10-09'
  const deadline = f.current.supply.nearest_deadline_at; const before = structuredClone(f.current.orders)
  await f.render('packing')
  await click(button('Добавить заказы'))
  await click(document.querySelector('[data-testid="fbs-05-workspace-add-orders-table"] input'))
  await click(document.querySelector('[data-testid="fbs-05-workspace-add-orders-submit"]'))
  await f.render('boxes')
  expect(f.current.supply.planned_shipment_date).toBe('2026-10-09'); expect(f.current.supply.nearest_deadline_at).toBe(deadline)
  expect(f.current.orders.filter(o => o.id !== 'new')).toEqual(before)
  expect(f.calls.some(c => c.path.endsWith('/planned-shipment-date'))).toBe(false)
  expect(document.body.textContent).toContain('Сдать в Wildberries до')
  expect([...document.querySelectorAll<HTMLButtonElement>('[role="tab"]')].every(t => !t.disabled)).toBe(true)
})
