import { useEffect, useMemo, useState, type ReactNode } from 'react'
import {
  Box,
  Button,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  FormControl,
  InputLabel,
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
  seller_name?: string | null
}

/** @deprecated use WbProductPickerCatalogRow */
export type SellerWbCatalogRow = WbProductPickerCatalogRow

type PickerVariant = 'seller' | 'ff'

type Props = {
  open: boolean
  busy: boolean
  catalog: WbProductPickerCatalogRow[] | null
  disabledProductIds: Set<string>
  testIdPrefix: string
  qtyColumnLabel: string
  applyLabel?: string
  variant?: PickerVariant
  inDraftMessage?: string
  emptyMessage?: string
  showAvailableColumn?: boolean
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
  catalog,
  disabledProductIds,
  testIdPrefix,
  qtyColumnLabel,
  applyLabel = 'Добавить в заявку',
  variant = 'seller',
  inDraftMessage = 'Товар уже добавлен в заявку',
  emptyMessage,
  showAvailableColumn = false,
  getAvailable,
  filterRow,
  renderTrailingHeadCells,
  renderTrailingBodyCells,
  onClose,
  onApply,
}: Props) {
  const [pickerSearch, setPickerSearch] = useState('')
  const [pickerCategory, setPickerCategory] = useState('__all__')
  const [pickerQtyByProduct, setPickerQtyByProduct] = useState<Record<string, number>>({})

  useEffect(() => {
    if (!open) {
      setPickerSearch('')
      setPickerCategory('__all__')
      setPickerQtyByProduct({})
    }
  }, [open])

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
  const filteredPickerRows = useMemo(
    () => filterCatalogRows(catalog, pickerSearch, pickerCategory, filterRow),
    [catalog, filterRow, pickerCategory, pickerSearch],
  )

  const setPickerQty = (productId: string, qty: number) => {
    setPickerQtyByProduct((prev) => ({ ...prev, [productId]: qty }))
  }

  const handleClose = () => {
    if (busy) {
      return
    }
    onClose()
  }

  const handleApply = async () => {
    await onApply(pickerQtyByProduct)
  }

  const productColCount = variant === 'ff' ? 7 : 6
  const trailingColCount =
    (showAvailableColumn ? 1 : 0) + (renderTrailingHeadCells ? 1 : 0) + 1
  const totalColCount = productColCount + trailingColCount

  const qtyCell = (r: WbProductPickerCatalogRow, inDraft: boolean) => {
    const qty = pickerQtyByProduct[r.id] ?? 0
    const available = getAvailable?.(r.id) ?? 0
    return (
      <TableCell align="right" sx={{ minWidth: 120 }}>
        <TextField
          type="number"
          size="small"
          disabled={inDraft || busy}
          value={qty || ''}
          onChange={(e) => setPickerQty(r.id, Number(e.target.value))}
          slotProps={{
            htmlInput: {
              min: 0,
              ...(showAvailableColumn ? { max: available } : {}),
              'data-testid': `${testIdPrefix}-qty`,
            },
          }}
        />
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
          <TextField
            label="Поиск (артикул, ШК, nm, название, артикул продавца)"
            value={pickerSearch}
            onChange={(e) => setPickerSearch(e.target.value)}
            onKeyDown={(e) => {
              if (e.key !== 'Enter' || !catalog) {
                return
              }
              e.preventDefault()
              const productId = resolveProductIdByBarcode(catalog, pickerSearch)
              const targetId =
                productId ?? (filteredPickerRows.length === 1 ? filteredPickerRows[0]!.id : null)
              if (!targetId || disabledProductIds.has(targetId)) {
                return
              }
              setPickerQty(targetId, (pickerQtyByProduct[targetId] ?? 0) + 1)
              setPickerSearch('')
            }}
            size="small"
            fullWidth
            slotProps={{ htmlInput: { 'data-testid': `${testIdPrefix}-search` } }}
          />
          <FormControl size="small" sx={{ minWidth: 260 }}>
            <InputLabel id={`${testIdPrefix}-cat-label`}>Категория (WB)</InputLabel>
            <Select
              labelId={`${testIdPrefix}-cat-label`}
              label="Категория (WB)"
              value={pickerCategory}
              onChange={(e) => setPickerCategory(e.target.value)}
              data-testid={`${testIdPrefix}-category`}
            >
              <MenuItem value="__all__">Все</MenuItem>
              {categories.map((c) => (
                <MenuItem key={c} value={c}>
                  {c}
                </MenuItem>
              ))}
            </Select>
          </FormControl>
        </Stack>
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
                    Доступно
                  </TableCell>
                ) : null}
                <TableCell align="right" sx={{ width: 140 }}>
                  {qtyColumnLabel}
                </TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {filteredPickerRows.map((r) => {
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
                        <TableCell
                          sx={{ whiteSpace: 'normal', wordBreak: 'break-word', overflow: 'hidden' }}
                          title={r.wb_primary_barcode ?? (r.wb_barcodes[0] ?? '—')}
                        >
                          {r.wb_primary_barcode ?? (r.wb_barcodes[0] ?? '—')}
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
