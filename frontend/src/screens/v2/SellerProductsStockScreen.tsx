import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import {
  Alert,
  Box,
  Button,
  Checkbox,
  Chip,
  Divider,
  Drawer,
  FormControl,
  FormControlLabel,
  CircularProgress,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
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
  TextField,
  Typography,
} from '@mui/material'
import { apiUrl } from '../../api'
import { ProductPhotoThumb } from '../../components/ProductPhotoThumb'
import { ProductStockLines } from '../../components/ProductStockLines'
import { formatStockQty } from '../../utils/formatStockQty'
import { readApiErrorMessage } from '../../utils/readApiErrorMessage'
import { printPackagingInstructions } from '../../utils/printPackagingInstructions'
import { MarketplaceChip } from '../../ui-kit'
import { FbsStockDialogContainer } from '../ff/products-fbs/FbsStockDialogContainer'

type WbCatalogRow = {
  id: string
  sku_code: string
  name: string
  wb_vendor_code: string | null
  wb_nm_id: number | null
  ozon_sku: string | null
  ozon_offer_id: string | null
  wb_subject_name: string | null
  wb_primary_image_url: string | null
  wb_barcodes: string[]
  wb_primary_barcode: string | null
  wb_size: string | null
  packaging_instructions: string | null
  requires_honest_sign: boolean
  has_packaging_instructions: boolean
}

// Остаток на ФФ по товару — из /operations/inventory-balances/summary. Тот же
// запрос и те же три числа Остаток / Резерв / Доступно, что в каталоге
// фулфилмента (CAT-20, WMS-532 R4).
type StockSummaryRow = {
  product_id: string
  sku_code: string
  product_name: string
  quantity: number
  reserved: number
  available: number
}

// Направления остатка (резервы) — только чтение. Механику резервирования
// правит фулфилмент в своём каталоге, здесь товар только смотрит список.
type StockDirectionRow = {
  id: string
  product_id: string
  name: string
  comment: string | null
  quantity: number
  is_fbs: boolean
}

function matchesCatalogSearch(
  row: {
    name: string
    wb_vendor_code: string | null
    sku_code: string
    wb_primary_barcode: string | null
    wb_barcodes: string[]
  },
  query: string,
): boolean {
  const needle = query.trim().toLowerCase()
  if (!needle) return true
  const haystack = [
    row.name,
    row.wb_vendor_code ?? '',
    row.sku_code,
    row.wb_primary_barcode ?? '',
    ...row.wb_barcodes,
  ]
    .join(' ')
    .toLowerCase()
  return haystack.includes(needle)
}

export type SellerCatalogLoad =
  | { outcome: 'stale' }
  | { outcome: 'loaded'; rows: WbCatalogRow[] }
  | { outcome: 'failed'; message: string }

/**
 * Каталог применяется, только если к моменту ответа вкладка осталась в той же
 * сессии.
 *
 * WMS-488: пока список грузился, сессию могли сменить (другой селлер в соседней
 * вкладке, переключение магазина). Запоздалый ответ — это товары прежнего
 * селлера, и на экране им места нет.
 */
export async function loadSellerCatalog(
  headers: Record<string, string>,
  isCurrentSession: () => boolean,
): Promise<SellerCatalogLoad> {
  try {
    const res = await fetch(apiUrl('/products/wb-catalog'), { headers })
    if (!isCurrentSession()) {
      return { outcome: 'stale' }
    }
    if (!res.ok) {
      const message = await readApiErrorMessage(res)
      return isCurrentSession() ? { outcome: 'failed', message } : { outcome: 'stale' }
    }
    const rows = (await res.json()) as WbCatalogRow[]
    return isCurrentSession() ? { outcome: 'loaded', rows } : { outcome: 'stale' }
  } catch (e) {
    if (!isCurrentSession()) {
      return { outcome: 'stale' }
    }
    return {
      outcome: 'failed',
      message: e instanceof Error ? e.message : 'Не удалось загрузить товары.',
    }
  }
}

type Props = {
  token: string
  authHeaders: (t: string) => Record<string, string>
  sellerId: string
  sellerName: string
  warehouses: Array<{ id: string; name: string; code?: string; is_operational?: boolean }>
}

