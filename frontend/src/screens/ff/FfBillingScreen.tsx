import { useEffect, useMemo, useState } from 'react'
import { Box, Button, MenuItem, Select, Stack, Tab, Tabs } from '@mui/material'
import {
  DataTable,
  EmptyState,
  ErrorNotice,
  FilterBar,
  MoneyCell,
  PeriodPicker,
  PrimaryAction,
  QtyCell,
  ScreenHeader,
  StatusChip,
  TextCell,
} from '../../ui-kit'

type Seller = { id: string; name: string }
type Props = { sellers?: Seller[] }
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

function currentMonth(): string {
  const now = new Date()
  return `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}`
}

const serviceLabels: Record<string, string> = {
  inbound: 'Приёмка',
  marketplace_outbound: 'Отгрузка',
  storage: 'Хранение',
}
const unitLabels: Record<string, string> = { document: 'За документ', item: 'За штуку', liter_day: 'За литр-день' }
const problemLabels: Record<string, string> = { unpriced: 'Нет тарифа', storage_period_not_closed: 'Хранение не закрыто' }

export function FfBillingScreen({ sellers = [] }: Props) {
  const [tab, setTab] = useState(0)
  const [month, setMonth] = useState(currentMonth)
  const [sellerId, setSellerId] = useState('all')
  const [service, setService] = useState('all')
  const [mode, setMode] = useState<'operations' | 'performers'>('operations')
  const [search, setSearch] = useState('')
  const [rows, setRows] = useState<LedgerEntry[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(false)

  useEffect(() => {
    if (tab !== 0) return
    const controller = new AbortController()
    setLoading(true)
    setError(false)
    const params = new URLSearchParams({ period: month, seller_id: sellerId, service_code: service, mode })
    if (search) params.set('document_number', search)
    fetch(`/api/billing/ledger?${params}`, { signal: controller.signal })
      .then((response) => {
        if (!response.ok) throw new Error('billing-ledger')
        return response.json() as Promise<{ entries?: LedgerEntry[]; rows?: LedgerEntry[] }>
      })
      .then((data) => setRows(data.entries ?? data.rows ?? []))
      .catch((reason: unknown) => { if ((reason as Error).name !== 'AbortError') setError(true) })
      .finally(() => setLoading(false))
    return () => controller.abort()
  }, [month, mode, search, service, sellerId, tab])

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

  return <Box data-testid="ff-billing-screen">
    <ScreenHeader title="Расчёты" purpose="Начисления за работу склада и автоматически выставленные счета селлерам." />
    <Tabs value={tab} onChange={(_, value: number) => setTab(value)} aria-label="Расчёты">
      <Tab label="Начисления" data-testid="billing-tab-charges" /><Tab label="Счета" data-testid="billing-tab-invoices" />
    </Tabs>
    <FilterBar search={search} onSearchChange={setSearch} searchPlaceholder="Номер документа" testId="billing-filter-bar">
      <PeriodPicker value={month} onChange={setMonth} testId="billing-period" />
      <Select size="small" value={sellerId} onChange={(event) => setSellerId(event.target.value)} inputProps={{ 'data-testid': 'billing-seller' }} sx={{ minWidth: 190 }} aria-label="Селлер">
        <MenuItem value="all">Все селлеры</MenuItem>{sellers.map((seller) => <MenuItem key={seller.id} value={seller.id}>{seller.name}</MenuItem>)}
      </Select>
      <Select size="small" value={service} onChange={(event) => setService(event.target.value)} inputProps={{ 'data-testid': 'billing-service' }} sx={{ minWidth: 160 }} aria-label="Услуга">
        <MenuItem value="all">Все услуги</MenuItem><MenuItem value="inbound">Приёмка</MenuItem><MenuItem value="marketplace_outbound">Отгрузка</MenuItem><MenuItem value="storage">Хранение</MenuItem>
      </Select>
      <Select size="small" value={mode} onChange={(event) => setMode(event.target.value as typeof mode)} inputProps={{ 'data-testid': 'billing-mode' }} sx={{ minWidth: 190 }} aria-label="Режим">
        <MenuItem value="operations">По операциям</MenuItem><MenuItem value="performers">По исполнителям</MenuItem>
      </Select>
    </FilterBar>
    {error ? <ErrorNotice testId="billing-error">Не удалось загрузить начисления. Повторите попытку</ErrorNotice> : null}
    {hasUnpriced && mode === 'operations' ? <Stack direction="row" sx={{ mb: 2 }}><PrimaryAction onClick={() => undefined}>Открыть тарифы</PrimaryAction></Stack> : null}
    <DataTable columns={mode === 'operations' ? operationColumns : performerColumns} rows={activeRows} loading={loading} getRowKey={(row) => ('id' in row ? row.id : `${row.performer_name}-${row.service_code}-${row.unit}`)} testId="billing-ledger-table" empty={{ title: mode === 'performers' ? 'За месяц нет завершённых операций с исполнителем' : hasFilters ? 'По выбранным условиям начислений нет — измените фильтры' : 'За выбранный месяц начислений нет', hint: mode === 'performers' ? undefined : 'Начисления появятся после завершённой приёмки, отгрузки или фиксации хранения' }} />
  </Box>
}
