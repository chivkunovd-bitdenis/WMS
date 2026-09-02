import { StrictMode, useEffect } from 'react'
import { createRoot } from 'react-dom/client'
import { MemoryRouter } from 'react-router-dom'
import { CssBaseline, ThemeProvider } from '@mui/material'

import { muiTheme } from '../../mui/theme'
import { AuthedAppLayout } from '../../layouts/AuthedAppLayout'
import { FfBillingScreen } from './FfBillingScreen'
import '../../index.css'

// Полный макет экрана «Расчёты» на подставных данных.
//
// Это не отдельная страница-рисунок: рендерится настоящий экран внутри
// настоящего шелла портала — левое меню, шапка, вкладки, фильтры, плашки,
// кнопка «Выставить счёт». Подменён только сервер: `fetch` отвечает выдуманным
// отчётом. Поэтому макет показывает ровно то, что увидит оператор вживую.

const SELLERS = [
  { id: 'seller-1', name: 'Ромашка' },
  { id: 'seller-2', name: 'Северный ветер' },
  { id: 'seller-3', name: 'Луна Трейд' },
]

const SUMMARY = {
  rows: [
    {
      seller_id: 'seller-1',
      seller_name: 'Ромашка',
      operation_count: 24,
      item_quantity: 2745,
      not_billable_count: 2,
      details_target: '',
      unpriced_count: 0,
      net_total_kopecks: 913500,
    },
    {
      seller_id: 'seller-2',
      seller_name: 'Северный ветер',
      operation_count: 11,
      item_quantity: 860,
      not_billable_count: 0,
      details_target: '',
      unpriced_count: 3,
      net_total_kopecks: 264000,
    },
    {
      seller_id: 'seller-3',
      seller_name: 'Луна Трейд',
      operation_count: 6,
      item_quantity: 410,
      not_billable_count: 1,
      details_target: '',
      unpriced_count: 0,
      net_total_kopecks: 118000,
    },
  ],
  totals: {
    seller_count: 3,
    operation_count: 41,
    item_quantity: 4015,
    not_billable_count: 3,
    net_total_kopecks: 1295500,
  },
}

type StubEntry = {
  id: string
  service: string
  number: string
  quantity: number
  rate: number
  day: number
  invoiced?: number
}

const ENTRIES: Record<string, StubEntry[]> = {
  'seller-1': [
    { id: 'in-1', service: 'inbound', number: 'Приёмка № 000045', quantity: 1480, rate: 300, day: 12, invoiced: 1 },
    { id: 'in-2', service: 'inbound', number: 'Приёмка № 000046', quantity: 320, rate: 300, day: 14 },
    { id: 'pack-1', service: 'packing', number: 'Упаковка № 000031', quantity: 640, rate: 500, day: 18 },
    { id: 'pack-2', service: 'packing', number: 'Упаковка № 000032', quantity: 45, rate: 700, day: 19 },
    { id: 'out-1', service: 'marketplace_outbound', number: 'Отгрузка № 000012', quantity: 820, rate: 300, day: 21 },
    { id: 'out-2', service: 'marketplace_outbound', number: 'Отгрузка № 000014', quantity: 260, rate: 300, day: 26 },
    { id: 'ret-1', service: 'return', number: 'Возврат № 000004', quantity: 18, rate: 400, day: 27 },
  ],
  'seller-2': [
    { id: 'in-3', service: 'inbound', number: 'Приёмка № 000041', quantity: 560, rate: 300, day: 9 },
    { id: 'out-3', service: 'marketplace_outbound', number: 'Отгрузка № 000009', quantity: 300, rate: 300, day: 16 },
  ],
  'seller-3': [
    { id: 'in-4', service: 'inbound', number: 'Приёмка № 000038', quantity: 410, rate: 300, day: 11 },
  ],
}

function detailsFor(sellerId: string) {
  const seller = SELLERS.find((row) => row.id === sellerId)
  return {
    seller_id: sellerId,
    seller_name: seller?.name ?? 'Селлер',
    entries: (ENTRIES[sellerId] ?? []).map((row) => ({
      id: row.id,
      kind: 'operation_fact' as const,
      occurred_at: `2026-08-${String(row.day).padStart(2, '0')}T09:30:00Z`,
      service_code: row.service,
      item_quantity: row.quantity,
      source_type: row.service === 'inbound' ? 'inbound_intake' : 'marketplace_unload',
      source_id: row.id,
      source_target: { kind: 'route' as const, to: '#' },
      document_number: row.number,
      product_name: null,
      sku: null,
      result: 'completed' as const,
      unit: 'item',
      rate_kopecks: row.rate,
      amount_kopecks: row.rate * row.quantity,
      billing_ledger_entry_id: `ledger-${row.id}`,
      invoice_history: { state: 'known' as const, count: row.invoiced ?? 0 },
    })),
    storage_row: {
      kind: 'storage' as const,
      date_from: '2026-08-01',
      date_to: '2026-08-31',
      liter_days: 1240,
      status: 'calculated' as const,
      amount_kopecks: 62000,
      calculation_token: 'preview-token',
    },
    next_cursor: null,
  }
}

