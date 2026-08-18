import { Fragment, useCallback, useEffect, useMemo, useRef, useState } from 'react'
import {
  Alert,
  Button,
  Paper,
  Skeleton,
  Stack,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  TextField,
  Typography,
} from '@mui/material'
import FileDownloadOutlined from '@mui/icons-material/FileDownloadOutlined'
import { apiUrl } from '../../api'
import { useDebouncedValue } from '../../hooks/useDebouncedValue'
import { PageHeader } from '../../ui/PageHeader'
import { readApiErrorMessage } from '../../utils/readApiErrorMessage'
import { MarkingSellerPicker } from '../shared/MarkingSellerPicker'
import { ProductPhotoThumb } from '../../components/ProductPhotoThumb'

const TEXT_FILTER_DEBOUNCE_MS = 400

// Тот же порядок, что и REPORT_GROUP_ORDER в
// backend/app/services/inventory_movement_report_service.py — колонки отчёта идут
// в стабильном порядке, но показываются только те группы, по которым реально есть
// движения в текущей выборке.
const GROUP_ORDER = [
  'intake',
  'transfer',
  'tz_import',
  'mp_unload',
  'fbs',
  'outbound_shipment',
  'discrepancy',
  'other',
]

type MovementGroup = {
  key: string
  label: string
  in_qty: number
  out_qty: number
}

type ReportRow = {
  product_id: string
  sku_code: string
  product_name: string
  wb_vendor_code: string | null
  wb_barcode: string | null
  photo_url: string | null
  seller_id: string | null
  seller_name: string | null
  groups: MovementGroup[]
  total_in: number
  total_out: number
  net: number
}

type Props = {
  token: string
  sellers?: { id: string; name: string }[]
}

