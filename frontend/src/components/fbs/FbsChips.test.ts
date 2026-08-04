import { describe, expect, it } from 'vitest'

import { resolveDeadlineNow } from './FbsChips'

describe('resolveDeadlineNow', () => {
  it('uses server time as the initial deadline reference and only client elapsed time afterwards', () => {
    const serverNow = '2026-08-04T10:00:00.000Z'
    const clientAnchor = 1_000_000

    expect(resolveDeadlineNow(serverNow, clientAnchor, clientAnchor)).toBe(Date.parse(serverNow))
    expect(resolveDeadlineNow(serverNow, clientAnchor + 90_000, clientAnchor)).toBe(
      Date.parse(serverNow) + 90_000,
    )
  })

  it('falls back to the client clock when server time is absent or malformed', () => {
    expect(resolveDeadlineNow(null, 120_000, 100_000)).toBe(120_000)
    expect(resolveDeadlineNow('not-a-date', 120_000, 100_000)).toBe(120_000)
  })
})
