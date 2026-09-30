import { useCallback, useEffect, useRef, useState } from 'react'
import {
  Alert, Box, Button, CircularProgress, Collapse, Dialog, DialogContent,
  IconButton, Paper, Stack, Table, TableBody, TableCell, TableHead, TableRow,
  Typography,
} from '@mui/material'
import CloseIcon from '@mui/icons-material/Close'
import ExpandMoreIcon from '@mui/icons-material/ExpandMore'
import { apiUrl } from '../../api'
import { FbsSupplyHistoryTimeline, type FbsSupplyHistory } from './FbsSupplyHistoryDialog'
import {
  syncFbsSupplyTrackingStatus,
  type FbsTrackingSummary,
  type FbsWorkspace,
} from './fbsApi'

const WB_STATUS: Record<string, string> = {
  waiting: 'Ожидает приёмки WB',
  sorted: 'Отсортирован WB',
  sold: 'Выкуплен',
  canceled: 'Отменён',
  canceled_by_client: 'Отменён покупателем',
  declined_by_client: 'Отказ покупателя',
  defect: 'Брак',
  ready_for_pickup: 'Ожидает выдачи',
  postponed_delivery: 'Доставка перенесена',
  accepted_by_carrier: 'Принят перевозчиком',
  sent_to_carrier: 'Передан перевозчику',
  canceled_by_carrier: 'Отменён перевозчиком',
}

const SUPPLIER_STATUS: Record<string, string> = {
  new: 'Новый', confirm: 'В сборке', complete: 'В доставке',
  cancel: 'Отменён продавцом', cancel_carrier: 'Отменён перевозчиком',
}

function wbMoment(value: string): string {
  return new Intl.DateTimeFormat('ru-RU', {
    timeZone: 'Europe/Moscow', dateStyle: 'short', timeStyle: 'short',
  }).format(new Date(value))
}

