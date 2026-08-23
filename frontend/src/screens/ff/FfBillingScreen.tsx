import { useEffect, useMemo, useState } from 'react'
import { Link as RouterLink, useNavigate } from 'react-router-dom'
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
  PrintAction,
  SecondaryAction,
} from '../../ui-kit'

type Seller = { id: string; name: string }
type Props = { sellers?: Seller[]; token: string; onOpenInbound: (id: string) => void }
type LedgerEntry = {
  id: string
  entry_type: 'charge' | 'reversal' | string
  occurred_at: string
  seller_name: string
  service_code: 'inbound' | 'marketplace_outbound' | 'storage_liter_day' | string
  source_type: string
  source_id: string
  document_number: string
  quantity: number
  unit: 'document' | 'item' | 'liter_day' | string
  rate: number | null
  amount: number | null
  performer_name: string | null
  problem: 'unpriced' | 'storage_period_not_closed' | null
}
type PerformerRow = { performer_name: string; service_code: string; unit: string; quantity: number; documents: number }
type BillingProfileSnapshot = Record<string, string | null | undefined>
type Invoice = { id: string; number: string; period: string; seller_name: string; issued_at: string; total_amount: number; status: 'issued' | 'cancelled'; issues?: { seller_name: string; period: string; reason: string }[]; lines?: InvoiceLine[]; ff_profile?: BillingProfileSnapshot; seller_profile?: BillingProfileSnapshot }
type InvoiceLine = { id: string; service_code: string; unit: string; quantity: number; rate: number; amount: number; documents?: { date: string; number: string; quantity: number; amount: number }[] }
type InvoiceIssue = { id?: string; seller_id?: string; seller_name: string; period: string; reason: string; message?: string }
type BillingListResponse<T> = { entries?: T[]; invoices?: T[]; rows?: T[]; issues?: InvoiceIssue[] }

export const STORAGE_SERVICE_CODE = 'storage_liter_day'
export const CANCEL_INVOICE_ERROR_MESSAGE = 'Отмена не подтверждена. Проверьте статус счёта перед повторной попыткой.'

const MOSCOW_TIME_ZONE = 'Europe/Moscow'

export function formatMoscowDate(value: string): string {
  return new Intl.DateTimeFormat('ru-RU', { timeZone: MOSCOW_TIME_ZONE }).format(new Date(value))
}

export function buildLedgerSearchParams(month: string): URLSearchParams {
  return new URLSearchParams({ period: month })
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
const problemLabels: Record<string, string> = { unpriced: 'Нет тарифа', storage_period_not_closed: 'Хранение не закрыто' }
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
  const lineHtml = (invoice.lines ?? []).map((line) => `<tr><td>${escapeHtml(serviceLabels[line.service_code] ?? '—')}</td><td>${escapeHtml(unitLabels[line.unit] ?? '—')}</td><td>${escapeHtml(line.quantity)}</td><td>${escapeHtml(formatMoney(line.rate))}</td><td>${escapeHtml(formatMoney(line.amount))}</td></tr>`).join('')
  return `<!doctype html><html lang="ru"><head><meta charset="utf-8"><title>Счёт ${escapeHtml(invoice.number)}</title></head><body><h1>Счёт ${escapeHtml(invoice.number)}</h1><p>${escapeHtml(formatPeriod(invoice.period))} · выставлен ${escapeHtml(formatMoscowDate(invoice.issued_at))}</p><h3>Получатель</h3>${profileHtml(invoice.ff_profile, 'Реквизиты ФФ')}<h3>Плательщик</h3>${profileHtml(invoice.seller_profile, invoice.seller_name)}<table><thead><tr><th>Услуга</th><th>Расчёт</th><th>Количество</th><th>Ставка</th><th>Сумма</th></tr></thead><tbody>${lineHtml}</tbody></table><h2>Итого: ${escapeHtml(formatMoney(invoice.total_amount))}</h2></body></html>`
}

function responseRows<T>(payload: BillingListResponse<T> | T[], key: 'entries' | 'invoices'): T[] {
  if (Array.isArray(payload)) return payload
  return payload[key] ?? payload.rows ?? []
}

function invoiceIssueContext(sellerId: string, period: string): string {
  return `${sellerId}:${period}`
}

