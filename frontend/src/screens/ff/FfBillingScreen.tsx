import { useEffect, useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Box, Dialog, DialogActions, DialogContent, DialogTitle, MenuItem, Select, Stack, Tab, Tabs, Typography } from '@mui/material'
import ExpandMore from '@mui/icons-material/ExpandMore'
import {
  DataTable,
  ErrorNotice,
  FilterBar,
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
type Props = { sellers?: Seller[]; token: string }
type LedgerEntry = {
  id: string
  occurred_at: string
  seller_name: string
  service_code: 'inbound' | 'marketplace_outbound' | 'storage' | string
  document_number: string
  quantity: number
  unit: 'document' | 'item' | 'liter_day' | string
  rate: number | null
  amount: number | null
  performer_name: string | null
  problem: 'unpriced' | 'storage_period_not_closed' | null
}
type PerformerRow = { performer_name: string; service_code: string; unit: string; quantity: number; documents: number }
type Invoice = { id: string; number: string; period: string; seller_name: string; issued_at: string; total_amount: number; status: 'issued' | 'cancelled'; issues?: { seller_name: string; period: string; reason: string }[]; lines?: InvoiceLine[]; ff_profile?: Record<string, string>; seller_profile?: Record<string, string> }
type InvoiceLine = { id: string; service_code: string; unit: string; quantity: number; rate: number; amount: number; documents?: { date: string; number: string; quantity: number; amount: number }[] }
type InvoiceIssue = { id?: string; seller_id?: string; seller_name: string; period: string; reason: string; message?: string }
type BillingListResponse<T> = { entries?: T[]; invoices?: T[]; rows?: T[]; issues?: InvoiceIssue[] }

function currentMonth(): string {
  const now = new Date()
  const lastClosedMonth = new Date(now.getFullYear(), now.getMonth() - 1, 1)
  return `${lastClosedMonth.getFullYear()}-${String(lastClosedMonth.getMonth() + 1).padStart(2, '0')}`
}

function monthStart(month: string): string {
  return `${month}-01`
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
  storage: 'Хранение',
}
const unitLabels: Record<string, string> = { document: 'За документ', item: 'За штуку', liter_day: 'За литр-день' }
const problemLabels: Record<string, string> = { unpriced: 'Нет тарифа', storage_period_not_closed: 'Хранение не закрыто' }

function responseRows<T>(payload: BillingListResponse<T> | T[], key: 'entries' | 'invoices'): T[] {
  if (Array.isArray(payload)) return payload
  return payload[key] ?? payload.rows ?? []
}

export function FfBillingScreen({ sellers = [], token }: Props) {
  const navigate = useNavigate()
  const [tab, setTab] = useState(0)
  const [month, setMonth] = useState(currentMonth)
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
  const [invoiceRefresh, setInvoiceRefresh] = useState(0)
  const [selectedInvoice, setSelectedInvoice] = useState<Invoice | null>(null)
  const [expandedLine, setExpandedLine] = useState<string | null>(null)
  const [cancelConfirm, setCancelConfirm] = useState(false)
  const [forming, setForming] = useState(false)

  useEffect(() => {
    if (tab !== 0) return
    const controller = new AbortController()
    setLoading(true)
    setError(false)
    setRows([])
    const params = new URLSearchParams({ date: monthStart(month) })
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
    if (tab !== 1) return
    const controller = new AbortController()
    setInvoiceLoading(true); setInvoiceError(false)
    setInvoices([])
    setInvoiceIssues([])
    const params = new URLSearchParams({ period: month, seller_id: sellerId, status: invoiceStatus })
    if (invoiceSearch) params.set('number', invoiceSearch)
    fetch(`/api/billing/invoices?${params}`, { headers: { Authorization: `Bearer ${token}` }, signal: controller.signal })
      .then((response) => { if (!response.ok) throw new Error('billing-invoices'); return response.json() as Promise<BillingListResponse<Invoice> | Invoice[]> })
      .then((data) => {
        setInvoices(responseRows(data, 'invoices'))
        setInvoiceIssues(Array.isArray(data) ? [] : data.issues ?? [])
      })
      .catch((reason: unknown) => { if ((reason as Error).name !== 'AbortError') setInvoiceError(true) })
      .finally(() => setInvoiceLoading(false))
    return () => controller.abort()
  }, [invoiceRefresh, invoiceSearch, invoiceStatus, month, sellerId, tab, token])

  const performerRows = useMemo<PerformerRow[]>(() => {
    const grouped = new Map<string, PerformerRow>()
    rows.forEach((row) => {
      const key = `${row.performer_name ?? 'Исполнитель не зафиксирован'}|${row.service_code}|${row.unit}`
      const current = grouped.get(key) ?? { performer_name: row.performer_name ?? 'Исполнитель не зафиксирован', service_code: row.service_code, unit: row.unit, quantity: 0, documents: 0 }
      current.quantity += row.quantity
      current.documents += 1
      grouped.set(key, current)
    })
    return [...grouped.values()]
  }, [rows])

  const operationColumns = [
    { key: 'date', header: 'Дата', width: 120, render: (row: LedgerEntry) => <TextCell value={new Date(row.occurred_at).toLocaleDateString('ru-RU')} /> },
    { key: 'seller', header: 'Селлер', width: 190, render: (row: LedgerEntry) => <TextCell value={row.seller_name} /> },
    { key: 'service', header: 'Услуга', width: 150, render: (row: LedgerEntry) => serviceLabels[row.service_code] ?? row.service_code },
    { key: 'document', header: 'Документ', width: 190, render: (row: LedgerEntry) => <TextCell value={row.document_number} /> },
    { key: 'quantity', header: 'Количество', width: 120, align: 'right' as const, render: (row: LedgerEntry) => <QtyCell value={row.quantity} /> },
    { key: 'unit', header: 'Расчёт', width: 150, render: (row: LedgerEntry) => unitLabels[row.unit] ?? row.unit },
    { key: 'rate', header: 'Ставка', width: 130, align: 'right' as const, render: (row: LedgerEntry) => <MoneyCell value={row.rate} /> },
    { key: 'amount', header: 'Сумма', width: 140, align: 'right' as const, render: (row: LedgerEntry) => <MoneyCell value={row.amount} /> },
    { key: 'performer', header: 'Исполнитель', width: 220, render: (row: LedgerEntry) => <TextCell value={row.performer_name ?? 'Исполнитель не зафиксирован'} /> },
    { key: 'problem', header: 'Проблема', width: 180, render: (row: LedgerEntry) => row.problem ? <StatusChip label={problemLabels[row.problem]} tone="stop" /> : '—' },
  ]
  const performerColumns = [
    { key: 'performer', header: 'Исполнитель', render: (row: PerformerRow) => <TextCell value={row.performer_name} /> },
    { key: 'service', header: 'Услуга', render: (row: PerformerRow) => serviceLabels[row.service_code] ?? row.service_code },
    { key: 'unit', header: 'Расчёт', render: (row: PerformerRow) => unitLabels[row.unit] ?? row.unit },
    { key: 'quantity', header: 'Количество', align: 'right' as const, render: (row: PerformerRow) => <QtyCell value={row.quantity} /> },
    { key: 'documents', header: 'Документов', align: 'right' as const, render: (row: PerformerRow) => <QtyCell value={row.documents} /> },
  ]
  const activeRows = mode === 'operations' ? rows : performerRows
  const hasFilters = Boolean(search || sellerId !== 'all' || service !== 'all')
  const hasUnpriced = rows.some((row) => row.problem === 'unpriced')
  const invoiceColumns = [
    { key: 'number', header: 'Номер', width: 170, render: (row: Invoice) => <TextCell value={row.number} /> },
    { key: 'period', header: 'Период', width: 150, render: (row: Invoice) => <TextCell value={formatPeriod(row.period)} /> },
    { key: 'seller', header: 'Селлер', width: 220, render: (row: Invoice) => <TextCell value={row.seller_name} /> },
    { key: 'issued', header: 'Выставлен', width: 150, render: (row: Invoice) => <TextCell value={new Date(row.issued_at).toLocaleDateString('ru-RU')} /> },
    { key: 'amount', header: 'Сумма', width: 160, align: 'right' as const, render: (row: Invoice) => <MoneyCell value={row.total_amount} /> },
    { key: 'status', header: 'Статус', width: 140, render: (row: Invoice) => <StatusChip label={row.status === 'issued' ? 'Выставлен' : 'Отменён'} tone={row.status === 'issued' ? 'ok' : 'neutral'} /> },
    { key: 'action', header: 'Действие', width: 70, render: (row: Invoice) => <IconAction title="Открыть счёт" testId={`billing-invoice-open-${row.id}`} onClick={() => { setSelectedInvoice(row); setExpandedLine(null) }}><ExpandMore fontSize="small" /></IconAction> },
  ]
  const issueLabels: Record<string, string> = { unpriced: 'Нет тарифа', missing_profile: 'Нет реквизитов', storage_period_not_closed: 'Хранение не закрыто' }
  const issueActions: Record<string, string> = { unpriced: 'Открыть тарифы', missing_profile: 'Открыть селлера', storage_period_not_closed: 'Открыть хранение' }
  const openIssue = (reason: string) => {
    if (reason === 'unpriced') navigate('/app/ff/settings')
    else if (reason === 'missing_profile') navigate('/app/ff/sellers')
    else navigate('/app/ff/inventory')
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
      } else {
        setInvoiceRefresh((value) => value + 1)
      }
      setTab(1)
    } catch {
      setInvoiceError(true)
    } finally {
      setForming(false)
    }
  }
  const printInvoice = () => {
    if (!selectedInvoice) return
    const lines = selectedInvoice.lines ?? []
    const profile = (value: Record<string, string> | undefined, fallback: string) => {
      const fields = value ? Object.entries(value).filter(([, field]) => field).map(([key, field]) => `<div>${escapeHtml(key)}: ${escapeHtml(field)}</div>`).join('') : ''
      return fields || `<div>${escapeHtml(fallback)}</div>`
    }
    const html = `<html><body><h1>Счёт ${escapeHtml(selectedInvoice.number)}</h1><p>${escapeHtml(formatPeriod(selectedInvoice.period))} · выставлен ${escapeHtml(new Date(selectedInvoice.issued_at).toLocaleDateString('ru-RU'))}</p><h3>Получатель</h3>${profile(selectedInvoice.ff_profile, 'Реквизиты ФФ')}<h3>Плательщик</h3>${profile(selectedInvoice.seller_profile, selectedInvoice.seller_name)}${lines.map((line) => `<p>${escapeHtml(serviceLabels[line.service_code] ?? line.service_code)} · ${escapeHtml(line.quantity)} · ${escapeHtml(line.rate)} · ${escapeHtml(line.amount)}</p>`).join('')}<h2>Итого: ${escapeHtml(selectedInvoice.total_amount)} ₽</h2></body></html>`
    const printWindow = window.open('', '_blank'); printWindow?.document.write(html); printWindow?.document.close(); printWindow?.print()
  }
  const cancelInvoice = () => {
    if (!selectedInvoice || selectedInvoice.status !== 'issued') return
    fetch(`/api/billing/invoices/${selectedInvoice.id}/cancel`, { method: 'POST', headers: { Authorization: `Bearer ${token}` } })
      .then((response) => { if (!response.ok) throw new Error('cancel') ; return response.json() as Promise<{ status: Invoice['status'] }> })
      .then((data) => { const updated = { ...selectedInvoice, status: data.status }; setSelectedInvoice(updated); setInvoices((items) => items.map((item) => item.id === updated.id ? updated : item)); setCancelConfirm(false) })
  }

  return <Box data-testid="ff-billing-screen">
    <ScreenHeader title="Расчёты" purpose="Начисления за работу склада и автоматически выставленные счета селлерам." />
    <Tabs value={tab} onChange={(_, value: number) => setTab(value)} aria-label="Расчёты">
      <Tab label="Начисления" data-testid="billing-tab-charges" /><Tab label="Счета" data-testid="billing-tab-invoices" />
    </Tabs>
    <FilterBar search={tab === 0 ? search : invoiceSearch} onSearchChange={tab === 0 ? setSearch : setInvoiceSearch} searchPlaceholder={tab === 0 ? 'Номер документа' : 'Номер счёта'} testId="billing-filter-bar">
      <PeriodPicker value={month} onChange={setMonth} testId="billing-period" />
      <Select size="small" value={sellerId} onChange={(event) => setSellerId(event.target.value)} inputProps={{ 'data-testid': 'billing-seller' }} sx={{ minWidth: 190 }} aria-label="Селлер">
        <MenuItem value="all">Все селлеры</MenuItem>{sellers.map((seller) => <MenuItem key={seller.id} value={seller.id}>{seller.name}</MenuItem>)}
      </Select>
      {tab === 0 ? <Select size="small" value={service} onChange={(event) => setService(event.target.value)} inputProps={{ 'data-testid': 'billing-service' }} sx={{ minWidth: 160 }} aria-label="Услуга">
        <MenuItem value="all">Все услуги</MenuItem><MenuItem value="inbound">Приёмка</MenuItem><MenuItem value="marketplace_outbound">Отгрузка</MenuItem><MenuItem value="storage">Хранение</MenuItem>
      </Select> : <Select size="small" value={invoiceStatus} onChange={(event) => setInvoiceStatus(event.target.value)} inputProps={{ 'data-testid': 'billing-status' }} sx={{ minWidth: 160 }} aria-label="Статус"><MenuItem value="all">Все статусы</MenuItem><MenuItem value="issued">Выставлен</MenuItem><MenuItem value="cancelled">Отменён</MenuItem></Select>}
      {tab === 0 ? <Select size="small" value={mode} onChange={(event) => setMode(event.target.value as typeof mode)} inputProps={{ 'data-testid': 'billing-mode' }} sx={{ minWidth: 190 }} aria-label="Режим">
        <MenuItem value="operations">По операциям</MenuItem><MenuItem value="performers">По исполнителям</MenuItem>
      </Select> : null}
    </FilterBar>
    {tab === 0 ? <><>{error ? <ErrorNotice testId="billing-error">Не удалось загрузить начисления. Повторите попытку</ErrorNotice> : null}</>{hasUnpriced && mode === 'operations' ? <Stack direction="row" sx={{ mb: 2 }}><PrimaryAction onClick={() => navigate('/app/ff/settings')}>Открыть тарифы</PrimaryAction></Stack> : null}<DataTable columns={mode === 'operations' ? operationColumns : performerColumns} rows={activeRows} loading={loading} getRowKey={(row) => ('id' in row ? row.id : `${row.performer_name}-${row.service_code}-${row.unit}`)} testId="billing-ledger-table" empty={{ title: mode === 'performers' ? 'За месяц нет завершённых операций с исполнителем' : hasFilters ? 'По выбранным условиям начислений нет — измените фильтры' : 'За выбранный месяц начислений нет', hint: mode === 'performers' ? undefined : 'Начисления появятся после завершённой приёмки, отгрузки или фиксации хранения' }} /></> : <><>{invoiceError ? <ErrorNotice testId="billing-invoices-error">Не удалось загрузить счета. Повторите попытку</ErrorNotice> : null}</>{invoiceIssues.length ? <Stack spacing={1} sx={{ mb: 2 }} data-testid="billing-invoice-issues">{invoiceIssues.map((issue, index) => <Stack key={`${issue.seller_name}-${issue.period}-${issue.reason}-${index}`} direction="row" spacing={1} alignItems="center"><Typography>{issue.seller_name} · {issue.period}</Typography><StatusChip label={issueLabels[issue.reason] ?? 'Требуется исправление'} tone="stop" /><PrimaryAction onClick={() => openIssue(issue.reason)}>{issueActions[issue.reason] ?? 'Исправить'}</PrimaryAction></Stack>)}<PrimaryAction disabledReason="Сначала устраните причины, перечисленные выше" onClick={retryFormation}>{'Повторить формирование'}</PrimaryAction></Stack> : sellerId !== 'all' && !invoiceLoading ? <Stack direction="row" sx={{ mb: 2 }}><PrimaryAction disabledReason={forming ? 'Формирование уже выполняется' : undefined} onClick={retryFormation}>Причины устранены — повторите формирование</PrimaryAction></Stack> : null}<DataTable columns={invoiceColumns} rows={invoices} loading={invoiceLoading} getRowKey={(row) => row.id} testId="billing-invoices-table" empty={{ title: 'За этот месяц счета не выставлены', hint: 'Нет начислений для формирования' }} /></>}
    <Dialog open={Boolean(selectedInvoice)} onClose={() => setSelectedInvoice(null)} maxWidth="lg" fullWidth aria-labelledby="billing-invoice-dialog-title"><DialogTitle id="billing-invoice-dialog-title">Счёт {selectedInvoice?.number} {selectedInvoice ? <StatusChip label={selectedInvoice.status === 'issued' ? 'Выставлен' : 'Отменён'} tone={selectedInvoice.status === 'issued' ? 'ok' : 'neutral'} /> : null}</DialogTitle><DialogContent dividers>{selectedInvoice ? <Stack spacing={2}><Typography>Период: {formatPeriod(selectedInvoice.period)} · Выставлен: {new Date(selectedInvoice.issued_at).toLocaleDateString('ru-RU')}</Typography><Stack direction="row" spacing={2}><Box flex={1}><Typography fontWeight="bold">Получатель</Typography><Typography>{selectedInvoice.ff_profile?.legal_name ?? 'Реквизиты ФФ'}</Typography></Box><Box flex={1}><Typography fontWeight="bold">Плательщик</Typography><Typography>{selectedInvoice.seller_profile?.legal_name ?? selectedInvoice.seller_name}</Typography></Box></Stack><DataTable columns={[{ key: 'service', header: 'Услуга', render: (line: InvoiceLine) => serviceLabels[line.service_code] ?? line.service_code }, { key: 'unit', header: 'Расчёт', render: (line: InvoiceLine) => unitLabels[line.unit] ?? line.unit }, { key: 'qty', header: 'Количество', render: (line: InvoiceLine) => <QtyCell value={line.quantity} /> }, { key: 'rate', header: 'Ставка', render: (line: InvoiceLine) => <MoneyCell value={line.rate} /> }, { key: 'amount', header: 'Сумма', render: (line: InvoiceLine) => <MoneyCell value={line.amount} /> }, { key: 'details', header: 'Детализация', render: (line: InvoiceLine) => <IconAction title="Показать документы" onClick={() => setExpandedLine(expandedLine === line.id ? null : line.id)}><ExpandMore fontSize="small" /></IconAction> }]} rows={selectedInvoice.lines ?? []} loading={false} getRowKey={(line) => line.id} testId="billing-invoice-lines" empty={{ title: 'Строк счёта нет' }} />{expandedLine ? <Stack data-testid="billing-invoice-documents">{(selectedInvoice.lines?.find((line) => line.id === expandedLine)?.documents ?? []).map((doc) => <Typography key={`${doc.date}-${doc.number}`}>Исходный документ: {doc.date} · {line.service_code === 'storage' ? `Расчёт хранения за ${formatPeriod(selectedInvoice.period)}` : doc.number} · {doc.quantity} · {doc.amount}</Typography>)}</Stack> : null}<Typography textAlign="right" fontWeight="bold">Итого: <MoneyCell value={selectedInvoice.total_amount} /></Typography></Stack> : null}</DialogContent><DialogActions><PrintAction what="счёт" placement="panel" onClick={printInvoice} testId="billing-invoice-print" />{selectedInvoice?.status === 'issued' ? <DangerAction onClick={() => setCancelConfirm(true)} testId="billing-invoice-cancel">Отменить счёт</DangerAction> : null}<SecondaryAction onClick={() => setSelectedInvoice(null)}>Закрыть</SecondaryAction></DialogActions></Dialog><Dialog open={cancelConfirm} onClose={() => setCancelConfirm(false)}><DialogTitle>Отменить счёт?</DialogTitle><DialogContent>Счёт останется в истории со статусом «Отменён». Это действие нельзя отменить.</DialogContent><DialogActions><DangerAction onClick={cancelInvoice}>Отменить счёт</DangerAction><SecondaryAction onClick={() => setCancelConfirm(false)}>Назад</SecondaryAction></DialogActions></Dialog>
  </Box>
}
