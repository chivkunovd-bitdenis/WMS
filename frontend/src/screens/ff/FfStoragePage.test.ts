import { describe, expect, it } from 'vitest'

import { isStorageRateStartDateAllowed } from './FfStoragePage'

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
