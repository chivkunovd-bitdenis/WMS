import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import {
  Alert,
  Box,
  Button,
  Checkbox,
  Chip,
  Divider,
  Drawer,
  FormControl,
  FormControlLabel,
  CircularProgress,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
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
  TablePagination,
  TableRow,
  TextField,
  Typography,
} from '@mui/material'
import { apiUrl } from '../../api'
import { ProductPhotoThumb } from '../../components/ProductPhotoThumb'
import { ProductStockLines } from '../../components/ProductStockLines'
import { formatStockQty } from '../../utils/formatStockQty'
import { readApiErrorMessage } from '../../utils/readApiErrorMessage'
import { printPackagingInstructions } from '../../utils/printPackagingInstructions'
import { MarketplaceChip, MarketplaceIcon, type MarketplaceKind } from '../../ui-kit'
import { FbsStockDialogContainer } from '../ff/products-fbs/FbsStockDialogContainer'

// WMS-548 D5: товар на фулфилменте (row сегодняшней строки /products/wb-catalog)
// и карточка, ещё не заведённая товаром WMS ("не на фулфилменте"), в одной
// таблице. Второе — новое: без него селлер не увидит, что ещё можно добавить.
export type SellerCatalogProductItem = {
  key: string
  on_fulfillment: true
  marketplace: 'wildberries' | 'ozon'
  id: string
  sku_code: string
  name: string
  wb_vendor_code: string | null
  wb_nm_id: number | null
  ozon_sku: string | null
  ozon_offer_id: string | null
  wb_subject_name: string | null
  wb_primary_image_url: string | null
  wb_barcodes: string[]
  wb_primary_barcode: string | null
  wb_size: string | null
  packaging_instructions: string | null
  requires_honest_sign: boolean
  has_packaging_instructions: boolean
}

export type SellerCatalogCardItem = {
  key: string
  on_fulfillment: false
  marketplace: 'wildberries' | 'ozon'
  nm_id?: number | null
  // Контракт D2: id карточки Ozon — строка (offer/product id), не число.
  ozon_product_id?: string | null
  vendor_code: string | null
  name: string
  photo_url: string | null
  barcodes: string[]
  sizes: string[]
  category: string | null
}

export type SellerCatalogItem = SellerCatalogProductItem | SellerCatalogCardItem

type SellerCatalogPage = {
  items: SellerCatalogItem[]
  total: number
  scope_total: number
  categories: string[]
}

type FulfillmentFilter = 'all' | 'yes' | 'no'

// Остаток на ФФ по товару — из /operations/inventory-balances/summary. Тот же
// запрос и те же три числа Остаток / Резерв / Доступно, что в каталоге
// фулфилмента (CAT-20, WMS-532 R4); не на ФФ карточки в этом ответе не
// участвуют — им остаток не считается (WMS-548 R7).
type StockSummaryRow = {
  product_id: string
  sku_code: string
  product_name: string
  quantity: number
  reserved: number
  available: number
}

// Направления остатка (резервы) — только чтение. Механику резервирования
// правит фулфилмент в своём каталоге, здесь товар только смотрит список.
type StockDirectionRow = {
  id: string
  product_id: string
  name: string
  comment: string | null
  quantity: number
  is_fbs: boolean
}

// Контракт D2 (backend/app/api/seller_catalog.py: AddToFulfillmentEntryOut /
// AddToFulfillmentSkippedOut) — marketplace и id всегда есть, id строкой.
export type AddToFulfillmentOutcomeEntry = {
  marketplace: string
  id: string
  vendor_code: string | null
  products_added?: number
  reason?: string
}

type AddToFulfillmentOutcome = {
  added?: AddToFulfillmentOutcomeEntry[]
  skipped?: AddToFulfillmentOutcomeEntry[]
}

const ADD_TO_FULFILLMENT_BATCH_SIZE = 500

export function isProductItem(item: SellerCatalogItem): item is SellerCatalogProductItem {
  return item.on_fulfillment
}

export function isCardItem(item: SellerCatalogItem): item is SellerCatalogCardItem {
  return !item.on_fulfillment
}

// Строкой — контракт add-to-fulfillment сравнивает id как строку (backend
// шлёт str(nm_id) для WB и сам ozon_product_id для Ozon).
export function cardMarketplaceId(item: SellerCatalogCardItem): string | null {
  if (item.marketplace === 'wildberries') {
    return item.nm_id != null ? String(item.nm_id) : null
  }
  return item.ozon_product_id ?? null
}

export function itemMarketplaces(item: SellerCatalogItem): MarketplaceKind[] {
  if (isProductItem(item)) {
    // Товар на ФФ — «как сейчас» (R7): значок только для Ozon, точно как в
    // etalon; WB остаётся без чипа, экран этих строк D5 не меняет.
    return item.ozon_sku || item.ozon_offer_id ? ['ozon'] : []
  }
  // Карточка не на ФФ — новая строка (R7): значок площадки обязателен.
  return [item.marketplace === 'ozon' ? 'ozon' : 'wb']
}

function itemPhotoUrl(item: SellerCatalogItem): string | null {
  return isProductItem(item) ? item.wb_primary_image_url : item.photo_url
}

function itemVendorCode(item: SellerCatalogItem): string | null {
  return isProductItem(item) ? item.wb_vendor_code : item.vendor_code
}

