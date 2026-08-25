import { describe, expect, it } from 'vitest'

import { sellerHasOzonConnection } from './ffManualProductOzon'

describe('sellerHasOzonConnection', () => {
  it('allows Ozon fields only for the selected connected seller', () => {
    const sellers = [
      { id: 'wb-only', name: 'WB only', ozon_connected: false },
      { id: 'ozon', name: 'Ozon', ozon_connected: true },
    ]

    expect(sellerHasOzonConnection(sellers, 'wb-only')).toBe(false)
    expect(sellerHasOzonConnection(sellers, 'ozon')).toBe(true)
    expect(sellerHasOzonConnection(sellers, '')).toBe(false)
  })

  it('keeps the optional API field backward compatible', () => {
    expect(
      sellerHasOzonConnection([{ id: 'legacy', name: 'Legacy seller' }], 'legacy'),
    ).toBe(false)
  })
})
