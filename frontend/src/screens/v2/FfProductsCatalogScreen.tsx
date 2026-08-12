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
import InfoOutlinedIcon from '@mui/icons-material/InfoOutlined'
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
}

type Props = {
  token: string
  authHeaders: (t: string) => Record<string, string>
  sellers: SellerRow[]
  onSellersChanged?: () => void | Promise<void>
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

export function FfProductsCatalogScreen({ token, authHeaders, sellers, onSellersChanged }: Props) {
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

  const load = useCallback(async () => {
    setError(null)
    setBusy(true)
    try {
      const sellerFilter = selectedSellerId !== '__all__' ? selectedSellerId : null
      const qs = sellerFilter ? `?seller_id=${encodeURIComponent(sellerFilter)}` : ''
      const [catRes, stRes] = await Promise.all([
        fetch(apiUrl(`/products/ff-catalog${qs}`), { headers: { ...authHeaders(token) } }),
        fetch(apiUrl('/operations/inventory-balances/summary'), {
          headers: { ...authHeaders(token) },
        }),
      ])
      if (!catRes.ok) {
        throw new Error(await readApiErrorMessage(catRes))
      }
      if (!stRes.ok) {
        throw new Error(await readApiErrorMessage(stRes))
      }
      setCatalog((await catRes.json()) as FfCatalogRow[])
      setStock((await stRes.json()) as StockSummaryRow[])
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Не удалось загрузить товары.')
    } finally {
      setBusy(false)
    }
  }, [authHeaders, selectedSellerId, token])

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
      }
    })
    if (selectedSellerId === '__all__') {
      return merged
    }
    return merged.filter((r) => r.seller_id === selectedSellerId)
  }, [catalog, selectedSellerId, stock])

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

  function toggleSort(next: SortKey) {
    if (sortKey !== next) {
      setSortKey(next)
      setSortDir('asc')
      return
    }
    setSortDir((d) => (d === 'asc' ? 'desc' : 'asc'))
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
        setError(await readApiErrorMessage(res))
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

  return (
    <FfProductMarkingPrintProvider token={token}>
    <Box>
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

      <Paper variant="outlined" sx={{ p: 2, mb: 2 }} data-testid="ff-products-filters">
        <Stack spacing={2}>
          <Stack
            direction={{ xs: 'column', sm: 'row' }}
            spacing={1}
            sx={{ justifyContent: 'flex-end' }}
          >
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
          {busy ? <CircularProgress size={18} data-testid="ff-products-loading" /> : null}
          </Stack>
        </Stack>
      </Paper>

      <TableContainer component={Paper} variant="outlined" data-testid="ff-products-list">
        <Table stickyHeader size="small" data-testid="ff-products-table">
          <TableHead>
            <TableRow>
              <TableCell width={68}>Фото</TableCell>
              <TableCell width={230}>SKU / ШК</TableCell>
              <TableCell width={120}>Артикул WB</TableCell>
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
              <TableCell width={220}>Селлер</TableCell>
              <TableCell width={130}>ТЗ / ЧЗ</TableCell>
              <TableCell align="right" width={130}>
                <TableSortLabel
                  active={sortKey === 'quantity'}
                  direction={sortKey === 'quantity' ? sortDir : 'asc'}
                  onClick={() => toggleSort('quantity')}
                  data-testid="ff-products-sort-quantity"
                >
                  Доступно
                </TableSortLabel>
                <Tooltip
                  arrow
                  title="Доступно для FBO = товар в ячейках минус резервы. Товар в сортировке ещё не свободный остаток."
                >
                  <InfoOutlinedIcon
                    sx={{ ml: 0.5, fontSize: 15, verticalAlign: 'text-bottom', color: 'text.secondary' }}
                    data-testid="ff-products-available-formula"
                  />
                </Tooltip>
              </TableCell>
              <TableCell width={190}>Распределение</TableCell>
              <TableCell align="center" width={56} />
            </TableRow>
          </TableHead>
          <TableBody>
            {sortedRows.map((p) => {
              const displayMeta = catalogRowToDisplayMeta(p)
              const barcode = resolveProductPrimaryBarcode(displayMeta)
              return (
              <TableRow key={p.id} hover data-testid="ff-product-row">
                <TableCell>
                  <ProductPhotoThumb src={p.wb_primary_image_url} />
                </TableCell>
                <TableCell>
                  <Stack spacing={0.5}>
                    <Typography variant="body2" sx={{ fontWeight: 600 }}>
                      {p.sku_code}
                    </Typography>
                    <ProductBarcodeCell
                      barcode={barcode || null}
                      wb_size={p.wb_size}
                      wb_composition={p.wb_composition}
                      testId={`ff-catalog-barcode-${p.id}`}
                    />
                  </Stack>
                </TableCell>
                <TableCell>{p.wb_nm_id ?? '—'}</TableCell>
                <TableCell>
                  <Stack spacing={0.25}>
                    <Stack direction="row" spacing={0.5} sx={{ alignItems: 'center', flexWrap: 'wrap' }}>
                      <span>{p.name}</span>
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
                      <Typography variant="caption" color="text.secondary">
                        Артикул продавца: {p.wb_vendor_code}
                      </Typography>
                    ) : null}
                    {p.wb_size ? (
                      <Typography variant="caption" color="text.secondary">
                        Размер: {p.wb_size}
                      </Typography>
                    ) : null}
                  </Stack>
                </TableCell>
                <TableCell>{p.seller_name ?? '—'}</TableCell>
                <TableCell>
                  <Stack spacing={0.5}>
                    <Typography
                      variant="body2"
                      color={p.has_packaging_instructions ? 'text.primary' : 'text.secondary'}
                      data-testid={`ff-packaging-status-${p.id}`}
                    >
                      {p.has_packaging_instructions ? 'Заполнено' : 'Нет ТЗ'}
                    </Typography>
                    {p.requires_honest_sign ? (
                      <Typography variant="caption" color="text.secondary">
                        ЧЗ нужен
                      </Typography>
                    ) : null}
                    <Button
                      size="small"
                      onClick={() => openPackagingEdit(p)}
                      data-testid={`ff-packaging-edit-${p.id}`}
                      sx={{ alignSelf: 'flex-start', minWidth: 0, px: 0 }}
                    >
                      ТЗ
                    </Button>
                  </Stack>
                </TableCell>
                <TableCell align="right">
                  <Stack spacing={0.25} sx={{ alignItems: 'flex-end' }}>
                    <Typography variant="body2" sx={{ fontWeight: 700 }}>
                      {p.available} шт
                    </Typography>
                    {p.reserved > 0 ? (
                      <Typography variant="caption" color="text.secondary">
                        резерв {p.reserved}
                      </Typography>
                    ) : null}
                  </Stack>
                </TableCell>
                <TableCell>
                  <Stack direction="row" spacing={0.5} sx={{ alignItems: 'center' }}>
                    <Box sx={{ minWidth: 0 }}>
                      <Typography variant="body2" noWrap>
                        Ячейки {p.quantity_in_storage} · Сортировка{' '}
                        <span data-testid="ff-product-qty-sorting">{p.quantity_in_sorting}</span>
                      </Typography>
                      <Typography variant="caption" color="text.secondary" noWrap>
                        Свободно для FBO {p.available}
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
                <TableCell colSpan={9}>
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
                        Остаток появляется после завершения пересчёта на приёмке (зона «Сортировка»).
                        После раскладки по ячейкам товар доступен к резерву.
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
        slotProps={{ paper: { sx: { p: 2, width: 320 }, 'data-testid': 'ff-products-distribution-popover' } }}
      >
        {distributionProduct ? (
          <Stack spacing={1.25}>
            <Box>
              <Typography variant="subtitle2">{distributionProduct.sku_code}</Typography>
              <Typography variant="body2" color="text.secondary" noWrap>
                {distributionProduct.name}
              </Typography>
            </Box>
            <Divider />
            <Stack spacing={0.75}>
              <DistributionLine
                label="Не упаковано"
                value={distributionProduct.quantity_unpacked}
                testId={`ff-product-unpacked-${distributionProduct.id}`}
              />
              <DistributionLine
                label="Упаковано"
                value={distributionProduct.quantity_packed}
                testId={`ff-product-packed-${distributionProduct.id}`}
              />
              <DistributionLine label="Сортировка" value={distributionProduct.quantity_in_sorting} />
              <DistributionLine label="В ячейках" value={distributionProduct.quantity_in_storage} />
              <DistributionLine label="Резервы" value={distributionProduct.reserved} />
              <DistributionLine label="Свободно для FBO" value={distributionProduct.available} strong />
            </Stack>
            <Typography variant="caption" color="text.secondary">
              Доступно для FBO = в ячейках − резервы. Данных по FBS-направлениям в ответе каталога
              сейчас нет, поэтому разбивка по направлениям здесь не показывается.
            </Typography>
          </Stack>
        ) : null}
      </Popover>

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
