import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { MenuItem, Stack, TextField, Typography } from '@mui/material'
import { apiUrl } from '../../api'
import {
  DataTable,
  ErrorNotice,
  FilterBar,
  MovementFlowChart,
  PrimaryAction,
  ProductCell,
  QtyCell,
  ReportMetricStrip,
  ScreenHeader,
  TextCell,
  WarningNotice,
} from '../../ui-kit'

type Props = { token: string; sellers?: { id: string; name: string }[]; warehouses?: { id: string; name: string }[] }
type Overview = {
  current_balance: number
  in_qty: number
  out_qty: number
  comparison: { previous_out_qty: number; change_percent: number | null; change: number }
  daily: { date: string; in_qty: number; out_qty: number; previous_out_qty?: number }[]
  generated_at: string
  source_freshness: string | null
  warnings: string[]
}
type Row = {
  product_id: string
  sku_code: string
  product_name: string
  photo_url: string | null
  wb_vendor_code: string | null
  wb_barcode: string | null
  seller_name: string | null
  current_balance?: number
  total_in: number
  total_out: number
  net: number
  // The first reporting API revision used the shorter names below. Keep the
  // screen tolerant while the deployed backend rolls forward; rendering still
  // uses one canonical shape.
  sku?: string
  name?: string
  vendor_code?: string | null
  barcode?: string | null
  in_qty?: number
  out_qty?: number
}

const normalizeRow = (row: Row): Row => ({
  ...row,
  sku_code: row.sku_code ?? row.sku ?? '—',
  product_name: row.product_name ?? row.name ?? '—',
  wb_vendor_code: row.wb_vendor_code ?? row.vendor_code ?? null,
  wb_barcode: row.wb_barcode ?? row.barcode ?? null,
  total_in: row.total_in ?? row.in_qty ?? 0,
  total_out: row.total_out ?? row.out_qty ?? 0,
  net: row.net ?? (row.in_qty ?? 0) - (row.out_qty ?? 0),
})

const dateString = (date: Date) => date.toISOString().slice(0, 10)
const monthStart = (date: Date) => `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, '0')}-01`
const monthEnd = (date: Date) => dateString(new Date(date.getFullYear(), date.getMonth() + 1, 0))
const yearStart = (date: Date) => `${date.getFullYear()}-01-01`
const yearEnd = (date: Date) => `${date.getFullYear()}-12-31`

