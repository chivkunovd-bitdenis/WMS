import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { Link as RouterLink, useParams, useSearchParams } from 'react-router-dom'
import {
  Alert,
  Box,
  Chip,
  IconButton,
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
  Typography,
} from '@mui/material'
import ArrowBackOutlined from '@mui/icons-material/ArrowBackOutlined'
import ChevronRightOutlined from '@mui/icons-material/ChevronRightOutlined'
import { apiUrl } from '../../api'
import { PageHeader } from '../../ui/PageHeader'
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

type TabKey = 'codes' | 'ledger'

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
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const loadRequestId = useRef(0)

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

  useEffect(() => {
    void loadOverview()
  }, [loadOverview])

  const personalAvailable = useMemo(
    () => (overview?.personal_pools ?? []).reduce((sum, pool) => sum + pool.available, 0),
    [overview],
  )

  const sharedBasketsCount = overview?.shared_baskets.length ?? 0

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
        <Paper variant="outlined" sx={{ p: 2 }} data-testid={`${testIdPrefix}-codes`}>
          <Typography variant="body2" color="text.secondary">
            Список кодов маркировки появится на этой вкладке.
          </Typography>
        </Paper>
      ) : null}

      {tab === 'ledger' ? (
        <Paper variant="outlined" sx={{ p: 2 }} data-testid={`${testIdPrefix}-ledger`}>
          <Typography variant="body2" color="text.secondary">
            Лента событий по товару появится на этой вкладке.
          </Typography>
        </Paper>
      ) : null}
    </Stack>
  )
}
