import { useEffect, useMemo, useState } from 'react'
import {
  Alert,
  Avatar,
  Box,
  Button,
  CircularProgress,
  Paper,
  Stack,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TablePagination,
  TableRow,
  Typography,
} from '@mui/material'
import { apiUrl } from '../../api'
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
    return catalog.map((p) => ({
      ...p,
      stock_total: byProduct.get(p.id)?.quantity ?? 0,
    }))
  }, [catalog, stock])

  const pagedRows = useMemo(() => {
    const start = page * rowsPerPage
    return rows.slice(start, start + rowsPerPage)
  }, [page, rows, rowsPerPage])

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
        Каталог WB и остаток на фулфилменте (итого по SKU)
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
              <TableCell>ШК</TableCell>
              <TableCell>Артикул продавца</TableCell>
              <TableCell>nm</TableCell>
              <TableCell>Название</TableCell>
              <TableCell align="right">Остаток (итого)</TableCell>
            </TableRow>
          </TableHead>
          <TableBody>
            {pagedRows.map((p) => (
              <TableRow key={p.id} hover data-testid="seller-product-row">
                <TableCell>
                  <Avatar
                    variant="rounded"
                    src={p.wb_primary_image_url ?? undefined}
                    sx={{ width: 44, height: 44 }}
                  />
                </TableCell>
                <TableCell>{p.sku_code}</TableCell>
                <TableCell>{p.wb_primary_barcode ?? (p.wb_barcodes[0] ?? '—')}</TableCell>
                <TableCell>{p.wb_vendor_code ?? '—'}</TableCell>
                <TableCell>{p.wb_nm_id ?? '—'}</TableCell>
                <TableCell>{p.name}</TableCell>
                <TableCell align="right">{p.stock_total}</TableCell>
              </TableRow>
            ))}
            {rows.length === 0 ? (
              <TableRow>
                <TableCell colSpan={7}>
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
    </Box>
  )
}
