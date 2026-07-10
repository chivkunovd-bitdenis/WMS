import { describe, expect, it } from 'vitest'

import { createLatestRequestSequence } from './latestRequestSequence'

describe('createLatestRequestSequence', () => {
  it('accepts only the latest request and supports invalidation', () => {
    const sequence = createLatestRequestSequence()

    const first = sequence.next()
    const second = sequence.next()

    expect(sequence.isLatest(first)).toBe(false)
    expect(sequence.isLatest(second)).toBe(true)

    sequence.invalidate()

    expect(sequence.isLatest(second)).toBe(false)
  })

  it('rejects an apply completion after close and reopen', () => {
    const sequence = createLatestRequestSequence()
    const oldApply = sequence.next()

    sequence.invalidate()
    const reopenedDialog = sequence.next()

    expect(sequence.isLatest(oldApply)).toBe(false)
    expect(sequence.isLatest(reopenedDialog)).toBe(true)
  })
})