// Счёт в макете тоже должен быть настоящим: пустое окно по кнопке «Выставить
// счёт» ничего не показывает про то, как экран работает.
const INVOICE_PREVIEW = {
  id: 'invoice-preview',
  seller_id: 'seller-1',
  number: 'СЧ-2026-000117',
  creation_mode: 'selected_operations' as const,
  period_start: '2026-08-01',
  period_end: '2026-08-31',
  status: 'issued' as const,
  issued_at: '2026-09-01T08:00:00Z',
  total_amount_kopecks: 913500,
  ff_profile: {
    legal_name: 'ООО «Короб ВМС»',
    inn: '7712345678',
    kpp: '771201001',
    bank_name: 'АО «Тинькофф Банк»',
    bik: '044525974',
    settlement_account: '40702810000000012345',
    correspondent_account: '30101810145250000974',
  },
  seller_profile: {
    legal_name: 'ООО «Ромашка»',
    inn: '5024998877',
    kpp: '502401001',
  },
  lines: [
    { id: 'l1', description: 'Приёмка товара, 1 800 шт.', unit_price_kopecks: 300, total_amount_kopecks: 540000, sort_order: 0 },
    { id: 'l2', description: 'Упаковка, 685 шт.', unit_price_kopecks: null, total_amount_kopecks: 351500, sort_order: 1 },
    { id: 'l3', description: 'Хранение за август, 1 240 л·дн', unit_price_kopecks: 50, total_amount_kopecks: 62000, sort_order: 2 },
  ],
}

function stubResponse(url: string): unknown {
  if (url.includes('/billing/seller-report/summary')) return SUMMARY
  const details = /\/billing\/seller-report\/sellers\/([^/?]+)\/details/.exec(url)
  if (details) return detailsFor(details[1] ?? 'seller-1')
  if (url.includes('/billing/invoices-v2')) return INVOICE_PREVIEW
  if (url.includes('/billing/invoices')) return { items: [], next_cursor: null }
  if (url.includes('/notifications')) return { items: [], unread_count: 0 }
  return {}
}

function installStubServer() {
  window.fetch = ((input: RequestInfo | URL) => {
    const url = typeof input === 'string' ? input : input instanceof URL ? input.href : input.url
    return Promise.resolve(
      new Response(JSON.stringify(stubResponse(url)), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      }),
    )
  }) as typeof window.fetch
}

// Раскрыть надо ровно один раз за загрузку страницы: StrictMode прогоняет
// эффект дважды, и второй клик сложил бы селлера обратно.
let autoExpanded = false

export function BillingScreenPreview() {
  // Селлер раскрывается сам: макет должен показывать разделы, а не пустую
  // таблицу, в которую ещё надо догадаться ткнуть.
  useEffect(() => {
    if (autoExpanded) return
    let tries = 0
    const timer = window.setInterval(() => {
      tries += 1
      const toggle = document.querySelector<HTMLButtonElement>(
        '[data-testid^="billing-seller-summary-expand-"]',
      )
      if (toggle) {
        autoExpanded = true
        toggle.click()
        window.clearInterval(timer)
        // И сразу отмечаем раздел: с пустым выбором кнопка «Выставить счёт»
        // открывает пустую форму ручного счёта, и по макету не видно главного —
        // что счёт собирается из выбранных начислений.
        window.setTimeout(() => {
          const box = [...document.querySelectorAll<HTMLInputElement>('input[type="checkbox"]')].find(
            (input) =>
              input.closest('[data-testid]')?.getAttribute('data-testid') ===
              'billing-pick-section-inbound',
          )
          box?.click()
        }, 500)
        return
      }
      if (tries > 40) window.clearInterval(timer)
    }, 100)
    return () => window.clearInterval(timer)
  }, [])

  return (
    <ThemeProvider theme={muiTheme}>
      <CssBaseline />
      <MemoryRouter initialEntries={['/app/ff/billing']}>
        <AuthedAppLayout
          onLogout={() => undefined}
          portal="ff"
          meRole="fulfillment_admin"
          userLabel="staging-admin@example.com"
          userRoleLabel="администратор"
        >
          <FfBillingScreen token="preview" sellers={SELLERS} onOpenInbound={() => undefined} />
        </AuthedAppLayout>
      </MemoryRouter>
    </ThemeProvider>
  )
}

type RootHost = HTMLElement & { __previewRoot?: ReturnType<typeof createRoot> }

installStubServer()

const container = document.getElementById('root') as RootHost | null
if (container) {
  const root = container.__previewRoot ?? createRoot(container)
  container.__previewRoot = root
  root.render(
    <StrictMode>
      <BillingScreenPreview />
    </StrictMode>,
  )
}
