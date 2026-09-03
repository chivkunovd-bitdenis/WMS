import { useEffect, useRef, useState } from 'react'
import { Box, Stack, Tab, Tabs, Typography } from '@mui/material'
import {
  DataTable,
  ErrorNotice,
  FilterBar,
  formatMoney,
  MoneyCell,
  QtyCell,
  ScreenHeader,
  TextCell,
  MoscowDateRangeInput,
  ReportMetricStrip,
  SecondaryAction,
  SelectInput,
  ActionGroup,
} from '../../ui-kit'
import { buildInvoicePrintHtml as buildPrintDocument, type PrintProfile } from './invoicePrint'
import { FfBillingInvoiceCreate } from './FfBillingInvoiceCreate'
import { FfBillingSellerDetails, type SellerReportDetails } from './FfBillingSellerDetails'
import { FfBillingProfilesDialog } from './FfBillingProfilesDialog'
import { FbsSupplyHistoryDialog } from '../v2/FbsSupplyHistoryDialog'
import { FfBillingInvoicesPanel } from './FfBillingInvoicesPanel'

type Seller = { id: string; name: string }
type Props = { sellers?: Seller[]; token: string; onOpenInbound: (id: string) => void }
type ApiDecimal = number | string
type LedgerEntry = {
  id: string
  entry_type: 'charge' | 'reversal' | string
  occurred_at: string
  seller_name: string
  service_code: 'inbound' | 'marketplace_outbound' | 'storage_liter_day' | string
  source_type: string
  source_id: string
  document_number: string
  quantity: ApiDecimal
  unit: 'document' | 'item' | 'liter_day' | string
  rate: ApiDecimal | null
  amount: ApiDecimal | null
  performer_name: string | null
  problem: 'unpriced' | 'storage_period_not_closed' | null
}
type BillingProfileSnapshot = Record<string, string | null | undefined>
type Invoice = { id: string; number: string; period: string; seller_name: string; issued_at: string; total_amount: ApiDecimal; status: 'issued' | 'cancelled'; issues?: { seller_name: string; period: string; reason: string }[]; lines?: InvoiceLine[]; ff_profile?: BillingProfileSnapshot; seller_profile?: BillingProfileSnapshot }
type InvoiceLine = { id: string; service_code: string; unit: string; quantity: ApiDecimal; rate: ApiDecimal; amount: ApiDecimal; documents?: { date: string; number: string; quantity: ApiDecimal; amount: ApiDecimal }[] }
type SellerReportRow = { seller_id: string; seller_name: string; operation_count: number; item_quantity: number; not_billable_count: number; details_target: string; unpriced_count?: number; net_total_kopecks?: number }
type SellerReportSummary = { rows: SellerReportRow[]; totals: { seller_count: number; operation_count: number; item_quantity: number; not_billable_count: number; net_total_kopecks?: number; inbound_items?: number; packing_items?: number; outbound_items?: number; fbs_items?: number } }

export const STORAGE_SERVICE_CODE = 'storage_liter_day'
export const CANCEL_INVOICE_ERROR_MESSAGE = 'Отмена не подтверждена. Проверьте статус счёта перед повторной попыткой.'

const MOSCOW_TIME_ZONE = 'Europe/Moscow'

export function parseApiDecimal(value: ApiDecimal): number {
  return typeof value === 'number' ? value : Number(value)
}

export function joinVisibleParts(parts: Array<string | null | undefined>): string {
  return parts.map((part) => part?.trim()).filter(Boolean).join(' · ')
}

export function formatMoscowDate(value: string): string {
  return new Intl.DateTimeFormat('ru-RU', { timeZone: MOSCOW_TIME_ZONE }).format(new Date(value))
}

export function formatMoscowDateTime(value: string): string {
  return new Intl.DateTimeFormat('ru-RU', { timeZone: MOSCOW_TIME_ZONE, dateStyle: 'short', timeStyle: 'short' }).format(new Date(value))
}

export function buildLedgerSearchParams(month: string): URLSearchParams {
  return new URLSearchParams({ period: month })
}

export function sellerReportSearchParams(range: { start: string; end: string }, includeFinance: boolean, sellerId = 'all', search = ''): URLSearchParams {
  const params = new URLSearchParams({ date_from: range.start, date_to: range.end, include_finance: String(includeFinance) })
  if (sellerId !== 'all') params.set('seller_id', sellerId)
  if (search) params.set('search', search)
  return params
}

