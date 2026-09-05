import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { Link, MenuItem, Stack, TextField, Typography } from '@mui/material'
import { Link as RouterLink } from 'react-router-dom'
import { apiUrl } from '../../api'
import { ProductPhotoThumb } from '../../components/ProductPhotoThumb'
import { sellerQuickRange } from './FfBillingScreen'
import {
  ActionGroup,
  DataTable,
  ErrorNotice,
  WarningNotice,
  FilterBar,
  MoscowDateRangeInput,
  PrimaryAction,
  SecondaryAction,
  QtyCell,
  ReportMetricStrip,
  ScreenHeader,
  TextCell,
} from '../../ui-kit'

type Props = {
  token: string
  /** Открыть документ приёмки: экран отчёта сам его не рисует. */
  onOpenInbound?: (id: string) => void
  sellers?: { id: string; name: string }[]
  warehouses?: { id: string; name: string }[]
  contentInset?: number
}
type ReportWarning =
  | { code: 'wildberries_stale'; source: 'wildberries'; last_updated_at: string | null }
  | { code: 'reporting_dimensions_legacy'; count: number }
type Overview = {
  current_balance: number
  /** Остаток на начало периода. Считается сервером откатом сегодняшнего
   *  остатка на все движения с начала периода: на прошлом периоде разность
   *  «остаток − приход + расход» давала цифру, которой на складе не было. */
  opening_balance?: number
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
type OperationRow = { operation: string; in_qty: number; out_qty: number; net: number; integrity_error?: boolean }
type MovementRow = {
  id: string
  at: string
  operation: string
  quantity: number
  product_id?: string | null
  product_name?: string | null
  sku_code?: string | null
  document: {
    kind: 'inbound' | 'marketplace_unload' | 'fbs_supply' | 'fbs_order'
    id: string
    number: string
  } | null
}
type Grouping = 'seller' | 'product' | 'operation'

export function reportCsvDisabledReason(options: {
  periodError: string; csvLoading: boolean; tableError: boolean;
  loading: boolean; loadedRowCount: number;
}): string | undefined {
  return options.periodError
    || (options.csvLoading ? 'Файл формируется' : '')
    || (options.loading || options.tableError ? 'Строки отчёта не загружены' : '')
    || (options.loadedRowCount === 0 ? 'За выбранный период нечего выгружать' : undefined)
}

export function ReportNotices({ warnings, detailRows }: {
  warnings: ReportWarning[]; detailRows: { integrity_error?: boolean }[];
}) {
  return <>
    {warnings.map(warning => <WarningNotice key={warning.code} testId={`ff-reports-warning-${warning.code}`}>
      {warning.code === 'wildberries_stale'
        ? `Данные Wildberries могут быть неполными. Последнее обновление: ${warning.last_updated_at ? new Date(warning.last_updated_at).toLocaleString('ru-RU', { timeZone: 'Europe/Moscow' }) : '—'}.`
        : `В отчёте есть исторические записи, восстановленные по доступным связям: ${warning.count}`}
    </WarningNotice>)}
    {detailRows.some(row => row.integrity_error)
      ? <ErrorNotice testId="ff-reports-integrity-error">В истории есть неполное перемещение. Значения показаны как записаны; отчёт ничего не достраивал.</ErrorNotice>
      : null}
  </>
}

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
const nextDateString = (date: string) => {
  const [year, month, day] = date.split('-').map(Number)
  return dateString(addDays({ year, month, day }, 1))
}
const moscowApiBoundary = (date: string) => `${date}T00:00:00+03:00`

export function FfReportsPage({ token, onOpenInbound, sellers = [], warehouses = [], contentInset = 308 }: Props) {
  const now = useMemo(() => moscowCalendarDate(new Date()), [])
  const [dateFrom, setDateFrom] = useState(monthStart(now))
  const [dateTo, setDateTo] = useState(monthEnd(now))
  const [sellerId, setSellerId] = useState('')
  const [warehouseId, setWarehouseId] = useState('')
  const [search, setSearch] = useState('')
  const [overview, setOverview] = useState<Overview | null>(null)
  const [rows, setRows] = useState<Row[]>([])
  const [grouping, setGrouping] = useState<Grouping>('product')
  const [sellerRows, setSellerRows] = useState<SellerRow[]>([])
  // Раскрытая строка селлера тянет свои данные: товары и разбивку по видам
  // движений. Держать их в основном ответе нельзя — это отчёт по всем селлерам.
  const [expandedSeller, setExpandedSeller] = useState<string | null>(null)
  const [sellerProducts, setSellerProducts] = useState<Row[]>([])
  const [sellerOperations, setSellerOperations] = useState<OperationRow[]>([])
  const [sellerDetailLoading, setSellerDetailLoading] = useState(false)
  const [sellerDetailError, setSellerDetailError] = useState(false)
  // Третий уровень: движения одного товара. Кладовщик открывает товар, чтобы
  // увидеть, когда он приехал, когда уехал и по какому документу.
  const [expandedProduct, setExpandedProduct] = useState<string | null>(null)
  const [movements, setMovements] = useState<MovementRow[]>([])
  const [movementsLoading, setMovementsLoading] = useState(false)
  const [movementsError, setMovementsError] = useState(false)
  const [movementsTruncated, setMovementsTruncated] = useState(false)
  const [movementsLimit, setMovementsLimit] = useState(0)
  const [expandedOperation, setExpandedOperation] = useState<string | null>(null)
  const [page, setPage] = useState(1)
  const [total, setTotal] = useState(0)
  const groupingRef = useRef<Grouping>('product')
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

  // Раскрыть можно и товар, и вид движения: в группировке «по видам» третьего
  // уровня не было вовсе, потому что ручка требовала товар.
  const loadMovements = useCallback(async (
    scope: { productId?: string; operation?: string },
    scopedSellerId: string,
  ) => {
    setMovementsLoading(true)
    setMovementsError(false)
    setMovementsTruncated(false)
    try {
      const query = params()
      if (scope.productId) query.set('product_id', scope.productId)
      if (scope.operation) query.set('operation', scope.operation)
      if (scopedSellerId) query.set('seller_id', scopedSellerId)
      const response = await fetch(apiUrl(`/reports/inventory/movements?${query.toString()}`), {
        headers: { Authorization: `Bearer ${token}` },
      })
      if (!response.ok) throw new Error('movements')
      const payload = (await response.json()) as {
        rows?: MovementRow[]
        truncated?: boolean
        limit?: number
      }
      setMovements(payload.rows ?? [])
      setMovementsTruncated(Boolean(payload.truncated))
      setMovementsLimit(payload.limit ?? 0)
    } catch {
      setMovementsError(true)
      setMovements([])
    } finally {
      setMovementsLoading(false)
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
        loadTable(controller.signal, 1, 'seller').catch(error => { if (!(error instanceof DOMException && error.name === 'AbortError')) setTableError(true) }),
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


  useEffect(() => {
    const from = new Date(`${dateFrom}T00:00:00`)
    const to = new Date(`${dateTo}T00:00:00`)
    const days = Number.isNaN(from.getTime()) || Number.isNaN(to.getTime()) ? 0 : (to.getTime() - from.getTime()) / 86_400_000 + 1
    setPeriodError(days < 1 ? 'Дата начала не может быть позже даты окончания' : days > 366 ? 'Период не может быть длиннее 366 дней' : '')
  }, [dateFrom, dateTo])

  // Порядок такой, как читают: сколько пришло, сколько ушло, сколько осталось.
  // «Нетто» убрано — оно не отвечало ни на один вопрос склада.
  const metrics = [
    // Остаток на начало показываем явно: без него «приход 50, расход 2,
    // остаток 58» читается как ошибка расчёта, хотя арифметика верна.
    { key: 'opening', label: 'Было на начало', value: overview?.opening_balance ?? null },
    { key: 'inbound', label: 'Приход за период', value: overview?.in_qty ?? null },
    { key: 'outbound', label: 'Расход за период', value: overview?.out_qty ?? null },
    { key: 'balance', label: 'Остаток сейчас', value: overview?.current_balance ?? null },
  ]
  // Одна и та же таблица движений для обоих третьих уровней: по товару и по
  // виду движения. Во втором случае товар обязателен — в пачке их много.
  const movementsTable = (options: { showProduct: boolean }) => movementsError
    ? <ErrorNotice testId="ff-reports-movements-error">Не удалось загрузить движения</ErrorNotice>
    : <Stack spacing={1}>
        {movementsTruncated ? <Typography variant="caption" color="text.secondary" data-testid="ff-reports-movements-truncated">
          Показаны первые {movementsLimit} движений из большего числа. Сузьте период или фильтр, чтобы увидеть остальные.
        </Typography> : null}
        <DataTable<MovementRow> columns={[
          { key: 'at', header: 'Когда', width: 190, render: move => <TextCell value={new Date(move.at).toLocaleString('ru-RU', { timeZone: 'Europe/Moscow' })} width={160} /> },
          ...(options.showProduct ? [{ key: 'product', header: 'Товар', width: 260, render: (move: MovementRow) => <TextCell value={move.product_name ?? '—'} width={250} /> }] : []),
          { key: 'operation', header: 'Движение', width: 260, render: (move: MovementRow) => <TextCell value={move.operation} /> },
          { key: 'document', header: 'Документ', width: 200, render: (move: MovementRow) => {
              const doc = move.document
              if (!doc) return <TextCell value="—" />
              if (doc.kind === 'inbound') return <Link component="button" type="button" sx={{ textAlign: 'left' }} onClick={() => onOpenInbound?.(doc.id)}>{doc.number}</Link>
              if (doc.kind === 'marketplace_unload') return <Link component={RouterLink} to={`/app/ff/mp-shipments?open_mp=${doc.id}`} sx={{ textAlign: 'left' }}>{doc.number}</Link>
              if (doc.kind === 'fbs_supply') return <Link component={RouterLink} to={`/app/ff/fbs?supply_id=${doc.id}`} sx={{ textAlign: 'left' }}>{doc.number}</Link>
              return <TextCell value={doc.number} />
            } },
          { key: 'qty', header: 'Штук', align: 'right', width: 110, render: (move: MovementRow) => <QtyCell value={move.quantity} /> },
        ]} rows={movements} getRowKey={move => move.id} loading={movementsLoading} empty={{ title: 'Движений за период нет' }} testId="ff-reports-movements" />
      </Stack>

  const csvDisabledReason = reportCsvDisabledReason({
    periodError, csvLoading, tableError, loading: loading || tableLoading,
    loadedRowCount: sellerRows.length,
  })

  return <Stack spacing={0} sx={{ minWidth: 0, width: `calc(100vw - ${contentInset}px)` }} data-testid="ff-reports-page">
    <ScreenHeader title="Остатки и движения" purpose="Текущий остаток и складские движения за выбранный период." />
    <FilterBar search={search} onSearchChange={setSearch} searchPlaceholder="Название, артикул продавца, SKU, ШК" testId="ff-reports-filters">
      <MoscowDateRangeInput label="Период" startLabel="с" endLabel="по" value={{ start: dateFrom, end: dateTo }} onChange={(value) => { setDateFrom(value.start ?? dateFrom); setDateTo(value.end ?? dateTo) }} maxDays={366} testId="ff-reports-range" />
      <Stack direction="row" spacing={0.5} sx={{ flexWrap: 'wrap', flexShrink: 0, alignSelf: { sm: 'flex-end' }, pb: { sm: 0.25 } }} aria-label="Быстрый период">
        {([['today', 'Сегодня'], ['seven_days', '7 дней'], ['thirty_days', '30 дней'], ['current_month', 'Этот месяц'], ['previous_month', 'Прошлый месяц']] as const).map(([key, label]) => (
          <SecondaryAction key={key} onClick={() => { const range = sellerQuickRange(key); setDateFrom(range.start); setDateTo(range.end) }}>{label}</SecondaryAction>
        ))}
      </Stack>
      {warehouses.length > 1 ? <TextField select size="small" label="Склад" sx={{ minWidth: 180 }} value={warehouseId} onChange={event => setWarehouseId(event.target.value)} data-testid="ff-reports-warehouse"><MenuItem value="">Все склады</MenuItem>{warehouses.map(warehouse => <MenuItem key={warehouse.id} value={warehouse.id}>{warehouse.name}</MenuItem>)}</TextField> : null}
      {sellers.length > 0 ? <TextField select size="small" label="Селлер" sx={{ minWidth: 200 }} value={sellerId} onChange={event => setSellerId(event.target.value)} data-testid="ff-reports-seller"><MenuItem value="">Все селлеры</MenuItem>{sellers.map(seller => <MenuItem key={seller.id} value={seller.id}>{seller.name}</MenuItem>)}</TextField> : null}
    </FilterBar>
    {periodError ? <ErrorNotice testId="ff-reports-period-error">{periodError}</ErrorNotice> : null}
    {summaryError ? <ErrorNotice testId="ff-reports-summary-error">Не удалось загрузить сводку. Повторите попытку. <PrimaryAction onClick={() => void retryOverview()}>Повторить</PrimaryAction></ErrorNotice> : <>
      <ReportMetricStrip items={metrics} loading={loading || summaryLoading} testId="ff-reports-metrics" />
      <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }} data-testid="ff-reports-freshness">Данные на {overview ? new Date(overview.generated_at).toLocaleString('ru-RU', { timeZone: 'Europe/Moscow' }) : '—'} МСК</Typography>
    </>}
    {tableError ? <ErrorNotice testId="ff-reports-table-error">Не удалось загрузить строки отчёта. Повторите попытку.</ErrorNotice> : null}
    <ReportNotices warnings={overview?.warnings ?? []} detailRows={[
      ...rows, ...sellerProducts, ...sellerOperations,
    ]} />
    {csvError ? <ErrorNotice testId="ff-reports-csv-error">Не удалось скачать CSV. Повторите попытку.</ErrorNotice> : null}
    <Stack direction="row" spacing={2} sx={{ mb: 2, alignItems: 'center' }} data-testid="ff-reports-table-controls">
      <TextField select size="small" label="Группировка" value={grouping} onChange={event => { const next = event.target.value as Grouping; groupingRef.current = next; setGrouping(next); setExpandedSeller(null); setExpandedProduct(null) }} data-testid="ff-reports-grouping">
        <MenuItem value="product">По товарам</MenuItem><MenuItem value="operation">По операциям</MenuItem>
      </TextField>
      <PrimaryAction onClick={() => void downloadCsv()} disabledReason={csvDisabledReason} data-testid="ff-reports-download-csv">{csvLoading ? 'Формирование CSV…' : 'Скачать CSV'}</PrimaryAction>
    </Stack>
    {tableError ? null : <><DataTable<SellerRow> columns={[
      { key: 'seller', header: 'Селлер', width: 320, render: row => <TextCell value={row.seller_name} width={310} /> },
      { key: 'products', header: 'Товаров', align: 'right', width: 110, render: row => <QtyCell value={row.product_count} /> },
      { key: 'in', header: 'Приход', align: 'right', width: 110, render: row => <QtyCell value={row.total_in} /> },
      { key: 'out', header: 'Расход', align: 'right', width: 110, render: row => <QtyCell value={row.total_out} /> },
      { key: 'balance', header: <Typography component="span" variant="inherit" sx={{ whiteSpace: 'normal', lineHeight: 1.15 }}>Остаток сейчас</Typography>, align: 'right', width: 130, render: row => <QtyCell value={row.current_balance} /> },
    ]} rows={sellerRows} getRowKey={row => row.seller_id || 'no-seller'} loading={loading || tableLoading} empty={{ title: 'За выбранный период движений нет', hint: 'Измените период или снимите фильтры.' }} testId="ff-reports-seller-table" expand={{
      isExpanded: row => expandedSeller === (row.seller_id || 'no-seller'),
      label: row => `Показать движения селлера ${row.seller_name}`,
      onToggle: row => {
        const key = row.seller_id || 'no-seller'
        if (expandedSeller === key) { setExpandedSeller(null); return }
        setExpandedSeller(key)
        setExpandedProduct(null)
        setSellerProducts([]); setSellerOperations([]); setMovements([])
        void loadSellerDetail(row.seller_id)
      },
      render: row => sellerDetailError
        ? <ErrorNotice testId="ff-reports-seller-detail-error">Не удалось загрузить движения селлера</ErrorNotice>
        : grouping === 'operation'
          ? <DataTable<OperationRow> columns={[
              { key: 'operation', header: 'Движение', width: 320, render: op => <TextCell value={op.operation} width={310} /> },
              { key: 'in', header: 'Приход', align: 'right', width: 110, render: op => <QtyCell value={op.in_qty} /> },
              { key: 'out', header: 'Расход', align: 'right', width: 110, render: op => <QtyCell value={op.out_qty} /> },
            ]} rows={sellerOperations} getRowKey={op => op.operation} loading={sellerDetailLoading} empty={{ title: 'Движений за период нет' }} testId="ff-reports-seller-operations" expand={{
              isExpanded: op => expandedOperation === op.operation,
              label: op => `Показать движения: ${op.operation}`,
              onToggle: op => {
                if (expandedOperation === op.operation) { setExpandedOperation(null); return }
                setExpandedOperation(op.operation)
                setMovements([])
                void loadMovements({ operation: op.operation }, row.seller_id)
              },
              render: () => movementsTable({ showProduct: true }),
            }} />
          : <DataTable<Row> columns={[
              { key: 'product', header: 'Товар', width: 320, render: product => <Stack direction="row" spacing={1.25} sx={{ alignItems: 'center', minWidth: 0 }}><ProductPhotoThumb src={product.photo_url} alt={product.product_name} size={40} previewSize={280} testId={`ff-reports-photo-${product.product_id}`} /><Stack sx={{ minWidth: 0 }}><Typography variant="body2" sx={{ fontWeight: 600 }} noWrap>{product.product_name}</Typography><Typography variant="caption" color="text.secondary" noWrap>{[product.sku_code, product.wb_vendor_code].filter(Boolean).join(' · ')}</Typography></Stack></Stack> },
              { key: 'barcode', header: 'ШК', width: 150, render: product => <TextCell value={product.wb_barcode ?? '—'} width={140} /> },
              { key: 'in', header: 'Приход', align: 'right', width: 110, render: product => <QtyCell value={product.total_in} /> },
              { key: 'out', header: 'Расход', align: 'right', width: 110, render: product => <QtyCell value={product.total_out} /> },
              { key: 'balance', header: <Typography component="span" variant="inherit" sx={{ whiteSpace: 'normal', lineHeight: 1.15 }}>Остаток сейчас</Typography>, align: 'right', width: 130, render: product => <QtyCell value={product.current_balance ?? 0} /> },
            ]} rows={sellerProducts} getRowKey={product => product.product_id} loading={sellerDetailLoading} empty={{ title: 'Товаров за период нет' }} testId="ff-reports-seller-products" expand={{
              isExpanded: product => expandedProduct === product.product_id,
              label: product => `Показать движения товара ${product.product_name}`,
              onToggle: product => {
                if (expandedProduct === product.product_id) { setExpandedProduct(null); return }
                setExpandedProduct(product.product_id)
                setMovements([])
                void loadMovements({ productId: product.product_id }, row.seller_id)
              },
              render: () => movementsTable({ showProduct: false }),
            }} />,
    }} />

    <Stack direction="row" sx={{ py: 2, justifyContent: 'space-between', alignItems: 'center' }} data-testid="ff-reports-pagination">
      <Typography variant="body2" color="text.secondary">{total === 0 ? '0 из 0' : `${(page - 1) * 50 + 1}–${Math.min(page * 50, total)} из ${total}`}</Typography>
      <ActionGroup><SecondaryAction data-testid="ff-reports-previous-page" disabledReason={page <= 1 ? 'Это первая страница' : undefined} onClick={() => void changeTable('seller', page - 1)}>Назад</SecondaryAction><SecondaryAction data-testid="ff-reports-next-page" disabledReason={page * 50 >= total ? 'Это последняя страница' : undefined} onClick={() => void changeTable('seller', page + 1)}>Вперёд</SecondaryAction></ActionGroup>
    </Stack></>}
  </Stack>
}
