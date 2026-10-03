import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import {
  Alert,
  Box,
  Button,
  Chip,
  CircularProgress,
  FormControl,
  InputLabel,
  MenuItem,
  Paper,
  Select,
  Stack,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TablePagination,
  TableRow,
  Typography,
} from '@mui/material'
import { MarketplaceIcon } from '../../ui-kit'
import {
  SELLER_FBS_STATUS_FILTER_OPTIONS,
  buildSellerFbsOrdersParams,
  loadSellerFbsOrdersPage,
  sellerFbsAgeLabel,
  sellerFbsItemsLabel,
  sellerFbsMarketplaceShort,
  sellerFbsReceivedAtLabel,
  sellerFbsStatusLabel,
  type SellerFbsMarketplaceFilter,
  type SellerFbsOrderRow,
  type SellerFbsStatusFilter,
} from './sellerFbsOrdersApi'

// WMS-616: отдельный read-only список FBS-заказов селлера. Без складских
// действий (R9): сборку, упаковку, стикеры и короба ведёт фулфилмент на
// своём экране; здесь — только просмотр.

type Props = {
  token: string
  authHeaders: (t: string) => Record<string, string>
}

// Такт обновления «Возраст»: раз в минуту — так же, как складской пилл
// дедлайна. Чаще не нужно: цифра целого часа всё равно меняется редко.
const AGE_TICK_MS = 60_000