function moscowToday(): string {
  const parts = new Intl.DateTimeFormat('en-CA', { timeZone: MOSCOW_TIME_ZONE, year: 'numeric', month: '2-digit', day: '2-digit' }).formatToParts(new Date())
  return `${parts.find((part) => part.type === 'year')?.value}-${parts.find((part) => part.type === 'month')?.value}-${parts.find((part) => part.type === 'day')?.value}`
}

type SellerQuickPeriod = 'today' | 'seven_days' | 'thirty_days' | 'current_month' | 'previous_month'

function dateAtUtc(iso: string): Date { return new Date(`${iso}T00:00:00Z`) }
function asIsoDate(value: Date): string { return value.toISOString().slice(0, 10) }
function minusDays(iso: string, days: number): string {
  const value = dateAtUtc(iso)
  value.setUTCDate(value.getUTCDate() - days)
  return asIsoDate(value)
}

export function sellerQuickRange(period: SellerQuickPeriod, today = moscowToday()): { start: string; end: string } {
  const value = dateAtUtc(today)
  if (period === 'today') return { start: today, end: today }
  if (period === 'seven_days') return { start: minusDays(today, 6), end: today }
  if (period === 'thirty_days') return { start: minusDays(today, 29), end: today }
  if (period === 'current_month') return { start: `${today.slice(0, 8)}01`, end: today }
  value.setUTCDate(0)
  return { start: `${value.getUTCFullYear()}-${String(value.getUTCMonth() + 1).padStart(2, '0')}-01`, end: asIsoDate(value) }
}

type CancelInvoiceResult = { ok: true; status: Invoice['status'] } | { ok: false; message: string }

export async function cancelInvoiceRequest(invoiceId: string, token: string): Promise<CancelInvoiceResult> {
  try {
    const response = await fetch(`/api/billing/invoices/${invoiceId}/cancel`, { method: 'POST', headers: { Authorization: `Bearer ${token}` } })
    if (!response.ok) throw new Error('cancel')
    const data = await response.json() as { status: Invoice['status'] }
    return { ok: true, status: data.status }
  } catch {
    return { ok: false, message: CANCEL_INVOICE_ERROR_MESSAGE }
  }
}

type LedgerDocumentTarget = { kind: 'inbound'; sourceId: string } | { kind: 'route'; to: string }

export function ledgerDocumentTarget(entry: Pick<LedgerEntry, 'source_type' | 'source_id'>): LedgerDocumentTarget | null {
  if (entry.source_type === 'inbound_intake') {
    return { kind: 'inbound', sourceId: entry.source_id }
  }
  if (entry.source_type === 'marketplace_unload') {
    return { kind: 'route', to: `/app/ff/mp-shipments?open_mp=${encodeURIComponent(entry.source_id)}` }
  }
  return null
}

type BillingTab = 'charges' | 'invoices'
type BillingTabPeriods = Record<BillingTab, string>

function formatMonth(year: number, month: number): string {
  return `${year}-${String(month).padStart(2, '0')}`
}

function moscowYearMonth(date: Date): { year: number; month: number } {
  const values = new Intl.DateTimeFormat('en-US', {
    timeZone: MOSCOW_TIME_ZONE,
    year: 'numeric',
    month: '2-digit',
  }).formatToParts(date)
  const year = Number(values.find((part) => part.type === 'year')?.value)
  const month = Number(values.find((part) => part.type === 'month')?.value)
  return { year, month }
}

export function initialBillingTabPeriods(now = new Date()): BillingTabPeriods {
  const { year, month } = moscowYearMonth(now)
  const previousYear = month === 1 ? year - 1 : year
  const previousMonth = month === 1 ? 12 : month - 1
  return {
    charges: formatMonth(year, month),
    invoices: formatMonth(previousYear, previousMonth),
  }
}

export function updateBillingTabPeriod(periods: BillingTabPeriods, tab: BillingTab, period: string): BillingTabPeriods {
  return { ...periods, [tab]: period }
}

function formatPeriod(period: string): string {
  const [year, month] = period.split('-').map(Number)
  if (!year || !month) return period
  return new Intl.DateTimeFormat('ru-RU', { month: 'long', year: 'numeric' }).format(new Date(year, month - 1, 1))
}

const serviceLabels: Record<string, string> = {
  inbound: 'Приёмка',
  marketplace_outbound: 'Отгрузка',
  storage_liter_day: 'Хранение',
}
/** В счёте колонка «Ед.» узкая: длинные подписи рвутся на три строки. */
const printUnitLabels: Record<string, string> = { document: 'док.', item: 'шт.', liter_day: 'л·дн' }

