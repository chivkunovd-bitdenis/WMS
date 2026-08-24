import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import {
  Alert,
  Badge,
  Box,
  Button,
  Checkbox,
  Chip,
  CircularProgress,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  Divider,
  Drawer,
  FormControl,
  FormControlLabel,
  IconButton,
  InputLabel,
  MenuItem,
  Paper,
  Select,
  Stack,
  Tab,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  Tabs,
  TextField,
  Tooltip,
  Typography,
} from '@mui/material'
import DownloadOutlinedIcon from '@mui/icons-material/DownloadOutlined'
import QrCode2OutlinedIcon from '@mui/icons-material/QrCode2Outlined'
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
import { FfCatalogInboundPackages } from './FfCatalogInboundPackages'

type SellerRow = { id: string; name: string }

type FfCatalogRow = {
  id: string
  seller_id: string | null
  seller_name: string | null
  name: string
  sku_code: string
  wb_nm_id: number | null
  wb_vendor_code: string | null
  wb_subject_name: string | null
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
  marking_available_count?: number
  fbs_stock_sync_enabled?: boolean
  fbs_stock_limit?: number | null
  fbs_published_amount?: number | null
  fbs_sync_status?: string | null
}

// Остаток на ФФ по товару — из /operations/inventory-balances/summary. Тот же
// запрос, которым раньше пользовался селлерский экран (см. CAT-11/CAT-12).
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

function matchesCatalogSearch(
  row: {
    name: string
    wb_vendor_code: string | null
    sku_code: string
    wb_primary_barcode: string | null
    wb_barcodes: string[]
  },
  query: string,
): boolean {
  const needle = query.trim().toLowerCase()
  if (!needle) return true
  const haystack = [row.name, row.wb_vendor_code ?? '', row.sku_code, row.wb_primary_barcode ?? '', ...row.wb_barcodes]
    .join(' ')
    .toLowerCase()
  return haystack.includes(needle)
}

