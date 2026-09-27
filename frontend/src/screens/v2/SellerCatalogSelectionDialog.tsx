import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import {
  Alert,
  Button,
  Checkbox,
  CircularProgress,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
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
  TablePagination,
  TableRow,
  TextField,
  Typography,
} from '@mui/material'
import { apiUrl } from '../../api'
import { ProductPhotoThumb } from '../../components/ProductPhotoThumb'
import { readApiErrorMessage } from '../../utils/readApiErrorMessage'
import { MarketplaceChip, MARKETPLACE_LABELS, type MarketplaceKind } from '../../ui-kit'

// WMS-548 D4: окно выбора товаров, которое открывается сразу после первого
// сохранения ключа площадки (см. SellerSettingsScreen) и по контракту
// GET/POST /seller-catalog/... из документа требований (раздел «План
// реализации», кусок D2). Бэкенд этого контракта — отдельная задача (D2/D3);
// здесь строго его формат, без домыслов о внутреннем устройстве.

export type SellerCatalogMarketplace = 'wildberries' | 'ozon'

const ADD_TO_FULFILLMENT_CHUNK_SIZE = 500

function marketplaceKind(marketplace: SellerCatalogMarketplace): MarketplaceKind {
  return marketplace === 'wildberries' ? 'wb' : 'ozon'
}

function keyPrefix(marketplace: SellerCatalogMarketplace): string {
  return marketplace === 'wildberries' ? 'wb:' : 'ozon:'
}

// Строка ответа /seller-catalog/page: для товара на ФФ — поля сегодняшней
// строки /products/wb-catalog; для карточки не на ФФ — nm_id/ozon_product_id,
// vendor_code, name, photo_url, barcodes, sizes, category (контракт WMS-548).
export type SellerCatalogPageRow = {
  key: string
  on_fulfillment: boolean
  marketplace: SellerCatalogMarketplace
  name: string
  // товар на ФФ
  wb_vendor_code?: string | null
  wb_nm_id?: number | null
  wb_primary_image_url?: string | null
  wb_barcodes?: string[] | null
  wb_primary_barcode?: string | null
  wb_size?: string | null
  // карточка не на ФФ
  nm_id?: number | null
  ozon_product_id?: string | number | null
  vendor_code?: string | null
  photo_url?: string | null
  barcodes?: string[] | null
  sizes?: string[] | null
}

export type SellerCatalogPage = {
  items: SellerCatalogPageRow[]
  total: number
  scope_total: number
  categories: string[]
}

/** Единый вид строки для таблицы независимо от того, товар это на ФФ или ещё нет. */
export function displaySellerCatalogRow(row: SellerCatalogPageRow) {
  // Бэкенд всегда присылает оба массива ШК (пустым, а не null, для неактуальной
  // стороны — Pydantic default_factory=list), поэтому здесь нельзя merge-ить
  // через `??`: пустой wb_barcodes у карточки не на ФФ молча забивал бы
  // настоящий barcodes нулём найденных ШК.
  const wbBarcodes = row.wb_barcodes ?? []
  const genericBarcodes = row.barcodes ?? []
  const barcodes = wbBarcodes.length > 0 ? wbBarcodes : genericBarcodes
  const primaryBarcode = row.wb_primary_barcode ?? barcodes[0] ?? null
  const sizes = row.wb_size ? [row.wb_size] : (row.sizes ?? [])
  return {
    key: row.key,
    name: row.name,
    vendorCode: row.wb_vendor_code ?? row.vendor_code ?? null,
    photoUrl: row.wb_primary_image_url ?? row.photo_url ?? null,
    primaryBarcode,
    extraBarcodeCount: Math.max(barcodes.length - (primaryBarcode ? 1 : 0), 0),
    sizesText: sizes.length > 0 ? sizes.join(', ') : null,
    onFulfillment: row.on_fulfillment,
  }
}

function readKeysList(body: unknown): string[] {
  if (Array.isArray(body)) return body.filter((v): v is string => typeof v === 'string')
  if (body && typeof body === 'object' && Array.isArray((body as { keys?: unknown }).keys)) {
    return ((body as { keys: unknown[] }).keys).filter((v): v is string => typeof v === 'string')
  }
  return []
}