export function FfReportsPage({ token, sellers = [], warehouses = [] }: Props) {
  const now = useMemo(() => new Date(), [])
  const [period, setPeriod] = useState('month')
  const [dateFrom, setDateFrom] = useState(monthStart(now))
  const [dateTo, setDateTo] = useState(monthEnd(now))
  const [sellerId, setSellerId] = useState('')
  const [warehouseId, setWarehouseId] = useState('')
  const [search, setSearch] = useState('')
  const [comparison, setComparison] = useState('previous')
  const [overview, setOverview] = useState<Overview | null>(null)
  const [rows, setRows] = useState<Row[]>([])
  const [grouping, setGrouping] = useState<'product' | 'operation'>('product')
  const [page, setPage] = useState(1)
  const [total, setTotal] = useState(0)
  const groupingRef = useRef<'product' | 'operation'>('product')
  const [loading, setLoading] = useState(false)
  const [tableLoading, setTableLoading] = useState(false)
  const [summaryError, setSummaryError] = useState(false)
  const [tableError, setTableError] = useState(false)
  const [csvError, setCsvError] = useState(false)
  const [csvLoading, setCsvLoading] = useState(false)
  const [periodError, setPeriodError] = useState('')
  const abortRef = useRef<AbortController | null>(null)
  const tableAbortRef = useRef<AbortController | null>(null)

  const params = useCallback((group?: string, requestedPage?: number) => {
    const query = new URLSearchParams({ date_from: `${dateFrom}T00:00:00`, date_to: `${dateTo}T23:59:59` })
    if (sellerId) query.set('seller_id', sellerId)
    if (warehouseId) query.set('warehouse_id', warehouseId)
    if (search.trim()) query.set('search', search.trim())
    if (group) query.set('group_by', group)
    if (requestedPage) query.set('page', String(requestedPage))
    return query
  }, [dateFrom, dateTo, sellerId, search, warehouseId])

  const loadOverview = useCallback(async (signal: AbortSignal) => {
    const response = await fetch(apiUrl(`/reports/overview?${params().toString()}`), {
      headers: { Authorization: `Bearer ${token}` }, signal,
    })
    if (!response.ok) throw new Error('summary')
    setOverview((await response.json()) as Overview)
  }, [params, token])

  const loadTable = useCallback(async (signal: AbortSignal, requestedPage: number, requestedGrouping: 'product' | 'operation') => {
    const response = await fetch(apiUrl(`/reports/inventory?${params(requestedGrouping, requestedPage).toString()}`), {
      headers: { Authorization: `Bearer ${token}` }, signal,
    })
    if (!response.ok) throw new Error('table')
    const result = (await response.json()) as { rows?: Row[]; total?: number }
    setRows((result.rows ?? []).map(normalizeRow))
    setTotal(result.total ?? 0)
  }, [params, token])

  const load = useCallback(async () => {
    if (periodError) return
    abortRef.current?.abort()
    const controller = new AbortController()
    abortRef.current = controller
    setLoading(true); setSummaryError(false); setTableError(false)
    try {
      const headers = { Authorization: `Bearer ${token}` }
      await Promise.all([
        loadOverview(controller.signal).catch(error => { if (!(error instanceof DOMException && error.name === 'AbortError')) setSummaryError(true) }),
        loadTable(controller.signal, 1, groupingRef.current).catch(error => { if (!(error instanceof DOMException && error.name === 'AbortError')) setTableError(true) }),
      ])
      setPage(1)
    } catch (error) {
      if (!(error instanceof DOMException && error.name === 'AbortError')) setSummaryError(true)
    } finally {
      if (!controller.signal.aborted) setLoading(false)
    }
  }, [loadOverview, loadTable, periodError, token])

  useEffect(() => { void load(); return () => abortRef.current?.abort() }, [load])

  const changeTable = useCallback(async (nextGrouping: 'product' | 'operation', nextPage: number) => {
    tableAbortRef.current?.abort()
    const controller = new AbortController()
    tableAbortRef.current = controller
    setTableLoading(true); setTableError(false)
    try { await loadTable(controller.signal, nextPage, nextGrouping); setPage(nextPage) }
    catch (error) { if (!(error instanceof DOMException && error.name === 'AbortError')) setTableError(true) }
    finally {
      if (tableAbortRef.current === controller) setTableLoading(false)
    }
  }, [loadTable])

  const downloadCsv = async () => {
    if (csvLoading) return
    setCsvError(false)
    setCsvLoading(true)
    try {
      const response = await fetch(apiUrl(`/reports/inventory/export.csv?${params(grouping).toString()}`), { headers: { Authorization: `Bearer ${token}` } })
      if (!response.ok) throw new Error('csv')
      const blob = await response.blob()
      const url = URL.createObjectURL(blob)
      const link = document.createElement('a'); link.href = url; link.download = 'inventory-report.csv'; link.click(); URL.revokeObjectURL(url)
    } catch { setCsvError(true) } finally { setCsvLoading(false) }
  }

  const choosePeriod = (value: string) => {
    setPeriod(value)
    const end = new Date()
    if (value === '7') { const start = new Date(end); start.setDate(end.getDate() - 6); setDateFrom(dateString(start)); setDateTo(dateString(end)) }
    if (value === '30') { const start = new Date(end); start.setDate(end.getDate() - 29); setDateFrom(dateString(start)); setDateTo(dateString(end)) }
    if (value === 'month') { setDateFrom(monthStart(end)); setDateTo(monthEnd(end)) }
    if (value === 'year') { setDateFrom(yearStart(end)); setDateTo(yearEnd(end)) }
  }

  useEffect(() => {
    const from = new Date(`${dateFrom}T00:00:00`)
    const to = new Date(`${dateTo}T00:00:00`)
    const days = Number.isNaN(from.getTime()) || Number.isNaN(to.getTime()) ? 0 : (to.getTime() - from.getTime()) / 86_400_000 + 1
    setPeriodError(days < 1 ? 'Дата начала не может быть позже даты окончания' : days > 366 ? 'Период не может быть длиннее 366 дней' : '')
  }, [dateFrom, dateTo])

  const metrics = [
    { key: 'balance', label: 'Остаток сейчас', value: overview?.current_balance ?? null },
    { key: 'inbound', label: 'Приход за период', value: overview?.in_qty ?? null },
    { key: 'outbound', label: 'Расход за период', value: overview?.out_qty ?? null },
    { key: 'comparison', label: 'Расход к прошлому периоду', value: overview?.comparison.change ?? null, delta: overview?.comparison.change_percent == null ? undefined : { value: overview.comparison.change_percent, unit: 'percent' as const, direction: overview.comparison.change_percent >= 0 ? 'up' as const : 'down' as const, a11yLabel: 'Процент изменения расхода' }, nullValueLabel: 'В прошлом периоде расхода не было' },
  ]

  return <Stack spacing={0} data-testid="ff-reports-page">
    <ScreenHeader title="Остатки и движения" purpose="Текущий остаток и складские движения за выбранный период." />
    <FilterBar search={search} onSearchChange={setSearch} searchPlaceholder="Название, артикул продавца, SKU, ШК" testId="ff-reports-filters">
      <TextField select size="small" label="Период" value={period} onChange={event => choosePeriod(event.target.value)} data-testid="ff-reports-period"><MenuItem value="7">7 дней</MenuItem><MenuItem value="30">30 дней</MenuItem><MenuItem value="month">Текущий месяц</MenuItem><MenuItem value="year">Текущий год</MenuItem><MenuItem value="custom">Другой период</MenuItem></TextField>
      {warehouses.length > 1 ? <TextField select size="small" label="Склад" value={warehouseId} onChange={event => setWarehouseId(event.target.value)} data-testid="ff-reports-warehouse"><MenuItem value="">Все склады</MenuItem>{warehouses.map(warehouse => <MenuItem key={warehouse.id} value={warehouse.id}>{warehouse.name}</MenuItem>)}</TextField> : null}
      {sellers.length > 0 ? <TextField select size="small" label="Селлер" value={sellerId} onChange={event => setSellerId(event.target.value)} data-testid="ff-reports-seller"><MenuItem value="">Все селлеры</MenuItem>{sellers.map(seller => <MenuItem key={seller.id} value={seller.id}>{seller.name}</MenuItem>)}</TextField> : null}
      <TextField select size="small" label="Сравнение" value={comparison} onChange={event => setComparison(event.target.value)} data-testid="ff-reports-comparison"><MenuItem value="previous">Предыдущий период</MenuItem><MenuItem value="none">Не показывать</MenuItem></TextField>
      {period === 'custom' ? <><TextField size="small" label="С" type="date" value={dateFrom} onChange={event => { setDateFrom(event.target.value) }} data-testid="ff-reports-date-from" slotProps={{ inputLabel: { shrink: true } }} /><TextField size="small" label="По" type="date" value={dateTo} onChange={event => { setDateTo(event.target.value) }} data-testid="ff-reports-date-to" slotProps={{ inputLabel: { shrink: true } }} /></> : null}
    </FilterBar>
    {overview?.warnings.map(warning => <WarningNotice key={warning} testId="ff-reports-warning">{warning}</WarningNotice>)}
    {periodError ? <ErrorNotice testId="ff-reports-period-error">{periodError}</ErrorNotice> : null}
    {summaryError ? <ErrorNotice testId="ff-reports-summary-error">Не удалось загрузить сводку. <PrimaryAction onClick={() => void load()}>Повторить</PrimaryAction></ErrorNotice> : null}
    <ReportMetricStrip items={metrics} loading={loading} testId="ff-reports-metrics" />
    <MovementFlowChart series={overview?.daily.map(day => ({ date: day.date, inbound: day.in_qty, outbound: day.out_qty, previousOutbound: day.previous_out_qty })) ?? []} showPrevious={comparison === 'previous'} loading={loading} ariaDescription="Дневной приход и расход" testId="ff-reports-chart" />
    <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }} data-testid="ff-reports-freshness">Данные на {overview ? new Date(overview.generated_at).toLocaleString('ru-RU', { timeZone: 'Europe/Moscow' }) : '—'} МСК</Typography>
    {tableError ? <ErrorNotice testId="ff-reports-table-error">Не удалось загрузить строки отчёта. Повторите попытку.</ErrorNotice> : null}
    {csvError ? <ErrorNotice testId="ff-reports-csv-error">Не удалось скачать CSV. Повторите попытку.</ErrorNotice> : null}
    <Stack direction="row" spacing={2} alignItems="center" sx={{ mb: 2 }} data-testid="ff-reports-table-controls">
      <TextField select size="small" label="Группировка" value={grouping} onChange={event => { const next = event.target.value as 'product' | 'operation'; groupingRef.current = next; setGrouping(next); void changeTable(next, 1) }} data-testid="ff-reports-grouping">
        <MenuItem value="product">По товарам</MenuItem><MenuItem value="operation">По операциям</MenuItem>
      </TextField>
      <PrimaryAction onClick={() => void downloadCsv()} disabledReason={periodError || csvLoading ? (csvLoading ? 'Файл формируется' : periodError) : (rows.length === 0 ? 'За выбранный период нечего выгружать' : undefined)} data-testid="ff-reports-download-csv">{csvLoading ? 'Формирование CSV…' : 'Скачать CSV'}</PrimaryAction>
    </Stack>
    <DataTable<Row> columns={grouping === 'product' ? [
      { key: 'product', header: 'Товар', width: 150, render: row => <ProductCell sku={row.sku_code} photo={row.photo_url ? <img src={row.photo_url} alt="" width="32" height="32" /> : undefined} /> },
      { key: 'name', header: 'Название', width: 240, render: row => <TextCell value={row.product_name} /> },
      { key: 'vendor', header: 'Артикул продавца', width: 170, render: row => <TextCell value={row.wb_vendor_code ?? '—'} /> },
      { key: 'barcode', header: 'ШК', width: 150, render: row => <TextCell value={row.wb_barcode ?? '—'} /> },
      ...(sellers.length > 0 ? [{ key: 'seller', header: 'Селлер', width: 150, render: row => <TextCell value={row.seller_name ?? '—'} /> }] : []),
      { key: 'balance', header: 'Остаток сейчас', align: 'right', render: row => <QtyCell value={row.current_balance ?? 0} /> },
      { key: 'in', header: 'Приход', align: 'right', render: row => <QtyCell value={row.total_in} /> },
      { key: 'out', header: 'Расход', align: 'right', render: row => <QtyCell value={row.total_out} /> },
      { key: 'net', header: 'Нетто', align: 'right', render: row => <QtyCell value={row.net} /> },
    ] : [
      { key: 'operation', header: 'Операция', width: 260, render: row => <TextCell value={(row as Row & { operation?: string }).operation ?? '—'} /> },
      { key: 'in', header: 'Приход', width: 130, align: 'right', render: row => <QtyCell value={row.total_in ?? (row as Row & { in_qty?: number }).in_qty ?? 0} /> },
      { key: 'out', header: 'Расход', width: 130, align: 'right', render: row => <QtyCell value={row.total_out ?? (row as Row & { out_qty?: number }).out_qty ?? 0} /> },
      { key: 'net', header: 'Нетто', width: 130, align: 'right', render: row => <QtyCell value={row.net} /> },
    ]} rows={rows} getRowKey={row => row.product_id ?? (row as Row & { operation?: string }).operation ?? 'report-row'} loading={loading || tableLoading} empty={{ title: 'За выбранный период движений нет', hint: 'Измените период или снимите фильтры.' }} testId="ff-reports-table" />
    <Stack direction="row" justifyContent="space-between" alignItems="center" sx={{ py: 2 }} data-testid="ff-reports-pagination">
      <Typography variant="body2" color="text.secondary">{total === 0 ? '0 из 0' : `${(page - 1) * 50 + 1}–${Math.min(page * 50, total)} из ${total}`}</Typography>
      <Stack direction="row" spacing={1}><PrimaryAction testId="ff-reports-previous-page" disabledReason={page <= 1 ? 'Это первая страница' : undefined} onClick={() => void changeTable(grouping, page - 1)}>Назад</PrimaryAction><PrimaryAction testId="ff-reports-next-page" disabledReason={page * 50 >= total ? 'Это последняя страница' : undefined} onClick={() => void changeTable(grouping, page + 1)}>Вперёд</PrimaryAction></Stack>
    </Stack>
  </Stack>
}
