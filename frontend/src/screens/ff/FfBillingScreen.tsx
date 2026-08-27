import { useEffect, useRef, useState } from 'react'
import { Link as RouterLink } from 'react-router-dom'
import { Box, Dialog, DialogActions, DialogContent, DialogTitle, Link, MenuItem, Select, Stack, Tab, Tabs, Typography } from '@mui/material'
import ExpandMore from '@mui/icons-material/ExpandMore'
import {
  DataTable,
  ErrorNotice,
  FilterBar,
  formatMoney,
  MoneyCell,
  PeriodPicker,
  PrimaryAction,
  QtyCell,
  ScreenHeader,
  StatusChip,
  TextCell,
  DangerAction,
  IconAction,
  MoscowDateRangeInput,
  PreferenceSwitch,
  PrintAction,
  ReportMetricStrip,
  SecondaryAction,
  SelectInput,
} from '../../ui-kit'

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
type InvoiceIssue = { id?: string; seller_id?: string; seller_name: string; period: string; reason: string; message?: string }
type BillingListResponse<T> = { entries?: T[]; invoices?: T[]; rows?: T[]; issues?: InvoiceIssue[] }
type SellerReportRow = { seller_id: string; seller_name: string; operation_count: number; item_quantity: number; not_billable_count: number; details_target: string; unpriced_count?: number; net_total_kopecks?: number }
type SellerReportEntry = { id: string; kind: 'operation_fact' | 'legacy_billing'; occurred_at: string; service_code: string; item_quantity: number | null; source_type: string; source_id: string; source_target: { kind: 'inbound'; source_id: string } | { kind: 'route'; to: string } | null; document_number: string | null; product_name: string | null; sku: string | null; result: 'completed' | 'reversed' | 'not_billable' | 'unpriced'; unit?: string | null; rate_kopecks?: number | null; amount_kopecks?: number | null; billing_ledger_entry_id?: string; invoice_history?: { state: 'known'; count: number } | { state: 'unknown' } }
type StorageReportRow = { kind: 'storage'; date_from: string; date_to: string; liter_days: number; status: 'calculated' | 'missing_dimensions'; amount_kopecks?: number; calculation_token: string }
type SellerReportSummary = { rows: SellerReportRow[]; totals: { seller_count: number; operation_count: number; item_quantity: number; not_billable_count: number; net_total_kopecks?: number } }
type SellerReportDetails = { seller_id: string; seller_name: string; entries: SellerReportEntry[]; storage_row: StorageReportRow | null; next_cursor: string | null; totals: SellerReportSummary['totals'] }

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

