import { describe, expect, it } from 'vitest'
import { inboundMarketplaceLabel } from './inboundDraftMarketplace'

describe('inbound marketplace label', () => {
  it('uses the complete catalog marketplace set, including WB without an Ozon binding', () => {
    expect(inboundMarketplaceLabel({ marketplaces: ['wb'] })).toBe('WB')
    expect(inboundMarketplaceLabel({ marketplaces: ['wb', 'ozon'] })).toBe('WB / Ozon')
  })
})
