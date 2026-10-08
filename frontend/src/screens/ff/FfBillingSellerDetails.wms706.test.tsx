// @vitest-environment jsdom
import { act } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, beforeAll, beforeEach, describe, expect, it } from 'vitest'

import {
  billableIds,
  FfBillingSellerDetails,
  invoiceSelectionKey,
  selectionReason,
  type SellerReportDetails,
  type SellerReportEntry,
} from './FfBillingSellerDetails'

// WMS-706: заказ FBS в работе в документах селлера. Контракт для разработки:
// строка заказа в работе несёт признак in_work = true, и на экране это даёт пометку
// «(в работе)» после номера, колонку «В работе» сразу после «Штук» и галочку по
// каждой услуге отдельно. Раздел «Выбрать весь раздел» такие строки не берёт.
// Признак in_work в типе SellerReportEntry ещё не объявлен, поэтому фикстуры
// собираются через функцию, которая его принимает.

beforeAll(() => {
  ;(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true
})

function entry(partial: Partial<SellerReportEntry> & { in_work?: boolean }): SellerReportEntry {
  return {
    id: 'row',
    kind: 'operation_fact',
    occurred_at: '2026-08-15T09:00:00Z',
    service_code: 'fbs_order',
    item_quantity: 1,
    source_type: 'fbs_order',
    source_id: 'order',
    source_target: { kind: 'fbs_order', source_id: 'order' },
    document_number: 'Заказ 1',
    product_name: 'Товар',
    sku: 'SKU',
    result: 'completed',
    ...partial,
  } as SellerReportEntry
}

const inWork = entry({
  id: 'work-fbs',
  source_id: 'order-work',
  document_number: 'Заказ 1001',
  item_quantity: 3,
  in_work: true,
  supply: { id: 'supply-1', number: 'Поставка 7' },
})

const handed = entry({
  id: 'handed-fbs',
  source_id: 'order-handed',
  source_target: { kind: 'fbs_order', source_id: 'order-handed' },
  document_number: 'Заказ 1002',
  item_quantity: 2,
  rate_kopecks: 1000,
  amount_kopecks: 2000,
  billing_ledger_entry_id: 'ledger-handed',
  fbs_status_label: 'Передан ВБ',
  invoice_history: { state: 'known', count: 0 },
})

const details: SellerReportDetails = {
  seller_id: 'seller-a',
  seller_name: 'Селлер А',
  entries: [inWork, handed],
  storage_row: null,
  next_cursor: null,
}

let host: HTMLDivElement
let root: Root

beforeEach(() => {
  host = document.createElement('div')
  document.body.append(host)
  root = createRoot(host)
})

afterEach(async () => {
  await act(async () => root.unmount())
  host.remove()
})

async function render({ sellerScope = false }: { sellerScope?: boolean }) {
  await act(async () => {
    root.render(
      <MemoryRouter>
        <FfBillingSellerDetails
          details={details}
          loading={false}
          error={false}
          includeFinance
          sellerScope={sellerScope}
          selectedRootIds={[]}
          onToggleRoot={() => {}}
          storageSelected={false}
          onToggleStorage={() => {}}
          onLoadMore={() => {}}
          onOpenInbound={() => {}}
          onOpenFbsOrder={() => {}}
        />
      </MemoryRouter>,
    )
  })
}

async function openFbsDocuments(): Promise<HTMLElement> {
  await act(async () => {
    ;(host.querySelector('[data-testid="billing-seller-sections-expand-fbs"]') as HTMLElement).click()
  })
  const table = host.querySelector('[data-testid="billing-seller-entries-fbs"]') as HTMLElement | null
  expect(table, 'раздел FBS должен раскрываться в таблицу документов').not.toBeNull()
  return table as HTMLElement
}

function rowWith(table: HTMLElement, text: string): HTMLTableRowElement | undefined {
  return [...table.querySelectorAll('tbody tr')].find((tr) => tr.textContent?.includes(text)) as
    | HTMLTableRowElement
    | undefined
}

function headersOf(table: HTMLElement): string[] {
  return [...table.querySelectorAll('thead th')].map((th) => th.textContent?.trim() ?? '')
}

describe('WMS-706 · пометка «(в работе)» у номера заказа', () => {
  it('C2: номер заказа в работе помечен в скобках, плашки статуса у него нет, номер остаётся ссылкой', async () => {
    await render({})
    const table = await openFbsDocuments()
    expect(table.textContent ?? '').toMatch(/Заказ 1001\s*\(в работе\)/)
    expect(table.textContent ?? '').not.toMatch(/Заказ 1002\s*\(в работе\)/)
    const workRow = rowWith(table, 'Заказ 1001')
    expect(workRow, 'строка заказа в работе должна быть в таблице').toBeDefined()
    expect(workRow?.textContent ?? '', 'у заказа в работе плашки «Передан ВБ» быть не должно').not.toContain('Передан ВБ')
    expect(workRow?.querySelector('button')?.textContent ?? '', 'номер заказа в работе остаётся ссылкой').toContain('Заказ 1001')
    const handedRow = rowWith(table, 'Заказ 1002')
    expect(handedRow?.textContent ?? '', 'переданный заказ сохраняет плашку «Передан ВБ»').toContain('Передан ВБ')
  })
})

describe('WMS-706 · колонка «В работе»', () => {
  it('C3: колонка стоит сразу после «Штук»: штуки заказа в работе, у остальных строк пусто', async () => {
    await render({})
    const table = await openFbsDocuments()
    const headers = headersOf(table)
    const quantityAt = headers.indexOf('Штук')
    expect(quantityAt, `колонка «Штук» должна остаться: ${headers.join(' | ')}`).toBeGreaterThanOrEqual(0)
    expect(
      headers[quantityAt + 1],
      `колонка «В работе» должна стоять сразу после «Штук»; заголовки: ${headers.join(' | ')}`,
    ).toBe('В работе')
    const cellOf = (text: string, column: number) =>
      rowWith(table, text)?.querySelectorAll('td')[column]?.textContent?.trim() ?? ''
    expect(cellOf('Заказ 1001', quantityAt + 1), 'в колонке «В работе» заказа в работе стоят его штуки').toBe('3')
    expect(cellOf('Заказ 1002', quantityAt + 1), 'в колонке «В работе» переданного заказа должно быть пусто').not.toMatch(/\d/)
  })

  it('C7: у строки в работе пусты ставка и сумма', async () => {
    await render({})
    const table = await openFbsDocuments()
    const headers = headersOf(table)
    const workRow = rowWith(table, 'Заказ 1001')
    const cellOf = (name: string) => workRow?.querySelectorAll('td')[headers.indexOf(name)]?.textContent ?? ''
    expect(cellOf('Ставка'), 'ставка строки в работе до счёта должна быть пустой').not.toMatch(/\d/)
    expect(cellOf('Сумма'), 'сумма строки в работе до счёта должна быть пустой').not.toMatch(/\d/)
  })
})

describe('WMS-706 · выбор в счёт', () => {
  it('C9: строка в работе выбирается по своей галочке, но «Выбрать весь раздел» её не берёт', () => {
    expect(selectionReason(inWork), 'галочка строки в работе должна быть доступна').toBeUndefined()
    expect(invoiceSelectionKey(inWork)).toBe('source:fbs_order:order-work:fbs_order')
    expect(billableIds([inWork, handed]), '«Выбрать весь раздел» выбирает только строки не в работе').toEqual([
      'ledger-handed',
    ])
  })
})

describe('WMS-706 · кабинет селлера не меняется', () => {
  it('C19: в кабинете селлера нет пометки «(в работе)» и колонки «В работе»', async () => {
    await render({ sellerScope: true })
    const table = await openFbsDocuments()
    expect(table.textContent ?? '', 'в кабинете селлера пометки быть не должно').not.toMatch(/\(в работе\)/)
    expect(headersOf(table), 'в кабинете селлера колонки «В работе» быть не должно').not.toContain('В работе')
  })
})
