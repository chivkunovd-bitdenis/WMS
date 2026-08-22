import { describe, expect, it } from 'vitest'

import { buildLedgerSearchParams, STORAGE_SERVICE_CODE } from './FfBillingScreen'

describe('FfBillingScreen billing contract', () => {
  it('requests the selected month through the period parameter', () => {
    const params = buildLedgerSearchParams('2026-08')

    expect(params.get('period')).toBe('2026-08')
    expect(params.has('date')).toBe(false)
  })

  it('uses the shared storage ledger service code', () => {
    expect(STORAGE_SERVICE_CODE).toBe('storage_liter_day')
  })
})
