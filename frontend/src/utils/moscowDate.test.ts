import { describe, expect, it } from 'vitest'
import { getMoscowDateString } from './moscowDate'

describe('getMoscowDateString', () => {
  it('returns_tomorrow_moscow_when_it_is_23_utc_but_next_day_in_moscow', () => {
    // 2026-08-22T23:30:00Z → MSK 2026-08-23 02:30:00 → date '2026-08-23'
    expect(getMoscowDateString(new Date('2026-08-22T23:30:00Z'))).toBe('2026-08-23')
  })

  it('returns the same day during Moscow afternoon hours', () => {
    // 2026-08-22T12:00:00Z → MSK 2026-08-22 15:00:00 → date '2026-08-22'
    expect(getMoscowDateString(new Date('2026-08-22T12:00:00Z'))).toBe('2026-08-22')
  })

  it('rolls over at exactly 21:00 UTC which is midnight in Moscow', () => {
    // 2026-08-22T21:00:00Z → MSK 2026-08-23 00:00:00 → date '2026-08-23'
    expect(getMoscowDateString(new Date('2026-08-22T21:00:00Z'))).toBe('2026-08-23')
  })

  it('returns correct date one second before midnight UTC but still today in Moscow', () => {
    // 2026-08-22T20:59:59Z → MSK 2026-08-22 23:59:59 → date '2026-08-22'
    expect(getMoscowDateString(new Date('2026-08-22T20:59:59Z'))).toBe('2026-08-22')
  })
})
