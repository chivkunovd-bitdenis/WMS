import { describe, expect, it } from 'vitest'
import {
  computeMarkingAvailable,
  computeMarkingAvailableFromInventory,
  sumSharedBasketAvailable,
} from './useFfProductMarkingPrint'

describe('markingAvailability', () => {
  it('sums personal pools and shared baskets', () => {
    expect(
      computeMarkingAvailable(
        [{ available: 2 }, { available: 3 }],
        [{ available: 10 }, { available: 5 }],
      ),
    ).toBe(20)
  })

  it('inventory row with only shared basket is printable', () => {
    expect(
      computeMarkingAvailableFromInventory(0, [{ available: 42 }]),
    ).toBe(42)
  })

  it('sumSharedBasketAvailable handles empty list', () => {
    expect(sumSharedBasketAvailable([])).toBe(0)
  })
})
