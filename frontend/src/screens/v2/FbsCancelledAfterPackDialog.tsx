import { useCallback, useEffect, useState } from 'react'
import {
  Alert, Button, CircularProgress, Dialog, DialogActions, DialogContent, DialogTitle,
  Stack, Table, TableBody, TableCell, TableContainer, TableHead, TablePagination,
  TableRow, TextField, Typography,
} from '@mui/material'
import { fetchFbsCancelledAfterPack, type FbsCancelledAfterPackOrder } from './fbsApi'

const PAGE_SIZE = 50

type Props = {
  open: boolean
  token: string
  authHeaders: (token: string) => Record<string, string>
  sellerId?: string
  onClose: () => void
  onOpenSupply: (id: string) => void
}

export function FbsCancelledAfterPackDialog({
  open, token, authHeaders, sellerId, onClose, onOpenSupply,
}: Props) {
  const [search, setSearch] = useState('')
  const [query, setQuery] = useState('')
  const [page, setPage] = useState(0)
  const [items, setItems] = useState<FbsCancelledAfterPackOrder[]>([])
  const [total, setTotal] = useState(0)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [revision, setRevision] = useState(0)
  const refresh = useCallback(() => setRevision((value) => value + 1), [])

  useEffect(() => {
    const timer = window.setTimeout(() => { setQuery(search.trim()); setPage(0) }, 250)
    return () => window.clearTimeout(timer)
  }, [search])

  useEffect(() => { setPage(0) }, [sellerId])

  useEffect(() => {
    if (!open) return
    let current = true
    setBusy(true)
    setError(null)
    void fetchFbsCancelledAfterPack(token, authHeaders, {
      sellerId, search: query, limit: PAGE_SIZE, offset: page * PAGE_SIZE,
    }).then((result) => {
      if (!current) return
      setItems(result.items)
      setTotal(result.total)
    }).catch((cause) => {
      if (!current) return
      setItems([])
      setTotal(0)
      setError(cause instanceof Error ? cause.message : 'Не удалось загрузить список.')
    }).finally(() => { if (current) setBusy(false) })
    return () => { current = false }
  }, [open, token, authHeaders, sellerId, query, page, revision])

  return (
    <Dialog open={open} onClose={onClose} fullWidth maxWidth="lg" data-testid="fbs-cancelled-after-pack">
      <DialogTitle>К вскрытию · Wildberries</DialogTitle>
      <DialogContent>
        <Typography color="text.secondary" sx={{ mb: 2 }}>
          Отменённые заказы со следами сборки. Найдите короб и выньте отменённый заказ перед выездом.
        </Typography>
        <Stack direction="row" spacing={2} sx={{ mb: 2 }}>
          <TextField
            fullWidth size="small" label="Номер заказа, короба или артикул"
            value={search} onChange={(event) => setSearch(event.target.value)}
            slotProps={{ htmlInput: { maxLength: 200 } }} data-testid="fbs-cancelled-after-pack-search"
          />
          <Button onClick={refresh} disabled={busy}>Обновить</Button>
        </Stack>
        {error ? <Alert severity="error">{error}</Alert> : null}
        {busy ? <CircularProgress size={24} aria-label="Загрузка списка" /> : (
          <TableContainer>
            <Table size="small">
              <TableHead><TableRow>
                <TableCell>Заказ / товар</TableCell><TableCell>Селлер</TableCell>
                <TableCell>Короб</TableCell><TableCell>Поставка</TableCell><TableCell>Отмена</TableCell>
              </TableRow></TableHead>
              <TableBody>
                {items.map((item) => (
                  <TableRow key={item.order_id}>
                    <TableCell>
                      <Typography variant="body2" sx={{ fontWeight: 600 }}>№{item.wb_order_id}</Typography>
                      <Typography variant="body2">{item.product.name}</Typography>
                      <Typography variant="caption">{item.product.article ?? '—'}{item.product.size ? ` · ${item.product.size}` : ''}</Typography>
                    </TableCell>
                    <TableCell>{item.seller.name}</TableCell>
                    <TableCell>
                      {item.cargo_places.length ? item.cargo_places.map((box) => (
                        <Stack key={box.box_id} sx={{ mb: 0.5 }}>
                          <Typography variant="body2">Короб №{box.box_number}</Typography>
                          <Typography variant="caption">{box.box_barcode}</Typography>
                          {box.wb_trbx_id ? <Typography variant="caption">{box.wb_trbx_id}</Typography> : null}
                        </Stack>
                      )) : 'Короб не указан'}
                    </TableCell>
                    <TableCell>
                      {item.supply.id ? (
                        <Button size="small" onClick={() => { onClose(); onOpenSupply(item.supply.id!) }}>
                          {item.supply.wb_supply_id || item.supply.name || 'Открыть поставку'}
                        </Button>
                      ) : item.supply.wb_supply_id || '—'}
                      {item.supply_departed ? <Typography variant="caption" sx={{ display: 'block' }}>Поставка передана</Typography> : null}
                    </TableCell>
                    <TableCell>
                      <Typography variant="body2">{item.cancellation_reason}</Typography>
                      <Typography variant="caption">Обновлено {new Date(item.cancelled_at).toLocaleString('ru-RU')}</Typography>
                    </TableCell>
                  </TableRow>
                ))}
                {!items.length && !error ? <TableRow><TableCell colSpan={5}>Заказы не найдены</TableCell></TableRow> : null}
              </TableBody>
            </Table>
          </TableContainer>
        )}
        <TablePagination
          component="div" count={total} page={page} rowsPerPage={PAGE_SIZE} rowsPerPageOptions={[PAGE_SIZE]}
          onPageChange={(_, value) => setPage(value)} disabled={busy}
          labelDisplayedRows={({ from, to, count }) => `${from}–${to} из ${count}`}
          getItemAriaLabel={(type) => type === 'next' ? 'Следующая страница' : 'Предыдущая страница'}
        />
      </DialogContent>
      <DialogActions><Button onClick={onClose}>Закрыть</Button></DialogActions>
    </Dialog>
  )
}