function ledgerDocumentLabel(entry: LedgerEntry): string {
  return entry.entry_type === 'reversal' ? `Сторно ${entry.document_number}` : entry.document_number
}

export function InvoiceDocumentDetails({ line, period }: { line: InvoiceLine; period: string }) {
  return <Stack data-testid="billing-invoice-documents" spacing={0.5}>{(line.documents ?? []).map((doc) => <Stack key={`${doc.date}-${doc.number}`} direction="row" spacing={1} sx={{ alignItems: 'baseline', flexWrap: 'wrap' }}><Typography component="span">Исходный документ: {formatMoscowDate(doc.date)} · {line.service_code === STORAGE_SERVICE_CODE ? `Расчёт хранения за ${formatPeriod(period)}` : doc.number} ·</Typography><QtyCell value={doc.quantity} /><Typography component="span">·</Typography><MoneyCell minor={doc.amount} /></Stack>)}</Stack>
}

export function FfBillingScreen({ sellers = [], token, onOpenInbound }: Props) {
  const navigate = useNavigate()
  const [tab, setTab] = useState<BillingTab>('charges')
  const [months, setMonths] = useState(initialBillingTabPeriods)
  const month = months[tab]
  const setMonth = (period: string) => setMonths((periods) => updateBillingTabPeriod(periods, tab, period))
  const [sellerId, setSellerId] = useState('all')
  const [service, setService] = useState('all')
  const [mode, setMode] = useState<'operations' | 'performers'>('operations')
  const [search, setSearch] = useState('')
  const [rows, setRows] = useState<LedgerEntry[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(false)
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

  useEffect(() => {
    if (tab !== 'charges') return
    const controller = new AbortController()
    setLoading(true)
    setError(false)
    setRows([])
    const params = buildLedgerSearchParams(month)
    if (sellerId !== 'all') params.set('seller_id', sellerId)
    if (service !== 'all') params.set('service_code', service)
    if (search) params.set('document_number', search)
    fetch(`/api/billing/ledger?${params}`, { headers: { Authorization: `Bearer ${token}` }, signal: controller.signal })
      .then((response) => {
        if (!response.ok) throw new Error('billing-ledger')
        return response.json() as Promise<BillingListResponse<LedgerEntry> | LedgerEntry[]>
      })
      .then((data) => setRows(responseRows(data, 'entries')))
      .catch((reason: unknown) => { if ((reason as Error).name !== 'AbortError') setError(true) })
      .finally(() => setLoading(false))
    return () => controller.abort()
  }, [month, mode, search, service, sellerId, tab, token])

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

  const performerRows = useMemo<PerformerRow[]>(() => {
    const grouped = new Map<string, PerformerRow>()
    rows.forEach((row) => {
      if (row.entry_type === 'reversal') return
      const key = `${row.performer_name ?? 'Исполнитель не зафиксирован'}|${row.service_code}|${row.unit}`
      const current = grouped.get(key) ?? { performer_name: row.performer_name ?? 'Исполнитель не зафиксирован', service_code: row.service_code, unit: row.unit, quantity: 0, documents: 0 }
      current.quantity += row.quantity
      current.documents += 1
      grouped.set(key, current)
    })
    return [...grouped.values()]
  }, [rows])

  const operationColumns = [
    { key: 'date', header: 'Дата', width: 120, render: (row: LedgerEntry) => <TextCell value={formatMoscowDate(row.occurred_at)} /> },
    { key: 'seller', header: 'Селлер', width: 190, render: (row: LedgerEntry) => <TextCell value={row.seller_name} /> },
    { key: 'service', header: 'Услуга', width: 150, render: (row: LedgerEntry) => serviceLabels[row.service_code] ?? '—' },
    { key: 'document', header: 'Документ', width: 190, render: (row: LedgerEntry) => {
      const target = ledgerDocumentTarget(row)
      return target ? (
        target.kind === 'inbound' ? (
          <Link component="button" type="button" variant="body2" onClick={() => onOpenInbound(target.sourceId)} data-testid={`billing-document-${row.id}`}>
            <TextCell value={ledgerDocumentLabel(row)} />
          </Link>
        ) : (
          <Link component={RouterLink} to={target.to} variant="body2" data-testid={`billing-document-${row.id}`}>
            <TextCell value={ledgerDocumentLabel(row)} />
          </Link>
        )
      ) : <TextCell value={ledgerDocumentLabel(row)} />
    } },
    { key: 'quantity', header: 'Количество', width: 120, align: 'right' as const, render: (row: LedgerEntry) => <QtyCell value={row.quantity} /> },
    { key: 'unit', header: 'Расчёт', width: 150, render: (row: LedgerEntry) => unitLabels[row.unit] ?? '—' },
    { key: 'rate', header: 'Ставка', width: 130, align: 'right' as const, render: (row: LedgerEntry) => <MoneyCell minor={row.rate} /> },
    { key: 'amount', header: 'Сумма', width: 140, align: 'right' as const, render: (row: LedgerEntry) => <MoneyCell minor={row.amount} /> },
    { key: 'performer', header: 'Исполнитель', width: 220, render: (row: LedgerEntry) => <TextCell value={row.performer_name ?? 'Исполнитель не зафиксирован'} /> },
    { key: 'problem', header: 'Проблема', width: 180, render: (row: LedgerEntry) => row.problem ? <StatusChip label={problemLabels[row.problem]} tone="stop" /> : '—' },
  ]
  const performerColumns = [
    { key: 'performer', header: 'Исполнитель', width: 220, render: (row: PerformerRow) => <TextCell value={row.performer_name} width={200} /> },
    { key: 'service', header: 'Услуга', width: 150, render: (row: PerformerRow) => serviceLabels[row.service_code] ?? '—' },
    { key: 'unit', header: 'Расчёт', width: 150, render: (row: PerformerRow) => unitLabels[row.unit] ?? '—' },
    { key: 'quantity', header: 'Количество', width: 120, align: 'right' as const, render: (row: PerformerRow) => <QtyCell value={row.quantity} /> },
    { key: 'documents', header: 'Документов', width: 120, align: 'right' as const, render: (row: PerformerRow) => <QtyCell value={row.documents} /> },
  ]
  const hasFilters = Boolean(search || sellerId !== 'all' || service !== 'all')
  const hasUnpriced = rows.some((row) => row.problem === 'unpriced')
  const hasUnknownLedgerCodes = rows.some((row) => serviceLabels[row.service_code] === undefined || unitLabels[row.unit] === undefined)
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
  const issueLabels: Record<string, string> = {
    unpriced: 'Нет тарифа',
    missing_seller_profile: 'Нет реквизитов',
    missing_ff_profile: 'Нет реквизитов',
    storage_period_not_closed: 'Хранение не закрыто',
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

  return <Box data-testid="ff-billing-screen">
    <ScreenHeader title="Расчёты" purpose="Начисления за работу склада и автоматически выставленные счета селлерам." />
    <Tabs value={tab} onChange={(_, value: BillingTab) => setTab(value)} aria-label="Расчёты">
      <Tab label="Начисления" value="charges" data-testid="billing-tab-charges" /><Tab label="Счета" value="invoices" data-testid="billing-tab-invoices" />
    </Tabs>
    <FilterBar search={tab === 'charges' ? search : invoiceSearch} onSearchChange={tab === 'charges' ? setSearch : setInvoiceSearch} searchPlaceholder={tab === 'charges' ? 'Номер документа' : 'Номер счёта'} testId="billing-filter-bar">
      <PeriodPicker value={month} onChange={setMonth} testId="billing-period" />
      <Select size="small" value={sellerId} onChange={(event) => setSellerId(event.target.value)} inputProps={{ 'data-testid': 'billing-seller' }} sx={{ minWidth: 190 }} aria-label="Селлер">
        <MenuItem value="all">Все селлеры</MenuItem>{sellers.map((seller) => <MenuItem key={seller.id} value={seller.id}>{seller.name}</MenuItem>)}
      </Select>
      {tab === 'charges' ? <Select size="small" value={service} onChange={(event) => setService(event.target.value)} inputProps={{ 'data-testid': 'billing-service' }} sx={{ minWidth: 160 }} aria-label="Услуга">
        <MenuItem value="all">Все услуги</MenuItem><MenuItem value="inbound">Приёмка</MenuItem><MenuItem value="marketplace_outbound">Отгрузка</MenuItem><MenuItem value={STORAGE_SERVICE_CODE}>Хранение</MenuItem>
      </Select> : <Select size="small" value={invoiceStatus} onChange={(event) => setInvoiceStatus(event.target.value)} inputProps={{ 'data-testid': 'billing-status' }} sx={{ minWidth: 160 }} aria-label="Статус"><MenuItem value="all">Все статусы</MenuItem><MenuItem value="issued">Выставлен</MenuItem><MenuItem value="cancelled">Отменён</MenuItem></Select>}
      {tab === 'charges' ? <Select size="small" value={mode} onChange={(event) => setMode(event.target.value as typeof mode)} inputProps={{ 'data-testid': 'billing-mode' }} sx={{ minWidth: 190 }} aria-label="Режим">
        <MenuItem value="operations">По операциям</MenuItem><MenuItem value="performers">По исполнителям</MenuItem>
      </Select> : null}
    </FilterBar>
    {tab === 'charges' ? <><>{error ? <ErrorNotice testId="billing-error">Не удалось загрузить начисления. Повторите попытку</ErrorNotice> : null}</>{hasUnknownLedgerCodes ? <ErrorNotice testId="billing-ledger-data-error">В некоторых начислениях не удалось распознать услугу или расчёт. Проверьте данные перед сверкой</ErrorNotice> : null}{hasUnpriced && mode === 'operations' ? <Stack direction="row" sx={{ mb: 2 }}><PrimaryAction onClick={() => navigate('/app/ff/settings?tab=tariffs')}>Открыть тарифы</PrimaryAction></Stack> : null}{mode === 'operations' ? <DataTable columns={operationColumns} rows={rows} loading={loading} getRowKey={(row) => row.id} testId="billing-ledger-table" empty={{ title: hasFilters ? 'По выбранным условиям начислений нет — измените фильтры' : 'За выбранный месяц начислений нет', hint: 'Начисления появятся после завершённой приёмки, отгрузки или фиксации хранения' }} /> : <DataTable columns={performerColumns} rows={performerRows} loading={loading} getRowKey={(row) => `${row.performer_name}-${row.service_code}-${row.unit}`} testId="billing-ledger-table" empty={{ title: 'За месяц нет завершённых операций с исполнителем' }} />}</> : <><>{invoiceError ? <ErrorNotice testId="billing-invoices-error">Не удалось загрузить счета. Повторите попытку</ErrorNotice> : null}</>{invoiceIssues.length ? <Stack spacing={1} sx={{ mb: 2 }} data-testid="billing-invoice-issues">{invoiceIssues.map((issue, index) => {
      const action = issueAction(issue)
      return <Stack key={`${issue.seller_name}-${issue.period}-${issue.reason}-${index}`} direction="row" spacing={1} sx={{ alignItems: 'center' }}><Typography>{issue.seller_name} · {issue.period}</Typography><StatusChip label={issueLabels[issue.reason] ?? 'Требуется исправление'} tone="stop" />{action ? <PrimaryAction data-testid={`billing-invoice-issue-action-${issue.id ?? index}`} onClick={() => navigate(action.to)}>{action.label}</PrimaryAction> : null}</Stack>
    })}<PrimaryAction disabledReason="Сначала устраните причины, перечисленные выше" onClick={retryFormation}>{'Повторить формирование'}</PrimaryAction></Stack> : canRetryFormation && !invoiceLoading ? <Stack direction="row" spacing={1} sx={{ mb: 2 }}><Typography>Причины устранены — повторите формирование</Typography><PrimaryAction disabledReason={forming ? 'Формирование уже выполняется' : undefined} onClick={retryFormation}>Повторить формирование</PrimaryAction></Stack> : null}<DataTable columns={invoiceColumns} rows={invoices} loading={invoiceLoading} getRowKey={(row) => row.id} testId="billing-invoices-table" empty={{ title: 'За этот месяц счета не выставлены', hint: 'Нет начислений для формирования' }} /></>}
    <Dialog open={Boolean(selectedInvoice)} onClose={() => setSelectedInvoice(null)} maxWidth="lg" fullWidth aria-labelledby="billing-invoice-dialog-title"><DialogTitle id="billing-invoice-dialog-title">Счёт {selectedInvoice?.number} {selectedInvoice ? <StatusChip label={selectedInvoice.status === 'issued' ? 'Выставлен' : 'Отменён'} tone={selectedInvoice.status === 'issued' ? 'ok' : 'neutral'} /> : null}</DialogTitle><DialogContent dividers>{selectedInvoice ? <Stack spacing={2}><Typography>Период: {formatPeriod(selectedInvoice.period)} · Выставлен: {formatMoscowDate(selectedInvoice.issued_at)}</Typography><Stack direction="row" spacing={2}>{([['Получатель', selectedInvoice.ff_profile, 'Реквизиты ФФ'], ['Плательщик', selectedInvoice.seller_profile, selectedInvoice.seller_name]] as const).map(([title, profile, fallback]) => <Box sx={{ flex: 1 }} key={title}><Typography sx={{ fontWeight: 'bold' }}>{title}</Typography>{profileRows(profile, fallback).map(([label, value]) => <Typography key={label}>{label}: {value}</Typography>)}</Box>)}</Stack>{hasUnknownInvoiceLineCodes ? <ErrorNotice testId="billing-invoice-data-error">В счёте есть строка с нераспознанной услугой или расчётом. Проверьте данные перед печатью</ErrorNotice> : null}<DataTable columns={[{ key: 'service', header: 'Услуга', width: 180, render: (line: InvoiceLine) => serviceLabels[line.service_code] ?? '—' }, { key: 'unit', header: 'Расчёт', width: 170, render: (line: InvoiceLine) => unitLabels[line.unit] ?? '—' }, { key: 'qty', header: 'Количество', width: 120, align: 'right', render: (line: InvoiceLine) => <QtyCell value={line.quantity} /> }, { key: 'rate', header: 'Ставка', width: 130, align: 'right', render: (line: InvoiceLine) => <MoneyCell minor={line.rate} /> }, { key: 'amount', header: 'Сумма', width: 140, align: 'right', render: (line: InvoiceLine) => <MoneyCell minor={line.amount} /> }, { key: 'details', header: 'Детализация', width: 70, align: 'center', render: (line: InvoiceLine) => <IconAction title="Показать документы" onClick={() => setExpandedLine(expandedLine === line.id ? null : line.id)}><ExpandMore fontSize="small" /></IconAction> }]} rows={selectedInvoice.lines ?? []} loading={false} getRowKey={(line) => line.id} testId="billing-invoice-lines" empty={{ title: 'Строк счёта нет' }} />{expandedInvoiceLine ? <InvoiceDocumentDetails line={expandedInvoiceLine} period={selectedInvoice.period} /> : null}<Typography sx={{ textAlign: 'right', fontWeight: 'bold' }}>Итого: <MoneyCell minor={selectedInvoice.total_amount} /></Typography></Stack> : null}</DialogContent><DialogActions><PrintAction what="счёт" placement="panel" onClick={printInvoice} testId="billing-invoice-print" />{selectedInvoice?.status === 'issued' ? <DangerAction onClick={() => { setCancelError(null); setCancelConfirm(true) }} data-testid="billing-invoice-cancel">Отменить счёт</DangerAction> : null}<SecondaryAction onClick={() => setSelectedInvoice(null)}>Закрыть</SecondaryAction></DialogActions></Dialog><Dialog open={cancelConfirm} onClose={() => { if (!cancelling) { setCancelError(null); setCancelConfirm(false) } }}><DialogTitle>Отменить счёт?</DialogTitle><DialogContent>Счёт останется в истории со статусом «Отменён». Это действие нельзя отменить.{cancelError ? <ErrorNotice testId="billing-invoice-cancel-error">{cancelError}</ErrorNotice> : null}</DialogContent><DialogActions><DangerAction onClick={cancelInvoice} disabledReason={cancelling ? 'Отмена уже выполняется' : undefined} data-testid="billing-invoice-cancel-confirm">Отменить счёт</DangerAction><SecondaryAction onClick={() => { setCancelError(null); setCancelConfirm(false) }} disabledReason={cancelling ? 'Дождитесь завершения отмены' : undefined}>Назад</SecondaryAction></DialogActions></Dialog>
  </Box>
}
