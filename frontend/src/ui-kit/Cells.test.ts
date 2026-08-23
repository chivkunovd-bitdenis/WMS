import { createElement } from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import { describe, expect, it } from 'vitest'

import { formatMoney, MoneyCell } from './Cells'

describe('formatMoney', () => {
  it('formats integer kopecks, zero, reversal and missing amounts as RUB', () => {
    expect(formatMoney(4500)).toBe('45,00\u00a0₽')
    expect(formatMoney(0)).toBe('0,00\u00a0₽')
    expect(formatMoney(-60000)).toBe('-600,00\u00a0₽')
    expect(formatMoney(null)).toBe('—')
    expect(formatMoney(undefined)).toBe('—')
  })
})

describe('MoneyCell', () => {
  it('renders positive, reversal, zero and missing minor amounts', () => {
    const cases: Array<[number | null, string]> = [
      [4500, '45,00\u00a0₽'],
      [-60000, '-600,00\u00a0₽'],
      [0, '0,00\u00a0₽'],
      [null, '—'],
    ]

    for (const [minor, expected] of cases) {
      expect(renderToStaticMarkup(createElement(MoneyCell, { minor }))).toContain(expected)
    }
  })
})
