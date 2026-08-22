import { describe, expect, it } from 'vitest'
import type { TransferRow, TransferType } from './TransfersScreen'

// Воспроизводим фильтрацию из filteredTransfers useMemo (TransfersScreen).
// TC-S25-*: журнал переносов — тип и поиск.
type TransferTypeFilter = TransferType | 'all'

function filterTransfers(
  transfers: TransferRow[],
  typeFilter: TransferTypeFilter,
  search: string,
): TransferRow[] {
  const q = search.trim().toLowerCase()
  return transfers
    .filter((t) => typeFilter === 'all' || t.transfer_type === typeFilter)
    .filter(
      (t) =>
        !q ||
        t.product_name.toLowerCase().includes(q) ||
        (t.from_location_code ?? '').toLowerCase().includes(q) ||
        (t.to_location_code ?? '').toLowerCase().includes(q),
    )
}

function makeTransfer(
  partial: Partial<TransferRow> & Pick<TransferRow, 'id' | 'transfer_type'>,
): TransferRow {
  return {
    from_location_code: null,
    to_location_code: null,
    from_warehouse_name: null,
    to_warehouse_name: null,
    product_name: 'Товар',
    quantity: 1,
    supply_id: null,
    created_at: '2026-01-01T00:00:00Z',
    ...partial,
  }
}

describe('TransfersScreen type filter (R-12)', () => {
  it('TC-S25-001 показывает все переносы когда typeFilter=all', () => {
    const transfers = [
      makeTransfer({ id: '1', transfer_type: 'manual' }),
      makeTransfer({ id: '2', transfer_type: 'auto_pick' }),
    ]
    expect(filterTransfers(transfers, 'all', '')).toHaveLength(2)
  })

  it('TC-S25-002 фильтрует только ручные переносы', () => {
    const transfers = [
      makeTransfer({ id: '1', transfer_type: 'manual' }),
      makeTransfer({ id: '2', transfer_type: 'auto_pick' }),
    ]
    const result = filterTransfers(transfers, 'manual', '')
    expect(result).toHaveLength(1)
    expect(result[0].id).toBe('1')
  })

  it('TC-S25-003 фильтрует только автопереносы при подборе', () => {
    const transfers = [
      makeTransfer({ id: '1', transfer_type: 'manual' }),
      makeTransfer({ id: '2', transfer_type: 'auto_pick' }),
    ]
    const result = filterTransfers(transfers, 'auto_pick', '')
    expect(result).toHaveLength(1)
    expect(result[0].id).toBe('2')
  })

  it('TC-S25-004 поиск по названию товара (регистронезависимый)', () => {
    const transfers = [
      makeTransfer({ id: '1', transfer_type: 'manual', product_name: 'Ботинки синие' }),
      makeTransfer({ id: '2', transfer_type: 'manual', product_name: 'Носки белые' }),
    ]
    const result = filterTransfers(transfers, 'all', 'БОТИНКИ')
    expect(result).toHaveLength(1)
    expect(result[0].id).toBe('1')
  })

  it('TC-S25-005 поиск по коду ячейки откуда', () => {
    const transfers = [
      makeTransfer({ id: '1', transfer_type: 'manual', from_location_code: 'A-01' }),
      makeTransfer({ id: '2', transfer_type: 'manual', from_location_code: 'B-02' }),
    ]
    expect(filterTransfers(transfers, 'all', 'a-01')).toHaveLength(1)
  })

  it('TC-S25-006 поиск по коду ячейки куда', () => {
    const transfers = [
      makeTransfer({ id: '1', transfer_type: 'auto_pick', to_location_code: 'C-10' }),
      makeTransfer({ id: '2', transfer_type: 'auto_pick', to_location_code: 'D-20' }),
    ]
    expect(filterTransfers(transfers, 'all', 'c-10')).toHaveLength(1)
  })

  it('TC-S25-007 тип+поиск применяются совместно', () => {
    const transfers = [
      makeTransfer({ id: '1', transfer_type: 'manual', product_name: 'Куртка' }),
      makeTransfer({ id: '2', transfer_type: 'auto_pick', product_name: 'Куртка' }),
      makeTransfer({ id: '3', transfer_type: 'manual', product_name: 'Брюки' }),
    ]
    const result = filterTransfers(transfers, 'manual', 'куртка')
    expect(result).toHaveLength(1)
    expect(result[0].id).toBe('1')
  })

  it('TC-S25-008 пустой список не вызывает ошибок', () => {
    expect(filterTransfers([], 'all', '')).toHaveLength(0)
    expect(filterTransfers([], 'manual', 'что-то')).toHaveLength(0)
  })
})
