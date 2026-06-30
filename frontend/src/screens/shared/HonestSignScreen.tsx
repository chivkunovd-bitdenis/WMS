import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  Alert,
  Box,
  Button,
  Chip,
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
import { apiUrl } from '../../api'
import { ProductBarcodePrintButton } from '../../components/ProductBarcodePrintButton'
import { ProductPhotoThumb } from '../../components/ProductPhotoThumb'
import { useWbProductCatalog } from '../../hooks/useWbProductCatalog'
import { PageHeader } from '../../ui/PageHeader'
import { productDisplayMetaFromCatalog } from '../../types/wbProductCatalog'
import { readApiErrorMessage } from '../../utils/readApiErrorMessage'
import { MarkingImportDialog } from './MarkingImportDialog'
import { MarkingSellerPicker } from './MarkingSellerPicker'

/** @deprecated Pool-centric type; kept for imports from legacy tests/helpers. */
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

type SharedBasketRow = {
  pool_id: string
  gtin: string
  title: string
  available: number
  products_count: number
}

type ProductInventoryRow = {
  product_id: string
  sku_code: string
  product_name: string
  requires_honest_sign: boolean
  available_count: number
  printed_count: number
  personal_available: number
  shared_baskets: SharedBasketRow[]
}

type MarkingInventoryResponse = {
  rows: ProductInventoryRow[]
  unlinked_available_count: number
}

type StockFilter = 'all' | 'low' | 'empty'

type KpiCardConfig = {
  label: string
  value: number | string
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
  /** Seller portal: highlight low-stock product cards above the table */
  showSellerDashboard?: boolean
}

function productMatchesSearch(row: ProductInventoryRow, query: string): boolean {
  const needle = query.trim().toLowerCase()
  if (!needle) {
    return true
  }
  return (
    row.product_name.toLowerCase().includes(needle) ||
    row.sku_code.toLowerCase().includes(needle)
  )
}

function isLowPersonalStock(row: ProductInventoryRow): boolean {
  return row.personal_available > 0 && row.personal_available <= 10
}

function isProblematicProduct(row: ProductInventoryRow): boolean {
  return row.personal_available === 0 || isLowPersonalStock(row)
}

function hasMarkingActivity(row: ProductInventoryRow): boolean {
  return (
    row.personal_available > 0 ||
    row.printed_count > 0 ||
    row.shared_baskets.length > 0 ||
    row.requires_honest_sign
  )
}

