import { renderToStaticMarkup } from 'react-dom/server'
import { describe, expect, it } from 'vitest'
import { FfBillingInvoicesPanel } from './FfBillingInvoicesPanel'

const sellers = [
  { id: 'seller-a', name: 'ООО Восход' },
  { id: 'seller-b', name: 'ИП Лисицына' },
]

describe('FfBillingInvoicesPanel with a seller pinned by the seller card (WMS-491)', () => {
  it('drops the seller dropdown and the seller column when fixedSellerId is set', () => {
    const markup = renderToStaticMarkup(
      <FfBillingInvoicesPanel token="test-token" sellers={sellers} fixedSellerId="seller-a" />,
    )
    expect(markup).not.toContain('data-testid="billing-seller"')
    // «Селлер» — заголовок колонки; в закреплённом режиме этой колонки нет вовсе.
    expect(markup).not.toMatch(/<th[^>]*>Селлер<\/th>/)
  })

  it('keeps the seller dropdown and column in the normal "Расчёты" usage', () => {
    const markup = renderToStaticMarkup(<FfBillingInvoicesPanel token="test-token" sellers={sellers} />)
    expect(markup).toContain('data-testid="billing-seller"')
    expect(markup).toMatch(/<th[^>]*>Селлер<\/th>/)
  })

  it('keeps the status filter and search available when a seller is pinned', () => {
    const markup = renderToStaticMarkup(
      <FfBillingInvoicesPanel token="test-token" sellers={sellers} fixedSellerId="seller-a" />,
    )
    expect(markup).toContain('data-testid="billing-status"')
    expect(markup).toContain('data-testid="filter-search"')
  })
})
