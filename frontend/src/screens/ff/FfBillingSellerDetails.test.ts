import { describe, expect, it } from 'vitest'

import { buildSections, type SellerReportDetails } from './FfBillingSellerDetails'

describe('FfBillingSellerDetails FBS grouping', () => {
  it('keeps non-billable FBS picks out of the FBS ledger section', () => {
    const details: SellerReportDetails = {
      seller_id: 'seller-a',
      seller_name: 'Seller A',
      next_cursor: null,
      storage_row: null,
      entries: [
        {
          id: 'fbs-order', kind: 'operation_fact', occurred_at: '2026-09-13T12:00:00Z',
          service_code: 'fbs_order', item_quantity: 3, source_type: 'fbs_order', source_id: 'order-a',
          source_target: { kind: 'fbs_order', source_id: 'order-a' }, document_number: 'Ozon-1',
          product_name: 'X', sku: 'X', result: 'completed', rate_kopecks: 4000, amount_kopecks: 12000,
          billing_ledger_entry_id: 'ledger-fbs',
        },
        ...['pick-1', 'pick-2', 'pick-3'].map((id) => ({
          id, kind: 'operation_fact' as const, occurred_at: '2026-09-13T11:00:00Z',
          service_code: 'fbs_pick', item_quantity: 1, source_type: 'fbs_supply', source_id: 'supply-a',
          source_target: null, document_number: 'Supply-1', product_name: 'X', sku: 'X',
          result: 'completed' as const,
        })),
      ],
    }

    const sections = buildSections(details)
    const fbs = sections.find((section) => section.kind === 'service' && section.id === 'fbs')
    const other = sections.find((section) => section.kind === 'service' && section.id === 'other')

    expect(fbs?.kind).toBe('service')
    if (fbs?.kind !== 'service') throw new Error('FBS section is missing')
    // The only FBS row is the same billable delivery that produces the summary's 3 units.
    expect(fbs.entries.map((entry) => entry.service_code)).toEqual(['fbs_order'])
    expect(fbs.entries.reduce((sum, entry) => sum + (entry.item_quantity ?? 0), 0)).toBe(3)
    expect(other?.kind).toBe('service')
    if (other?.kind !== 'service') throw new Error('Auxiliary FBS picks are missing')
    expect(other.entries.map((entry) => entry.service_code)).toEqual(['fbs_pick', 'fbs_pick', 'fbs_pick'])
  })
})
