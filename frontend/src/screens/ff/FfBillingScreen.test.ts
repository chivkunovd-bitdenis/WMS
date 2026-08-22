import { describe, expect, it } from 'vitest'

import { buildInvoicePrintHtml, buildLedgerSearchParams, STORAGE_SERVICE_CODE } from './FfBillingScreen'

describe('FfBillingScreen billing contract', () => {
  it('requests the selected month through the period parameter', () => {
    const params = buildLedgerSearchParams('2026-08')

    expect(params.get('period')).toBe('2026-08')
    expect(params.has('date')).toBe(false)
  })

  it('uses the shared storage ledger service code', () => {
    expect(STORAGE_SERVICE_CODE).toBe('storage_liter_day')
  })

  it('builds a printable invoice without technical profile keys or controls', () => {
    const html = buildInvoicePrintHtml({
      id: 'invoice-1',
      number: 'СЧ-2026-00041',
      period: '2026-07',
      seller_name: 'Луна',
      issued_at: '2026-08-01T00:00:00Z',
      total_amount: 48392,
      status: 'issued',
      ff_profile: { legal_name: 'ООО «Фулфилмент Волна»', inn: '7701234567' },
      seller_profile: { legal_name: 'ООО «Луна Трейд»', inn: '7812345678' },
      lines: [{ id: 'line-1', service_code: 'inbound', unit: 'item', quantity: 1245, rate: 12, amount: 14940 }],
    })

    expect(html).toContain('Юридическое наименование')
    expect(html).toContain('48 392,00 ₽')
    expect(html).not.toContain('legal_name')
    expect(html).not.toContain('<button')
  })
})
