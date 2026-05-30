import { useCallback, useEffect, useMemo, useState } from 'react'
import {
  Alert,
  Box,
  Button,
  Chip,
  CircularProgress,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
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
  TableRow,
  TableSortLabel,
  TextField,
  Typography,
} from '@mui/material'
import { apiUrl } from '../../api'
import { ProductPhotoThumb } from '../../components/ProductPhotoThumb'
import { readApiErrorMessage } from '../../utils/readApiErrorMessage'

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
  packaging_instructions: string | null
  has_packaging_instructions: boolean
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
}

type SortKey = 'name' | 'quantity'
type SortDir = 'asc' | 'desc'

export function FfProductsCatalogScreen({ token, authHeaders, sellers }: Props) {
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [selectedSellerId, setSelectedSellerId] = useState<string>('__all__')
  const [catalog, setCatalog] = useState<FfCatalogRow[]>([])
  const [stock, setStock] = useState<StockSummaryRow[]>([])
  const [sortKey, setSortKey] = useState<SortKey>('name')
  const [sortDir, setSortDir] = useState<SortDir>('asc')
  const [editProduct, setEditProduct] = useState<FfCatalogRow | null>(null)
  const [editText, setEditText] = useState('')
  const [editBusy, setEditBusy] = useState(false)

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

  const sortedRows = useMemo(() => {
    const dir = sortDir === 'asc' ? 1 : -1
    return [...rows].sort((a, b) => {
      if (sortKey === 'quantity') {
        const d = (a.quantity - b.quantity) * dir
        if (d !== 0) return d
        return a.name.localeCompare(b.name) * dir
      }
      const d = a.name.localeCompare(b.name) * dir
      if (d !== 0) return d
      return (a.quantity - b.quantity) * dir
    })
  }, [rows, sortDir, sortKey])

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
  }

  async function savePackagingInstructions() {
    if (!editProduct) return
    setEditBusy(true)
    setError(null)
    try {
      const res = await fetch(apiUrl(`/products/${editProduct.id}/packaging-instructions`), {
        method: 'PATCH',
        headers: { ...authHeaders(token), 'Content-Type': 'application/json' },
        body: JSON.stringify({ packaging_instructions: editText.trim() || null }),
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
    <Box>
      <Typography variant="h5" gutterBottom>
        Товары
      </Typography>
      <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
        Складской каталог ФФ: товары всех селлеров, по которым уже были движения на складе.
      </Typography>

      {error ? (
        <Alert severity="error" sx={{ mb: 2 }} data-testid="ff-products-error">
          {error}
        </Alert>
      ) : null}

      <Paper variant="outlined" sx={{ p: 2, mb: 2 }} data-testid="ff-products-filters">
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
      </Paper>

      <TableContainer component={Paper} variant="outlined" data-testid="ff-products-list">
        <Table stickyHeader size="small" data-testid="ff-products-table">
          <TableHead>
            <TableRow>
              <TableCell width={68}>Фото</TableCell>
              <TableCell width={140}>SKU</TableCell>
              <TableCell width={190}>ШК</TableCell>
              <TableCell width={160}>Артикул продавца</TableCell>
              <TableCell width={110}>WB nm</TableCell>
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
              <TableCell width={120}>ТЗ упаковки</TableCell>
              <TableCell align="right" width={100}>
                <TableSortLabel
                  active={sortKey === 'quantity'}
                  direction={sortKey === 'quantity' ? sortDir : 'asc'}
                  onClick={() => toggleSort('quantity')}
                  data-testid="ff-products-sort-quantity"
                >
                  На складе
                </TableSortLabel>
              </TableCell>
              <TableCell align="right" width={100} data-testid="ff-products-col-unpacked">
                Не упак.
              </TableCell>
              <TableCell align="right" width={100} data-testid="ff-products-col-packed">
                Упаковано
              </TableCell>
              <TableCell align="right" width={120} data-testid="ff-products-col-sorting">
                В сортировке
              </TableCell>
              <TableCell align="right" width={120}>
                В ячейках
              </TableCell>
              <TableCell align="right" width={110}>
                Доступно
              </TableCell>
            </TableRow>
          </TableHead>
          <TableBody>
            {sortedRows.map((p) => (
              <TableRow key={p.id} hover data-testid="ff-product-row">
                <TableCell>
                  <ProductPhotoThumb src={p.wb_primary_image_url} />
                </TableCell>
                <TableCell>{p.sku_code}</TableCell>
                <TableCell>{p.wb_primary_barcode ?? (p.wb_barcodes[0] ?? '—')}</TableCell>
                <TableCell>{p.wb_vendor_code ?? '—'}</TableCell>
                <TableCell>{p.wb_nm_id ?? '—'}</TableCell>
                <TableCell>{p.name}</TableCell>
                <TableCell>{p.seller_name ?? '—'}</TableCell>
                <TableCell>
                  <Stack direction="row" spacing={0.5} sx={{ alignItems: 'center' }}>
                    <Chip
                      size="small"
                      label={p.has_packaging_instructions ? 'Заполнено' : 'Нет ТЗ'}
                      color={p.has_packaging_instructions ? 'success' : 'warning'}
                      data-testid={`ff-packaging-status-${p.id}`}
                    />
                    <Button
                      size="small"
                      onClick={() => openPackagingEdit(p)}
                      data-testid={`ff-packaging-edit-${p.id}`}
                    >
                      ТЗ
                    </Button>
                  </Stack>
                </TableCell>
                <TableCell align="right">{p.quantity}</TableCell>
                <TableCell align="right" data-testid={`ff-product-unpacked-${p.id}`}>
                  {p.quantity_unpacked}
                </TableCell>
                <TableCell align="right" data-testid={`ff-product-packed-${p.id}`}>
                  {p.quantity_packed}
                </TableCell>
                <TableCell align="right" data-testid="ff-product-qty-sorting">
                  {p.quantity_in_sorting}
                </TableCell>
                <TableCell align="right">{p.quantity_in_storage}</TableCell>
                <TableCell align="right">{p.available}</TableCell>
              </TableRow>
            ))}
            {sortedRows.length === 0 && !busy ? (
              <TableRow>
                <TableCell colSpan={14}>
                  <Typography variant="body2" color="text.secondary">
                    Пока нет товаров.
                  </Typography>
                  <Typography variant="body2" color="text.secondary" sx={{ mt: 0.5 }}>
                    Остаток появляется после завершения пересчёта на приёмке (зона «Сортировка»).
                    После разкладки по ячейкам товар доступен к резерву.
                  </Typography>
                </TableCell>
              </TableRow>
            ) : null}
          </TableBody>
        </Table>
      </TableContainer>

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
  )
}
