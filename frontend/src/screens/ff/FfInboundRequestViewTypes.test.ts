import { describe, expect, it } from 'vitest'

import { discrepancyActTitle } from './FfInboundRequestViewTypes'

describe('TC-NEW-A3-006 discrepancy act display parity', () => {
  it('keeps the baseline two-digit Russian year in the visible act title', () => {
    expect(discrepancyActTitle('2026-08-28T12:34:00+03:00')).toBe('Акт от 28.08.26, 12:34')
  })
})
