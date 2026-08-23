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

  it('uses only the API flag after a service warehouse is renamed', () => {
    expect(
      reportWarehouseOptions([
        { id: 'physical', name: 'FBS WB Основной', code: 'main', is_operational: true },
        { id: 'service', name: 'Архив', code: 'fbs-wb-archive', is_operational: false },
      ]),
    ).toEqual([{ id: 'physical', name: 'FBS WB Основной' }])
  })
})
