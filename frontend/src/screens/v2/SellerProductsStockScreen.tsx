import { useEffect, useMemo, useState } from 'react'
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
  Paper,
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

type WbCatalogRow = {
  id: string
  sku_code: string
  name: string
  wb_vendor_code: string | null
  wb_nm_id: number | null
  wb_primary_image_url: string | null
  wb_barcodes: string[]
  wb_primary_barcode: string | null
  wb_size: string | null
  packaging_instructions: string | null
  has_packaging_instructions: boolean
}

type StockSummaryRow = {
  product_id: string
  sku_code: string
  product_name: string
  quantity: number
  quantity_in_sorting: number
  quantity_in_storage: number
  reserved: number
  available: number
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
  const [catalog, setCatalog] = useState<WbCatalogRow[]>([])
  const [stock, setStock] = useState<StockSummaryRow[]>([])
  const [page, setPage] = useState(0)
  const [rowsPerPage, setRowsPerPage] = useState(10)
  const [editProduct, setEditProduct] = useState<WbCatalogRow | null>(null)
  const [editText, setEditText] = useState('')
  const [editBusy, setEditBusy] = useState(false)

  async function refreshAll() {
    setError(null)
    setBusy(true)
    try {
      const [catRes, stRes] = await Promise.all([
        fetch(apiUrl('/products/wb-catalog'), { headers: { ...authHeaders(token) } }),
        fetch(apiUrl('/operations/inventory-balances/summary'), {
          headers: { ...authHeaders(token) },
        }),
      ])
      if (!catRes.ok) {
        setError(await readApiErrorMessage(catRes))
        return
      }
      if (!stRes.ok) {
        setError(await readApiErrorMessage(stRes))
        return
      }
      setCatalog((await catRes.json()) as WbCatalogRow[])
      setStock((await stRes.json()) as StockSummaryRow[])
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Не удалось загрузить товары.')
    } finally {
      setBusy(false)
    }
  }

  useEffect(() => {
    void refreshAll()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const rows = useMemo(() => {
    const byProduct = new Map(stock.map((s) => [s.product_id, s]))
    return catalog.map((p) => {
      const bal = byProduct.get(p.id)
      const onHand = bal?.quantity ?? 0
      const reserved = bal?.reserved ?? 0
      const inStorage = bal?.quantity_in_storage ?? 0
      const freeTotal = Math.max(0, onHand - reserved)
      const availableForMp = bal?.available ?? Math.max(0, inStorage - reserved)
      return {
        ...p,
        stock_on_hand: onHand,
        stock_in_storage: inStorage,
        stock_in_sorting: bal?.quantity_in_sorting ?? 0,
        stock_reserved: reserved,
        // «Остаток» для селлера: всего на ФФ минус резерв (не вычитаем сортировку повторно).
        stock_free_total: freeTotal,
        // Доступно к новой отгрузке на МП — только из ячеек (как на бэкенде).
        stock_available_for_mp: availableForMp,
      }
    })
  }, [catalog, stock])

  const pagedRows = useMemo(() => {
    const start = page * rowsPerPage
    return rows.slice(start, start + rowsPerPage)
  }, [page, rows, rowsPerPage])

  function openPackagingEdit(p: WbCatalogRow) {
    setEditProduct(p)
    setEditText(p.packaging_instructions ?? '')
  }

  async function savePackagingInstructions() {
    if (!editProduct) return
    setEditBusy(true)
    setError(null)
    try {
      const res = await fetch(
        apiUrl(`/products/${editProduct.id}/packaging-instructions`),
        {
          method: 'PATCH',
          headers: { ...authHeaders(token), 'Content-Type': 'application/json' },
          body: JSON.stringify({ packaging_instructions: editText.trim() || null }),
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

  async function onSyncProducts() {
    setError(null)
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

  return (
    <Box>
      <Typography variant="h5" gutterBottom>
        Товары
      </Typography>
      <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
        Каталог WB и остаток на фулфилменте. <strong>Остаток</strong> — всего на ФФ минус резерв;
        отгрузку на МП можно планировать только по колонке «В ячейках» (после разкладки ФФ).
      </Typography>

      {error ? (
        <Alert severity="error" sx={{ mb: 2 }} data-testid="seller-products-error">
          {error}
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
          {busy ? <CircularProgress size={18} /> : null}
        </Stack>
      </Paper>

      <TableContainer component={Paper} variant="outlined" data-testid="seller-products-list">
        <Table stickyHeader size="small" data-testid="seller-products-table">
          <TableHead>
            <TableRow>
              <TableCell>Фото</TableCell>
              <TableCell>SKU</TableCell>
              <TableCell>Размер</TableCell>
              <TableCell>ШК</TableCell>
              <TableCell>Артикул продавца</TableCell>
              <TableCell>nm</TableCell>
              <TableCell>Название</TableCell>
              <TableCell align="right">На ФФ</TableCell>
              <TableCell align="right">В сортировке</TableCell>
              <TableCell align="right">В ячейках</TableCell>
              <TableCell align="right">Зарезерв.</TableCell>
              <TableCell align="right">Остаток</TableCell>
              <TableCell align="right">К отгрузке</TableCell>
              <TableCell>ТЗ упаковки</TableCell>
            </TableRow>
          </TableHead>
          <TableBody>
            {pagedRows.map((p) => (
              <TableRow key={p.id} hover data-testid="seller-product-row">
                <TableCell>
                  <ProductPhotoThumb src={p.wb_primary_image_url} />
                </TableCell>
                <TableCell>{p.sku_code}</TableCell>
                <TableCell>{p.wb_size ?? '—'}</TableCell>
                <TableCell>{p.wb_primary_barcode ?? (p.wb_barcodes[0] ?? '—')}</TableCell>
                <TableCell>{p.wb_vendor_code ?? '—'}</TableCell>
                <TableCell>{p.wb_nm_id ?? '—'}</TableCell>
                <TableCell>{p.name}</TableCell>
                <TableCell align="right" data-testid="seller-stock-on-hand">
                  {p.stock_on_hand}
                </TableCell>
                <TableCell align="right" data-testid="seller-stock-in-sorting">
                  {p.stock_in_sorting}
                </TableCell>
                <TableCell align="right" data-testid="seller-stock-in-storage">
                  {p.stock_in_storage}
                </TableCell>
                <TableCell align="right" data-testid="seller-stock-reserved">
                  {p.stock_reserved}
                </TableCell>
                <TableCell align="right" data-testid="seller-stock-free-total">
                  {p.stock_free_total}
                </TableCell>
                <TableCell align="right" data-testid="seller-stock-available">
                  {p.stock_available_for_mp}
                  {p.stock_reserved > 0 ? (
                    <Typography
                      component="span"
                      variant="caption"
                      color="text.secondary"
                      sx={{ display: 'block' }}
                      data-testid="seller-stock-available-hint"
                    >
                      (свободно {p.stock_free_total})
                    </Typography>
                  ) : null}
                </TableCell>
                <TableCell>
                  <Stack direction="row" spacing={1} sx={{ alignItems: 'center' }}>
                    <Chip
                      size="small"
                      label={p.has_packaging_instructions ? 'Заполнено' : 'Нет ТЗ'}
                      color={p.has_packaging_instructions ? 'success' : 'warning'}
                      variant="outlined"
                      data-testid={`seller-packaging-status-${p.id}`}
                    />
                    <Button
                      size="small"
                      onClick={() => openPackagingEdit(p)}
                      data-testid={`seller-packaging-edit-${p.id}`}
                    >
                      Редактировать
                    </Button>
                  </Stack>
                </TableCell>
              </TableRow>
            ))}
            {rows.length === 0 ? (
              <TableRow>
                <TableCell colSpan={14}>
                  <Typography variant="body2" color="text.secondary">
                    Пока нет товаров.
                  </Typography>
                </TableCell>
              </TableRow>
            ) : null}
          </TableBody>
        </Table>
        <TablePagination
          component="div"
          count={rows.length}
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
            variant="contained"
            disabled={editBusy}
            onClick={() => void savePackagingInstructions()}
            data-testid="seller-packaging-save"
          >
            Сохранить
          </Button>
        </DialogActions>
      </Dialog>
    </Box>
  )
}
