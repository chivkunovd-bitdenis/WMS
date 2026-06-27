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
import { apiUrl } from '../../api'
import { PageHeader } from '../../ui/PageHeader'
import { readApiErrorMessage } from '../../utils/readApiErrorMessage'

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

  const [rows, setRows] = useState<LedgerRow[]>([])
  const [total, setTotal] = useState(0)
  const [offset, setOffset] = useState(0)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [eventType, setEventType] = useState('')
  const [document, setDocument] = useState('')
  const [cisMask, setCisMask] = useState('')

  const limit = 50

  const authHeaders = useMemo(() => ({ Authorization: `Bearer ${token}` }), [token])

  const load = useCallback(async () => {
    setBusy(true)
    setError(null)
    try {
      const params = new URLSearchParams()
      params.set('limit', String(limit))
      params.set('offset', String(offset))
      if (selectedSellerId) {
        params.set('seller_id', selectedSellerId)
      }
      if (poolIdFromUrl) {
        params.set('pool_id', poolIdFromUrl)
      }
      if (eventType) {
        params.set('event_type', eventType)
      }
      if (document.trim()) {
        params.set('document', document.trim())
      }
      const res = await fetch(apiUrl(`/operations/marking-codes/ledger?${params.toString()}`), {
        headers: authHeaders,
      })
      if (!res.ok) {
        setError(await readApiErrorMessage(res))
        return
      }
      const data = (await res.json()) as { rows: LedgerRow[]; total: number }
      let nextRows = data.rows
      const mask = cisMask.trim()
      if (mask) {
        nextRows = nextRows.filter((r) => r.cis_masked.includes(mask))
      }
      setRows(nextRows)
      setTotal(data.total)
    } finally {
      setBusy(false)
    }
  }, [
    authHeaders,
    cisMask,
    document,
    eventType,
    offset,
    poolIdFromUrl,
    selectedSellerId,
  ])

  useEffect(() => {
    void load()
  }, [load])

  return (
    <Stack spacing={2} data-testid={`${testIdPrefix}-page`}>
      <Stack direction="row" spacing={1} sx={{ alignItems: 'center' }}>
        <IconButton component={RouterLink} to={`${routeBase}/honest-sign`} data-testid={`${testIdPrefix}-back`}>
          <ArrowBackOutlined />
        </IconButton>
        <PageHeader title="Лента расхода" description="События по кодам маркировки." />
      </Stack>

      {sellers.length > 0 ? (
        <Stack direction="row" spacing={1} sx={{ flexWrap: 'wrap' }}>
          {sellers.map((s) => (
            <Button
              key={s.id}
              size="small"
              variant={selectedSellerId === s.id ? 'contained' : 'outlined'}
              onClick={() => {
                setOffset(0)
                onSelectedSellerIdChange?.(s.id)
              }}
              data-testid={`${testIdPrefix}-seller-${s.id}`}
            >
              {s.name}
            </Button>
          ))}
        </Stack>
      ) : null}

      {poolIdFromUrl ? (
        <Alert severity="info">Фильтр по пулу: {poolIdFromUrl}</Alert>
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
              {t}
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
          label="Маска КМ"
          value={cisMask}
          onChange={(e) => setCisMask(e.target.value)}
          data-testid={`${testIdPrefix}-cis-mask`}
        />
        <Button variant="outlined" onClick={() => void load()} data-testid={`${testIdPrefix}-apply`}>
          Применить
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
                    <Chip size="small" label={row.event_type} />
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