export function buildInvoicePrintHtml(invoice: Invoice): string {
  // Вёрстка счёта одна на все окна и живёт в `invoicePrint.ts`. Здесь только
  // перевод старого счёта в её язык: у него есть количество и ставка, поэтому
  // в документе появляются колонки «Кол-во», «Ед.» и «Цена».
  const totalKopecks = Math.round(parseApiDecimal(invoice.total_amount))
  return buildPrintDocument({
    number: invoice.number,
    dateLabel: invoice.issued_at ? `от ${formatMoscowDate(invoice.issued_at)}` : '',
    periodLabel: formatPeriod(invoice.period),
    supplierName: 'Фулфилмент',
    payerName: invoice.seller_name,
    supplier: (invoice.ff_profile ?? {}) as PrintProfile,
    payer: (invoice.seller_profile ?? {}) as PrintProfile,
    lines: (invoice.lines ?? []).map((line) => ({
      description: serviceLabels[line.service_code] ?? line.service_code,
      quantity: parseApiDecimal(line.quantity).toLocaleString('ru-RU'),
      unit: printUnitLabels[line.unit] ?? '',
      price: formatMoney(line.rate),
      amount: formatMoney(line.amount),
    })),
    total: formatMoney(invoice.total_amount),
    totalKopecks,
  })
}

export function InvoiceDocumentDetails({ line, period }: { line: InvoiceLine; period: string }) {
  return <Stack data-testid="billing-invoice-documents" spacing={0.5}>{(line.documents ?? []).map((doc) => {
    const quantity = parseApiDecimal(doc.quantity)
    const money = formatMoney(doc.amount)
    const text = joinVisibleParts([
      formatMoscowDate(doc.date),
      line.service_code === STORAGE_SERVICE_CODE ? `Расчёт хранения за ${formatPeriod(period)}` : doc.number,
      Number.isFinite(quantity) ? quantity.toLocaleString('ru-RU') : null,
      money === '—' ? null : money,
    ])
    return <Typography key={`${doc.date}-${doc.number}`}>Исходный документ: {text}</Typography>
  })}</Stack>
}

