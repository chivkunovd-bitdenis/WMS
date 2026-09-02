import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { Box, MenuItem, Stack, TextField, Typography } from '@mui/material'
import { apiUrl } from '../../api'
import {
  ActionGroup,
  DataTable,
  ErrorNotice,
  FilterBar,
  PrimaryAction,
  SecondaryAction,
  ProductCell,
  QtyCell,
  ReportMetricStrip,
  ScreenHeader,
  StatusChip,
  TextCell,
  WarningNotice,
} from '../../ui-kit'

type Props = {
  token: string
  sellers?: { id: string; name: string }[]
  warehouses?: { id: string; name: string }[]
  contentInset?: number
}
type ReportWarning =
  | { code: 'wildberries_stale'; source: 'wildberries'; last_updated_at: string | null }
  | { code: 'reporting_dimensions_legacy'; count: number }
type Overview = {
  current_balance: number
  in_qty: number
  out_qty: number
  comparison: { previous_out_qty: number; change_percent: number | null; change: number }
  daily: { date: string; in_qty: number; out_qty: number; previous_out_qty?: number }[]
  generated_at: string
  source_freshness: { source: string; last_updated_at: string | null; is_stale: boolean } | null
  warnings: ReportWarning[]
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
  integrity_error?: boolean
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

type SellerRow = {
  seller_id: string
  seller_name: string
  product_count: number
  current_balance: number
  total_in: number
  total_out: number
  net: number
}
type OperationRow = { operation: string; in_qty: number; out_qty: number; net: number }
type Grouping = 'seller' | 'product' | 'operation'

type CalendarDate = { year: number; month: number; day: number }

const moscowDateFormatter = new Intl.DateTimeFormat('en-CA', {
  timeZone: 'Europe/Moscow', year: 'numeric', month: '2-digit', day: '2-digit',
})

const dateString = ({ year, month, day }: CalendarDate) => `${year}-${String(month).padStart(2, '0')}-${String(day).padStart(2, '0')}`
const moscowCalendarDate = (date: Date): CalendarDate => {
  const parts = moscowDateFormatter.formatToParts(date)
  const value = (type: 'year' | 'month' | 'day') => Number(parts.find((part) => part.type === type)?.value)
  return { year: value('year'), month: value('month'), day: value('day') }
}
const addDays = (date: CalendarDate, days: number) => {
  const result = new Date(Date.UTC(date.year, date.month - 1, date.day + days))
  return { year: result.getUTCFullYear(), month: result.getUTCMonth() + 1, day: result.getUTCDate() }
}
const monthStart = (date: CalendarDate) => dateString({ ...date, day: 1 })
const monthEnd = (date: CalendarDate) => dateString(addDays({
  year: date.month === 12 ? date.year + 1 : date.year,
  month: date.month === 12 ? 1 : date.month + 1,
  day: 1,
}, -1))
const yearStart = (date: CalendarDate) => `${date.year}-01-01`
const yearEnd = (date: CalendarDate) => `${date.year}-12-31`
const nextDateString = (date: string) => {
  const [year, month, day] = date.split('-').map(Number)
  return dateString(addDays({ year, month, day }, 1))
}
const moscowApiBoundary = (date: string) => `${date}T00:00:00+03:00`
const moscowTimestamp = (value: string | null) => value
  ? `${new Date(value).toLocaleString('ru-RU', { timeZone: 'Europe/Moscow' })} МСК`
  : 'нет данных об обновлении'
const warningText = (warning: ReportWarning) => warning.code === 'wildberries_stale'
  ? `Данные Wildberries могут быть неполными. Последнее обновление: ${moscowTimestamp(warning.last_updated_at)}.`
  : `В отчёте есть исторические записи, восстановленные по доступным связям: ${warning.count}`

export function FfReportsPage({ token, sellers = [], warehouses = [], contentInset = 308 }: Props) {
  const now = useMemo(() => moscowCalendarDate(new Date()), [])
  const [period, setPeriod] = useState('month')
  const [dateFrom, setDateFrom] = useState(monthStart(now))
  const [dateTo, setDateTo] = useState(monthEnd(now))
  const [sellerId, setSellerId] = useState('')
  const [warehouseId, setWarehouseId] = useState('')
  const [search, setSearch] = useState('')
  const [overview, setOverview] = useState<Overview | null>(null)
  const [rows, setRows] = useState<Row[]>([])
  const [grouping, setGrouping] = useState<Grouping>('seller')
  const [sellerRows, setSellerRows] = useState<SellerRow[]>([])
  // Раскрытая строка селлера тянет свои данные: товары и разбивку по видам
  // движений. Держать их в основном ответе нельзя — это отчёт по всем селлерам.
  const [expandedSeller, setExpandedSeller] = useState<string | null>(null)
  const [sellerProducts, setSellerProducts] = useState<Row[]>([])
  const [sellerOperations, setSellerOperations] = useState<OperationRow[]>([])
  const [sellerDetailLoading, setSellerDetailLoading] = useState(false)
  const [sellerDetailError, setSellerDetailError] = useState(false)
  const [page, setPage] = useState(1)
  const [total, setTotal] = useState(0)
  const groupingRef = useRef<Grouping>('seller')
  const [loading, setLoading] = useState(false)
  const [summaryLoading, setSummaryLoading] = useState(false)
  const [tableLoading, setTableLoading] = useState(false)
  const [summaryError, setSummaryError] = useState(false)
  const [tableError, setTableError] = useState(false)
  const [csvError, setCsvError] = useState(false)
  const [csvLoading, setCsvLoading] = useState(false)
  const [periodError, setPeriodError] = useState('')
  const abortRef = useRef<AbortController | null>(null)
  const overviewRetryAbortRef = useRef<AbortController | null>(null)
  const tableAbortRef = useRef<AbortController | null>(null)
  const effectiveWarehouseId = warehouses.length === 1 ? warehouses[0].id : warehouseId

  const params = useCallback((group?: string, requestedPage?: number) => {
    // The reporting API uses an exclusive end boundary. Sending the next Moscow
    // calendar day keeps every fractional second of the selected final day.
    const query = new URLSearchParams({
      date_from: moscowApiBoundary(dateFrom),
      date_to: moscowApiBoundary(nextDateString(dateTo)),
    })
    if (sellerId) query.set('seller_id', sellerId)
    if (effectiveWarehouseId) query.set('warehouse_id', effectiveWarehouseId)
    if (search.trim()) query.set('search', search.trim())
    if (group) query.set('group_by', group)
    if (requestedPage) query.set('page', String(requestedPage))
    return query
  }, [dateFrom, dateTo, effectiveWarehouseId, sellerId, search])

  const loadOverview = useCallback(async (signal: AbortSignal) => {
    const response = await fetch(apiUrl(`/reports/overview?${params().toString()}`), {
      headers: { Authorization: `Bearer ${token}` }, signal,
    })
    if (!response.ok) throw new Error('summary')
    setOverview((await response.json()) as Overview)
  }, [params, token])

  const loadTable = useCallback(async (signal: AbortSignal, requestedPage: number, requestedGrouping: Grouping) => {
    const response = await fetch(apiUrl(`/reports/inventory?${params(requestedGrouping, requestedPage).toString()}`), {
      headers: { Authorization: `Bearer ${token}` }, signal,
    })
    if (!response.ok) throw new Error('table')
    const result = (await response.json()) as { rows?: (Row & SellerRow)[]; total?: number }
    if (requestedGrouping === 'seller') {
      setSellerRows((result.rows ?? []) as SellerRow[])
      setRows([])
    } else {
      setSellerRows([])
      setRows((result.rows ?? []).map(normalizeRow))
    }
    setTotal(result.total ?? 0)
  }, [params, token])

  // Подробности селлера: те же два разреза отчёта, но суженные до одного
  // селлера. Отдельного эндпоинта не заводим — данные и так те же самые.
  const loadSellerDetail = useCallback(async (sellerRowId: string) => {
    setSellerDetailLoading(true)
    setSellerDetailError(false)
    try {
      const scoped = (group: string) => {
        const query = params(group)
        if (sellerRowId) query.set('seller_id', sellerRowId)
        return query.toString()
      }
      const [products, operations] = await Promise.all([
        fetch(apiUrl(`/reports/inventory?${scoped('product')}`), { headers: { Authorization: `Bearer ${token}` } }),
        fetch(apiUrl(`/reports/inventory?${scoped('operation')}`), { headers: { Authorization: `Bearer ${token}` } }),
      ])
      if (!products.ok || !operations.ok) throw new Error('detail')
      const productsPayload = (await products.json()) as { rows?: Row[] }
      const operationsPayload = (await operations.json()) as { rows?: OperationRow[] }
      setSellerProducts((productsPayload.rows ?? []).map(normalizeRow))
      setSellerOperations(operationsPayload.rows ?? [])
    } catch {
      setSellerDetailError(true)
      setSellerProducts([])
      setSellerOperations([])
    } finally {
      setSellerDetailLoading(false)
    }
  }, [params, token])

  const load = useCallback(async () => {
    if (periodError) return
    overviewRetryAbortRef.current?.abort()
    abortRef.current?.abort()
    tableAbortRef.current?.abort()
    tableAbortRef.current = null
    setTableLoading(false)
    const controller = new AbortController()
    abortRef.current = controller
    setLoading(true); setSummaryLoading(false); setSummaryError(false); setTableError(false)
    // A changed filter must never leave values from the previous scope visible.
    setOverview(null); setRows([]); setSellerRows([]); setTotal(0)
    setExpandedSeller(null); setSellerProducts([]); setSellerOperations([])
    try {
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
  }, [loadOverview, loadTable, periodError])

  const retryOverview = useCallback(async () => {
    if (periodError) return
    overviewRetryAbortRef.current?.abort()
    const controller = new AbortController()
    overviewRetryAbortRef.current = controller
    setSummaryLoading(true); setSummaryError(false); setOverview(null)
    try {
      await loadOverview(controller.signal)
    } catch (error) {
      if (!(error instanceof DOMException && error.name === 'AbortError')) setSummaryError(true)
    } finally {
      if (overviewRetryAbortRef.current === controller) setSummaryLoading(false)
    }
  }, [loadOverview, periodError])

  useEffect(() => {
    void load()
    return () => {
      abortRef.current?.abort()
      overviewRetryAbortRef.current?.abort()
      tableAbortRef.current?.abort()
    }
  }, [load])

  const changeTable = useCallback(async (nextGrouping: Grouping, nextPage: number) => {
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
      const response = await fetch(apiUrl(`/reports/inventory/export.csv?${params(grouping === 'seller' ? 'product' : grouping).toString()}`), { headers: { Authorization: `Bearer ${token}` } })
      if (!response.ok) throw new Error('csv')
      const blob = await response.blob()
      const url = URL.createObjectURL(blob)
      const link = document.createElement('a'); link.href = url; link.download = 'inventory-report.csv'; link.click(); URL.revokeObjectURL(url)
    } catch { setCsvError(true) } finally { setCsvLoading(false) }
  }

  const choosePeriod = (value: string) => {
    setPeriod(value)
    const end = moscowCalendarDate(new Date())
    if (value === '7') { setDateFrom(dateString(addDays(end, -6))); setDateTo(dateString(end)) }
    if (value === '30') { setDateFrom(dateString(addDays(end, -29))); setDateTo(dateString(end)) }
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
    { key: 'net', label: 'Нетто за период', value: overview == null ? null : overview.in_qty - overview.out_qty },
  ]
  const hasIntegrityError = rows.some((row) => row.integrity_error)
  const csvDisabledReason = periodError
    || (csvLoading ? 'Файл формируется' : '')
    || (tableError ? 'Строки отчёта не загружены' : '')
    || (rows.length === 0 ? 'За выбранный период нечего выгружать' : undefined)

  return <Stack spacing={0} sx={{ minWidth: 0, width: `calc(100vw - ${contentInset}px)` }} data-testid="ff-reports-page">
    <ScreenHeader title="Остатки и движения" purpose="Текущий остаток и складские движения за выбранный период." />
    <FilterBar search={search} onSearchChange={setSearch} searchPlaceholder="Название, артикул продавца, SKU, ШК" testId="ff-reports-filters">
      <TextField select size="small" label="Период" value={period} onChange={event => choosePeriod(event.target.value)} data-testid="ff-reports-period"><MenuItem value="7">7 дней</MenuItem><MenuItem value="30">30 дней</MenuItem><MenuItem value="month">Текущий месяц</MenuItem><MenuItem value="year">Текущий год</MenuItem><MenuItem value="custom">Другой период</MenuItem></TextField>
      {warehouses.length > 1 ? <TextField select size="small" label="Склад" value={warehouseId} onChange={event => setWarehouseId(event.target.value)} data-testid="ff-reports-warehouse"><MenuItem value="">Все склады</MenuItem>{warehouses.map(warehouse => <MenuItem key={warehouse.id} value={warehouse.id}>{warehouse.name}</MenuItem>)}</TextField> : null}
      {sellers.length > 0 ? <TextField select size="small" label="Селлер" value={sellerId} onChange={event => setSellerId(event.target.value)} data-testid="ff-reports-seller"><MenuItem value="">Все селлеры</MenuItem>{sellers.map(seller => <MenuItem key={seller.id} value={seller.id}>{seller.name}</MenuItem>)}</TextField> : null}
      {period === 'custom' ? <><TextField size="small" label="С" type="date" value={dateFrom} onChange={event => { setDateFrom(event.target.value) }} data-testid="ff-reports-date-from" slotProps={{ inputLabel: { shrink: true } }} /><TextField size="small" label="По" type="date" value={dateTo} onChange={event => { setDateTo(event.target.value) }} data-testid="ff-reports-date-to" slotProps={{ inputLabel: { shrink: true } }} /></> : null}
    </FilterBar>
    {overview?.warnings.map((warning, index) => <WarningNotice key={`${warning.code}-${index}`} testId="ff-reports-warning">{warningText(warning)}</WarningNotice>)}
    {periodError ? <ErrorNotice testId="ff-reports-period-error">{periodError}</ErrorNotice> : null}
    {summaryError ? <ErrorNotice testId="ff-reports-summary-error">Не удалось загрузить сводку. Повторите попытку. <PrimaryAction onClick={() => void retryOverview()}>Повторить</PrimaryAction></ErrorNotice> : <>
      <ReportMetricStrip items={metrics} loading={loading || summaryLoading} testId="ff-reports-metrics" />
      <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }} data-testid="ff-reports-freshness">Данные на {overview ? new Date(overview.generated_at).toLocaleString('ru-RU', { timeZone: 'Europe/Moscow' }) : '—'} МСК</Typography>
    </>}
    {tableError ? <ErrorNotice testId="ff-reports-table-error">Не удалось загрузить строки отчёта. Повторите попытку.</ErrorNotice> : null}
    {hasIntegrityError ? <ErrorNotice testId="ff-reports-integrity-error">В истории есть неполное перемещение. Значения показаны как записаны; отчёт ничего не достраивал.</ErrorNotice> : null}
    {csvError ? <ErrorNotice testId="ff-reports-csv-error">Не удалось скачать CSV. Повторите попытку.</ErrorNotice> : null}
    <Stack direction="row" spacing={2} sx={{ mb: 2, alignItems: 'center' }} data-testid="ff-reports-table-controls">
      <TextField select size="small" label="Группировка" value={grouping} onChange={event => { const next = event.target.value as Grouping; groupingRef.current = next; setGrouping(next); setExpandedSeller(null); void changeTable(next, 1) }} data-testid="ff-reports-grouping">
        <MenuItem value="seller">По селлерам</MenuItem><MenuItem value="product">По товарам</MenuItem><MenuItem value="operation">По операциям</MenuItem>
      </TextField>
      <PrimaryAction onClick={() => void downloadCsv()} disabledReason={csvDisabledReason} data-testid="ff-reports-download-csv">{csvLoading ? 'Формирование CSV…' : 'Скачать CSV'}</PrimaryAction>
    </Stack>
    {tableError ? null : <>{grouping === 'seller' ? <DataTable<SellerRow> columns={[
      { key: 'seller', header: 'Селлер', render: row => <TextCell value={row.seller_name} /> },
      { key: 'products', header: 'Товаров', align: 'right', width: 110, render: row => <QtyCell value={row.product_count} /> },
      { key: 'balance', header: <Typography component="span" variant="inherit" sx={{ whiteSpace: 'normal', lineHeight: 1.15 }}>Остаток сейчас</Typography>, align: 'right', width: 120, render: row => <QtyCell value={row.current_balance} /> },
      { key: 'in', header: 'Приход', align: 'right', width: 100, render: row => <QtyCell value={row.total_in} /> },
      { key: 'out', header: 'Расход', align: 'right', width: 100, render: row => <QtyCell value={row.total_out} /> },
      { key: 'net', header: 'Нетто', align: 'right', width: 100, render: row => <QtyCell value={row.net} /> },
    ]} rows={sellerRows} getRowKey={row => row.seller_id || 'no-seller'} loading={loading || tableLoading} empty={{ title: 'За выбранный период движений нет', hint: 'Измените период или снимите фильтры.' }} testId="ff-reports-seller-table" expand={{
      isExpanded: row => expandedSeller === (row.seller_id || 'no-seller'),
      label: row => `Показать движения селлера ${row.seller_name}`,
      onToggle: row => {
        const key = row.seller_id || 'no-seller'
        if (expandedSeller === key) { setExpandedSeller(null); return }
        setExpandedSeller(key)
        setSellerProducts([]); setSellerOperations([])
        void loadSellerDetail(row.seller_id)
      },
      render: () => sellerDetailError
        ? <ErrorNotice testId="ff-reports-seller-detail-error">Не удалось загрузить движения селлера</ErrorNotice>
        : <Stack spacing={2} data-testid="ff-reports-seller-detail">
          <Box>
            <Typography variant="subtitle2" sx={{ mb: 1 }}>Виды движений</Typography>
            <DataTable<OperationRow> columns={[
              { key: 'operation', header: 'Движение', render: row => <TextCell value={row.operation} /> },
              { key: 'in', header: 'Приход', align: 'right', width: 100, render: row => <QtyCell value={row.in_qty} /> },
              { key: 'out', header: 'Расход', align: 'right', width: 100, render: row => <QtyCell value={row.out_qty} /> },
              { key: 'net', header: 'Нетто', align: 'right', width: 100, render: row => <QtyCell value={row.net} /> },
            ]} rows={sellerOperations} getRowKey={row => row.operation} loading={sellerDetailLoading} empty={{ title: 'Движений за период нет' }} testId="ff-reports-seller-operations" />
          </Box>
          <Box>
            <Typography variant="subtitle2" sx={{ mb: 1 }}>Товары</Typography>
            <DataTable<Row> columns={[
              { key: 'product', header: 'Товар', width: 105, render: row => <ProductCell sku={row.sku_code} photo={row.photo_url ? <img src={row.photo_url} alt="" width="32" height="32" /> : undefined} /> },
              { key: 'name', header: 'Название', render: row => <TextCell value={row.product_name} /> },
              { key: 'vendor', header: <Typography component="span" variant="inherit" sx={{ whiteSpace: 'normal', lineHeight: 1.15 }}>Артикул продавца</Typography>, width: 120, render: row => <TextCell value={row.wb_vendor_code ?? '—'} width={110} /> },
              { key: 'barcode', header: 'ШК', width: 120, render: row => <TextCell value={row.wb_barcode ?? '—'} width={110} /> },
              { key: 'balance', header: <Typography component="span" variant="inherit" sx={{ whiteSpace: 'normal', lineHeight: 1.15 }}>Остаток сейчас</Typography>, align: 'right', width: 105, render: row => <QtyCell value={row.current_balance ?? 0} /> },
              { key: 'in', header: 'Приход', align: 'right', width: 90, render: row => <QtyCell value={row.total_in} /> },
              { key: 'out', header: 'Расход', align: 'right', width: 90, render: row => <QtyCell value={row.total_out} /> },
              { key: 'net', header: 'Нетто', align: 'right', width: 90, render: row => <QtyCell value={row.net} /> },
            ]} rows={sellerProducts} getRowKey={row => row.product_id} loading={sellerDetailLoading} empty={{ title: 'Товаров за период нет' }} testId="ff-reports-seller-products" />
          </Box>
        </Stack>,
    }} /> : <DataTable<Row> columns={grouping === 'product' ? [
      { key: 'product', header: 'Товар', width: 105, render: row => <Stack direction="row" spacing={1} sx={{ alignItems: 'center' }}><ProductCell sku={row.sku_code} photo={row.photo_url ? <img src={row.photo_url} alt="" width="32" height="32" /> : undefined} />{row.integrity_error ? <StatusChip label="Ошибка" tone="stop" testId="ff-reports-row-integrity-error" /> : null}</Stack> },
      { key: 'name', header: 'Название', width: 125, render: row => <TextCell value={row.product_name} width={115} /> },
      { key: 'vendor', header: <Typography component="span" variant="inherit" sx={{ whiteSpace: 'normal', lineHeight: 1.15 }}>Артикул продавца</Typography>, width: 120, render: row => <TextCell value={row.wb_vendor_code ?? '—'} width={110} /> },
      { key: 'barcode', header: 'ШК', width: 120, render: row => <TextCell value={row.wb_barcode ?? '—'} width={110} /> },
      ...(sellers.length > 0 ? [{ key: 'seller', header: 'Селлер', width: 90, render: (row: Row) => <TextCell value={row.seller_name ?? '—'} width={80} /> }] : []),
      { key: 'balance', header: <Typography component="span" variant="inherit" sx={{ whiteSpace: 'normal', lineHeight: 1.15 }}>Остаток сейчас</Typography>, align: 'right', width: 105, render: row => <QtyCell value={row.current_balance ?? 0} /> },
      { key: 'in', header: 'Приход', align: 'right', width: 65, render: row => <QtyCell value={row.total_in} /> },
      { key: 'out', header: 'Расход', align: 'right', width: 65, render: row => <QtyCell value={row.total_out} /> },
      { key: 'net', header: 'Нетто', align: 'right', width: 65, render: row => <QtyCell value={row.net} /> },
    ] : [
      { key: 'operation', header: 'Операция', width: 260, render: row => <Stack direction="row" spacing={1} sx={{ alignItems: 'center' }}><TextCell value={(row as Row & { operation?: string }).operation ?? '—'} />{row.integrity_error ? <StatusChip label="Ошибка" tone="stop" testId="ff-reports-row-integrity-error" /> : null}</Stack> },
      { key: 'in', header: 'Приход', width: 130, align: 'right', render: row => { const value = row.total_in ?? (row as Row & { in_qty?: number }).in_qty ?? 0; return <QtyCell value={row.integrity_error && value === 0 ? null : value} /> } },
      { key: 'out', header: 'Расход', width: 130, align: 'right', render: row => { const value = row.total_out ?? (row as Row & { out_qty?: number }).out_qty ?? 0; return <QtyCell value={row.integrity_error && value === 0 ? null : value} /> } },
      { key: 'net', header: 'Нетто', width: 130, align: 'right', render: row => <QtyCell value={row.net} /> },
    ]} rows={rows} getRowKey={row => row.product_id ?? (row as Row & { operation?: string }).operation ?? 'report-row'} loading={loading || tableLoading} empty={{ title: 'За выбранный период движений нет', hint: 'Измените период или снимите фильтры.' }} testId="ff-reports-table" />}
    <Stack direction="row" sx={{ py: 2, justifyContent: 'space-between', alignItems: 'center' }} data-testid="ff-reports-pagination">
      <Typography variant="body2" color="text.secondary">{total === 0 ? '0 из 0' : `${(page - 1) * 50 + 1}–${Math.min(page * 50, total)} из ${total}`}</Typography>
      <ActionGroup><SecondaryAction data-testid="ff-reports-previous-page" disabledReason={page <= 1 ? 'Это первая страница' : undefined} onClick={() => void changeTable(grouping, page - 1)}>Назад</SecondaryAction><SecondaryAction data-testid="ff-reports-next-page" disabledReason={page * 50 >= total ? 'Это последняя страница' : undefined} onClick={() => void changeTable(grouping, page + 1)}>Вперёд</SecondaryAction></ActionGroup>
    </Stack></>}
  </Stack>
}
