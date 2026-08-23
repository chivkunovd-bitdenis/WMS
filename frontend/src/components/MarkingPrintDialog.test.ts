import { describe, expect, it } from 'vitest'

import { resolveTapeCounts } from './MarkingPrintDialog'

describe('resolveTapeCounts', () => {
  it('keeps zero ЧЗ and an empty tape when the order QR is printed', () => {
    expect(resolveTapeCounts(0, 0, true)).toEqual({
      cz: 0,
      wb: 0,
      tape: [],
      layout: { units: [] },
    })
  })

  it('keeps the old one-ЧЗ minimum when there is no order QR', () => {
    expect(resolveTapeCounts(0, 0, false)).toEqual({
      cz: 1,
      wb: 0,
      tape: ['cz'],
      layout: { units: [{ block: 'cz', copies: 1 }] },
    })
  })

  it('does not add ЧЗ when WB labels remain in the tape', () => {
    expect(resolveTapeCounts(0, 2, true)).toEqual({
      cz: 0,
      wb: 2,
      tape: ['label', 'label'],
      layout: { units: [{ block: 'label', copies: 2 }] },
    })
  })
})
