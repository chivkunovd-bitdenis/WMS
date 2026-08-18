import { useCallback, useEffect, useMemo, useState } from 'react'
import {
  Alert,
  Box,
  Button,
  Checkbox,
  Chip,
  FormControlLabel,
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
import { printPackagingInstructions } from '../../utils/printPackagingInstructions'

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
  requires_honest_sign: boolean
  has_packaging_instructions: boolean
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
  const [page, setPage] = useState(0)
  const [rowsPerPage, setRowsPerPage] = useState(10)
  const [editProduct, setEditProduct] = useState<WbCatalogRow | null>(null)
  const [editText, setEditText] = useState('')
  const [editRequiresHonestSign, setEditRequiresHonestSign] = useState(false)
  const [editBusy, setEditBusy] = useState(false)
  const [selectedProductIds, setSelectedProductIds] = useState<Set<string>>(new Set())
  const [bulkHonestSignBusy, setBulkHonestSignBusy] = useState(false)

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

  const pagedRows = useMemo(() => {
    const start = page * rowsPerPage
    return catalog.slice(start, start + rowsPerPage)
  }, [catalog, page, rowsPerPage])

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
        Каталог товаров, синхронизированных из WB. Остаток по складам и публикация в FBS
        настраиваются на экране каталога фулфилмента.
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
            <col style={{ width: '8%' }} />
            <col style={{ width: '24%' }} />
            <col style={{ width: '14%' }} />
            <col style={{ width: '10%' }} />
            <col style={{ width: '14%' }} />
            <col style={{ width: '8%' }} />
            <col style={{ width: '9%' }} />
            <col style={{ width: '9%' }} />
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
              <TableCell>Артикул WB</TableCell>
              <TableCell>ШК</TableCell>
              <TableCell>Размер</TableCell>
              <TableCell>ТЗ</TableCell>
              <TableCell>ЧЗ</TableCell>
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
                  <Typography variant="body2" sx={{ fontWeight: 600 }} title={p.name} noWrap>
                    {p.name}
                  </Typography>
                  <Typography variant="caption" color="text.secondary" noWrap>
                    SKU {p.sku_code}
                  </Typography>
                </TableCell>
                <TableCell>
                  <Typography variant="body2" title={p.wb_vendor_code ?? '—'} noWrap>
                    {p.wb_vendor_code ?? '—'}
                  </Typography>
                </TableCell>
                <TableCell>
                  <Typography variant="body2" title={String(p.wb_nm_id ?? '—')} noWrap>
                    {p.wb_nm_id ?? '—'}
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
              </TableRow>
            ))}
            {catalog.length === 0 ? (
              <TableRow>
                <TableCell colSpan={9}>
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
          count={catalog.length}
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
    </Box>
  )
}
