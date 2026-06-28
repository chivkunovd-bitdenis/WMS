import { useCallback, useEffect, useMemo, useState } from 'react'
import { Link as RouterLink, useSearchParams } from 'react-router-dom'
import {
  Alert,
  Button,
  Chip,
  IconButton,
  MenuItem,
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
import ArrowBackOutlined from '@mui/icons-material/ArrowBackOutlined'
import FileDownloadOutlined from '@mui/icons-material/FileDownloadOutlined'
import { apiUrl } from '../../api'
import { useDebouncedValue } from '../../hooks/useDebouncedValue'
import { PageHeader } from '../../ui/PageHeader'
import { readApiErrorMessage } from '../../utils/readApiErrorMessage'
import { MarkingSellerPicker } from './MarkingSellerPicker'
import { ledgerEventLabel } from '../../utils/markingStatus'

const TEXT_FILTER_DEBOUNCE_MS = 400

type LedgerRow = {
  id: string
  created_at: string
  event_type: string
  cis_masked: string
  pool_title: string | null
  product_name: string | null
  product_sku: string | null
  seller_name: string | null
  document_number: string | null
  actor_email: string | null
}

type Props = {
  token: string
  testIdPrefix?: string
  routeBase?: string
  sellers?: { id: string; name: string }[]
  selectedSellerId?: string | null
  onSelectedSellerIdChange?: (id: string | null) => void
}

const EVENT_TYPES = ['', 'imported', 'printed', 'applied', 'shipped', 'voided', 'defective']

function toDateFromParam(isoDate: string): string {
  return `${isoDate}T00:00:00`
}

function toDateToParam(isoDate: string): string {
  return `${isoDate}T23:59:59`
}

export function HonestSignLedgerPage({
  token,
  testIdPrefix = 'honest-sign-ledger',
  routeBase = '/app/ff',
  sellers = [],
  selectedSellerId = null,
  onSelectedSellerIdChange,
}: Props) {
  const [searchParams] = useSearchParams()
  const poolIdFromUrl = searchParams.get('pool_id')
  const eventTypeFromUrl = searchParams.get('event_type') ?? ''

  const [rows, setRows] = useState<LedgerRow[]>([])
  const [total, setTotal] = useState(0)
  const [offset, setOffset] = useState(0)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [eventType, setEventType] = useState('')
  const [document, setDocument] = useState('')
  const [cisMask, setCisMask] = useState('')
  const [poolTitle, setPoolTitle] = useState<string | null>(null)
  const [dateFrom, setDateFrom] = useState('')
  const [dateTo, setDateTo] = useState('')
  const [exportBusy, setExportBusy] = useState(false)

  const debouncedDocument = useDebouncedValue(document, TEXT_FILTER_DEBOUNCE_MS)
  const debouncedCisMask = useDebouncedValue(cisMask, TEXT_FILTER_DEBOUNCE_MS)

  const limit = 50

  const authHeaders = useMemo(() => ({ Authorization: `Bearer ${token}` }), [token])

  const poolNameFromRows = useMemo(
    () => rows.find((r) => r.pool_title)?.pool_title ?? null,
    [rows],
  )
  const poolFilterLabel = poolTitle ?? poolNameFromRows

  const buildFilterParams = useCallback(() => {
    const params = new URLSearchParams()
    if (selectedSellerId) {
      params.set('seller_id', selectedSellerId)
    }
    if (poolIdFromUrl) {
      params.set('pool_id', poolIdFromUrl)
    }
    if (eventType) {
      params.set('event_type', eventType)
    }
    if (debouncedDocument.trim()) {
      params.set('document', debouncedDocument.trim())
    }
    const mask = debouncedCisMask.trim()
    if (mask) {
      params.set('cis_mask', mask)
    }
    if (dateFrom) {
      params.set('date_from', toDateFromParam(dateFrom))
    }
    if (dateTo) {
      params.set('date_to', toDateToParam(dateTo))
    }
    return params
  }, [
    dateFrom,
    dateTo,
    debouncedCisMask,
    debouncedDocument,
    eventType,
    poolIdFromUrl,
    selectedSellerId,
  ])

  const load = useCallback(async () => {
    setBusy(true)
    setError(null)
    try {
      const params = buildFilterParams()
      params.set('limit', String(limit))
      params.set('offset', String(offset))
      const res = await fetch(apiUrl(`/operations/marking-codes/ledger?${params.toString()}`), {
        headers: authHeaders,
      })
      if (!res.ok) {
        setError(await readApiErrorMessage(res))
        return
      }
      const data = (await res.json()) as { rows: LedgerRow[]; total: number }
      setRows(data.rows)
      setTotal(data.total)
    } finally {
      setBusy(false)
    }
  }, [authHeaders, buildFilterParams, offset])

  const exportCsv = async () => {
    setExportBusy(true)
    setError(null)
    try {
      const params = buildFilterParams()
      const res = await fetch(
        apiUrl(`/operations/marking-codes/ledger/export?${params.toString()}`),
        { headers: authHeaders },
      )
      if (!res.ok) {
        setError(await readApiErrorMessage(res))
        return
      }
      const blob = await res.blob()
      const url = URL.createObjectURL(blob)
      const a = window.document.createElement('a')
      a.href = url
      const disposition = res.headers.get('Content-Disposition')
      const match = disposition?.match(/filename="([^"]+)"/)
      a.download = match?.[1] ?? 'ledger-export.csv'
      a.click()
      URL.revokeObjectURL(url)
    } finally {
      setExportBusy(false)
    }
  }

  useEffect(() => {
    void load()
  }, [load])

  useEffect(() => {
    if (!poolIdFromUrl) {
      setPoolTitle(null)
      return
    }
    setPoolTitle(null)
    let cancelled = false
    void (async () => {
      const res = await fetch(
        apiUrl(`/operations/marking-codes/pools/${encodeURIComponent(poolIdFromUrl)}`),
        { headers: authHeaders },
      )
      if (cancelled || !res.ok) {
        return
      }
      const body = (await res.json()) as { title: string }
      if (!cancelled) {
        setPoolTitle(body.title)
      }
    })()
    return () => {
      cancelled = true
    }
  }, [authHeaders, poolIdFromUrl])

  useEffect(() => {
    if (eventTypeFromUrl && EVENT_TYPES.includes(eventTypeFromUrl)) {
      setEventType(eventTypeFromUrl)
      setOffset(0)
    }
  }, [eventTypeFromUrl])

  return (
    <Stack spacing={2} data-testid={`${testIdPrefix}-page`}>
      <Stack direction="row" spacing={1} sx={{ alignItems: 'center' }}>
        <IconButton component={RouterLink} to={`${routeBase}/honest-sign`} data-testid={`${testIdPrefix}-back`}>
          <ArrowBackOutlined />
        </IconButton>
        <PageHeader title="Лента расхода" description="События по КМ." />
      </Stack>

      <MarkingSellerPicker
        sellers={sellers}
        selectedSellerId={selectedSellerId}
        onSelectedSellerIdChange={(id) => {
          setOffset(0)
          onSelectedSellerIdChange?.(id)
        }}
        testIdPrefix={testIdPrefix}
      />

      {poolIdFromUrl ? (
        <Alert severity="info" data-testid={`${testIdPrefix}-pool-filter`}>
          Фильтр по пулу: {poolFilterLabel ?? '…'}
        </Alert>
      ) : null}

      {error ? (
        <Alert severity="error" data-testid={`${testIdPrefix}-error`}>
          {error}
        </Alert>
      ) : null}

      <Stack direction={{ xs: 'column', sm: 'row' }} spacing={1} sx={{ flexWrap: 'wrap' }}>
        <TextField
          select
          size="small"
          label="Тип события"
          value={eventType}
          onChange={(e) => {
            setOffset(0)
            setEventType(e.target.value)
          }}
          sx={{ minWidth: 160 }}
          data-testid={`${testIdPrefix}-event-type`}
        >
          <MenuItem value="">Все</MenuItem>
          {EVENT_TYPES.filter(Boolean).map((t) => (
            <MenuItem key={t} value={t}>
              {ledgerEventLabel(t)}
            </MenuItem>
          ))}
        </TextField>
        <TextField
          size="small"
          label="Документ"
          value={document}
          onChange={(e) => {
            setOffset(0)
            setDocument(e.target.value)
          }}
          data-testid={`${testIdPrefix}-document`}
        />
        <TextField
          size="small"
          label="С"
          type="date"
          value={dateFrom}
          onChange={(e) => {
            setOffset(0)
            setDateFrom(e.target.value)
          }}
          slotProps={{ inputLabel: { shrink: true } }}
          sx={{ minWidth: 150 }}
          data-testid={`${testIdPrefix}-date-from`}
        />
        <TextField
          size="small"
          label="По"
          type="date"
          value={dateTo}
          onChange={(e) => {
            setOffset(0)
            setDateTo(e.target.value)
          }}
          slotProps={{ inputLabel: { shrink: true } }}
          sx={{ minWidth: 150 }}
          data-testid={`${testIdPrefix}-date-to`}
        />
        <TextField
          size="small"
          label="Маска КМ"
          value={cisMask}
          onChange={(e) => {
            setOffset(0)
            setCisMask(e.target.value)
          }}
          data-testid={`${testIdPrefix}-cis-mask`}
        />
        <Button
          variant="outlined"
          startIcon={<FileDownloadOutlined />}
          disabled={exportBusy || busy}
          onClick={() => void exportCsv()}
          data-testid={`${testIdPrefix}-export`}
        >
          Экспорт
        </Button>
      </Stack>

      <TableContainer component={Paper} variant="outlined">
        <Table size="small" data-testid={`${testIdPrefix}-table`}>
          <TableHead>
            <TableRow>
              <TableCell>Время</TableCell>
              <TableCell>Событие</TableCell>
              <TableCell>КМ</TableCell>
              <TableCell>Пул / товар</TableCell>
              <TableCell>Селлер</TableCell>
              <TableCell>Документ</TableCell>
              <TableCell>Пользователь</TableCell>
            </TableRow>
          </TableHead>
          <TableBody>
            {busy ? (
              <TableRow>
                <TableCell colSpan={7}>
                  <Skeleton height={32} />
                </TableCell>
              </TableRow>
            ) : rows.length === 0 ? (
              <TableRow>
                <TableCell colSpan={7}>
                  <Typography variant="body2" color="text.secondary">
                    События не найдены.
                  </Typography>
                </TableCell>
              </TableRow>
            ) : (
              rows.map((row) => (
                <TableRow key={row.id} data-testid={`${testIdPrefix}-row-${row.id}`}>
                  <TableCell>{new Date(row.created_at).toLocaleString('ru-RU')}</TableCell>
                  <TableCell>
                    <Chip size="small" label={ledgerEventLabel(row.event_type)} />
                  </TableCell>
                  <TableCell>{row.cis_masked}</TableCell>
                  <TableCell>
                    {row.pool_title ?? '—'}
                    {row.product_sku ? ` / ${row.product_sku}` : ''}
                  </TableCell>
                  <TableCell>{row.seller_name ?? '—'}</TableCell>
                  <TableCell>{row.document_number ?? '—'}</TableCell>
                  <TableCell>{row.actor_email ?? '—'}</TableCell>
                </TableRow>
              ))
            )}
          </TableBody>
        </Table>
      </TableContainer>

      <Stack direction="row" spacing={1} sx={{ alignItems: 'center' }}>
        <Typography variant="body2" color="text.secondary">
          Показано {rows.length} из {total}
        </Typography>
        <Button
          size="small"
          disabled={offset === 0 || busy}
          onClick={() => setOffset((o) => Math.max(0, o - limit))}
          data-testid={`${testIdPrefix}-prev`}
        >
          Назад
        </Button>
        <Button
          size="small"
          disabled={offset + limit >= total || busy}
          onClick={() => setOffset((o) => o + limit)}
          data-testid={`${testIdPrefix}-next`}
        >
          Далее
        </Button>
      </Stack>
    </Stack>
  )
}