function sellerFinanceStorageKey(token: string) {
  try {
    const payload = JSON.parse(atob(token.split('.')[1].replace(/-/g, '+').replace(/_/g, '/'))) as { tenant_id?: string; sub?: string }
    return `${payload.tenant_id ?? 'tenant'}:${payload.sub ?? 'user'}:billing:sellers:finance`
  } catch { return 'tenant:user:billing:sellers:finance' }
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

function escapeHtml(value: unknown): string {
  const entities: Record<string, string> = { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }
  return String(value ?? '').replace(/[&<>"']/g, (character) => entities[character] ?? character)
}

const serviceLabels: Record<string, string> = {
  inbound: 'Приёмка',
  marketplace_outbound: 'Отгрузка',
  storage_liter_day: 'Хранение',
}
const unitLabels: Record<string, string> = { document: 'За документ', item: 'За штуку', liter_day: 'За литр-день' }
const profileFieldLabels: Record<string, string> = {
  legal_name: 'Юридическое наименование',
  inn: 'ИНН',
  kpp: 'КПП',
  bank_name: 'Название банка',
  bik: 'БИК',
  settlement_account: 'Расчётный счёт',
  correspondent_account: 'Корреспондентский счёт',
}

function profileRows(profile: BillingProfileSnapshot | undefined, fallback: string): [string, string][] {
  const rows = Object.entries(profile ?? {})
    .filter(([key, value]) => Boolean(profileFieldLabels[key] && value))
    .map(([key, value]) => [profileFieldLabels[key], String(value)] as [string, string])
  return rows.length ? rows : [['Наименование', fallback]]
}

export function buildInvoicePrintHtml(invoice: Invoice): string {
  const profileHtml = (profile: BillingProfileSnapshot | undefined, fallback: string) => profileRows(profile, fallback)
    .map(([label, value]) => `<div><strong>${escapeHtml(label)}:</strong> ${escapeHtml(value)}</div>`)
    .join('')
  const lineHtml = (invoice.lines ?? []).map((line) => `<tr><td>${escapeHtml(serviceLabels[line.service_code] ?? '—')}</td><td>${escapeHtml(unitLabels[line.unit] ?? '—')}</td><td>${escapeHtml(parseApiDecimal(line.quantity).toLocaleString('ru-RU'))}</td><td>${escapeHtml(formatMoney(line.rate))}</td><td>${escapeHtml(formatMoney(line.amount))}</td></tr>`).join('')
  return `<!doctype html><html lang="ru"><head><meta charset="utf-8"><title>Счёт ${escapeHtml(invoice.number)}</title></head><body><h1>Счёт ${escapeHtml(invoice.number)}</h1><p>${escapeHtml(formatPeriod(invoice.period))} · выставлен ${escapeHtml(formatMoscowDate(invoice.issued_at))}</p><h3>Получатель</h3>${profileHtml(invoice.ff_profile, 'Реквизиты ФФ')}<h3>Плательщик</h3>${profileHtml(invoice.seller_profile, invoice.seller_name)}<table><thead><tr><th>Услуга</th><th>Расчёт</th><th>Количество</th><th>Ставка</th><th>Сумма</th></tr></thead><tbody>${lineHtml}</tbody></table><h2>Итого: ${escapeHtml(formatMoney(invoice.total_amount))}</h2></body></html>`
}

function responseRows<T>(payload: BillingListResponse<T> | T[], key: 'entries' | 'invoices'): T[] {
  if (Array.isArray(payload)) return payload
  return payload[key] ?? payload.rows ?? []
}

function invoiceIssueContext(sellerId: string, period: string): string {
  return `${sellerId}:${period}`
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
  const [months, setMonths] = useState(initialBillingTabPeriods)
  const month = months[tab]
  const setMonth = (period: string) => setMonths((periods) => updateBillingTabPeriod(periods, tab, period))
  const [sellerId, setSellerId] = useState('all')
  const [search, setSearch] = useState('')
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(false)
  const today = moscowToday()
  const [reportRange, setReportRange] = useState({ start: today, end: today })
  const financeStorageKey = sellerFinanceStorageKey(token)
  const [includeFinance, setIncludeFinance] = useState(() => localStorage.getItem(financeStorageKey) === 'true')
  const [report, setReport] = useState<SellerReportSummary>({ rows: [], totals: { seller_count: 0, operation_count: 0, item_quantity: 0, not_billable_count: 0 } })
  const [selectedReportSeller, setSelectedReportSeller] = useState<string | null>(null)
  const [reportDetails, setReportDetails] = useState<SellerReportDetails | null>(null)
  const [detailsCursor, setDetailsCursor] = useState<string | null>(null)
  const [detailsLoading, setDetailsLoading] = useState(false)
  const [detailsError, setDetailsError] = useState(false)
  const summaryRequestId = useRef(0)
  const detailsRequestId = useRef(0)
  const [invoices, setInvoices] = useState<Invoice[]>([])
  const [invoiceLoading, setInvoiceLoading] = useState(false)
  const [invoiceError, setInvoiceError] = useState(false)
  const [invoiceSearch, setInvoiceSearch] = useState('')
  const [invoiceStatus, setInvoiceStatus] = useState('all')
  const [invoiceIssues, setInvoiceIssues] = useState<InvoiceIssue[]>([])
  const [retryableIssueContexts, setRetryableIssueContexts] = useState<string[]>([])
  const [invoiceRefresh, setInvoiceRefresh] = useState(0)
  const [selectedInvoice, setSelectedInvoice] = useState<Invoice | null>(null)
  const [expandedLine, setExpandedLine] = useState<string | null>(null)
  const [cancelConfirm, setCancelConfirm] = useState(false)
  const [cancelling, setCancelling] = useState(false)
  const [cancelError, setCancelError] = useState<string | null>(null)
  const [forming, setForming] = useState(false)
  const expandedInvoiceLine = selectedInvoice?.lines?.find((line) => line.id === expandedLine)
  const clearSellerReportDetails = () => {
    detailsRequestId.current += 1
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

  useEffect(() => { localStorage.setItem(financeStorageKey, String(includeFinance)) }, [financeStorageKey, includeFinance])

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

  useEffect(() => {
    if (tab !== 'invoices') return
    const controller = new AbortController()
    setInvoiceLoading(true); setInvoiceError(false)
    setInvoices([])
    setInvoiceIssues([])
    const params = new URLSearchParams({ period: month, seller_id: sellerId, status: invoiceStatus })
    if (invoiceSearch) params.set('number', invoiceSearch)
    fetch(`/api/billing/invoices?${params}`, { headers: { Authorization: `Bearer ${token}` }, signal: controller.signal })
      .then((response) => { if (!response.ok) throw new Error('billing-invoices'); return response.json() as Promise<BillingListResponse<Invoice> | Invoice[]> })
      .then((data) => {
        const nextInvoices = responseRows(data, 'invoices')
        const nextIssues = Array.isArray(data) ? [] : data.issues ?? []
        setInvoices(nextInvoices)
        setInvoiceIssues(nextIssues)
        setRetryableIssueContexts((contexts) => {
          const issueContexts = nextIssues
            .filter((issue) => Boolean(issue.seller_id))
            .map((issue) => invoiceIssueContext(issue.seller_id!, issue.period))
          const currentContext = sellerId === 'all' ? null : invoiceIssueContext(sellerId, month)
          const retained = currentContext && nextInvoices.length ? contexts.filter((context) => context !== currentContext) : contexts
          return [...new Set([...retained, ...issueContexts])]
        })
      })
      .catch((reason: unknown) => { if ((reason as Error).name !== 'AbortError') setInvoiceError(true) })
      .finally(() => setInvoiceLoading(false))
    return () => controller.abort()
  }, [invoiceRefresh, invoiceSearch, invoiceStatus, month, sellerId, tab, token])

  const hasUnknownInvoiceLineCodes = selectedInvoice?.lines?.some((line) => serviceLabels[line.service_code] === undefined || unitLabels[line.unit] === undefined) ?? false
  const selectedInvoiceContext = sellerId === 'all' ? null : invoiceIssueContext(sellerId, month)
  const canRetryFormation = Boolean(
    selectedInvoiceContext
    && retryableIssueContexts.includes(selectedInvoiceContext)
    && !invoiceIssues.length
    && !invoices.length
    && !invoiceSearch
    && invoiceStatus === 'all',
  )
  const invoiceColumns = [
    { key: 'number', header: 'Номер', width: 170, render: (row: Invoice) => <TextCell value={row.number} /> },
    { key: 'period', header: 'Период', width: 150, render: (row: Invoice) => <TextCell value={formatPeriod(row.period)} /> },
    { key: 'seller', header: 'Селлер', width: 220, render: (row: Invoice) => <TextCell value={row.seller_name} /> },
    { key: 'issued', header: 'Выставлен', width: 150, render: (row: Invoice) => <TextCell value={formatMoscowDate(row.issued_at)} /> },
    { key: 'amount', header: 'Сумма', width: 160, align: 'right' as const, render: (row: Invoice) => <MoneyCell minor={row.total_amount} /> },
    { key: 'status', header: 'Статус', width: 140, render: (row: Invoice) => <StatusChip label={row.status === 'issued' ? 'Выставлен' : 'Отменён'} tone={row.status === 'issued' ? 'ok' : 'neutral'} /> },
    { key: 'action', header: 'Действие', width: 70, render: (row: Invoice) => <IconAction title="Открыть счёт" testId={`billing-invoice-open-${row.id}`} onClick={() => { setSelectedInvoice(row); setExpandedLine(null) }}><ExpandMore fontSize="small" /></IconAction> },
  ]
  const sellerColumns = [
    { key: 'seller', header: 'Селлер', width: 250, render: (row: SellerReportRow) => <TextCell value={row.seller_name} width={230} /> },
    { key: 'operations', header: 'Операций', width: 110, align: 'right' as const, render: (row: SellerReportRow) => <QtyCell value={row.operation_count} /> },
    { key: 'items', header: 'Штук', width: 100, align: 'right' as const, render: (row: SellerReportRow) => <QtyCell value={row.item_quantity} /> },
    { key: 'notBillable', header: 'Не тарифицируется', width: 160, align: 'right' as const, render: (row: SellerReportRow) => <QtyCell value={row.not_billable_count} /> },
    ...(includeFinance ? [{ key: 'unpriced', header: 'Нет ставки', width: 120, align: 'right' as const, render: (row: SellerReportRow) => <QtyCell value={row.unpriced_count ?? 0} /> }, { key: 'accrued', header: 'Начислено', width: 140, align: 'right' as const, render: (row: SellerReportRow) => <MoneyCell minor={row.net_total_kopecks ?? null} /> }] : []),
    { key: 'action', header: 'Действие', width: 170, render: (row: SellerReportRow) => <PrimaryAction onClick={() => { setSelectedReportSeller(row.seller_id); setDetailsCursor(null); setReportDetails(null) }}>Показать операции</PrimaryAction> },
  ]
  const sourceLabel = (row: SellerReportEntry) => joinVisibleParts([
    { inbound_intake: 'Приёмка', marketplace_unload: 'Разгрузка' }[row.source_type] ?? 'Документ',
    row.document_number,
  ]) || '—'
  const productLabel = (row: SellerReportEntry) => joinVisibleParts([row.product_name, row.sku]) || '—'
  const resultChip = (row: SellerReportEntry) => {
    const presentation = {
      completed: { label: 'Выполнено', tone: 'ok' as const },
      reversed: { label: 'Сторно', tone: 'neutral' as const },
      not_billable: { label: 'Не тарифицируется', tone: 'neutral' as const },
      unpriced: { label: 'Нет ставки', tone: 'warn' as const },
    }[row.result]
    return <StatusChip label={presentation.label} tone={presentation.tone} />
  }
  const reportEntryColumns = [
    { key: 'date', header: 'Дата и время', width: 180, render: (row: SellerReportEntry) => <TextCell value={formatMoscowDateTime(row.occurred_at)} /> },
    { key: 'document', header: 'Документ / источник', width: 190, render: (row: SellerReportEntry) => <TextCell value={sourceLabel(row)} /> },
    { key: 'service', header: 'Услуга', width: 150, render: (row: SellerReportEntry) => <TextCell value={serviceLabels[row.service_code] ?? '—'} /> },
    { key: 'product', header: 'Товар / SKU', width: 210, render: (row: SellerReportEntry) => <TextCell value={productLabel(row)} /> },
    { key: 'quantity', header: 'Штук', width: 90, align: 'right' as const, render: (row: SellerReportEntry) => <TextCell value={row.item_quantity == null ? '—' : String(row.item_quantity)} /> },
    { key: 'result', header: 'Результат', width: 170, render: resultChip },
    ...(includeFinance ? [{ key: 'unit', header: 'Единица', width: 110, render: (row: SellerReportEntry) => <TextCell value={row.unit ? (unitLabels[row.unit] ?? '—') : '—'} /> }, { key: 'rate', header: 'Ставка', width: 120, align: 'right' as const, render: (row: SellerReportEntry) => <MoneyCell minor={row.rate_kopecks ?? null} /> }, { key: 'amount', header: 'Сумма', width: 120, align: 'right' as const, render: (row: SellerReportEntry) => <MoneyCell minor={row.amount_kopecks ?? null} /> }, { key: 'invoice', header: 'Счёт выставлялся', width: 170, render: (row: SellerReportEntry) => row.invoice_history?.state === 'known' ? <TextCell value={row.invoice_history.count ? `✓ ${row.invoice_history.count}` : '—'} /> : <TextCell value="Нет данных о старом счёте" hint="Старые снимки счёта неполные или это новая операция" /> }] : []),
    { key: 'source', header: 'Источник', width: 160, render: (row: SellerReportEntry) => {
      const target = row.source_target
      if (target?.kind === 'inbound') return <Link component="button" type="button" onClick={() => onOpenInbound(target.source_id)}>Открыть документ</Link>
      if (target?.kind === 'route') return <Link component={RouterLink} to={target.to}>Открыть документ</Link>
      return <TextCell value="Недоступен" hint="Первоисточник недоступен или не поддерживает переход" />
    } },
  ]
  const issueLabels: Record<string, string> = {
    unpriced: 'Нет тарифа',
    missing_seller_profile: 'Нет реквизитов',
    missing_ff_profile: 'Нет реквизитов',
    storage_period_not_closed: 'Хранение не закрыто',
    billing_calculation_overflow: 'Начисление не рассчитано',
  }
  const issueAction = (issue: InvoiceIssue): { label: string; to: string } | null => {
    if (issue.reason === 'unpriced') return { label: 'Открыть тарифы', to: '/app/ff/settings?tab=tariffs' }
    if (issue.reason === 'missing_seller_profile' && issue.seller_id) {
      return { label: 'Открыть селлера', to: `/app/ff/sellers?seller_id=${encodeURIComponent(issue.seller_id)}` }
    }
    if (issue.reason === 'missing_ff_profile') return { label: 'Открыть настройки', to: '/app/ff/settings?tab=tariffs' }
    if (issue.reason === 'storage_period_not_closed') return { label: 'Открыть хранение', to: '/app/ff/inventory' }
    return null
  }
  const retryFormation = async () => {
    if (sellerId === 'all' || forming) return
    setForming(true)
    try {
      const response = await fetch(`/api/billing/invoices/${sellerId}/${month}/form`, { method: 'POST', headers: { Authorization: `Bearer ${token}` } })
      if (!response.ok) throw new Error('billing-form')
      const result = await response.json() as { status: string; reason?: string; message?: string }
      setInvoiceError(false)
      if (result.status === 'blocked' && result.reason) {
        setInvoiceIssues([{
          seller_id: sellerId,
          seller_name: sellers.find((seller) => seller.id === sellerId)?.name ?? 'Селлер',
          period: month,
          reason: result.reason,
          message: result.message,
        }])
      } else if (result.status === 'empty') {
        const context = invoiceIssueContext(sellerId, month)
        setRetryableIssueContexts((contexts) => contexts.filter((candidate) => candidate !== context))
      } else {
        setInvoiceRefresh((value) => value + 1)
      }
      setTab('invoices')
    } catch {
      setInvoiceError(true)
    } finally {
      setForming(false)
    }
  }
  const printInvoice = () => {
    if (!selectedInvoice) return
    const printWindow = window.open('', '_blank'); printWindow?.document.write(buildInvoicePrintHtml(selectedInvoice)); printWindow?.document.close(); printWindow?.print()
  }
  const cancelInvoice = async () => {
    if (!selectedInvoice || selectedInvoice.status !== 'issued' || cancelling) return
    setCancelling(true)
    setCancelError(null)
    try {
      const result = await cancelInvoiceRequest(selectedInvoice.id, token)
      if (!result.ok) {
        setCancelError(result.message)
        return
      }
      const updated = { ...selectedInvoice, status: result.status }
      setSelectedInvoice(updated)
      setInvoices((items) => items.map((item) => item.id === updated.id ? updated : item))
      setCancelConfirm(false)
    } finally {
      setCancelling(false)
    }
  }

  return <Box data-testid="ff-billing-screen" sx={{ width: 'calc(100vw - 308px)', minWidth: 0 }}>
    <ScreenHeader title="Расчёты" purpose="Начисления за работу склада и автоматически выставленные счета селлерам." />
    <Tabs value={tab} onChange={(_, value: BillingTab) => setTab(value)} aria-label="Расчёты">
      <Tab label="Селлеры" value="charges" data-testid="billing-tab-sellers" /><Tab label="Счета" value="invoices" data-testid="billing-tab-invoices" />
    </Tabs>
    <FilterBar search={tab === 'charges' ? search : invoiceSearch} onSearchChange={tab === 'charges' ? (value) => { clearSellerReportDetails(); setSearch(value) } : setInvoiceSearch} searchPlaceholder={tab === 'charges' ? 'Селлер' : 'Номер счёта'} testId="billing-filter-bar">
      {tab === 'charges' ? <><MoscowDateRangeInput label="Период" startLabel="С" endLabel="По" value={reportRange} onChange={(value) => { clearSellerReportDetails(); setReportRange({ start: value.start ?? today, end: value.end ?? today }) }} maxDate={today} maxDays={366} testId="billing-seller-range" /><Stack direction="row" spacing={0.5} sx={{ flexWrap: 'wrap' }} aria-label="Быстрый период">{([['today', 'Сегодня'], ['seven_days', '7 дней'], ['thirty_days', '30 дней'], ['current_month', 'Этот месяц'], ['previous_month', 'Прошлый месяц']] as Array<[SellerQuickPeriod, string]>).map(([period, label]) => <SecondaryAction key={period} onClick={() => { clearSellerReportDetails(); setReportRange(sellerQuickRange(period, today)) }}>{label}</SecondaryAction>)}</Stack><PreferenceSwitch label="Финансы" checked={includeFinance} onChange={(value) => { clearSellerReportDetails(); setIncludeFinance(value) }} testId="billing-seller-finance" /></> : <PeriodPicker value={month} onChange={setMonth} testId="billing-period" />}
      {tab === 'charges' ? <SelectInput label="Селлер" value={sellerId} onChange={(value) => { clearSellerReportDetails(); setSellerId(value) }} options={[{ value: 'all', label: 'Все селлеры' }, ...sellers.map((seller) => ({ value: seller.id, label: seller.name }))]} testId="billing-seller" /> : <Select size="small" value={sellerId} onChange={(event) => setSellerId(event.target.value)} inputProps={{ 'data-testid': 'billing-seller' }} sx={{ minWidth: 190 }} aria-label="Селлер"><MenuItem value="all">Все селлеры</MenuItem>{sellers.map((seller) => <MenuItem key={seller.id} value={seller.id}>{seller.name}</MenuItem>)}</Select>}
      {tab === 'invoices' ? <Select size="small" value={invoiceStatus} onChange={(event) => setInvoiceStatus(event.target.value)} inputProps={{ 'data-testid': 'billing-status' }} sx={{ minWidth: 160 }} aria-label="Статус"><MenuItem value="all">Все статусы</MenuItem><MenuItem value="issued">Выставлен</MenuItem><MenuItem value="cancelled">Отменён</MenuItem></Select> : null}
    </FilterBar>
    {tab === 'charges' ? <>{error ? <ErrorNotice testId="billing-seller-report-error">Не удалось загрузить отчёт по селлерам. Повторите попытку</ErrorNotice> : null}<ReportMetricStrip items={[{ key: 'sellers', label: 'Селлеров', value: report.totals.seller_count }, { key: 'operations', label: 'Операций', value: report.totals.operation_count }, { key: 'items', label: 'Штук', value: report.totals.item_quantity }, ...(includeFinance ? [{ key: 'accrued', label: 'Начислено', moneyMinor: report.totals.net_total_kopecks ?? 0 }] : [])]} loading={loading} testId="billing-seller-metrics" /><DataTable columns={sellerColumns} rows={report.rows} loading={loading} getRowKey={(row) => row.seller_id} testId="billing-seller-summary" empty={{ title: 'За выбранный период операций нет', hint: 'Измените период или фильтр селлера.' }} />{selectedReportSeller ? <Stack spacing={1} sx={{ mt: 3 }} data-testid="billing-seller-details"><Typography variant="h6">Операции селлера</Typography>{detailsError ? <ErrorNotice>Не удалось загрузить детализацию. Сводка сохранена.</ErrorNotice> : null}{reportDetails?.storage_row ? <DataTable columns={[{ key: 'storage', header: 'Услуга', width: 220, render: () => 'Хранение' }, { key: 'period', header: 'Период', width: 200, render: (row: StorageReportRow) => `${row.date_from} — ${row.date_to}` }, { key: 'literDays', header: 'Литро-дни', width: 130, align: 'right' as const, render: (row: StorageReportRow) => <TextCell value={String(row.liter_days)} /> }, ...(includeFinance ? [{ key: 'amount', header: 'Сумма', width: 130, align: 'right' as const, render: (row: StorageReportRow) => <MoneyCell minor={row.amount_kopecks ?? null} /> }] : []), { key: 'status', header: 'Статус', width: 180, render: (row: StorageReportRow) => row.status === 'missing_dimensions' ? <StatusChip label="Нет габаритов" tone="warn" hint="У товара нет габаритов для точного расчёта" /> : <StatusChip label="Рассчитано" tone="ok" /> }]} rows={[reportDetails.storage_row]} loading={detailsLoading} getRowKey={() => 'storage'} testId="billing-seller-storage" empty={{ title: 'Хранение не рассчитано' }} /> : null}<DataTable columns={reportEntryColumns} rows={reportDetails?.entries ?? []} loading={detailsLoading} getRowKey={(row) => row.id} testId="billing-seller-entries" empty={{ title: 'Операций нет' }} />{reportDetails?.next_cursor ? <SecondaryAction disabledReason={detailsLoading ? 'Загрузка операций' : undefined} onClick={() => setDetailsCursor(reportDetails.next_cursor)}>Загрузить ещё</SecondaryAction> : null}</Stack> : null}</> : <><>{invoiceError ? <ErrorNotice testId="billing-invoices-error">Не удалось загрузить счета. Повторите попытку</ErrorNotice> : null}</>{invoiceIssues.length ? <Stack spacing={1} sx={{ mb: 2 }} data-testid="billing-invoice-issues">{invoiceIssues.map((issue, index) => {
      const action = issueAction(issue)
      return <Stack key={`${issue.seller_name}-${issue.period}-${issue.reason}-${index}`} direction="row" spacing={1} sx={{ alignItems: 'center' }}><Typography>{issue.seller_name} · {issue.period}</Typography><StatusChip label={issueLabels[issue.reason] ?? 'Требуется исправление'} tone="stop" />{action ? <RouterLink to={action.to} data-testid={`billing-invoice-issue-action-${issue.id ?? index}`} style={{ textDecoration: 'none' }}><PrimaryAction>{action.label}</PrimaryAction></RouterLink> : null}</Stack>
    })}<PrimaryAction disabledReason="Сначала устраните причины, перечисленные выше" onClick={retryFormation}>{'Повторить формирование'}</PrimaryAction></Stack> : canRetryFormation && !invoiceLoading ? <Stack direction="row" spacing={1} sx={{ mb: 2 }}><Typography>Причины устранены — повторите формирование</Typography><PrimaryAction disabledReason={forming ? 'Формирование уже выполняется' : undefined} onClick={retryFormation}>Повторить формирование</PrimaryAction></Stack> : null}<DataTable columns={invoiceColumns} rows={invoices} loading={invoiceLoading} getRowKey={(row) => row.id} testId="billing-invoices-table" empty={{ title: 'За этот месяц счета не выставлены', hint: 'Нет начислений для формирования' }} /></>}
    <Dialog open={Boolean(selectedInvoice)} onClose={() => setSelectedInvoice(null)} maxWidth="lg" fullWidth aria-labelledby="billing-invoice-dialog-title"><DialogTitle id="billing-invoice-dialog-title">Счёт {selectedInvoice?.number} {selectedInvoice ? <StatusChip label={selectedInvoice.status === 'issued' ? 'Выставлен' : 'Отменён'} tone={selectedInvoice.status === 'issued' ? 'ok' : 'neutral'} /> : null}</DialogTitle><DialogContent dividers>{selectedInvoice ? <Stack spacing={2}><Typography>Период: {formatPeriod(selectedInvoice.period)} · Выставлен: {formatMoscowDate(selectedInvoice.issued_at)}</Typography><Stack direction="row" spacing={2}>{([['Получатель', selectedInvoice.ff_profile, 'Реквизиты ФФ'], ['Плательщик', selectedInvoice.seller_profile, selectedInvoice.seller_name]] as const).map(([title, profile, fallback]) => <Box sx={{ flex: 1 }} key={title}><Typography sx={{ fontWeight: 'bold' }}>{title}</Typography>{profileRows(profile, fallback).map(([label, value]) => <Typography key={label}>{label}: {value}</Typography>)}</Box>)}</Stack>{hasUnknownInvoiceLineCodes ? <ErrorNotice testId="billing-invoice-data-error">В счёте есть строка с нераспознанной услугой или расчётом. Проверьте данные перед печатью</ErrorNotice> : null}<DataTable columns={[{ key: 'service', header: 'Услуга', width: 180, render: (line: InvoiceLine) => serviceLabels[line.service_code] ?? '—' }, { key: 'unit', header: 'Расчёт', width: 170, render: (line: InvoiceLine) => unitLabels[line.unit] ?? '—' }, { key: 'qty', header: 'Количество', width: 120, align: 'right', render: (line: InvoiceLine) => <QtyCell value={parseApiDecimal(line.quantity)} /> }, { key: 'rate', header: 'Ставка', width: 130, align: 'right', render: (line: InvoiceLine) => <MoneyCell minor={line.rate} /> }, { key: 'amount', header: 'Сумма', width: 140, align: 'right', render: (line: InvoiceLine) => <MoneyCell minor={line.amount} /> }, { key: 'details', header: 'Детализация', width: 70, align: 'center', render: (line: InvoiceLine) => <IconAction title="Показать документы" onClick={() => setExpandedLine(expandedLine === line.id ? null : line.id)}><ExpandMore fontSize="small" /></IconAction> }]} rows={selectedInvoice.lines ?? []} loading={false} getRowKey={(line) => line.id} testId="billing-invoice-lines" empty={{ title: 'Строк счёта нет' }} />{expandedInvoiceLine ? <InvoiceDocumentDetails line={expandedInvoiceLine} period={selectedInvoice.period} /> : null}<Typography sx={{ textAlign: 'right', fontWeight: 'bold' }}>Итого: <MoneyCell minor={selectedInvoice.total_amount} /></Typography></Stack> : null}</DialogContent><DialogActions><PrintAction what="счёт" placement="panel" onClick={printInvoice} testId="billing-invoice-print" />{selectedInvoice?.status === 'issued' ? <DangerAction onClick={() => { setCancelError(null); setCancelConfirm(true) }} data-testid="billing-invoice-cancel">Отменить счёт</DangerAction> : null}<SecondaryAction onClick={() => setSelectedInvoice(null)}>Закрыть</SecondaryAction></DialogActions></Dialog><Dialog open={cancelConfirm} onClose={() => { if (!cancelling) { setCancelError(null); setCancelConfirm(false) } }}><DialogTitle>Отменить счёт?</DialogTitle><DialogContent>Счёт останется в истории со статусом «Отменён». Это действие нельзя отменить.{cancelError ? <ErrorNotice testId="billing-invoice-cancel-error">{cancelError}</ErrorNotice> : null}</DialogContent><DialogActions><DangerAction onClick={cancelInvoice} disabledReason={cancelling ? 'Отмена уже выполняется' : undefined} data-testid="billing-invoice-cancel-confirm">Отменить счёт</DangerAction><SecondaryAction onClick={() => { setCancelError(null); setCancelConfirm(false) }} disabledReason={cancelling ? 'Дождитесь завершения отмены' : undefined}>Назад</SecondaryAction></DialogActions></Dialog>
  </Box>
}
