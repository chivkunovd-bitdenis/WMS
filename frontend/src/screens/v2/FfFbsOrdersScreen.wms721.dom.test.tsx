// @vitest-environment jsdom
// WMS-721 C1-C3, C8: existing status chip/rows and real orders screen.
// API fixtures are the browser boundary; no Playwright or live marketplace I/O.
// Baseline: 67 cases, 46 expected product failures and 21 preserved-behaviour passes.
// All 21 green cases fail when chip/row labels are corrupted and the shipped tab
// leaks into WB. All three product files were restored byte-for-byte afterwards.
import { act } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { MemoryRouter } from 'react-router-dom'
import { Table, TableBody } from '@mui/material'
import { afterEach, beforeAll, beforeEach, expect, it, vi } from 'vitest'
import { FbsStatusChip } from '../../components/fbs/FbsChips'
import { FbsAssemblyTaskRows } from './FbsAssemblyTaskRows'
import { FfFbsOrdersScreen } from './FfFbsOrdersScreen'
import { orderStatusForChip } from './fbsUx'
import type { FbsSupplyWorklistItem } from './fbsApi'

const { supplyList, orderList, assemblyList, sellerWarehouses } = vi.hoisted(() => ({
  supplyList: vi.fn(), orderList: vi.fn(), assemblyList: vi.fn(), sellerWarehouses: vi.fn(),
}))
vi.mock('./fbsApi', async (original) => ({
  ...await original<typeof import('./fbsApi')>(),
  fetchFbsSupplyWorklist: supplyList, fetchFbsWorklist: orderList,
  fetchFbsAssemblyTasks: assemblyList, fetchFbsSellerWarehouses: sellerWarehouses,
}))
// Closed neighbouring panels do not participate in the status/tab operation.
vi.mock('./FfFbsSupplyWorkspace', () => ({ FfFbsSupplyWorkspace: () => null }))
vi.mock('./FfFbsSupplyAssembly', () => ({ FfFbsSupplyAssembly: () => null }))
vi.mock('./FbsCancelledAfterPackDialog', () => ({ FbsCancelledAfterPackDialog: () => null }))
vi.mock('./FbsPrintPreviewDialog', () => ({ FbsPrintPreviewDialog: () => null }))

