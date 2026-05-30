import { useCallback, useEffect, useState } from 'react'
import { Link as RouterLink, useLocation } from 'react-router-dom'
import {
  Alert,
  Box,
  Button,
  Checkbox,
  Chip,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  FormControl,
  InputLabel,
  Link,
  MenuItem,
  Paper,
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
import { apiUrl } from '../../api'
import { PageHeader } from '../../ui/PageHeader'
import { readApiErrorMessage } from '../../utils/readApiErrorMessage'

export type PackagingTaskLine = {
  id: string
  product_id: string
  sku_code: string
  product_name: string
  storage_location_id: string
  storage_location_code: string
  packaging_instructions: string | null
  qty_total: number
  qty_suggested_packed: number
  qty_confirmed_packed: number
  qty_need_pack: number
  qty_packed_in_task: number
  qty_done: number
  is_complete: boolean
}

export type PackagingTask = {
  id: string
  warehouse_id: string
  status: string
  marketplace_unload_request_id: string | null
  inbound_intake_request_id: string | null
  is_complete: boolean
  lines: PackagingTaskLine[]
}

type TaskPanelProps = {
  token: string
  task: PackagingTask
  unloadLabel?: string | null
  onClose?: () => void
  onUpdated: (task: PackagingTask) => void
}

function statusLabel(status: string): string {
  if (status === 'draft') return 'Черновик'
  if (status === 'in_progress') return 'В работе'
  if (status === 'done') return 'Выполнено'
  return status
}

export function FfPackagingTaskPanel({
  token,
  task,
  unloadLabel,
  onClose,
  onUpdated,
}: TaskPanelProps) {
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const authHeaders = {
    Authorization: `Bearer ${token}`,
    'Content-Type': 'application/json',
  }

  const confirmPacked = async (lineId: string) => {
    setBusy(true)
    setError(null)
    try {
      const res = await fetch(
        apiUrl(`/operations/packaging-tasks/${task.id}/lines/${lineId}/confirm-packed`),
        { method: 'POST', headers: authHeaders, body: JSON.stringify({}) },
      )
      if (!res.ok) {
        setError(await readApiErrorMessage(res))
        return
      }
      onUpdated((await res.json()) as PackagingTask)
    } finally {
      setBusy(false)
    }
  }

  const packQty = async (lineId: string, qty: number) => {
    setBusy(true)
    setError(null)
    try {
      const res = await fetch(
        apiUrl(`/operations/packaging-tasks/${task.id}/lines/${lineId}/pack`),
        {
          method: 'POST',
          headers: authHeaders,
          body: JSON.stringify({ quantity: qty }),
        },
      )
      if (!res.ok) {
        setError(await readApiErrorMessage(res))
        return
      }
      onUpdated((await res.json()) as PackagingTask)
    } finally {
      setBusy(false)
    }
  }

  return (
    <Stack spacing={2} data-testid="ff-packaging-task-panel">
      <Stack direction="row" spacing={1} sx={{ alignItems: 'center', flexWrap: 'wrap' }}>
        <Chip label={statusLabel(task.status)} size="small" data-testid="ff-packaging-task-status" />
        {task.marketplace_unload_request_id ? (
          <Link
            component={RouterLink}
            to={`/ff/mp-shipments?open_mp=${task.marketplace_unload_request_id}`}
            variant="body2"
            data-testid="ff-packaging-linked-unload"
          >
            Отгрузка: {unloadLabel ?? task.marketplace_unload_request_id.slice(0, 8)}
          </Link>
        ) : unloadLabel ? (
          <Typography variant="body2" color="text.secondary" data-testid="ff-packaging-linked-unload">
            Отгрузка: {unloadLabel}
          </Typography>
        ) : null}
      </Stack>
      {error ? (
        <Alert severity="error" data-testid="ff-packaging-error">
          {error}
        </Alert>
      ) : null}
      <TableContainer component={Paper} variant="outlined">
        <Table size="small">
          <TableHead>
            <TableRow>
              <TableCell>Товар / ячейка</TableCell>
              <TableCell>Инструкция</TableCell>
              <TableCell align="right">Всего</TableCell>
              <TableCell align="right">На полке упак.</TableCell>
              <TableCell align="right">Упаковать</TableCell>
              <TableCell align="right">Готово</TableCell>
              <TableCell align="right">Действия</TableCell>
            </TableRow>
          </TableHead>
          <TableBody>
            {task.lines.map((ln) => (
              <TableRow key={ln.id} data-testid="ff-packaging-line">
                <TableCell>
                  <Typography variant="body2">{ln.sku_code}</Typography>
                  <Typography variant="caption" color="text.secondary">
                    {ln.product_name} · {ln.storage_location_code}
                  </Typography>
                </TableCell>
                <TableCell sx={{ maxWidth: 220 }}>
                  <Typography variant="caption" data-testid="ff-packaging-instructions">
                    {ln.packaging_instructions?.trim() || '— ТЗ не заполнено —'}
                  </Typography>
                </TableCell>
                <TableCell align="right">{ln.qty_total}</TableCell>
                <TableCell align="right">{ln.qty_suggested_packed}</TableCell>
                <TableCell align="right">{ln.qty_need_pack}</TableCell>
                <TableCell align="right">{ln.qty_done}</TableCell>
                <TableCell align="right">
                  <Stack direction="row" spacing={0.5} sx={{ justifyContent: 'flex-end' }}>
                    {ln.qty_confirmed_packed < ln.qty_suggested_packed ? (
                      <Button
                        size="small"
                        disabled={busy || ln.qty_suggested_packed < 1}
                        onClick={() => void confirmPacked(ln.id)}
                        data-testid="ff-packaging-confirm-shelf"
                      >
                        Подтвердить с полки
                      </Button>
                    ) : null}
                    {ln.qty_packed_in_task < ln.qty_need_pack ? (
                      <Button
                        size="small"
                        variant="contained"
                        disabled={busy}
                        onClick={() => void packQty(ln.id, ln.qty_need_pack - ln.qty_packed_in_task)}
                        data-testid="ff-packaging-pack-btn"
                      >
                        Упаковать
                      </Button>
                    ) : null}
                  </Stack>
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </TableContainer>
      {onClose ? (
        <Stack direction="row" sx={{ justifyContent: 'flex-end' }}>
          <Button onClick={onClose} data-testid="ff-packaging-close">
            Закрыть
          </Button>
        </Stack>
      ) : null}
    </Stack>
  )
}

type PageProps = {
  token: string
}

type WarehouseRow = { id: string; name: string; code: string }

type SortingBalanceRow = {
  product_id: string
  sku_code: string
  product_name: string
  quantity_unpacked: number
}

type CreateDialogProps = {
  open: boolean
  token: string
  onClose: () => void
  onCreated: (task: PackagingTask) => void
}

function FfCreatePackagingTaskDialog({ open, token, onClose, onCreated }: CreateDialogProps) {
  const authHeaders = {
    Authorization: `Bearer ${token}`,
    'Content-Type': 'application/json',
  }
  const [warehouses, setWarehouses] = useState<WarehouseRow[]>([])
  const [warehouseId, setWarehouseId] = useState('')
  const [rows, setRows] = useState<SortingBalanceRow[]>([])
  const [selected, setSelected] = useState<Record<string, boolean>>({})
  const [qtyByProduct, setQtyByProduct] = useState<Record<string, string>>({})
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (!open) {
      setWarehouseId('')
      setRows([])
      setSelected({})
      setQtyByProduct({})
      setError(null)
      return
    }
    void (async () => {
      const res = await fetch(apiUrl('/warehouses'), { headers: authHeaders })
      if (!res.ok) {
        setError(await readApiErrorMessage(res))
        return
      }
      const list = (await res.json()) as WarehouseRow[]
      setWarehouses(list)
      if (list.length === 1) {
        setWarehouseId(list[0]!.id)
      }
    })()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, token])

  useEffect(() => {
    if (!open || !warehouseId) {
      setRows([])
      return
    }
    void (async () => {
      const locRes = await fetch(apiUrl(`/warehouses/${warehouseId}/sorting-location`), {
        headers: authHeaders,
      })
      if (!locRes.ok) {
        setError(await readApiErrorMessage(locRes))
        return
      }
      const loc = (await locRes.json()) as { id: string }
      const balRes = await fetch(
        apiUrl(`/operations/inventory-balances?storage_location_id=${loc.id}`),
        { headers: authHeaders },
      )
      if (!balRes.ok) {
        setError(await readApiErrorMessage(balRes))
        return
      }
      const balances = (await balRes.json()) as {
        product_id: string
        sku_code: string
        product_name: string
        quantity_unpacked: number
      }[]
      const unpacked = balances.filter((b) => b.quantity_unpacked > 0)
      setRows(unpacked)
      const sel: Record<string, boolean> = {}
      const qty: Record<string, string> = {}
      for (const b of unpacked) {
        sel[b.product_id] = true
        qty[b.product_id] = String(b.quantity_unpacked)
      }
      setSelected(sel)
      setQtyByProduct(qty)
    })()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, warehouseId, token])

  const submit = async () => {
    const lines = rows
      .filter((r) => selected[r.product_id])
      .map((r) => ({
        product_id: r.product_id,
        quantity: Math.floor(Number(qtyByProduct[r.product_id] ?? '0')),
      }))
      .filter((ln) => ln.quantity >= 1)
    if (!warehouseId || lines.length === 0) {
      setError('Выберите склад и хотя бы один товар с количеством ≥ 1.')
      return
    }
    setBusy(true)
    setError(null)
    try {
      const res = await fetch(apiUrl('/operations/packaging-tasks'), {
        method: 'POST',
        headers: authHeaders,
        body: JSON.stringify({ warehouse_id: warehouseId, lines }),
      })
      if (!res.ok) {
        setError(await readApiErrorMessage(res))
        return
      }
      onCreated((await res.json()) as PackagingTask)
      onClose()
    } finally {
      setBusy(false)
    }
  }

  return (
    <Dialog open={open} onClose={onClose} fullWidth maxWidth="md" data-testid="ff-packaging-create-dialog">
      <DialogTitle>Создать задание из сортировки</DialogTitle>
      <DialogContent>
        <Stack spacing={2} sx={{ mt: 1 }}>
          {error ? <Alert severity="error">{error}</Alert> : null}
          <FormControl fullWidth size="small">
            <InputLabel id="ff-packaging-wh-label">Склад</InputLabel>
            <Select
              labelId="ff-packaging-wh-label"
              label="Склад"
              value={warehouseId}
              onChange={(e) => setWarehouseId(String(e.target.value))}
              data-testid="ff-packaging-create-warehouse"
            >
              {warehouses.map((w) => (
                <MenuItem key={w.id} value={w.id}>
                  {w.name}
                </MenuItem>
              ))}
            </Select>
          </FormControl>
          {warehouseId && rows.length === 0 ? (
            <Typography variant="body2" color="text.secondary" data-testid="ff-packaging-create-empty">
              В зоне «Сортировка» нет неупакованного товара.
            </Typography>
          ) : null}
          {rows.length > 0 ? (
            <TableContainer component={Paper} variant="outlined">
              <Table size="small">
                <TableHead>
                  <TableRow>
                    <TableCell padding="checkbox" />
                    <TableCell>Товар</TableCell>
                    <TableCell align="right">Неупаковано</TableCell>
                    <TableCell align="right">В задание</TableCell>
                  </TableRow>
                </TableHead>
                <TableBody>
                  {rows.map((r) => (
                    <TableRow key={r.product_id} data-testid="ff-packaging-create-row">
                      <TableCell padding="checkbox">
                        <Checkbox
                          checked={Boolean(selected[r.product_id])}
                          onChange={(e) =>
                            setSelected((prev) => ({ ...prev, [r.product_id]: e.target.checked }))
                          }
                        />
                      </TableCell>
                      <TableCell>
                        {r.sku_code} · {r.product_name}
                      </TableCell>
                      <TableCell align="right">{r.quantity_unpacked}</TableCell>
                      <TableCell align="right">
                        <TextField
                          size="small"
                          type="number"
                          value={qtyByProduct[r.product_id] ?? ''}
                          onChange={(e) =>
                            setQtyByProduct((prev) => ({
                              ...prev,
                              [r.product_id]: e.target.value,
                            }))
                          }
                          slotProps={{
                            htmlInput: {
                              min: 1,
                              max: r.quantity_unpacked,
                              'data-testid': `ff-packaging-create-qty-${r.product_id}`,
                            },
                          }}
                          sx={{ width: 88 }}
                        />
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </TableContainer>
          ) : null}
        </Stack>
      </DialogContent>
      <DialogActions>
        <Button onClick={onClose} disabled={busy}>
          Отмена
        </Button>
        <Button
          variant="contained"
          disabled={busy || !warehouseId || rows.length === 0}
          onClick={() => void submit()}
          data-testid="ff-packaging-create-submit"
        >
          Создать
        </Button>
      </DialogActions>
    </Dialog>
  )
}

export function FfPackagingPage({ token }: PageProps) {
  const location = useLocation()
  const [tasks, setTasks] = useState<PackagingTask[]>([])
  const [selected, setSelected] = useState<PackagingTask | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [createOpen, setCreateOpen] = useState(false)

  const loadTaskById = useCallback(
    async (taskId: string) => {
      const res = await fetch(apiUrl(`/operations/packaging-tasks/${taskId}`), {
        headers: { Authorization: `Bearer ${token}` },
      })
      if (!res.ok) {
        setError(await readApiErrorMessage(res))
        return
      }
      setSelected((await res.json()) as PackagingTask)
    },
    [token],
  )

  const load = useCallback(async () => {
    const res = await fetch(apiUrl('/operations/packaging-tasks'), {
      headers: { Authorization: `Bearer ${token}` },
    })
    if (!res.ok) {
      setError(await readApiErrorMessage(res))
      return
    }
    setTasks((await res.json()) as PackagingTask[])
  }, [token])

  useEffect(() => {
    void load()
  }, [load])

  useEffect(() => {
    const state = location.state as { taskId?: string } | null
    if (state?.taskId) {
      void loadTaskById(state.taskId)
    }
  }, [location.state, loadTaskById])

  return (
    <Box data-testid="ff-packaging-page">
      <PageHeader
        title="Упаковка"
        description="Задания на маркировку и упаковку. Можно создать из сортировки или открыть из отгрузки на МП."
      />
      <Stack direction="row" sx={{ justifyContent: 'flex-end', mb: 2 }}>
        <Button
          variant="contained"
          onClick={() => setCreateOpen(true)}
          data-testid="ff-packaging-create-open"
        >
          Создать задание
        </Button>
      </Stack>
      {error ? <Alert severity="error">{error}</Alert> : null}
      {selected ? (
        <FfPackagingTaskPanel
          token={token}
          task={selected}
          onClose={() => setSelected(null)}
          onUpdated={(t) => {
            setSelected(t)
            void load()
          }}
        />
      ) : (
        <TableContainer component={Paper} variant="outlined" data-testid="ff-packaging-queue">
          <Table size="small">
            <TableHead>
              <TableRow>
                <TableCell>Статус</TableCell>
                <TableCell>Строк</TableCell>
                <TableCell>Отгрузка</TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {tasks.length === 0 ? (
                <TableRow>
                  <TableCell colSpan={3}>
                    <Typography variant="body2" color="text.secondary">
                      Нет открытых заданий.
                    </Typography>
                  </TableCell>
                </TableRow>
              ) : (
                tasks.map((t) => (
                  <TableRow
                    key={t.id}
                    hover
                    sx={{ cursor: 'pointer' }}
                    onClick={() => setSelected(t)}
                    data-testid="ff-packaging-queue-row"
                  >
                    <TableCell>{statusLabel(t.status)}</TableCell>
                    <TableCell>{t.lines.length}</TableCell>
                    <TableCell>{t.marketplace_unload_request_id ? 'Да' : '—'}</TableCell>
                  </TableRow>
                ))
              )}
            </TableBody>
          </Table>
        </TableContainer>
      )}
      <FfCreatePackagingTaskDialog
        open={createOpen}
        token={token}
        onClose={() => setCreateOpen(false)}
        onCreated={(task) => {
          setSelected(task)
          void load()
        }}
      />
    </Box>
  )
}

type DialogProps = {
  open: boolean
  token: string
  unloadId: string
  unloadLabel: string
  onClose: () => void
}

export function FfPackagingTaskDialog({
  open,
  token,
  unloadId,
  unloadLabel,
  onClose,
}: DialogProps) {
  const [task, setTask] = useState<PackagingTask | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (!open) {
      setTask(null)
      return
    }
    void (async () => {
      const res = await fetch(apiUrl(`/operations/packaging-tasks/by-unload/${unloadId}`), {
        headers: { Authorization: `Bearer ${token}` },
      })
      if (!res.ok) {
        setError(await readApiErrorMessage(res))
        return
      }
      setTask((await res.json()) as PackagingTask)
    })()
  }, [open, token, unloadId])

  return (
    <Dialog open={open} onClose={onClose} fullWidth maxWidth="lg" data-testid="ff-packaging-dialog">
      <DialogTitle>Задание на упаковку</DialogTitle>
      <DialogContent>
        {error ? <Alert severity="error">{error}</Alert> : null}
        {task ? (
          <FfPackagingTaskPanel
            token={token}
            task={task}
            unloadLabel={unloadLabel}
            onUpdated={setTask}
          />
        ) : null}
      </DialogContent>
      <DialogActions>
        <Button onClick={onClose} data-testid="ff-packaging-dialog-close">
          Вернуться к отгрузке
        </Button>
      </DialogActions>
    </Dialog>
  )
}
