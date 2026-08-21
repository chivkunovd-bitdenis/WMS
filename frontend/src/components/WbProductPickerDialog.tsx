import { useEffect, useMemo, useState, type ReactNode } from 'react'
import {
  Alert,
  Box,
  Button,
  Checkbox,
  CircularProgress,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  FormControl,
  InputLabel,
  ListItemText,
  MenuItem,
  Select,
  Stack,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  TextField,
  Typography,
} from '@mui/material'
import { FfProductLineCells, FfProductTableHeadCells } from './FfProductLineCells'
import { ProductPhotoThumb } from './ProductPhotoThumb'
import { ProductBarcodeCell } from './ProductBarcodeCell'
import {
  productDisplayMetaFromCatalog,
  type WbProductCatalogRow,
} from '../types/wbProductCatalog'
import { resolveProductIdByBarcode } from '../utils/resolveProductByBarcode'

export type WbProductPickerCatalogRow = {
  id: string
  name: string
  sku_code: string
  wb_nm_id: number | null
  wb_vendor_code: string | null
  wb_subject_name: string | null
  wb_primary_image_url: string | null
  wb_barcodes: string[]
  wb_primary_barcode?: string | null
  wb_size?: string | null
  wb_composition?: string | null
  seller_name?: string | null
}

/** @deprecated use WbProductPickerCatalogRow */
export type SellerWbCatalogRow = WbProductPickerCatalogRow

type PickerVariant = 'seller' | 'ff'

type Props = {
  open: boolean
  busy: boolean
  /** Каталог ещё едет с сервера: окно уже открыто, таблицы пока нет. */
  catalogLoading?: boolean
  /**
   * Поиск идёт на сервере: в каталоге больше товаров, чем разумно грузить в браузер.
   * Тогда фильтр по категориям прячется — он считается по загруженным строкам и на
   * неполной выборке врал бы, — а сам поиск уходит наружу через onSearchChange.
   */
  serverSearch?: boolean
  onSearchChange?: (value: string) => void
  catalog: WbProductPickerCatalogRow[] | null
  disabledProductIds: Set<string>
  testIdPrefix: string
  qtyColumnLabel: string
  applyLabel?: string
  initialSearch?: string
  variant?: PickerVariant
  inDraftMessage?: string
  emptyMessage?: string
  showAvailableColumn?: boolean
  availableColumnLabel?: string
  getAvailable?: (productId: string) => number
  filterRow?: (row: WbProductPickerCatalogRow) => boolean
  renderTrailingHeadCells?: ReactNode
  renderTrailingBodyCells?: (row: WbProductPickerCatalogRow) => ReactNode
  onClose: () => void
  onApply: (selections: Record<string, number>) => void | Promise<void>
}

function wbCategories(catalog: WbProductPickerCatalogRow[] | null): string[] {
  if (!catalog) {
    return []
  }
  const s = new Set<string>()
  for (const r of catalog) {
    const c = r.wb_subject_name?.trim()
    if (c) {
      s.add(c)
    }
  }
  return Array.from(s).sort((a, b) => a.localeCompare(b))
}

function filterCatalogRows(
  catalog: WbProductPickerCatalogRow[] | null,
  search: string,
  category: string,
  filterRow?: (row: WbProductPickerCatalogRow) => boolean,
): WbProductPickerCatalogRow[] {
  if (!catalog) {
    return []
  }
  const q = search.trim().toLowerCase()
  return catalog.filter((r) => {
    if (filterRow && !filterRow(r)) {
      return false
    }
    if (category !== '__all__') {
      const sub = (r.wb_subject_name ?? '').trim()
      if (sub !== category) {
        return false
      }
    }
    if (!q) {
      return true
    }
    const nm = r.wb_nm_id != null ? String(r.wb_nm_id) : ''
    const barcodes = r.wb_barcodes.join(' ').toLowerCase()
    const hay = `${r.sku_code} ${r.wb_vendor_code ?? ''} ${r.name} ${nm} ${barcodes}`.toLowerCase()
    return hay.includes(q)
  })
}

function inDraftCaption(message: string): ReactNode {
  return (
    <Typography variant="caption" color="text.secondary" sx={{ display: 'block' }} noWrap>
      {message}
    </Typography>
  )
}

