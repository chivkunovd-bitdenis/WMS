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
  TablePagination,
  TableRow,
  Tabs,
  TextField,
  Tooltip,
  Typography,
} from '@mui/material'
import DownloadOutlinedIcon from '@mui/icons-material/DownloadOutlined'
import QrCode2OutlinedIcon from '@mui/icons-material/QrCode2Outlined'
import TuneOutlined from '@mui/icons-material/TuneOutlined'
import { apiUrl } from '../../api'
import { FbsStockDialog } from '../ff/products-fbs/FbsStockDialog'
import {
  toProduct as toFbsProduct,
  toRule as toFbsRule,
  type ApiRule as FbsApiRule,
} from '../ff/products-fbs/FfProductsFbsPage'
import type {
  FbsRule as FbsRuleModel,
  Product as FbsProduct,
  Seller as FbsSeller,
} from '../ff/products-fbs/stub'
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
import { MarketplaceChip } from '../../ui-kit'

type SellerRow = { id: string; name: string }
type WarehouseRow = { id: string; name: string; code: string; is_operational: boolean }

function isTechnicalFbsWarehouse(warehouse: WarehouseRow): boolean {
  return warehouse.code.startsWith('fbs-wb-') || warehouse.name.startsWith('FBS WB ')
}

type FfCatalogRow = {
  id: string
  seller_id: string | null
  seller_name: string | null
  name: string
  sku_code: string
  wb_nm_id: number | null
  wb_vendor_code: string | null
  ozon_sku?: string | null
  ozon_offer_id?: string | null
  wb_subject_name: string | null
  wb_primary_image_url: string | null
  wb_barcodes: string[]
  wb_primary_barcode: string | null
  wb_size: string | null
  wb_color: string | null
  wb_brand: string | null
  wb_composition: string | null
  packaging_instructions: string | null
  country_of_origin_iso_code?: string | null
  requires_honest_sign: boolean
  has_packaging_instructions: boolean
  marking_available_count?: number
  fbs_stock_sync_enabled?: boolean
  fbs_stock_limit?: number | null
  fbs_published_amount?: number | null
  fbs_percent?: number | null
  fbs_same_everywhere?: boolean | null
  fbs_sync_status?: string | null
}

