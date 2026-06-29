import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { Link as RouterLink, useParams, useSearchParams } from 'react-router-dom'
import {
  Alert,
  Box,
  Button,
  Chip,
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
import ChevronRightOutlined from '@mui/icons-material/ChevronRightOutlined'
import { apiUrl } from '../../api'
import { PageHeader } from '../../ui/PageHeader'
import { codeStatusLabel, ledgerEventLabel } from '../../utils/markingStatus'
import { maskCisCode } from '../../utils/printMarkingCodeLabel'
import { readApiErrorMessage } from '../../utils/readApiErrorMessage'

type MarkingOverviewProduct = {
  id: string
  sku_code: string
  name: string
  requires_honest_sign: boolean
}

type PersonalPool = {
  pool_id: string
  gtin: string
  title: string
  available: number
  printed: number
  loaded: number
}

type SharedBasket = {
  pool_id: string
  gtin: string
  title: string
  available: number
  products_count: number
}

type MarkingOverview = {
  product: MarkingOverviewProduct
  personal_pools: PersonalPool[]
  shared_baskets: SharedBasket[]
}

type ProductCode = {
  id: string
  cis_code: string
  status: string
  created_at: string
}

type LedgerRow = {
  id: string
  created_at: string
  event_type: string
  cis_masked: string
  document_number: string | null
  actor_email: string | null
}

type TabKey = 'codes' | 'ledger'

type PoolThresholdDetail = {
  low_stock_threshold: number | null
  forecast_days_threshold: number | null
}

const STATUS_OPTIONS = ['', 'available', 'reserved', 'printed', 'applied', 'defective', 'void']

const LEDGER_PREVIEW_LIMIT = 5

type Props = {
  token: string
  testIdPrefix?: string
  routeBase?: string
}

export function HonestSignProductPage({
  token,
  testIdPrefix = 'honest-sign-product',
  routeBase = '/app/ff',
}: Props) {
  const { productId } = useParams<{ productId: string }>()
  const [searchParams, setSearchParams] = useSearchParams()
  const tabParam = searchParams.get('tab')
  const tab: TabKey | null = tabParam === 'codes' || tabParam === 'ledger' ? tabParam : null

  const [overview, setOverview] = useState<MarkingOverview | null>(null)
  const [codes, setCodes] = useState<ProductCode[]>([])
  const [ledger, setLedger] = useState<LedgerRow[]>([])
  const [busy, setBusy] = useState(false)
  const [codesBusy, setCodesBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [statusFilter, setStatusFilter] = useState('')
  const [lowThreshold, setLowThreshold] = useState('')
  const [forecastDaysThreshold, setForecastDaysThreshold] = useState('')
  const [thresholdLoading, setThresholdLoading] = useState(false)
  const [thresholdSaving, setThresholdSaving] = useState(false)
  const [thresholdError, setThresholdError] = useState<string | null>(null)
  const loadRequestId = useRef(0)
  const codesRequestId = useRef(0)
  const thresholdRequestId = useRef(0)
  const ledgerAbortRef = useRef<AbortController | null>(null)

  const authHeaders = useMemo(
    () => ({ Authorization: `Bearer ${token}` }),
    [token],
  )

  const loadOverview = useCallback(async () => {
    if (!productId) {
      return
    }
    const requestId = ++loadRequestId.current
    setBusy(true)
    setError(null)
    try {
      const res = await fetch(
        apiUrl(`/operations/marking-codes/products/${productId}/marking-overview`),
        { headers: authHeaders },
      )
      if (requestId !== loadRequestId.current) {
        return
      }
      if (!res.ok) {
        setError(await readApiErrorMessage(res))
        setOverview(null)
        return
      }
      setOverview((await res.json()) as MarkingOverview)
    } finally {
      if (requestId === loadRequestId.current) {
        setBusy(false)
      }
    }
  }, [authHeaders, productId])

  const loadCodes = useCallback(async () => {
    if (!productId) {
      return
    }
    const requestId = ++codesRequestId.current
    setCodesBusy(true)
    try {
      const res = await fetch(
        apiUrl(`/operations/marking-codes/products/${productId}/codes`),
        { headers: authHeaders },
      )
      if (requestId !== codesRequestId.current) {
        return
      }
      if (res.ok) {
        setCodes((await res.json()) as ProductCode[])
      }
    } finally {
      if (requestId === codesRequestId.current) {
        setCodesBusy(false)
      }
    }
  }, [authHeaders, productId])

  const loadLedger = useCallback(async () => {
    if (!productId) {
      return
    }
    ledgerAbortRef.current?.abort()
    const ac = new AbortController()
    ledgerAbortRef.current = ac
    try {
      const res = await fetch(
        apiUrl(
          `/operations/marking-codes/ledger?product_id=${encodeURIComponent(productId)}&limit=${LEDGER_PREVIEW_LIMIT}`,
        ),
        { headers: authHeaders, signal: ac.signal },
      )
      if (ac.signal.aborted) {
        return
      }
      if (res.ok) {
        const data = (await res.json()) as { rows: LedgerRow[] }
        if (!ac.signal.aborted) {
          setLedger(data.rows)
        }
      }
    } catch (err) {
      if (err instanceof DOMException && err.name === 'AbortError') {
        return
      }
      throw err
    }
  }, [authHeaders, productId])

  useEffect(() => {
    void loadOverview()
  }, [loadOverview])

  useEffect(() => {
    if (tab === 'codes') {
      void loadCodes()
    }
    if (tab === 'ledger') {
      void loadLedger()
    }
    return () => {
      ledgerAbortRef.current?.abort()
    }
  }, [tab, loadCodes, loadLedger])

  const filteredCodes = useMemo(() => {
    if (!statusFilter) {
      return codes
    }
    return codes.filter((c) => c.status === statusFilter)
  }, [codes, statusFilter])

  const personalAvailable = useMemo(
    () => (overview?.personal_pools ?? []).reduce((sum, pool) => sum + pool.available, 0),
    [overview],
  )

  const personalPools = overview?.personal_pools ?? []
  const singlePersonalPool =
    personalPools.length === 1 ? personalPools[0] : null
  const hasMultiplePersonalPools = personalPools.length > 1

  const sharedBasketsCount = overview?.shared_baskets.length ?? 0

  const loadThreshold = useCallback(
    async (poolId: string) => {
      const requestId = ++thresholdRequestId.current
      setThresholdLoading(true)
      setThresholdError(null)
      try {
        const res = await fetch(apiUrl(`/operations/marking-codes/pools/${poolId}`), {
          headers: authHeaders,
        })
        if (requestId !== thresholdRequestId.current) {
          return
        }
        if (!res.ok) {
          setThresholdError(await readApiErrorMessage(res))
          return
        }
        const body = (await res.json()) as PoolThresholdDetail
        if (requestId !== thresholdRequestId.current) {
          return
        }
        setLowThreshold(
          body.low_stock_threshold != null ? String(body.low_stock_threshold) : '',
        )
        setForecastDaysThreshold(
          body.forecast_days_threshold != null
            ? String(body.forecast_days_threshold)
            : '',
        )
      } finally {
        if (requestId === thresholdRequestId.current) {
          setThresholdLoading(false)
        }
      }
    },
    [authHeaders],
  )

  const saveThreshold = useCallback(async () => {
    if (!singlePersonalPool) {
      return
    }
    setThresholdSaving(true)
    setThresholdError(null)
    try {
      const res = await fetch(
        apiUrl(
          `/operations/marking-codes/pools/${singlePersonalPool.pool_id}/threshold`,
        ),
        {
          method: 'PUT',
          headers: { ...authHeaders, 'Content-Type': 'application/json' },
          body: JSON.stringify({
            low_stock_threshold: lowThreshold.trim() ? Number(lowThreshold) : null,
            forecast_days_threshold: forecastDaysThreshold.trim()
              ? Number(forecastDaysThreshold)
              : null,
          }),
        },
      )
      if (!res.ok) {
        setThresholdError(await readApiErrorMessage(res))
        return
      }
      const body = (await res.json()) as PoolThresholdDetail
      setLowThreshold(
        body.low_stock_threshold != null ? String(body.low_stock_threshold) : '',
      )
      setForecastDaysThreshold(
        body.forecast_days_threshold != null
          ? String(body.forecast_days_threshold)
          : '',
      )
    } finally {
      setThresholdSaving(false)
    }
  }, [
    authHeaders,
    forecastDaysThreshold,
    lowThreshold,
    singlePersonalPool,
  ])

  useEffect(() => {
    if (!singlePersonalPool) {
      setLowThreshold('')
      setForecastDaysThreshold('')
      setThresholdError(null)
      return
    }
    void loadThreshold(singlePersonalPool.pool_id)
  }, [loadThreshold, singlePersonalPool])

  const setTab = (next: TabKey | null) => {
    setSearchParams(next ? { tab: next } : {})
  }

  if (!productId) {
    return null
  }

  const product = overview?.product

  return (
    <Stack spacing={2} data-testid={`${testIdPrefix}-page`}>
      <Stack direction="row" spacing={1} sx={{ alignItems: 'flex-start', flexWrap: 'wrap' }}>
        <IconButton
          component={RouterLink}
          to={`${routeBase}/honest-sign`}
          aria-label="Назад к списку"
          data-testid={`${testIdPrefix}-back`}
          sx={{ mt: 0.5 }}
        >
          <ArrowBackOutlined />
        </IconButton>
        <Box sx={{ flex: 1, minWidth: 200 }}>
          <Stack direction="row" spacing={1} sx={{ alignItems: 'center', flexWrap: 'wrap' }}>
            <PageHeader
              title={product?.name ?? 'Карточка товара'}
              description={product ? `SKU ${product.sku_code}` : 'Загрузка…'}
            />
            {product?.requires_honest_sign ? (
              <Chip
                label="Нужен ЧЗ"
                color="primary"
                size="small"
                data-testid={`${testIdPrefix}-badge-honest-sign`}
              />
            ) : null}
          </Stack>
        </Box>
      </Stack>

      {error ? (
        <Alert severity="error" data-testid={`${testIdPrefix}-error`}>
          {error}
        </Alert>
      ) : null}

      {busy && !overview ? (
        <Skeleton height={120} data-testid={`${testIdPrefix}-loading`} />
      ) : null}

      {overview ? (
        <Stack spacing={2} data-testid={`${testIdPrefix}-overview`}>
          <Stack direction="row" spacing={1} sx={{ flexWrap: 'wrap' }}>
            <Paper variant="outlined" sx={{ p: 1.5, minWidth: 180 }}>
              <Typography variant="caption" color="text.secondary">
                Доступно личных
              </Typography>
              <Typography variant="h6" data-testid={`${testIdPrefix}-personal-available`}>
                {personalAvailable}
              </Typography>
            </Paper>
            <Paper variant="outlined" sx={{ p: 1.5, minWidth: 180 }}>
              <Typography variant="caption" color="text.secondary">
                Доступ к общим корзинам
              </Typography>
              <Typography variant="h6" data-testid={`${testIdPrefix}-shared-baskets-count`}>
                {sharedBasketsCount}
              </Typography>
            </Paper>
          </Stack>

          {hasMultiplePersonalPools ? (
            <Alert
              severity="warning"
              data-testid={`${testIdPrefix}-threshold-multiple-pools`}
            >
              У товара несколько личных пулов — настройка порога остатка для каждого пула пока
              недоступна (TODO).
            </Alert>
          ) : null}

          {singlePersonalPool ? (
            <Paper variant="outlined" sx={{ p: 2 }} data-testid={`${testIdPrefix}-threshold`}>
              <Typography variant="subtitle1" sx={{ mb: 1.5 }}>
                Порог остатка
              </Typography>
              {thresholdError ? (
                <Alert severity="error" sx={{ mb: 1.5 }} data-testid={`${testIdPrefix}-threshold-error`}>
                  {thresholdError}
                </Alert>
              ) : null}
              <Stack
                direction={{ xs: 'column', sm: 'row' }}
                spacing={1.5}
                sx={{ alignItems: { sm: 'flex-end' } }}
              >
                <TextField
                  size="small"
                  label="Мин. остаток"
                  type="number"
                  value={lowThreshold}
                  onChange={(e) => setLowThreshold(e.target.value)}
                  disabled={thresholdLoading || thresholdSaving}
                  slotProps={{ htmlInput: { min: 0 } }}
                  data-testid={`${testIdPrefix}-threshold-low`}
                />
                <TextField
                  size="small"
                  label="Предупреждать за N дней до конца"
                  type="number"
                  value={forecastDaysThreshold}
                  onChange={(e) => setForecastDaysThreshold(e.target.value)}
                  disabled={thresholdLoading || thresholdSaving}
                  slotProps={{ htmlInput: { min: 0 } }}
                  sx={{ minWidth: { sm: 280 } }}
                  data-testid={`${testIdPrefix}-threshold-forecast-days`}
                />
                <Button
                  variant="contained"
                  size="small"
                  disabled={thresholdLoading || thresholdSaving}
                  onClick={() => void saveThreshold()}
                  data-testid={`${testIdPrefix}-threshold-save`}
                >
                  Сохранить
                </Button>
              </Stack>
            </Paper>
          ) : null}

          <Typography variant="subtitle1" data-testid={`${testIdPrefix}-sources-heading`}>
            Откуда коды
          </Typography>

          {overview.personal_pools.length === 0 && overview.shared_baskets.length === 0 ? (
            <Paper variant="outlined" sx={{ p: 2 }} data-testid={`${testIdPrefix}-sources-empty`}>
              <Typography variant="body2" color="text.secondary">
                Пулы и корзины для этого товара пока не привязаны.
              </Typography>
            </Paper>
          ) : (
            <Stack spacing={2}>
              {overview.personal_pools.length > 0 ? (
                <Box data-testid={`${testIdPrefix}-personal-pools`}>
                  <Typography variant="subtitle2" sx={{ mb: 1 }}>
                    Личные пулы
                  </Typography>
                  <TableContainer component={Paper} variant="outlined">
                    <Table size="small" sx={{ tableLayout: 'fixed' }}>
                      <TableHead>
                        <TableRow>
                          <TableCell>Пул</TableCell>
                          <TableCell>GTIN</TableCell>
                          <TableCell align="right">Загружено</TableCell>
                          <TableCell align="right">Доступно</TableCell>
                          <TableCell width={48} />
                        </TableRow>
                      </TableHead>
                      <TableBody>
                        {overview.personal_pools.map((pool) => (
                          <TableRow
                            key={pool.pool_id}
                            hover
                            component={RouterLink}
                            to={`${routeBase}/honest-sign/pool/${pool.pool_id}`}
                            sx={{ textDecoration: 'none', cursor: 'pointer' }}
                            data-testid={`${testIdPrefix}-personal-pool-${pool.pool_id}`}
                          >
                            <TableCell>{pool.title}</TableCell>
                            <TableCell>{pool.gtin}</TableCell>
                            <TableCell align="right">{pool.loaded}</TableCell>
                            <TableCell align="right">{pool.available}</TableCell>
                            <TableCell align="right">
                              <ChevronRightOutlined fontSize="small" color="action" />
                            </TableCell>
                          </TableRow>
                        ))}
                      </TableBody>
                    </Table>
                  </TableContainer>
                </Box>
              ) : null}

              {overview.shared_baskets.length > 0 ? (
                <Box data-testid={`${testIdPrefix}-shared-baskets`}>
                  <Typography variant="subtitle2" sx={{ mb: 1 }}>
                    Общие корзины
                  </Typography>
                  <TableContainer component={Paper} variant="outlined">
                    <Table size="small" sx={{ tableLayout: 'fixed' }}>
                      <TableHead>
                        <TableRow>
                          <TableCell>Корзина</TableCell>
                          <TableCell>GTIN</TableCell>
                          <TableCell align="right">Доступно</TableCell>
                          <TableCell>Состав</TableCell>
                          <TableCell width={48} />
                        </TableRow>
                      </TableHead>
                      <TableBody>
                        {overview.shared_baskets.map((basket) => (
                          <TableRow
                            key={basket.pool_id}
                            hover
                            component={RouterLink}
                            to={`${routeBase}/honest-sign/pool/${basket.pool_id}`}
                            sx={{ textDecoration: 'none', cursor: 'pointer' }}
                            data-testid={`${testIdPrefix}-shared-basket-${basket.pool_id}`}
                          >
                            <TableCell>{basket.title}</TableCell>
                            <TableCell>{basket.gtin}</TableCell>
                            <TableCell align="right">{basket.available}</TableCell>
                            <TableCell>
                              делится с {basket.products_count} товарами
                            </TableCell>
                            <TableCell align="right">
                              <ChevronRightOutlined fontSize="small" color="action" />
                            </TableCell>
                          </TableRow>
                        ))}
                      </TableBody>
                    </Table>
                  </TableContainer>
                </Box>
              ) : null}
            </Stack>
          )}
        </Stack>
      ) : null}

      <Tabs
        value={tab ?? false}
        onChange={(_, v: TabKey) => setTab(v)}
        data-testid={`${testIdPrefix}-tabs`}
      >
        <Tab label="Коды" value="codes" data-testid={`${testIdPrefix}-tab-codes`} />
        <Tab label="Лента" value="ledger" data-testid={`${testIdPrefix}-tab-ledger`} />
      </Tabs>

      {tab === 'codes' ? (
        <Stack spacing={1.5} data-testid={`${testIdPrefix}-codes`}>
          <TextField
            select
            size="small"
            label="Статус"
            value={statusFilter}
            onChange={(e) => setStatusFilter(e.target.value)}
            sx={{ minWidth: 160, maxWidth: 240 }}
            data-testid={`${testIdPrefix}-codes-status`}
          >
            <MenuItem value="">Все</MenuItem>
            {STATUS_OPTIONS.filter(Boolean).map((s) => (
              <MenuItem key={s} value={s}>
                {codeStatusLabel(s)}
              </MenuItem>
            ))}
          </TextField>
          {statusFilter && codes.length > 0 ? (
            <Typography
              variant="body2"
              color="text.secondary"
              data-testid={`${testIdPrefix}-codes-count`}
            >
              Показано {filteredCodes.length} из {codes.length}
            </Typography>
          ) : codes.length > 0 ? (
            <Typography
              variant="body2"
              color="text.secondary"
              data-testid={`${testIdPrefix}-codes-count`}
            >
              {codes.length} КМ
            </Typography>
          ) : null}
          <TableContainer component={Paper} variant="outlined">
            <Table size="small" sx={{ tableLayout: 'fixed' }}>
              <TableHead>
                <TableRow>
                  <TableCell>КМ</TableCell>
                  <TableCell>Статус</TableCell>
                  <TableCell>Дата</TableCell>
                </TableRow>
              </TableHead>
              <TableBody>
                {codesBusy ? (
                  <TableRow>
                    <TableCell colSpan={3}>
                      <Skeleton height={32} />
                    </TableCell>
                  </TableRow>
                ) : filteredCodes.length === 0 ? (
                  <TableRow>
                    <TableCell colSpan={3}>
                      <Typography variant="body2" color="text.secondary">
                        Коды не найдены.
                      </Typography>
                    </TableCell>
                  </TableRow>
                ) : (
                  filteredCodes.map((c) => (
                    <TableRow key={c.id} data-testid={`${testIdPrefix}-code-row-${c.id}`}>
                      <TableCell>{maskCisCode(c.cis_code)}</TableCell>
                      <TableCell>
                        <Chip size="small" label={codeStatusLabel(c.status)} />
                      </TableCell>
                      <TableCell>{new Date(c.created_at).toLocaleString('ru-RU')}</TableCell>
                    </TableRow>
                  ))
                )}
              </TableBody>
            </Table>
          </TableContainer>
        </Stack>
      ) : null}

      {tab === 'ledger' ? (
        <Stack spacing={1.5} data-testid={`${testIdPrefix}-ledger`}>
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
              to={`${routeBase}/honest-sign/ledger?product_id=${encodeURIComponent(productId)}`}
              variant="outlined"
              size="small"
              data-testid={`${testIdPrefix}-ledger-open-full`}
            >
              Вся лента товара
            </Button>
          </Stack>
          <TableContainer component={Paper} variant="outlined">
            <Table size="small" sx={{ tableLayout: 'fixed' }}>
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
    </Stack>
  )
}