export function itemPrimaryBarcode(item: SellerCatalogItem): string | null {
  if (isProductItem(item)) {
    return item.wb_primary_barcode ?? item.wb_barcodes[0] ?? null
  }
  return item.barcodes[0] ?? null
}

function itemAllBarcodes(item: SellerCatalogItem): string[] {
  return isProductItem(item) ? item.wb_barcodes : item.barcodes
}

export function itemSizeLabel(item: SellerCatalogItem): string {
  if (isProductItem(item)) {
    return item.wb_size ?? '—'
  }
  return item.sizes.length > 0 ? item.sizes.join(', ') : '—'
}

/** Разбивает идентификаторы на порции не больше 500 штук (контракт D2). */
export function chunk<T>(items: T[], size: number): T[][] {
  const result: T[][] = []
  for (let i = 0; i < items.length; i += size) {
    result.push(items.slice(i, i + size))
  }
  return result
}

export function outcomeEntryMarketplace(entry: AddToFulfillmentOutcomeEntry): 'wildberries' | 'ozon' {
  return entry.marketplace === 'ozon' ? 'ozon' : 'wildberries'
}

// А12 (решение 27.09, коммит 89fddfc7): причину пропуска на экране не
// расшифровываем — только артикул продавца (или, если его нет, id карточки).
export function outcomeEntryLabel(entry: AddToFulfillmentOutcomeEntry, cards: SellerCatalogCardItem[]): string {
  const marketplace = outcomeEntryMarketplace(entry)
  const match = cards.find(
    (card) => card.marketplace === marketplace && cardMarketplaceId(card) === entry.id,
  )
  return match?.vendor_code ?? entry.vendor_code ?? entry.id
}

export type SellerCatalogPageLoad =
  | { outcome: 'stale' }
  | { outcome: 'loaded'; page: SellerCatalogPage }
  | { outcome: 'failed'; message: string }

/**
 * Страница каталога применяется, только если к моменту ответа вкладка
 * осталась в той же сессии.
 *
 * WMS-488: пока список грузился, сессию могли сменить (другой селлер в
 * соседней вкладке, переключение магазина). Запоздалый ответ — это карточки
 * прежнего селлера, и на экране им места нет.
 */
export async function loadSellerCatalogPage(
  headers: Record<string, string>,
  params: URLSearchParams,
  isCurrentSession: () => boolean,
  signal?: AbortSignal,
): Promise<SellerCatalogPageLoad> {
  try {
    const res = await fetch(apiUrl(`/seller-catalog/page?${params.toString()}`), { headers, signal })
    if (!isCurrentSession()) {
      return { outcome: 'stale' }
    }
    if (!res.ok) {
      const message = await readApiErrorMessage(res)
      return isCurrentSession() ? { outcome: 'failed', message } : { outcome: 'stale' }
    }
    const page = (await res.json()) as SellerCatalogPage
    return isCurrentSession() ? { outcome: 'loaded', page } : { outcome: 'stale' }
  } catch (e) {
    if ((e as { name?: string }).name === 'AbortError') {
      return { outcome: 'stale' }
    }
    if (!isCurrentSession()) {
      return { outcome: 'stale' }
    }
    return {
      outcome: 'failed',
      message: e instanceof Error ? e.message : 'Не удалось загрузить товары.',
    }
  }
}

export type SellerCatalogSyncOutcome = {
  wbFailure: string | null
  ozonFailure: string | null
}

/**
 * «Синхронизировать по API» обновляет каждую подключённую площадку сама по
 * себе — отказ WB не должен отменять Ozon и наоборот (R12; ревью Astra №1,
 * WMS-548, замечание F4). Раньше сбой WB (нет ключа, отвечает 409) обрывал
 * функцию до проверки Ozon, а сетевая ошибка самого запроса синхронизации
 * Ozon тонула в catch, который должен был гасить только отказ проверки
 * подключения — снаружи это выглядело так, будто кнопка вообще ничего не
 * сделала.
 *
 * Обе площадки сначала проверяются на подключение (у WB — has_content_token,
 * у Ozon — connected) и синхронизируются, только если ключ есть; неподключённая
 * площадка пропускается молча — «ключа нет» не ошибка, а обычное состояние
 * (после приёмки F4 голый `missing_content_token` на экране у селлера без
 * WB выглядел как сбой там, где WB у него просто не подключён). Отказ самой
 * проверки подключения — тоже не сбой синхронизации, площадку в этот раз
 * просто не трогаем. А вот отказ самого запроса синхронизации уже
 * подключённой площадки — результат, который обязан быть виден, человеческим
 * текстом, а не кодом.
 */
/**
 * Превращает код ошибки бэкенда в человеческую строку. Известные коды —
 * своим текстом (как `invalid_wb_token` уже расшифрован в SellerSettingsScreen);
 * всё остальное, что похоже на код, а не на готовую фразу (readApiErrorMessage
 * уже умеет разворачивать часть кодов через общий словарь, но не все), —
 * общим сообщением про площадку, а не голым идентификатором на экране
 * (тот же приём, что и humanFfCatalogError в каталоге ФФ).
 */
function humanSyncFailureMessage(rawMessage: string, platformFallback: string): string {
  const trimmed = rawMessage.trim()
  if (trimmed.includes('invalid_wb_token')) {
    return 'Ключ WB не подходит — проверка не прошла.'
  }
  if (/^[a-z0-9_:-]+$/.test(trimmed)) {
    return platformFallback
  }
  return trimmed || platformFallback
}

