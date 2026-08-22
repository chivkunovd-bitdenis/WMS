import { describe, expect, it } from 'vitest'

import { reportWarehouseOptions } from './SellerApp'

describe('reportWarehouseOptions', () => {
  it('keeps only operational warehouses when the API exposes the flag', () => {
    expect(
      reportWarehouseOptions([
        { id: 'physical', name: 'Основной склад', code: 'main', is_operational: true },
        { id: 'service', name: 'Служебный архив', code: 'archive', is_operational: false },
      ]),
    ).toEqual([{ id: 'physical', name: 'Основной склад' }])
  })

  it('hides the migrated FBS service warehouse for the legacy API response', () => {
    expect(
      reportWarehouseOptions([
        { id: 'physical', name: 'Основной склад', code: 'main' },
        { id: 'service', name: 'FBS WB Архив', code: 'fbs-wb-archive' },
      ]),
    ).toEqual([{ id: 'physical', name: 'Основной склад' }])
  })
})
