import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  Alert,
  Box,
  Button,
  Chip,
  IconButton,
  Menu,
  MenuItem,
  Paper,
  Skeleton,
  Snackbar,
  Stack,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  TextField,
  ToggleButton,
  ToggleButtonGroup,
  Tooltip,
  Typography,
} from '@mui/material'
import ChevronRightOutlined from '@mui/icons-material/ChevronRightOutlined'
import UploadFileOutlined from '@mui/icons-material/UploadFileOutlined'
import TimelineOutlined from '@mui/icons-material/TimelineOutlined'
import MoreVertOutlined from '@mui/icons-material/MoreVertOutlined'
import { apiUrl } from '../../api'
import { PageHeader } from '../../ui/PageHeader'
import { readApiErrorMessage } from '../../utils/readApiErrorMessage'
import { MarkingImportDialog, type PoolImportContext } from './MarkingImportDialog'
import { MarkingPoolProductsDialog } from './MarkingPoolProductsDialog'
import { MarkingSellerPicker } from './MarkingSellerPicker'

export type MarkingPoolRow = {
  id: string
  title: string
  gtin: string
  products: { id: string; sku_code: string; name: string }[]
  available: number
  reserved: number
  printed: number
  defective: number
  forecast_days: number | null
  low_stock_threshold: number | null
  forecast_days_threshold?: number | null
  consumption_7d?: number
  loaded?: number
  used?: number
}

type StockFilter = 'all' | 'low' | 'empty'

type KpiCardConfig = {
  label: string
  value: number
  testId: string
  interactive: boolean
  active?: boolean
  onClick?: () => void
}

type Props = {
  token: string
  sellerId?: string | null
  sellerIdRequiredForImport?: boolean
  sellers?: { id: string; name: string }[]
  selectedSellerId?: string | null
  onSelectedSellerIdChange?: (id: string | null) => void
  testIdPrefix?: string
  /** FF: /app/ff · seller: /seller */
  routeBase?: string
  /** T3.4: карточки остатков вместо только таблицы */
  showSellerDashboard?: boolean
}

function poolMatchesSearch(row: MarkingPoolRow, query: string): boolean {
  const needle = query.trim().toLowerCase()
  if (!needle) {
    return true
  }
  if (row.title.toLowerCase().includes(needle) || row.gtin.toLowerCase().includes(needle)) {
    return true
  }
  return row.products.some(
    (p) =>
      p.sku_code.toLowerCase().includes(needle) || p.name.toLowerCase().includes(needle),
  )
}

function isLowStock(row: MarkingPoolRow): boolean {
  if (row.low_stock_threshold != null) {
    return row.available < row.low_stock_threshold
  }
  return row.available > 0 && row.available <= 10
}

function isProblematicPool(row: MarkingPoolRow): boolean {
  return row.available === 0 || isLowStock(row)
}

function ProductChips({
  products,
  testIdPrefix,
  poolId,
}: {
  products: MarkingPoolRow['products']
  testIdPrefix: string
  poolId: string
}) {
  const visible = products.slice(0, 3)
  const rest = products.length - visible.length
  return (
    <Stack direction="row" spacing={0.5} sx={{ flexWrap: 'wrap' }}>
      {visible.map((p) => (
        <Chip
          key={p.id}
          size="small"
          label={p.sku_code}
          data-testid={`${testIdPrefix}-pool-chip-${poolId}-${p.id}`}
        />
      ))}
      {rest > 0 ? (
        <Chip size="small" variant="outlined" label={`ещё ${rest}`} />
      ) : null}
    </Stack>
  )
}

function forecastDateLabel(forecastDays: number): string {
  const d = new Date()
  d.setDate(d.getDate() + Math.ceil(forecastDays))
  const dd = String(d.getDate()).padStart(2, '0')
  const mm = String(d.getMonth() + 1).padStart(2, '0')
  return `${dd}.${mm}`
}

