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
  Menu,
  MenuItem,
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

type DirectionDeleteTarget = {
  productId: string
  direction: StockDirectionRow
}

type DirectionDraft = {
  name: string
  comment: string
  quantity: string
  is_fbs: boolean
}

function emptyDirectionDraft(): DirectionDraft {
  return {
    name: '',
    comment: '',
    quantity: '',
    is_fbs: false,
  }
}

function directionQuantityFromDraft(raw: string): number | null {
  const trimmed = raw.trim()
  if (!trimmed) return null
  const qty = Number(trimmed)
  return Number.isInteger(qty) && qty >= 0 ? qty : null
}

function fbsPublicationState(row: WbCatalogRow & { stock_fbs: number }) {
  if (row.stock_fbs <= 0) {
    return { label: 'Нет FBS', color: 'text.secondary', canToggle: false }
  }
  if (row.fbs_sync_status === 'error' || row.fbs_sync_status === 'conflict') {
    return { label: 'Ошибка WB', color: 'error.main', canToggle: true }
  }
  if (row.fbs_stock_sync_enabled && row.fbs_sync_status === 'confirmed') {
    return {
      label: `WB: ${row.fbs_published_amount ?? row.stock_fbs} шт`,
      color: 'success.main',
      canToggle: true,
    }
  }
  if (row.fbs_stock_sync_enabled) {
    return { label: 'Проверяем WB', color: 'warning.main', canToggle: true }
  }
  return { label: 'Пауза', color: 'text.secondary', canToggle: true }
}

type BulkPublicationAction = 'enable' | 'pause' | 'retry'