/** Все найденные фильтром ключи этой площадки, которых ещё нет на ФФ (для «выбрать всё найденное»). */
export async function fetchAddableSellerCatalogKeys(
  marketplace: SellerCatalogMarketplace,
  fetchImpl: typeof fetch,
  url: string,
  headers: Record<string, string>,
): Promise<string[]> {
  const res = await fetchImpl(url, { headers })
  if (!res.ok) {
    throw new Error(await readApiErrorMessage(res))
  }
  const keys = readKeysList(await res.json())
  const prefix = keyPrefix(marketplace)
  return keys.filter((k) => k.startsWith(prefix))
}

/**
 * Открывать ли окно после сохранения ключа (R1, решение А9): только при первом
 * ключе этой площадки (не при замене), если проверка прошла и у пользователя
 * есть право «Товары» — то же право, что открывает /seller-catalog (R14).
 */
export function shouldOpenCatalogSelectionAfterKeySave(params: {
  hadKeyBefore: boolean
  validationOk: boolean | undefined
  canManageProducts: boolean
}): boolean {
  return !params.hadKeyBefore && params.validationOk !== false && params.canManageProducts
}

/** Есть ли у селлера хоть одна карточка этой площадки — гейт открытия окна (R1). */
export async function hasAnySellerCatalogCards(
  fetchImpl: typeof fetch,
  url: string,
  headers: Record<string, string>,
): Promise<boolean> {
  try {
    const res = await fetchImpl(url, { headers })
    if (!res.ok) return false
    const body = (await res.json()) as { scope_total?: number }
    return (body.scope_total ?? 0) > 0
  } catch {
    return false
  }
}

export function chunkKeys<T>(items: T[], size: number): T[][] {
  const out: T[][] = []
  for (let i = 0; i < items.length; i += size) {
    out.push(items.slice(i, i + size))
  }
  return out
}

/** Тело POST /seller-catalog/add-to-fulfillment для одной площадки. */
export function buildAddToFulfillmentPayload(
  keys: string[],
  marketplace: SellerCatalogMarketplace,
): { wb_nm_ids: number[]; ozon_product_ids: string[] } {
  if (marketplace === 'wildberries') {
    const wb_nm_ids = keys
      .filter((k) => k.startsWith('wb:'))
      .map((k) => Number(k.slice(3)))
      .filter((n) => Number.isFinite(n))
    return { wb_nm_ids, ozon_product_ids: [] }
  }
  const ozon_product_ids = keys.filter((k) => k.startsWith('ozon:')).map((k) => k.slice(5))
  return { wb_nm_ids: [], ozon_product_ids }
}

function entryValue(entry: Record<string, unknown>, keys: string[]): unknown {
  for (const key of keys) {
    if (entry[key] != null) return entry[key]
  }
  return null
}

function entryKey(entry: Record<string, unknown>, marketplace: SellerCatalogMarketplace): string | null {
  const id = entryValue(entry, ['id', 'nm_id', 'ozon_product_id', 'wb_nm_id'])
  if (id == null) return null
  return `${keyPrefix(marketplace)}${id}`
}

function entryVendorCode(entry: Record<string, unknown>): string | null {
  const v = entryValue(entry, ['vendor_code', 'offer_id', 'wb_vendor_code'])
  return typeof v === 'string' ? v : null
}

function entryReason(entry: Record<string, unknown>): string {
  const v = entry.reason
  return typeof v === 'string' ? v : 'не удалось добавить'
}

export type AddToFulfillmentOutcome = {
  addedKeys: string[]
  skipped: Array<{ vendorCode: string | null; reason: string }>
  failureMessage: string | null
}

/**
 * Отправляет отмеченные ключи порциями (R9, R15): порция сохраняется сама, обрыв
 * на середине не теряет уже добавленное — обработка останавливается на первой же
 * неудачной порции, а её ключи (и все последующие) остаются в выделении для повтора.
 */