function forecastDaysHint(forecastDays: number): string {
  const rounded = Math.round(forecastDays * 10) / 10
  return `(${rounded} дн.)`
}

function ForecastLabel({
  forecastDays,
  testId,
}: {
  forecastDays: number | null
  testId?: string
}) {
  if (forecastDays == null || forecastDays <= 0) {
    return (
      <Typography component="span" variant="inherit" data-testid={testId}>
        —
      </Typography>
    )
  }
  const dateLabel = forecastDateLabel(forecastDays)
  const hint = forecastDaysHint(forecastDays)
  return (
    <Tooltip title={hint}>
      <Typography
        component="span"
        variant="inherit"
        data-testid={testId}
        sx={{ cursor: 'help', borderBottom: '1px dotted', borderColor: 'text.disabled' }}
      >
        {dateLabel}
      </Typography>
    </Tooltip>
  )
}

export function HonestSignScreen({
  token,
  sellerId,
  sellerIdRequiredForImport = false,
  sellers = [],
  selectedSellerId = null,
  onSelectedSellerIdChange,
  testIdPrefix = 'honest-sign',
  routeBase = '/app/ff',
  showSellerDashboard = false,
}: Props) {
  const navigate = useNavigate()
  const poolsTableRef = useRef<HTMLDivElement>(null)
  const poolsLoadAbortRef = useRef<AbortController | null>(null)
  const [pools, setPools] = useState<MarkingPoolRow[]>([])
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [search, setSearch] = useState('')
  const [stockFilter, setStockFilter] = useState<StockFilter>('all')
  const [menuAnchor, setMenuAnchor] = useState<HTMLElement | null>(null)
  const [menuPool, setMenuPool] = useState<MarkingPoolRow | null>(null)
  const [linkPool, setLinkPool] = useState<MarkingPoolRow | null>(null)
  const [importOpen, setImportOpen] = useState(false)
  const [importPoolContext, setImportPoolContext] = useState<PoolImportContext | null>(null)
  const [toastMessage, setToastMessage] = useState<string | null>(null)

  const openImport = (pool?: MarkingPoolRow) => {
    if (sellerIdRequiredForImport && !effectiveSellerId) {
      return
    }
    setImportPoolContext(
      pool
        ? {
            gtin: pool.gtin,
            title: pool.title,
            productIds: pool.products.map((p) => p.id),
          }
        : null,
    )
    setImportOpen(true)
  }

  const closeImport = () => {
    setImportOpen(false)
    setImportPoolContext(null)
  }

  const effectiveSellerId = sellerId ?? selectedSellerId
  const importDisabled = sellerIdRequiredForImport && !effectiveSellerId

  const loadPools = useCallback(async () => {
    poolsLoadAbortRef.current?.abort()
    const ac = new AbortController()
    poolsLoadAbortRef.current = ac
    setBusy(true)
    setError(null)
    try {
      const q =
        effectiveSellerId && !sellerId
          ? `?seller_id=${encodeURIComponent(effectiveSellerId)}`
          : sellerId
            ? ''
            : effectiveSellerId
              ? `?seller_id=${encodeURIComponent(effectiveSellerId)}`
              : ''
      const res = await fetch(apiUrl(`/operations/marking-codes/pools${q}`), {
        headers: { Authorization: `Bearer ${token}` },
        signal: ac.signal,
      })
      if (ac.signal.aborted) {
        return
      }
      if (!res.ok) {
        setError(await readApiErrorMessage(res))
        return
      }
      setPools((await res.json()) as MarkingPoolRow[])
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
  }, [effectiveSellerId, sellerId, token])

  useEffect(() => {
    if (sellerIdRequiredForImport && !effectiveSellerId) {
      setPools([])
      return
    }
    void loadPools()
    return () => {
      poolsLoadAbortRef.current?.abort()
    }
  }, [effectiveSellerId, loadPools, sellerIdRequiredForImport])

  const kpis = useMemo(() => {
    const availableTotal = pools.reduce((s, p) => s + p.available, 0)
    const defectiveTotal = pools.reduce((s, p) => s + p.defective, 0)
    const lowCount = pools.filter(isLowStock).length
    const spend7d = pools.reduce((s, p) => s + (p.consumption_7d ?? 0), 0)
    return { availableTotal, defectiveTotal, lowCount, spend7d }
  }, [pools])

  const scrollToPoolsTable = useCallback(() => {
    poolsTableRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' })
  }, [])

  const kpiCards = useMemo((): KpiCardConfig[] => {
    return [
      {
        label: 'Доступно всего',
        value: kpis.availableTotal,
        testId: 'kpi-available',
        interactive: true,
        active: stockFilter === 'all',
        onClick: () => {
          setStockFilter('all')
          scrollToPoolsTable()
        },
      },
      {
        label: 'Расход 7 дней',
        value: kpis.spend7d,
        testId: 'kpi-spend-7d',
        interactive: false,
      },
      {
        label: 'Брак',
        value: kpis.defectiveTotal,
        testId: 'kpi-defective',
        interactive: true,
        onClick: () => {
          navigate(`${routeBase}/honest-sign/ledger?event_type=defective`)
        },
      },
      {
        label: 'Пулы на исходе',
        value: kpis.lowCount,
        testId: 'kpi-low-stock',
        interactive: true,
        active: stockFilter === 'low',
        onClick: () => {
          setStockFilter('low')
          scrollToPoolsTable()
        },
      },
    ]
  }, [kpis, navigate, routeBase, scrollToPoolsTable, stockFilter])

  const filteredPools = useMemo(() => {
    return pools.filter((row) => {
      if (!poolMatchesSearch(row, search)) {
        return false
      }
      if (stockFilter === 'empty') {
        return row.available === 0
      }
      if (stockFilter === 'low') {
        return isLowStock(row)
      }
      return true
    })
  }, [pools, search, stockFilter])

  const problematicPools = useMemo(
    () => filteredPools.filter(isProblematicPool),
    [filteredPools],
  )

  const tablePools = useMemo(() => {
    if (!showSellerDashboard) {
      return filteredPools
    }
    const problematicIds = new Set(problematicPools.map((row) => row.id))
    return filteredPools.filter((row) => !problematicIds.has(row.id))
  }, [filteredPools, problematicPools, showSellerDashboard])

  const openMenu = (event: React.MouseEvent<HTMLElement>, pool: MarkingPoolRow) => {
    event.stopPropagation()
    setMenuAnchor(event.currentTarget)
    setMenuPool(pool)
  }

  const closeMenu = () => {
    setMenuAnchor(null)
    setMenuPool(null)
  }

  const onLinkedProductsSaved = (products: MarkingPoolRow['products']) => {
    if (!linkPool) {
      return
    }
    setPools((prev) =>
      prev.map((p) => (p.id === linkPool.id ? { ...p, products } : p)),
    )
    setLinkPool(null)
    void loadPools()
  }

  return (
    <Stack spacing={2} data-testid={`${testIdPrefix}-page`}>
      <PageHeader
        title="Честный знак"
        description="Пулы КМ по GTIN: остаток общий на пул, товары привязываются вручную."
      />

      {sellerIdRequiredForImport ? (
        <MarkingSellerPicker
          sellers={sellers}
          selectedSellerId={selectedSellerId}
          onSelectedSellerIdChange={(id) => onSelectedSellerIdChange?.(id)}
          testIdPrefix={testIdPrefix}
        />
      ) : null}

      {error ? (
        <Alert severity="error" data-testid={`${testIdPrefix}-error`}>
          {error}
        </Alert>
      ) : null}

      <Stack direction={{ xs: 'column', sm: 'row' }} spacing={1} sx={{ flexWrap: 'wrap' }}>
        {kpiCards.map((kpi) => (
          <Paper
            key={kpi.testId}
            variant="outlined"
            component={kpi.interactive ? 'button' : 'div'}
            type={kpi.interactive ? 'button' : undefined}
            onClick={kpi.interactive ? kpi.onClick : undefined}
            sx={{
              p: 1.5,
              minWidth: 140,
              flex: 1,
              display: 'block',
              width: '100%',
              textAlign: 'left',
              font: 'inherit',
              color: 'inherit',
              cursor: kpi.interactive ? 'pointer' : 'default',
              borderColor: kpi.active ? 'primary.main' : 'divider',
              bgcolor: kpi.active ? 'primary.50' : 'background.paper',
              transition: 'background-color 0.15s ease, border-color 0.15s ease',
              ...(kpi.interactive
                ? {
                    '&:hover': {
                      borderColor: 'primary.main',
                      bgcolor: kpi.active ? 'primary.50' : 'action.hover',
                    },
                  }
                : {}),
            }}
            data-testid={`${testIdPrefix}-${kpi.testId}`}
            data-interactive={kpi.interactive ? 'true' : 'false'}
          >
            <Stack direction="row" spacing={0.5} sx={{ justifyContent: 'space-between', alignItems: 'flex-start' }}>
              <Box>
                <Typography variant="caption" color="text.secondary">
                  {kpi.label}
                </Typography>
                <Typography variant="h6">{kpi.value}</Typography>
              </Box>
              {kpi.interactive ? (
                <ChevronRightOutlined fontSize="small" color="action" sx={{ mt: 0.25, flexShrink: 0 }} />
              ) : null}
            </Stack>
          </Paper>
        ))}
      </Stack>

      {showSellerDashboard && problematicPools.length > 0 ? (
        <Stack spacing={1} data-testid={`${testIdPrefix}-seller-dashboard`}>
          <Typography variant="subtitle2" color="text.secondary">
            Требуют внимания
          </Typography>
          {problematicPools.map((row) => {
            const low = isLowStock(row)
            const spendPerDay =
              row.consumption_7d != null ? Math.round((row.consumption_7d / 7) * 10) / 10 : 0
            return (
              <Paper
                key={row.id}
                variant="outlined"
                sx={{
                  p: 2,
                  bgcolor: low ? 'error.50' : row.available <= 20 ? 'warning.50' : 'background.paper',
                }}
                data-testid={`${testIdPrefix}-pool-card-${row.id}`}
              >
                <Stack
                  direction={{ xs: 'column', sm: 'row' }}
                  spacing={1}
                  sx={{ justifyContent: 'space-between', alignItems: { sm: 'center' } }}
                >
                  <Box>
                    <Typography variant="subtitle1" sx={{ fontWeight: 600 }}>
                      {row.title}
                    </Typography>
                    <Typography variant="caption" color="text.secondary">
                      GTIN {row.gtin}
                    </Typography>
                  </Box>
                  <Button
                    size="small"
                    variant="contained"
                    startIcon={<UploadFileOutlined />}
                    onClick={() => openImport(row)}
                    data-testid={`${testIdPrefix}-pool-card-upload-${row.id}`}
                  >
                    Догрузить
                  </Button>
                </Stack>
                <Stack direction="row" spacing={2} sx={{ mt: 1, flexWrap: 'wrap' }}>
                  <Typography variant="body2">Загружено: {row.loaded ?? '—'}</Typography>
                  <Typography variant="body2">Использовано: {row.used ?? '—'}</Typography>
                  <Typography variant="body2">Доступно: {row.available}</Typography>
                  <Typography variant="body2">Расход/день: {spendPerDay}</Typography>
                  <Typography variant="body2">
                    Прогноз: <ForecastLabel forecastDays={row.forecast_days} />
                  </Typography>
                </Stack>
              </Paper>
            )
          })}
        </Stack>
      ) : null}

      <Stack direction={{ xs: 'column', sm: 'row' }} spacing={1}>
        <Tooltip
          title="Выберите селлера"
          disableHoverListener={!importDisabled}
          disableFocusListener={!importDisabled}
          disableTouchListener={!importDisabled}
        >
          <Box component="span" sx={{ display: 'inline-flex' }}>
            <Button
              variant="contained"
              startIcon={<UploadFileOutlined />}
              disabled={importDisabled}
              onClick={() => openImport()}
              data-testid={`${testIdPrefix}-open-import`}
            >
              Загрузить КМ
            </Button>
          </Box>
        </Tooltip>
        <Button
          variant="outlined"
          startIcon={<TimelineOutlined />}
          onClick={() => navigate(`${routeBase}/honest-sign/ledger`)}
          data-testid={`${testIdPrefix}-open-ledger`}
        >
          Лента расхода
        </Button>
      </Stack>

      <Stack direction={{ xs: 'column', sm: 'row' }} spacing={1.5} sx={{ alignItems: { sm: 'center' } }}>
        <TextField
          size="small"
          label="Поиск"
          placeholder="Название, GTIN, артикул"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          sx={{ flex: 1 }}
          data-testid={`${testIdPrefix}-search`}
        />
        <ToggleButtonGroup
          exclusive
          size="small"
          value={stockFilter}
          onChange={(_, v: StockFilter | null) => v && setStockFilter(v)}
          data-testid={`${testIdPrefix}-stock-filter`}
        >
          <ToggleButton value="all">Все</ToggleButton>
          <ToggleButton value="low">На исходе</ToggleButton>
          <ToggleButton value="empty">Пустые</ToggleButton>
        </ToggleButtonGroup>
      </Stack>

      <TableContainer component={Paper} variant="outlined" ref={poolsTableRef}>
        <Table size="small" data-testid={`${testIdPrefix}-pools-table`}>
          <TableHead>
            <TableRow>
              <TableCell>Пул</TableCell>
              <TableCell>Товары</TableCell>
              <TableCell align="right">Доступно</TableCell>
              <TableCell align="right">Резерв</TableCell>
              <TableCell align="right">Напечатано</TableCell>
              <TableCell align="right">Брак</TableCell>
              <TableCell align="right">Прогноз</TableCell>
              <TableCell padding="checkbox" />
            </TableRow>
          </TableHead>
          <TableBody>
            {busy ? (
              Array.from({ length: 3 }).map((_, i) => (
                <TableRow key={i}>
                  <TableCell colSpan={8}>
                    <Skeleton height={32} />
                  </TableCell>
                </TableRow>
              ))
            ) : tablePools.length === 0 ? (
              <TableRow>
                <TableCell colSpan={8}>
                  <Stack spacing={1} sx={{ py: 2, alignItems: 'flex-start' }}>
                    <Typography variant="body2" color="text.secondary">
                      {pools.length === 0
                        ? 'Пулов пока нет — загрузите КМ из файла.'
                        : showSellerDashboard && problematicPools.length > 0
                          ? 'Проблемные пулы показаны в блоке выше. По фильтру в таблице ничего нет.'
                          : 'Ничего не найдено по фильтру.'}
                    </Typography>
                    {pools.length === 0 ? (
                      <Button
                        variant="contained"
                        size="small"
                        startIcon={<UploadFileOutlined />}
                        onClick={() => openImport()}
                        data-testid={`${testIdPrefix}-empty-upload`}
                      >
                        Загрузить КМ
                      </Button>
                    ) : null}
                  </Stack>
                </TableCell>
              </TableRow>
            ) : (
              tablePools.map((row) => {
                const low = isLowStock(row)
                return (
                  <TableRow
                    key={row.id}
                    hover
                    sx={{ cursor: 'pointer' }}
                    onClick={() => navigate(`${routeBase}/honest-sign/pool/${row.id}`)}
                    data-testid={`${testIdPrefix}-pool-row-${row.id}`}
                  >
                    <TableCell>
                      <Stack spacing={0.25}>
                        <Typography variant="body2" sx={{ fontWeight: 600 }}>
                          {row.title}
                        </Typography>
                        <Typography variant="caption" color="text.secondary">
                          GTIN {row.gtin}
                        </Typography>
                      </Stack>
                    </TableCell>
                    <TableCell>
                      {row.products.length > 0 ? (
                        <ProductChips
                          products={row.products}
                          testIdPrefix={testIdPrefix}
                          poolId={row.id}
                        />
                      ) : (
                        <Button
                          size="small"
                          onClick={(e) => {
                            e.stopPropagation()
                            setLinkPool(row)
                          }}
                          data-testid={`${testIdPrefix}-pool-link-quick-${row.id}`}
                        >
                          Привязать
                        </Button>
                      )}
                    </TableCell>
                    <TableCell
                      align="right"
                      sx={{ color: low ? 'error.main' : undefined, fontWeight: low ? 600 : 400 }}
                    >
                      {row.available}
                    </TableCell>
                    <TableCell align="right">{row.reserved}</TableCell>
                    <TableCell align="right">{row.printed}</TableCell>
                    <TableCell align="right">{row.defective}</TableCell>
                    <TableCell align="right">
                      <ForecastLabel
                        forecastDays={row.forecast_days}
                        testId={`${testIdPrefix}-pool-forecast-${row.id}`}
                      />
                    </TableCell>
                    <TableCell padding="checkbox" align="right">
                      <IconButton
                        size="small"
                        aria-label="Действия пула"
                        onClick={(e) => openMenu(e, row)}
                        data-testid={`${testIdPrefix}-pool-menu-${row.id}`}
                      >
                        <MoreVertOutlined fontSize="small" />
                      </IconButton>
                    </TableCell>
                  </TableRow>
                )
              })
            )}
          </TableBody>
        </Table>
      </TableContainer>

      <Menu anchorEl={menuAnchor} open={Boolean(menuAnchor)} onClose={closeMenu}>
        <MenuItem
          onClick={() => {
            if (menuPool) {
              setLinkPool(menuPool)
            }
            closeMenu()
          }}
          data-testid={`${testIdPrefix}-menu-link-products`}
        >
          Привязать товары
        </MenuItem>
        <MenuItem
          onClick={() => {
            if (menuPool) {
              navigate(`${routeBase}/honest-sign/pool/${menuPool.id}?tab=codes`)
            }
            closeMenu()
          }}
          data-testid={`${testIdPrefix}-menu-codes`}
        >
          Коды
        </MenuItem>
        <MenuItem
          onClick={() => {
            if (menuPool) {
              navigate(`${routeBase}/honest-sign/ledger?pool_id=${menuPool.id}`)
            }
            closeMenu()
          }}
          data-testid={`${testIdPrefix}-menu-ledger`}
        >
          Лента пула
        </MenuItem>
      </Menu>

      {linkPool && effectiveSellerId ? (
        <MarkingPoolProductsDialog
          open
          token={token}
          poolId={linkPool.id}
          poolTitle={linkPool.title}
          sellerId={effectiveSellerId}
          linkedProducts={linkPool.products}
          testIdPrefix={testIdPrefix}
          onClose={() => setLinkPool(null)}
          onSaved={onLinkedProductsSaved}
        />
      ) : null}

      {importOpen && effectiveSellerId ? (
        <MarkingImportDialog
          open
          token={token}
          sellerId={effectiveSellerId}
          testIdPrefix={testIdPrefix}
          poolContext={importPoolContext}
          onClose={closeImport}
          onImported={(message) => {
            setToastMessage(message)
            void loadPools()
          }}
        />
      ) : null}

      <Snackbar
        open={toastMessage != null}
        autoHideDuration={5000}
        onClose={() => setToastMessage(null)}
        message={toastMessage ?? ''}
        data-testid={`${testIdPrefix}-import-toast`}
      />
    </Stack>
  )
}