function firstDayOfMonth(d: Date): string {
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-01`
}

function lastDayOfMonth(d: Date): string {
  const last = new Date(d.getFullYear(), d.getMonth() + 1, 0)
  return `${last.getFullYear()}-${String(last.getMonth() + 1).padStart(2, '0')}-${String(last.getDate()).padStart(2, '0')}`
}

function toDateFromParam(isoDate: string): string {
  return `${isoDate}T00:00:00`
}

function toDateToParam(isoDate: string): string {
  return `${isoDate}T23:59:59`
}

function groupByKey(row: ReportRow, key: string): MovementGroup | undefined {
  return row.groups.find((g) => g.key === key)
}

function excelCell(value: string | number | null | undefined): string {
  const text = value === null || value === undefined ? '' : String(value)
  return text.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
}

function downloadReportExcel(
  rows: ReportRow[],
  visibleGroups: { key: string; label: string }[],
): void {
  const headers = [
    'Название',
    'Артикул селлера',
    'SKU',
    'ШК',
    'Селлер',
    ...visibleGroups.flatMap((g) => [`${g.label}, приход`, `${g.label}, расход`]),
    'Итого приход',
    'Итого расход',
    'Итого нетто',
  ]
  const bodyRows = rows.map((row) => [
    row.product_name,
    row.wb_vendor_code ?? '',
    row.sku_code,
    row.wb_barcode ?? '',
    row.seller_name ?? '',
    ...visibleGroups.flatMap((g) => {
      const found = groupByKey(row, g.key)
      return [found?.in_qty ?? 0, found?.out_qty ?? 0]
    }),
    row.total_in,
    row.total_out,
    row.net,
  ])
  const html = [
    '<html><head><meta charset="utf-8" /></head><body><table>',
    `<thead><tr>${headers.map((header) => `<th>${excelCell(header)}</th>`).join('')}</tr></thead>`,
    `<tbody>${bodyRows
      .map((row) => `<tr>${row.map((cell) => `<td>${excelCell(cell)}</td>`).join('')}</tr>`)
      .join('')}</tbody>`,
    '</table></body></html>',
  ].join('')
  const blob = new Blob([html], { type: 'application/vnd.ms-excel;charset=utf-8' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = `otchet-dvizheniy-${new Date().toISOString().slice(0, 10)}.xls`
  document.body.appendChild(a)
  a.click()
  a.remove()
  URL.revokeObjectURL(url)
}

export function FfReportsPage({ token, sellers = [] }: Props) {
  const today = useMemo(() => new Date(), [])
  const [rows, setRows] = useState<ReportRow[]>([])
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [dateFrom, setDateFrom] = useState(firstDayOfMonth(today))
  const [dateTo, setDateTo] = useState(lastDayOfMonth(today))
  const [sellerId, setSellerId] = useState<string | null>(null)
  const [search, setSearch] = useState('')

  const debouncedSearch = useDebouncedValue(search, TEXT_FILTER_DEBOUNCE_MS)
  const loadAbortRef = useRef<AbortController | null>(null)
  const authHeaders = useMemo(() => ({ Authorization: `Bearer ${token}` }), [token])

  const buildFilterParams = useCallback(() => {
    const params = new URLSearchParams()
    params.set('date_from', toDateFromParam(dateFrom))
    params.set('date_to', toDateToParam(dateTo))
    if (sellerId) {
      params.set('seller_id', sellerId)
    }
    if (debouncedSearch.trim()) {
      params.set('search', debouncedSearch.trim())
    }
    return params
  }, [dateFrom, dateTo, sellerId, debouncedSearch])

  const load = useCallback(async () => {
    loadAbortRef.current?.abort()
    const ac = new AbortController()
    loadAbortRef.current = ac
    setBusy(true)
    setError(null)
    try {
      const params = buildFilterParams()
      const res = await fetch(
        apiUrl(`/operations/inventory-movements/summary?${params.toString()}`),
        { headers: authHeaders, signal: ac.signal },
      )
      if (ac.signal.aborted) {
        return
      }
      if (!res.ok) {
        setError(await readApiErrorMessage(res))
        setRows([])
        return
      }
      const data = (await res.json()) as ReportRow[]
      if (ac.signal.aborted) {
        return
      }
      setRows(data)
    } catch (err) {
      if (err instanceof DOMException && err.name === 'AbortError') {
        return
      }
      throw err
    } finally {
      if (!ac.signal.aborted) {
        setBusy(false)
      }
    }
  }, [authHeaders, buildFilterParams])

  useEffect(() => {
    void load()
    return () => {
      loadAbortRef.current?.abort()
    }
  }, [load])

  const visibleGroups = useMemo(() => {
    const byKey = new Map<string, string>()
    for (const row of rows) {
      for (const g of row.groups) {
        if (!byKey.has(g.key)) {
          byKey.set(g.key, g.label)
        }
      }
    }
    return GROUP_ORDER.filter((key) => byKey.has(key)).map((key) => ({
      key,
      label: byKey.get(key)!,
    }))
  }, [rows])

  const colCount = 5 + visibleGroups.length * 2 + 3

  return (
    <Stack spacing={2} data-testid="ff-reports-page">
      <PageHeader
        title="Отчёты"
        description="Приход и расход по товару за период — сводка по журналу складских движений."
      />

      {error ? (
        <Alert severity="error" data-testid="ff-reports-error">
          {error}
        </Alert>
      ) : null}

      <Stack direction={{ xs: 'column', sm: 'row' }} spacing={1} sx={{ flexWrap: 'wrap', alignItems: { sm: 'center' } }}>
        <MarkingSellerPicker
          sellers={sellers}
          selectedSellerId={sellerId}
          onSelectedSellerIdChange={setSellerId}
          testIdPrefix="ff-reports"
        />
        <TextField
          size="small"
          label="С"
          type="date"
          value={dateFrom}
          onChange={(e) => setDateFrom(e.target.value)}
          slotProps={{ inputLabel: { shrink: true } }}
          sx={{ minWidth: 150 }}
          data-testid="ff-reports-date-from"
        />
        <TextField
          size="small"
          label="По"
          type="date"
          value={dateTo}
          onChange={(e) => setDateTo(e.target.value)}
          slotProps={{ inputLabel: { shrink: true } }}
          sx={{ minWidth: 150 }}
          data-testid="ff-reports-date-to"
        />
        <TextField
          size="small"
          label="Поиск по товару"
          placeholder="Название, артикул, SKU, ШК"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          sx={{ minWidth: 220 }}
          data-testid="ff-reports-search"
        />
        <Button
          variant="outlined"
          startIcon={<FileDownloadOutlined />}
          disabled={busy || rows.length === 0}
          onClick={() => downloadReportExcel(rows, visibleGroups)}
          data-testid="ff-reports-export"
        >
          Скачать Excel
        </Button>
      </Stack>

      <TableContainer component={Paper} variant="outlined">
        <Table size="small" data-testid="ff-reports-table">
          <TableHead>
            <TableRow>
              <TableCell rowSpan={2}>Фото</TableCell>
              <TableCell rowSpan={2}>Название</TableCell>
              <TableCell rowSpan={2}>Артикул</TableCell>
              <TableCell rowSpan={2}>ШК</TableCell>
              <TableCell rowSpan={2}>Селлер</TableCell>
              {visibleGroups.map((g) => (
                <TableCell key={g.key} align="center" colSpan={2}>
                  {g.label}
                </TableCell>
              ))}
              <TableCell align="center" colSpan={3}>
                Итого
              </TableCell>
            </TableRow>
            <TableRow>
              {visibleGroups.map((g) => (
                <Fragment key={g.key}>
                  <TableCell align="right">Приход</TableCell>
                  <TableCell align="right">Расход</TableCell>
                </Fragment>
              ))}
              <TableCell align="right">Приход</TableCell>
              <TableCell align="right">Расход</TableCell>
              <TableCell align="right">Нетто</TableCell>
            </TableRow>
          </TableHead>
          <TableBody>
            {busy ? (
              <TableRow>
                <TableCell colSpan={colCount}>
                  <Skeleton height={32} />
                </TableCell>
              </TableRow>
            ) : rows.length === 0 ? (
              <TableRow>
                <TableCell colSpan={colCount}>
                  <Typography variant="body2" color="text.secondary">
                    За выбранный период движений не найдено.
                  </Typography>
                </TableCell>
              </TableRow>
            ) : (
              rows.map((row) => (
                <TableRow key={row.product_id} data-testid={`ff-reports-row-${row.product_id}`}>
                  <TableCell>
                    <ProductPhotoThumb src={row.photo_url} alt={row.product_name} />
                  </TableCell>
                  <TableCell sx={{ maxWidth: 260 }}>
                    <Typography variant="body2" title={row.product_name}>
                      {row.product_name}
                    </Typography>
                  </TableCell>
                  <TableCell>{row.wb_vendor_code ?? row.sku_code}</TableCell>
                  <TableCell>{row.wb_barcode ?? '—'}</TableCell>
                  <TableCell>{row.seller_name ?? '—'}</TableCell>
                  {visibleGroups.map((g) => {
                    const found = groupByKey(row, g.key)
                    return (
                      <Fragment key={g.key}>
                        <TableCell align="right">{found?.in_qty ? found.in_qty : '—'}</TableCell>
                        <TableCell align="right">{found?.out_qty ? found.out_qty : '—'}</TableCell>
                      </Fragment>
                    )
                  })}
                  <TableCell align="right" sx={{ fontWeight: 600 }}>
                    {row.total_in}
                  </TableCell>
                  <TableCell align="right" sx={{ fontWeight: 600 }}>
                    {row.total_out}
                  </TableCell>
                  <TableCell align="right" sx={{ fontWeight: 600 }}>
                    {row.net}
                  </TableCell>
                </TableRow>
              ))
            )}
          </TableBody>
        </Table>
      </TableContainer>

      <Typography variant="body2" color="text.secondary">
        Показано {rows.length} товар(ов). Данные читаются из журнала складских движений «как
        есть» — если сумма расходится с фактическим остатком, отчёт не исправляет расхождение, а
        помогает его увидеть.
      </Typography>
    </Stack>
  )
}
