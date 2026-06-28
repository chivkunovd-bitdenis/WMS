import { useCallback, useEffect, useMemo, useState } from 'react'
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
  Typography,
} from '@mui/material'
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

function forecastUntilLabel(forecastDays: number | null): string {
  if (forecastDays == null || forecastDays <= 0) return '—'
  const d = new Date()
  d.setDate(d.getDate() + Math.ceil(forecastDays))
  const dd = String(d.getDate()).padStart(2, '0')
  const mm = String(d.getMonth() + 1).padStart(2, '0')
  return `${dd}.${mm}`
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

  const loadPools = useCallback(async () => {
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
      })
      if (!res.ok) {
        setError(await readApiErrorMessage(res))
        return
      }
      setPools((await res.json()) as MarkingPoolRow[])
    } finally {
      setBusy(false)
    }
  }, [effectiveSellerId, sellerId, token])

  useEffect(() => {
    if (sellerIdRequiredForImport && !effectiveSellerId) {
      setPools([])
      return
    }
    void loadPools()
  }, [effectiveSellerId, loadPools, sellerIdRequiredForImport])

  const kpis = useMemo(() => {
    const availableTotal = pools.reduce((s, p) => s + p.available, 0)
    const defectiveTotal = pools.reduce((s, p) => s + p.defective, 0)
    const lowCount = pools.filter(isLowStock).length
    const spend7d = pools.reduce((s, p) => s + (p.consumption_7d ?? 0), 0)
    return { availableTotal, defectiveTotal, lowCount, spend7d }
  }, [pools])

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
        description="Пулы кодов по GTIN: остаток общий на пул, товары привязываются вручную."
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
        {[
          { label: 'Доступно всего', value: kpis.availableTotal, testId: 'kpi-available' },
          { label: 'Расход 7 дней', value: kpis.spend7d, testId: 'kpi-spend-7d' },
          { label: 'Брак', value: kpis.defectiveTotal, testId: 'kpi-defective' },
          {
            label: 'Пулы на исходе',
            value: kpis.lowCount,
            testId: 'kpi-low-stock',
            onClick: () => setStockFilter('low'),
          },
        ].map((kpi) => (
          <Paper
            key={kpi.testId}
            variant="outlined"
            sx={{ p: 1.5, minWidth: 140, flex: 1, cursor: kpi.onClick ? 'pointer' : 'default' }}
            onClick={kpi.onClick}
            data-testid={`${testIdPrefix}-${kpi.testId}`}
          >
            <Typography variant="caption" color="text.secondary">
              {kpi.label}
            </Typography>
            <Typography variant="h6">{kpi.value}</Typography>
          </Paper>
        ))}
      </Stack>

      {showSellerDashboard && pools.length > 0 ? (
        <Stack spacing={1} data-testid={`${testIdPrefix}-seller-dashboard`}>
          {pools.map((row) => {
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
                    Прогноз до: {forecastUntilLabel(row.forecast_days)}
                  </Typography>
                </Stack>
              </Paper>
            )
          })}
        </Stack>
      ) : null}

      <Stack direction={{ xs: 'column', sm: 'row' }} spacing={1}>
        <Button
          variant="contained"
          startIcon={<UploadFileOutlined />}
          disabled={sellerIdRequiredForImport && !effectiveSellerId}
          onClick={() => openImport()}
          data-testid={`${testIdPrefix}-open-import`}
        >
          Загрузить коды
        </Button>
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

      <TableContainer component={Paper} variant="outlined">
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
            ) : filteredPools.length === 0 ? (
              <TableRow>
                <TableCell colSpan={8}>
                  <Stack spacing={1} sx={{ py: 2, alignItems: 'flex-start' }}>
                    <Typography variant="body2" color="text.secondary">
                      {pools.length === 0
                        ? 'Пулов пока нет — загрузите коды из файла.'
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
                        Загрузить коды
                      </Button>
                    ) : null}
                  </Stack>
                </TableCell>
              </TableRow>
            ) : (
              filteredPools.map((row) => {
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
                      {row.forecast_days != null ? `${row.forecast_days} д` : '—'}
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