export function FbsSupplyTrackingCard({
  token, authHeaders, workspace, open, onClose,
}: {
  token: string
  authHeaders: (token: string) => Record<string, string>
  workspace: FbsWorkspace
  open: boolean
  onClose: () => void
}) {
  const supplyId = workspace.supply.id
  const [summary, setSummary] = useState<FbsTrackingSummary | null>(workspace.tracking_summary ?? null)
  const [supplyStatus, setSupplyStatus] = useState(workspace.supply.status)
  const [closedAt, setClosedAt] = useState<string | null>(null)
  const [scanAt, setScanAt] = useState<string | null>(null)
  const [syncing, setSyncing] = useState(false)
  const [syncError, setSyncError] = useState(false)
  const [historyOpen, setHistoryOpen] = useState(false)
  const [history, setHistory] = useState<FbsSupplyHistory | null>(null)
  const [historyError, setHistoryError] = useState(false)
  const syncingRef = useRef(false)
  const openRef = useRef(open)
  openRef.current = open

  useEffect(() => {
    setSummary(workspace.tracking_summary ?? null)
    setSupplyStatus(workspace.supply.status)
    setClosedAt(null)
    setScanAt(null)
    setHistoryOpen(false)
    setHistory(null)
    setSyncError(false)
  }, [supplyId])

  const refresh = useCallback(async () => {
    if (syncingRef.current || !openRef.current) return
    syncingRef.current = true
    setSyncing(true)
    try {
      const result = await syncFbsSupplyTrackingStatus(token, authHeaders, supplyId)
      if (!openRef.current) return
      setSummary(result.tracking_summary)
      setSupplyStatus(result.supply_status)
      setClosedAt(result.wb_closed_at)
      setScanAt(result.wb_scan_at)
      setSyncError(false)
    } catch {
      if (openRef.current) setSyncError(true)
    } finally {
      syncingRef.current = false
      if (openRef.current) setSyncing(false)
    }
  }, [token, authHeaders, supplyId])

  useEffect(() => {
    if (!open) return
    void refresh()
    const timer = window.setInterval(() => {
      if (document.visibilityState === 'visible') void refresh()
    }, 90_000)
    return () => window.clearInterval(timer)
  }, [open, refresh])

  useEffect(() => {
    if (!open || !historyOpen || history) return
    let current = true
    void fetch(apiUrl(`/operations/fbs-supplies/${supplyId}/history`), {
      headers: { ...authHeaders(token) },
    }).then(async (response) => {
      if (!response.ok) throw new Error('history')
      const result = (await response.json()) as FbsSupplyHistory
      if (current) setHistory(result)
    }).catch(() => { if (current) setHistoryError(true) })
    return () => { current = false }
  }, [open, historyOpen, history, supplyId, authHeaders, token])

  const currentOrders = new Map(summary?.orders.map((order) => [order.order_id, order]) ?? [])
  return (
    <Dialog open={open} onClose={onClose} fullWidth maxWidth="lg" data-testid="fbs-tracking-card">
      <Box sx={{ p: 2.5, borderBottom: 1, borderColor: 'divider' }}>
        <Stack direction="row" spacing={1.5} sx={{ alignItems: 'flex-start' }}>
          <Box sx={{ flex: 1, minWidth: 0 }}>
            <Typography variant="h6">{workspace.supply.name}</Typography>
            <Typography variant="body2" color="text.secondary">
              {workspace.supply.seller.name} · WB №{workspace.supply.wb_supply_id}
            </Typography>
            <Typography variant="body2" sx={{ mt: 1, fontWeight: 650 }}>
              {supplyStatus === 'done' ? 'Завершена' : 'В доставке'}
            </Typography>
            {closedAt ? <Typography variant="caption" color="text.secondary" sx={{ display: 'block' }}>Передана в доставку WB: {wbMoment(closedAt)}</Typography> : null}
            {scanAt ? <Typography variant="caption" color="text.secondary" sx={{ display: 'block' }}>Сканирована WB: {wbMoment(scanAt)}</Typography> : null}
          </Box>
          {syncing ? <CircularProgress size={18} aria-label="Обновляем статусы WB" /> : null}
          <IconButton aria-label="Закрыть" onClick={onClose}><CloseIcon /></IconButton>
        </Stack>
      </Box>
      <DialogContent sx={{ p: 2.5 }}>
        {syncError ? <Alert severity="warning" sx={{ mb: 2 }}>Не удалось обновить статусы WB. Показаны последние полученные данные.</Alert> : null}
        <Paper variant="outlined" sx={{ overflowX: 'auto' }}>
          <Table size="small" data-testid="fbs-tracking-orders">
            <TableHead><TableRow><TableCell>Заказ WB</TableCell><TableCell>Товар</TableCell><TableCell>Этап продавца</TableCell><TableCell>Статус WB</TableCell></TableRow></TableHead>
            <TableBody>
              {workspace.orders.map((order) => {
                const state = currentOrders.get(order.id)
                const supplier = state?.supplier_status ?? null
                const wb = state?.wb_status ?? null
                return (
                  <TableRow key={order.id} data-testid={`fbs-tracking-order-${order.id}`}>
                    <TableCell>№{order.wb_order_id}</TableCell>
                    <TableCell>{order.product.name}</TableCell>
                    <TableCell>{supplier ? SUPPLIER_STATUS[supplier] ?? supplier : '—'}</TableCell>
                    <TableCell>{wb ? WB_STATUS[wb] ?? wb : 'Нет данных WB'}</TableCell>
                  </TableRow>
                )
              })}
            </TableBody>
          </Table>
        </Paper>
        <Box sx={{ mt: 2 }}>
          <Button
            onClick={() => setHistoryOpen((value) => !value)}
            endIcon={<ExpandMoreIcon sx={{ transform: historyOpen ? 'rotate(180deg)' : 'none' }} />}
            aria-expanded={historyOpen}
            data-testid="fbs-tracking-history-toggle"
          >
            История поставки
          </Button>
          <Collapse in={historyOpen} unmountOnExit>
            <Box sx={{ py: 1.5 }}>
              {historyError ? <Alert severity="warning">Не удалось загрузить историю поставки.</Alert> : null}
              {history ? <FbsSupplyHistoryTimeline history={history} /> : !historyError ? <CircularProgress size={18} /> : null}
            </Box>
          </Collapse>
        </Box>
      </DialogContent>
    </Dialog>
  )
}