function SharedBasketChips({
  baskets,
  testIdPrefix,
  productId,
}: {
  baskets: SharedBasketRow[]
  testIdPrefix: string
  productId: string
}) {
  if (baskets.length === 0) {
    return (
      <Typography variant="body2" color="text.secondary">
        —
      </Typography>
    )
  }
  return (
    <Stack direction="row" spacing={0.5} sx={{ flexWrap: 'wrap' }}>
      {baskets.map((b) => (
        <Chip
          key={b.pool_id}
          size="small"
          variant="outlined"
          label={`🧺 ${b.available} · на ${b.products_count} тов.`}
          data-testid={`${testIdPrefix}-product-basket-${productId}-${b.pool_id}`}
        />
      ))}
    </Stack>
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
  const productsTableRef = useRef<HTMLDivElement>(null)
  const inventoryLoadAbortRef = useRef<AbortController | null>(null)
  const [products, setProducts] = useState<ProductInventoryRow[]>([])
  const [unlinkedAvailable, setUnlinkedAvailable] = useState(0)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [search, setSearch] = useState('')
  const [stockFilter, setStockFilter] = useState<StockFilter>('all')
  const [importOpen, setImportOpen] = useState(false)
  const [toastMessage, setToastMessage] = useState<string | null>(null)

  const effectiveSellerId = sellerId ?? selectedSellerId
  const importDisabled = sellerIdRequiredForImport && !effectiveSellerId
  const { catalogById } = useWbProductCatalog(
    token,
    !sellerIdRequiredForImport || Boolean(effectiveSellerId),
    effectiveSellerId,
  )

  const loadInventory = useCallback(async () => {
    inventoryLoadAbortRef.current?.abort()
    const ac = new AbortController()
    inventoryLoadAbortRef.current = ac
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
      const res = await fetch(apiUrl(`/operations/marking-codes/inventory${q}`), {
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
      const body = (await res.json()) as MarkingInventoryResponse
      setProducts(body.rows)
      setUnlinkedAvailable(body.unlinked_available_count)
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
      setProducts([])
      setUnlinkedAvailable(0)
      return
    }
    void loadInventory()
    return () => {
      inventoryLoadAbortRef.current?.abort()
    }
  }, [effectiveSellerId, loadInventory, sellerIdRequiredForImport])

  const kpis = useMemo(() => {
    const personalTotal = products.reduce((s, p) => s + p.personal_available, 0)
    const lowCount = products.filter(isLowPersonalStock).length
    const sharedBasketProducts = products.filter((p) => p.shared_baskets.length > 0).length
    return { personalTotal, lowCount, sharedBasketProducts }
  }, [products])

  const scrollToProductsTable = useCallback(() => {
    productsTableRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' })
  }, [])

  const kpiCards = useMemo((): KpiCardConfig[] => {
    return [
      {
        label: 'Доступно личных',
        value: kpis.personalTotal,
        testId: 'kpi-available',
        interactive: true,
        active: stockFilter === 'all',
        onClick: () => {
          setStockFilter('all')
          scrollToProductsTable()
        },
      },
      {
        label: 'С общими корзинами',
        value: kpis.sharedBasketProducts,
        testId: 'kpi-spend-7d',
        interactive: false,
      },
      {
        label: 'Брак',
        value: '→',
        testId: 'kpi-defective',
        interactive: true,
        onClick: () => {
          navigate(`${routeBase}/honest-sign/ledger?event_type=defective`)
        },
      },
      {
        label: 'На исходе',
        value: kpis.lowCount,
        testId: 'kpi-low-stock',
        interactive: true,
        active: stockFilter === 'low',
        onClick: () => {
          setStockFilter('low')
          scrollToProductsTable()
        },
      },
    ]
  }, [kpis, navigate, routeBase, scrollToProductsTable, stockFilter])

  const filteredProducts = useMemo(() => {
    return products.filter((row) => {
      if (!productMatchesSearch(row, search)) {
        return false
      }
      if (stockFilter === 'empty') {
        return row.personal_available === 0
      }
      if (stockFilter === 'low') {
        return isLowPersonalStock(row)
      }
      return true
    })
  }, [products, search, stockFilter])

  const problematicProducts = useMemo(
    () =>
      filteredProducts.filter(
        (row) => isProblematicProduct(row) && hasMarkingActivity(row),
      ),
    [filteredProducts],
  )

  const tableProducts = useMemo(() => {
    if (!showSellerDashboard) {
      return filteredProducts
    }
    const problematicIds = new Set(problematicProducts.map((row) => row.product_id))
    return filteredProducts.filter((row) => !problematicIds.has(row.product_id))
  }, [filteredProducts, problematicProducts, showSellerDashboard])

  const openImport = () => {
    if (sellerIdRequiredForImport && !effectiveSellerId) {
      return
    }
    setImportOpen(true)
  }

  const closeImport = () => {
    setImportOpen(false)
  }

  const hasAnyMarkingData = useMemo(
    () =>
      products.some(
        (p) =>
          p.personal_available > 0 ||
          p.printed_count > 0 ||
          p.shared_baskets.length > 0,
      ) || unlinkedAvailable > 0,
    [products, unlinkedAvailable],
  )

  return (
    <Stack spacing={2} data-testid={`${testIdPrefix}-page`}>
      <PageHeader
        title="Честный знак"
        description="Остатки кодов маркировки по товарам: личный запас и общие корзины на несколько SKU."
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

      {unlinkedAvailable > 0 ? (
        <Alert severity="info" data-testid={`${testIdPrefix}-unlinked-hint`}>
          Кодов без привязки к товару: {unlinkedAvailable}. Загрузите файл и привяжите товары при
          импорте.
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

      {showSellerDashboard && problematicProducts.length > 0 ? (
        <Stack spacing={1} data-testid={`${testIdPrefix}-seller-dashboard`}>
          <Typography variant="subtitle2" color="text.secondary">
            Требуют внимания
          </Typography>
          {problematicProducts.map((row) => {
            const low = isLowPersonalStock(row)
            return (
              <Paper
                key={row.product_id}
                variant="outlined"
                sx={{
                  p: 2,
                  bgcolor: low ? 'error.50' : row.personal_available === 0 ? 'warning.50' : 'background.paper',
                }}
                data-testid={`${testIdPrefix}-product-card-${row.product_id}`}
              >
                <Stack
                  direction={{ xs: 'column', sm: 'row' }}
                  spacing={1}
                  sx={{ justifyContent: 'space-between', alignItems: { sm: 'center' } }}
                >
                  <Box>
                    <Typography variant="subtitle1" sx={{ fontWeight: 600 }}>
                      {row.product_name}
                    </Typography>
                    <Typography variant="caption" color="text.secondary">
                      {row.sku_code}
                    </Typography>
                  </Box>
                  <Button
                    size="small"
                    variant="contained"
                    startIcon={<UploadFileOutlined />}
                    onClick={() => openImport()}
                    data-testid={`${testIdPrefix}-product-card-upload-${row.product_id}`}
                  >
                    Догрузить
                  </Button>
                </Stack>
                <Stack direction="row" spacing={2} sx={{ mt: 1, flexWrap: 'wrap' }}>
                  <Typography variant="body2">Личный остаток: {row.personal_available}</Typography>
                  <Typography variant="body2">Напечатано: {row.printed_count}</Typography>
                  {row.shared_baskets.length > 0 ? (
                    <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.5 }}>
                      <Typography variant="body2">Корзины:</Typography>
                      <SharedBasketChips
                        baskets={row.shared_baskets}
                        testIdPrefix={testIdPrefix}
                        productId={row.product_id}
                      />
                    </Box>
                  ) : null}
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

      <Paper variant="outlined" sx={{ p: 2 }}>
        <Stack direction={{ xs: 'column', sm: 'row' }} spacing={1.5} sx={{ alignItems: { sm: 'center' } }}>
          <TextField
            size="small"
            label="Поиск"
            placeholder="Артикул или название"
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
      </Paper>

      <TableContainer component={Paper} variant="outlined" ref={productsTableRef}>
        <Table
          size="small"
          sx={{ tableLayout: 'fixed' }}
          data-testid={`${testIdPrefix}-products-table`}
        >
          <TableHead>
            <TableRow>
              <TableCell sx={{ minWidth: 280 }}>Товар</TableCell>
              <TableCell align="right" sx={{ width: 110, whiteSpace: 'nowrap' }}>
                Личный остаток
              </TableCell>
              <TableCell sx={{ minWidth: 160 }}>Общая корзина</TableCell>
              <TableCell align="right" sx={{ width: 100, whiteSpace: 'nowrap' }}>
                Напечатано
              </TableCell>
              <TableCell align="right" sx={{ width: 88, whiteSpace: 'nowrap' }}>
                Действия
              </TableCell>
            </TableRow>
          </TableHead>
          <TableBody>
            {busy ? (
              Array.from({ length: 3 }).map((_, i) => (
                <TableRow key={i}>
                  <TableCell colSpan={5}>
                    <Skeleton height={32} />
                  </TableCell>
                </TableRow>
              ))
            ) : tableProducts.length === 0 ? (
              <TableRow>
                <TableCell colSpan={5}>
                  <Stack spacing={1} sx={{ py: 2, alignItems: 'flex-start' }}>
                    <Typography variant="body2" color="text.secondary">
                      {!hasAnyMarkingData
                        ? 'Пока нет кодов маркировки — загрузите КМ из файла.'
                        : showSellerDashboard && problematicProducts.length > 0
                          ? 'Товары, требующие внимания, показаны в блоке выше. По фильтру в таблице ничего нет.'
                          : 'Ничего не найдено по фильтру.'}
                    </Typography>
                    {!hasAnyMarkingData ? (
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
              tableProducts.map((row) => {
                const low = isLowPersonalStock(row)
                const displayMeta = productDisplayMetaFromCatalog(
                  row.product_id,
                  { sku_code: row.sku_code, product_name: row.product_name },
                  catalogById,
                )
                return (
                  <TableRow
                    key={row.product_id}
                    hover
                    sx={{ cursor: 'pointer' }}
                    onClick={() =>
                      navigate(`${routeBase}/honest-sign/product/${row.product_id}`)
                    }
                    data-testid={`${testIdPrefix}-product-row-${row.product_id}`}
                  >
                    <TableCell>
                      <Stack direction="row" spacing={1.5} sx={{ alignItems: 'center', minWidth: 0 }}>
                        <ProductPhotoThumb
                          src={displayMeta.wb_primary_image_url}
                          alt={displayMeta.product_name}
                          testId={`${testIdPrefix}-product-photo-${row.product_id}`}
                        />
                        <Box sx={{ minWidth: 0, flex: 1 }}>
                          <Typography
                            variant="body2"
                            sx={{ fontWeight: 700 }}
                            data-testid={`${testIdPrefix}-product-sku-${row.product_id}`}
                          >
                            {displayMeta.sku_code}
                          </Typography>
                          <Typography
                            variant="body2"
                            noWrap
                            title={displayMeta.product_name}
                            data-testid={`${testIdPrefix}-product-name-${row.product_id}`}
                          >
                            {displayMeta.product_name}
                          </Typography>
                          {displayMeta.wb_size ? (
                            <Typography
                              variant="caption"
                              color="text.secondary"
                              data-testid={`${testIdPrefix}-product-size-${row.product_id}`}
                            >
                              Размер: {displayMeta.wb_size}
                            </Typography>
                          ) : null}
                          {row.requires_honest_sign ? (
                            <Chip
                              size="small"
                              color="primary"
                              variant="outlined"
                              label="ЧЗ"
                              sx={{ alignSelf: 'flex-start', mt: 0.25 }}
                            />
                          ) : null}
                        </Box>
                      </Stack>
                    </TableCell>
                    <TableCell
                      align="right"
                      sx={{ color: low ? 'error.main' : undefined, fontWeight: low ? 600 : 400 }}
                    >
                      {row.personal_available}
                    </TableCell>
                    <TableCell>
                      <SharedBasketChips
                        baskets={row.shared_baskets}
                        testIdPrefix={testIdPrefix}
                        productId={row.product_id}
                      />
                    </TableCell>
                    <TableCell align="right">{row.printed_count}</TableCell>
                    <TableCell align="right" onClick={(e) => e.stopPropagation()}>
                      <Stack direction="row" spacing={0.25} sx={{ justifyContent: 'flex-end' }}>
                        <ProductBarcodePrintButton
                          meta={displayMeta}
                          testId={`${testIdPrefix}-product-print-${row.product_id}`}
                        />
                        <ChevronRightOutlined fontSize="small" color="action" sx={{ mt: 0.75 }} />
                      </Stack>
                    </TableCell>
                  </TableRow>
                )
              })
            )}
          </TableBody>
        </Table>
      </TableContainer>

      {importOpen && effectiveSellerId ? (
        <MarkingImportDialog
          open
          token={token}
          sellerId={effectiveSellerId}
          testIdPrefix={testIdPrefix}
          onClose={closeImport}
          onImported={(message) => {
            setToastMessage(message)
            void loadInventory()
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
