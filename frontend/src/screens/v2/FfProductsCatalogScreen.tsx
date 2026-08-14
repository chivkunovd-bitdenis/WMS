import { useCallback, useEffect, useMemo, useState } from 'react'
import {
  Alert,
  Box,
  Button,
  Checkbox,
  Chip,
  FormControlLabel,
  CircularProgress,
  Divider,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  FormControl,
  IconButton,
  InputLabel,
  MenuItem,
  Paper,
  Popover,
  Select,
  Stack,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  TableSortLabel,
  TextField,
  Tooltip,
  Typography,
} from '@mui/material'
import Inventory2OutlinedIcon from '@mui/icons-material/Inventory2Outlined'
import { apiUrl } from '../../api'
import { ProductPhotoThumb } from '../../components/ProductPhotoThumb'
import { ProductBarcodeCell } from '../../components/ProductBarcodeCell'
import { ProductBarcodePrintButton } from '../../components/ProductBarcodePrintButton'
import { FfProductMarkingPrintProvider } from '../../components/FfProductMarkingPrintProvider'
import { readApiErrorMessage } from '../../utils/readApiErrorMessage'
import { printPackagingInstructions } from '../../utils/printPackagingInstructions'
import {
  catalogRowToDisplayMeta,
  resolveProductPrimaryBarcode,
} from '../../types/wbProductCatalog'
import { FfManualProductCreateDialog } from '../ff/FfManualProductCreateDialog'
import { FfProductTzImportDialog } from '../ff/FfProductTzImportDialog'
import { FfSellerCreateDialog } from '../ff/FfSellerCreateDialog'

type SellerRow = { id: string; name: string }

type FfCatalogRow = {
  id: string
  seller_id: string | null
  seller_name: string | null
  name: string
  sku_code: string
  wb_nm_id: number | null
  wb_vendor_code: string | null
  wb_primary_image_url: string | null
  wb_barcodes: string[]
  wb_primary_barcode: string | null
  wb_size: string | null
  wb_color: string | null
  wb_brand: string | null
  wb_composition: string | null
  packaging_instructions: string | null
  requires_honest_sign: boolean
  has_packaging_instructions: boolean
  is_manual?: boolean
}

type StockSummaryRow = {
  product_id: string
  sku_code: string
  product_name: string
  quantity: number
  quantity_unpacked: number
  quantity_packed: number
  quantity_in_sorting: number
  quantity_in_storage: number
  reserved: number
  available: number
  quantity_fbs: number
  quantity_reserved_directions: number
  quantity_free_fbo: number
}

type Props = {
  token: string
  authHeaders: (t: string) => Record<string, string>
  sellers: SellerRow[]
  onSellersChanged?: () => void | Promise<void>
  canManageCatalog?: boolean
}

type SortKey = 'name' | 'quantity'
type SortDir = 'asc' | 'desc'
type DistributionAnchor = { productId: string; element: HTMLElement } | null

function rowMatchesSearch(
  row: {
    name: string
    sku_code: string
    wb_vendor_code: string | null
    wb_primary_barcode: string | null
    wb_barcodes: string[]
  },
  query: string,
): boolean {
  const needle = query.trim().toLowerCase()
  if (!needle) return true
  return (
    row.name.toLowerCase().includes(needle) ||
    row.sku_code.toLowerCase().includes(needle) ||
    (row.wb_vendor_code?.toLowerCase().includes(needle) ?? false) ||
    (row.wb_primary_barcode?.toLowerCase().includes(needle) ?? false) ||
    row.wb_barcodes.some((b) => b.toLowerCase().includes(needle))
  )
}

function humanFfCatalogError(message: string): string {
  const normalized = message.trim()
  const lower = normalized.toLowerCase()
  if (
    lower === 'forbidden' ||
    lower.includes('forbidden') ||
    lower === 'seller_not_linked' ||
    normalized.includes('Нет доступа')
  ) {
    return 'Нет доступа к каталогу.'
  }
  if (
    lower === 'not_authenticated' ||
    lower === 'invalid_token' ||
    lower === 'user_not_found'
  ) {
    return 'Войдите заново.'
  }
  if (/^[a-z0-9_:-]+$/.test(normalized)) {
    return 'Не удалось загрузить каталог.'
  }
  return normalized || 'Не удалось загрузить каталог.'
}