export async function syncSellerCatalogMarketplaces(
  headers: Record<string, string>,
): Promise<SellerCatalogSyncOutcome> {
  // Неподключённую площадку пропускаем молча — как и у Ozon, «ключа нет»
  // не ошибка синхронизации, а обычное состояние (WMS-548, доработка после
  // приёмки F4: голый missing_content_token на экране у селлера без WB пугал
  // его там, где WB у него попросту не подключён).
  let wbConnected = false
  try {
    const wbStatusRes = await fetch(apiUrl('/integrations/wildberries/self/tokens'), { headers })
    if (wbStatusRes.ok) {
      const wbStatus = (await wbStatusRes.json()) as { has_content_token?: boolean }
      wbConnected = Boolean(wbStatus.has_content_token)
    }
  } catch {
    // Неудачная проверка подключения — не сбой синхронизации, WB просто не трогаем.
  }

  let wbFailure: string | null = null
  if (wbConnected) {
    try {
      const wbRes = await fetch(apiUrl('/integrations/wildberries/self/sync-products'), {
        method: 'POST',
        headers,
      })
      if (!wbRes.ok) {
        wbFailure = humanSyncFailureMessage(
          await readApiErrorMessage(wbRes),
          'Не удалось синхронизировать Wildberries.',
        )
      }
    } catch (e) {
      wbFailure = e instanceof Error ? e.message : 'Не удалось синхронизировать Wildberries.'
    }
  }

  let ozonConnected = false
  try {
    const statusRes = await fetch(apiUrl('/integrations/ozon/self/account'), { headers })
    if (statusRes.ok) {
      const status = (await statusRes.json()) as { connected?: boolean }
      ozonConnected = Boolean(status.connected)
    }
  } catch {
    // См. комментарий выше: неудачная проверка подключения — не сбой синхронизации.
  }

  let ozonFailure: string | null = null
  if (ozonConnected) {
    try {
      const ozonRes = await fetch(apiUrl('/integrations/ozon/self/sync-products'), {
        method: 'POST',
        headers,
      })
      if (!ozonRes.ok) {
        ozonFailure = humanSyncFailureMessage(
          await readApiErrorMessage(ozonRes),
          'Не удалось синхронизировать Ozon.',
        )
      }
    } catch (e) {
      ozonFailure = e instanceof Error ? e.message : 'Не удалось синхронизировать Ozon.'
    }
  }

  return { wbFailure, ozonFailure }
}

type Props = {
  token: string
  authHeaders: (t: string) => Record<string, string>
  sellerId: string
  sellerName: string
  warehouses: Array<{ id: string; name: string; code?: string; is_operational?: boolean }>
}

