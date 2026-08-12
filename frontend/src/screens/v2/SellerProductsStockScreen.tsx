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
  Drawer,
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
  quantity_fbs: number
  quantity_reserved_directions: number
  quantity_free_fbo: number
}

type StockDirectionRow = {
  id: string
  product_id: string
  name: string
  comment: string | null
  quantity: number
  is_fbs: boolean
}

type DirectionDraft = {
  name: string
  comment: string
  quantity: string
  is_fbs: boolean
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
  const [editRequiresHonestSign, setEditRequiresHonestSign] = useState(false)
  const [editBusy, setEditBusy] = useState(false)
  const [fbsPending, setFbsPending] = useState<Set<string>>(new Set())
  const [limitDraft, setLimitDraft] = useState<Record<string, string>>({})
  const [fbsBulkBusy, setFbsBulkBusy] = useState(false)
  const [directionProductId, setDirectionProductId] = useState<string | null>(null)
  const [directions, setDirections] = useState<Record<string, StockDirectionRow[]>>({})
  const [directionDrafts, setDirectionDrafts] = useState<Record<string, DirectionDraft>>({})
  const [directionBusy, setDirectionBusy] = useState<Set<string>>(new Set())

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
        stock_fbs: bal?.quantity_fbs ?? 0,
        stock_reserved_directions: bal?.quantity_reserved_directions ?? 0,
        stock_free_fbo: bal?.quantity_free_fbo ?? onHand,
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

  const markDirectionBusy = useCallback((productId: string, pending: boolean) => {
    setDirectionBusy((current) => {
      const next = new Set(current)
      if (pending) next.add(productId)
      else next.delete(productId)
      return next
    })
  }, [])

  const directionDraftFor = useCallback(
    (productId: string): DirectionDraft =>
      directionDrafts[productId] ?? {
        name: '',
        comment: '',
        quantity: '',
        is_fbs: false,
      },
    [directionDrafts],
  )

  const patchDirectionDraft = useCallback((productId: string, patch: Partial<DirectionDraft>) => {
    setDirectionDrafts((current) => {
      const prev = current[productId] ?? {
        name: '',
        comment: '',
        quantity: '',
        is_fbs: false,
      }
      return { ...current, [productId]: { ...prev, ...patch } }
    })
  }, [])

  const loadDirections = useCallback(
    async (productId: string) => {
      markDirectionBusy(productId, true)
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
        setDirections((current) => ({
          ...current,
          [productId]: body,
        }))
      } catch (e) {
        setError(e instanceof Error ? e.message : 'Не удалось загрузить направления остатка.')
      } finally {
        markDirectionBusy(productId, false)
      }
    },
    [authHeaders, markDirectionBusy, token],
  )

  const openDirections = useCallback(
    async (productId: string) => {
      setDirectionProductId(productId)
      if (directions[productId] == null) {
        await loadDirections(productId)
      }
    },
    [directions, loadDirections],
  )

  const directionProduct = useMemo(
    () => rows.find((row) => row.id === directionProductId) ?? null,
    [directionProductId, rows],
  )
  const drawerDraft = directionProduct ? directionDraftFor(directionProduct.id) : null

  const createDirection = useCallback(
    async (productId: string) => {
      const draft = directionDraftFor(productId)
      const qty = Number(draft.quantity)
      if (!draft.name.trim()) {
        setError('Название направления обязательно.')
        return
      }
      if (!Number.isInteger(qty) || qty < 0) {
        setError('Количество направления должно быть целым числом от нуля.')
        return
      }
      markDirectionBusy(productId, true)
      setError(null)
      try {
        const res = await fetch(apiUrl(`/products/${productId}/stock-directions`), {
          method: 'POST',
          headers: { ...authHeaders(token), 'Content-Type': 'application/json' },
          body: JSON.stringify({
            name: draft.name.trim(),
            comment: draft.comment.trim() || null,
            quantity: qty,
            is_fbs: draft.is_fbs,
          }),
        })
        if (!res.ok) {
          setError(await readApiErrorMessage(res))
          return
        }
        setDirectionDrafts((current) => ({
          ...current,
          [productId]: { name: '', comment: '', quantity: '', is_fbs: false },
        }))
        await loadDirections(productId)
        await refreshAll()
      } catch (e) {
        setError(e instanceof Error ? e.message : 'Не удалось создать направление.')
      } finally {
        markDirectionBusy(productId, false)
      }
    },
    [authHeaders, directionDraftFor, loadDirections, markDirectionBusy, refreshAll, token],
  )

  const deleteDirection = useCallback(
    async (productId: string, directionId: string) => {
      markDirectionBusy(productId, true)
      setError(null)
      try {
        const res = await fetch(apiUrl(`/products/stock-directions/${directionId}`), {
          method: 'DELETE',
          headers: { ...authHeaders(token) },
        })
        if (!res.ok) {
          setError(await readApiErrorMessage(res))
          return
        }
        await loadDirections(productId)
        await refreshAll()
      } catch (e) {
        setError(e instanceof Error ? e.message : 'Не удалось удалить направление.')
      } finally {
        markDirectionBusy(productId, false)
      }
    },
    [authHeaders, loadDirections, markDirectionBusy, refreshAll, token],
  )

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

      <Paper variant="outlined" sx={{ p: 2, mb: 2 }} data-testid="seller-fbs-sync-panel">
        <Typography variant="subtitle1" sx={{ fontWeight: 600 }}>
          Продажа по ФБС
        </Typography>
        <Typography variant="body2" color="text.secondary" sx={{ mt: 0.5, maxWidth: 720 }}>
          WB получает только FBS-пул, который выделен в распределении товара галкой FBS. Если
          FBS-пул равен нулю, в WB уходит ноль, даже когда общий остаток на фулфилменте больше.
          Остальные направления остаются резервами или свободным FBO-остатком.
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
              <TableCell>Товар</TableCell>
              <TableCell>Артикул WB</TableCell>
              <TableCell>ШК</TableCell>
              <TableCell align="right">На ФФ</TableCell>
              <TableCell align="right">В ячейках</TableCell>
              <TableCell align="right">Свободный FBO</TableCell>
              <TableCell sx={{ minWidth: 170 }}>Распределение</TableCell>
              <TableCell sx={{ minWidth: 210 }}>Продажа по ФБС</TableCell>
              <TableCell>ТЗ упаковки</TableCell>
            </TableRow>
          </TableHead>
          <TableBody>
            {pagedRows.map((p) => (
              <TableRow hover data-testid="seller-product-row" key={p.id}>
                <TableCell>
                  <Stack direction="row" spacing={1.25} sx={{ alignItems: 'center', minWidth: 260 }}>
                    <ProductPhotoThumb src={p.wb_primary_image_url} />
                    <Box sx={{ minWidth: 0 }}>
                      <Typography variant="body2" sx={{ fontWeight: 600 }}>
                        {p.name}
                      </Typography>
                      <Typography variant="caption" color="text.secondary" sx={{ display: 'block' }}>
                        SKU {p.sku_code}
                        {p.wb_vendor_code ? ` · ${p.wb_vendor_code}` : ''}
                        {p.wb_size ? ` · ${p.wb_size}` : ''}
                      </Typography>
                    </Box>
                  </Stack>
                </TableCell>
                <TableCell>{p.wb_nm_id ?? '—'}</TableCell>
                <TableCell>{p.wb_primary_barcode ?? (p.wb_barcodes[0] ?? '—')}</TableCell>
                <TableCell align="right" data-testid="seller-stock-on-hand">
                  {p.stock_on_hand}
                </TableCell>
                <TableCell align="right" data-testid="seller-stock-in-storage">
                  {p.stock_in_storage}
                </TableCell>
                <TableCell align="right" data-testid="seller-stock-free-fbo">
                  {p.stock_free_fbo}
                </TableCell>
                <TableCell data-testid={`seller-stock-distribution-${p.id}`}>
                  <Stack spacing={0.5}>
                    <Typography variant="body2" sx={{ whiteSpace: 'nowrap' }}>
                      FBS {p.stock_fbs} шт · резервы {p.stock_reserved_directions} шт
                    </Typography>
                    <Button
                      size="small"
                      variant="outlined"
                      sx={{ alignSelf: 'flex-start' }}
                      onClick={() => void openDirections(p.id)}
                      data-testid={`seller-stock-directions-toggle-${p.id}`}
                    >
                      Распределение
                    </Button>
                  </Stack>
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
                        {p.stock_fbs === 0 ? (
                          <Alert severity="info" variant="outlined" sx={{ py: 0 }}>
                            FBS-пул 0: в WB уйдёт 0 шт.
                          </Alert>
                        ) : null}
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

      <Drawer
        anchor="right"
        open={directionProduct != null}
        onClose={() => setDirectionProductId(null)}
        slotProps={{
          paper: { sx: { width: { xs: '100%', sm: 480 }, maxWidth: '100%' } },
        }}
        data-testid={
          directionProduct ? `seller-stock-directions-panel-${directionProduct.id}` : undefined
        }
      >
        {directionProduct && drawerDraft ? (
          <Box sx={{ p: 2.5 }}>
            <Stack spacing={2}>
              <Box>
                <Typography variant="h6">Распределение остатка</Typography>
                <Typography variant="body2" color="text.secondary">
                  {directionProduct.sku_code} · {directionProduct.name}
                </Typography>
              </Box>
              <Stack direction="row" spacing={2}>
                <Box>
                  <Typography variant="caption" color="text.secondary">
                    FBS
                  </Typography>
                  <Typography variant="h6">{directionProduct.stock_fbs} шт</Typography>
                </Box>
                <Box>
                  <Typography variant="caption" color="text.secondary">
                    Резервы
                  </Typography>
                  <Typography variant="h6">
                    {directionProduct.stock_reserved_directions} шт
                  </Typography>
                </Box>
                <Box>
                  <Typography variant="caption" color="text.secondary">
                    Свободный FBO
                  </Typography>
                  <Typography variant="h6">{directionProduct.stock_free_fbo} шт</Typography>
                </Box>
              </Stack>
              {directionProduct.stock_fbs === 0 ? (
                <Alert severity="info" variant="outlined">
                  FBS-пул не выделен. При включённой синхронизации WB получит 0 шт.
                </Alert>
              ) : null}
              <Divider />
              <Stack spacing={1}>
                {directions[directionProduct.id]?.length === 0 &&
                !directionBusy.has(directionProduct.id) ? (
                  <Typography variant="body2" color="text.secondary">
                    Направлений пока нет.
                  </Typography>
                ) : null}
                {(directions[directionProduct.id] ?? []).map((direction) => (
                  <Paper
                    key={direction.id}
                    variant="outlined"
                    sx={{ p: 1.25 }}
                    data-testid={`seller-stock-direction-row-${direction.id}`}
                  >
                    <Stack direction="row" spacing={1} sx={{ alignItems: 'flex-start' }}>
                      <Box sx={{ minWidth: 0, flex: 1 }}>
                        <Typography variant="body2" sx={{ fontWeight: 600 }}>
                          {direction.name}
                        </Typography>
                        <Typography variant="caption" color="text.secondary">
                          {direction.is_fbs ? 'FBS-пул' : 'Резерв/набор'} · {direction.quantity} шт
                        </Typography>
                        {direction.comment ? (
                          <Typography variant="caption" color="text.secondary" sx={{ display: 'block' }}>
                            {direction.comment}
                          </Typography>
                        ) : null}
                      </Box>
                      <Button
                        size="small"
                        color="warning"
                        disabled={directionBusy.has(directionProduct.id)}
                        onClick={() => void deleteDirection(directionProduct.id, direction.id)}
                        data-testid={`seller-stock-direction-delete-${direction.id}`}
                      >
                        Удалить
                      </Button>
                    </Stack>
                  </Paper>
                ))}
              </Stack>
              <Divider />
              <Stack spacing={1.25}>
                <TextField
                  size="small"
                  label="Название"
                  value={drawerDraft.name}
                  onChange={(e) => patchDirectionDraft(directionProduct.id, { name: e.target.value })}
                  slotProps={{
                    htmlInput: { 'data-testid': `seller-stock-direction-name-${directionProduct.id}` },
                  }}
                />
                <TextField
                  size="small"
                  label="Количество"
                  value={drawerDraft.quantity}
                  onChange={(e) =>
                    patchDirectionDraft(directionProduct.id, { quantity: e.target.value })
                  }
                  slotProps={{
                    htmlInput: {
                      inputMode: 'numeric',
                      'data-testid': `seller-stock-direction-quantity-${directionProduct.id}`,
                    },
                  }}
                />
                <TextField
                  size="small"
                  label="Комментарий"
                  value={drawerDraft.comment}
                  onChange={(e) =>
                    patchDirectionDraft(directionProduct.id, { comment: e.target.value })
                  }
                  slotProps={{
                    htmlInput: {
                      'data-testid': `seller-stock-direction-comment-${directionProduct.id}`,
                    },
                  }}
                />
                <FormControlLabel
                  sx={{ m: 0 }}
                  control={
                    <Checkbox
                      checked={drawerDraft.is_fbs}
                      onChange={(e) =>
                        patchDirectionDraft(directionProduct.id, { is_fbs: e.target.checked })
                      }
                      data-testid={`seller-stock-direction-fbs-${directionProduct.id}`}
                    />
                  }
                  label="FBS-пул для публикации в WB"
                />
                <Stack direction="row" spacing={1} sx={{ alignItems: 'center' }}>
                  <Button
                    variant="contained"
                    disabled={directionBusy.has(directionProduct.id)}
                    onClick={() => void createDirection(directionProduct.id)}
                    data-testid={`seller-stock-direction-submit-${directionProduct.id}`}
                  >
                    Добавить
                  </Button>
                  <Button onClick={() => setDirectionProductId(null)}>Закрыть</Button>
                  {directionBusy.has(directionProduct.id) ? <CircularProgress size={18} /> : null}
                </Stack>
              </Stack>
            </Stack>
          </Box>
        ) : null}
      </Drawer>

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
