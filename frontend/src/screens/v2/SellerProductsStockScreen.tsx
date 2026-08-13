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
  Switch,
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
  // Признак «продаём этот товар по ФБС». Пока выключен — в кабинет WB про товар
  // не пишем ничего, и он не участвует в выгрузке остатков.
  fbs_stock_sync_enabled: boolean
  fbs_stock_limit: number | null
  fbs_published_amount: number | null
  fbs_sync_status: string | null
}

const FBS_SYNC_STATUS_LABEL: Record<string, { text: string; color: 'default' | 'success' | 'warning' | 'error' }> = {
  pending: { text: 'В очереди', color: 'warning' },
  confirmed: { text: 'В WB', color: 'success' },
  error: { text: 'Ошибка', color: 'error' },
  conflict: { text: 'Дубль chrtId', color: 'error' },
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
  const [notice, setNotice] = useState<string | null>(null)
  const [catalog, setCatalog] = useState<WbCatalogRow[]>([])
  const [stock, setStock] = useState<StockSummaryRow[]>([])
  const [page, setPage] = useState(0)
  const [rowsPerPage, setRowsPerPage] = useState(10)
  const [editProduct, setEditProduct] = useState<WbCatalogRow | null>(null)
  const [editText, setEditText] = useState('')
  const [editRequiresHonestSign, setEditRequiresHonestSign] = useState(false)
  const [editBusy, setEditBusy] = useState(false)
  const [fbsPending, setFbsPending] = useState<Set<string>>(new Set())
  const [limitDraft, setLimitDraft] = useState<Record<string, string>>({})
  const [fbsBulkBusy, setFbsBulkBusy] = useState(false)
  const [selectedProductIds, setSelectedProductIds] = useState<Set<string>>(new Set())
  const [bulkHonestSignBusy, setBulkHonestSignBusy] = useState(false)

  const refreshAll = useCallback(async () => {
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
  }, [authHeaders, token])

  useEffect(() => {
    void refreshAll()
  }, [refreshAll])

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

  const fbsEnabledCount = useMemo(
    () => rows.filter((row) => row.fbs_stock_sync_enabled).length,
    [rows],
  )
  const productIds = useMemo(() => rows.map((row) => row.id), [rows])
  const selectedCount = selectedProductIds.size
  const allProductsSelected =
    productIds.length > 0 && productIds.every((id) => selectedProductIds.has(id))
  const someProductsSelected = productIds.some((id) => selectedProductIds.has(id))

  useEffect(() => {
    const existing = new Set(productIds)
    setSelectedProductIds((current) => {
      const nextIds = [...current].filter((id) => existing.has(id))
      if (nextIds.length === current.size) {
        return current
      }
      return new Set(nextIds)
    })
  }, [productIds])

  function toggleAllProducts(checked: boolean) {
    setSelectedProductIds(checked ? new Set(productIds) : new Set())
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

  // ── Синхронизация остатков ФБС по каждому товару ───────────────────────────
  // Переключатель применяется оптимистично: строка перерисовывается сразу, а если
  // сервер откажет — возвращаем прежнее значение и показываем ошибку.

  const markFbsPending = useCallback((productId: string, pending: boolean) => {
    setFbsPending((current) => {
      const next = new Set(current)
      if (pending) next.add(productId)
      else next.delete(productId)
      return next
    })
  }, [])

  const patchRow = useCallback((productId: string, patch: Partial<WbCatalogRow>) => {
    setCatalog((current) =>
      current.map((row) => (row.id === productId ? { ...row, ...patch } : row)),
    )
  }, [])

  const sendFbsPatch = useCallback(
    async (productId: string, body: Record<string, unknown>) => {
      const res = await fetch(apiUrl(`/products/${productId}/fbs-stock-sync`), {
        method: 'PATCH',
        headers: { ...authHeaders(token), 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      })
      if (!res.ok) {
        throw new Error(await readApiErrorMessage(res))
      }
    },
    [authHeaders, token],
  )

  const toggleFbsSync = useCallback(
    async (row: WbCatalogRow, enabled: boolean) => {
      const previous = row.fbs_stock_sync_enabled
      setError(null)
      patchRow(row.id, { fbs_stock_sync_enabled: enabled })
      markFbsPending(row.id, true)
      try {
        await sendFbsPatch(row.id, { fbs_stock_sync_enabled: enabled })
      } catch (e) {
        patchRow(row.id, { fbs_stock_sync_enabled: previous })
        setError(
          e instanceof Error
            ? e.message
            : 'Не удалось переключить синхронизацию остатка по этому товару.',
        )
      } finally {
        markFbsPending(row.id, false)
      }
    },
    [markFbsPending, patchRow, sendFbsPatch],
  )

  const commitLimit = useCallback(
    async (row: WbCatalogRow) => {
      const raw = (limitDraft[row.id] ?? '').trim()
      const parsed = raw === '' ? null : Number(raw)
      if (parsed !== null && (!Number.isInteger(parsed) || parsed < 0)) {
        setError('Лимит должен быть целым числом от нуля или пустым.')
        return
      }
      setLimitDraft((current) => {
        const next = { ...current }
        delete next[row.id]
        return next
      })
      if (parsed === row.fbs_stock_limit) {
        return
      }
      const previous = row.fbs_stock_limit
      setError(null)
      patchRow(row.id, { fbs_stock_limit: parsed })
      markFbsPending(row.id, true)
      try {
        await sendFbsPatch(row.id, { fbs_stock_limit: parsed })
      } catch (e) {
        patchRow(row.id, { fbs_stock_limit: previous })
        setError(e instanceof Error ? e.message : 'Не удалось сохранить лимит.')
      } finally {
        markFbsPending(row.id, false)
      }
    },
    [limitDraft, markFbsPending, patchRow, sendFbsPatch],
  )

  const bulkFbsSync = useCallback(
    async (enabled: boolean) => {
      setError(null)
      setNotice(null)
      setFbsBulkBusy(true)
      try {
        const res = await fetch(apiUrl('/products/fbs-stock-sync/bulk'), {
          method: 'PATCH',
          headers: { ...authHeaders(token), 'Content-Type': 'application/json' },
          body: JSON.stringify({ product_ids: null, fbs_stock_sync_enabled: enabled }),
        })
        if (!res.ok) {
          setError(await readApiErrorMessage(res))
          return
        }
        await refreshAll()
      } catch (e) {
        setError(
          e instanceof Error ? e.message : 'Не удалось переключить синхронизацию по всем товарам.',
        )
      } finally {
        setFbsBulkBusy(false)
      }
    },
    [authHeaders, refreshAll, token],
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
    <Box>
      <Typography variant="h5" gutterBottom>
        Товары
      </Typography>
      <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
        Каталог WB и остаток на фулфилменте. <strong>Остаток</strong> — всего на ФФ минус резерв;
        отгрузку на МП можно планировать только по колонке «В ячейках» (после раскладки ФФ).
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

      <Paper variant="outlined" sx={{ p: 2, mb: 2 }} data-testid="seller-fbs-sync-panel">
        <Typography variant="subtitle1" sx={{ fontWeight: 600 }}>
          Продажа по ФБС
        </Typography>
        <Typography variant="body2" color="text.secondary" sx={{ mt: 0.5, maxWidth: 720 }}>
          Включите переключатель у тех товаров, которые продаёте по ФБС. С этого момента остаток
          с фулфилмента уходит в ваш кабинет WB и дальше поддерживается сам: любое движение товара
          на складе тут же меняет цифру в кабинете. Пока переключатель выключен, WB про этот товар
          от нас ничего не получает.
        </Typography>
        <Stack
          direction="row"
          spacing={1.5}
          sx={{ mt: 1.5, flexWrap: 'wrap', alignItems: 'center' }}
        >
          <Chip
            size="small"
            variant="outlined"
            color={fbsEnabledCount > 0 ? 'success' : 'default'}
            label={`Включено товаров: ${fbsEnabledCount} из ${rows.length}`}
            data-testid="seller-fbs-enabled-count"
          />
          <Button
            size="small"
            variant="outlined"
            disabled={fbsBulkBusy || busy || rows.length === 0}
            onClick={() => void bulkFbsSync(true)}
            data-testid="seller-fbs-enable-all"
          >
            Включить всем
          </Button>
          <Button
            size="small"
            variant="outlined"
            color="warning"
            disabled={fbsBulkBusy || busy || fbsEnabledCount === 0}
            onClick={() => void bulkFbsSync(false)}
            data-testid="seller-fbs-disable-all"
          >
            Выключить всем
          </Button>
          {fbsBulkBusy ? <CircularProgress size={18} /> : null}
        </Stack>
      </Paper>

      <TableContainer component={Paper} variant="outlined" data-testid="seller-products-list">
        <Table stickyHeader size="small" data-testid="seller-products-table">
          <TableHead>
            <TableRow>
              <TableCell padding="checkbox" width={52}>
                <Checkbox
                  size="small"
                  checked={allProductsSelected}
                  indeterminate={someProductsSelected && !allProductsSelected}
                  disabled={busy || productIds.length === 0}
                  onChange={(e) => toggleAllProducts(e.target.checked)}
                  slotProps={{ input: { 'aria-label': 'Выбрать все товары' } }}
                  data-testid="seller-products-select-all"
                />
              </TableCell>
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
              <TableCell sx={{ minWidth: 210 }}>Продажа по ФБС</TableCell>
              <TableCell>ТЗ упаковки</TableCell>
            </TableRow>
          </TableHead>
          <TableBody>
            {pagedRows.map((p) => (
              <TableRow key={p.id} hover data-testid="seller-product-row">
                <TableCell padding="checkbox">
                  <Checkbox
                    size="small"
                    checked={selectedProductIds.has(p.id)}
                    onChange={(e) => toggleProductSelected(p.id, e.target.checked)}
                    slotProps={{ input: { 'aria-label': `Выбрать товар ${p.sku_code}` } }}
                    data-testid={`seller-product-select-${p.id}`}
                  />
                </TableCell>
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
                <TableCell align="right">
                  <Box component="span" data-testid="seller-stock-available">
                    {p.stock_available_for_mp}
                  </Box>
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
                <TableCell data-testid={`seller-fbs-cell-${p.id}`}>
                  <Stack spacing={0.75}>
                    <FormControlLabel
                      sx={{ m: 0 }}
                      control={
                        <Switch
                          size="small"
                          checked={p.fbs_stock_sync_enabled}
                          disabled={fbsPending.has(p.id) || fbsBulkBusy}
                          onChange={(_, checked) => void toggleFbsSync(p, checked)}
                          slotProps={{
                            input: { 'data-testid': `seller-fbs-toggle-${p.id}` } as Record<
                              string,
                              string
                            >,
                          }}
                        />
                      }
                      label={
                        <Typography variant="caption" color="text.secondary">
                          {p.fbs_stock_sync_enabled ? 'Синхронизируем' : 'Выключено'}
                        </Typography>
                      }
                    />
                    {p.fbs_stock_sync_enabled ? (
                      <>
                        <TextField
                          size="small"
                          label="Лимит"
                          placeholder="без лимита"
                          value={limitDraft[p.id] ?? (p.fbs_stock_limit ?? '')}
                          disabled={fbsPending.has(p.id) || fbsBulkBusy}
                          onChange={(e) =>
                            setLimitDraft((current) => ({ ...current, [p.id]: e.target.value }))
                          }
                          onBlur={() => void commitLimit(p)}
                          onKeyDown={(e) => {
                            if (e.key === 'Enter') (e.target as HTMLInputElement).blur()
                          }}
                          slotProps={{
                            htmlInput: {
                              inputMode: 'numeric',
                              'data-testid': `seller-fbs-limit-${p.id}`,
                            },
                          }}
                          sx={{ maxWidth: 130 }}
                        />
                        <Stack direction="row" spacing={0.75} sx={{ alignItems: 'center' }}>
                          <Chip
                            size="small"
                            variant="outlined"
                            color={FBS_SYNC_STATUS_LABEL[p.fbs_sync_status ?? '']?.color ?? 'default'}
                            label={
                              FBS_SYNC_STATUS_LABEL[p.fbs_sync_status ?? '']?.text ?? 'Ещё не уходил'
                            }
                            data-testid={`seller-fbs-status-${p.id}`}
                          />
                          <Typography variant="caption" color="text.secondary">
                            {p.fbs_published_amount != null ? `${p.fbs_published_amount} шт` : '—'}
                          </Typography>
                        </Stack>
                      </>
                    ) : null}
                  </Stack>
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
                    {p.requires_honest_sign ? (
                      <Chip
                        size="small"
                        label="ЧЗ"
                        color="info"
                        variant="outlined"
                        data-testid={`seller-honest-sign-status-${p.id}`}
                      />
                    ) : null}
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
                <TableCell colSpan={16}>
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