type Props = {
  token: string
  authHeaders: (t: string) => Record<string, string>
  sellers: SellerRow[]
  canManageCatalog?: boolean
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
  canManageCatalog = false,
}: Props) {
  const navigate = useNavigate()
  const [searchParams, setSearchParams] = useSearchParams()
  const ozonPrototype = searchParams.get('ozonPrototype') === '1'
  const [ozonMappingOpen, setOzonMappingOpen] = useState(false)
  const [ozonMapping, setOzonMapping] = useState<'unmapped' | 'ambiguous' | 'confirmed'>('unmapped')
  // Ширины колонок ужаты так, чтобы таблица целиком помещалась в контейнер —
  // тогда липкой колонке действий физически некуда сдвигаться, и она
  // не перекрывает соседей вовсе (тот же приём, что и в SellerInboundDraftScreen).
  const tableMinWidth = 1284
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [catalog, setCatalog] = useState<FfCatalogRow[]>([])
  const [packageProducts, setPackageProducts] = useState<FfCatalogRow[]>([])
  const [stock, setStock] = useState<StockSummaryRow[]>([])
  const [dialogSellers, setDialogSellers] = useState<SellerRow[]>(sellers)
  const [createOpen, setCreateOpen] = useState(false)
  const [importOpen, setImportOpen] = useState(false)
  const [importNotice, setImportNotice] = useState<string | null>(null)
  const [fbsLimitProduct, setFbsLimitProduct] = useState<FfCatalogRow | null>(null)
  const [fbsLimitDraft, setFbsLimitDraft] = useState('')
  const [fbsLimitSaving, setFbsLimitSaving] = useState(false)
  const [fbsLimitError, setFbsLimitError] = useState<string | null>(null)
  const fbsLimitAutoOpenedRef = useRef<string | null>(null)
  const [editProduct, setEditProduct] = useState<FfCatalogRow | null>(null)
  const [editText, setEditText] = useState('')
  const [editRequiresHonestSign, setEditRequiresHonestSign] = useState(false)
  const [editBusy, setEditBusy] = useState(false)

  // ── Фильтры над таблицей (CAT-12, часть 2) ──────────────────────────────
  const [filterSearch, setFilterSearch] = useState('')
  const [filterSellerId, setFilterSellerId] = useState('')
  const [filterCategory, setFilterCategory] = useState('')
  const [catalogView, setCatalogView] = useState<'products' | 'packages'>('products')

  // ── FBS-пул: направления остатка (перенесено из SellerProductsStockScreen) ──
  const [directionProductId, setDirectionProductId] = useState<string | null>(null)
  const [directions, setDirections] = useState<Record<string, StockDirectionRow[]>>({})
  const [directionDrafts, setDirectionDrafts] = useState<Record<string, DirectionDraft>>({})
  const [directionBusy, setDirectionBusy] = useState<Set<string>>(new Set())
  const [editingDirectionId, setEditingDirectionId] = useState<string | null>(null)
  const [deleteTarget, setDeleteTarget] = useState<DirectionDeleteTarget | null>(null)

  const load = useCallback(async () => {
    setError(null)
    setBusy(true)
    try {
      // seller_id можно передавать бэкенду только с роли фулфилмент-админа —
      // для остальных ролей эндпоинт и так отдаёт каталог по всем селлерам,
      // поэтому для них фильтрация по селлеру остаётся клиентской (см. filteredRows).
      const qs = canManageCatalog && filterSellerId ? `?seller_id=${encodeURIComponent(filterSellerId)}` : ''
      const res = await fetch(apiUrl(`/products/ff-catalog${qs}`), {
        headers: { ...authHeaders(token) },
      })
      if (!res.ok) {
        throw new Error(humanFfCatalogError(await readApiErrorMessage(res)))
      }
      const loadedCatalog = (await res.json()) as FfCatalogRow[]
      setCatalog(loadedCatalog)
      if (!filterSellerId) setPackageProducts(loadedCatalog)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Не удалось загрузить товары.')
    } finally {
      setBusy(false)
    }
  }, [authHeaders, token, canManageCatalog, filterSellerId])

  useEffect(() => {
    void load()
  }, [load])

  const loadStock = useCallback(async () => {
    try {
      const res = await fetch(apiUrl('/operations/inventory-balances/summary'), {
        headers: { ...authHeaders(token) },
      })
      if (!res.ok) {
        setError(humanFfCatalogError(await readApiErrorMessage(res)))
        return
      }
      setStock((await res.json()) as StockSummaryRow[])
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Не удалось загрузить остатки.')
    }
  }, [authHeaders, token])

  useEffect(() => {
    void loadStock()
  }, [loadStock])

  const refreshAll = useCallback(async () => {
    await Promise.all([load(), loadStock()])
  }, [load, loadStock])

  const openFbsLimitDialog = useCallback((product: FfCatalogRow) => {
    setFbsLimitProduct(product)
    setFbsLimitDraft(product.fbs_stock_limit != null ? String(product.fbs_stock_limit) : '')
    setFbsLimitError(null)
  }, [])

  const closeFbsLimitDialog = useCallback(() => {
    if (fbsLimitSaving) return
    setFbsLimitProduct(null)
    setFbsLimitError(null)
  }, [fbsLimitSaving])

  const saveFbsLimit = useCallback(async () => {
    if (!fbsLimitProduct) return
    const trimmed = fbsLimitDraft.trim()
    let limitValue: number | null = null
    if (trimmed) {
      const parsed = Number(trimmed)
      if (!Number.isInteger(parsed) || parsed < 0) {
        setFbsLimitError('Введите целое число не меньше 0 или оставьте поле пустым.')
        return
      }
      limitValue = parsed
    }
    setFbsLimitSaving(true)
    setFbsLimitError(null)
    try {
      const res = await fetch(apiUrl(`/products/${fbsLimitProduct.id}/fbs-stock-sync`), {
        method: 'PATCH',
        headers: { ...authHeaders(token), 'Content-Type': 'application/json' },
        body: JSON.stringify({ fbs_stock_limit: limitValue }),
      })
      if (!res.ok) {
        throw new Error(humanFfCatalogError(await readApiErrorMessage(res)))
      }
      setImportNotice(
        limitValue != null
          ? `Остаток FBS для «${fbsLimitProduct.sku_code}» обновлён: ${limitValue} шт.`
          : `Остаток FBS для «${fbsLimitProduct.sku_code}» сброшен.`,
      )
      setFbsLimitProduct(null)
      await load()
    } catch (e) {
      setFbsLimitError(e instanceof Error ? e.message : 'Не удалось сохранить остаток FBS.')
    } finally {
      setFbsLimitSaving(false)
    }
  }, [authHeaders, fbsLimitDraft, fbsLimitProduct, load, token])

  useEffect(() => {
    const targetId = searchParams.get('fbs_limit')
    if (!targetId || catalog.length === 0) return
    if (fbsLimitAutoOpenedRef.current === targetId) return
    const match = catalog.find((p) => p.id === targetId)
    if (match) {
      openFbsLimitDialog(match)
    }
    fbsLimitAutoOpenedRef.current = targetId
    const next = new URLSearchParams(searchParams)
    next.delete('fbs_limit')
    setSearchParams(next, { replace: true })
  }, [catalog, openFbsLimitDialog, searchParams, setSearchParams])

  useEffect(() => {
    if (sellers.length > 0) {
      setDialogSellers(sellers)
    }
  }, [sellers])

  const loadDialogSellers = useCallback(async (): Promise<SellerRow[]> => {
    if (!canManageCatalog) return []
    try {
      const res = await fetch(apiUrl('/sellers'), {
        headers: { ...authHeaders(token) },
      })
      if (!res.ok) {
        throw new Error(humanFfCatalogError(await readApiErrorMessage(res)))
      }
      const rows = (await res.json()) as SellerRow[]
      setDialogSellers(rows)
      return rows
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Не удалось загрузить селлеров.')
      return []
    }
  }, [authHeaders, canManageCatalog, token])

  useEffect(() => {
    void loadDialogSellers()
  }, [loadDialogSellers])

  const openCreateDialog = useCallback(async () => {
    await loadDialogSellers()
    setCreateOpen(true)
  }, [loadDialogSellers])

  const openImportDialog = useCallback(async () => {
    await loadDialogSellers()
    setImportOpen(true)
  }, [loadDialogSellers])

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

  // ── Остаток / резервы — перенесено из SellerProductsStockScreen
  // (было там до задачи CAT-11, теперь живёт здесь — в каталоге фулфилмента).

  const rows = useMemo(() => {
    const byProduct = new Map(stock.map((s) => [s.product_id, s]))
    return catalog.map((p) => {
      const bal = byProduct.get(p.id)
      return {
        ...p,
        stock_on_hand: bal?.quantity ?? 0,
        stock_in_storage: bal?.quantity_in_storage ?? 0,
        stock_fbs: bal?.quantity_fbs ?? 0,
        stock_reserved_directions: bal?.quantity_reserved_directions ?? 0,
        stock_free_fbo: bal?.quantity_free_fbo ?? bal?.quantity ?? 0,
      }
    })
  }, [catalog, stock])

  const categoryOptions = useMemo(() => {
    const set = new Set<string>()
    for (const row of rows) {
      const value = row.wb_subject_name?.trim()
      if (value) set.add(value)
    }
    return Array.from(set).sort((a, b) => a.localeCompare(b, 'ru'))
  }, [rows])

  const filteredRows = useMemo(
    () =>
      rows.filter(
        (row) =>
          matchesCatalogSearch(row, filterSearch) &&
          (!filterSellerId || row.seller_id === filterSellerId) &&
          (!filterCategory || row.wb_subject_name === filterCategory),
      ),
    [rows, filterSearch, filterSellerId, filterCategory],
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
    (productId: string): DirectionDraft => directionDrafts[productId] ?? emptyDirectionDraft(),
    [directionDrafts],
  )

  const patchDirectionDraft = useCallback((productId: string, patch: Partial<DirectionDraft>) => {
    setDirectionDrafts((current) => {
      const prev = current[productId] ?? emptyDirectionDraft()
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
          setError(humanFfCatalogError(await readApiErrorMessage(res)))
          return
        }
        const body = (await res.json()) as StockDirectionRow[]
        setDirections((current) => ({ ...current, [productId]: body }))
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
      setDirectionDrafts((current) => ({ ...current, [productId]: emptyDirectionDraft() }))
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
    setDirectionDrafts((current) => ({ ...current, [productId]: emptyDirectionDraft() }))
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
          setError(humanFfCatalogError(await readApiErrorMessage(res)))
          return
        }
        setDirectionDrafts((current) => ({ ...current, [productId]: emptyDirectionDraft() }))
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

  const confirmDeleteDirection = useCallback(async () => {
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
        setError(humanFfCatalogError(await readApiErrorMessage(res)))
        return
      }
      setDeleteTarget(null)
      if (editingDirectionId === direction.id) {
        setEditingDirectionId(null)
        setDirectionDrafts((current) => ({ ...current, [productId]: emptyDirectionDraft() }))
      }
      await loadDirections(productId)
      await refreshAll()
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Не удалось удалить направление.')
    } finally {
      markDirectionBusy(productId, false)
    }
  }, [authHeaders, deleteTarget, editingDirectionId, loadDirections, markDirectionBusy, refreshAll, token])

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
          {catalogView === 'products'
            ? 'Карточки товаров селлеров: название, артикулы, ШК, размер, ТЗ упаковки и остаток на ФФ.'
            : 'Сканируйте короб или грузоместо и проверяйте его состав и документ прихода.'}
        </Typography>

        <Tabs
          value={catalogView}
          onChange={(_, value: 'products' | 'packages') => setCatalogView(value)}
          aria-label="Разделы каталога"
          data-testid="ff-catalog-tabs"
          sx={{ mb: 2, borderBottom: '1px solid', borderColor: 'divider' }}
        >
          <Tab
            id="ff-catalog-tab-products"
            aria-controls="ff-catalog-products-panel"
            value="products"
            label="Товары"
            data-testid="ff-catalog-tab-products"
          />
          <Tab
            id="ff-catalog-tab-packages"
            aria-controls="ff-catalog-packages-panel"
            value="packages"
            label="Короба и грузоместа"
            data-testid="ff-catalog-tab-packages"
          />
        </Tabs>

        <Box
          id="ff-catalog-products-panel"
          role="tabpanel"
          aria-labelledby="ff-catalog-tab-products"
          hidden={catalogView !== 'products'}
          data-testid="ff-catalog-products-panel"
        >

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

        {/* GLOBAL-02: две кнопки не нуждаются в отдельной карточке во всю ширину —
            рамка вокруг пустоты только раздувает экран. Действия идут прямо над таблицей. */}
        <Stack
          direction={{ xs: 'column', sm: 'row' }}
          spacing={1}
          sx={{ mb: 2, maxWidth: '100%', justifyContent: 'flex-end', alignItems: { sm: 'center' } }}
          data-testid="ff-products-actions"
        >
          {busy ? <CircularProgress size={18} data-testid="ff-products-loading" /> : null}
          {canManageCatalog ? (
            <>
              <Button
                variant="contained"
                startIcon={<DownloadOutlinedIcon />}
                onClick={() => void openImportDialog()}
                data-testid="ff-products-import-tz"
              >
                Загрузить Excel
              </Button>
              <Button
                variant="outlined"
                onClick={() => void openCreateDialog()}
                data-testid="ff-products-create"
              >
                Создать товар
              </Button>
            </>
          ) : null}
          {ozonPrototype ? <Button variant="outlined" onClick={() => setOzonMappingOpen(true)} data-testid="ozon-catalog-mapping-action">Ozon: {ozonMapping === 'confirmed' ? 'связь подтверждена' : 'проверить связь'}</Button> : null}
        </Stack>

        <Paper variant="outlined" sx={{ p: 2, mb: 2 }} data-testid="ff-catalog-filters">
          <Stack
            direction={{ xs: 'column', sm: 'row' }}
            spacing={2}
            sx={{ alignItems: { sm: 'center' }, flexWrap: 'wrap', rowGap: 2 }}
          >
            <TextField
              size="small"
              placeholder="Поиск по названию, артикулу, SKU или ШК"
              value={filterSearch}
              onChange={(e) => setFilterSearch(e.target.value)}
              slotProps={{ htmlInput: { 'data-testid': 'ff-catalog-search' } }}
              sx={{ minWidth: 260 }}
            />
            <FormControl size="small" sx={{ minWidth: 200 }}>
              <InputLabel id="ff-catalog-seller-filter-label">Селлер</InputLabel>
              <Select
                labelId="ff-catalog-seller-filter-label"
                label="Селлер"
                value={filterSellerId}
                onChange={(e) => setFilterSellerId(e.target.value)}
                data-testid="ff-catalog-seller-filter"
              >
                <MenuItem value="">Все селлеры</MenuItem>
                {sellers.map((s) => (
                  <MenuItem key={s.id} value={s.id}>
                    {s.name}
                  </MenuItem>
                ))}
              </Select>
            </FormControl>
            <FormControl size="small" sx={{ minWidth: 200 }}>
              <InputLabel id="ff-catalog-category-filter-label">Категория</InputLabel>
              <Select
                labelId="ff-catalog-category-filter-label"
                label="Категория"
                value={filterCategory}
                onChange={(e) => setFilterCategory(e.target.value)}
                data-testid="ff-catalog-category-filter"
              >
                <MenuItem value="">Все категории</MenuItem>
                {categoryOptions.map((c) => (
                  <MenuItem key={c} value={c}>
                    {c}
                  </MenuItem>
                ))}
              </Select>
            </FormControl>
            <Typography variant="body2" color="text.secondary" data-testid="ff-catalog-filter-count">
              Найдено: {filteredRows.length} из {rows.length}
            </Typography>
          </Stack>
        </Paper>

        <TableContainer
          component={Paper}
          variant="outlined"
          sx={{ width: '100%', maxWidth: '100%', minWidth: 0, overflowX: 'auto' }}
          data-testid="ff-products-list"
        >
          <Table
            stickyHeader
            size="small"
            data-testid="ff-products-table"
            sx={{
              minWidth: tableMinWidth,
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
              <col style={{ width: 56 }} />
              <col style={{ width: 200 }} />
              <col style={{ width: 130 }} />
              <col style={{ width: 118 }} />
              <col style={{ width: 130 }} />
              <col style={{ width: 64 }} />
              <col style={{ width: 110 }} />
              <col style={{ width: 130 }} />
              <col style={{ width: 70 }} />
              <col style={{ width: 70 }} />
              <col style={{ width: 110 }} />
              <col style={{ width: 96 }} />
            </colgroup>
            <TableHead>
              <TableRow>
                <TableCell>Фото</TableCell>
                <TableCell>Название</TableCell>
                <TableCell>Артикул продавца</TableCell>
                <TableCell>SKU</TableCell>
                <TableCell>ШК</TableCell>
                <TableCell>Размер</TableCell>
                <TableCell>Селлер</TableCell>
                <TableCell align="right">Остаток</TableCell>
                <TableCell>ТЗ</TableCell>
                <TableCell>ЧЗ</TableCell>
                <TableCell>Резервы</TableCell>
                <TableCell
                  align="center"
                  sx={{
                    position: 'sticky',
                    right: 0,
                    zIndex: 3,
                    bgcolor: 'background.paper',
                    borderLeft: '1px solid',
                    borderLeftColor: 'divider',
                  }}
                />
              </TableRow>
            </TableHead>
            <TableBody>
              {filteredRows.map((p) => {
                const displayMeta = catalogRowToDisplayMeta(p)
                const barcode = resolveProductPrimaryBarcode(displayMeta)
                const markingCount = p.marking_available_count ?? 0
                return (
                  <TableRow key={p.id} hover data-testid="ff-product-row">
                    <TableCell>
                      <ProductPhotoThumb src={p.wb_primary_image_url} />
                    </TableCell>
                    <TableCell>
                      <Typography
                        component="span"
                        variant="body2"
                        title={p.name}
                        sx={{
                          minWidth: 0,
                          display: '-webkit-box',
                          WebkitBoxOrient: 'vertical',
                          WebkitLineClamp: 2,
                          overflow: 'hidden',
                          lineHeight: 1.25,
                        }}
                      >
                        {p.name}
                      </Typography>
                    </TableCell>
                    <TableCell>
                      <Typography variant="body2" sx={{ wordBreak: 'break-word' }}>
                        {p.wb_vendor_code ?? '—'}
                      </Typography>
                    </TableCell>
                    <TableCell>
                      <Typography variant="body2" sx={{ fontWeight: 600, wordBreak: 'break-word' }}>
                        {p.sku_code}
                      </Typography>
                    </TableCell>
                    <TableCell>
        <Box
                        sx={{
                          minWidth: 0,
                          maxWidth: '100%',
                          '& [data-testid^="ff-catalog-barcode-"]': { maxWidth: '100%' },
                        }}
                      >
                        <ProductBarcodeCell
                          barcode={barcode || null}
                          wb_size={null}
                          wb_composition={null}
                          testId={`ff-catalog-barcode-${p.id}`}
                        />
                      </Box>
                    </TableCell>
                    <TableCell>
                      <Typography variant="body2" noWrap>
                        {p.wb_size ?? '—'}
                      </Typography>
                    </TableCell>
                    <TableCell>
                      <Typography
                        variant="body2"
                        sx={{ wordBreak: 'break-word' }}
                      >
                        {p.seller_name ?? '—'}
                      </Typography>
                    </TableCell>
                    <TableCell align="right">
                      <Stack spacing={0.15} sx={{ minWidth: 0, alignItems: 'flex-end' }}>
                        <Typography
                          variant="caption"
                          data-testid={`ff-catalog-stock-in-storage-${p.id}`}
                          title={`В ячейках ${p.stock_in_storage}`}
                          noWrap
                        >
                          В ячейках {p.stock_in_storage}
                        </Typography>
                        <Typography
                          variant="caption"
                          color="text.secondary"
                          data-testid={`ff-catalog-stock-on-hand-${p.id}`}
                          title={`На ФФ ${p.stock_on_hand}`}
                          noWrap
                        >
                          На ФФ {p.stock_on_hand}
                        </Typography>
                        <Typography
                          variant="caption"
                          color="text.secondary"
                          data-testid={`ff-catalog-stock-free-fbo-${p.id}`}
                          title={`Свободный FBO ${p.stock_free_fbo}`}
                          noWrap
                        >
                          Свободный FBO {p.stock_free_fbo}
                        </Typography>
                      </Stack>
                    </TableCell>
                    <TableCell sx={{ minWidth: 0 }}>
                      <Button
                        size="small"
                        variant={p.has_packaging_instructions ? 'contained' : 'outlined'}
                        color={p.has_packaging_instructions ? 'primary' : 'inherit'}
                        onClick={() => openPackagingEdit(p)}
                        disabled={!canManageCatalog}
                        data-testid={`ff-packaging-edit-${p.id}`}
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
                          data-testid={`ff-honest-sign-status-${p.id}`}
                        />
                      ) : null}
                    </TableCell>
                    <TableCell data-testid={`ff-catalog-reserves-cell-${p.id}`} sx={{ minWidth: 0 }}>
                      <Button
                        size="small"
                        variant="outlined"
                        onClick={() => void openDirections(p.id)}
                        data-testid={`ff-catalog-reserves-${p.id}`}
                      >
                        Резервы
                      </Button>
                    </TableCell>
                    <TableCell
                      align="center"
                      sx={{
                        position: 'sticky',
                        right: 0,
                        zIndex: 1,
                        bgcolor: 'background.paper',
                        borderLeft: '1px solid',
                        borderLeftColor: 'divider',
                      }}
                    >
                      <Stack direction="row" spacing={0.25} sx={{ justifyContent: 'center' }}>
                        <Tooltip
                          title={`Коды маркировки: ${markingCount}`}
                        >
                          <span>
                            <IconButton
                              size="small"
                              aria-label={`Коды маркировки ${p.sku_code}: ${markingCount}`}
                              data-testid={`ff-catalog-marking-link-${p.id}`}
                              disabled={!canManageCatalog}
                              onClick={() => navigate(`/app/ff/honest-sign/product/${p.id}`)}
                            >
                              <Badge
                                badgeContent={markingCount}
                                color="warning"
                                invisible={markingCount <= 0}
                                overlap="circular"
                              >
                                <QrCode2OutlinedIcon
                                  fontSize="small"
                                  color={markingCount > 0 ? 'warning' : 'disabled'}
                                />
                              </Badge>
                            </IconButton>
                          </span>
                        </Tooltip>
                        <ProductBarcodePrintButton
                          meta={displayMeta}
                          testId={`ff-catalog-print-${p.id}`}
                          productId={p.id}
                          requiresHonestSign={p.requires_honest_sign}
                          markingAvailable={markingCount}
                        />
                        <Tooltip
                          title={
                            p.fbs_stock_limit != null
                              ? `Остаток FBS: ${p.fbs_stock_limit} шт`
                              : 'Остаток FBS не задан'
                          }
                        >
                          <span>
                            <IconButton
                              size="small"
                              aria-label={`Остаток FBS ${p.sku_code}`}
                              data-testid={`ff-catalog-fbs-limit-${p.id}`}
                              disabled={!canManageCatalog}
                              onClick={() => openFbsLimitDialog(p)}
                            >
                              <Inventory2OutlinedIcon
                                fontSize="small"
                                color={p.fbs_stock_limit != null ? 'primary' : 'disabled'}
                              />
                            </IconButton>
                          </span>
                        </Tooltip>
                      </Stack>
                    </TableCell>
                  </TableRow>
                )
              })}
              {filteredRows.length === 0 && !busy ? (
                <TableRow>
                  <TableCell colSpan={12}>
                    {rows.length === 0 ? (
                      canManageCatalog ? (
                        <Typography variant="body2" color="text.secondary" data-testid="ff-products-empty">
                          В каталоге пока нет товаров. Скачайте шаблон, загрузите Excel или создайте
                          один товар вручную.
                        </Typography>
                      ) : (
                        <Typography variant="body2" color="text.secondary" data-testid="ff-products-empty">
                          В каталоге пока нет товаров.
                        </Typography>
                      )
                    ) : (
                      <Typography variant="body2" color="text.secondary" data-testid="ff-products-empty">
                        Ничего не найдено.
                      </Typography>
                    )}
                  </TableCell>
                </TableRow>
              ) : null}
            </TableBody>
          </Table>
        </TableContainer>

        </Box>

        {catalogView === 'packages' ? (
          <Box id="ff-catalog-packages-panel" role="tabpanel" aria-labelledby="ff-catalog-tab-packages">
            <FfCatalogInboundPackages
              token={token}
              authHeaders={authHeaders}
              products={packageProducts}
            />
          </Box>
        ) : null}

        {canManageCatalog ? (
          <>
            <FfManualProductCreateDialog
              open={createOpen}
              token={token}
              authHeaders={authHeaders}
              sellers={dialogSellers}
              onClose={() => setCreateOpen(false)}
              onCreated={async () => {
                setImportNotice('Товар создан.')
                await load()
              }}
            />
            <FfProductTzImportDialog
              open={importOpen}
              token={token}
              sellers={dialogSellers}
              onClose={() => setImportOpen(false)}
              onApplied={async (message) => {
                setImportNotice(message)
                await load()
              }}
            />
          </>
        ) : null}

        <Dialog
          open={fbsLimitProduct != null}
          onClose={closeFbsLimitDialog}
          maxWidth="xs"
          fullWidth
          data-testid="ff-catalog-fbs-limit-dialog"
        >

        {ozonPrototype ? <Alert severity="info" sx={{ mb: 2 }} data-testid="ozon-catalog-inline-summary">Loviana · Ozon mappings загружены локально: offer_id / product_id / SKU проверяются только в диалоге действия; новая колонка и вкладка не добавлены.</Alert> : null}
          <DialogTitle>Остаток FBS</DialogTitle>
          <DialogContent>
            {fbsLimitProduct ? (
              <Stack spacing={2} sx={{ pt: 1 }}>
                <Typography variant="body2" color="text.secondary">
                  {fbsLimitProduct.sku_code} · {fbsLimitProduct.name}
                </Typography>
                <Typography variant="body2" color="text.secondary">
                  Максимальное количество этого товара, доступное для продажи по FBS. От
                  этого числа делится остаток по складам WB на экране «Остатки WB».
                </Typography>
                {fbsLimitError ? (
                  <Alert severity="error" data-testid="ff-catalog-fbs-limit-error">
                    {fbsLimitError}
                  </Alert>
                ) : null}
                <TextField
                  label="Остаток FBS (шт)"
                  type="number"
                  value={fbsLimitDraft}
                  onChange={(e) => setFbsLimitDraft(e.target.value)}
                  placeholder="Не задан"
                  slotProps={{ htmlInput: { min: 0, 'data-testid': 'ff-catalog-fbs-limit-input' } }}
                  fullWidth
                  disabled={fbsLimitSaving}
                />
              </Stack>
            ) : null}
          </DialogContent>
          <DialogActions>
            <Button onClick={closeFbsLimitDialog} disabled={fbsLimitSaving}>
              Отмена
            </Button>
            <Button
              variant="contained"
              onClick={() => void saveFbsLimit()}
              disabled={fbsLimitSaving}
              data-testid="ff-catalog-fbs-limit-save"
            >
              {fbsLimitSaving ? 'Сохраняем…' : 'Сохранить'}
            </Button>
          </DialogActions>
        </Dialog>

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

        <Drawer
          anchor="right"
          open={directionProduct != null}
          onClose={closeDirections}
          slotProps={{
            paper: { sx: { width: { xs: '100%', sm: 500 }, maxWidth: '100%' } },
          }}
          data-testid={
            directionProduct ? `ff-stock-directions-panel-${directionProduct.id}` : undefined
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
                      data-testid={`ff-stock-direction-row-${direction.id}`}
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
                            data-testid={`ff-stock-direction-edit-${direction.id}`}
                          >
                            Редактировать
                          </Button>
                          <Button
                            size="small"
                            color="warning"
                            disabled={directionBusy.has(directionProduct.id)}
                            onClick={() => requestDeleteDirection(directionProduct.id, direction)}
                            data-testid={`ff-stock-direction-delete-${direction.id}`}
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
                      htmlInput: { 'data-testid': `ff-stock-direction-name-${directionProduct.id}` },
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
                        'data-testid': `ff-stock-direction-quantity-${directionProduct.id}`,
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
                        'data-testid': `ff-stock-direction-comment-${directionProduct.id}`,
                      },
                    }}
                  />
                  <Stack direction="row" spacing={1} sx={{ alignItems: 'center' }}>
                    <Button
                      variant="contained"
                      disabled={directionBusy.has(directionProduct.id)}
                      onClick={() => void submitDirection(directionProduct.id)}
                      data-testid={`ff-stock-direction-submit-${directionProduct.id}`}
                    >
                      {editingDirectionId ? 'Сохранить' : 'Добавить'}
                    </Button>
                    {editingDirectionId ? (
                      <Button
                        disabled={directionBusy.has(directionProduct.id)}
                        onClick={() => cancelDirectionEdit(directionProduct.id)}
                        data-testid={`ff-stock-direction-cancel-edit-${directionProduct.id}`}
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
          data-testid="ff-stock-direction-delete-dialog"
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
              data-testid="ff-stock-direction-confirm-delete"
            >
              Удалить
            </Button>
          </DialogActions>
        </Dialog>
      </Box>
      <Dialog open={ozonMappingOpen} onClose={() => setOzonMappingOpen(false)} maxWidth="sm" fullWidth><DialogTitle>Сопоставление Ozon · Loviana</DialogTitle><DialogContent><Stack spacing={1.5} sx={{ pt: 1 }}><Typography>Платье Margo · WMS SKU-204</Typography><Paper variant="outlined" sx={{ p: 1.5 }}><Typography variant="body2"><b>Кандидат 1</b> · offer_id OFFER-MARGO · product_id 2201 · SKU MARGO-42 · ШК 4601234567890</Typography><Typography variant="caption">Причина: точный уникальный seller SKU</Typography></Paper><Paper variant="outlined" sx={{ p: 1.5 }}><Typography variant="body2"><b>Кандидат 2</b> · ШК совпал, account Fashion</Typography><Typography variant="caption" color="error">Конфликт: barcode неоднозначен между account; auto-link запрещён.</Typography></Paper>{ozonMapping === 'ambiguous' ? <Alert severity="warning">Неоднозначный кандидат отклонён. Выберите точный offer/SKU.</Alert> : null}{ozonMapping === 'confirmed' ? <Alert severity="success">Связь Ozon Loviana подтверждена; WB-связь и WMS SKU не изменены.</Alert> : null}</Stack></DialogContent><DialogActions><Button onClick={() => setOzonMapping('ambiguous')}>Отклонить конфликт</Button><Button variant="contained" onClick={() => setOzonMapping('confirmed')}>Подтвердить точный offer/SKU</Button><Button onClick={() => setOzonMappingOpen(false)}>Закрыть</Button></DialogActions></Dialog>
    </FfProductMarkingPrintProvider>
  )
}