export function FfBillingScreen({ sellers = [], token, onOpenInbound }: Props) {
  const [tab, setTab] = useState<BillingTab>('charges')
  const [sellerId, setSellerId] = useState('all')
  const search = ''
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(false)
  const today = moscowToday()
  const [reportRange, setReportRange] = useState({ start: today, end: today })
  // Финансы на «Расчётах» включены всегда. Переключатель прятал единственное,
  // ради чего экран открывают, — суммы; товародвижение живёт на своём экране,
  // и совмещать их в одной таблице отдельно решено не было.
  const includeFinance = true
  const [report, setReport] = useState<SellerReportSummary>({ rows: [], totals: { seller_count: 0, operation_count: 0, item_quantity: 0, not_billable_count: 0 } })
  const [selectedReportSeller, setSelectedReportSeller] = useState<string | null>(null)
  const [reportDetails, setReportDetails] = useState<SellerReportDetails | null>(null)
  const [detailsCursor, setDetailsCursor] = useState<string | null>(null)
  const [detailsLoading, setDetailsLoading] = useState(false)
  const [detailsError, setDetailsError] = useState(false)
  const [selectedRootIds, setSelectedRootIds] = useState<string[]>([])
  const [storageSelected, setStorageSelected] = useState(false)
  const [invoicesRefresh, setInvoicesRefresh] = useState(0)
  // История заказа FBS открывается прямо из расчётов: номер заказа и есть
  // ссылка на его документ.
  const [historySupplyId, setHistorySupplyId] = useState<string | null>(null)
  // Хранение приезжает отдельным запросом: его расчёт прокручивает движения
  // товара с начала времён, и ждать его вместе с таблицей оператор не должен.
  const [storageLiterDays, setStorageLiterDays] = useState<number | null>(null)
  const summaryRequestId = useRef(0)
  const detailsRequestId = useRef(0)
  const clearSellerReportDetails = () => {
    detailsRequestId.current += 1
    setSelectedRootIds([])
    setStorageSelected(false)
    setSelectedReportSeller(null)
    setReportDetails(null)
    setDetailsCursor(null)
    setDetailsLoading(false)
    setDetailsError(false)
  }

  useEffect(() => {
    if (tab !== 'charges') return
    const controller = new AbortController()
    const requestId = ++summaryRequestId.current
    let alive = true
    setLoading(true)
    setError(false)
    const params = sellerReportSearchParams(reportRange, includeFinance, sellerId, search)
    fetch(`/api/billing/seller-report/summary?${params}`, { headers: { Authorization: `Bearer ${token}` }, signal: controller.signal })
      .then((response) => {
        if (!response.ok) throw new Error('seller-report-summary')
        return response.json() as Promise<SellerReportSummary>
      })
      .then((data) => { if (alive && requestId === summaryRequestId.current) setReport(data) })
      .catch((reason: unknown) => { if (alive && requestId === summaryRequestId.current && (reason as Error).name !== 'AbortError') setError(true) })
      .finally(() => { if (alive && requestId === summaryRequestId.current) setLoading(false) })
    return () => { alive = false; controller.abort() }
  }, [includeFinance, reportRange, search, sellerId, tab, token])

  useEffect(() => {
    if (tab !== 'charges') return
    const controller = new AbortController()
    let alive = true
    setStorageLiterDays(null)
    const params = new URLSearchParams({ date_from: reportRange.start, date_to: reportRange.end })
    if (sellerId !== 'all') params.set('seller_id', sellerId)
    fetch(`/api/billing/seller-report/storage-total?${params}`, { headers: { Authorization: `Bearer ${token}` }, signal: controller.signal })
      .then((response) => { if (!response.ok) throw new Error('storage-total'); return response.json() as Promise<{ liter_days: number }> })
      .then((data) => { if (alive) setStorageLiterDays(Math.round(data.liter_days)) })
      .catch(() => undefined)
    return () => { alive = false; controller.abort() }
  }, [reportRange, sellerId, tab, token])

  useEffect(() => {
    if (tab !== 'charges' || !selectedReportSeller) return
    const controller = new AbortController()
    const requestId = ++detailsRequestId.current
    let alive = true
    setDetailsLoading(true); setDetailsError(false)
    const params = sellerReportSearchParams(reportRange, includeFinance)
    if (detailsCursor) params.set('cursor', detailsCursor)
    fetch(`/api/billing/seller-report/sellers/${selectedReportSeller}/details?${params}`, { headers: { Authorization: `Bearer ${token}` }, signal: controller.signal })
      .then((response) => { if (!response.ok) throw new Error('seller-report-details'); return response.json() as Promise<SellerReportDetails> })
      .then((data) => { if (alive && requestId === detailsRequestId.current) setReportDetails((current) => {
        if (!detailsCursor) return data
        const existing = new Set((current?.entries ?? []).map((entry) => entry.id))
        return {
          ...data,
          entries: [...(current?.entries ?? []), ...data.entries.filter((entry) => !existing.has(entry.id))],
          storage_row: current?.storage_row ?? data.storage_row,
        }
      }) })
      .catch((reason: unknown) => { if (alive && requestId === detailsRequestId.current && (reason as Error).name !== 'AbortError') setDetailsError(true) })
      .finally(() => { if (alive && requestId === detailsRequestId.current) setDetailsLoading(false) })
    return () => { alive = false; controller.abort() }
  }, [detailsCursor, includeFinance, reportRange, selectedReportSeller, tab, token])


  const sellerColumns = [
    { key: 'seller', header: 'Селлер', width: 220, render: (row: SellerReportRow) => <TextCell value={row.seller_name} width={200} /> },
    { key: 'operations', header: 'Документов', width: 110, align: 'right' as const, render: (row: SellerReportRow) => <QtyCell value={row.operation_count} /> },
    { key: 'items', header: 'Штук', width: 100, align: 'right' as const, render: (row: SellerReportRow) => <QtyCell value={row.item_quantity} /> },
    // Деньги стоят раньше счётчиков проблем намеренно: на 1280 таблица не
    // помещается в карточку целиком, и вправо должно уезжать то, что смотрят
    // реже, а не сумма, ради которой экран и открывают.
    ...(includeFinance ? [{ key: 'accrued', header: 'Стоимость услуг', width: 150, align: 'right' as const, render: (row: SellerReportRow) => <MoneyCell minor={row.net_total_kopecks ?? null} /> }] : []),
    { key: 'notBillable', header: 'Не тарифицируется', width: 140, align: 'right' as const, render: (row: SellerReportRow) => <QtyCell value={row.not_billable_count} /> },
    ...(includeFinance ? [{ key: 'unpriced', header: 'Нет ставки', width: 105, align: 'right' as const, render: (row: SellerReportRow) => <QtyCell value={row.unpriced_count ?? 0} /> }] : []),
  ]
  const toggleRoot = (rootId: string, checked: boolean) => setSelectedRootIds((ids) => checked ? [...new Set([...ids, rootId])] : ids.filter((id) => id !== rootId))

  return <Box data-testid="ff-billing-screen" sx={{ width: '100%', maxWidth: '100%', minWidth: 0, overflowX: 'hidden' }}>
    <ScreenHeader title="Расчёты" purpose="Начисления за работу склада и счета селлерам за выбранный период." />
    <Tabs value={tab} onChange={(_, value: BillingTab) => setTab(value)} aria-label="Расчёты">
      <Tab label="Селлеры" value="charges" data-testid="billing-tab-sellers" /><Tab label="Выставленные счета" value="invoices" data-testid="billing-tab-invoices" />
    </Tabs>
    {tab === 'charges' ? <FilterBar testId="billing-filter-bar">
      <><MoscowDateRangeInput label="Период" startLabel="с" endLabel="по" value={reportRange} onChange={(value) => { clearSellerReportDetails(); setReportRange({ start: value.start ?? today, end: value.end ?? today }) }} maxDate={today} maxDays={366} testId="billing-seller-range" /><Stack direction="row" spacing={0.5} sx={{ flexWrap: 'wrap', alignSelf: { sm: 'flex-end' }, pb: { sm: 0.25 } }} aria-label="Быстрый период">{([['today', 'Сегодня'], ['seven_days', '7 дней'], ['thirty_days', '30 дней'], ['current_month', 'Этот месяц'], ['previous_month', 'Прошлый месяц']] as Array<[SellerQuickPeriod, string]>).map(([period, label]) => <SecondaryAction key={period} onClick={() => { clearSellerReportDetails(); setReportRange(sellerQuickRange(period, today)) }}>{label}</SecondaryAction>)}</Stack></>
      <SelectInput label="Селлер" value={sellerId} onChange={(value) => { clearSellerReportDetails(); setSellerId(value) }} options={[{ value: 'all', label: 'Все селлеры' }, ...sellers.map((seller) => ({ value: seller.id, label: seller.name }))]} testId="billing-seller" />
    </FilterBar> : null}
    {tab === 'charges' ? <>{error ? <ErrorNotice testId="billing-seller-report-error">Не удалось загрузить отчёт по селлерам. Повторите попытку</ErrorNotice> : null}<ReportMetricStrip items={[{ key: 'sellers', label: 'Селлеров', value: report.totals.seller_count }, { key: 'inbound', label: 'Принято', value: report.totals.inbound_items ?? 0 }, { key: 'packing', label: 'Упаковано', value: report.totals.packing_items ?? 0 }, { key: 'outbound', label: 'Отгружено ФБО', value: report.totals.outbound_items ?? 0 }, { key: 'fbs', label: 'Отгружено FBS', value: report.totals.fbs_items ?? 0 }, { key: 'storage', label: 'Хранение', value: storageLiterDays, unit: 'л·дн', nullValueLabel: 'Считается' }, ...(includeFinance ? [{ key: 'accrued', label: 'Стоимость услуг', moneyMinor: report.totals.net_total_kopecks ?? 0 }] : [])]} loading={loading} testId="billing-seller-metrics" /><ActionGroup><FfBillingProfilesDialog token={token} sellers={sellers} />{includeFinance ? <FfBillingInvoiceCreate token={token} sellers={sellers} sellerId={selectedReportSeller} sellerName={reportDetails?.seller_name ?? ''} dateFrom={reportRange.start} dateTo={reportRange.end} selectedRootIds={selectedRootIds} storageToken={storageSelected ? reportDetails?.storage_row?.calculation_token ?? null : null} onIssued={() => { setSelectedRootIds([]); setStorageSelected(false); setInvoicesRefresh((value) => value + 1) }} /> : null}</ActionGroup><DataTable columns={sellerColumns} rows={report.rows} loading={loading} getRowKey={(row) => row.seller_id} testId="billing-seller-summary" empty={{ title: 'За выбранный период документов нет', hint: 'Измените период или фильтр селлера.' }} expand={{ isExpanded: (row) => row.seller_id === selectedReportSeller, label: (row) => `Показать документы селлера ${row.seller_name}`, onToggle: (row) => { if (row.seller_id === selectedReportSeller) { clearSellerReportDetails(); return } clearSellerReportDetails(); setSelectedReportSeller(row.seller_id) }, render: () => <FfBillingSellerDetails details={reportDetails} loading={detailsLoading} error={detailsError} includeFinance={includeFinance} selectedRootIds={selectedRootIds} onToggleRoot={toggleRoot} storageSelected={storageSelected} onToggleStorage={setStorageSelected} onLoadMore={setDetailsCursor} onOpenInbound={onOpenInbound} onOpenFbsOrder={setHistorySupplyId} /> }} /></> : <FfBillingInvoicesPanel token={token} sellers={sellers} refreshToken={invoicesRefresh} />}
    <FbsSupplyHistoryDialog token={token} supplyId={historySupplyId} open={Boolean(historySupplyId)} onClose={() => setHistorySupplyId(null)} />
  </Box>
}