let root: Root
let host: HTMLDivElement
const authHeaders = () => ({ Authorization: 'Bearer wms721-fixture' })
const originalFetch = globalThis.fetch
beforeAll(() => {
  ;(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true
  Element.prototype.scrollIntoView = () => undefined
})
beforeEach(() => {
  window.localStorage.clear()
  window.sessionStorage.clear()
  host = document.createElement('div')
  document.body.appendChild(host)
  root = createRoot(host)
  orderList.mockReset().mockResolvedValue({ items: [], total: 0, warehouse_options: [], server_now: '2026-10-09T08:00:00Z' })
  supplyList.mockReset().mockResolvedValue({ items: [], total: 0, server_now: '2026-10-09T08:00:00Z' })
  assemblyList.mockReset().mockResolvedValue({ items: [] })
  sellerWarehouses.mockReset().mockResolvedValue([])
  globalThis.fetch = vi.fn(async () => new Response(JSON.stringify({ hours: 0, orders: 0, in12: 0, in24: 0 }), {
    headers: { 'Content-Type': 'application/json' },
  }))
})
afterEach(async () => {
  await act(async () => { root.unmount() })
  host.remove()
  document.body.innerHTML = ''
  globalThis.fetch = originalFetch
})

// Existing raw fields are intentionally supplied: local sorted alone is not a
// delivery fact. The contract concerns visible labels, not a new component API.
const labels: Array<[string | null, string | null, string, boolean, string]> = [
  ['awaiting_packaging', null, 'new', false, 'Новый'],
  ['awaiting_packaging', null, 'packed', false, 'Упакован'],
  ['awaiting_approve', null, 'external_processing', false, 'Ожидает подтверждения'],
  ['awaiting_verification', null, 'external_processing', false, 'Создано'],
  ['awaiting_registration', null, 'external_processing', false, 'Ожидает регистрации'],
  ['awaiting_deliver', null, 'packed', false, 'Готов к сдаче'],
  ['awaiting_deliver', null, 'in_delivery', true, 'Отгружен'],
  ['awaiting_deliver', 'posting_transferring_to_delivery', 'in_delivery', true, 'Передаётся в доставку'],
  ['acceptance_in_progress', null, 'sorted', true, 'Идёт приёмка'],
  ['driver_pickup', null, 'in_delivery', true, 'У водителя'],
  ['delivering', null, 'in_delivery', true, 'В доставке'],
  ['delivering', null, 'sorted', true, 'В доставке'],
  ['delivered', null, 'done', true, 'Доставлен'],
  ['delivering', 'posting_delivered', 'done', true, 'Доставлен'],
  ['delivering', 'posting_received', 'done', true, 'Получен'],
  ['cancelled', 'posting_received', 'cancelled', true, 'Отменён'],
  ['cancelled_from_split_pending', null, 'in_delivery', true, 'Разделён'],
  ['cancelled_from_split_pending', null, 'cancelled', false, 'Отменён'],
  ['arbitration', null, 'in_delivery', true, 'Арбитраж'],
  ['client_arbitration', null, 'in_delivery', true, 'Клиентский арбитраж'],
  ['not_accepted', null, 'in_delivery', true, 'Не принят на сортировочном центре'],
  ['new', null, 'new', false, 'Новый'],
  ['sent_by_seller', null, 'in_delivery', true, 'В доставке'],
  ['done', null, 'done', true, 'Доставлен'],
  ['canceled', null, 'cancelled', true, 'Отменён'],
  [null, null, 'external_processing', false, 'Статус уточняется'],
  ['future-status', null, 'in_delivery', true, 'Статус уточняется'],
]
labels.push(...([
  ['posting_acceptance_in_progress', 'Идёт приёмка'],
  ['posting_in_arbitration', 'Арбитраж'],
  ['posting_in_client_arbitration', 'Клиентский арбитраж'],
  ['posting_created', 'Создано'], ['posting_split_pending', 'Создано'],
  ['posting_in_carriage', 'В перевозке'], ['posting_not_in_carriage', 'Не добавлен в перевозку'],
  ['posting_registered', 'Зарегистрирован'],
  ['posting_awaiting_passport_data', 'Ожидает паспортных данных'],
  ['posting_awaiting_registration', 'Ожидает регистрации'],
  ['posting_registration_error', 'Ошибка регистрации'],
  ['posting_canceled', 'Отменён'],
  ['posting_conditionally_delivered', 'Условно доставлен'],
  ['posting_in_courier_service', 'Курьер в пути'],
  ['posting_transferred_to_courier_service', 'Передаётся в службу доставки'],
  ['posting_driver_pick_up', 'У водителя'], ['posting_in_pickup_point', 'В пункте выдачи'],
  ['posting_on_way_to_city', 'В пути в город'], ['posting_on_way_to_pickup_point', 'В пути в пункт выдачи'],
  ['posting_returned_to_warehouse', 'Возвращён на склад'],
  ['posting_not_in_sort_center', 'Не принят на сортировочном центре'], ['ship_failed', 'Сборка не удалась'],
] as Array<[string, string]>).map(([sub, label]) => ['delivering', sub, 'in_delivery', true, label] as typeof labels[number]))
labels.push(['awaiting_registration', 'posting_transferring_to_delivery', 'in_delivery', true, 'Передаётся курьеру'])

it.each(labels)('test_c1_ozon_status_labels: %s / %s (%s; handed=%s) → %s', async (raw, sub, local, handed, label) => {
  const order = {
    marketplace: 'ozon' as const, status: local, wb_status: raw,
    supplier_status: sub ?? raw, supply_id: handed ? 'supply-721' : null,
    delivered_at: handed ? '2026-10-09T08:00:00Z' : null,
  }
  await act(async () => { root.render(<FbsStatusChip status={orderStatusForChip(order)} />) })
  expect(host.querySelector('[data-testid="fbs-status-chip"]')?.textContent).toBe(label)
})

async function mountScreen() {
  await act(async () => {
    root.render(<MemoryRouter><FfFbsOrdersScreen token="wms721" authHeaders={authHeaders}
      sellers={[{ id: 'seller-721', name: 'Селлер 721' }]} /></MemoryRouter>)
  })
}
const tabs = () => {
  const list = [...host.querySelectorAll<HTMLElement>('[role="tablist"]')]
    .find((node) => node.textContent?.includes('Новые'))!
  return [...list.querySelectorAll<HTMLElement>('[role="tab"]')]
}
async function chooseMarketplace(name: string) {
  const select = host.querySelector<HTMLElement>('[data-testid="fbs-worklist-marketplace"] [role="combobox"]')!
  await act(async () => { select.dispatchEvent(new MouseEvent('mousedown', { bubbles: true })) })
  const option = [...document.querySelectorAll<HTMLElement>('[role="option"]')].find((node) => node.textContent === name)
  expect(option, `marketplace option ${name}`).toBeDefined()
  await act(async () => { option!.click() })
}

it('test_c2_c8_shipped_tab_mixed_filter', async () => {
  await mountScreen()
  expect(tabs().map((tab) => tab.textContent).slice(0, 4)).toEqual(['Новые', 'В работе', 'Отгруженные', 'В доставке'])
  await act(async () => { tabs().find((tab) => tab.textContent === 'Отгруженные')!.click() })
  expect(supplyList).toHaveBeenCalled()
  expect(supplyList.mock.calls.at(-1)?.[2].status_group).toBe('shipped')
})

it('test_c8_wb_filter_preserves_tabs', async () => {
  await mountScreen()
  await chooseMarketplace('Wildberries')
  expect(tabs().map((tab) => tab.textContent)).toEqual(['Новые', 'В работе', 'В доставке', 'Просрочены', 'Завершённые', 'Отменённые'])
})

it('test_c2_c8_shipped_tab_ozon_filter', async () => {
  await mountScreen()
  await chooseMarketplace('Ozon')
  expect(tabs().map((tab) => tab.textContent).slice(0, 4)).toEqual(['Новые', 'В работе', 'Отгруженные', 'В доставке'])
})

function supply(status: string): FbsSupplyWorklistItem {
  return {
    id: 'supply-721', marketplace: 'ozon', wb_supply_id: null, name: 'Поставка Ozon 721', status,
    seller: { id: 'seller-721', name: 'Селлер 721' },
    wb_warehouse: { id: 11, name: 'Ozon Логистика' },
    wms_warehouse: { id: 'warehouse-721', name: 'Основной склад' },
    orders_count: 2, units_count: 2, picked_units_count: 2, boxes_count: 1,
    planned_shipment_date: null, can_add_orders: false,
  }
}

it.each([
  ['shipped', 'Отгружена'], ['acceptance_in_progress', 'Идёт приёмка'],
  ['in_delivery', 'В доставке'], ['done', 'Завершена'], ['assembling', 'В работе'],
])('test_c2_c3_supply_status_label: %s → %s', async (status, label) => {
  const openSupply = vi.fn()
  await act(async () => {
    root.render(<Table><TableBody><FbsAssemblyTaskRows tasks={[]} supplies={[supply(status)]}
      printingSupplyId={null} onOpenAssembly={() => undefined} onOpenSupply={openSupply}
      onPrintSupply={() => undefined} /></TableBody></Table>)
  })
  const row = host.querySelector<HTMLElement>('[data-testid="fbs-18-supply-supply-721"]')!
  expect(row.querySelector('[data-testid="fbs-18-supply-status"]')?.textContent).toBe(label)
  expect(row.textContent).not.toContain('Частично отклонена')
  await act(async () => { row.click() })
  expect(openSupply).toHaveBeenCalledWith('supply-721')
})

it.each([
  ['new', 'Новый'], ['in_supply', 'В отгрузке'], ['assembling', 'Сборка'],
  ['packed', 'Упакован'], ['in_delivery', 'В доставке'], ['sorted', 'Отсортирован'],
  ['done', 'Завершён'], ['cancelled', 'Отменён'], ['defect', 'Дефект'],
])('test_c8_wb_status_labels: %s → %s', async (status, label) => {
  await act(async () => { root.render(<FbsStatusChip status={orderStatusForChip({
    marketplace: 'wb', status, wb_status: 'waiting',
  })} />) })
  expect(host.querySelector('[data-testid="fbs-status-chip"]')?.textContent).toBe(label)
})
