import { describe, expect, it } from 'vitest'

import { isStorageRateStartDateAllowed, mergeRecalculatedStorageData, mergeRecalculatedStorageStatements } from './FfStoragePage'

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

describe('mergeRecalculatedStorageStatements', () => {
  it('replaces the open draft returned by tariff repricing and keeps the rest of the table', () => {
    const current = [
      { id: 'draft-open', status: 'draft', total_amount: '100.00' },
      { id: 'fixed', status: 'fixed', total_amount: '80.00' },
    ]
    const recalculated = [
      { id: 'draft-open', status: 'draft', total_amount: '140.00' },
      { id: 'draft-another-month', status: 'draft', total_amount: '30.00' },
    ]

    const result = mergeRecalculatedStorageStatements(current, recalculated)

    expect(result).toEqual([
      { id: 'draft-open', status: 'draft', total_amount: '140.00' },
      { id: 'fixed', status: 'fixed', total_amount: '80.00' },
    ])
    expect(result[1]).toBe(current[1])
    expect(current[0].total_amount).toBe('100.00')
  })

  it('keeps the last successful table when repricing returns no rows', () => {
    const current = [{ id: 'draft-open', total_amount: '100.00' }]

    const result = mergeRecalculatedStorageStatements(current, [])

    expect(result).toEqual(current)
    expect(result[0]).toBe(current[0])
  })
})

describe('mergeRecalculatedStorageData', () => {
  it('keeps the server state that says the selected past month has no applicable tariff', () => {
    const current = {
      tariff_configured: false,
      warehouses: [],
      statements: [{ id: 'draft-open', total_amount: '0.00' }],
    }

    const result = mergeRecalculatedStorageData(current, [])

    expect(result.tariff_configured).toBe(false)
    expect(result.statements).toEqual(current.statements)
    expect(result.statements[0]).toBe(current.statements[0])
  })

  it('keeps fixed rows while the server state says the selected covered month has a tariff', () => {
    const current = {
      tariff_configured: true,
      warehouses: [],
      statements: [
        { id: 'draft-open', status: 'draft', total_amount: '100.00' },
        { id: 'fixed', status: 'fixed', total_amount: '80.00' },
      ],
    }

    const result = mergeRecalculatedStorageData(current, [
      { id: 'draft-open', status: 'draft', total_amount: '140.00' },
    ])

    expect(result.tariff_configured).toBe(true)
    expect(result.statements).toEqual([
      { id: 'draft-open', status: 'draft', total_amount: '140.00' },
      { id: 'fixed', status: 'fixed', total_amount: '80.00' },
    ])
    expect(result.statements[1]).toBe(current.statements[1])
  })
})
