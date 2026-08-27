import { createElement } from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { buildInvoicePrintHtml, buildLedgerSearchParams, CANCEL_INVOICE_ERROR_MESSAGE, cancelInvoiceRequest, formatMoscowDate, formatMoscowDateTime, initialBillingTabPeriods, InvoiceDocumentDetails, joinVisibleParts, ledgerDocumentTarget, parseApiDecimal, sellerQuickRange, sellerReportSearchParams, STORAGE_SERVICE_CODE, updateBillingTabPeriod } from './FfBillingScreen'

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

  it('sends Moscow date bounds and finance mode to the additive seller-report endpoint', () => {
    const params = sellerReportSearchParams({ start: '2026-08-20', end: '2026-08-22' }, false, 'seller-1', 'Альфа')

    expect(params.toString()).toBe('date_from=2026-08-20&date_to=2026-08-22&include_finance=false&seller_id=seller-1&search=%D0%90%D0%BB%D1%8C%D1%84%D0%B0')
    expect(params.has('amount_kopecks')).toBe(false)
  })

  it('normalizes decimal strings returned by the invoice API', () => {
    expect(parseApiDecimal('181900.000')).toBe(181900)
    expect(parseApiDecimal('63000.00')).toBe(63000)
  })

  it('joins only visible invoice document parts', () => {
    expect(joinVisibleParts(['31.07.2026', '', null, '181 900', '14 552,00 ₽']))
      .toBe('31.07.2026 · 181 900 · 14 552,00 ₽')
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

  it('keeps quick seller periods in Moscow calendar dates', () => {
    expect(sellerQuickRange('today', '2026-08-31')).toEqual({ start: '2026-08-31', end: '2026-08-31' })
    expect(sellerQuickRange('seven_days', '2026-08-31')).toEqual({ start: '2026-08-25', end: '2026-08-31' })
    expect(sellerQuickRange('thirty_days', '2026-08-31')).toEqual({ start: '2026-08-02', end: '2026-08-31' })
    expect(sellerQuickRange('current_month', '2026-08-31')).toEqual({ start: '2026-08-01', end: '2026-08-31' })
    expect(sellerQuickRange('previous_month', '2026-01-15')).toEqual({ start: '2025-12-01', end: '2025-12-31' })
    expect(formatMoscowDateTime('2026-08-20T10:00:00+03:00')).toContain('20.08.2026')
  })

  it('opens charges and invoices with Moscow months and preserves each manually selected month', () => {
    const opened = initialBillingTabPeriods(new Date('2026-08-31T21:30:00Z'))

    expect(opened.charges).toBe('2026-09')
    expect(opened.invoices).toBe('2026-08')

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
      total_amount: '63000.00',
      status: 'issued',
      ff_profile: { legal_name: 'ООО «Фулфилмент Волна»', inn: '7701234567' },
      seller_profile: { legal_name: 'ООО «Луна Трейд»', inn: '7812345678' },
      lines: [{ id: 'line-1', service_code: 'inbound', unit: 'item', quantity: '84.000', rate: '1200', amount: '63000' }],
    })

    expect(html).toContain('Юридическое наименование')
    expect(html).toContain('12,00 ₽')
    expect(html).toContain('630,00 ₽')
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

  it('renders expanded source document as one clean sequence of visible parts', () => {
    const markup = renderToStaticMarkup(createElement(InvoiceDocumentDetails, {
      period: '2026-07',
      line: {
        id: 'line-1', service_code: 'inbound', unit: 'item', quantity: '84.000', rate: '1200', amount: '100800',
        documents: [{ date: '2026-07-18T10:00:00Z', number: 'ПР-000141', quantity: '84.000', amount: '100800' }],
      },
    }))

    expect(markup).toContain('ПР-000141')
    expect(markup).toContain('ПР-000141 · 84 · 1 008,00 ₽')
    expect(markup).not.toContain('100800')
    expect(markup.replace(/<[^>]+>/g, '')).not.toContain('· ·')
  })
})
