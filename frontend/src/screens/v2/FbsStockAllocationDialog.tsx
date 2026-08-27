import { useMemo, useState } from 'react'
import { Link as RouterLink } from 'react-router-dom'
import {
  Alert,
  Box,
  Button,
  CircularProgress,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  Link as MuiLink,
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
import type { FbsStockPoolProduct } from './fbsApi'
import { QtyCell } from '../../ui-kit'
import { ProductPhotoThumb } from '../../components/ProductPhotoThumb'

// Карточка товара в каталоге ФФ — сюда ведём оператора, если у товара не задан
// остаток FBS и поле распределения по складу недоступно для ввода.
const PRODUCT_CATALOG_PATH = '/app/ff/products'

type Props = {
  open: boolean
  loading: boolean
  saving: boolean
  error: string | null
  onErrorClose: () => void
  warehouseName: string
  wbId: number | null
  items: FbsStockPoolProduct[]
  drafts: Record<string, string>
  onDraftChange: (productId: string, value: string) => void
  onSave: () => void
  onClose: () => void
}

function isItemDirty(item: FbsStockPoolProduct, drafts: Record<string, string>): boolean {
  const draft = drafts[item.product_id]
  return draft !== undefined && draft !== String(item.allocated_this_binding)
}

function matchesSearch(item: FbsStockPoolProduct, query: string): boolean {
  const needle = query.trim().toLowerCase()
  if (!needle) return true
  const haystack = [
    item.name,
    item.sku_code,
    item.wb_chrt_id != null ? String(item.wb_chrt_id) : '',
    item.wb_vendor_code ?? '',
    item.wb_barcode ?? '',
  ]
    .join(' ')
    .toLowerCase()
  return haystack.includes(needle)
}

export function FbsStockAllocationDialog({
  open,
  loading,
  saving,
  error,
  onErrorClose,
  warehouseName,
  wbId,
  items,
  drafts,
  onDraftChange,
  onSave,
  onClose,
}: Props) {
  const hasChanges = items.some((item) => isItemDirty(item, drafts))
  const [search, setSearch] = useState('')
  const filteredItems = useMemo(
    () => items.filter((item) => matchesSearch(item, search)),
    [items, search],
  )

  return (
    <Dialog open={open} onClose={onClose} maxWidth="lg" fullWidth data-testid="fbs-stock-pool-panel">
      <DialogTitle>
        Остатки по складу «{warehouseName}»
        {wbId != null ? (
          <Typography variant="caption" color="text.secondary" sx={{ display: 'block', fontWeight: 400 }}>
            WB склад {wbId}
          </Typography>
        ) : null}
      </DialogTitle>
      <DialogContent>
        <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
          Здесь вы делите остаток товара между складами: сумма по всем складам не может
          превышать остаток FBS, заданный в карточке товара.
        </Typography>
        {error ? (
          <Alert severity="error" sx={{ mb: 2 }} onClose={onErrorClose}>
            {error}
          </Alert>
        ) : null}
        {loading ? (
          <Box sx={{ py: 4, textAlign: 'center' }}>
            <CircularProgress />
          </Box>
        ) : (
          <>
            <TextField
              size="small"
              fullWidth
              placeholder="Поиск по названию, артикулу или ШК"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              sx={{ mb: 2 }}
              data-testid="fbs-pool-search"
            />
            <TableContainer sx={{ maxHeight: 420 }}>
              <Table
                size="small"
                sx={{
                  '& th, & td': { verticalAlign: 'top' },
                }}
              >
              <TableHead>
                <TableRow>
                  <TableCell sx={{ minWidth: 320 }}>Товар</TableCell>
                  <TableCell align="right" sx={{ width: 170 }}>
                    Остаток FBS в каталоге
                  </TableCell>
                  <TableCell align="right" sx={{ width: 170 }}>
                    Занято на других складах
                  </TableCell>
                  <TableCell align="right" sx={{ width: 220 }}>
                    Остаток на этом складе
                  </TableCell>
                </TableRow>
              </TableHead>
              <TableBody>
                {items.length === 0 ? (
                  <TableRow>
                    <TableCell colSpan={4}>
                      <Typography color="text.secondary">
                        У этого селлера нет товаров
                      </Typography>
                    </TableCell>
                  </TableRow>
                ) : filteredItems.length === 0 ? (
                  <TableRow>
                    <TableCell colSpan={4}>
                      <Typography color="text.secondary">Ничего не найдено</Typography>
                    </TableCell>
                  </TableRow>
                ) : (
                  filteredItems.map((item) => {
                    const notConfigured = item.pool_limit <= 0
                    const dirty = isItemDirty(item, drafts)
                    return (
                      <TableRow
                        key={item.product_id}
                        data-testid="fbs-stock-pool-row"
                        sx={dirty ? { backgroundColor: 'action.selected' } : undefined}
                      >
                        <TableCell>
                          <Stack direction="row" spacing={1.25} sx={{ alignItems: 'flex-start' }}>
                            <ProductPhotoThumb
                              src={item.image_url}
                              alt={item.name}
                              testId={`fbs-stock-pool-photo-${item.product_id}`}
                            />
                            <Box sx={{ minWidth: 0 }}>
                              <Typography variant="body2">{item.name}</Typography>
                              <Typography variant="caption" color="text.secondary" sx={{ display: 'block' }}>
                                {item.sku_code}
                              </Typography>
                              {item.wb_vendor_code ? (
                                <Typography variant="caption" color="text.secondary" sx={{ display: 'block' }}>
                                  Артикул: {item.wb_vendor_code}
                                </Typography>
                              ) : null}
                              {item.wb_barcode ? (
                                <Typography variant="caption" color="text.secondary" sx={{ display: 'block' }}>
                                  ШК: {item.wb_barcode}
                                </Typography>
                              ) : null}
                              {item.wb_size ? (
                                <Typography variant="caption" color="text.secondary" sx={{ display: 'block' }}>
                                  Размер: {item.wb_size}
                                </Typography>
                              ) : null}
                            </Box>
                          </Stack>
                        </TableCell>
                        <TableCell align="right">
                          <QtyCell value={item.pool_limit} />
                        </TableCell>
                        <TableCell align="right">
                          <QtyCell value={item.allocated_elsewhere} muted />
                        </TableCell>
                        <TableCell align="right">
                          <TextField
                            type="number"
                            size="small"
                            fullWidth
                            disabled={notConfigured || saving}
                            value={drafts[item.product_id] ?? ''}
                            onChange={(e) => onDraftChange(item.product_id, e.target.value)}
                            slotProps={{
                              htmlInput: {
                                min: 0,
                                max: item.available_for_this_binding,
                                style: { textAlign: 'right' },
                              },
                            }}
                            data-testid="fbs-stock-pool-input"
                          />
                          {notConfigured ? (
                            <Typography
                              variant="caption"
                              color="text.secondary"
                              sx={{ display: 'block', mt: 0.5, textAlign: 'left' }}
                            >
                              У товара не задан остаток FBS в каталоге, поэтому его нельзя
                              разложить по складам.{' '}
                              <MuiLink
                                component={RouterLink}
                                to={`${PRODUCT_CATALOG_PATH}?fbs_limit=${item.product_id}`}
                                target="_blank"
                                rel="noopener"
                              >
                                Задать остаток в карточке товара
                              </MuiLink>
                            </Typography>
                          ) : dirty ? (
                            <Typography
                              variant="caption"
                              color="warning.main"
                              sx={{ display: 'block', mt: 0.5, textAlign: 'left' }}
                            >
                              Изменено, ещё не сохранено
                            </Typography>
                          ) : null}
                        </TableCell>
                      </TableRow>
                    )
                  })
                )}
              </TableBody>
            </Table>
            </TableContainer>
          </>
        )}
      </DialogContent>
      <DialogActions>
        <Button onClick={onClose}>Закрыть</Button>
        <Button
          variant="contained"
          onClick={onSave}
          disabled={saving || !hasChanges}
          data-testid="fbs-stock-pool-save"
        >
          {saving ? 'Сохраняем…' : 'Сохранить изменения'}
        </Button>
      </DialogActions>
    </Dialog>
  )
}
