import { useCallback, useEffect, useMemo, useState } from 'react'
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
import { readApiErrorMessage } from '../../utils/readApiErrorMessage'
import { printPackagingInstructions } from '../../utils/printPackagingInstructions'

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
// запрос и формат, что и в каталоге фулфилмента (см. CAT-20).
type StockSummaryRow = {
  product_id: string
  sku_code: string
  product_name: string
  quantity: number
  quantity_in_sorting: number
  quantity_in_storage: number
  reserved: number
  available: number
  quantity_fbs: number
  quantity_reserved_directions: number
  quantity_free_fbo: number
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
    ozon_sku: string | null
    ozon_offer_id: string | null
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
    row.ozon_sku ?? '',
    row.ozon_offer_id ?? '',
    row.sku_code,
    row.wb_primary_barcode ?? '',
    ...row.wb_barcodes,
  ]
    .join(' ')
    .toLowerCase()
  return haystack.includes(needle)
}

type Props = {
  token: string
  authHeaders: (t: string) => Record<string, string>
}

export function SellerProductsStockScreen({
  token,
  authHeaders,
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

  // ── Фильтры над таблицей (перенесены из каталога фулфилмента, CAT-20) ─────
  const [filterSearch, setFilterSearch] = useState('')
  const [filterCategory, setFilterCategory] = useState('')
  const [filterMarketplace, setFilterMarketplace] = useState<'wildberries' | 'ozon' | ''>('')

  // ── Резервы: список направлений остатка, только чтение (CAT-20) ──────────
  const [reservesProductId, setReservesProductId] = useState<string | null>(null)
  const [reserveDirections, setReserveDirections] = useState<Record<string, StockDirectionRow[]>>({})
  const [reserveBusy, setReserveBusy] = useState<Set<string>>(new Set())

  const refreshAll = useCallback(async () => {
    setError(null)
    setBusy(true)
    try {
      const res = await fetch(apiUrl('/products/wb-catalog'), { headers: { ...authHeaders(token) } })
      if (!res.ok) {
        setError(await readApiErrorMessage(res))
        return
      }
      setCatalog((await res.json()) as WbCatalogRow[])
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Не удалось загрузить товары.')
    } finally {
      setBusy(false)
    }
  }, [authHeaders, token])

  useEffect(() => {
    void refreshAll()
  }, [refreshAll])

  const loadStock = useCallback(async () => {
    try {
      const res = await fetch(apiUrl('/operations/inventory-balances/summary'), {
        headers: { ...authHeaders(token) },
      })
      if (!res.ok) {
        setError(await readApiErrorMessage(res))
        return
      }
      setStock((await res.json()) as StockSummaryRow[])
    } catch (e) {
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
        stock_in_storage: bal?.quantity_in_storage ?? 0,
        stock_reserved_directions: bal?.quantity_reserved_directions ?? 0,
        stock_free_fbo: bal?.quantity_free_fbo ?? bal?.quantity ?? 0,
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

  const hasMixedMarketplaces = useMemo(
    () =>
      rows.some((row) => row.wb_nm_id != null || Boolean(row.wb_vendor_code)) &&
      rows.some((row) => Boolean(row.ozon_sku || row.ozon_offer_id)),
    [rows],
  )

  useEffect(() => {
    if (!hasMixedMarketplaces) setFilterMarketplace('')
  }, [hasMixedMarketplaces])

  const filteredRows = useMemo(
    () =>
      rows.filter(
        (row) =>
          matchesCatalogSearch(row, filterSearch) &&
          (!filterMarketplace ||
            (filterMarketplace === 'wildberries'
              ? Boolean(row.wb_nm_id != null || row.wb_vendor_code)
              : Boolean(row.ozon_sku || row.ozon_offer_id))) &&
          (!filterCategory || row.wb_subject_name === filterCategory),
      ),
    [rows, filterSearch, filterMarketplace, filterCategory],
  )

  useEffect(() => {
    setPage(0)
  }, [filterSearch, filterMarketplace, filterCategory])

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
      markReserveBusy(productId, true)
      setError(null)
      try {
        const res = await fetch(apiUrl(`/products/${productId}/stock-directions`), {
          headers: { ...authHeaders(token) },
        })
        if (!res.ok) {
          setError(await readApiErrorMessage(res))
          return
        }
        const body = (await res.json()) as StockDirectionRow[]
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
        Каталог товаров, синхронизированных из маркетплейсов. Остаток и резервы здесь только для
        просмотра — их настраивает фулфилмент на своём экране каталога.
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
          {hasMixedMarketplaces ? (
            <FormControl size="small" sx={{ minWidth: 170 }}>
              <InputLabel id="seller-catalog-marketplace-filter-label">Маркетплейс</InputLabel>
              <Select
                labelId="seller-catalog-marketplace-filter-label"
                label="Маркетплейс"
                value={filterMarketplace}
                onChange={(event) =>
                  setFilterMarketplace(event.target.value as 'wildberries' | 'ozon' | '')
                }
                data-testid="seller-catalog-marketplace-filter"
              >
                <MenuItem value="">Все</MenuItem>
                <MenuItem value="wildberries">Wildberries</MenuItem>
                <MenuItem value="ozon">Ozon</MenuItem>
              </Select>
            </FormControl>
          ) : null}
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
              lineHeight: 1.2,
              whiteSpace: 'normal',
            },
            '& .MuiButton-sizeSmall': {
              minHeight: 24,
              lineHeight: 1,
            },
          }}
        >
          <colgroup>
            <col style={{ width: '4%' }} />
            <col style={{ width: '7%' }} />
            <col style={{ width: '15%' }} />
            <col style={{ width: '10%' }} />
            <col style={{ width: '9%' }} />
            <col style={{ width: '11%' }} />
            <col style={{ width: '6%' }} />
            <col style={{ width: '13%' }} />
            <col style={{ width: '8%' }} />
            <col style={{ width: '7%' }} />
            <col style={{ width: '10%' }} />
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
                  <Stack spacing={0.5} sx={{ alignItems: 'flex-start', minWidth: 0 }}>
                    <Typography variant="body2" sx={{ fontWeight: 600 }} title={p.name} noWrap>
                      {p.name}
                    </Typography>
                    {p.ozon_sku || p.ozon_offer_id ? (
                      <Chip
                        size="small"
                        label="Ozon"
                        variant="outlined"
                        data-testid="seller-catalog-marketplace-ozon"
                      />
                    ) : null}
                  </Stack>
                </TableCell>
                <TableCell>
                  <Typography variant="body2" title={p.wb_vendor_code ?? '—'} noWrap>
                    {p.wb_vendor_code ?? '—'}
                  </Typography>
                </TableCell>
                <TableCell>
                  <Typography variant="body2" sx={{ fontWeight: 600 }} title={p.sku_code} noWrap>
                    {p.sku_code}
                  </Typography>
                </TableCell>
                <TableCell>
                  <Typography
                    variant="body2"
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
                  <Stack spacing={0.15} sx={{ minWidth: 0, alignItems: 'flex-end' }}>
                    <Typography
                      variant="caption"
                      data-testid={`seller-catalog-stock-in-storage-${p.id}`}
                      title={`В ячейках ${p.stock_in_storage}`}
                      noWrap
                    >
                      В ячейках {p.stock_in_storage}
                    </Typography>
                    <Typography
                      variant="caption"
                      color="text.secondary"
                      data-testid={`seller-catalog-stock-on-hand-${p.id}`}
                      title={`На ФФ ${p.stock_on_hand}`}
                      noWrap
                    >
                      На ФФ {p.stock_on_hand}
                    </Typography>
                    <Typography
                      variant="caption"
                      color="text.secondary"
                      data-testid={`seller-catalog-stock-free-fbo-${p.id}`}
                      title={`Свободный FBO ${p.stock_free_fbo}`}
                      noWrap
                    >
                      Свободный FBO {p.stock_free_fbo}
                    </Typography>
                  </Stack>
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
                      minWidth: 64,
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
              <Stack direction="row" spacing={2}>
                <Box>
                  <Typography variant="caption" color="text.secondary">
                    Резервы
                  </Typography>
                  <Typography variant="h6">{reservesProduct.stock_reserved_directions} шт</Typography>
                </Box>
                <Box>
                  <Typography variant="caption" color="text.secondary">
                    Свободный FBO
                  </Typography>
                  <Typography variant="h6">{reservesProduct.stock_free_fbo} шт</Typography>
                </Box>
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
    </Box>
  )
}