export function SellerProductsStockScreen({
  token,
  authHeaders,
  sellerId,
  sellerName,
  warehouses,
}: Props) {
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [notice, setNotice] = useState<string | null>(null)
  const [catalog, setCatalog] = useState<WbCatalogRow[]>([])
  const [stock, setStock] = useState<StockSummaryRow[]>([])
  const [page, setPage] = useState(0)
  const [rowsPerPage, setRowsPerPage] = useState(10)
  const [editProduct, setEditProduct] = useState<WbCatalogRow | null>(null)
  const [editText, setEditText] = useState('')
  const [editRequiresHonestSign, setEditRequiresHonestSign] = useState(false)
  const [editBusy, setEditBusy] = useState(false)
  const [selectedProductIds, setSelectedProductIds] = useState<Set<string>>(new Set())
  const [bulkHonestSignBusy, setBulkHonestSignBusy] = useState(false)
  const [stockDialogRows, setStockDialogRows] = useState<WbCatalogRow[] | null>(null)

  // ── Фильтры над таблицей (перенесены из каталога фулфилмента, CAT-20) ─────
  const [filterSearch, setFilterSearch] = useState('')
  const [filterCategory, setFilterCategory] = useState('')

  // ── Резервы: список направлений остатка, только чтение (CAT-20) ──────────
  const [reservesProductId, setReservesProductId] = useState<string | null>(null)
  const [reserveDirections, setReserveDirections] = useState<Record<string, StockDirectionRow[]>>({})
  const [reserveBusy, setReserveBusy] = useState<Set<string>>(new Set())

  // Токен сессии, к которой относятся показанные строки. Держим в ref, чтобы
  // ответ, пришедший после смены сессии, было с чем сравнить (WMS-488).
  const sessionTokenRef = useRef(token)
  useEffect(() => {
    sessionTokenRef.current = token
    // Показанное принадлежит прежнему токену: до ответа по новому на экране
    // не должно остаться ни строки прежнего селлера.
    setCatalog([])
    setStock([])
    setReserveDirections({})
  }, [token])

  const refreshAll = useCallback(async () => {
    const requestToken = token
    const isCurrentSession = () => sessionTokenRef.current === requestToken
    setError(null)
    setBusy(true)
    const result = await loadSellerCatalog({ ...authHeaders(requestToken) }, isCurrentSession)
    if (result.outcome === 'stale') {
      return
    }
    setBusy(false)
    if (result.outcome === 'failed') {
      setError(result.message)
      return
    }
    setCatalog(result.rows)
  }, [authHeaders, token])

  useEffect(() => {
    void refreshAll()
  }, [refreshAll])

  const loadStock = useCallback(async () => {
    const requestToken = token
    try {
      const res = await fetch(apiUrl('/operations/inventory-balances/summary'), {
        headers: { ...authHeaders(requestToken) },
      })
      if (sessionTokenRef.current !== requestToken) {
        return
      }
      if (!res.ok) {
        setError(await readApiErrorMessage(res))
        return
      }
      const body = (await res.json()) as StockSummaryRow[]
      if (sessionTokenRef.current !== requestToken) {
        return
      }
      setStock(body)
    } catch (e) {
      if (sessionTokenRef.current !== requestToken) {
        return
      }
      setError(e instanceof Error ? e.message : 'Не удалось загрузить остатки.')
    }
  }, [authHeaders, token])

  useEffect(() => {
    void loadStock()
  }, [loadStock])

  const rows = useMemo(() => {
    const byProduct = new Map(stock.map((s) => [s.product_id, s]))
    return catalog.map((p) => {
      const bal = byProduct.get(p.id)
      return {
        ...p,
        stock_on_hand: bal?.quantity ?? 0,
        stock_reserved: bal?.reserved ?? 0,
        stock_available: bal?.available ?? 0,
      }
    })
  }, [catalog, stock])

  const categoryOptions = useMemo(() => {
    const set = new Set<string>()
    for (const row of rows) {
      const value = row.wb_subject_name?.trim()
      if (value) set.add(value)
    }
    return Array.from(set).sort((a, b) => a.localeCompare(b, 'ru'))
  }, [rows])

  const filteredRows = useMemo(
    () =>
      rows.filter(
        (row) =>
          matchesCatalogSearch(row, filterSearch) &&
          (!filterCategory || row.wb_subject_name === filterCategory),
      ),
    [rows, filterSearch, filterCategory],
  )

  useEffect(() => {
    setPage(0)
  }, [filterSearch, filterCategory])

  const pagedRows = useMemo(() => {
    const start = page * rowsPerPage
    return filteredRows.slice(start, start + rowsPerPage)
  }, [filteredRows, page, rowsPerPage])

  const selectedRows = useMemo(
    () => catalog.filter((row) => selectedProductIds.has(row.id)),
    [catalog, selectedProductIds],
  )
  const selectedCount = selectedRows.length
  const visibleProductIds = useMemo(() => pagedRows.map((row) => row.id), [pagedRows])
  const visibleSelectedCount = useMemo(
    () => visibleProductIds.filter((id) => selectedProductIds.has(id)).length,
    [selectedProductIds, visibleProductIds],
  )
  const allVisibleSelected = visibleProductIds.length > 0 && visibleSelectedCount === visibleProductIds.length
  const someVisibleSelected = visibleSelectedCount > 0 && !allVisibleSelected

  useEffect(() => {
    const rowIds = new Set(catalog.map((row) => row.id))
    setSelectedProductIds((current) => {
      const next = new Set([...current].filter((id) => rowIds.has(id)))
      return next.size === current.size ? current : next
    })
  }, [catalog])

  function openPackagingEdit(p: WbCatalogRow) {
    setEditProduct(p)
    setEditText(p.packaging_instructions ?? '')
    setEditRequiresHonestSign(Boolean(p.requires_honest_sign))
  }

  function printPackagingTz() {
    if (!editProduct) return
    printPackagingInstructions({
      sku_code: editProduct.sku_code,
      product_name: editProduct.name,
      instructions: editText,
      requires_honest_sign: editRequiresHonestSign,
    })
  }

  async function savePackagingInstructions() {
    if (!editProduct) return
    setEditBusy(true)
    setError(null)
    setNotice(null)
    try {
      const res = await fetch(
        apiUrl(`/products/${editProduct.id}/packaging-instructions`),
        {
          method: 'PATCH',
          headers: { ...authHeaders(token), 'Content-Type': 'application/json' },
          body: JSON.stringify({
            packaging_instructions: editText.trim() || null,
            requires_honest_sign: editRequiresHonestSign,
          }),
        },
      )
      if (!res.ok) {
        setError(await readApiErrorMessage(res))
        return
      }
      setEditProduct(null)
      await refreshAll()
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Не удалось сохранить ТЗ.')
    } finally {
      setEditBusy(false)
    }
  }

  async function applyHonestSignToSelected() {
    const productIdsToUpdate = [...selectedProductIds]
    if (productIdsToUpdate.length === 0) return
    const selectedIds = new Set(productIdsToUpdate)
    setBulkHonestSignBusy(true)
    setError(null)
    setNotice(null)
    try {
      const res = await fetch(apiUrl('/products/requires-honest-sign/bulk'), {
        method: 'PATCH',
        headers: { ...authHeaders(token), 'Content-Type': 'application/json' },
        body: JSON.stringify({
          product_ids: productIdsToUpdate,
          requires_honest_sign: true,
        }),
      })
      if (!res.ok) {
        setError(await readApiErrorMessage(res))
        return
      }
      const body = (await res.json()) as { updated_count: number }
      setCatalog((current) =>
        current.map((row) =>
          selectedIds.has(row.id) ? { ...row, requires_honest_sign: true } : row,
        ),
      )
      setSelectedProductIds(new Set())
      setNotice(`Честный знак включён: ${body.updated_count} товаров.`)
      await refreshAll()
    } catch (e) {
      setError(
        e instanceof Error ? e.message : 'Не удалось включить Честный знак выбранным товарам.',
      )
    } finally {
      setBulkHonestSignBusy(false)
    }
  }

  const toggleSelectedProduct = useCallback((productId: string, checked: boolean) => {
    setSelectedProductIds((current) => {
      const next = new Set(current)
      if (checked) next.add(productId)
      else next.delete(productId)
      return next
    })
  }, [])

  const toggleVisibleProducts = useCallback(
    (checked: boolean) => {
      setSelectedProductIds((current) => {
        const next = new Set(current)
        for (const productId of visibleProductIds) {
          if (checked) next.add(productId)
          else next.delete(productId)
        }
        return next
      })
    },
    [visibleProductIds],
  )

  async function onSyncProducts() {
    setError(null)
    setNotice(null)
    setBusy(true)
    try {
      const res = await fetch(apiUrl('/integrations/wildberries/self/sync-products'), {
        method: 'POST',
        headers: { ...authHeaders(token) },
      })
      if (!res.ok) {
        setError(await readApiErrorMessage(res))
        return
      }
      await refreshAll()
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Не удалось синхронизировать товары.')
    } finally {
      setBusy(false)
    }
  }

  const markReserveBusy = useCallback((productId: string, pending: boolean) => {
    setReserveBusy((current) => {
      const next = new Set(current)
      if (pending) next.add(productId)
      else next.delete(productId)
      return next
    })
  }, [])

  const loadReserveDirections = useCallback(
    async (productId: string) => {
      const requestToken = token
      markReserveBusy(productId, true)
      setError(null)
      try {
        const res = await fetch(apiUrl(`/products/${productId}/stock-directions`), {
          headers: { ...authHeaders(requestToken) },
        })
        if (sessionTokenRef.current !== requestToken) {
          return
        }
        if (!res.ok) {
          setError(await readApiErrorMessage(res))
          return
        }
        const body = (await res.json()) as StockDirectionRow[]
        if (sessionTokenRef.current !== requestToken) {
          return
        }
        setReserveDirections((current) => ({ ...current, [productId]: body }))
      } catch (e) {
        setError(e instanceof Error ? e.message : 'Не удалось загрузить резервы.')
      } finally {
        markReserveBusy(productId, false)
      }
    },
    [authHeaders, markReserveBusy, token],
  )

  const openReserves = useCallback(
    async (productId: string) => {
      setReservesProductId(productId)
      if (reserveDirections[productId] == null) {
        await loadReserveDirections(productId)
      }
    },
    [loadReserveDirections, reserveDirections],
  )

  const closeReserves = useCallback(() => {
    setReservesProductId(null)
  }, [])

  const reservesProduct = useMemo(
    () => rows.find((row) => row.id === reservesProductId) ?? null,
    [reservesProductId, rows],
  )

  return (
    <Box
      sx={{
        minWidth: 0,
        width: '100%',
        maxWidth: '100%',
        boxSizing: 'border-box',
        overflow: 'hidden',
      }}
    >
      <Typography variant="h5" gutterBottom>
        Товары
      </Typography>
      <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
        Каталог товаров, синхронизированных из маркетплейсов.
      </Typography>

      {error ? (
        <Alert severity="error" sx={{ mb: 2 }} data-testid="seller-products-error">
          {error}
        </Alert>
      ) : null}
      {notice ? (
        <Alert
          severity="success"
          sx={{ mb: 2 }}
          data-testid="seller-products-notice"
          onClose={() => setNotice(null)}
        >
          {notice}
        </Alert>
      ) : null}

      <Paper variant="outlined" sx={{ p: 2, mb: 2 }} data-testid="seller-products-actions">
        <Stack direction="row" spacing={1.5} sx={{ flexWrap: 'wrap', alignItems: 'center' }}>
          <Button
            variant="contained"
            data-testid="seller-sync-products"
            disabled={busy}
            onClick={() => void onSyncProducts()}
          >
            Синхронизировать по API
          </Button>
          <Button
            variant="outlined"
            color="success"
            disabled={bulkHonestSignBusy || busy || selectedCount === 0}
            onClick={() => void applyHonestSignToSelected()}
            data-testid="seller-products-bulk-honest-sign"
          >
            Включить ЧЗ
          </Button>
          {busy ? <CircularProgress size={18} /> : null}
          {bulkHonestSignBusy ? <CircularProgress size={18} /> : null}
        </Stack>
      </Paper>

      {selectedCount > 0 ? (
        <Paper
          variant="outlined"
          sx={{ p: 2, mb: 2, borderColor: 'primary.main' }}
          data-testid="seller-catalog-selection-bar"
        >
          <Stack
            direction={{ xs: 'column', sm: 'row' }}
            spacing={2}
            sx={{ alignItems: { sm: 'center' }, justifyContent: 'space-between' }}
          >
            <Typography variant="subtitle2" data-testid="seller-catalog-selection-count">
              Выбрано {selectedCount}
            </Typography>
            <Button
              variant="contained"
              onClick={() => setStockDialogRows(selectedRows)}
              data-testid="seller-catalog-fbs-set-stock"
            >
              Задать остаток · {selectedCount}
            </Button>
          </Stack>
        </Paper>
      ) : null}

      <Paper variant="outlined" sx={{ p: 2, mb: 2 }} data-testid="seller-catalog-filters">
        <Stack
          direction={{ xs: 'column', sm: 'row' }}
          spacing={2}
          sx={{ alignItems: { sm: 'center' }, flexWrap: 'wrap', rowGap: 2 }}
        >
          <TextField
            size="small"
            placeholder="Поиск по названию, артикулу, SKU или ШК"
            value={filterSearch}
            onChange={(e) => setFilterSearch(e.target.value)}
            slotProps={{ htmlInput: { 'data-testid': 'seller-catalog-search' } }}
            sx={{ minWidth: 260 }}
          />
          <FormControl size="small" sx={{ minWidth: 200 }}>
            <InputLabel id="seller-catalog-category-filter-label">Категория</InputLabel>
            <Select
              labelId="seller-catalog-category-filter-label"
              label="Категория"
              value={filterCategory}
              onChange={(e) => setFilterCategory(e.target.value)}
              data-testid="seller-catalog-category-filter"
            >
              <MenuItem value="">Все категории</MenuItem>
              {categoryOptions.map((c) => (
                <MenuItem key={c} value={c}>
                  {c}
                </MenuItem>
              ))}
            </Select>
          </FormControl>
          <Typography variant="body2" color="text.secondary" data-testid="seller-catalog-filter-count">
            Найдено: {filteredRows.length} из {rows.length}
          </Typography>
        </Stack>
      </Paper>

      <TableContainer
        component={Paper}
        variant="outlined"
        sx={{ width: '100%', maxWidth: '100%', minWidth: 0, overflowX: 'hidden' }}
        data-testid="seller-products-list"
      >
        <Table
          stickyHeader
          size="small"
          data-testid="seller-products-table"
          sx={{
            width: '100%',
            tableLayout: 'fixed',
            '& .MuiTableCell-root': {
              px: 1,
              py: 0.375,
              overflow: 'hidden',
              verticalAlign: 'middle',
            },
            '& .MuiTypography-root': {
              lineHeight: 1.15,
            },
            '& .MuiTableCell-head': {
              fontWeight: 600,
              fontSize: '0.7rem',
              lineHeight: 1.2,
              whiteSpace: 'normal',
            },
            '& .MuiButton-sizeSmall': {
              minHeight: 24,
              lineHeight: 1,
            },
          }}
        >
          {/* «Остаток» шире за счёт артикулов (WMS-532 R3, R4): на 1024 px в 10 %
              не помещалось даже «Доступно 27», а «−1 234 567» срезалось. Артикулы
              и SKU по-прежнему в одну строку с многоточием и подсказкой. */}
          <colgroup>
            <col style={{ width: '5%' }} />
            <col style={{ width: '5%' }} />
            <col style={{ width: '10.5%' }} />
            <col style={{ width: '15%' }} />
            <col style={{ width: '14.5%' }} />
            <col style={{ width: '10.5%' }} />
            <col style={{ width: '8%' }} />
            <col style={{ width: '15%' }} />
            <col style={{ width: '6%' }} />
            <col style={{ width: '4%' }} />
            <col style={{ width: '7.5%' }} />
          </colgroup>
          <TableHead>
            <TableRow>
              <TableCell padding="checkbox">
                <Checkbox
                  size="small"
                  checked={allVisibleSelected}
                  indeterminate={someVisibleSelected}
                  disabled={visibleProductIds.length === 0}
                  onChange={(event) => toggleVisibleProducts(event.target.checked)}
                  slotProps={{ input: { 'aria-label': 'Выбрать товары на странице' } }}
                  data-testid="seller-products-select-all"
                />
              </TableCell>
              <TableCell>Фото</TableCell>
              <TableCell>Название</TableCell>
              <TableCell>Артикул продавца</TableCell>
              <TableCell>SKU</TableCell>
              <TableCell>ШК</TableCell>
              <TableCell>Размер</TableCell>
              <TableCell align="right">Остаток</TableCell>
              <TableCell>ТЗ</TableCell>
              <TableCell>ЧЗ</TableCell>
              <TableCell>Резервы</TableCell>
            </TableRow>
          </TableHead>
          <TableBody>
            {pagedRows.map((p) => (
              <TableRow
                hover
                selected={selectedProductIds.has(p.id)}
                data-testid="seller-product-row"
                key={p.id}
                sx={{ height: 68 }}
              >
                <TableCell padding="checkbox">
                  <Checkbox
                    size="small"
                    checked={selectedProductIds.has(p.id)}
                    onChange={(event) => toggleSelectedProduct(p.id, event.target.checked)}
                    slotProps={{ input: { 'aria-label': `Выбрать товар ${p.sku_code}` } }}
                    data-testid={`seller-product-select-${p.id}`}
                  />
                </TableCell>
                <TableCell>
                  <ProductPhotoThumb src={p.wb_primary_image_url} />
                </TableCell>
                <TableCell>
                  <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.75, minWidth: 0 }}>
                    <Typography
                      variant="caption"
                      sx={{
                        minWidth: 0,
                        fontWeight: 600,
                        display: '-webkit-box',
                        WebkitLineClamp: 2,
                        WebkitBoxOrient: 'vertical',
                        overflow: 'hidden',
                      }}
                      title={p.name}
                    >
                      {p.name}
                    </Typography>
                    {p.ozon_sku || p.ozon_offer_id ? (
                      <MarketplaceChip marketplace="ozon" testId="seller-catalog-marketplace-ozon" />
                    ) : null}
                  </Box>
                </TableCell>
                <TableCell>
                  <Typography
                    variant="caption"
                    sx={{ fontSize: '0.7rem' }}
                    title={p.wb_vendor_code ?? '—'}
                    noWrap
                  >
                    {p.wb_vendor_code ?? '—'}
                  </Typography>
                </TableCell>
                <TableCell>
                  <Typography
                    variant="caption"
                    sx={{ fontSize: '0.7rem', fontWeight: 600 }}
                    title={p.sku_code}
                    noWrap
                  >
                    {p.sku_code}
                  </Typography>
                </TableCell>
                <TableCell>
                  <Typography
                    variant="caption"
                    sx={{ fontSize: '0.7rem' }}
                    title={p.wb_primary_barcode ?? p.wb_barcodes[0] ?? '—'}
                    noWrap
                  >
                    {p.wb_primary_barcode ?? p.wb_barcodes[0] ?? '—'}
                  </Typography>
                </TableCell>
                <TableCell>
                  <Typography variant="body2" title={p.wb_size ?? '—'} noWrap>
                    {p.wb_size ?? '—'}
                  </Typography>
                </TableCell>
                <TableCell align="right">
                  <ProductStockLines
                    totals={{
                      onHand: p.stock_on_hand,
                      reserved: p.stock_reserved,
                      available: p.stock_available,
                    }}
                    productId={p.id}
                    testIdPrefix="seller-catalog-stock"
                    fontSize="0.65rem"
                  />
                </TableCell>
                <TableCell sx={{ minWidth: 0 }}>
                  <Button
                    size="small"
                    variant={p.has_packaging_instructions ? 'contained' : 'outlined'}
                    color={p.has_packaging_instructions ? 'primary' : 'inherit'}
                    onClick={() => openPackagingEdit(p)}
                    data-testid={`seller-packaging-edit-${p.id}`}
                    aria-label={p.has_packaging_instructions ? 'Редактировать ТЗ' : 'Добавить ТЗ'}
                    title={p.has_packaging_instructions ? 'Редактировать ТЗ' : 'Добавить ТЗ'}
                    sx={{
                      minWidth: 56,
                      px: 1,
                      ...(p.has_packaging_instructions
                        ? {}
                        : { color: 'text.secondary', borderColor: 'divider' }),
                    }}
                  >
                    ТЗ
                  </Button>
                </TableCell>
                <TableCell sx={{ minWidth: 0 }}>
                  {p.requires_honest_sign ? (
                    <Chip
                      size="small"
                      label="ЧЗ"
                      color="info"
                      variant="outlined"
                      data-testid={`seller-honest-sign-status-${p.id}`}
                    />
                  ) : null}
                </TableCell>
                <TableCell sx={{ minWidth: 0 }}>
                  <Button
                    size="small"
                    variant="outlined"
                    onClick={() => void openReserves(p.id)}
                    data-testid={`seller-catalog-reserves-${p.id}`}
                    sx={{ minWidth: 0, px: 1 }}
                  >
                    Резервы
                  </Button>
                </TableCell>
              </TableRow>
            ))}
            {catalog.length === 0 ? (
              <TableRow>
                <TableCell colSpan={11}>
                  <Typography variant="body2" color="text.secondary">
                    Пока нет товаров.
                  </Typography>
                </TableCell>
              </TableRow>
            ) : filteredRows.length === 0 && !busy ? (
              <TableRow>
                <TableCell colSpan={11}>
                  <Typography variant="body2" color="text.secondary">
                    Ничего не найдено.
                  </Typography>
                </TableCell>
              </TableRow>
            ) : null}
          </TableBody>
        </Table>
        <TablePagination
          component="div"
          count={filteredRows.length}
          page={page}
          onPageChange={(_, next) => setPage(next)}
          rowsPerPage={rowsPerPage}
          onRowsPerPageChange={(e) => {
            const next = Number(e.target.value)
            setRowsPerPage(next)
            setPage(0)
          }}
          rowsPerPageOptions={[10, 20, 50, 100]}
          labelRowsPerPage="На странице"
          data-testid="seller-products-pagination"
        />
      </TableContainer>

      <Dialog
        open={editProduct != null}
        onClose={() => !editBusy && setEditProduct(null)}
        fullWidth
        maxWidth="sm"
        data-testid="seller-packaging-dialog"
      >
        <DialogTitle>ТЗ на упаковку</DialogTitle>
        <DialogContent>
          {editProduct ? (
            <Stack spacing={2} sx={{ mt: 1 }}>
              <Typography variant="body2" color="text.secondary">
                {editProduct.sku_code} · {editProduct.name}
              </Typography>
              <FormControlLabel
                control={
                  <Checkbox
                    checked={editRequiresHonestSign}
                    onChange={(e) => setEditRequiresHonestSign(e.target.checked)}
                    data-testid="seller-requires-honest-sign"
                  />
                }
                label="Нужен Честный знак при упаковке"
              />
              <TextField
                label="Инструкция для фулфилмента"
                multiline
                minRows={4}
                fullWidth
                value={editText}
                onChange={(e) => setEditText(e.target.value)}
                slotProps={{ htmlInput: { 'data-testid': 'seller-packaging-text' } }}
              />
            </Stack>
          ) : null}
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setEditProduct(null)} disabled={editBusy}>
            Отмена
          </Button>
          <Button
            variant="outlined"
            disabled={editBusy || !editProduct}
            onClick={printPackagingTz}
            data-testid="seller-packaging-print"
          >
            Печать
          </Button>
          <Button
            variant="contained"
            disabled={editBusy}
            onClick={() => void savePackagingInstructions()}
            data-testid="seller-packaging-save"
          >
            Сохранить
          </Button>
        </DialogActions>
      </Dialog>

      <Drawer
        anchor="right"
        open={reservesProduct != null}
        onClose={closeReserves}
        slotProps={{
          paper: { sx: { width: { xs: '100%', sm: 460 }, maxWidth: '100%' } },
        }}
        data-testid={reservesProduct ? `seller-reserves-panel-${reservesProduct.id}` : undefined}
      >
        {reservesProduct ? (
          <Box sx={{ p: 2.5 }}>
            <Stack spacing={2}>
              <Box>
                <Typography variant="h6">Резервы</Typography>
                <Typography
                  variant="body2"
                  color="text.secondary"
                  sx={{
                    display: '-webkit-box',
                    WebkitLineClamp: 2,
                    WebkitBoxOrient: 'vertical',
                    overflow: 'hidden',
                  }}
                >
                  {reservesProduct.sku_code} · {reservesProduct.name}
                </Typography>
              </Box>
              {/* Те же три числа, что в ячейке «Остаток» этой строки (WMS-532 R5):
                  направления ниже — лишь часть резерва. */}
              <Stack direction="row" sx={{ flexWrap: 'wrap', columnGap: 2, rowGap: 1 }}>
                {[
                  { key: 'on-hand', label: 'Остаток', value: reservesProduct.stock_on_hand },
                  { key: 'reserved', label: 'Резерв', value: reservesProduct.stock_reserved },
                  { key: 'available', label: 'Доступно', value: reservesProduct.stock_available },
                ].map((item) => (
                  <Box key={item.key} data-testid={`seller-reserves-${item.key}`}>
                    <Typography variant="caption" color="text.secondary">
                      {item.label}
                    </Typography>
                    <Typography variant="h6" sx={{ whiteSpace: 'nowrap' }}>
                      {formatStockQty(item.value)} шт
                    </Typography>
                  </Box>
                ))}
              </Stack>
              <Divider />
              <Stack spacing={1}>
                {reserveBusy.has(reservesProduct.id) ? (
                  <Stack direction="row" spacing={1} sx={{ alignItems: 'center' }}>
                    <CircularProgress size={18} />
                    <Typography variant="body2" color="text.secondary">
                      Загружаем…
                    </Typography>
                  </Stack>
                ) : null}
                {!reserveBusy.has(reservesProduct.id) &&
                (reserveDirections[reservesProduct.id]?.length ?? 0) === 0 ? (
                  <Typography variant="body2" color="text.secondary">
                    Направлений пока нет.
                  </Typography>
                ) : null}
                {(reserveDirections[reservesProduct.id] ?? []).map((direction) => (
                  <Paper
                    key={direction.id}
                    variant="outlined"
                    sx={{ p: 1.25 }}
                    data-testid={`seller-reserve-direction-row-${direction.id}`}
                  >
                    <Typography
                      variant="body2"
                      sx={{
                        fontWeight: 600,
                        display: '-webkit-box',
                        WebkitLineClamp: 2,
                        WebkitBoxOrient: 'vertical',
                        overflow: 'hidden',
                      }}
                    >
                      {direction.name}
                    </Typography>
                    <Typography variant="caption" color="text.secondary">
                      {direction.is_fbs ? 'FBS-пул' : 'Резерв/набор'} · {direction.quantity} шт
                    </Typography>
                    {direction.comment ? (
                      <Typography
                        variant="caption"
                        color="text.secondary"
                        sx={{
                          display: '-webkit-box',
                          WebkitLineClamp: 2,
                          WebkitBoxOrient: 'vertical',
                          overflow: 'hidden',
                        }}
                      >
                        {direction.comment}
                      </Typography>
                    ) : null}
                  </Paper>
                ))}
              </Stack>
              <Divider />
              <Button onClick={closeReserves} data-testid="seller-reserves-close">
                Закрыть
              </Button>
            </Stack>
          </Box>
        ) : null}
      </Drawer>

      {stockDialogRows ? (
        <FbsStockDialogContainer
          token={token}
          sellerId={sellerId}
          sellerName={sellerName}
          chosen={stockDialogRows}
          warehouses={warehouses}
          canEditBindings={false}
          onClose={() => setStockDialogRows(null)}
          onChanged={() => void loadStock()}
          onLoadError={setError}
        />
      ) : null}
    </Box>
  )
}
