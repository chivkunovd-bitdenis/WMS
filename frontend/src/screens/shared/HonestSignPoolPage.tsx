import { useCallback, useEffect, useMemo, useState } from 'react'
import { Link as RouterLink, useParams, useSearchParams } from 'react-router-dom'
import {
  Alert,
  Box,
  Button,
  Chip,
  Drawer,
  IconButton,
  MenuItem,
  Paper,
  Skeleton,
  Stack,
  Tab,
  Tabs,
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
import DownloadOutlined from '@mui/icons-material/DownloadOutlined'
import { apiUrl } from '../../api'
import { PageHeader } from '../../ui/PageHeader'
import { codeStatusLabel } from '../../utils/markingStatus'
import { readApiErrorMessage } from '../../utils/readApiErrorMessage'
import { codeStatusLabel, ledgerEventLabel } from '../../utils/markingStatus'
import { MarkingPoolProductsDialog } from './MarkingPoolProductsDialog'

type PoolDetail = {
  id: string
  seller_id: string
  title: string
  gtin: string
  products: { id: string; sku_code: string; name: string }[]
  available: number
  reserved: number
  printed: number
  defective: number
  forecast_days: number | null
  low_stock_threshold?: number | null
  forecast_days_threshold?: number | null
  consumption_7d?: number
  loaded?: number
  used?: number
  import_batches: {
    import_id: string
    document_number: string | null
    filename: string
    accepted_count: number
    created_at: string
  }[]
}

type PoolCode = {
  id: string
  cis_masked: string
  status: string
  created_at: string
  printed_by: string | null
  document_number: string | null
}

type HistoryEvent = {
  id: string
  created_at: string
  event_type: string
  document_number: string | null
  actor_email: string | null
}

type LedgerRow = {
  id: string
  created_at: string
  event_type: string
  cis_masked: string
  document_number: string | null
  actor_email: string | null
}

type TabKey = 'overview' | 'products' | 'codes' | 'ledger'

const STATUS_OPTIONS = ['', 'available', 'reserved', 'printed', 'applied', 'defective', 'void']

const LEDGER_PREVIEW_LIMIT = 5

type Props = {
  token: string
  testIdPrefix?: string
  routeBase?: string
}

export function HonestSignPoolPage({
  token,
  testIdPrefix = 'honest-sign-pool',
  routeBase = '/app/ff',
}: Props) {
  const { poolId } = useParams<{ poolId: string }>()
  const [searchParams, setSearchParams] = useSearchParams()
  const tab = (searchParams.get('tab') as TabKey | null) ?? 'overview'

  const [detail, setDetail] = useState<PoolDetail | null>(null)
  const [codes, setCodes] = useState<PoolCode[]>([])
  const [ledger, setLedger] = useState<LedgerRow[]>([])
  const [busy, setBusy] = useState(false)
  const [codesBusy, setCodesBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [statusFilter, setStatusFilter] = useState('')
  const [codeSearch, setCodeSearch] = useState('')
  const [linkOpen, setLinkOpen] = useState(false)
  const [historyCodeId, setHistoryCodeId] = useState<string | null>(null)
  const [history, setHistory] = useState<HistoryEvent[]>([])
  const [historyBusy, setHistoryBusy] = useState(false)
  const [lowThreshold, setLowThreshold] = useState('')
  const [forecastThreshold, setForecastThreshold] = useState('')
  const [thresholdSaving, setThresholdSaving] = useState(false)
  const [exportBusy, setExportBusy] = useState(false)

  const authHeaders = useMemo(
    () => ({ Authorization: `Bearer ${token}` }),
    [token],
  )

  const loadDetail = useCallback(async () => {
    if (!poolId) {
      return
    }
    setBusy(true)
    setError(null)
    try {
      const res = await fetch(apiUrl(`/operations/marking-codes/pools/${poolId}`), {
        headers: authHeaders,
      })
      if (!res.ok) {
        setError(await readApiErrorMessage(res))
        return
      }
      const body = (await res.json()) as PoolDetail
      setDetail(body)
      setLowThreshold(
        body.low_stock_threshold != null ? String(body.low_stock_threshold) : '',
      )
      setForecastThreshold(
        body.forecast_days_threshold != null ? String(body.forecast_days_threshold) : '',
      )
    } finally {
      setBusy(false)
    }
  }, [authHeaders, poolId])

  const loadCodes = useCallback(async () => {
    if (!poolId) {
      return
    }
    setCodesBusy(true)
    try {
      const q = statusFilter ? `?status=${encodeURIComponent(statusFilter)}` : ''
      const res = await fetch(apiUrl(`/operations/marking-codes/pools/${poolId}/codes${q}`), {
        headers: authHeaders,
      })
      if (res.ok) {
        setCodes((await res.json()) as PoolCode[])
      }
    } finally {
      setCodesBusy(false)
    }
  }, [authHeaders, poolId, statusFilter])

  const loadLedger = useCallback(async () => {
    if (!poolId) {
      return
    }
    const res = await fetch(
      apiUrl(
        `/operations/marking-codes/ledger?pool_id=${encodeURIComponent(poolId)}&limit=${LEDGER_PREVIEW_LIMIT}`,
      ),
      { headers: authHeaders },
    )
    if (res.ok) {
      const data = (await res.json()) as { rows: LedgerRow[] }
      setLedger(data.rows)
    }
  }, [authHeaders, poolId])

  useEffect(() => {
    void loadDetail()
  }, [loadDetail])

  useEffect(() => {
    if (tab === 'codes') {
      void loadCodes()
    }
    if (tab === 'ledger') {
      void loadLedger()
    }
  }, [tab, loadCodes, loadLedger])

  const setTab = (next: TabKey) => {
    setSearchParams(next === 'overview' ? {} : { tab: next })
  }

  const filteredCodes = useMemo(() => {
    const tail = codeSearch.trim()
    if (!tail) {
      return codes
    }
    return codes.filter((c) => c.cis_masked.includes(tail))
  }, [codeSearch, codes])

  const poolCodesTotal = detail?.loaded ?? codes.length
  const isDisplayFiltered = filteredCodes.length !== codes.length
  const isExportSubsetOfPool =
    statusFilter !== '' && codes.length > 0 && codes.length < poolCodesTotal

  const buildCodesCsv = (rows: PoolCode[]) => {
    const header = 'cis_masked,status,created_at,printed_by,document_number'
    const lines = rows.map(
      (c) =>
        `${c.cis_masked},${c.status},${c.created_at},${c.printed_by ?? ''},${c.document_number ?? ''}`,
    )
    return [header, ...lines].join('\n')
  }

  const downloadCsv = (filename: string, content: string) => {
    const blob = new Blob([content], { type: 'text/csv;charset=utf-8' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = filename
    a.click()
    URL.revokeObjectURL(url)
  }

  const exportCsv = async () => {
    if (!poolId) {
      return
    }
    setExportBusy(true)
    setError(null)
    try {
      const q = statusFilter ? `?status=${encodeURIComponent(statusFilter)}` : ''
      const res = await fetch(apiUrl(`/operations/marking-codes/pools/${poolId}/codes${q}`), {
        headers: authHeaders,
      })
      if (!res.ok) {
        setError(await readApiErrorMessage(res))
        return
      }
      const exportRows = (await res.json()) as PoolCode[]
      setCodes(exportRows)
      downloadCsv(`pool-${poolId}-codes.csv`, buildCodesCsv(exportRows))
    } finally {
      setExportBusy(false)
    }
  }

  const saveThresholds = async () => {
    if (!poolId) return
    setThresholdSaving(true)
    setError(null)
    try {
      const res = await fetch(apiUrl(`/operations/marking-codes/pools/${poolId}/threshold`), {
        method: 'PUT',
        headers: { ...authHeaders, 'Content-Type': 'application/json' },
        body: JSON.stringify({
          low_stock_threshold: lowThreshold.trim() ? Number(lowThreshold) : null,
          forecast_days_threshold: forecastThreshold.trim() ? Number(forecastThreshold) : null,
        }),
      })
      if (!res.ok) {
        setError(await readApiErrorMessage(res))
        return
      }
      await loadDetail()
    } finally {
      setThresholdSaving(false)
    }
  }

  const openHistory = async (codeId: string) => {
    setHistoryCodeId(codeId)
    setHistoryBusy(true)
    try {
      const res = await fetch(apiUrl(`/operations/marking-codes/codes/${codeId}/history`), {
        headers: authHeaders,
      })
      if (res.ok) {
        setHistory((await res.json()) as HistoryEvent[])
      }
    } finally {
      setHistoryBusy(false)
    }
  }

  if (!poolId) {
    return null
  }

  return (
    <Stack spacing={2} data-testid={`${testIdPrefix}-page`}>
      <Stack direction="row" spacing={1} sx={{ alignItems: 'center' }}>
        <IconButton
          component={RouterLink}
          to={`${routeBase}/honest-sign`}
          aria-label="Назад к списку пулов"
          data-testid={`${testIdPrefix}-back`}
        >
          <ArrowBackOutlined />
        </IconButton>
        <PageHeader
          title={detail?.title ?? 'Карточка пула'}
          description={detail ? `GTIN ${detail.gtin}` : 'Загрузка…'}
        />
      </Stack>

      {error ? (
        <Alert severity="error" data-testid={`${testIdPrefix}-error`}>
          {error}
        </Alert>
      ) : null}

      <Tabs value={tab} onChange={(_, v: TabKey) => setTab(v)} data-testid={`${testIdPrefix}-tabs`}>
        <Tab label="Обзор" value="overview" data-testid={`${testIdPrefix}-tab-overview`} />
        <Tab label="Товары" value="products" data-testid={`${testIdPrefix}-tab-products`} />
        <Tab label="Коды" value="codes" data-testid={`${testIdPrefix}-tab-codes`} />
        <Tab label="Лента" value="ledger" data-testid={`${testIdPrefix}-tab-ledger`} />
      </Tabs>

      {busy && !detail ? (
        <Skeleton height={120} />
      ) : null}

      {tab === 'overview' && detail ? (
        <Stack spacing={2} data-testid={`${testIdPrefix}-overview`}>
          <Stack direction="row" spacing={1} sx={{ flexWrap: 'wrap' }}>
            {[
              ['Доступно', detail.available],
              ['Резерв', detail.reserved],
              ['Напечатано', detail.printed],
              ['Брак', detail.defective],
              ['Расход 7д', detail.consumption_7d ?? '—'],
              ['Прогноз', detail.forecast_days ?? '—'],
            ].map(([label, value]) => (
              <Paper key={String(label)} variant="outlined" sx={{ p: 1.5, minWidth: 120 }}>
                <Typography variant="caption" color="text.secondary">
                  {label}
                </Typography>
                <Typography variant="h6">{value}</Typography>
              </Paper>
            ))}
          </Stack>
          <Paper variant="outlined" sx={{ p: 2 }} data-testid={`${testIdPrefix}-thresholds`}>
            <Typography variant="subtitle2" sx={{ mb: 1 }}>
              Пороги остатка
            </Typography>
            <Stack direction={{ xs: 'column', sm: 'row' }} spacing={1.5} sx={{ alignItems: { sm: 'flex-end' } }}>
              <TextField
                size="small"
                label="Мин. остаток"
                type="number"
                value={lowThreshold}
                onChange={(e) => setLowThreshold(e.target.value)}
                data-testid={`${testIdPrefix}-threshold-low`}
              />
              <TextField
                size="small"
                label="Прогноз, дней"
                type="number"
                value={forecastThreshold}
                onChange={(e) => setForecastThreshold(e.target.value)}
                data-testid={`${testIdPrefix}-threshold-forecast`}
              />
              <Button
                variant="contained"
                size="small"
                disabled={thresholdSaving}
                onClick={() => void saveThresholds()}
                data-testid={`${testIdPrefix}-threshold-save`}
              >
                Сохранить
              </Button>
            </Stack>
          </Paper>
          <Typography variant="subtitle2">История загрузок</Typography>
          <TableContainer component={Paper} variant="outlined">
            <Table size="small">
              <TableHead>
                <TableRow>
                  <TableCell>Документ</TableCell>
                  <TableCell>Файл</TableCell>
                  <TableCell align="right">Принято</TableCell>
                  <TableCell>Дата</TableCell>
                </TableRow>
              </TableHead>
              <TableBody>
                {detail.import_batches.length === 0 ? (
                  <TableRow>
                    <TableCell colSpan={4}>
                      <Typography variant="body2" color="text.secondary">
                        Загрузок пока нет.
                      </Typography>
                    </TableCell>
                  </TableRow>
                ) : (
                  detail.import_batches.map((b) => (
                    <TableRow key={b.import_id} data-testid={`${testIdPrefix}-batch-${b.import_id}`}>
                      <TableCell>{b.document_number ?? '—'}</TableCell>
                      <TableCell>{b.filename}</TableCell>
                      <TableCell align="right">{b.accepted_count}</TableCell>
                      <TableCell>{new Date(b.created_at).toLocaleString('ru-RU')}</TableCell>
                    </TableRow>
                  ))
                )}
              </TableBody>
            </Table>
          </TableContainer>
        </Stack>
      ) : null}

      {tab === 'products' && detail ? (
        <Stack spacing={2} data-testid={`${testIdPrefix}-products`}>
          <Alert severity="info">Остаток КМ общий на весь пул, не на каждый товар.</Alert>
          <Button variant="outlined" onClick={() => setLinkOpen(true)} data-testid={`${testIdPrefix}-link-products`}>
            Привязать товары
          </Button>
          <Stack direction="row" spacing={0.75} sx={{ flexWrap: 'wrap' }}>
            {detail.products.map((p) => (
              <Chip key={p.id} label={`${p.sku_code} — ${p.name}`} data-testid={`${testIdPrefix}-product-${p.id}`} />
            ))}
          </Stack>
        </Stack>
      ) : null}

      {tab === 'codes' ? (
        <Stack spacing={1.5} data-testid={`${testIdPrefix}-codes`}>
          <Stack direction={{ xs: 'column', sm: 'row' }} spacing={1}>
            <TextField
              select
              size="small"
              label="Статус"
              value={statusFilter}
              onChange={(e) => setStatusFilter(e.target.value)}
              sx={{ minWidth: 160 }}
              data-testid={`${testIdPrefix}-codes-status`}
            >
              <MenuItem value="">Все</MenuItem>
              {STATUS_OPTIONS.filter(Boolean).map((s) => (
                <MenuItem key={s} value={s}>
                  {codeStatusLabel(s)}
                </MenuItem>
              ))}
            </TextField>
            <TextField
              size="small"
              label="Хвост КМ"
              value={codeSearch}
              onChange={(e) => setCodeSearch(e.target.value)}
              sx={{ flex: 1 }}
              data-testid={`${testIdPrefix}-codes-search`}
            />
            <Button
              variant="outlined"
              startIcon={<DownloadOutlined />}
              onClick={() => void exportCsv()}
              disabled={codes.length === 0 || exportBusy || codesBusy}
              data-testid={`${testIdPrefix}-codes-export`}
            >
              {exportBusy
                ? 'Экспорт…'
                : isExportSubsetOfPool
                  ? `Экспорт CSV (${codes.length} из ${poolCodesTotal})`
                  : `Экспорт CSV (${codes.length})`}
            </Button>
          </Stack>
          {isDisplayFiltered ? (
            <Typography
              variant="body2"
              color="text.secondary"
              data-testid={`${testIdPrefix}-codes-count`}
            >
              Показано {filteredCodes.length} из {codes.length}. Экспорт выгружает все{' '}
              {codes.length} кодов текущей выборки.
            </Typography>
          ) : isExportSubsetOfPool ? (
            <Typography
              variant="body2"
              color="text.secondary"
              data-testid={`${testIdPrefix}-codes-count`}
            >
              В выборке {codes.length} из {poolCodesTotal} кодов пула (фильтр по статусу). Экспорт
              выгружает все {codes.length} кодов выборки.
            </Typography>
          ) : codes.length > 0 ? (
            <Typography
              variant="body2"
              color="text.secondary"
              data-testid={`${testIdPrefix}-codes-count`}
            >
              {codes.length} кодов
            </Typography>
          ) : null}
          <TableContainer component={Paper} variant="outlined">
            <Table size="small">
              <TableHead>
                <TableRow>
                  <TableCell>КМ</TableCell>
                  <TableCell>Статус</TableCell>
                  <TableCell>Дата</TableCell>
                  <TableCell>Документ</TableCell>
                  <TableCell />
                </TableRow>
              </TableHead>
              <TableBody>
                {codesBusy ? (
                  <TableRow>
                    <TableCell colSpan={5}>
                      <Skeleton height={32} />
                    </TableCell>
                  </TableRow>
                ) : filteredCodes.length === 0 ? (
                  <TableRow>
                    <TableCell colSpan={5}>
                      <Typography variant="body2" color="text.secondary">
                        Коды не найдены.
                      </Typography>
                    </TableCell>
                  </TableRow>
                ) : (
                  filteredCodes.map((c) => (
                    <TableRow key={c.id} data-testid={`${testIdPrefix}-code-row-${c.id}`}>
                      <TableCell>{c.cis_masked}</TableCell>
                      <TableCell>
                        <Chip size="small" label={codeStatusLabel(c.status)} />
                      </TableCell>
                      <TableCell>{new Date(c.created_at).toLocaleString('ru-RU')}</TableCell>
                      <TableCell>{c.document_number ?? '—'}</TableCell>
                      <TableCell>
                        <Button size="small" onClick={() => void openHistory(c.id)}>
                          История
                        </Button>
                      </TableCell>
                    </TableRow>
                  ))
                )}
              </TableBody>
            </Table>
          </TableContainer>
        </Stack>
      ) : null}

      {tab === 'ledger' ? (
        <Stack spacing={1.5} data-testid={`${testIdPrefix}-ledger-preview`}>
          <Stack
            direction={{ xs: 'column', sm: 'row' }}
            spacing={1}
            sx={{ alignItems: { sm: 'center' }, justifyContent: 'space-between' }}
          >
            <Typography variant="subtitle2">
              Последние {LEDGER_PREVIEW_LIMIT} событий
            </Typography>
            <Button
              component={RouterLink}
              to={`${routeBase}/honest-sign/ledger?pool_id=${encodeURIComponent(poolId)}`}
              variant="outlined"
              size="small"
              data-testid={`${testIdPrefix}-ledger-open-full`}
            >
              Вся лента пула
            </Button>
          </Stack>
          <TableContainer component={Paper} variant="outlined">
            <Table size="small">
              <TableHead>
                <TableRow>
                  <TableCell>Время</TableCell>
                  <TableCell>Событие</TableCell>
                  <TableCell>КМ</TableCell>
                </TableRow>
              </TableHead>
              <TableBody>
                {ledger.length === 0 ? (
                  <TableRow>
                    <TableCell colSpan={3}>
                      <Typography variant="body2" color="text.secondary">
                        Событий пока нет.
                      </Typography>
                    </TableCell>
                  </TableRow>
                ) : (
                  ledger.map((row) => (
                    <TableRow key={row.id} data-testid={`${testIdPrefix}-ledger-row-${row.id}`}>
                      <TableCell>{new Date(row.created_at).toLocaleString('ru-RU')}</TableCell>
                      <TableCell>
                        <Chip size="small" label={ledgerEventLabel(row.event_type)} />
                      </TableCell>
                      <TableCell>{row.cis_masked}</TableCell>
                    </TableRow>
                  ))
                )}
              </TableBody>
            </Table>
          </TableContainer>
        </Stack>
      ) : null}

      {detail && linkOpen ? (
        <MarkingPoolProductsDialog
          open
          token={token}
          poolId={detail.id}
          poolTitle={detail.title}
          sellerId={detail.seller_id}
          linkedProducts={detail.products}
          testIdPrefix={testIdPrefix.replace('-pool', '')}
          onClose={() => setLinkOpen(false)}
          onSaved={(products) => {
            setDetail((prev) => (prev ? { ...prev, products } : prev))
            setLinkOpen(false)
          }}
        />
      ) : null}

      <Drawer
        anchor="right"
        open={historyCodeId != null}
        onClose={() => setHistoryCodeId(null)}
        data-testid={`${testIdPrefix}-history-drawer`}
      >
        <Box sx={{ width: 360, p: 2 }}>
          <Typography variant="h6" sx={{ mb: 2 }}>
            История КМ
          </Typography>
          {historyBusy ? (
            <Skeleton height={80} />
          ) : (
            <Stack spacing={1.5}>
              {history.map((ev) => (
                <Paper key={ev.id} variant="outlined" sx={{ p: 1.5 }}>
                  <Typography variant="subtitle2">{ledgerEventLabel(ev.event_type)}</Typography>
                  <Typography variant="caption" color="text.secondary">
                    {new Date(ev.created_at).toLocaleString('ru-RU')}
                  </Typography>
                  {ev.document_number ? (
                    <Typography variant="body2">Документ: {ev.document_number}</Typography>
                  ) : null}
                  {ev.actor_email ? (
                    <Typography variant="body2">{ev.actor_email}</Typography>
                  ) : null}
                </Paper>
              ))}
            </Stack>
          )}
        </Box>
      </Drawer>
    </Stack>
  )
}
