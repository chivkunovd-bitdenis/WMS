import { createElement } from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { buildInvoicePrintHtml, buildLedgerSearchParams, CANCEL_INVOICE_ERROR_MESSAGE, cancelInvoiceRequest, formatMoscowDate, initialBillingTabPeriods, InvoiceDocumentDetails, ledgerDocumentTarget, STORAGE_SERVICE_CODE, updateBillingTabPeriod } from './FfBillingScreen'

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('FfBillingScreen billing contract', () => {
  it('requests the selected month through the period parameter', () => {
    const params = buildLedgerSearchParams('2026-08')

    expect(params.get('period')).toBe('2026-08')
    expect(params.has('date')).toBe(false)
  })

  it('uses the shared storage ledger service code', () => {
    expect(STORAGE_SERVICE_CODE).toBe('storage_liter_day')
  })

  it('formats dates in Moscow time independently from the environment timezone', () => {
    const timestamp = '2026-08-31T21:30:00Z'
    const originalTimezone = process.env.TZ

    process.env.TZ = 'America/Los_Angeles'
    const pacificResult = formatMoscowDate(timestamp)
    process.env.TZ = 'Asia/Tokyo'
    const tokyoResult = formatMoscowDate(timestamp)
    process.env.TZ = originalTimezone

    expect(pacificResult).toBe('01.09.2026')
    expect(tokyoResult).toBe('01.09.2026')
  })

  it('opens charges and invoices with their contract months and preserves each manually selected month', () => {
    const opened = initialBillingTabPeriods(new Date(2026, 7, 23))

    expect(opened.charges).toBe('2026-08')
    expect(opened.invoices).toBe('2026-07')

    const afterChargesSelection = updateBillingTabPeriod(opened, 'charges', '2026-06')
    const afterInvoicesSelection = updateBillingTabPeriod(afterChargesSelection, 'invoices', '2026-05')

    expect(afterInvoicesSelection.charges).toBe('2026-06')
    expect(afterInvoicesSelection.invoices).toBe('2026-05')
  })

  it('routes supported ledger sources to their existing documents', () => {
    expect(ledgerDocumentTarget({ source_type: 'inbound_intake', source_id: 'inbound-1' }))
      .toEqual({ kind: 'inbound', sourceId: 'inbound-1' })
    expect(ledgerDocumentTarget({ source_type: 'marketplace_unload', source_id: 'unload/1' }))
      .toEqual({ kind: 'route', to: '/app/ff/mp-shipments?open_mp=unload%2F1' })
    expect(ledgerDocumentTarget({ source_type: 'storage_measurement', source_id: 'storage-1' }))
      .toBeNull()
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

  it('keeps an issued invoice unchanged and reports that cancellation was not confirmed after a network failure', async () => {
    const fetchMock = vi.fn().mockRejectedValue(new Error('Network unavailable'))
    vi.stubGlobal('fetch', fetchMock)
    const originalStatus = 'issued'

    const result = await cancelInvoiceRequest('invoice-1', 'test')

    expect(fetchMock).toHaveBeenCalledWith('/api/billing/invoices/invoice-1/cancel', expect.objectContaining({ method: 'POST' }))
    expect(result).toEqual({ ok: false, message: CANCEL_INVOICE_ERROR_MESSAGE })
    expect(originalStatus).toBe('issued')
  })

  it('renders expanded source document quantity and kopeck amount in separate cells', () => {
    const markup = renderToStaticMarkup(createElement(InvoiceDocumentDetails, {
      period: '2026-07',
      line: {
        id: 'line-1', service_code: 'inbound', unit: 'item', quantity: 84, rate: 1200, amount: 100800,
        documents: [{ date: '2026-07-18T10:00:00Z', number: 'ПР-000141', quantity: 84, amount: 100800 }],
      },
    }))

    expect(markup).toContain('ПР-000141')
    expect(markup).toContain('>84</span>')
    expect(markup).toContain('>1 008,00 ₽</span>')
    expect(markup).not.toContain('100800')
  })
})
