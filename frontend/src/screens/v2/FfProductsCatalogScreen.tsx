import { useEffect, useMemo, useState } from 'react'
import {
  Alert,
  Box,
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
  TableRow,
  TableSortLabel,
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
}

type StockSummaryRow = {
  product_id: string
  sku_code: string
  product_name: string
  quantity: number
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

  useEffect(() => {
    let cancelled = false
    async function load() {
      setError(null)
      setBusy(true)
      try {
        const sellerFilter = selectedSellerId !== '__all__' ? selectedSellerId : null
        const qs = sellerFilter ? `?seller_id=${encodeURIComponent(sellerFilter)}` : ''
        const [catRes, stRes] = await Promise.all([
          fetch(apiUrl(`/products/ff-catalog${qs}`), { headers: { ...authHeaders(token) } }),
          fetch(apiUrl('/operations/inventory-balances/summary'), { headers: { ...authHeaders(token) } }),
        ])
        if (!catRes.ok) {
          throw new Error(await readApiErrorMessage(catRes))
        }
        if (!stRes.ok) {
          throw new Error(await readApiErrorMessage(stRes))
        }
        const cat = (await catRes.json()) as FfCatalogRow[]
        const st = (await stRes.json()) as StockSummaryRow[]
        if (cancelled) return
        setCatalog(cat)
        setStock(st)
      } catch (e) {
        if (!cancelled) {
          setError(e instanceof Error ? e.message : 'Не удалось загрузить товары.')
        }
      } finally {
        if (!cancelled) {
          setBusy(false)
        }
      }
    }
    void load()
    return () => {
      cancelled = true
    }
  }, [authHeaders, selectedSellerId, token])

  const rows = useMemo(() => {
    const byProduct = new Map(stock.map((s) => [s.product_id, s]))
    const merged = catalog.map((p) => ({
      ...p,
      quantity: byProduct.get(p.id)?.quantity ?? 0,
    }))
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
              <TableCell align="right" width={160}>
                <TableSortLabel
                  active={sortKey === 'quantity'}
                  direction={sortKey === 'quantity' ? sortDir : 'asc'}
                  onClick={() => toggleSort('quantity')}
                  data-testid="ff-products-sort-quantity"
                >
                  Остаток (итого)
                </TableSortLabel>
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
                <TableCell align="right">{p.quantity}</TableCell>
              </TableRow>
            ))}
            {sortedRows.length === 0 && !busy ? (
              <TableRow>
                <TableCell colSpan={8}>
                  <Typography variant="body2" color="text.secondary">
                    Пока нет товаров.
                  </Typography>
                </TableCell>
              </TableRow>
            ) : null}
          </TableBody>
        </Table>
      </TableContainer>
    </Box>
  )
}

