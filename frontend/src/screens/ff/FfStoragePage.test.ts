import { describe, expect, it } from 'vitest'

import { buildStorageTariffPayload, isStorageRateStartDateAllowed, STORAGE_TARIFF_SCOPE_LABEL } from './FfStoragePage'

describe('isStorageRateStartDateAllowed', () => {
  const moscowToday = '2026-08-23'

  it('rejects a date before today in Moscow', () => {
    expect(isStorageRateStartDateAllowed('2026-08-22', moscowToday)).toBe(false)
  })

  it('allows today and a future date in Moscow', () => {
    expect(isStorageRateStartDateAllowed(moscowToday, moscowToday)).toBe(true)
    expect(isStorageRateStartDateAllowed('2026-08-24', moscowToday)).toBe(true)
  })

})

describe('storage tariff dialog contract', () => {
  it('sends the loaded matrix revision and never scopes a tariff write to one warehouse', () => {
    expect(buildStorageTariffPayload({
      revision: 7,
      amount: 1.25,
      validFrom: '2026-08-28',
      sellerException: { sellerId: 'seller-1', amount: 1.5, validFrom: '2026-09-01' },
    })).toEqual({
      revision: 7,
      amount: 1.25,
      valid_from: '2026-08-28',
      seller_exception: { seller_id: 'seller-1', amount: 1.5, valid_from: '2026-09-01' },
    })
    expect(STORAGE_TARIFF_SCOPE_LABEL).toBe('Все операционные склады')
  })
})