export function SellerFbsOrdersScreen({ token, authHeaders }: Props) {
  const [items, setItems] = useState<SellerFbsOrderRow[]>([])
  const [total, setTotal] = useState(0)
  const [serverNowIso, setServerNowIso] = useState<string | null>(null)
  const [page, setPage] = useState(0)
  const [rowsPerPage, setRowsPerPage] = useState(50)
  const [marketplaceFilter, setMarketplaceFilter] =
    useState<SellerFbsMarketplaceFilter>('all')
  const [statusFilter, setStatusFilter] = useState<SellerFbsStatusFilter>('all')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  // Токен сессии, к которой относятся показанные строки — то же решение,
  // что и в seller-каталоге (WMS-488). После смены сессии содержимое чужого
  // селлера не должно задержаться на экране.
  const sessionTokenRef = useRef(token)
  const abortRef = useRef<AbortController | null>(null)
  useEffect(() => {
    sessionTokenRef.current = token
    setItems([])
    setTotal(0)
    setServerNowIso(null)
  }, [token])

  useEffect(() => {
    setPage(0)
  }, [marketplaceFilter, statusFilter, rowsPerPage])

  const load = useCallback(async () => {
    const requestToken = token
    const isCurrentSession = () => sessionTokenRef.current === requestToken
    abortRef.current?.abort()
    const controller = new AbortController()
    abortRef.current = controller
    setBusy(true)
    setError(null)
    const params = buildSellerFbsOrdersParams({
      limit: rowsPerPage,
      offset: page * rowsPerPage,
      marketplace: marketplaceFilter,
      status: statusFilter,
    })
    const result = await loadSellerFbsOrdersPage(
      fetch,
      { ...authHeaders(requestToken) },
      params,
      isCurrentSession,
      controller.signal,
    )
    if (result.outcome === 'stale') return
    setBusy(false)
    if (result.outcome === 'failed') {
      setError(result.message)
      return
    }
    setItems(result.page.items)
    setTotal(result.page.total)
    setServerNowIso(result.page.server_now)
  }, [authHeaders, marketplaceFilter, page, rowsPerPage, statusFilter, token])

  useEffect(() => {
    void load()
    return () => abortRef.current?.abort()
  }, [load])

  // Astra P2: «Возраст» рендерится от server_now + монотонное прошедшее с
  // момента ответа. Прошлая версия считала через Date.now()/useMemo, где
  // зависимости не менялись между тиками — значение useMemo оставалось тем же,
  // и возраст замирал. performance.now() монотонный, не зависит от NTP-прыжков
  // часов клиента, а ageTick гарантирует перерисовку таблицы раз в минуту.
  const [perfAnchor, setPerfAnchor] = useState<{
    serverNowMs: number
    perfMs: number
  } | null>(null)
  const [ageTick, setAgeTick] = useState(0)
  useEffect(() => {
    if (!serverNowIso) {
      setPerfAnchor(null)
      return
    }
    const serverNowMs = Date.parse(serverNowIso)
    if (!Number.isFinite(serverNowMs)) {
      setPerfAnchor(null)
      return
    }
    setPerfAnchor({ serverNowMs, perfMs: performance.now() })
    setAgeTick(0)
  }, [serverNowIso])
  useEffect(() => {
    if (!perfAnchor) return
    const timer = window.setInterval(() => setAgeTick((n) => n + 1), AGE_TICK_MS)
    return () => window.clearInterval(timer)
  }, [perfAnchor])

  const resolvedNowIso = useMemo(() => {
    if (!perfAnchor) return null
    const elapsed = performance.now() - perfAnchor.perfMs
    return new Date(perfAnchor.serverNowMs + elapsed).toISOString()
    // Зависимость от ageTick — именно та, из-за которой возраст перестал
    // замирать: forceAgeTick меняется, useMemo пересчитывается.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [perfAnchor, ageTick])

  return (
    <Box
      sx={{
        minWidth: 0,
        width: '100%',
        maxWidth: '100%',
        boxSizing: 'border-box',
      }}
    >
      <Typography variant="h5" gutterBottom>
        FBS
      </Typography>
      <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
        Заказы FBS, которые площадки передали фулфилменту. Селлер видит
        только свои.
      </Typography>

      {error ? (
        <Alert
          severity="error"
          sx={{ mb: 2 }}
          data-testid="seller-fbs-error"
          action={
            <Button
              color="inherit"
              size="small"
              onClick={() => void load()}
              data-testid="seller-fbs-retry"
            >
              Повторить
            </Button>
          }
        >
          {error}
        </Alert>
      ) : null}

      <Paper variant="outlined" sx={{ p: 2, mb: 2 }} data-testid="seller-fbs-filters">
        <Stack
          direction={{ xs: 'column', sm: 'row' }}
          spacing={2}
          sx={{ alignItems: { sm: 'center' }, flexWrap: 'wrap', rowGap: 2 }}
        >
          <FormControl size="small" sx={{ minWidth: 200 }}>
            <InputLabel id="seller-fbs-marketplace-filter-label">Маркетплейс</InputLabel>
            <Select
              labelId="seller-fbs-marketplace-filter-label"
              label="Маркетплейс"
              value={marketplaceFilter}
              onChange={(e) => setMarketplaceFilter(e.target.value as SellerFbsMarketplaceFilter)}
              data-testid="seller-fbs-marketplace-filter"
            >
              <MenuItem value="all">Все маркетплейсы</MenuItem>
              <MenuItem value="wb">Wildberries</MenuItem>
              <MenuItem value="ozon">Ozon</MenuItem>
            </Select>
          </FormControl>
          <FormControl size="small" sx={{ minWidth: 220 }}>
            <InputLabel id="seller-fbs-status-filter-label">Статус</InputLabel>
            <Select
              labelId="seller-fbs-status-filter-label"
              label="Статус"
              value={statusFilter}
              onChange={(e) => setStatusFilter(e.target.value as SellerFbsStatusFilter)}
              data-testid="seller-fbs-status-filter"
            >
              {SELLER_FBS_STATUS_FILTER_OPTIONS.map((option) => (
                <MenuItem key={option.value} value={option.value}>
                  {option.label}
                </MenuItem>
              ))}
            </Select>
          </FormControl>
          <Typography variant="body2" color="text.secondary" data-testid="seller-fbs-filter-count">
            {`Найдено: ${total}`}
          </Typography>
          {busy ? <CircularProgress size={18} /> : null}
        </Stack>
      </Paper>

      <TableContainer
        component={Paper}
        variant="outlined"
        sx={{ width: '100%', maxWidth: '100%', minWidth: 0, overflowX: 'auto' }}
        data-testid="seller-fbs-orders-list"
      >
        <Table
          stickyHeader
          size="small"
          data-testid="seller-fbs-orders-table"
          sx={{
            width: '100%',
            minWidth: 720,
            '& .MuiTableCell-root': {
              px: 1.25,
              py: 0.5,
              verticalAlign: 'middle',
            },
            '& .MuiTableCell-head': {
              fontWeight: 600,
              fontSize: '0.72rem',
              lineHeight: 1.2,
              whiteSpace: 'nowrap',
            },
          }}
        >
          <TableHead>
            <TableRow>
              <TableCell>Маркетплейс</TableCell>
              <TableCell>Номер заказа</TableCell>
              <TableCell align="right">Товаров</TableCell>
              <TableCell>Статус</TableCell>
              <TableCell>Поступил</TableCell>
              <TableCell>Возраст</TableCell>
            </TableRow>
          </TableHead>
          <TableBody>
            {items.map((row) => (
              <TableRow
                hover
                key={row.id}
                data-testid="seller-fbs-order-row"
                data-order-id={row.id}
                data-marketplace={row.marketplace}
                data-status-group={row.status_group}
              >
                <TableCell sx={{ width: 160 }}>
                  <Stack direction="row" spacing={0.75} sx={{ alignItems: 'center' }}>
                    <MarketplaceIcon
                      marketplace={row.marketplace === 'ozon' ? 'ozon' : 'wb'}
                      testId={`seller-fbs-mp-${row.id}`}
                    />
                    <Typography variant="body2">
                      {sellerFbsMarketplaceShort(row.marketplace)}
                    </Typography>
                  </Stack>
                </TableCell>
                <TableCell>
                  {/* R3: длинный внешний номер не перекрывает соседние колонки — ломаем перенос */}
                  <Typography
                    variant="body2"
                    sx={{ fontFamily: 'monospace', wordBreak: 'break-all' }}
                    data-testid={`seller-fbs-order-external-${row.id}`}
                  >
                    {row.external_order_id ?? '—'}
                  </Typography>
                </TableCell>
                <TableCell align="right">
                  <Typography variant="body2" data-testid={`seller-fbs-order-qty-${row.id}`}>
                    {sellerFbsItemsLabel(row)}
                  </Typography>
                </TableCell>
                <TableCell>
                  <Chip
                    size="small"
                    variant="outlined"
                    label={sellerFbsStatusLabel(row.status_group)}
                    data-testid={`seller-fbs-order-status-${row.id}`}
                  />
                </TableCell>
                <TableCell>
                  <Typography variant="body2" data-testid={`seller-fbs-order-received-${row.id}`}>
                    {sellerFbsReceivedAtLabel(row.received_at)}
                  </Typography>
                </TableCell>
                <TableCell>
                  <Typography variant="body2" data-testid={`seller-fbs-order-age-${row.id}`}>
                    {resolvedNowIso
                      ? sellerFbsAgeLabel({ receivedAtIso: row.received_at, serverNowIso: resolvedNowIso })
                      : '—'}
                  </Typography>
                </TableCell>
              </TableRow>
            ))}
            {items.length === 0 && !busy ? (
              <TableRow>
                <TableCell colSpan={6}>
                  <Typography variant="body2" color="text.secondary">
                    Пока нет FBS-заказов.
                  </Typography>
                </TableCell>
              </TableRow>
            ) : null}
          </TableBody>
        </Table>
        <TablePagination
          component="div"
          count={total}
          page={page}
          onPageChange={(_, next) => setPage(next)}
          rowsPerPage={rowsPerPage}
          onRowsPerPageChange={(e) => {
            setRowsPerPage(Number(e.target.value))
            setPage(0)
          }}
          rowsPerPageOptions={[25, 50, 100, 200]}
          labelRowsPerPage="На странице"
          data-testid="seller-fbs-orders-pagination"
        />
      </TableContainer>
    </Box>
  )
}