export function WbProductPickerDialog({
  open,
  busy,
  catalogLoading = false,
  serverSearch = false,
  onSearchChange,
  catalog,
  disabledProductIds,
  testIdPrefix,
  qtyColumnLabel,
  applyLabel = 'Добавить в заявку',
  initialSearch = '',
  variant = 'seller',
  inDraftMessage = 'Товар уже добавлен в заявку',
  emptyMessage,
  showAvailableColumn = false,
  availableColumnLabel = 'Доступно',
  getAvailable,
  filterRow,
  renderTrailingHeadCells,
  renderTrailingBodyCells,
  onClose,
  onApply,
}: Props) {
  const [pickerSearch, setPickerSearch] = useState('')
  const [pickerCategories, setPickerCategories] = useState<string[]>([])
  const [pickerQtyByProduct, setPickerQtyByProduct] = useState<Record<string, number>>({})
  const [selectedProductIds, setSelectedProductIds] = useState<Set<string>>(() => new Set())
  const [bulkQty, setBulkQty] = useState('')
  const [pickerError, setPickerError] = useState<string | null>(null)
  const [lastScannedProductId, setLastScannedProductId] = useState<string | null>(null)

  useEffect(() => {
    setPickerSearch(open ? initialSearch : '')
    if (open) {
      onSearchChange?.(initialSearch)
    }
    setPickerCategories([])
    setPickerQtyByProduct({})
    setSelectedProductIds(new Set())
    setBulkQty('')
    setPickerError(null)
    setLastScannedProductId(null)
  }, [initialSearch, open])

  const catalogById = useMemo(() => {
    const m = new Map<string, WbProductCatalogRow>()
    if (catalog) {
      for (const r of catalog) {
        m.set(r.id, r as WbProductCatalogRow)
      }
    }
    return m
  }, [catalog])

  const categories = useMemo(() => wbCategories(catalog), [catalog])
  /**
   * Потолок отрисовки. 21.08.2026: у продавца с 9266 товарами окно выбора рисовало
   * все строки разом — с фотографией, галкой и полем ввода в каждой. Вкладка
   * замирала намертво, и человек считал, что кнопка не работает. Поиск и выбор
   * по-прежнему идут по всему каталогу: ограничена только отрисовка.
   */
  const PICKER_VISIBLE_LIMIT = 200
  const filteredPickerRows = useMemo(
    () => {
      if (!catalog) {
        return []
      }
      const bySearch = filterCatalogRows(catalog, pickerSearch, '__all__', filterRow)
      const byCategory = pickerCategories.length === 0 ? bySearch : bySearch.filter((row) => {
        const category = row.wb_subject_name?.trim()
        return Boolean(category && pickerCategories.includes(category))
      })
      if (!lastScannedProductId) {
        return byCategory
      }
      return [...byCategory].sort((a, b) => {
        if (a.id === lastScannedProductId) return -1
        if (b.id === lastScannedProductId) return 1
        return 0
      })
    },
    [catalog, filterRow, lastScannedProductId, pickerCategories, pickerSearch],
  )

  const setPickerQty = (productId: string, qty: number) => {
    setPickerQtyByProduct((prev) => ({ ...prev, [productId]: qty }))
    setSelectedProductIds((prev) => {
      const next = new Set(prev)
      if (Number.isFinite(qty) && qty > 0) {
        next.add(productId)
      }
      return next
    })
  }

  const incrementPickerQty = (productId: string) => {
    setPickerQtyByProduct((prev) => ({ ...prev, [productId]: (prev[productId] ?? 0) + 1 }))
    setSelectedProductIds((prev) => {
      const next = new Set(prev)
      next.add(productId)
      return next
    })
  }

  const toggleSelected = (productId: string, checked: boolean) => {
    setSelectedProductIds((prev) => {
      const next = new Set(prev)
      if (checked) {
        next.add(productId)
        setPickerQtyByProduct((qtyPrev) => ({
          ...qtyPrev,
          [productId]: qtyPrev[productId] && qtyPrev[productId] > 0 ? qtyPrev[productId]! : 1,
        }))
      } else {
        next.delete(productId)
      }
      return next
    })
  }

  const visiblePickerRows = useMemo(
    () => filteredPickerRows.slice(0, PICKER_VISIBLE_LIMIT),
    [filteredPickerRows],
  )
  const hiddenPickerRowsCount = filteredPickerRows.length - visiblePickerRows.length

  const selectCurrentRows = () => {
    const selectable = filteredPickerRows.filter((row) => !disabledProductIds.has(row.id))
    setSelectedProductIds((prev) => {
      const next = new Set(prev)
      for (const row of selectable) {
        next.add(row.id)
      }
      return next
    })
    setPickerQtyByProduct((prev) => {
      const next = { ...prev }
      for (const row of selectable) {
        if (!next[row.id] || next[row.id] < 1) {
          next[row.id] = 1
        }
      }
      return next
    })
  }

  const applyBulkQty = () => {
    const n = Math.floor(Number(bulkQty))
    if (!Number.isFinite(n) || n < 1) {
      setPickerError('Укажите количество для отмеченных строк.')
      return
    }
    setPickerQtyByProduct((prev) => {
      const next = { ...prev }
      for (const productId of selectedProductIds) {
        if (!disabledProductIds.has(productId)) {
          next[productId] = n
        }
      }
      return next
    })
    setPickerError(null)
  }

  const handleClose = () => {
    if (busy) {
      return
    }
    onClose()
  }

  const handleApply = async () => {
    const selections: Record<string, number> = {}
    for (const productId of selectedProductIds) {
      const qty = pickerQtyByProduct[productId] ?? 0
      if (qty > 0 && !disabledProductIds.has(productId)) {
        selections[productId] = qty
      }
    }
    await onApply(selections)
  }

  const productColCount = variant === 'ff' ? 7 : 6
  const trailingColCount =
    (showAvailableColumn ? 1 : 0) + (renderTrailingHeadCells ? 1 : 0) + 1
  const totalColCount = productColCount + trailingColCount
  const pickerErrorTestId =
    testIdPrefix === 'ff-inbound-picker'
      ? `${testIdPrefix}-scan-error`
      : `${testIdPrefix}-error`
  const notFoundMessage =
    testIdPrefix === 'seller-inbound-picker'
      ? 'Товар с таким штрихкодом не найден в каталоге'
      : 'Товар не найден в каталоге селлера'

  const qtyCell = (r: WbProductPickerCatalogRow, inDraft: boolean) => {
    const qty = pickerQtyByProduct[r.id] ?? 0
    const available = getAvailable?.(r.id) ?? 0
    return (
      <TableCell align="right" sx={{ minWidth: 120 }}>
        <Stack direction="row" spacing={0.5} sx={{ alignItems: 'center', justifyContent: 'flex-end' }}>
          <Checkbox
            size="small"
            checked={selectedProductIds.has(r.id)}
            disabled={inDraft || busy}
            onChange={(_, checked) => toggleSelected(r.id, checked)}
            data-testid={`${testIdPrefix}-select-row`}
          />
          <TextField
            type="number"
            size="small"
            disabled={inDraft || busy}
            value={qty || ''}
            onChange={(e) => setPickerQty(r.id, Number(e.target.value))}
            sx={{ width: 86 }}
            slotProps={{
              htmlInput: {
                min: 0,
                ...(showAvailableColumn ? { max: available } : {}),
                'data-testid': `${testIdPrefix}-qty`,
              },
            }}
          />
        </Stack>
      </TableCell>
    )
  }

  return (
    <Dialog
      open={open}
      onClose={handleClose}
      maxWidth={false}
      fullWidth
      slotProps={{ paper: { sx: { width: 'min(1200px, 96vw)', maxHeight: '92vh' } } }}
      data-testid={testIdPrefix}
    >
      <DialogTitle>Выбор товаров</DialogTitle>
      <DialogContent dividers>
        <Stack spacing={2} sx={{ mb: 2 }}>
          {pickerError ? (
            <Alert severity="warning" data-testid={pickerErrorTestId}>
              {pickerError}
            </Alert>
          ) : null}
          <TextField
            label="Поиск (артикул, ШК, артикул WB, название, артикул продавца)"
            value={pickerSearch}
            onChange={(e) => {
              setPickerSearch(e.target.value)
              setPickerError(null)
              onSearchChange?.(e.target.value)
            }}
            onKeyDown={(e) => {
              if (e.key !== 'Enter' || !catalog) {
                return
              }
              e.preventDefault()
              const input = e.currentTarget.querySelector('input')
              const rawSearch = input?.value || (e.target as HTMLInputElement).value || pickerSearch
              const productId = resolveProductIdByBarcode(catalog, rawSearch)
              const targetId =
                productId ?? (filteredPickerRows.length === 1 ? filteredPickerRows[0]!.id : null)
              if (!targetId) {
                setPickerError(notFoundMessage)
                return
              }
              if (disabledProductIds.has(targetId)) {
                setPickerError(inDraftMessage)
                return
              }
              incrementPickerQty(targetId)
              setLastScannedProductId(targetId)
              setPickerSearch('')
              setPickerError(null)
            }}
            size="small"
            fullWidth
            slotProps={{ htmlInput: { 'data-testid': `${testIdPrefix}-search` } }}
          />
          <Stack direction={{ xs: 'column', md: 'row' }} spacing={1.5} sx={{ alignItems: { md: 'center' } }}>
            {/* Фильтр по категориям считается по загруженным строкам. Когда каталог
                большой и приходит частями, полного списка категорий у экрана нет —
                показывать неполный значит врать, поэтому фильтр прячется. */}
            <FormControl size="small" sx={{ minWidth: 260, display: serverSearch ? 'none' : undefined }}>
              <InputLabel id={`${testIdPrefix}-cat-label`}>Категории WB</InputLabel>
              <Select
                multiple
                labelId={`${testIdPrefix}-cat-label`}
                label="Категории WB"
                value={pickerCategories}
                onChange={(e) => {
                  const value = e.target.value
                  setPickerCategories(typeof value === 'string' ? value.split(',') : value)
                }}
                renderValue={(selected) =>
                  selected.length === 0 ? 'Все категории' : `${selected.length} категорий`
                }
                data-testid={`${testIdPrefix}-category`}
              >
                {categories.map((c) => (
                  <MenuItem key={c} value={c}>
                    <Checkbox checked={pickerCategories.includes(c)} size="small" />
                    <ListItemText primary={c} />
                  </MenuItem>
                ))}
              </Select>
            </FormControl>
            <Button
              variant="outlined"
              onClick={selectCurrentRows}
              disabled={busy || filteredPickerRows.every((row) => disabledProductIds.has(row.id))}
              data-testid={`${testIdPrefix}-select-all`}
            >
              Выбрать все
            </Button>
            <TextField
              label="Проставить всем"
              type="number"
              size="small"
              value={bulkQty}
              onChange={(e) => setBulkQty(e.target.value)}
              sx={{ width: 160 }}
              slotProps={{ htmlInput: { min: 1, 'data-testid': `${testIdPrefix}-bulk-qty` } }}
            />
            <Button
              variant="outlined"
              onClick={applyBulkQty}
              disabled={busy || selectedProductIds.size === 0}
              data-testid={`${testIdPrefix}-bulk-apply`}
            >
              Проставить
            </Button>
          </Stack>
        </Stack>
        {catalogLoading ? (
          <Stack
            direction="row"
            spacing={1.5}
            sx={{ alignItems: 'center', py: 3 }}
            data-testid={`${testIdPrefix}-loading`}
          >
            <CircularProgress size={22} />
            <Typography variant="body2">Загружаем каталог товаров…</Typography>
          </Stack>
        ) : null}
        {serverSearch || hiddenPickerRowsCount > 0 ? (
          <Alert severity="info" sx={{ mb: 1 }} data-testid={`${testIdPrefix}-limited`}>
            {serverSearch
              ? `В каталоге товаров больше, чем показано (${visiblePickerRows.length}). Введите артикул, штрихкод, номер WB или часть названия — поиск идёт по всему каталогу.`
              : `Показаны первые ${visiblePickerRows.length} товаров из ${filteredPickerRows.length}. Уточните поиск, чтобы увидеть нужный.`}
          </Alert>
        ) : null}
        <TableContainer sx={{ width: '100%', overflowX: 'hidden' }}>
          <Table
            size="small"
            data-testid={`${testIdPrefix}-table`}
            sx={{
              tableLayout: 'fixed',
              width: '100%',
              '& th': { py: 1.25 },
              '& td': { py: 1.25 },
            }}
          >
            <TableHead>
              <TableRow>
                {variant === 'ff' ? (
                  <FfProductTableHeadCells />
                ) : (
                  <>
                    <TableCell sx={{ width: 56 }}>Фото</TableCell>
                    <TableCell sx={{ width: 160, pl: 2 }}>Артикул</TableCell>
                    <TableCell sx={{ width: 190 }}>ШК</TableCell>
                    <TableCell sx={{ width: 150 }}>Артикул продавца</TableCell>
                    <TableCell sx={{ width: 120, pr: 2 }}>Артикул WB</TableCell>
                    <TableCell sx={{ pl: 2 }}>Наименование</TableCell>
                  </>
                )}
                {renderTrailingHeadCells}
                {showAvailableColumn ? (
                  <TableCell align="right" sx={{ width: 110 }}>
                    {availableColumnLabel}
                  </TableCell>
                ) : null}
                <TableCell align="right" sx={{ width: 140 }}>
                  {qtyColumnLabel}
                </TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {visiblePickerRows.map((r) => {
                const inDraft = disabledProductIds.has(r.id)
                const available = getAvailable?.(r.id) ?? 0
                return (
                  <TableRow
                    key={r.id}
                    hover
                    sx={{
                      opacity: inDraft ? 0.45 : 1,
                      bgcolor: inDraft ? 'action.hover' : undefined,
                      '& td': { px: 1.25 },
                      '& td:first-of-type': { pl: 1 },
                      '& td:last-of-type': { pr: 1 },
                    }}
                    data-testid={`${testIdPrefix}-row`}
                    data-in-draft={inDraft ? '1' : '0'}
                  >
                    {variant === 'ff' ? (
                      <FfProductLineCells
                        meta={productDisplayMetaFromCatalog(
                          r.id,
                          { sku_code: r.sku_code, name: r.name },
                          catalogById,
                        )}
                        printTestId={`${testIdPrefix}-print-${r.id}`}
                        nameExtra={inDraft ? inDraftCaption(inDraftMessage) : null}
                      />
                    ) : (
                      <>
                        <TableCell>
                          <ProductPhotoThumb src={r.wb_primary_image_url} />
                        </TableCell>
                        <TableCell
                          sx={{
                            whiteSpace: 'normal',
                            wordBreak: 'break-word',
                            overflow: 'hidden',
                            pl: 2,
                          }}
                          title={r.sku_code}
                        >
                          {r.sku_code}
                        </TableCell>
                        <TableCell sx={{ maxWidth: 190 }}>
                          <ProductBarcodeCell
                            barcode={r.wb_primary_barcode ?? r.wb_barcodes[0] ?? null}
                            wb_size={r.wb_size}
                            wb_composition={r.wb_composition}
                          />
                        </TableCell>
                        <TableCell
                          sx={{ whiteSpace: 'normal', wordBreak: 'break-word', overflow: 'hidden' }}
                          title={r.wb_vendor_code ?? '—'}
                        >
                          {r.wb_vendor_code ?? '—'}
                        </TableCell>
                        <TableCell sx={{ pr: 2 }}>{r.wb_nm_id ?? '—'}</TableCell>
                        <TableCell
                          sx={{
                            pl: 2,
                            maxWidth: 440,
                            whiteSpace: 'nowrap',
                            overflow: 'hidden',
                            textOverflow: 'ellipsis',
                          }}
                          title={r.name}
                        >
                          <Typography variant="body2" sx={{ lineHeight: 1.25 }} noWrap>
                            {r.name}
                          </Typography>
                          {inDraft ? inDraftCaption(inDraftMessage) : null}
                        </TableCell>
                      </>
                    )}
                    {renderTrailingBodyCells?.(r)}
                    {showAvailableColumn ? (
                      <TableCell align="right">{available}</TableCell>
                    ) : null}
                    {qtyCell(r, inDraft)}
                  </TableRow>
                )
              })}
              {filteredPickerRows.length === 0 && emptyMessage ? (
                <TableRow>
                  <TableCell colSpan={totalColCount}>
                    <Box sx={{ py: 1 }}>
                      <Typography variant="body2" color="text.secondary">
                        {emptyMessage}
                      </Typography>
                    </Box>
                  </TableCell>
                </TableRow>
              ) : null}
            </TableBody>
          </Table>
        </TableContainer>
      </DialogContent>
      <DialogActions>
        <Button onClick={handleClose} disabled={busy} data-testid={`${testIdPrefix}-cancel`}>
          Отмена
        </Button>
        <Button
          variant="contained"
          onClick={() => void handleApply()}
          disabled={busy}
          data-testid={`${testIdPrefix}-apply`}
        >
          {applyLabel}
        </Button>
      </DialogActions>
    </Dialog>
  )
}

/** @deprecated use WbProductPickerDialog */
export const SellerWbProductPickerDialog = WbProductPickerDialog
