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

  return (
    <Dialog open={open} onClose={onClose} maxWidth="md" fullWidth data-testid="fbs-stock-pool-panel">
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
          <TableContainer>
            <Table
              size="small"
              sx={{
                '& th, & td': { verticalAlign: 'top' },
              }}
            >
              <TableHead>
                <TableRow>
                  <TableCell>Товар</TableCell>
                  <TableCell align="right">Остаток FBS в каталоге</TableCell>
                  <TableCell align="right">Занято на других складах</TableCell>
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
                        Нет товаров с включённой продажей по FBS у этого селлера
                      </Typography>
                    </TableCell>
                  </TableRow>
                ) : (
                  items.map((item) => {
                    const notConfigured = item.pool_limit <= 0
                    const dirty = isItemDirty(item, drafts)
                    return (
                      <TableRow
                        key={item.product_id}
                        data-testid="fbs-stock-pool-row"
                        sx={dirty ? { backgroundColor: 'action.selected' } : undefined}
                      >
                        <TableCell>
                          <Typography variant="body2">{item.name}</Typography>
                          <Typography variant="caption" color="text.secondary">
                            {item.sku_code}
                          </Typography>
                        </TableCell>
                        <TableCell align="right">{item.pool_limit}</TableCell>
                        <TableCell align="right">{item.allocated_elsewhere}</TableCell>
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
                                to={PRODUCT_CATALOG_PATH}
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