export function FfProductsCatalogScreen({
  token,
  authHeaders,
  sellers,
  onSellersChanged,
  canManageCatalog = false,
}: Props) {
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [selectedSellerId, setSelectedSellerId] = useState<string>('__all__')
  const [searchQuery, setSearchQuery] = useState('')
  const [catalog, setCatalog] = useState<FfCatalogRow[]>([])
  const [stock, setStock] = useState<StockSummaryRow[]>([])
  const [sortKey, setSortKey] = useState<SortKey>('name')
  const [sortDir, setSortDir] = useState<SortDir>('asc')
  const [editProduct, setEditProduct] = useState<FfCatalogRow | null>(null)
  const [editText, setEditText] = useState('')
  const [editRequiresHonestSign, setEditRequiresHonestSign] = useState(false)
  const [editBusy, setEditBusy] = useState(false)
  const [createOpen, setCreateOpen] = useState(false)
  const [importOpen, setImportOpen] = useState(false)
  const [sellerCreateOpen, setSellerCreateOpen] = useState(false)
  const [importNotice, setImportNotice] = useState<string | null>(null)
  const [distributionAnchor, setDistributionAnchor] = useState<DistributionAnchor>(null)
  const [selectedProductIds, setSelectedProductIds] = useState<Set<string>>(new Set())
  const [bulkHonestSignBusy, setBulkHonestSignBusy] = useState(false)

  const load = useCallback(async () => {
    setError(null)
    setBusy(true)
    try {
      const sellerFilter = canManageCatalog && selectedSellerId !== '__all__' ? selectedSellerId : null
      const qs = sellerFilter ? `?seller_id=${encodeURIComponent(sellerFilter)}` : ''
      const [catRes, stRes] = await Promise.all([
        fetch(apiUrl(`/products/ff-catalog${qs}`), { headers: { ...authHeaders(token) } }),
        fetch(apiUrl('/operations/inventory-balances/summary'), {
          headers: { ...authHeaders(token) },
        }),
      ])
      if (!catRes.ok) {
        throw new Error(humanFfCatalogError(await readApiErrorMessage(catRes)))
      }
      if (!stRes.ok) {
        throw new Error(humanFfCatalogError(await readApiErrorMessage(stRes)))
      }
      setCatalog((await catRes.json()) as FfCatalogRow[])
      setStock((await stRes.json()) as StockSummaryRow[])
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Не удалось загрузить товары.')
    } finally {
      setBusy(false)
    }
  }, [authHeaders, canManageCatalog, selectedSellerId, token])

  useEffect(() => {
    void load()
  }, [load])

  const rows = useMemo(() => {
    const byProduct = new Map(stock.map((s) => [s.product_id, s]))
    const merged = catalog.map((p) => {
      const bal = byProduct.get(p.id)
      return {
        ...p,
        quantity: bal?.quantity ?? 0,
        quantity_unpacked: bal?.quantity_unpacked ?? 0,
        quantity_packed: bal?.quantity_packed ?? 0,
        quantity_in_sorting: bal?.quantity_in_sorting ?? 0,
        quantity_in_storage: bal?.quantity_in_storage ?? 0,
        reserved: bal?.reserved ?? 0,
        available: bal?.available ?? 0,
        quantity_fbs: bal?.quantity_fbs ?? 0,
        quantity_reserved_directions: bal?.quantity_reserved_directions ?? 0,
        quantity_free_fbo: bal?.quantity_free_fbo ?? (bal?.quantity ?? 0),
      }
    })
    if (!canManageCatalog || selectedSellerId === '__all__') {
      return merged
    }
    return merged.filter((r) => r.seller_id === selectedSellerId)
  }, [canManageCatalog, catalog, selectedSellerId, stock])

  const filteredRows = useMemo(() => {
    return rows.filter((r) => rowMatchesSearch(r, searchQuery))
  }, [rows, searchQuery])

  const sortedRows = useMemo(() => {
    const dir = sortDir === 'asc' ? 1 : -1
    return [...filteredRows].sort((a, b) => {
      if (sortKey === 'quantity') {
        const d = (a.available - b.available) * dir
        if (d !== 0) return d
        return a.name.localeCompare(b.name) * dir
      }
      const d = a.name.localeCompare(b.name) * dir
      if (d !== 0) return d
      return (a.available - b.available) * dir
    })
  }, [filteredRows, sortDir, sortKey])

  const visibleProductIds = useMemo(() => sortedRows.map((row) => row.id), [sortedRows])
  const selectedCount = selectedProductIds.size
  const allVisibleSelected =
    visibleProductIds.length > 0 && visibleProductIds.every((id) => selectedProductIds.has(id))
  const someVisibleSelected = visibleProductIds.some((id) => selectedProductIds.has(id))

  useEffect(() => {
    const visible = new Set(visibleProductIds)
    setSelectedProductIds((current) => {
      const nextIds = [...current].filter((id) => visible.has(id))
      if (nextIds.length === current.size) {
        return current
      }
      return new Set(nextIds)
    })
  }, [visibleProductIds])

  function toggleSort(next: SortKey) {
    if (sortKey !== next) {
      setSortKey(next)
      setSortDir('asc')
      return
    }
    setSortDir((d) => (d === 'asc' ? 'desc' : 'asc'))
  }

  function toggleAllVisibleProducts(checked: boolean) {
    setSelectedProductIds(checked ? new Set(visibleProductIds) : new Set())
  }

  function toggleProductSelected(productId: string, checked: boolean) {
    setSelectedProductIds((current) => {
      const next = new Set(current)
      if (checked) {
        next.add(productId)
      } else {
        next.delete(productId)
      }
      return next
    })
  }

  function openPackagingEdit(p: FfCatalogRow) {
    setEditProduct(p)
    setEditText(p.packaging_instructions ?? '')
    setEditRequiresHonestSign(Boolean(p.requires_honest_sign))
  }

  function printPackagingTz() {
    if (!editProduct) return
    printPackagingInstructions({
      sku_code: editProduct.sku_code,
      product_name: editProduct.name,
      seller_name: editProduct.seller_name,
      instructions: editText,
      requires_honest_sign: editRequiresHonestSign,
    })
  }

  const distributionProduct = distributionAnchor
    ? sortedRows.find((p) => p.id === distributionAnchor.productId) ?? null
    : null

  async function savePackagingInstructions() {
    if (!editProduct) return
    setEditBusy(true)
    setError(null)
    try {
      const res = await fetch(apiUrl(`/products/${editProduct.id}/packaging-instructions`), {
        method: 'PATCH',
        headers: { ...authHeaders(token), 'Content-Type': 'application/json' },
        body: JSON.stringify({
          packaging_instructions: editText.trim() || null,
          requires_honest_sign: editRequiresHonestSign,
        }),
      })
      if (!res.ok) {
        setError(humanFfCatalogError(await readApiErrorMessage(res)))
        return
      }
      setEditProduct(null)
      await load()
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Не удалось сохранить ТЗ.')
    } finally {
      setEditBusy(false)
    }
  }

  async function applyHonestSignToSelected() {
    const productIds = [...selectedProductIds]
    if (productIds.length === 0) return
    const selectedIds = new Set(productIds)
    setBulkHonestSignBusy(true)
    setError(null)
    try {
      const res = await fetch(apiUrl('/products/requires-honest-sign/bulk'), {
        method: 'PATCH',
        headers: { ...authHeaders(token), 'Content-Type': 'application/json' },
        body: JSON.stringify({
          product_ids: productIds,
          requires_honest_sign: true,
        }),
      })
      if (!res.ok) {
        setError(humanFfCatalogError(await readApiErrorMessage(res)))
        return
      }
      const body = (await res.json()) as { updated_count: number }
      setCatalog((current) =>
        current.map((row) =>
          selectedIds.has(row.id) ? { ...row, requires_honest_sign: true } : row,
        ),
      )
      setSelectedProductIds(new Set())
      setImportNotice(`Честный знак включён: ${body.updated_count} товаров.`)
      await load()
    } catch (e) {
      setError(
        e instanceof Error ? e.message : 'Не удалось включить Честный знак выбранным товарам.',
      )
    } finally {
      setBulkHonestSignBusy(false)
    }
  }

  return (
    <FfProductMarkingPrintProvider token={token}>
    <Box
      sx={{
        minWidth: 0,
        width: '100%',
        maxWidth: 'calc(100vw - 308px)',
        boxSizing: 'border-box',
        overflowX: 'hidden',
      }}
    >
      <Typography variant="h5" gutterBottom>
        Каталог
      </Typography>
      <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
        Все товары селлеров и остатки на складе ФФ.
      </Typography>

      {error ? (
        <Alert severity="error" sx={{ mb: 2 }} data-testid="ff-products-error">
          {error}
        </Alert>
      ) : null}
      {importNotice ? (
        <Alert
          severity="success"
          sx={{ mb: 2 }}
          data-testid="ff-products-import-notice"
          onClose={() => setImportNotice(null)}
        >
          {importNotice}
        </Alert>
      ) : null}

      <Paper
        variant="outlined"
        sx={{ p: 2, mb: 2, maxWidth: '100%', overflowX: 'hidden' }}
        data-testid="ff-products-filters"
      >
        <Stack spacing={2}>
          {canManageCatalog ? (
            <Stack
              direction={{ xs: 'column', sm: 'row' }}
              spacing={1}
              sx={{ justifyContent: 'flex-end' }}
            >
              {selectedCount > 0 ? (
                <Chip
                  size="small"
                  variant="outlined"
                  color="primary"
                  label={`Выбрано: ${selectedCount}`}
                  data-testid="ff-products-selected-count"
                />
              ) : null}
              <Button
                variant="outlined"
                color="success"
                disabled={bulkHonestSignBusy || busy || selectedCount === 0}
                onClick={() => void applyHonestSignToSelected()}
                data-testid="ff-products-bulk-honest-sign"
              >
                Нужен ЧЗ выбранным
              </Button>
              <Button
                variant="outlined"
                onClick={() => setSellerCreateOpen(true)}
                data-testid="ff-products-create-seller"
              >
                Создать селлера
              </Button>
              <Button
                variant="outlined"
                onClick={() => setImportOpen(true)}
                data-testid="ff-products-import-tz"
              >
                Загрузить Excel
              </Button>
              <Button
                variant="contained"
                onClick={() => setCreateOpen(true)}
                data-testid="ff-products-create"
              >
                Создать товар
              </Button>
            </Stack>
          ) : null}
          <TextField
            fullWidth
            size="small"
            label="Поиск"
            placeholder="Артикул или название"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            slotProps={{ htmlInput: { 'data-testid': 'ff-products-search' } }}
          />
          <Stack direction={{ xs: 'column', sm: 'row' }} spacing={2} sx={{ alignItems: { sm: 'center' } }}>
            {canManageCatalog ? (
              <FormControl size="small" sx={{ minWidth: 260 }}>
                <InputLabel id="ff-products-seller-label">Селлер</InputLabel>
                <Select
                  labelId="ff-products-seller-label"
                  label="Селлер"
                  value={selectedSellerId}
                  onChange={(e) => setSelectedSellerId(String(e.target.value))}
                  data-testid="ff-products-seller-filter"
                >
                  <MenuItem value="__all__">Все</MenuItem>
                  {sellers.map((s) => (
                    <MenuItem key={s.id} value={s.id}>
                      {s.name}
                    </MenuItem>
                  ))}
                </Select>
              </FormControl>
            ) : null}
            {busy ? <CircularProgress size={18} data-testid="ff-products-loading" /> : null}
          </Stack>
        </Stack>
      </Paper>

      <TableContainer
        component={Paper}
        variant="outlined"
        sx={{ width: '100%', maxWidth: '100%', minWidth: 0, overflowX: 'hidden' }}
        data-testid="ff-products-list"
      >
        <Table
          stickyHeader
          size="small"
          data-testid="ff-products-table"
          sx={{
            width: '100%',
            tableLayout: 'fixed',
            '& .MuiTableCell-root': {
              px: 1,
              py: 1,
              overflow: 'hidden',
              verticalAlign: 'middle',
            },
            '& .MuiTableCell-head': {
              fontWeight: 600,
              lineHeight: 1.2,
              whiteSpace: 'normal',
            },
          }}
        >
          <colgroup>
            {canManageCatalog ? <col style={{ width: '4%' }} /> : null}
            <col style={{ width: '6%' }} />
            <col style={{ width: canManageCatalog ? '14%' : '15%' }} />
            <col style={{ width: '8%' }} />
            <col style={{ width: canManageCatalog ? '22%' : '24%' }} />
            <col style={{ width: canManageCatalog ? '13%' : '14%' }} />
            <col style={{ width: '9%' }} />
            <col style={{ width: '8%' }} />
            <col style={{ width: '12%' }} />
            <col style={{ width: '4%' }} />
          </colgroup>
          <TableHead>
            <TableRow>
              {canManageCatalog ? (
                <TableCell padding="checkbox" width={52}>
                  <Checkbox
                    size="small"
                    checked={allVisibleSelected}
                    indeterminate={someVisibleSelected && !allVisibleSelected}
                    disabled={busy || sortedRows.length === 0}
                    onChange={(e) => toggleAllVisibleProducts(e.target.checked)}
                    slotProps={{ input: { 'aria-label': 'Выбрать все товары' } }}
                    data-testid="ff-products-select-all"
                  />
                </TableCell>
              ) : null}
              <TableCell>Фото</TableCell>
              <TableCell>SKU / ШК</TableCell>
              <TableCell>Артикул WB</TableCell>
              <TableCell>
                <TableSortLabel
                  active={sortKey === 'name'}
                  direction={sortKey === 'name' ? sortDir : 'asc'}
                  onClick={() => toggleSort('name')}
                  data-testid="ff-products-sort-name"
                >
                  Название
                </TableSortLabel>
              </TableCell>
              <TableCell>Селлер</TableCell>
              <TableCell>ТЗ / ЧЗ</TableCell>
              <TableCell align="right">
                <TableSortLabel
                  active={sortKey === 'quantity'}
                  direction={sortKey === 'quantity' ? sortDir : 'asc'}
                  onClick={() => toggleSort('quantity')}
                  data-testid="ff-products-sort-quantity"
                >
                  Доступно
                </TableSortLabel>
              </TableCell>
              <TableCell>Распределение</TableCell>
              <TableCell align="center" />
            </TableRow>
          </TableHead>
          <TableBody>
            {sortedRows.map((p) => {
              const displayMeta = catalogRowToDisplayMeta(p)
              const barcode = resolveProductPrimaryBarcode(displayMeta)
              return (
              <TableRow key={p.id} hover data-testid="ff-product-row">
                {canManageCatalog ? (
                  <TableCell padding="checkbox">
                    <Checkbox
                      size="small"
                      checked={selectedProductIds.has(p.id)}
                      onChange={(e) => toggleProductSelected(p.id, e.target.checked)}
                      slotProps={{ input: { 'aria-label': `Выбрать товар ${p.sku_code}` } }}
                      data-testid={`ff-product-select-${p.id}`}
                    />
                  </TableCell>
                ) : null}
                <TableCell>
                  <ProductPhotoThumb src={p.wb_primary_image_url} />
                </TableCell>
                <TableCell>
                  <Stack spacing={0.5} sx={{ minWidth: 0 }}>
                    <Typography variant="body2" sx={{ fontWeight: 600 }} noWrap>
                      {p.sku_code}
                    </Typography>
                    <Box
                      sx={{
                        minWidth: 0,
                        maxWidth: '100%',
                        '& [data-testid^="ff-catalog-barcode-"]': { maxWidth: '100%' },
                      }}
                    >
                      <ProductBarcodeCell
                        barcode={barcode || null}
                        wb_size={p.wb_size}
                        wb_composition={p.wb_composition}
                        testId={`ff-catalog-barcode-${p.id}`}
                      />
                    </Box>
                  </Stack>
                </TableCell>
                <TableCell>
                  <Typography variant="body2" noWrap>
                    {p.wb_nm_id ?? '—'}
                  </Typography>
                </TableCell>
                <TableCell>
                  <Stack spacing={0.25} sx={{ minWidth: 0 }}>
                    <Stack direction="row" spacing={0.5} sx={{ alignItems: 'center', minWidth: 0 }}>
                      <Typography
                        component="span"
                        variant="body2"
                        sx={{
                          minWidth: 0,
                          display: '-webkit-box',
                          WebkitLineClamp: 2,
                          WebkitBoxOrient: 'vertical',
                          overflow: 'hidden',
                        }}
                      >
                        {p.name}
                      </Typography>
                      {p.is_manual ? (
                        <Chip
                          size="small"
                          label="Вручную"
                          variant="outlined"
                          data-testid={`ff-product-manual-${p.id}`}
                        />
                      ) : null}
                    </Stack>
                    {p.wb_vendor_code ? (
                      <Typography variant="caption" color="text.secondary" noWrap>
                        Артикул продавца: {p.wb_vendor_code}
                      </Typography>
                    ) : null}
                    {p.wb_size ? (
                      <Typography variant="caption" color="text.secondary" noWrap>
                        Размер: {p.wb_size}
                      </Typography>
                    ) : null}
                  </Stack>
                </TableCell>
                <TableCell>
                  <Typography variant="body2" noWrap>
                    {p.seller_name ?? '—'}
                  </Typography>
                </TableCell>
                <TableCell>
                  <Stack spacing={0.5} sx={{ minWidth: 0, alignItems: 'flex-start' }}>
                    <Typography
                      variant="body2"
                      color={p.has_packaging_instructions ? 'text.primary' : 'text.secondary'}
                      data-testid={`ff-packaging-status-${p.id}`}
                      noWrap
                    >
                      {p.has_packaging_instructions ? 'Заполнено' : 'Нет ТЗ'}
                    </Typography>
                    {p.requires_honest_sign ? (
                      <Chip
                        size="small"
                        label="ЧЗ"
                        color="info"
                        variant="outlined"
                        data-testid={`ff-honest-sign-status-${p.id}`}
                      />
                    ) : null}
                    {canManageCatalog ? (
                      <Button
                        size="small"
                        onClick={() => openPackagingEdit(p)}
                        data-testid={`ff-packaging-edit-${p.id}`}
                        sx={{ maxWidth: '100%', minWidth: 0, px: 0 }}
                      >
                        ТЗ
                      </Button>
                    ) : null}
                  </Stack>
                </TableCell>
                <TableCell align="right">
                  <Typography variant="body2" sx={{ fontWeight: 700 }}>
                    {p.available} шт
                  </Typography>
                </TableCell>
                <TableCell>
                  <Stack direction="row" spacing={0.5} sx={{ alignItems: 'center', minWidth: 0 }}>
                    <Box sx={{ minWidth: 0, flex: 1 }}>
                      <Typography variant="body2" noWrap>
                        FBS {p.quantity_fbs} · Резервы {p.quantity_reserved_directions}
                      </Typography>
                      <Typography variant="caption" color="text.secondary" noWrap>
                        FBO {p.quantity_free_fbo}
                      </Typography>
                    </Box>
                    <Tooltip title="Показать распределение остатка" arrow>
                      <IconButton
                        size="small"
                        onClick={(event) =>
                          setDistributionAnchor({ productId: p.id, element: event.currentTarget })
                        }
                        data-testid={`ff-product-distribution-${p.id}`}
                        aria-label={`Распределение остатка ${p.sku_code}`}
                      >
                        <Inventory2OutlinedIcon fontSize="small" />
                      </IconButton>
                    </Tooltip>
                  </Stack>
                </TableCell>
                <TableCell align="center">
                  <ProductBarcodePrintButton
                    meta={displayMeta}
                    testId={`ff-catalog-print-${p.id}`}
                    productId={p.id}
                    requiresHonestSign={p.requires_honest_sign}
                  />
                </TableCell>
              </TableRow>
            )})}
            {sortedRows.length === 0 && !busy ? (
              <TableRow>
                <TableCell colSpan={canManageCatalog ? 10 : 9}>
                  {searchQuery.trim() ? (
                    <Typography variant="body2" color="text.secondary" data-testid="ff-products-search-empty">
                      Ничего не найдено по запросу «{searchQuery.trim()}».
                    </Typography>
                  ) : (
                    <>
                      <Typography variant="body2" color="text.secondary">
                        Пока нет товаров.
                      </Typography>
                      <Typography variant="body2" color="text.secondary" sx={{ mt: 0.5 }}>
                        Остаток появится после приемки товара на склад.
                      </Typography>
                    </>
                  )}
                </TableCell>
              </TableRow>
            ) : null}
          </TableBody>
        </Table>
      </TableContainer>

      <Popover
        open={Boolean(distributionAnchor)}
        anchorEl={distributionAnchor?.element ?? null}
        onClose={() => setDistributionAnchor(null)}
        anchorOrigin={{ vertical: 'bottom', horizontal: 'right' }}
        transformOrigin={{ vertical: 'top', horizontal: 'right' }}
        marginThreshold={16}
        slotProps={{
          paper: {
            sx: {
              p: 2,
              width: 320,
              maxWidth: 'calc(100vw - 32px)',
              boxSizing: 'border-box',
              overflowX: 'hidden',
            },
          },
        }}
      >
        {distributionProduct ? (
          <Stack spacing={1.25} data-testid="ff-products-distribution-popover">
            <Box>
              <Typography variant="subtitle2">{distributionProduct.sku_code}</Typography>
              <Typography variant="body2" color="text.secondary" noWrap>
                {distributionProduct.name}
              </Typography>
            </Box>
            <Divider />
            <Stack spacing={0.75}>
              <DistributionLine
                label="FBS"
                value={distributionProduct.quantity_fbs}
                testId={`ff-product-fbs-${distributionProduct.id}`}
              />
              <DistributionLine
                label="Резервы/наборы"
                value={distributionProduct.quantity_reserved_directions}
                testId={`ff-product-reserve-directions-${distributionProduct.id}`}
              />
              <DistributionLine
                label="Свободно для FBO"
                value={distributionProduct.quantity_free_fbo}
                testId={`ff-product-free-fbo-${distributionProduct.id}`}
                strong
              />
            </Stack>
          </Stack>
        ) : null}
      </Popover>

      {canManageCatalog ? (
        <>
          <FfManualProductCreateDialog
            open={createOpen}
            token={token}
            authHeaders={authHeaders}
            sellers={sellers}
            defaultSellerId={selectedSellerId !== '__all__' ? selectedSellerId : null}
            onClose={() => setCreateOpen(false)}
            onCreated={async () => {
              setImportNotice('Товар создан.')
              await load()
            }}
          />
          <FfProductTzImportDialog
            open={importOpen}
            token={token}
            sellers={sellers}
            defaultSellerId={selectedSellerId !== '__all__' ? selectedSellerId : null}
            onClose={() => setImportOpen(false)}
            onApplied={async (message) => {
              setImportNotice(message)
              await load()
            }}
          />
          <FfSellerCreateDialog
            open={sellerCreateOpen}
            token={token}
            authHeaders={authHeaders}
            onClose={() => setSellerCreateOpen(false)}
            onCreated={async (created) => {
              await onSellersChanged?.()
              setSelectedSellerId(created.id)
              setImportNotice(`Селлер «${created.name}» создан и доступен для создания товаров.`)
            }}
          />
        </>
      ) : null}

      <Dialog
        open={editProduct !== null}
        onClose={() => setEditProduct(null)}
        fullWidth
        maxWidth="sm"
        data-testid="ff-packaging-dialog"
      >
        <DialogTitle>ТЗ на упаковку</DialogTitle>
        <DialogContent>
          <Typography variant="body2" color="text.secondary" sx={{ mb: 1 }}>
            {editProduct?.sku_code} · {editProduct?.name}
          </Typography>
          <FormControlLabel
            control={
              <Checkbox
                checked={editRequiresHonestSign}
                onChange={(e) => setEditRequiresHonestSign(e.target.checked)}
                data-testid="ff-requires-honest-sign"
              />
            }
            label="Нужен Честный знак при упаковке"
          />
          <TextField
            fullWidth
            multiline
            minRows={4}
            label="Инструкция для склада"
            value={editText}
            onChange={(e) => setEditText(e.target.value)}
            slotProps={{ htmlInput: { 'data-testid': 'ff-packaging-text' } }}
          />
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setEditProduct(null)} disabled={editBusy}>
            Отмена
          </Button>
          <Button
            variant="outlined"
            disabled={editBusy || !editProduct}
            onClick={printPackagingTz}
            data-testid="ff-packaging-print"
          >
            Печать
          </Button>
          <Button
            variant="contained"
            disabled={editBusy}
            onClick={() => void savePackagingInstructions()}
            data-testid="ff-packaging-save"
          >
            Сохранить
          </Button>
        </DialogActions>
      </Dialog>
    </Box>
    </FfProductMarkingPrintProvider>
  )
}

function DistributionLine({
  label,
  value,
  strong = false,
  testId,
}: {
  label: string
  value: number
  strong?: boolean
  testId?: string
}) {
  return (
    <Stack direction="row" sx={{ justifyContent: 'space-between', gap: 2 }}>
      <Typography variant="body2" color={strong ? 'text.primary' : 'text.secondary'}>
        {label}
      </Typography>
      <Typography variant="body2" sx={{ fontWeight: strong ? 700 : 500 }} data-testid={testId}>
        {value} шт
      </Typography>
    </Stack>
  )
}
