import { describe, expect, it } from 'vitest'
import { type OzonReturnPreviewGroup } from './OzonReturnPickerDialog'
import {
  filterOzonReturnGroups,
  formatOzonUtilizationDate,
  isOzonReturnUrgent,
  ozonGiveoutStatus,
} from './ozonReturnPickerHelpers'

const groups: OzonReturnPreviewGroup[] = [
  {
    giveout_id: 10,
    giveout_status: 'GIVEOUT_STATUS_APPROVED',
    warehouse_name: 'ПВЗ Тверская',
    warehouse_address: 'Тверская, 1',
    approved_articles_count: 1,
    total_articles_count: 2,
    storage_days: 3,
    utilization_forecast_date: '2026-08-28',
    already_imported: false,
    items: [
      {
        return_id: 1,
        product_id: 'product-1',
        return_barcode: 'RETURN-001',
        offer_id: 'seller-sku',
        ozon_sku: 12345,
        product_name: 'Куртка',
        quantity: 2,
        return_reason_name: 'Не подошёл размер',
        wms_sku: 'WMS-1',
        wms_barcode: '460000000001',
        matched: true,
        warning: null,
      },
    ],
  },
  {
    giveout_id: 20,
    giveout_status: 'GIVEOUT_STATUS_CREATED',
    warehouse_name: 'ПВЗ Арбат',
    warehouse_address: 'Арбат, 2',
    approved_articles_count: 1,
    total_articles_count: 1,
    storage_days: null,
    utilization_forecast_date: null,
    already_imported: true,
    items: [
      {
        return_id: 2,
        product_id: null,
        return_barcode: 'RETURN-002',
        offer_id: 'unmatched-sku',
        ozon_sku: 67890,
        product_name: 'Платье',
        quantity: 1,
        return_reason_name: null,
        wms_sku: null,
        wms_barcode: null,
        matched: false,
        warning: 'Товар не сопоставлен с каталогом',
      },
    ],
  },
]

describe('OzonReturnPickerDialog helpers', () => {
  it('searches by return-label barcode and retains only the matching pickup point', () => {
    expect(filterOzonReturnGroups(groups, 'return-002')).toEqual([
      expect.objectContaining({ giveout_id: 20 }),
    ])
  })

  it('recognises a utilization deadline under a week as urgent', () => {
    expect(isOzonReturnUrgent('2026-08-28', new Date('2026-08-25T12:00:00'))).toBe(true)
    expect(isOzonReturnUrgent('2026-09-02', new Date('2026-08-25T12:00:00'))).toBe(false)
  })

  it('maps provider status to the shared status-chip tone and formats a short deadline', () => {
    expect(ozonGiveoutStatus('GIVEOUT_STATUS_CANCELLED')).toEqual({
      label: 'Отменена',
      tone: 'stop',
    })
    expect(formatOzonUtilizationDate('2026-08-28')).toBe('28.08')
  })
})
