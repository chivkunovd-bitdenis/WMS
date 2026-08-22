import { describe, expect, it } from 'vitest'
import { formatMoney } from './Cells'

describe('formatMoney', () => {
  it('formats positive, zero, reversal and missing amounts as RUB', () => {
    expect(formatMoney(1234.5)).toBe('1\u00a0234,50\u00a0₽')
    expect(formatMoney(0)).toBe('0,00\u00a0₽')
    expect(formatMoney(-600)).toBe('-600,00\u00a0₽')
    expect(formatMoney(null)).toBe('—')
    expect(formatMoney(undefined)).toBe('—')
  })
})