type FfCatalogPage = {
  items: FfCatalogRow[]
  total: number
  scope_total: number
  limit: number
  offset: number
  categories: string[]
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

type Props = {
  token: string
  authHeaders: (t: string) => Record<string, string>
  sellers: SellerRow[]
  warehouses: WarehouseRow[]
  canManageCatalog?: boolean; addressStorageEnabled?: boolean
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

function fbsWarehousesLoadError(status: number, message: string): string {
  const lower = message.toLowerCase()
  if (status === 403 || lower.includes('нет токена') || lower.includes('missing_marketplace_token')) {
    return 'Backend не нашёл ключ, пригодный для Marketplace. Если ключ WB уже сохранён, проверьте его права Marketplace в карточке селлера.'
  }
  if (status === 401 || status === 502) {
    return 'Wildberries отклонил сохранённый ключ при загрузке складов. Проверьте права Marketplace у ключа селлера.'
  }
  return `Не удалось загрузить склады Wildberries: ${message}`
}

export function FfProductsCatalogScreen({
  token,
  authHeaders,
  sellers,
  warehouses,
  canManageCatalog = false, addressStorageEnabled = true,
}: Props) {
  const navigate = useNavigate()
  const [searchParams, setSearchParams] = useSearchParams()
  // Сумма всех четырнадцати колонок из colgroup ниже. Держать в согласии с ним:
  // при tableLayout: 'fixed' колонка без своей ширины забирает весь свободный
  // простор на широком экране и схлопывается в ноль на узком. Контейнер каталога
  // уже колонок (на 1440 — 1130px), таблица прокручивается вбок, поэтому колонка
  // действий липкая справа и из виду не уходит.
  const tableMinWidth = 1488
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [catalog, setCatalog] = useState<FfCatalogRow[]>([])
  const [catalogTotal, setCatalogTotal] = useState(0)
  const [catalogScopeTotal, setCatalogScopeTotal] = useState(0)
  const [categoryOptions, setCategoryOptions] = useState<string[]>([])
  const [packageProducts, setPackageProducts] = useState<FfCatalogRow[]>([])
  const [stock, setStock] = useState<StockSummaryRow[]>([])
  const [dialogSellers, setDialogSellers] = useState<SellerRow[]>(sellers)
  const [createOpen, setCreateOpen] = useState(false)
  const [importOpen, setImportOpen] = useState(false)
  const [importNotice, setImportNotice] = useState<string | null>(null)
  const fbsLimitAutoOpenedRef = useRef<string | null>(null)
  const [editProduct, setEditProduct] = useState<FfCatalogRow | null>(null)
  const [editText, setEditText] = useState('')
  const [editRequiresHonestSign, setEditRequiresHonestSign] = useState(false)
  const [editCountryIso, setEditCountryIso] = useState('')
  const [editOzonSku, setEditOzonSku] = useState('')
  const [editOzonOfferId, setEditOzonOfferId] = useState('')
  const [editOzonError, setEditOzonError] = useState<string | null>(null)
  const [editBusy, setEditBusy] = useState(false)

  // ── Массовая простановка остатка FBS по фактическому остатку на складе ──
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set())
  // Модалка «Задать остаток» — та же, что была на отдельном экране остатков FBS.
  // Владелец просил, чтобы настройка жила в каталоге, а не отдельным разделом.
  const [fbsDialog, setFbsDialog] = useState<{
    products: FbsProduct[]
    seller: FbsSeller
    rule: FbsRuleModel
  } | null>(null)
  const [fbsDialogError, setFbsDialogError] = useState<string | null>(null)

  // ── Фильтры над таблицей (CAT-12, часть 2) ──────────────────────────────
  const [filterSearch, setFilterSearch] = useState('')
  const [debouncedSearch, setDebouncedSearch] = useState('')
  const [filterSellerId, setFilterSellerId] = useState('')
  const [filterMarketplace, setFilterMarketplace] = useState<'wildberries' | 'ozon' | ''>('')
  const [filterCategory, setFilterCategory] = useState('')
  const [page, setPage] = useState(0)
  const [rowsPerPage, setRowsPerPage] = useState(100)
  const [catalogView, setCatalogView] = useState<'products' | 'packages'>('products')
  const catalogAbortRef = useRef<AbortController | null>(null)
  const packageAbortRef = useRef<AbortController | null>(null)

  // ── FBS-пул: направления остатка (перенесено из SellerProductsStockScreen) ──
  const [directionProductId, setDirectionProductId] = useState<string | null>(null)
  const [directions, setDirections] = useState<Record<string, StockDirectionRow[]>>({})
  const [directionDrafts, setDirectionDrafts] = useState<Record<string, DirectionDraft>>({})
  const [directionBusy, setDirectionBusy] = useState<Set<string>>(new Set())
  const [editingDirectionId, setEditingDirectionId] = useState<string | null>(null)
  const [deleteTarget, setDeleteTarget] = useState<DirectionDeleteTarget | null>(null)

  useEffect(() => {
    const timeout = window.setTimeout(() => setDebouncedSearch(filterSearch.trim()), 250)
    return () => window.clearTimeout(timeout)
  }, [filterSearch])

  useEffect(() => {
    setPage(0)
  }, [debouncedSearch, filterCategory, filterMarketplace, filterSellerId, rowsPerPage])

  // Выбор строк относится к тому, что видно на текущей странице сейчас —
  // при смене страницы или фильтра он теряет смысл и снимается.
  useEffect(() => {
    setSelectedIds(new Set())
    // Отказ относится к прежнему выделению. Если его не гасить, он остаётся на
    // экране и врёт: фильтр уже сузили до одного продавца, а сообщение всё ещё
    // перечисляет пятерых.
    setFbsDialogError(null)
  }, [page, rowsPerPage, debouncedSearch, filterCategory, filterMarketplace, filterSellerId])

  const load = useCallback(async () => {
    catalogAbortRef.current?.abort()
    const controller = new AbortController()
    catalogAbortRef.current = controller
    setError(null)
    setBusy(true)
    try {
      const params = new URLSearchParams({
        limit: String(rowsPerPage),
        offset: String(page * rowsPerPage),
      })
      if (filterSellerId) params.set('seller_id', filterSellerId)
      if (debouncedSearch) params.set('search', debouncedSearch)
      if (filterCategory) params.set('category', filterCategory)
      if (filterMarketplace) params.set('marketplace', filterMarketplace)
      const res = await fetch(apiUrl(`/products/ff-catalog-page?${params.toString()}`), {
        headers: { ...authHeaders(token) },
        signal: controller.signal,
      })
      if (!res.ok) {
        throw new Error(humanFfCatalogError(await readApiErrorMessage(res)))
      }
      const loadedPage = (await res.json()) as FfCatalogPage
      if (controller.signal.aborted) return

      const stockParams = new URLSearchParams()
      for (const item of loadedPage.items) stockParams.append('product_id', item.id)
      let loadedStock: StockSummaryRow[] = []
      if (loadedPage.items.length > 0) {
        const stockRes = await fetch(
          apiUrl(`/operations/inventory-balances/summary?${stockParams.toString()}`),
          { headers: { ...authHeaders(token) }, signal: controller.signal },
        )
        if (!stockRes.ok) {
          throw new Error(humanFfCatalogError(await readApiErrorMessage(stockRes)))
        }
        loadedStock = (await stockRes.json()) as StockSummaryRow[]
      }
      if (controller.signal.aborted) return
      setCatalog(loadedPage.items)
      setCatalogTotal(loadedPage.total)
      setCatalogScopeTotal(loadedPage.scope_total)
      setCategoryOptions(loadedPage.categories)
      setStock(loadedStock)
    } catch (e) {
      if ((e as { name?: string }).name === 'AbortError') return
      setError(e instanceof Error ? e.message : 'Не удалось загрузить товары.')
    } finally {
      if (catalogAbortRef.current === controller) setBusy(false)
    }
  }, [
    authHeaders,
    debouncedSearch,
    filterCategory,
    filterMarketplace,
    filterSellerId,
    page,
    rowsPerPage,
    token,
  ])

  useEffect(() => {
    void load()
    return () => catalogAbortRef.current?.abort()
  }, [load])

  useEffect(() => {
    if (catalogView !== 'packages' || packageProducts.length > 0) return
    packageAbortRef.current?.abort()
    const controller = new AbortController()
    packageAbortRef.current = controller
    void (async () => {
      try {
        const res = await fetch(apiUrl('/products/ff-catalog'), {
          headers: { ...authHeaders(token) },
          signal: controller.signal,
        })
        if (!res.ok) throw new Error(humanFfCatalogError(await readApiErrorMessage(res)))
        if (!controller.signal.aborted) setPackageProducts((await res.json()) as FfCatalogRow[])
      } catch (e) {
        if ((e as { name?: string }).name !== 'AbortError') {
          setError(e instanceof Error ? e.message : 'Не удалось загрузить товары коробов.')
        }
      }
    })()
    return () => controller.abort()
  }, [authHeaders, catalogView, packageProducts.length, token])

  const refreshAll = useCallback(async () => {
    await load()
  }, [load])


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
    setEditCountryIso(p.country_of_origin_iso_code ?? '')
    setEditOzonSku(p.ozon_sku ?? '')
    setEditOzonOfferId(p.ozon_offer_id ?? '')
    setEditOzonError(null)
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
    setEditOzonError(null)
    try {
      const normalizedOzonSku = editOzonSku.trim()
      const normalizedOzonOfferId = editOzonOfferId.trim()
      const ozonLinkChanged =
        normalizedOzonSku !== (editProduct.ozon_sku ?? '') ||
        normalizedOzonOfferId !== (editProduct.ozon_offer_id ?? '')
      if (ozonLinkChanged) {
        if (!normalizedOzonSku && !normalizedOzonOfferId) {
          setEditOzonError('Укажите SKU или артикул Ozon.')
          return
        }
        const linkRes = await fetch(apiUrl(`/products/${editProduct.id}/ozon-link`), {
          method: 'PATCH',
          headers: { ...authHeaders(token), 'Content-Type': 'application/json' },
          body: JSON.stringify({
            ozon_sku: normalizedOzonSku || null,
            ozon_offer_id: normalizedOzonOfferId || null,
          }),
        })
        if (!linkRes.ok) {
          const raw = await readApiErrorMessage(linkRes)
          setEditOzonError(
            raw === 'ozon_sku_taken'
              ? 'Этот SKU уже привязан к другому товару.'
              : humanFfCatalogError(raw),
          )
          return
        }
      }
      const res = await fetch(apiUrl(`/products/${editProduct.id}/packaging-instructions`), {
        method: 'PATCH',
        headers: { ...authHeaders(token), 'Content-Type': 'application/json' },
        body: JSON.stringify({
          packaging_instructions: editText.trim() || null,
          requires_honest_sign: editRequiresHonestSign,
          country_of_origin_iso_code: editCountryIso.trim().toUpperCase() || null,
        }),
      })
      if (!res.ok) {
        setError(humanFfCatalogError(await readApiErrorMessage(res)))
        return
      }
      if (ozonLinkChanged) {
        setImportNotice(`Привязка Ozon для «${editProduct.sku_code}» сохранена.`)
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

  const filteredRows = rows

  const allVisibleSelected =
    filteredRows.length > 0 && filteredRows.every((r) => selectedIds.has(r.id))
  const someVisibleSelected = filteredRows.some((r) => selectedIds.has(r.id))

  const toggleSelectAllVisible = useCallback(
    (checked: boolean) => {
      setFbsDialogError(null)
      setSelectedIds((current) => {
        const next = new Set(current)
        for (const row of filteredRows) {
          if (checked) next.add(row.id)
          else next.delete(row.id)
        }
        return next
      })
    },
    [filteredRows],
  )

  const toggleRowSelected = useCallback((id: string, checked: boolean) => {
    setFbsDialogError(null)
    setSelectedIds((current) => {
      const next = new Set(current)
      if (checked) next.add(id)
      else next.delete(id)
      return next
    })
  }, [])

  const openFbsStockDialog = useCallback(async (onlyIds?: string[]) => {
    setFbsDialogError(null)
    const pick = onlyIds ? new Set(onlyIds) : selectedIds
    const chosen = rows.filter((r) => pick.has(r.id) && r.seller_id)
    if (chosen.length === 0) {
      setFbsDialogError('Выберите товары с продавцом: без него складов WB нет.')
      return
    }
    const sellerId = chosen[0]!.seller_id as string
    if (chosen.some((r) => r.seller_id !== sellerId)) {
      // Называем селлеров поимённо: иначе оператор, выделивший «всё», не понимает,
      // что именно ему разъединять в списке на сотни строк.
      const names = Array.from(
        new Set(chosen.map((r) => r.seller_name ?? 'без продавца')),
      ).sort()
      setFbsDialogError(
        `Выбраны товары разных продавцов (${names.join(', ')}), а склады Wildberries ` +
          'у каждого свои. Оставьте в выделении одного продавца.',
      )
      return
    }
    try {
      const [rulesRes, whRes, bindingsRes] = await Promise.all([
        fetch(apiUrl('/products/fbs-rule/bulk'), {
          method: 'POST',
          headers: { 'Content-Type': 'application/json', ...authHeaders(token) },
          body: JSON.stringify({ product_ids: chosen.map((r) => r.id) }),
        }),
        fetch(apiUrl(`/operations/fbs-sellers/${sellerId}/warehouses`), {
          headers: { ...authHeaders(token) },
        }),
        fetch(apiUrl(`/operations/fbs-sellers/${sellerId}/warehouse-bindings`), {
          headers: { ...authHeaders(token) },
        }),
      ])
      if (!rulesRes.ok) throw new Error(await readApiErrorMessage(rulesRes))
      const rulesBody = (await rulesRes.json()) as {
        items: Array<FbsApiRule & { product_id: string }>
      }
      const ruleById = new Map(rulesBody.items.map((one) => [one.product_id, one]))
      type SellerWarehouseRow = {
        wb_warehouse_id: number | string
        name: string | null
        wms_warehouse_id: string | null
        served: boolean
      }
      const whRows: SellerWarehouseRow[] = whRes.ok
        ? ((await whRes.json()) as SellerWarehouseRow[])
        : []
      const warehouseLoadError = whRes.ok
        ? null
        : fbsWarehousesLoadError(whRes.status, await readApiErrorMessage(whRes))

      // Если WB временно не отдал список, не прячем уже сохранённые привязки:
      // оператор всё равно должен видеть внешний ID и выбранный WMS-склад.
      if (bindingsRes.ok) {
        const savedBindings = (await bindingsRes.json()) as Array<{
          wb_warehouse_id: number | string
          wms_warehouse_id: string
          is_active: boolean
          stock_sync_enabled: boolean
        }>
        const knownIds = new Set(whRows.map((one) => String(one.wb_warehouse_id)))
        for (const binding of savedBindings) {
          if (knownIds.has(String(binding.wb_warehouse_id))) continue
          whRows.push({
            wb_warehouse_id: binding.wb_warehouse_id,
            name: `Склад WB ${binding.wb_warehouse_id}`,
            wms_warehouse_id: binding.wms_warehouse_id,
            served: binding.is_active && binding.stock_sync_enabled,
          })
        }
      }
      const seller: FbsSeller = {
        id: sellerId,
        name: chosen[0]!.seller_name ?? '—',
        warehouses: whRows.map((one) => ({
          id: String(one.wb_warehouse_id),
          name: one.name ?? `Склад ${one.wb_warehouse_id}`,
          boundTo: one.wms_warehouse_id,
          fbsEnabled: one.served,
        })),
        // Имя поля осталось от старого макета, но Select справа выбирает именно
        // наш физический WMS-склад для WB-направления. Технические fbs-wb-* и
        // выключенные склады сюда не попадают.
        wbWarehouses: warehouses
          .filter((one) => one.is_operational && !isTechnicalFbsWarehouse(one))
          .map((one) => ({ id: one.id, name: one.name })),
      }
      const products: FbsProduct[] = chosen.map((r) =>
        toFbsProduct(
          {
            id: r.id,
            seller_id: r.seller_id,
            name: r.name,
            sku_code: r.sku_code,
            wb_size: r.wb_size,
            wb_primary_barcode: r.wb_primary_barcode,
          },
          ruleById.get(r.id),
          sellerId,
        ),
      )
      const rule: FbsRuleModel = toFbsRule(chosen[0]!.id, ruleById.get(chosen[0]!.id))
      setFbsDialog({ products, seller, rule })
      if (warehouseLoadError) setFbsDialogError(warehouseLoadError)
    } catch (e) {
      setFbsDialogError(e instanceof Error ? e.message : 'Не удалось открыть настройку остатка')
    }
  }, [authHeaders, rows, selectedIds, token, warehouses])

  // Одна ручка на обе настройки склада продавца: сопоставление и «обслуживаем».
  // Сервер принимает их вместе, поэтому при смене одного всегда отправляем и
  // второе — иначе он затрёт то, что мы не прислали.
  const saveFbsWarehouse = useCallback(
    async (
      wbWarehouseId: string,
      next: { served?: boolean; wmsWarehouseId: string | null },
      failureMessage: string,
    ) => {
      if (!fbsDialog) return
      setFbsDialogError(null)
      try {
        const res = await fetch(
          apiUrl(`/fbs-sellers/${fbsDialog.seller.id}/warehouses/${wbWarehouseId}`),
          {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json', ...authHeaders(token) },
            body: JSON.stringify({
              ...(next.served === undefined ? {} : { served: next.served }),
              wms_warehouse_id: next.wmsWarehouseId,
            }),
          },
        )
        if (!res.ok) throw new Error(await readApiErrorMessage(res))
        const saved = (await res.json()) as {
          served: boolean
          wms_warehouse_id: string | null
        }
        setFbsDialog((current) => {
          if (!current) return current
          return {
            ...current,
            seller: {
              ...current.seller,
              warehouses: current.seller.warehouses.map((one) =>
                one.id === wbWarehouseId
                  ? {
                      ...one,
                      boundTo: saved.wms_warehouse_id,
                      fbsEnabled: saved.served,
                    }
                  : one,
              ),
            },
          }
        })
      } catch (e) {
        setFbsDialogError(e instanceof Error ? e.message : failureMessage)
      }
    },
    [authHeaders, fbsDialog, token],
  )

  const bindFbsWarehouse = useCallback(async (wbWarehouseId: string, wmsWarehouseId: string) => {
    if (!fbsDialog) return
    // Пустое значение не превращаем в served=false: иначе обслуживаемое
    // WB-направление исчезнет из dialog и вернуть его отсюда будет невозможно.
    if (!wmsWarehouseId) return
    // Сопоставление и решение обслуживать склад — два разных действия.
    // Поэтому served здесь не отправляем: новая привязка останется выключенной,
    // а существующая сохранит своё текущее состояние. После выбора WMS-склада
    // оператор отдельно включает направление явной галочкой.
    await saveFbsWarehouse(
      wbWarehouseId,
      { wmsWarehouseId },
      'Не удалось сопоставить склад',
    )
  }, [fbsDialog, saveFbsWarehouse])

  const setFbsWarehouseServed = useCallback(async (wbWarehouseId: string, served: boolean) => {
    if (!fbsDialog) return
    const current = fbsDialog.seller.warehouses.find((one) => one.id === wbWarehouseId)
    await saveFbsWarehouse(
      wbWarehouseId,
      { served, wmsWarehouseId: current?.boundTo ?? null },
      served ? 'Не удалось включить склад' : 'Не удалось отключить склад',
    )
  }, [fbsDialog, saveFbsWarehouse])

  // Ссылка ?fbs_limit=<id> ведёт сюда из раскладки остатка по складам WB.
  // Старая модалка абсолютного лимита убрана, ссылка открывает ту же модалку
  // с долей, что и значок в строке. Эффект стоит после openFbsStockDialog:
  // выше он попал бы в мёртвую зону объявления.
  useEffect(() => {
    const targetId = searchParams.get('fbs_limit')
    if (!targetId || catalog.length === 0) return
    if (fbsLimitAutoOpenedRef.current === targetId) return
    if (catalog.some((p) => p.id === targetId)) {
      void openFbsStockDialog([targetId])
    }
    fbsLimitAutoOpenedRef.current = targetId
    const next = new URLSearchParams(searchParams)
    next.delete('fbs_limit')
    setSearchParams(next, { replace: true })
  }, [catalog, openFbsStockDialog, searchParams, setSearchParams])


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
                onChange={(e) => {
                  setFilterSellerId(e.target.value)
                  setFilterCategory('')
                }}
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
            <FormControl size="small" sx={{ minWidth: 170 }}>
              <InputLabel id="ff-catalog-marketplace-filter-label">Маркетплейс</InputLabel>
              <Select
                labelId="ff-catalog-marketplace-filter-label"
                label="Маркетплейс"
                value={filterMarketplace}
                onChange={(e) => setFilterMarketplace(e.target.value as 'wildberries' | 'ozon' | '')}
                data-testid="ff-catalog-marketplace-filter"
              >
                <MenuItem value="">Все</MenuItem>
                <MenuItem value="wildberries">Wildberries</MenuItem>
                <MenuItem value="ozon">Ozon</MenuItem>
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
              {busy ? 'Загрузка…' : `Найдено: ${catalogTotal} из ${catalogScopeTotal}`}
            </Typography>
          </Stack>
        </Paper>


        {selectedIds.size > 0 ? (
          <Paper
            variant="outlined"
            sx={{ p: 2, mb: 2, borderColor: 'primary.main' }}
            data-testid="ff-catalog-selection-bar"
          >
            <Stack
              direction={{ xs: 'column', sm: 'row' }}
              spacing={2}
              sx={{ alignItems: { sm: 'center' }, justifyContent: 'space-between' }}
            >
              <Typography variant="subtitle2" data-testid="ff-catalog-selection-count">
                Выбрано {selectedIds.size}
              </Typography>
              <Stack direction="row" spacing={1} sx={{ flexWrap: 'wrap' }}>
                {/* Как на согласованном макете: кнопка открывает настройку доли
                    остатка с ползунками, а не разом отдаёт весь остаток. */}
                <Button
                  variant="contained"
                  onClick={() => void openFbsStockDialog()}
                  data-testid="ff-catalog-fbs-set-stock"
                >
                  Задать остаток · {selectedIds.size}
                </Button>
              </Stack>
            </Stack>
            {/* Отказ показываем здесь, у самой кнопки. Раньше он рисовался в самом
                низу страницы, под таблицей на сотни строк: оператор нажимал кнопку,
                ничего не происходило, и она выглядела сломанной. */}
            {fbsDialogError ? (
              <Alert
                severity="error"
                sx={{ mt: 2 }}
                data-testid="ff-catalog-fbs-dialog-error"
              >
                {fbsDialogError}
              </Alert>
            ) : null}
          </Paper>
        ) : null}

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
              <col style={{ width: 44 }} />
              <col style={{ width: 56 }} />
              <col style={{ width: 160 }} />
              <col style={{ width: 170 }} />
              <col style={{ width: 118 }} />
              <col style={{ width: 130 }} />
              <col style={{ width: 64 }} />
              <col style={{ width: 110 }} />
              <col style={{ width: 130 }} />
              <col style={{ width: 124 }} />{/* «В Wildberries»: на 70px заголовок резало до «В Wildberr», а значение до «не перед» */}
              <col style={{ width: 70 }} />
              <col style={{ width: 110 }} />
              <col style={{ width: 96 }} />
              <col style={{ width: 106 }} />{/* действия: без своей ширины колонка схлопывалась в ноль на узком экране и забирала весь остаток на широком */}
            </colgroup>
            <TableHead>
              <TableRow>
                <TableCell padding="checkbox">
                  <Checkbox
                    checked={allVisibleSelected}
                    indeterminate={someVisibleSelected && !allVisibleSelected}
                    disabled={!canManageCatalog || filteredRows.length === 0}
                    onChange={(_, checked) => toggleSelectAllVisible(checked)}
                    data-testid="ff-catalog-select-all"
                  />
                </TableCell>
                <TableCell>Фото</TableCell>
                <TableCell>Название</TableCell>
                <TableCell>Артикул продавца</TableCell>
                <TableCell>SKU</TableCell>
                <TableCell>ШК</TableCell>
                <TableCell>Размер</TableCell>
                <TableCell>Селлер</TableCell>
                <TableCell align="right">Остаток</TableCell>
                <TableCell align="right">В Wildberries</TableCell>
                <TableCell>ТЗ</TableCell>
                <TableCell>ЧЗ</TableCell>
                <TableCell>Резервы</TableCell>
                {/* Колонка значков не липкая: липкая она постоянно съедала 106px
                    справа, и «В Wildberries» уходила под неё на узком экране.
                    Теперь колонка едет вместе с таблицей, как «ЧЗ» и «Резервы». */}
                <TableCell
                  align="center"
                  sx={{ borderLeft: '1px solid', borderLeftColor: 'divider' }}
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
                    <TableCell padding="checkbox">
                      <Checkbox
                        checked={selectedIds.has(p.id)}
                        disabled={!canManageCatalog}
                        onChange={(e) => toggleRowSelected(p.id, e.target.checked)}
                        data-testid={`ff-catalog-select-${p.id}`}
                      />
                    </TableCell>
                    <TableCell>
                      <ProductPhotoThumb src={p.wb_primary_image_url} />
                    </TableCell>
                    <TableCell>
                      <Stack spacing={0.25} sx={{ minWidth: 0 }}>
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
                        {p.country_of_origin_iso_code ? (
                          <Typography variant="caption" color="text.secondary" noWrap>
                            Страна: {p.country_of_origin_iso_code}
                          </Typography>
                        ) : null}
                      </Stack>
                    </TableCell>
                    <TableCell>
                      <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.75, minWidth: 0, minHeight: 45 }}>
                        <Typography variant="body2" sx={{ flex: '1 1 0', minWidth: 0, wordBreak: 'break-word' }}>
                          {p.wb_vendor_code ?? '—'}
                        </Typography>
                        {p.ozon_sku || p.ozon_offer_id ? (
                          <MarketplaceChip marketplace="ozon" testId="ff-catalog-marketplace-ozon" />
                        ) : null}
                      </Box>
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
                        {addressStorageEnabled ? <Typography
                          variant="caption"
                          data-testid={`ff-catalog-stock-in-storage-${p.id}`}
                          title={`В ячейках ${p.stock_in_storage}`}
                          noWrap
                        >
                          В ячейках {p.stock_in_storage}
                        </Typography> : null}
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
                    {/* Сколько из свободного остатка уходит в Wildberries.
                        Владелец просил видеть это прямо в каталоге, рядом с
                        остатком, а не на отдельном экране. */}
                    <TableCell align="right" sx={{ minWidth: 0 }}>
                      {p.fbs_stock_sync_enabled ? (
                        <Stack
                          direction="row"
                          spacing={0.75}
                          sx={{ alignItems: 'center', justifyContent: 'flex-end' }}
                        >
                          <Typography
                            variant="body2"
                            sx={{ fontWeight: 600 }}
                            data-testid={`ff-catalog-fbs-published-${p.id}`}
                          >
                            {(p.fbs_published_amount ?? 0).toLocaleString('ru-RU')}
                          </Typography>
                          {/* Как на макете: рядом с числом видно правило — общий
                              процент либо «по складам», если проценты разные.
                              Пока сервер не отдаёт эти поля, чипа нет: рисовать
                              «0%» значило бы показать неправду. */}
                          {p.fbs_same_everywhere === false || p.fbs_percent != null ? (
                            <Chip
                              size="small"
                              label={
                                p.fbs_same_everywhere === false
                                  ? 'по складам'
                                  : `${p.fbs_percent ?? 0}%`
                              }
                              sx={{ height: 20 }}
                              data-testid={`ff-catalog-fbs-rule-${p.id}`}
                            />
                          ) : null}
                        </Stack>
                      ) : (
                        <Typography
                          variant="caption"
                          color="text.secondary"
                          data-testid={`ff-catalog-fbs-published-${p.id}`}
                          noWrap
                        >
                          не передаётся
                        </Typography>
                      )}
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
                      sx={{ borderLeft: '1px solid', borderLeftColor: 'divider' }}
                    >
                      <Stack direction="row" spacing={0.25} sx={{ justifyContent: 'center' }}>
                        {/* Настройка остатка FBS по одному товару — как на
                            согласованном макете: значок в строке открывает ту же
                            модалку с ползунками, что и массовая кнопка сверху. */}
                        <Tooltip title="Остаток для FBS">
                          <span>
                            <IconButton
                              size="small"
                              aria-label={`Остаток для FBS ${p.sku_code}`}
                              data-testid={`ff-catalog-fbs-row-${p.id}`}
                              disabled={!canManageCatalog || !p.seller_id}
                              onClick={() => void openFbsStockDialog([p.id])}
                            >
                              <TuneOutlined fontSize="small" />
                            </IconButton>
                          </span>
                        </Tooltip>
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
                      </Stack>
                    </TableCell>
                  </TableRow>
                )
              })}
              {filteredRows.length === 0 && !busy ? (
                <TableRow>
                  <TableCell colSpan={14}>
                    {catalogScopeTotal === 0 ? (
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
                    ) : catalogTotal === 0 ? (
                      <Typography variant="body2" color="text.secondary" data-testid="ff-products-empty">
                        Ничего не найдено.
                      </Typography>
                    ) : null}
                  </TableCell>
                </TableRow>
              ) : null}
            </TableBody>
          </Table>
          <TablePagination
            component="div"
            count={catalogTotal}
            page={page}
            onPageChange={(_, nextPage) => setPage(nextPage)}
            rowsPerPage={rowsPerPage}
            onRowsPerPageChange={(event) => setRowsPerPage(Number(event.target.value))}
            rowsPerPageOptions={[50, 100, 200]}
            labelRowsPerPage="На странице"
            labelDisplayedRows={({ from, to, count }) => `${from}–${to} из ${count}`}
            data-testid="ff-catalog-pagination"
          />
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
          open={editProduct !== null}
          onClose={() => !editBusy && setEditProduct(null)}
          fullWidth
          maxWidth="sm"
          data-testid="ff-packaging-dialog"
        >
          <DialogTitle>Карточка товара</DialogTitle>
          <DialogContent>
            <Typography variant="body2" color="text.secondary" sx={{ mb: 1 }}>
              {editProduct?.sku_code} · {editProduct?.name}
            </Typography>
            {editOzonError ? (
              <Alert severity="error" sx={{ mb: 2 }} data-testid="ff-ozon-link-error">
                {editOzonError}
              </Alert>
            ) : null}
            <Stack spacing={1.5} sx={{ mb: 2 }}>
              <TextField
                fullWidth
                size="small"
                label="Артикул Wildberries"
                value={editProduct?.wb_vendor_code ?? ''}
                disabled
              />
              <Stack direction={{ xs: 'column', sm: 'row' }} spacing={1.5}>
                <TextField
                  fullWidth
                  size="small"
                  label="SKU Ozon"
                  value={editOzonSku}
                  onChange={(event) => setEditOzonSku(event.target.value)}
                  slotProps={{ htmlInput: { 'data-testid': 'ff-product-ozon-sku' } }}
                />
                <TextField
                  fullWidth
                  size="small"
                  label="Артикул Ozon"
                  value={editOzonOfferId}
                  onChange={(event) => setEditOzonOfferId(event.target.value)}
                  slotProps={{ htmlInput: { 'data-testid': 'ff-product-ozon-offer' } }}
                />
              </Stack>
              <TextField
                fullWidth
                size="small"
                label="Страна изготовления (ISO, 2 буквы)"
                value={editCountryIso}
                onChange={(event) => setEditCountryIso(event.target.value.toUpperCase().slice(0, 2))}
                slotProps={{ htmlInput: { 'data-testid': 'ff-product-country-iso' } }}
              />
            </Stack>
            <Divider sx={{ mb: 1 }} />
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

        {fbsDialog ? (
          <FbsStockDialog
            open
            products={fbsDialog.products}
            seller={fbsDialog.seller}
            rule={fbsDialog.rule}
            saveError={fbsDialogError}
            onClose={() => {
              setFbsDialog(null)
              setFbsDialogError(null)
            }}
            onBind={(wbWarehouseId, wmsWarehouseId) => {
              void bindFbsWarehouse(wbWarehouseId, wmsWarehouseId)
            }}
            onServedChange={(wbWarehouseId, served) => {
              void setFbsWarehouseServed(wbWarehouseId, served)
            }}
            onSave={(rule) => {
              const ids = fbsDialog.products.map((one) => one.id)
              void (async () => {
                try {
                  const res = await fetch(apiUrl('/products/fbs-rule'), {
                    method: 'PUT',
                    headers: { 'Content-Type': 'application/json', ...authHeaders(token) },
                    // PUT /products/fbs-rule ждёт правило вложенным в rule
                    // (ProductsFbsRuleBulkBody, extra="forbid"). Плоское тело
                    // отбивалось как «rule: Field required».
                    body: JSON.stringify({
                      product_ids: ids,
                      rule: {
                        publish: rule.publish,
                        same_everywhere: rule.sameEverywhere,
                        percent: rule.percent,
                        by_warehouse: rule.byWarehouse,
                        units_mode: rule.unitsMode,
                        // Что оператор видел в поле, то и записывается как новое
                        // выделение: сервер сдвинет точку отсчёта расхода на
                        // «сейчас», и съеденное до этой секунды уже учтено в том,
                        // что было показано.
                        units_by_warehouse: rule.unitsByWarehouse,
                      },
                    }),
                  })
                  if (!res.ok) {
                    setFbsDialogError(await readApiErrorMessage(res))
                    return
                  }
                  setFbsDialog(null)
                  setFbsDialogError(null)
                  await load()
                } catch (e) {
                  setFbsDialogError(
                    e instanceof Error ? e.message : 'Не удалось сохранить правило',
                  )
                }
              })()
            }}
          />
        ) : null}
      </Box>
    </FfProductMarkingPrintProvider>
  )
}