export function SellerProductsStockScreen({
  token,
  authHeaders,
  sellerId,
  sellerName,
  warehouses,
}: Props) {
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [notice, setNotice] = useState<string | null>(null)
  const [items, setItems] = useState<SellerCatalogItem[]>([])
  const [total, setTotal] = useState(0)
  const [scopeTotal, setScopeTotal] = useState(0)
  const [categoryOptions, setCategoryOptions] = useState<string[]>([])
  const [stock, setStock] = useState<StockSummaryRow[]>([])
  const [page, setPage] = useState(0)
  const [rowsPerPage, setRowsPerPage] = useState(10)
  const [editProduct, setEditProduct] = useState<SellerCatalogProductItem | null>(null)
  const [editText, setEditText] = useState('')
  const [editRequiresHonestSign, setEditRequiresHonestSign] = useState(false)
  const [editBusy, setEditBusy] = useState(false)
  // Отметка строк живёт между страницами и фильтрами (R9 D5) — иначе среди
  // тысяч карточек нельзя набрать выборку для «Добавить к фулфилменту»
  // постранично. Ключ строки — SellerCatalogItem.key.
  const [selectedKeys, setSelectedKeys] = useState<Set<string>>(new Set())
  const [selectedItemsByKey, setSelectedItemsByKey] = useState<Map<string, SellerCatalogItem>>(new Map())
  const [bulkHonestSignBusy, setBulkHonestSignBusy] = useState(false)
  const [addBusy, setAddBusy] = useState(false)
  const [stockDialogRows, setStockDialogRows] = useState<SellerCatalogProductItem[] | null>(null)

  // ── Фильтры над таблицей (перенесены из каталога фулфилмента, CAT-20;
  //    «Фулфилмент» — новый, WMS-548 R7/А10) ─────────────────────────────
  const [filterSearch, setFilterSearch] = useState('')
  const [debouncedSearch, setDebouncedSearch] = useState('')
  const [filterCategory, setFilterCategory] = useState('')
  const [filterFulfillment, setFilterFulfillment] = useState<FulfillmentFilter>('all')

  // ── Резервы: список направлений остатка, только чтение (CAT-20) ──────────
  const [reservesProductId, setReservesProductId] = useState<string | null>(null)
  const [reserveDirections, setReserveDirections] = useState<Record<string, StockDirectionRow[]>>({})
  const [reserveBusy, setReserveBusy] = useState<Set<string>>(new Set())

  // Токен сессии, к которой относятся показанные строки. Держим в ref, чтобы
  // ответ, пришедший после смены сессии, было с чем сравнить (WMS-488).
  const sessionTokenRef = useRef(token)
  const catalogAbortRef = useRef<AbortController | null>(null)
  useEffect(() => {
    sessionTokenRef.current = token
    // Показанное принадлежит прежнему токену: до ответа по новому на экране
    // не должно остаться ни строки прежнего селлера.
    setItems([])
    setStock([])
    setReserveDirections({})
    setSelectedKeys(new Set())
    setSelectedItemsByKey(new Map())
  }, [token])

  useEffect(() => {
    const timeout = window.setTimeout(() => setDebouncedSearch(filterSearch.trim()), 250)
    return () => window.clearTimeout(timeout)
  }, [filterSearch])

  useEffect(() => {
    setPage(0)
  }, [debouncedSearch, filterCategory, filterFulfillment, rowsPerPage])

  const load = useCallback(async () => {
    const requestToken = token
    const isCurrentSession = () => sessionTokenRef.current === requestToken
    catalogAbortRef.current?.abort()
    const controller = new AbortController()
    catalogAbortRef.current = controller
    setError(null)
    setBusy(true)
    const params = new URLSearchParams({
      limit: String(rowsPerPage),
      offset: String(page * rowsPerPage),
      on_fulfillment: filterFulfillment,
    })
    if (debouncedSearch) params.set('search', debouncedSearch)
    if (filterCategory) params.set('category', filterCategory)
    const result = await loadSellerCatalogPage(
      { ...authHeaders(requestToken) },
      params,
      isCurrentSession,
      controller.signal,
    )
    if (result.outcome === 'stale') {
      return
    }
    setBusy(false)
    if (result.outcome === 'failed') {
      setError(result.message)
      return
    }
    setItems(result.page.items)
    setTotal(result.page.total)
    setScopeTotal(result.page.scope_total)
    setCategoryOptions(result.page.categories)
    // Свежие данные выбранной строки (например, обновилось название после
    // синхронизации) — но саму отметку не трогаем, даже если строки нет на
    // этой странице.
    setSelectedItemsByKey((current) => {
      let changed = false
      const next = new Map(current)
      for (const item of result.page.items) {
        if (next.has(item.key)) {
          next.set(item.key, item)
          changed = true
        }
      }
      return changed ? next : current
    })
  }, [authHeaders, debouncedSearch, filterCategory, filterFulfillment, page, rowsPerPage, token])

  useEffect(() => {
    void load()
    return () => catalogAbortRef.current?.abort()
  }, [load])

  const loadStock = useCallback(async () => {
    const requestToken = token
    try {
      const res = await fetch(apiUrl('/operations/inventory-balances/summary'), {
        headers: { ...authHeaders(requestToken) },
      })
      if (sessionTokenRef.current !== requestToken) {
        return
      }
      if (!res.ok) {
        setError(await readApiErrorMessage(res))
        return
      }
      const body = (await res.json()) as StockSummaryRow[]
      if (sessionTokenRef.current !== requestToken) {
        return
      }
      setStock(body)
    } catch (e) {
      if (sessionTokenRef.current !== requestToken) {
        return
      }
      setError(e instanceof Error ? e.message : 'Не удалось загрузить остатки.')
    }
  }, [authHeaders, token])

  useEffect(() => {
    void loadStock()
  }, [loadStock])

  const stockByProductId = useMemo(() => new Map(stock.map((s) => [s.product_id, s])), [stock])

  const selectedItems = useMemo(() => [...selectedItemsByKey.values()], [selectedItemsByKey])
  const selectedProductItems = useMemo(() => selectedItems.filter(isProductItem), [selectedItems])
  const selectedCardItems = useMemo(() => selectedItems.filter(isCardItem), [selectedItems])
  const selectedTotalCount = selectedKeys.size

  const visibleKeys = useMemo(() => items.map((row) => row.key), [items])
  const visibleSelectedCount = useMemo(
    () => visibleKeys.filter((key) => selectedKeys.has(key)).length,
    [selectedKeys, visibleKeys],
  )
  const allVisibleSelected = visibleKeys.length > 0 && visibleSelectedCount === visibleKeys.length
  const someVisibleSelected = visibleSelectedCount > 0 && !allVisibleSelected

  function openPackagingEdit(p: SellerCatalogProductItem) {
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
      await load()
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Не удалось сохранить ТЗ.')
    } finally {
      setEditBusy(false)
    }
  }

  async function applyHonestSignToSelected() {
    const productIdsToUpdate = selectedProductItems.map((item) => item.id)
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
      setItems((current) =>
        current.map((row) =>
          isProductItem(row) && selectedIds.has(row.id) ? { ...row, requires_honest_sign: true } : row,
        ),
      )
      setSelectedKeys(new Set())
      setSelectedItemsByKey(new Map())
      setNotice(`Честный знак включён: ${body.updated_count} товаров.`)
      await load()
    } catch (e) {
      setError(
        e instanceof Error ? e.message : 'Не удалось включить Честный знак выбранным товарам.',
      )
    } finally {
      setBulkHonestSignBusy(false)
    }
  }

  const toggleSelectedRow = useCallback((item: SellerCatalogItem, checked: boolean) => {
    setSelectedKeys((current) => {
      const next = new Set(current)
      if (checked) next.add(item.key)
      else next.delete(item.key)
      return next
    })
    setSelectedItemsByKey((current) => {
      const next = new Map(current)
      if (checked) next.set(item.key, item)
      else next.delete(item.key)
      return next
    })
  }, [])

  const toggleVisibleRows = useCallback(
    (checked: boolean) => {
      setSelectedKeys((current) => {
        const next = new Set(current)
        for (const key of visibleKeys) {
          if (checked) next.add(key)
          else next.delete(key)
        }
        return next
      })
      setSelectedItemsByKey((current) => {
        const next = new Map(current)
        for (const row of items) {
          if (checked) next.set(row.key, row)
          else next.delete(row.key)
        }
        return next
      })
    },
    [items, visibleKeys],
  )

  async function onSyncProducts() {
    setError(null)
    setNotice(null)
    setBusy(true)
    try {
      // Каждая площадка синхронизируется независимо (R12; ревью Astra №1,
      // WMS-548, F4) — отказ WB не отменяет Ozon и наоборот.
      const outcome = await syncSellerCatalogMarketplaces({ ...authHeaders(token) })
      await load()
      const failures = [
        outcome.wbFailure,
        outcome.ozonFailure ? `Ozon: ${outcome.ozonFailure}` : null,
      ].filter((message): message is string => message != null)
      if (failures.length > 0) {
        setError(failures.join(' '))
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Не удалось синхронизировать товары.')
    } finally {
      setBusy(false)
    }
  }

  async function addSelectedToFulfillment() {
    const cards = selectedCardItems
    if (cards.length === 0) return
    setAddBusy(true)
    setError(null)
    setNotice(null)
    // Итоговое сообщение ставится только ПОСЛЕ перечитывания страницы (load()
    // ниже сбрасывает error на время своего запроса) — иначе результат гас
    // сразу же, не успев показаться (WMS-548 R9, решение А12).
    let failureMessage: string | null = null
    // id всегда строкой (контракт D2): для WB это nm_id, отправляется числом
    // в теле запроса; для Ozon — как есть.
    type Ref = { kind: 'wildberries' | 'ozon'; id: string }
    const refs: Ref[] = []
    for (const card of cards) {
      const id = cardMarketplaceId(card)
      if (id == null) continue
      refs.push({ kind: card.marketplace, id })
    }
    const batches = chunk(refs, ADD_TO_FULFILLMENT_BATCH_SIZE)
    const addedKeys = new Set<string>()
    // А12: причину пропуска не расшифровываем — только артикулы, одной строкой.
    const skippedLabels: string[] = []
    for (const batch of batches) {
      const body = {
        wb_nm_ids: batch.filter((r) => r.kind === 'wildberries').map((r) => Number(r.id)),
        ozon_product_ids: batch.filter((r) => r.kind === 'ozon').map((r) => r.id),
      }
      try {
        const res = await fetch(apiUrl('/seller-catalog/add-to-fulfillment'), {
          method: 'POST',
          headers: { ...authHeaders(token), 'Content-Type': 'application/json' },
          body: JSON.stringify(body),
        })
        if (!res.ok) {
          failureMessage = await readApiErrorMessage(res)
          break
        }
        const outcome = (await res.json()) as AddToFulfillmentOutcome
        for (const entry of outcome.added ?? []) {
          const marketplace = outcomeEntryMarketplace(entry)
          const match = cards.find(
            (card) => card.marketplace === marketplace && cardMarketplaceId(card) === entry.id,
          )
          if (match) addedKeys.add(match.key)
        }
        for (const entry of outcome.skipped ?? []) {
          skippedLabels.push(outcomeEntryLabel(entry, cards))
        }
      } catch (e) {
        failureMessage = e instanceof Error ? e.message : 'Не удалось добавить товары к фулфилменту.'
        break
      }
    }
    if (addedKeys.size > 0) {
      setSelectedKeys((current) => {
        const next = new Set(current)
        for (const key of addedKeys) next.delete(key)
        return next
      })
      setSelectedItemsByKey((current) => {
        const next = new Map(current)
        for (const key of addedKeys) next.delete(key)
        return next
      })
    }
    setAddBusy(false)
    // load() само сбрасывает error в начале своего запроса — сообщение по
    // итогу добавления ставим только после того, как оно отработает.
    await load()
    if (failureMessage) {
      setError(failureMessage)
    } else if (skippedLabels.length > 0) {
      setError(`Не добавлены: ${skippedLabels.join(', ')}.`)
    } else if (addedKeys.size > 0) {
      setNotice(`Добавлено к фулфилменту: ${addedKeys.size}.`)
    }
  }

  const markReserveBusy = useCallback((productId: string, pending: boolean) => {
    setReserveBusy((current) => {
      const next = new Set(current)
      if (pending) next.add(productId)
      else next.delete(productId)
      return next
    })
  }, [])

  const loadReserveDirections = useCallback(
    async (productId: string) => {
      const requestToken = token
      markReserveBusy(productId, true)
      setError(null)
      try {
        const res = await fetch(apiUrl(`/products/${productId}/stock-directions`), {
          headers: { ...authHeaders(requestToken) },
        })
        if (sessionTokenRef.current !== requestToken) {
          return
        }
        if (!res.ok) {
          setError(await readApiErrorMessage(res))
          return
        }
        const body = (await res.json()) as StockDirectionRow[]
        if (sessionTokenRef.current !== requestToken) {
          return
        }
        setReserveDirections((current) => ({ ...current, [productId]: body }))
      } catch (e) {
        setError(e instanceof Error ? e.message : 'Не удалось загрузить резервы.')
      } finally {
        markReserveBusy(productId, false)
      }
    },
    [authHeaders, markReserveBusy, token],
  )

  const openReserves = useCallback(
    async (productId: string) => {
      setReservesProductId(productId)
      if (reserveDirections[productId] == null) {
        await loadReserveDirections(productId)
      }
    },
    [loadReserveDirections, reserveDirections],
  )

  const closeReserves = useCallback(() => {
    setReservesProductId(null)
  }, [])

  const reservesProduct = useMemo(() => {
    const found = items.find((row) => isProductItem(row) && row.id === reservesProductId)
    return found && isProductItem(found) ? found : null
  }, [items, reservesProductId])
  const reservesStock = reservesProduct ? stockByProductId.get(reservesProduct.id) : undefined

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
        Каталог товаров, синхронизированных из маркетплейсов.
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
            disabled={bulkHonestSignBusy || busy || selectedProductItems.length === 0}
            onClick={() => void applyHonestSignToSelected()}
            data-testid="seller-products-bulk-honest-sign"
          >
            Включить ЧЗ
          </Button>
          {busy ? <CircularProgress size={18} /> : null}
          {bulkHonestSignBusy ? <CircularProgress size={18} /> : null}
        </Stack>
      </Paper>

      {selectedTotalCount > 0 ? (
        <Paper
          variant="outlined"
          sx={{ p: 2, mb: 2, borderColor: 'primary.main' }}
          data-testid="seller-catalog-selection-bar"
        >
          <Stack
            direction={{ xs: 'column', sm: 'row' }}
            spacing={2}
            sx={{ alignItems: { sm: 'center' }, justifyContent: 'space-between' }}
          >
            <Typography variant="subtitle2" data-testid="seller-catalog-selection-count">
              Выбрано {selectedTotalCount}
            </Typography>
            <Stack direction="row" spacing={1} sx={{ flexWrap: 'wrap' }}>
              <Button
                variant="contained"
                disabled={selectedProductItems.length === 0}
                onClick={() => setStockDialogRows(selectedProductItems)}
                data-testid="seller-catalog-fbs-set-stock"
              >
                Задать остаток · {selectedProductItems.length}
              </Button>
              <Button
                variant="outlined"
                disabled={addBusy || selectedCardItems.length === 0}
                onClick={() => void addSelectedToFulfillment()}
                data-testid="seller-catalog-add-to-fulfillment"
              >
                Добавить к фулфилменту
              </Button>
              {addBusy ? <CircularProgress size={18} /> : null}
            </Stack>
          </Stack>
        </Paper>
      ) : null}

      <Paper variant="outlined" sx={{ p: 2, mb: 2 }} data-testid="seller-catalog-filters">
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
            slotProps={{ htmlInput: { 'data-testid': 'seller-catalog-search' } }}
            sx={{ minWidth: 260 }}
          />
          <FormControl size="small" sx={{ minWidth: 200 }}>
            <InputLabel id="seller-catalog-category-filter-label">Категория</InputLabel>
            <Select
              labelId="seller-catalog-category-filter-label"
              label="Категория"
              value={filterCategory}
              onChange={(e) => setFilterCategory(e.target.value)}
              data-testid="seller-catalog-category-filter"
            >
              <MenuItem value="">Все категории</MenuItem>
              {categoryOptions.map((c) => (
                <MenuItem key={c} value={c}>
                  {c}
                </MenuItem>
              ))}
            </Select>
          </FormControl>
          <FormControl size="small" sx={{ minWidth: 200 }}>
            <InputLabel id="seller-catalog-fulfillment-filter-label">Фулфилмент</InputLabel>
            <Select
              labelId="seller-catalog-fulfillment-filter-label"
              label="Фулфилмент"
              value={filterFulfillment}
              onChange={(e) => setFilterFulfillment(e.target.value as FulfillmentFilter)}
              data-testid="seller-catalog-fulfillment-filter"
            >
              <MenuItem value="all">Все товары</MenuItem>
              <MenuItem value="yes">На фулфилменте</MenuItem>
              <MenuItem value="no">Не на фулфилменте</MenuItem>
            </Select>
          </FormControl>
          <Typography variant="body2" color="text.secondary" data-testid="seller-catalog-filter-count">
            {busy ? 'Загрузка…' : `Найдено: ${total} из ${scopeTotal}`}
          </Typography>
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
              fontSize: '0.7rem',
              lineHeight: 1.2,
              whiteSpace: 'normal',
            },
            '& .MuiButton-sizeSmall': {
              minHeight: 24,
              lineHeight: 1,
            },
          }}
        >
          {/* «Остаток» шире за счёт артикулов (WMS-532 R3, R4): на 1024 px в 10 %
              не помещалось даже «Доступно 27», а «−1 234 567» срезалось. Артикулы
              и SKU по-прежнему в одну строку с многоточием и подсказкой. */}
          <colgroup>
            <col style={{ width: '5%' }} />
            <col style={{ width: '5%' }} />
            <col style={{ width: '10.5%' }} />
            <col style={{ width: '15%' }} />
            <col style={{ width: '14.5%' }} />
            <col style={{ width: '10.5%' }} />
            <col style={{ width: '8%' }} />
            <col style={{ width: '15%' }} />
            <col style={{ width: '6%' }} />
            <col style={{ width: '4%' }} />
            <col style={{ width: '7.5%' }} />
          </colgroup>
          <TableHead>
            <TableRow>
              <TableCell padding="checkbox">
                <Checkbox
                  size="small"
                  checked={allVisibleSelected}
                  indeterminate={someVisibleSelected}
                  disabled={visibleKeys.length === 0}
                  onChange={(event) => toggleVisibleRows(event.target.checked)}
                  slotProps={{ input: { 'aria-label': 'Выбрать товары на странице' } }}
                  data-testid="seller-products-select-all"
                />
              </TableCell>
              <TableCell>Фото</TableCell>
              <TableCell>Название</TableCell>
              <TableCell>Артикул продавца</TableCell>
              <TableCell>SKU</TableCell>
              <TableCell>ШК</TableCell>
              <TableCell>Размер</TableCell>
              <TableCell align="right">Остаток</TableCell>
              <TableCell>ТЗ</TableCell>
              <TableCell>ЧЗ</TableCell>
              <TableCell>Резервы</TableCell>
            </TableRow>
          </TableHead>
          <TableBody>
            {items.map((row) => {
              const onFulfillment = isProductItem(row)
              const bal = onFulfillment ? stockByProductId.get(row.id) : undefined
              const primaryBarcode = itemPrimaryBarcode(row)
              const allBarcodes = itemAllBarcodes(row)
              return (
                <TableRow
                  hover
                  selected={selectedKeys.has(row.key)}
                  data-testid="seller-product-row"
                  key={row.key}
                  sx={{ height: 68 }}
                >
                  <TableCell padding="checkbox">
                    <Checkbox
                      size="small"
                      checked={selectedKeys.has(row.key)}
                      onChange={(event) => toggleSelectedRow(row, event.target.checked)}
                      slotProps={{ input: { 'aria-label': `Выбрать товар ${row.name}` } }}
                      data-testid={`seller-product-select-${row.key}`}
                    />
                  </TableCell>
                  <TableCell>
                    <ProductPhotoThumb src={itemPhotoUrl(row)} />
                  </TableCell>
                  <TableCell>
                    <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.75, minWidth: 0 }}>
                      <Typography
                        variant="caption"
                        sx={{
                          flex: '1 1 0',
                          minWidth: 0,
                          fontWeight: 600,
                          display: '-webkit-box',
                          WebkitLineClamp: 2,
                          WebkitBoxOrient: 'vertical',
                          overflow: 'hidden',
                        }}
                        title={row.name}
                      >
                        {row.name}
                      </Typography>
                      {onFulfillment ? (
                        itemMarketplaces(row).map((marketplace) => (
                          <MarketplaceChip
                            key={marketplace}
                            marketplace={marketplace}
                            testId={`seller-catalog-marketplace-${marketplace}-${row.key}`}
                          />
                        ))
                      ) : (
                        // Карточка не на ФФ — новая строка (R7), «значок площадки»
                        // обязателен для каждой такой строки, а не изредка, как
                        // сегодняшний чип «Ozon» на товаре. Полный текстовый чип
                        // «Wildberries» (94px) в узкой колонке названия (10.5%,
                        // как в etalon — ширины этот экран не меняет) съедал
                        // название почти целиком; компактный квадратный значок
                        // (22×22, тот же MarketplaceIcon, что и в окне «Задать
                        // остаток») даёт место и значку, и названию.
                        <MarketplaceIcon
                          marketplace={row.marketplace === 'ozon' ? 'ozon' : 'wb'}
                          testId={`seller-catalog-marketplace-${row.key}`}
                        />
                      )}
                    </Box>
                  </TableCell>
                  <TableCell>
                    <Typography
                      variant="caption"
                      sx={{ fontSize: '0.7rem' }}
                      title={itemVendorCode(row) ?? '—'}
                      noWrap
                    >
                      {itemVendorCode(row) ?? '—'}
                    </Typography>
                  </TableCell>
                  <TableCell>
                    <Typography
                      variant="caption"
                      sx={{ fontSize: '0.7rem', fontWeight: 600 }}
                      title={onFulfillment ? row.sku_code : '—'}
                      noWrap
                    >
                      {onFulfillment ? row.sku_code : '—'}
                    </Typography>
                  </TableCell>
                  <TableCell>
                    <Typography
                      variant="caption"
                      sx={{ fontSize: '0.7rem' }}
                      title={allBarcodes.length > 0 ? allBarcodes.join(', ') : undefined}
                      noWrap
                    >
                      {primaryBarcode ?? '—'}
                    </Typography>
                  </TableCell>
                  <TableCell>
                    <Typography variant="body2" title={itemSizeLabel(row)} noWrap>
                      {itemSizeLabel(row)}
                    </Typography>
                  </TableCell>
                  <TableCell align="right">
                    {onFulfillment ? (
                      <ProductStockLines
                        totals={{
                          onHand: bal?.quantity ?? 0,
                          reserved: bal?.reserved ?? 0,
                          available: bal?.available ?? 0,
                        }}
                        productId={row.id}
                        testIdPrefix="seller-catalog-stock"
                        fontSize="0.65rem"
                      />
                    ) : null}
                  </TableCell>
                  <TableCell sx={{ minWidth: 0 }}>
                    {onFulfillment ? (
                      <Button
                        size="small"
                        variant={row.has_packaging_instructions ? 'contained' : 'outlined'}
                        color={row.has_packaging_instructions ? 'primary' : 'inherit'}
                        onClick={() => openPackagingEdit(row)}
                        data-testid={`seller-packaging-edit-${row.id}`}
                        aria-label={row.has_packaging_instructions ? 'Редактировать ТЗ' : 'Добавить ТЗ'}
                        title={row.has_packaging_instructions ? 'Редактировать ТЗ' : 'Добавить ТЗ'}
                        sx={{
                          minWidth: 56,
                          px: 1,
                          ...(row.has_packaging_instructions
                            ? {}
                            : { color: 'text.secondary', borderColor: 'divider' }),
                        }}
                      >
                        ТЗ
                      </Button>
                    ) : null}
                  </TableCell>
                  <TableCell sx={{ minWidth: 0 }}>
                    {onFulfillment && row.requires_honest_sign ? (
                      <Chip
                        size="small"
                        label="ЧЗ"
                        color="info"
                        variant="outlined"
                        data-testid={`seller-honest-sign-status-${row.id}`}
                      />
                    ) : null}
                  </TableCell>
                  <TableCell sx={{ minWidth: 0 }}>
                    {onFulfillment ? (
                      <Button
                        size="small"
                        variant="outlined"
                        onClick={() => void openReserves(row.id)}
                        data-testid={`seller-catalog-reserves-${row.id}`}
                        sx={{ minWidth: 0, px: 1 }}
                      >
                        Резервы
                      </Button>
                    ) : null}
                  </TableCell>
                </TableRow>
              )
            })}
            {items.length === 0 && !busy ? (
              <TableRow>
                <TableCell colSpan={11}>
                  <Typography variant="body2" color="text.secondary">
                    {scopeTotal === 0 ? 'Пока нет товаров.' : 'Ничего не найдено.'}
                  </Typography>
                </TableCell>
              </TableRow>
            ) : null}
          </TableBody>
        </Table>
        <TablePagination
          component="div"
          count={total}
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

      <Drawer
        anchor="right"
        open={reservesProduct != null}
        onClose={closeReserves}
        slotProps={{
          paper: { sx: { width: { xs: '100%', sm: 460 }, maxWidth: '100%' } },
        }}
        data-testid={reservesProduct ? `seller-reserves-panel-${reservesProduct.id}` : undefined}
      >
        {reservesProduct ? (
          <Box sx={{ p: 2.5 }}>
            <Stack spacing={2}>
              <Box>
                <Typography variant="h6">Резервы</Typography>
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
                  {reservesProduct.sku_code} · {reservesProduct.name}
                </Typography>
              </Box>
              {/* Те же три числа, что в ячейке «Остаток» этой строки (WMS-532 R5):
                  направления ниже — лишь часть резерва. */}
              <Stack direction="row" sx={{ flexWrap: 'wrap', columnGap: 2, rowGap: 1 }}>
                {[
                  { key: 'on-hand', label: 'Остаток', value: reservesStock?.quantity ?? 0 },
                  { key: 'reserved', label: 'Резерв', value: reservesStock?.reserved ?? 0 },
                  { key: 'available', label: 'Доступно', value: reservesStock?.available ?? 0 },
                ].map((item) => (
                  <Box key={item.key} data-testid={`seller-reserves-${item.key}`}>
                    <Typography variant="caption" color="text.secondary">
                      {item.label}
                    </Typography>
                    <Typography variant="h6" sx={{ whiteSpace: 'nowrap' }}>
                      {formatStockQty(item.value)} шт
                    </Typography>
                  </Box>
                ))}
              </Stack>
              <Divider />
              <Stack spacing={1}>
                {reserveBusy.has(reservesProduct.id) ? (
                  <Stack direction="row" spacing={1} sx={{ alignItems: 'center' }}>
                    <CircularProgress size={18} />
                    <Typography variant="body2" color="text.secondary">
                      Загружаем…
                    </Typography>
                  </Stack>
                ) : null}
                {!reserveBusy.has(reservesProduct.id) &&
                (reserveDirections[reservesProduct.id]?.length ?? 0) === 0 ? (
                  <Typography variant="body2" color="text.secondary">
                    Направлений пока нет.
                  </Typography>
                ) : null}
                {(reserveDirections[reservesProduct.id] ?? []).map((direction) => (
                  <Paper
                    key={direction.id}
                    variant="outlined"
                    sx={{ p: 1.25 }}
                    data-testid={`seller-reserve-direction-row-${direction.id}`}
                  >
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
                  </Paper>
                ))}
              </Stack>
              <Divider />
              <Button onClick={closeReserves} data-testid="seller-reserves-close">
                Закрыть
              </Button>
            </Stack>
          </Box>
        ) : null}
      </Drawer>

      {stockDialogRows ? (
        <FbsStockDialogContainer
          token={token}
          sellerId={sellerId}
          sellerName={sellerName}
          chosen={stockDialogRows}
          warehouses={warehouses}
          canEditBindings={false}
          onClose={() => setStockDialogRows(null)}
          onChanged={() => void loadStock()}
          onLoadError={setError}
        />
      ) : null}
    </Box>
  )
}
