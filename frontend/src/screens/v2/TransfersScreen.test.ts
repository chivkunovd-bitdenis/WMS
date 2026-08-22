import { describe, expect, it } from 'vitest'

import { buildTransferOperations, type TransferMovementRow } from './TransfersScreen'

const movements: TransferMovementRow[] = [
  {
    id: 'out',
    product_id: 'product',
    sku_code: 'SKU-1',
    product_name: 'Товар',
    storage_location_id: 'north-cell',
    storage_location_code: 'N-01',
    warehouse_id: 'north',
    quantity_delta: -3,
    movement_type: 'stock_transfer_out',
    transfer_group_id: 'pair',
    created_at: '2026-08-22T06:00:00Z',
  },
  {
    id: 'in',
    product_id: 'product',
    sku_code: 'SKU-1',
    product_name: 'Товар',
    storage_location_id: 'south-cell',
    storage_location_code: 'S-01',
    warehouse_id: 'south',
    quantity_delta: 3,
    movement_type: 'stock_transfer_in',
    transfer_group_id: 'pair',
    created_at: '2026-08-22T06:00:00Z',
  },
]

describe('buildTransferOperations', () => {
  it('turns the technical pair into one operation with both warehouse sides', () => {
    const operations = buildTransferOperations(
      movements,
      [{ id: 'north', name: 'Склад Север' }, { id: 'south', name: 'Склад Юг' }],
      [],
    )

    expect(operations).toEqual([{
      id: 'pair',
      product: 'SKU-1 — Товар',
      quantity: 3,
      fromWarehouse: { id: 'north', name: 'Склад Север' },
      toWarehouse: { id: 'south', name: 'Склад Юг' },
      fromLocation: 'N-01',
      toLocation: 'S-01',
    }])
  })

  it('does not invent the missing side of an incomplete pair', () => {
    expect(buildTransferOperations(movements.slice(0, 1), [], [])).toEqual([])
  })
})
