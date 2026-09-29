// @vitest-environment jsdom
import { act } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { Table, TableBody } from '@mui/material'
import { afterEach, beforeAll, describe, expect, it, vi } from 'vitest'
import { FbsAssemblyTaskRows } from './FbsAssemblyTaskRows'
import type { FbsAssemblyTask, FbsSupplyWorklistItem } from './fbsApi'

beforeAll(() => {
  ;(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true
})

const supply = (id: string, name: string, seller: string): FbsSupplyWorklistItem => ({
  id,
  marketplace: 'wb',
  wb_supply_id: `WB-${id}`,
  name,
  status: 'assembling',
  seller: { id: `seller-${seller}`, name: seller },
  wb_warehouse: { id: 507, name: 'Коледино' },
  wms_warehouse: { id: 'warehouse-1', name: 'Основной склад' },
  orders_count: 2,
  units_count: 2,
  picked_units_count: id === 'supply-2' ? 1 : 2,
  boxes_count: 1,
  planned_shipment_date: '2026-09-30T09:00:00Z',
  can_add_orders: false,
})

const supplies = [
  supply('supply-1', 'Поставка 1', 'Селлер А'),
  supply('supply-2', 'Поставка 2', 'Селлер Б'),
  supply('supply-3', 'Поставка без задания', 'Селлер В'),
]

const task: FbsAssemblyTask = {
  id: 'task-1',
  number: '№000123',
  created_at: '2026-09-29T12:30:00Z',
  created_by: { id: 'user-1', name: 'Кладовщик' },
  supplies: [
    {
      id: 'supply-1', marketplace: 'wb', name: 'Поставка 1',
      seller: { id: 'seller-Селлер А', name: 'Селлер А' }, status: 'assembling',
      orders_count: 3, picked_count: 2, units_count: 3, picked_units_count: 2, packed_count: 1,
    },
    {
      id: 'supply-2', marketplace: 'wb', name: 'Поставка 2',
      seller: { id: 'seller-Селлер Б', name: 'Селлер Б' }, status: 'assembling',
      orders_count: 2, picked_count: 1, units_count: 2, picked_units_count: 1, packed_count: 0,
    },
  ],
}

let root: Root | null = null
let host: HTMLDivElement | null = null

afterEach(async () => {
  if (root) await act(async () => { root!.unmount() })
  root = null
  host?.remove()
  host = null
  document.body.innerHTML = ''
})

describe('WMS-588: сборочное задание во «В работе»', () => {
  it('показывает агрегирующую строку, её поставки и открывает общую сборку по клику', async () => {
    const openAssembly = vi.fn()
    const openSupply = vi.fn()
    host = document.createElement('div')
    document.body.appendChild(host)
    root = createRoot(host)

    await act(async () => {
      root!.render(
        <Table>
          <TableBody>
            <FbsAssemblyTaskRows
              tasks={[task]}
              supplies={supplies}
              printingSupplyId={null}
              onOpenAssembly={openAssembly}
              onOpenSupply={openSupply}
              onPrintSupply={() => undefined}
            />
          </TableBody>
        </Table>,
      )
    })

    const taskRow = document.querySelector<HTMLElement>('[data-testid="fbs-assembly-task-task-1"]')
    expect(taskRow?.textContent).toContain('Сборочное задание №000123')
    expect(taskRow?.textContent).toContain('29.09.26')
    expect(taskRow?.textContent).toContain('2 поставки')
    expect(taskRow?.textContent).toContain('Селлер А, Селлер Б')
    expect(taskRow?.textContent).toContain('Подбор 3 / 5 · Упаковка 1 / 5')
    expect(taskRow?.textContent).not.toContain('Подобрано')

    const rowIds = [...document.querySelectorAll('tbody > tr')]
      .map((row) => row.getAttribute('data-testid'))
    expect(rowIds).toEqual([
      'fbs-assembly-task-task-1',
      'fbs-18-supply-supply-1',
      'fbs-18-supply-supply-2',
      'fbs-18-supply-supply-3',
    ])
    expect(document.querySelector('[data-testid="fbs-18-supply-supply-1"]')?.textContent)
      .toContain('Поставка 1')
    expect(document.querySelector('[data-testid="fbs-18-supply-supply-3"]')?.textContent)
      .toContain('Поставка без задания')
    expect(document.querySelector('[data-testid="fbs-supply-picked-supply-1"]')?.textContent)
      .toBe('Подобрано')
    expect(document.querySelector('[data-testid="fbs-supply-picked-supply-2"]')).toBeNull()
    expect(document.querySelector('[data-testid="fbs-supply-picked-supply-3"]')?.textContent)
      .toBe('Подобрано')

    const groupedRows = document.querySelectorAll('[data-assembly-task-id="task-1"]')
    expect(groupedRows).toHaveLength(2)
    expect(groupedRows[0]?.getAttribute('data-testid')).toBe('fbs-18-supply-supply-1')
    expect(groupedRows[1]?.getAttribute('data-testid')).toBe('fbs-18-supply-supply-2')
    expect(document.querySelector('[data-testid="fbs-18-supply-supply-3"]')
      ?.getAttribute('data-assembly-task-id')).toBeNull()

    const taskCell = taskRow?.querySelector('td')
    const firstGroupedCell = groupedRows[0]?.querySelector('td')
    const lastGroupedCell = groupedRows[1]?.querySelector('td')
    expect(getComputedStyle(taskCell!).borderTopWidth).toBe('2px')
    expect(getComputedStyle(firstGroupedCell!).borderLeftWidth).toBe('2px')
    expect(getComputedStyle(lastGroupedCell!).borderBottomWidth).toBe('2px')
    expect(getComputedStyle(taskCell!).backgroundColor)
      .not.toBe(getComputedStyle(firstGroupedCell!).backgroundColor)

    await act(async () => { taskRow!.click() })
    expect(openAssembly).toHaveBeenCalledWith(['supply-1', 'supply-2'])

    const supplyRow = document.querySelector<HTMLElement>('[data-testid="fbs-18-supply-supply-1"]')
    await act(async () => { supplyRow!.click() })
    expect(openSupply).toHaveBeenCalledWith('supply-1')
  })

  it('показывает «Подобрано» в шапке, когда подобраны все единицы всех поставок', async () => {
    host = document.createElement('div')
    document.body.appendChild(host)
    root = createRoot(host)
    const completedTask: FbsAssemblyTask = {
      ...task,
      supplies: task.supplies.map((one) => ({
        ...one,
        picked_count: one.orders_count,
        picked_units_count: one.units_count,
      })),
    }

    await act(async () => {
      root!.render(
        <Table>
          <TableBody>
            <FbsAssemblyTaskRows
              tasks={[completedTask]}
              supplies={supplies}
              printingSupplyId={null}
              onOpenAssembly={() => undefined}
              onOpenSupply={() => undefined}
              onPrintSupply={() => undefined}
            />
          </TableBody>
        </Table>,
      )
    })

    expect(document.querySelector('[data-testid="fbs-assembly-task-picked-task-1"]')?.textContent)
      .toBe('Подобрано')
  })
})
