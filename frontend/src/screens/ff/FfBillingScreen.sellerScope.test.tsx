import { renderToStaticMarkup } from 'react-dom/server'
import { MemoryRouter } from 'react-router-dom'
import { describe, expect, it } from 'vitest'

import { FfBillingScreen, sellerBillingSearchParams, sellerReportEmptyState } from './FfBillingScreen'
import {
  documentSupplyCell,
  documentTitleCell,
  FfBillingSellerDetails,
  sectionRateCell,
  type SellerReportDetails,
  type SellerReportEntry,
} from './FfBillingSellerDetails'
import { FfBillingInvoicesPanel, invoiceHistoryEmptyState } from './FfBillingInvoicesPanel'

// WMS-549: режим кабинета селлера у тех же компонентов «Расчётов» — без выбора
// селлера, без действий ФФ и без переходов в его экраны. Режим ФФ по умолчанию
// не должен измениться, поэтому каждая проверка сверяет оба режима.

describe('WMS-549 sellerBillingSearchParams', () => {
  it('sends only Moscow date bounds — server resolves the seller from the token', () => {
    const params = sellerBillingSearchParams({ start: '2026-09-01', end: '2026-09-27' })

    expect(params.toString()).toBe('date_from=2026-09-01&date_to=2026-09-27')
    expect(params.has('seller_id')).toBe(false)
    expect(params.has('include_finance')).toBe(false)
    expect(params.has('search')).toBe(false)
  })
})

describe('WMS-549 empty states without FF hints', () => {
  it('drops the seller-filter hint in seller scope, keeps it for FF', () => {
    expect(sellerReportEmptyState(true)).toEqual({ title: 'За выбранный период документов нет' })
    expect(sellerReportEmptyState(false)).toEqual({
      title: 'За выбранный период документов нет',
      hint: 'Измените период или фильтр селлера.',
    })
    expect(invoiceHistoryEmptyState(true)).toEqual({ title: 'Счета ещё не выставлены' })
    expect(invoiceHistoryEmptyState(false)).toEqual({
      title: 'Счета ещё не выставлены',
      hint: 'Выставьте счёт на вкладке «Селлеры»',
    })
  })
})

describe('WMS-549 FfBillingScreen seller scope', () => {
  it('shows «Начисления» instead of «Селлеры», hides the seller filter/FF actions/purpose line/seller table, shows the drill-down right away', () => {
    const markup = renderToStaticMarkup(
      <MemoryRouter>
        <FfBillingScreen token="seller-token" onOpenInbound={() => {}} sellerScope />
      </MemoryRouter>,
    )

    expect(markup).not.toContain('data-testid="billing-seller"')
    expect(markup).not.toContain('Реквизиты')
    expect(markup).not.toContain('Выставить счёт')
    expect(markup).not.toContain('Селлеров')
    expect(markup).not.toContain('Начисления за работу склада и счета селлерам за выбранный период.')
    // WMS-549 решение владельца 27.09: вкладка «Селлеры» заменена на «Начисления»,
    // таблицы селлеров (с его же именем) под ней больше нет.
    expect(markup).not.toContain('data-testid="billing-seller-summary"')
    expect(markup).not.toContain('>Селлеры<')
    expect(markup).toContain('Расчёты')
    expect(markup).toContain('>Начисления<')
    expect(markup).toContain('Выставленные счета')
    expect(markup).toContain('Ставки')
    expect(markup).toContain('Сегодня')
    // Раскрытие FfBillingSellerDetails смонтировано сразу, без клика по строке.
    expect(markup).toContain('data-testid="billing-seller-details-pending"')
  })

  it('keeps the FF screen unchanged by default: tab is still «Селлеры», seller table renders, no eager drill-down', () => {
    const markup = renderToStaticMarkup(
      <MemoryRouter>
        <FfBillingScreen
          token="ff-token"
          onOpenInbound={() => {}}
          sellers={[{ id: 'seller-1', name: 'Ромашка' }]}
        />
      </MemoryRouter>,
    )

    expect(markup).toContain('data-testid="billing-seller"')
    expect(markup).toContain('Реквизиты')
    expect(markup).toContain('Выставить счёт')
    expect(markup).toContain('Селлеров')
    expect(markup).toContain('Начисления за работу склада и счета селлерам за выбранный период.')
    expect(markup).toContain('data-testid="billing-seller-summary"')
    expect(markup).toContain('>Селлеры<')
    expect(markup).not.toContain('>Ставки<')
    expect(markup).not.toContain('data-testid="billing-seller-details-pending"')
  })
})

const detailsWithLinkableEntries: SellerReportDetails = {
  seller_id: 'seller-1',
  seller_name: 'Ромашка',
  next_cursor: null,
  storage_row: null,
  entries: [
    {
      id: 'inbound-1',
      kind: 'operation_fact',
      occurred_at: '2026-09-20T10:00:00Z',
      service_code: 'inbound',
      item_quantity: 10,
      source_type: 'inbound_intake',
      source_id: 'intake-1',
      source_target: { kind: 'inbound', source_id: 'intake-1' },
      document_number: 'ПР-000900',
      product_name: null,
      sku: null,
      result: 'completed',
      unit: 'item',
      rate_kopecks: 300,
      amount_kopecks: 3000,
      invoice_history: { state: 'known', count: 0 },
      supply: { id: 'supply-1', number: 'ФБС-000012' },
    },
  ],
}