const BULK_PUBLICATION_LABEL: Record<BulkPublicationAction, string> = {
  enable: 'Включить',
  pause: 'Поставить на паузу',
  retry: 'Повторить отправку',
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
  const [fbsBulkBusy, setFbsBulkBusy] = useState(false)
  const [selectedProductIds, setSelectedProductIds] = useState<Set<string>>(new Set())
  const [bulkMenuAnchor, setBulkMenuAnchor] = useState<HTMLElement | null>(null)
  const [bulkConfirmAction, setBulkConfirmAction] = useState<BulkPublicationAction | null>(null)
  const [bulkResult, setBulkResult] = useState<string | null>(null)
  const [directionProductId, setDirectionProductId] = useState<string | null>(null)
  const [directions, setDirections] = useState<Record<string, StockDirectionRow[]>>({})
  const [directionDrafts, setDirectionDrafts] = useState<Record<string, DirectionDraft>>({})
  const [directionBusy, setDirectionBusy] = useState<Set<string>>(new Set())
  const [editingDirectionId, setEditingDirectionId] = useState<string | null>(null)
  const [deleteTarget, setDeleteTarget] = useState<DirectionDeleteTarget | null>(null)
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

  const fbsPublishingCount = useMemo(
    () => rows.filter((row) => row.stock_fbs > 0 && row.fbs_stock_sync_enabled).length,
    [rows],
  )
  const selectedRows = useMemo(
    () => rows.filter((row) => selectedProductIds.has(row.id)),
    [rows, selectedProductIds],
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
    const rowIds = new Set(rows.map((row) => row.id))
    setSelectedProductIds((current) => {
      const next = new Set([...current].filter((id) => rowIds.has(id)))
      return next.size === current.size ? current : next
    })
  }, [rows])

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
      directionDrafts[productId] ?? emptyDirectionDraft(),
    [directionDrafts],
  )

  const patchDirectionDraft = useCallback((productId: string, patch: Partial<DirectionDraft>) => {
    setDirectionDrafts((current) => {
      const prev = current[productId] ?? {
        ...emptyDirectionDraft(),
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
      setEditingDirectionId(null)
      setDirectionDrafts((current) => ({
        ...current,
        [productId]: emptyDirectionDraft(),
      }))
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
  const deleteBusy = deleteTarget ? directionBusy.has(deleteTarget.productId) : false

  const closeDirections = useCallback(() => {
    setDirectionProductId(null)
    setEditingDirectionId(null)
    setDeleteTarget(null)
  }, [])

  const startDirectionEdit = useCallback((productId: string, direction: StockDirectionRow) => {
    setError(null)
    setEditingDirectionId(direction.id)
    setDirectionDrafts((current) => ({
      ...current,
      [productId]: {
        name: direction.name,
        comment: direction.comment ?? '',
        quantity: String(direction.quantity),
        is_fbs: direction.is_fbs,
      },
    }))
  }, [])

  const cancelDirectionEdit = useCallback((productId: string) => {
    setEditingDirectionId(null)
    setDirectionDrafts((current) => ({
      ...current,
      [productId]: emptyDirectionDraft(),
    }))
  }, [])

  const submitDirection = useCallback(
    async (productId: string) => {
      const draft = directionDraftFor(productId)
      const qty = directionQuantityFromDraft(draft.quantity)
      if (!draft.name.trim()) {
        setError('Название направления обязательно.')
        return
      }
      if (qty == null) {
        setError('Количество направления должно быть целым числом от нуля.')
        return
      }
      const isEditing = editingDirectionId != null
      markDirectionBusy(productId, true)
      setError(null)
      try {
        const res = await fetch(
          apiUrl(
            isEditing
              ? `/products/stock-directions/${editingDirectionId}`
              : `/products/${productId}/stock-directions`,
          ),
          {
            method: isEditing ? 'PATCH' : 'POST',
            headers: { ...authHeaders(token), 'Content-Type': 'application/json' },
            body: JSON.stringify({
              name: draft.name.trim(),
              comment: draft.comment.trim() || null,
              quantity: qty,
              is_fbs: draft.is_fbs,
            }),
          },
        )
        if (!res.ok) {
          setError(await readApiErrorMessage(res))
          return
        }
        setDirectionDrafts((current) => ({
          ...current,
          [productId]: emptyDirectionDraft(),
        }))
        setEditingDirectionId(null)
        await loadDirections(productId)
        await refreshAll()
      } catch (e) {
        setError(
          e instanceof Error
            ? e.message
            : isEditing
              ? 'Не удалось сохранить направление.'
              : 'Не удалось создать направление.',
        )
      } finally {
        markDirectionBusy(productId, false)
      }
    },
    [
      authHeaders,
      directionDraftFor,
      editingDirectionId,
      loadDirections,
      markDirectionBusy,
      refreshAll,
      token,
    ],
  )

  const requestDeleteDirection = useCallback((productId: string, direction: StockDirectionRow) => {
    setDeleteTarget({ productId, direction })
  }, [])

  const confirmDeleteDirection = useCallback(
    async () => {
      if (!deleteTarget) return
      const { productId, direction } = deleteTarget
      markDirectionBusy(productId, true)
      setError(null)
      try {
        const res = await fetch(apiUrl(`/products/stock-directions/${direction.id}`), {
          method: 'DELETE',
          headers: { ...authHeaders(token) },
        })
        if (!res.ok) {
          setError(await readApiErrorMessage(res))
          return
        }
        setDeleteTarget(null)
        if (editingDirectionId === direction.id) {
          setEditingDirectionId(null)
          setDirectionDrafts((current) => ({
            ...current,
            [productId]: emptyDirectionDraft(),
          }))
        }
        await loadDirections(productId)
        await refreshAll()
      } catch (e) {
        setError(e instanceof Error ? e.message : 'Не удалось удалить направление.')
      } finally {
        markDirectionBusy(productId, false)
      }
    },
    [
      authHeaders,
      deleteTarget,
      editingDirectionId,
      loadDirections,
      markDirectionBusy,
      refreshAll,
      token,
    ],
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

  const closeBulkConfirm = useCallback(() => {
    if (!fbsBulkBusy) setBulkConfirmAction(null)
  }, [fbsBulkBusy])

  const requestBulkPublication = useCallback((action: BulkPublicationAction) => {
    setBulkMenuAnchor(null)
    setBulkResult(null)
    setBulkConfirmAction(action)
  }, [])

  const configureSelectedFbsPool = useCallback(() => {
    setBulkMenuAnchor(null)
    const firstSelected = selectedRows[0]
    if (firstSelected) {
      void openDirections(firstSelected.id)
    }
  }, [openDirections, selectedRows])

  const confirmBulkFbsSync = useCallback(
    async () => {
      if (!bulkConfirmAction || selectedRows.length === 0) return
      const productIds = selectedRows.map((row) => row.id)
      const enabled = bulkConfirmAction !== 'pause'
      setError(null)
      setBulkResult(null)
      setNotice(null)
      setFbsBulkBusy(true)
      try {
        const res = await fetch(apiUrl('/products/fbs-stock-sync/bulk'), {
          method: 'PATCH',
          headers: { ...authHeaders(token), 'Content-Type': 'application/json' },
          body: JSON.stringify({ product_ids: productIds, fbs_stock_sync_enabled: enabled }),
        })
        if (!res.ok) {
          setError(await readApiErrorMessage(res))
          return
        }
        const body = (await res.json()) as { updated_count?: number }
        const updatedCount = body.updated_count ?? productIds.length
        const skippedCount = Math.max(0, productIds.length - updatedCount)
        setBulkResult(
          skippedCount > 0
            ? `Обновлено ${updatedCount}, пропущено ${skippedCount}. Будут изменены только выбранные товары.`
            : `Обновлено ${updatedCount}. Будут изменены только выбранные товары.`,
        )
        setBulkConfirmAction(null)
        setSelectedProductIds(new Set())
        await refreshAll()
      } catch (e) {
        setError(
          e instanceof Error
            ? e.message
            : 'Не удалось изменить публикацию по выбранным товарам.',
        )
      } finally {
        setFbsBulkBusy(false)
      }
    },
    [authHeaders, bulkConfirmAction, refreshAll, selectedRows, token],
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
        Каталог WB и остаток на фулфилменте. <strong>Остаток</strong> — всего на ФФ минус резерв;
        отгрузку на МП можно планировать только по колонке «В ячейках» (после раскладки ФФ).
      </Typography>

      {error ? (
        <Alert severity="error" sx={{ mb: 2 }} data-testid="seller-products-error">
          {error}
        </Alert>
      ) : null}
      {bulkResult ? (
        <Alert severity="success" sx={{ mb: 2 }} data-testid="seller-fbs-bulk-result">
          {bulkResult}
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
        <Stack
          direction="row"
          spacing={1.5}
          sx={{ flexWrap: 'wrap', alignItems: 'center', justifyContent: 'space-between', gap: 1 }}
        >
          <Stack spacing={0.25} sx={{ minWidth: 0 }}>
            <Typography variant="subtitle1" sx={{ fontWeight: 600 }}>
              Публикация FBS в WB
            </Typography>
            <Typography
              variant="caption"
              color="text.secondary"
              data-testid="seller-fbs-enabled-count"
            >
              Публикуется: {fbsPublishingCount} из {rows.length}
              {selectedCount > 0 ? ` · выбрано ${selectedCount}` : ''}
            </Typography>
          </Stack>
          <Stack direction="row" spacing={1} sx={{ alignItems: 'center', flexWrap: 'wrap' }}>
            {selectedCount > 0 ? (
              <>
                <Button
                  size="small"
                  variant="contained"
                  disabled={fbsBulkBusy || busy}
                  onClick={(event) => setBulkMenuAnchor(event.currentTarget)}
                  data-testid="seller-fbs-bulk-action"
                >
                  Изменить публикацию
                </Button>
                <Button
                  size="small"
                  disabled={fbsBulkBusy}
                  onClick={() => setSelectedProductIds(new Set())}
                  data-testid="seller-products-clear-selection"
                >
                  Сбросить
                </Button>
              </>
            ) : null}
            {fbsBulkBusy ? <CircularProgress size={18} /> : null}
          </Stack>
        </Stack>
      </Paper>
      <Menu
        anchorEl={bulkMenuAnchor}
        open={bulkMenuAnchor != null}
        onClose={() => setBulkMenuAnchor(null)}
      >
        <MenuItem
          onClick={() => requestBulkPublication('enable')}
          data-testid="seller-fbs-bulk-enable"
        >
          Включить
        </MenuItem>
        <MenuItem
          onClick={() => requestBulkPublication('pause')}
          data-testid="seller-fbs-bulk-pause"
        >
          Поставить на паузу
        </MenuItem>
        <MenuItem
          onClick={() => requestBulkPublication('retry')}
          data-testid="seller-fbs-bulk-retry"
        >
          Повторить отправку
        </MenuItem>
        <MenuItem onClick={configureSelectedFbsPool} data-testid="seller-fbs-bulk-configure">
          Настроить FBS-пул
        </MenuItem>
      </Menu>
      <Dialog
        open={bulkConfirmAction != null}
        onClose={closeBulkConfirm}
        fullWidth
        maxWidth="sm"
        data-testid="seller-fbs-bulk-confirm-dialog"
      >
        <DialogTitle>
          {bulkConfirmAction
            ? `${BULK_PUBLICATION_LABEL[bulkConfirmAction]} публикацию FBS для ${selectedCount} товаров?`
            : 'Изменить публикацию FBS?'}
        </DialogTitle>
        <DialogContent>
          <Stack spacing={1.25}>
            <Typography variant="body2" color="text.secondary">
              Будут изменены только выбранные товары.
            </Typography>
            <Stack spacing={0.5} data-testid="seller-fbs-bulk-selected-list">
              {selectedRows.slice(0, 5).map((row) => (
                <Typography key={row.id} variant="body2" noWrap>
                  {row.sku_code} · {row.name}
                </Typography>
              ))}
              {selectedRows.length > 5 ? (
                <Typography variant="caption" color="text.secondary">
                  Ещё {selectedRows.length - 5}
                </Typography>
              ) : null}
            </Stack>
          </Stack>
        </DialogContent>
        <DialogActions>
          <Button disabled={fbsBulkBusy} onClick={closeBulkConfirm}>
            Отмена
          </Button>
          <Button
            variant="contained"
            disabled={fbsBulkBusy || selectedCount === 0}
            onClick={() => void confirmBulkFbsSync()}
            data-testid="seller-fbs-bulk-confirm-submit"
          >
            Подтвердить
          </Button>
        </DialogActions>
      </Dialog>

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
            <col style={{ width: '28%' }} />
            <col style={{ width: '15%' }} />
            <col style={{ width: '16%' }} />
            <col style={{ width: '12%' }} />
            <col style={{ width: '13%' }} />
            <col style={{ width: '12%' }} />
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
              <TableCell>Товар</TableCell>
              <TableCell>Артикул WB</TableCell>
              <TableCell align="right">Остаток</TableCell>
              <TableCell>FBS-пул</TableCell>
              <TableCell>Публикация WB</TableCell>
              <TableCell>ТЗ / ЧЗ</TableCell>
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
                  <Stack direction="row" spacing={1.25} sx={{ alignItems: 'center', minWidth: 0 }}>
                    <ProductPhotoThumb src={p.wb_primary_image_url} />
                    <Box sx={{ minWidth: 0, flex: 1 }}>
                      <Typography
                        variant="body2"
                        sx={{ fontWeight: 600, maxWidth: '100%' }}
                        noWrap
                      >
                        {p.name}
                      </Typography>
                      <Typography
                        variant="caption"
                        color="text.secondary"
                        sx={{ display: 'block', maxWidth: '100%' }}
                        noWrap
                      >
                        SKU {p.sku_code}
                        {p.wb_vendor_code ? ` · ${p.wb_vendor_code}` : ''}
                        {p.wb_size ? ` · ${p.wb_size}` : ''}
                      </Typography>
                    </Box>
                  </Stack>
                </TableCell>
                <TableCell>
                  <Stack spacing={0.25} sx={{ minWidth: 0 }}>
                    <Typography variant="body2" title={String(p.wb_nm_id ?? '—')} noWrap>
                      {p.wb_nm_id ?? '—'}
                    </Typography>
                    {p.wb_primary_barcode || p.wb_barcodes[0] ? (
                      <Typography
                        variant="caption"
                        color="text.secondary"
                        title={p.wb_primary_barcode ?? p.wb_barcodes[0]}
                        noWrap
                      >
                        ШК {p.wb_primary_barcode ?? p.wb_barcodes[0]}
                      </Typography>
                    ) : null}
                  </Stack>
                </TableCell>
                <TableCell align="right">
                  <Stack spacing={0.15} sx={{ minWidth: 0, alignItems: 'flex-end' }}>
                    <Typography
                      variant="caption"
                      data-testid="seller-stock-in-storage"
                      title={`В ячейках ${p.stock_in_storage}`}
                      noWrap
                    >
                      В ячейках {p.stock_in_storage}
                    </Typography>
                    <Typography
                      variant="caption"
                      color="text.secondary"
                      data-testid="seller-stock-on-hand"
                      title={`На ФФ ${p.stock_on_hand}`}
                      noWrap
                    >
                      На ФФ {p.stock_on_hand}
                    </Typography>
                    <Typography
                      variant="caption"
                      color="text.secondary"
                      data-testid="seller-stock-free-fbo"
                      title={`Свободный FBO ${p.stock_free_fbo}`}
                      noWrap
                    >
                      Свободный FBO {p.stock_free_fbo}
                    </Typography>
                  </Stack>
                </TableCell>
                <TableCell
                  data-testid={`seller-stock-distribution-${p.id}`}
                  sx={{ minWidth: 0 }}
                >
                  <Stack spacing={0.25} sx={{ minWidth: 0 }}>
                    <Typography variant="body2" noWrap>
                      FBS {p.stock_fbs} шт
                    </Typography>
                    <Typography variant="caption" color="text.secondary" noWrap>
                      резервы {p.stock_reserved_directions} шт
                    </Typography>
                    <Button
                      size="small"
                      variant="outlined"
                      aria-label="Настроить FBS-пул"
                      title="Настроить FBS-пул"
                      sx={{ alignSelf: 'flex-start', width: 44, minWidth: 44, px: 0 }}
                      onClick={() => void openDirections(p.id)}
                      data-testid={`seller-stock-directions-toggle-${p.id}`}
                    >
                      Пул
                    </Button>
                  </Stack>
                </TableCell>
                <TableCell data-testid={`seller-fbs-cell-${p.id}`} sx={{ minWidth: 0 }}>
                  {(() => {
                    const publication = fbsPublicationState(p)
                    return (
                      <FormControlLabel
                        sx={{
                          m: 0,
                          maxWidth: '100%',
                          minWidth: 0,
                          alignItems: 'center',
                          '& .MuiFormControlLabel-label': { minWidth: 0 },
                        }}
                        control={
                          <Switch
                            size="small"
                            checked={publication.canToggle && p.fbs_stock_sync_enabled}
                            disabled={
                              fbsPending.has(p.id) || fbsBulkBusy || !publication.canToggle
                            }
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
                          <Typography
                            variant="caption"
                            color={publication.color}
                            data-testid={`seller-fbs-status-${p.id}`}
                            sx={{
                              display: '-webkit-box',
                              WebkitLineClamp: 2,
                              WebkitBoxOrient: 'vertical',
                              overflow: 'hidden',
                              maxWidth: '100%',
                            }}
                          >
                            {publication.label}
                          </Typography>
                        }
                      />
                    )
                  })()}
                </TableCell>
                <TableCell sx={{ minWidth: 0 }}>
                  <Stack spacing={0.25} sx={{ alignItems: 'flex-start', minWidth: 0 }}>
                    <Typography
                      variant="caption"
                      color={p.has_packaging_instructions ? 'text.primary' : 'text.secondary'}
                      data-testid={`seller-packaging-status-${p.id}`}
                      noWrap
                    >
                      {p.has_packaging_instructions ? 'ТЗ есть' : 'Без ТЗ'}
                    </Typography>
                    {p.requires_honest_sign ? (
                      <Chip
                        size="small"
                        label="ЧЗ"
                        color="info"
                        variant="outlined"
                        data-testid={`seller-honest-sign-status-${p.id}`}
                      />
                    ) : (
                      <Typography variant="caption" color="text.secondary" noWrap>
                        ЧЗ нет
                      </Typography>
                    )}
                    <Button
                      size="small"
                      variant="outlined"
                      onClick={() => openPackagingEdit(p)}
                      data-testid={`seller-packaging-edit-${p.id}`}
                      aria-label="Редактировать ТЗ"
                      title="Редактировать ТЗ"
                      sx={{ width: 36, minWidth: 36, px: 0 }}
                    >
                      ТЗ
                    </Button>
                  </Stack>
                </TableCell>
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

      <Drawer
        anchor="right"
        open={directionProduct != null}
        onClose={closeDirections}
        slotProps={{
          paper: { sx: { width: { xs: '100%', sm: 500 }, maxWidth: '100%' } },
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
                  FBS-пул не выделен. Сначала добавьте направление с галкой FBS.
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
                      </Box>
                      <Stack direction="row" spacing={0.5} sx={{ flexShrink: 0 }}>
                        <Button
                          size="small"
                          disabled={directionBusy.has(directionProduct.id)}
                          onClick={() => startDirectionEdit(directionProduct.id, direction)}
                          data-testid={`seller-stock-direction-edit-${direction.id}`}
                        >
                          Редактировать
                        </Button>
                        <Button
                          size="small"
                          color="warning"
                          disabled={directionBusy.has(directionProduct.id)}
                          onClick={() => requestDeleteDirection(directionProduct.id, direction)}
                          data-testid={`seller-stock-direction-delete-${direction.id}`}
                        >
                          Удалить
                        </Button>
                      </Stack>
                    </Stack>
                  </Paper>
                ))}
              </Stack>
              <Divider />
              <Stack spacing={1.25}>
                <Typography variant="subtitle2" sx={{ fontWeight: 600 }}>
                  {editingDirectionId ? 'Редактировать направление' : 'Новое направление'}
                </Typography>
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
                  multiline
                  minRows={2}
                  maxRows={3}
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
                    onClick={() => void submitDirection(directionProduct.id)}
                    data-testid={`seller-stock-direction-submit-${directionProduct.id}`}
                  >
                    {editingDirectionId ? 'Сохранить' : 'Добавить'}
                  </Button>
                  {editingDirectionId ? (
                    <Button
                      disabled={directionBusy.has(directionProduct.id)}
                      onClick={() => cancelDirectionEdit(directionProduct.id)}
                      data-testid={`seller-stock-direction-cancel-edit-${directionProduct.id}`}
                    >
                      Отмена
                    </Button>
                  ) : null}
                  <Button onClick={closeDirections}>Закрыть</Button>
                  {directionBusy.has(directionProduct.id) ? <CircularProgress size={18} /> : null}
                </Stack>
              </Stack>
            </Stack>
          </Box>
        ) : null}
      </Drawer>

      <Dialog
        open={deleteTarget != null}
        onClose={() => {
          if (!deleteBusy) setDeleteTarget(null)
        }}
        fullWidth
        maxWidth="xs"
        data-testid="seller-stock-direction-delete-dialog"
      >
        <DialogTitle>Удалить направление?</DialogTitle>
        <DialogContent>
          {deleteTarget ? (
            <Typography variant="body2" color="text.secondary">
              {deleteTarget.direction.is_fbs
                ? `Направление "${deleteTarget.direction.name}" на ${deleteTarget.direction.quantity} шт будет удалено из FBS-пула.`
                : `Направление "${deleteTarget.direction.name}" на ${deleteTarget.direction.quantity} шт будет удалено. Эти ${deleteTarget.direction.quantity} шт снова станут свободным FBO-остатком, если не заняты другими операциями.`}
            </Typography>
          ) : null}
        </DialogContent>
        <DialogActions>
          <Button disabled={deleteBusy} onClick={() => setDeleteTarget(null)}>
            Отмена
          </Button>
          <Button
            variant="contained"
            color="warning"
            disabled={deleteBusy}
            onClick={() => void confirmDeleteDirection()}
            data-testid="seller-stock-direction-confirm-delete"
          >
            Удалить
          </Button>
        </DialogActions>
      </Dialog>

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
