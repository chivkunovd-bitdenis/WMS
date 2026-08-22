import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { FbsSupplyCreateDialog } from './FbsSupplyCreateDialog'
import { ordersWord } from './fbsUx'

const { createMock, preflightMock } = vi.hoisted(() => ({
  createMock: vi.fn(),
  preflightMock: vi.fn(),
}))

vi.mock('./fbsApi', async () => {
  const actual = await vi.importActual<typeof import('./fbsApi')>('./fbsApi')
  return {
    ...actual,
    createFbsSupplyFromOrders: createMock,
    preflightFbsSupply: preflightMock,
  }
})

const warningPreflight = {
  compatible: true,
  summary: {
    seller: { id: 'seller-1', name: 'Селлер Один' },
    wb_warehouse: { id: 1, name: 'WB Подольск' },
    wms_warehouse: { id: 'north', name: 'Склад Север' },
    buyer_type: 'individual' as const,
    cargo_type: 'mgt',
    orders_count: 2,
    required_marking_count: 0,
    pvz_allowed_count: 2,
    pvz_blocked_count: 0,
    nearest_deadline_at: '2026-08-22T12:00:00Z',
  },
  issues: [],
  stock_preflight: {
    compatible: true,
    recommended_warehouse: { id: 'south', name: 'Склад Юг' },
    warning_lines: [{
      product_id: 'product-1', product_name: 'Товар 1', required: 10, current: 4, total: 10, shortage: 0,
      source_warehouse: { id: 'south', name: 'Склад Юг', available: 6 },
    }],
    blocking_lines: [],
  },
  warehouse_options: [{ id: 'north', name: 'Склад Север' }, { id: 'south', name: 'Склад Юг' }],
  recommended_warehouse: { id: 'south', name: 'Склад Юг' },
  inventory: [{
    product_id: 'product-1', product_name: 'Товар 1', required: 10, current: 4, total: 10, shortage: 0,
    source_warehouse: { id: 'south', name: 'Склад Юг', available: 6 },
  }],
}

function renderDialog() {
  return render(
    <FbsSupplyCreateDialog
      token="test-token"
      authHeaders={() => ({})}
      orderIds={['order-1', 'order-2']}
      open
      onClose={vi.fn()}
      onCreated={vi.fn()}
    />,
  )
}

describe('FBS supply creation copy', () => {
  beforeEach(() => {
    createMock.mockReset()
    preflightMock.mockReset()
  })

  it('TC-FBS-UX-001 uses correct Russian order forms', () => {
    expect([1, 2, 4, 5, 11, 21, 22, 25].map((count) => `${count} ${ordersWord(count)}`)).toEqual([
      '1 заказ',
      '2 заказа',
      '4 заказа',
      '5 заказов',
      '11 заказов',
      '21 заказ',
      '22 заказа',
      '25 заказов',
    ])
  })

  it('uses the top-level stock preflight and keeps creation available for a local shortage', async () => {
    preflightMock.mockResolvedValue(warningPreflight)
    createMock.mockResolvedValue({ id: 'supply-1' })
    renderDialog()

    expect(await screen.findByTestId('fbs-preflight-warning')).toHaveTextContent('На складе «Склад Север» не хватает 6 шт.')
    expect(screen.getByTestId('fbs-preflight-warning-table')).toHaveTextContent('Склад Юг · 6')
    const create = screen.getByTestId('fbs-create-submit')
    await waitFor(() => expect(create).toBeEnabled())
    fireEvent.click(create)
    await waitFor(() => expect(createMock).toHaveBeenCalledWith(
      'test-token', expect.any(Function), expect.objectContaining({ selected_warehouse_id: 'south' }),
    ))
  })

  it('blocks creation with the top-level aggregate shortage', async () => {
    preflightMock.mockResolvedValue({
      ...warningPreflight,
      compatible: false,
      stock_preflight: {
        ...warningPreflight.stock_preflight,
        compatible: false,
        warning_lines: [],
        blocking_lines: [{
          product_id: 'product-1', product_name: 'Товар 1', required: 10, current: 2, total: 7, shortage: 3,
          source_warehouse: { id: 'south', name: 'Склад Юг', available: 5 },
        }],
      },
      inventory: [{
        product_id: 'product-1', product_name: 'Товар 1', required: 10, current: 2, total: 7, shortage: 3,
        source_warehouse: { id: 'south', name: 'Склад Юг', available: 5 },
      }],
    })
    renderDialog()

    expect(await screen.findByTestId('fbs-preflight-stock-error')).toHaveTextContent('Не хватает 3 шт. по 1 товарам')
    expect(screen.getByTestId('fbs-create-submit')).toBeDisabled()
  })
})