describe('WMS-549 FfBillingSellerDetails seller scope', () => {
  it('hides the section pick column in seller scope, keeps it for FF', () => {
    const sellerMarkup = renderToStaticMarkup(
      <FfBillingSellerDetails
        details={detailsWithLinkableEntries}
        loading={false}
        error={false}
        includeFinance
        sellerScope
        selectedRootIds={[]}
        onToggleRoot={() => {}}
        storageSelected={false}
        onToggleStorage={() => {}}
        onLoadMore={() => {}}
        onOpenInbound={() => {}}
        onOpenFbsOrder={() => {}}
      />,
    )
    const ffMarkup = renderToStaticMarkup(
      <FfBillingSellerDetails
        details={detailsWithLinkableEntries}
        loading={false}
        error={false}
        includeFinance
        selectedRootIds={[]}
        onToggleRoot={() => {}}
        storageSelected={false}
        onToggleStorage={() => {}}
        onLoadMore={() => {}}
        onOpenInbound={() => {}}
        onOpenFbsOrder={() => {}}
      />,
    )

    expect(sellerMarkup).not.toContain('data-testid="billing-pick-section-inbound"')
    expect(ffMarkup).toContain('data-testid="billing-pick-section-inbound"')
  })

  it('renders the document number and supply as plain text in seller scope, as links for FF', () => {
    const entry = detailsWithLinkableEntries.entries[0] as SellerReportEntry
    const sellerTitle = renderToStaticMarkup(<>{documentTitleCell(entry, true, () => {}, () => {})}</>)
    const ffTitle = renderToStaticMarkup(
      <MemoryRouter>{documentTitleCell(entry, false, () => {}, () => {})}</MemoryRouter>,
    )
    const sellerSupply = renderToStaticMarkup(<>{documentSupplyCell(entry.supply ?? null, true)}</>)
    const ffSupply = renderToStaticMarkup(
      <MemoryRouter>{documentSupplyCell(entry.supply ?? null, false)}</MemoryRouter>,
    )

    expect(sellerTitle).not.toContain('<a ')
    expect(sellerTitle).not.toContain('<button')
    expect(sellerTitle).toContain('ПР-000900')
    expect(ffTitle).toContain('<button')

    expect(sellerSupply).not.toContain('<a ')
    expect(sellerSupply).toContain('ФБС-000012')
    expect(ffSupply).toContain('href="/app/ff/fbs?supply_id=supply-1"')
  })
})

describe('WMS-549 F4 (ревью Astra): без поясняющих всплывающих подсказок у селлера', () => {
  it('не передаёт hint статусу FBS в withStatus() для селлера, оставляет его у ФФ', () => {
    const entryWithStatus: SellerReportEntry = {
      ...(detailsWithLinkableEntries.entries[0] as SellerReportEntry),
      fbs_status_label: 'ВБ получил',
    }

    const sellerMarkup = renderToStaticMarkup(<>{documentTitleCell(entryWithStatus, true, () => {}, () => {})}</>)
    const ffMarkup = renderToStaticMarkup(
      <MemoryRouter>{documentTitleCell(entryWithStatus, false, () => {}, () => {})}</MemoryRouter>,
    )

    // Сам статус остаётся в обоих режимах (R10 его разрешает).
    expect(sellerMarkup).toContain('ВБ получил')
    expect(ffMarkup).toContain('ВБ получил')
    // Объясняющий Tooltip добавляет aria-label с текстом пояснения — у селлера его быть не должно.
    expect(sellerMarkup).not.toContain('aria-label="Wildberries подтвердил приём')
    expect(ffMarkup).toContain('aria-label="Wildberries подтвердил приём')
  })

  it('не передаёт пояснение «Документы раздела прошли по разным ставкам» для селлера, оставляет его у ФФ', () => {
    const entries: SellerReportEntry[] = [
      { ...(detailsWithLinkableEntries.entries[0] as SellerReportEntry), id: 'e1', rate_kopecks: 300 },
      { ...(detailsWithLinkableEntries.entries[0] as SellerReportEntry), id: 'e2', rate_kopecks: 500 },
    ]

    const sellerMarkup = renderToStaticMarkup(<>{sectionRateCell(entries, true)}</>)
    const ffMarkup = renderToStaticMarkup(<>{sectionRateCell(entries, false)}</>)

    expect(sellerMarkup).toContain('разные')
    expect(ffMarkup).toContain('разные')
    expect(sellerMarkup).not.toContain('aria-label="Документы раздела прошли по разным ставкам"')
    expect(ffMarkup).toContain('aria-label="Документы раздела прошли по разным ставкам"')
  })
})

describe('WMS-549 FfBillingInvoicesPanel seller scope', () => {
  it('drops the seller filter and the seller column', () => {
    const markup = renderToStaticMarkup(<FfBillingInvoicesPanel token="seller-token" sellerScope />)

    expect(markup).not.toContain('data-testid="billing-seller"')
    expect(markup).not.toContain('>Селлер<')
    expect(markup).toContain('>Статус<')
  })

  it('keeps the seller filter and column for FF by default', () => {
    const markup = renderToStaticMarkup(
      <FfBillingInvoicesPanel token="ff-token" sellers={[{ id: 'seller-1', name: 'Ромашка' }]} />,
    )

    expect(markup).toContain('data-testid="billing-seller"')
    expect(markup).toContain('>Селлер<')
  })
})