export async function addKeysToFulfillment(
  keys: string[],
  marketplace: SellerCatalogMarketplace,
  fetchImpl: typeof fetch,
  url: string,
  headers: Record<string, string>,
  chunkSize = ADD_TO_FULFILLMENT_CHUNK_SIZE,
): Promise<AddToFulfillmentOutcome> {
  const addedKeys: string[] = []
  const skipped: Array<{ vendorCode: string | null; reason: string }> = []
  for (const chunk of chunkKeys(keys, chunkSize)) {
    const payload = buildAddToFulfillmentPayload(chunk, marketplace)
    let res: Response
    try {
      res = await fetchImpl(url, {
        method: 'POST',
        headers: { ...headers, 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      })
    } catch (e) {
      return {
        addedKeys,
        skipped,
        failureMessage: e instanceof Error ? e.message : 'Не удалось добавить товары.',
      }
    }
    if (!res.ok) {
      return { addedKeys, skipped, failureMessage: await readApiErrorMessage(res) }
    }
    const body = (await res.json()) as { added?: unknown[]; skipped?: unknown[] }
    for (const raw of body.added ?? []) {
      const rec = raw as Record<string, unknown>
      const key = entryKey(rec, marketplace)
      if (key) addedKeys.push(key)
    }
    for (const raw of body.skipped ?? []) {
      const rec = raw as Record<string, unknown>
      skipped.push({ vendorCode: entryVendorCode(rec), reason: entryReason(rec) })
    }
  }
  return { addedKeys, skipped, failureMessage: null }
}

type Props = {
  marketplace: SellerCatalogMarketplace
  token: string
  authHeaders: (t: string) => Record<string, string>
  onClose: () => void
  onAdded?: () => void | Promise<void>
}

export function SellerCatalogSelectionDialog({ marketplace, token, authHeaders, onClose, onAdded }: Props) {
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [items, setItems] = useState<SellerCatalogPageRow[]>([])
  const [total, setTotal] = useState(0)
  const [scopeTotal, setScopeTotal] = useState(0)
  const [categories, setCategories] = useState<string[]>([])
  const [search, setSearch] = useState('')
  const [debouncedSearch, setDebouncedSearch] = useState('')
  const [category, setCategory] = useState('')
  const [page, setPage] = useState(0)
  const [rowsPerPage, setRowsPerPage] = useState(100)
  const [selectedKeys, setSelectedKeys] = useState<Set<string>>(new Set())
  const [selectAllBusy, setSelectAllBusy] = useState(false)
  const [addBusy, setAddBusy] = useState(false)
  const [addError, setAddError] = useState<string | null>(null)
  const abortRef = useRef<AbortController | null>(null)

  useEffect(() => {
    const timeout = window.setTimeout(() => setDebouncedSearch(search.trim()), 250)
    return () => window.clearTimeout(timeout)
  }, [search])

  useEffect(() => {
    setPage(0)
  }, [debouncedSearch, category])

  const load = useCallback(async () => {
    abortRef.current?.abort()
    const controller = new AbortController()
    abortRef.current = controller
    setError(null)
    setBusy(true)
    try {
      const params = new URLSearchParams({
        marketplace,
        on_fulfillment: 'all',
        limit: String(rowsPerPage),
        offset: String(page * rowsPerPage),
      })
      if (debouncedSearch) params.set('search', debouncedSearch)
      if (category) params.set('category', category)
      const res = await fetch(apiUrl(`/seller-catalog/page?${params.toString()}`), {
        headers: { ...authHeaders(token) },
        signal: controller.signal,
      })
      if (!res.ok) {
        throw new Error(await readApiErrorMessage(res))
      }
      const body = (await res.json()) as SellerCatalogPage
      if (controller.signal.aborted) return
      setItems(body.items)
      setTotal(body.total)
      setScopeTotal(body.scope_total)
      setCategories(body.categories)
    } catch (e) {
      if ((e as { name?: string }).name === 'AbortError') return
      setError(e instanceof Error ? e.message : 'Не удалось загрузить товары.')
    } finally {
      if (abortRef.current === controller) setBusy(false)
    }
  }, [authHeaders, category, debouncedSearch, marketplace, page, rowsPerPage, token])

  useEffect(() => {
    void load()
    return () => abortRef.current?.abort()
  }, [load])

  const rows = useMemo(() => items.map((row) => ({ raw: row, view: displaySellerCatalogRow(row) })), [items])

  const visibleAddableKeys = useMemo(
    () => rows.filter((r) => !r.view.onFulfillment).map((r) => r.view.key),
    [rows],
  )
  const visibleSelectedCount = useMemo(
    () => visibleAddableKeys.filter((k) => selectedKeys.has(k)).length,
    [selectedKeys, visibleAddableKeys],
  )
  const allVisibleSelected = visibleAddableKeys.length > 0 && visibleSelectedCount === visibleAddableKeys.length
  const someVisibleSelected = visibleSelectedCount > 0 && !allVisibleSelected
  const selectedCount = selectedKeys.size

  const toggleKey = useCallback((key: string, checked: boolean) => {
    setSelectedKeys((current) => {
      const next = new Set(current)
      if (checked) next.add(key)
      else next.delete(key)
      return next
    })
  }, [])

  const toggleVisible = useCallback(
    (checked: boolean) => {
      setSelectedKeys((current) => {
        const next = new Set(current)
        for (const key of visibleAddableKeys) {
          if (checked) next.add(key)
          else next.delete(key)
        }
        return next
      })
    },
    [visibleAddableKeys],
  )

  async function selectAllFound() {
    setSelectAllBusy(true)
    setError(null)
    try {
      const params = new URLSearchParams({ marketplace, on_fulfillment: 'all' })
      if (debouncedSearch) params.set('search', debouncedSearch)
      if (category) params.set('category', category)
      const keys = await fetchAddableSellerCatalogKeys(
        marketplace,
        fetch,
        apiUrl(`/seller-catalog/keys?${params.toString()}`),
        { ...authHeaders(token) },
      )
      setSelectedKeys(new Set(keys))
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Не удалось выбрать все найденные товары.')
    } finally {
      setSelectAllBusy(false)
    }
  }

  async function onAddToFulfillment() {
    const keys = [...selectedKeys]
    if (keys.length === 0) return
    setAddBusy(true)
    setAddError(null)
    try {
      const outcome = await addKeysToFulfillment(
        keys,
        marketplace,
        fetch,
        apiUrl('/seller-catalog/add-to-fulfillment'),
        { ...authHeaders(token) },
      )
      if (outcome.addedKeys.length > 0) {
        setSelectedKeys((current) => {
          const next = new Set(current)
          for (const k of outcome.addedKeys) next.delete(k)
          return next
        })
      }
      const parts: string[] = []
      if (outcome.failureMessage) parts.push(outcome.failureMessage)
      if (outcome.skipped.length > 0) {
        parts.push(`Не добавлены: ${outcome.skipped.map((s) => s.vendorCode ?? '—').join(', ')}`)
      }
      setAddError(parts.length > 0 ? parts.join(' ') : null)
      await load()
      if (outcome.addedKeys.length > 0) {
        await onAdded?.()
      }
    } finally {
      setAddBusy(false)
    }
  }

  const kind = marketplaceKind(marketplace)

  return (
    <Dialog open onClose={() => (addBusy ? undefined : onClose())} fullWidth maxWidth="xl" data-testid="seller-catalog-selection-dialog">
      <DialogTitle>Товары {MARKETPLACE_LABELS[kind]}</DialogTitle>
      <DialogContent>
        {error ? (
          <Alert severity="error" sx={{ mb: 2 }} data-testid="seller-catalog-selection-error">
            {error}
          </Alert>
        ) : null}
        {addError ? (
          <Alert severity="error" sx={{ mb: 2 }} data-testid="seller-catalog-selection-add-error">
            {addError}
          </Alert>
        ) : null}

        <Paper variant="outlined" sx={{ p: 2, mb: 2 }} data-testid="seller-catalog-selection-filters">
          <Stack direction={{ xs: 'column', sm: 'row' }} spacing={2} sx={{ alignItems: { sm: 'center' }, flexWrap: 'wrap', rowGap: 2 }}>
            <TextField
              size="small"
              placeholder="Поиск по названию, артикулу или ШК"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              slotProps={{ htmlInput: { 'data-testid': 'seller-catalog-selection-search' } }}
              sx={{ minWidth: 260 }}
            />
            <FormControl size="small" sx={{ minWidth: 200 }}>
              <InputLabel id="seller-catalog-selection-category-label">Категория</InputLabel>
              <Select
                labelId="seller-catalog-selection-category-label"
                label="Категория"
                value={category}
                onChange={(e) => setCategory(e.target.value)}
                data-testid="seller-catalog-selection-category"
              >
                <MenuItem value="">Все категории</MenuItem>
                {categories.map((c) => (
                  <MenuItem key={c} value={c}>
                    {c}
                  </MenuItem>
                ))}
              </Select>
            </FormControl>
            <Typography variant="body2" color="text.secondary" data-testid="seller-catalog-selection-count">
              {busy ? 'Загрузка…' : `Найдено: ${total} из ${scopeTotal}`}
            </Typography>
            <Button
              size="small"
              onClick={() => void selectAllFound()}
              disabled={selectAllBusy || total === 0}
              data-testid="seller-catalog-selection-select-all-found"
            >
              {selectAllBusy ? 'Выбираем…' : `Выбрать все найденные (${total})`}
            </Button>
            {busy ? <CircularProgress size={18} /> : null}
          </Stack>
        </Paper>

        <TableContainer component={Paper} variant="outlined" sx={{ width: '100%', maxWidth: '100%' }} data-testid="seller-catalog-selection-list">
          <Table stickyHeader size="small" data-testid="seller-catalog-selection-table">
            <TableHead>
              <TableRow>
                <TableCell padding="checkbox">
                  <Checkbox
                    size="small"
                    checked={allVisibleSelected}
                    indeterminate={someVisibleSelected}
                    disabled={visibleAddableKeys.length === 0}
                    onChange={(e) => toggleVisible(e.target.checked)}
                    slotProps={{ input: { 'aria-label': 'Выбрать карточки на странице' } }}
                    data-testid="seller-catalog-selection-select-all"
                  />
                </TableCell>
                <TableCell>Фото</TableCell>
                <TableCell>Название</TableCell>
                <TableCell>Артикул продавца</TableCell>
                <TableCell>ШК</TableCell>
                <TableCell>Размер</TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {rows.map(({ raw, view }) => (
                <TableRow key={view.key} hover data-testid="seller-catalog-selection-row">
                  <TableCell padding="checkbox">
                    <Checkbox
                      size="small"
                      checked={view.onFulfillment || selectedKeys.has(view.key)}
                      disabled={view.onFulfillment}
                      onChange={(e) => toggleKey(view.key, e.target.checked)}
                      slotProps={{ input: { 'aria-label': `Выбрать ${view.vendorCode ?? view.name}` } }}
                      data-testid={`seller-catalog-selection-select-${view.key}`}
                    />
                  </TableCell>
                  <TableCell>
                    <ProductPhotoThumb src={view.photoUrl} />
                  </TableCell>
                  <TableCell>
                    <Typography
                      variant="body2"
                      title={view.name}
                      sx={{ display: '-webkit-box', WebkitLineClamp: 2, WebkitBoxOrient: 'vertical', overflow: 'hidden' }}
                    >
                      {view.name}
                    </Typography>
                  </TableCell>
                  <TableCell>
                    <Stack direction="row" spacing={0.75} sx={{ alignItems: 'center', flexWrap: 'wrap' }}>
                      <Typography variant="body2">{view.vendorCode ?? '—'}</Typography>
                      <MarketplaceChip marketplace={marketplaceKind(raw.marketplace)} testId={`seller-catalog-selection-marketplace-${view.key}`} />
                    </Stack>
                  </TableCell>
                  <TableCell>
                    <Typography variant="body2" noWrap title={view.primaryBarcode ?? '—'}>
                      {view.primaryBarcode ?? '—'}
                    </Typography>
                    {view.extraBarcodeCount > 0 ? (
                      <Typography variant="caption" color="text.secondary">
                        +{view.extraBarcodeCount}
                      </Typography>
                    ) : null}
                  </TableCell>
                  <TableCell>
                    <Typography variant="body2" noWrap title={view.sizesText ?? '—'}>
                      {view.sizesText ?? '—'}
                    </Typography>
                  </TableCell>
                </TableRow>
              ))}
              {rows.length === 0 && !busy ? (
                <TableRow>
                  <TableCell colSpan={6}>
                    <Typography variant="body2" color="text.secondary" data-testid="seller-catalog-selection-empty">
                      Ничего не найдено.
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
              setRowsPerPage(Number(e.target.value))
              setPage(0)
            }}
            rowsPerPageOptions={[50, 100, 200]}
            labelRowsPerPage="На странице"
            data-testid="seller-catalog-selection-pagination"
          />
        </TableContainer>
      </DialogContent>
      <DialogActions>
        <Button onClick={onClose} disabled={addBusy} data-testid="seller-catalog-selection-close">
          Закрыть
        </Button>
        <Button
          variant="contained"
          onClick={() => void onAddToFulfillment()}
          disabled={addBusy || selectedCount === 0}
          data-testid="seller-catalog-selection-add"
        >
          {addBusy ? 'Добавляем…' : `Добавить к фулфилменту · ${selectedCount}`}
        </Button>
      </DialogActions>
    </Dialog>
  )
}
