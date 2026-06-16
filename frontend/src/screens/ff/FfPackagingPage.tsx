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
import { FfProductLineCells, FfProductTableHeadCells } from '../../components/FfProductLineCells'
import { useWbProductCatalog } from '../../hooks/useWbProductCatalog'
import { apiUrl } from '../../api'
import { PageHeader } from '../../ui/PageHeader'
import { productDisplayMetaFromCatalog } from '../../types/wbProductCatalog'
import { readApiErrorMessage } from '../../utils/readApiErrorMessage'
import { useMarkingCodePrint } from '../../utils/useMarkingCodePrint'

export type PackagingTaskLine = {
  id: string
  product_id: string
  sku_code: string
  product_name: string
  storage_location_id: string
  storage_location_code: string
  packaging_instructions: string | null
  requires_honest_sign: boolean
  qty_total: number
  qty_suggested_packed: number
  qty_confirmed_packed: number
  qty_need_pack: number
  qty_packed_in_task: number
  qty_done: number
  qty_marking_printed: number
  marking_available_count: number
  is_complete: boolean
}

export type PackagingTask = {
  id: string
  warehouse_id: string
  status: string
  marketplace_unload_request_id: string | null
  inbound_intake_request_id: string | null
  is_complete: boolean
  pick_resync_warning?: boolean
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
  if (status === 'cancelled') return 'Отменено'
  return status
}

export function FfPackagingTaskPanel({
  token,
  task,
  unloadLabel,
  onClose,
  onUpdated,
}: TaskPanelProps) {
  const { catalogById } = useWbProductCatalog(token)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const { openPrint, dialog: markingPrintDialog } = useMarkingCodePrint()

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

  const cancelTask = async () => {
    if (!window.confirm('Отменить задание на упаковку?')) {
      return
    }
    setBusy(true)
    setError(null)
    try {
      const res = await fetch(apiUrl(`/operations/packaging-tasks/${task.id}/cancel`), {
        method: 'POST',
        headers: authHeaders,
      })
      if (!res.ok) {
        setError(await readApiErrorMessage(res))
        return
      }
      onUpdated((await res.json()) as PackagingTask)
      onClose?.()
    } finally {
      setBusy(false)
    }
  }

  const manualTask =
    !task.marketplace_unload_request_id &&
    task.status !== 'done' &&
    task.status !== 'cancelled'

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
      {task.pick_resync_warning ? (
        <Alert severity="warning" data-testid="ff-packaging-pick-resync-warning">
          Подбор по ячейкам изменился. Количества в задании пересчитаны; уже упакованное в
          задании сохранено — проверьте строки.
        </Alert>
      ) : null}
      <TableContainer component={Paper} variant="outlined" sx={{ width: '100%', overflowX: 'hidden' }}>
        <Table
          size="small"
          sx={{
            tableLayout: 'fixed',
            width: '100%',
            '& th': { py: 1.25 },
            '& td': { py: 1.25 },
          }}
        >
          <TableHead>
            <TableRow>
              <FfProductTableHeadCells nameLabel="Наименование / ячейка" />
              <TableCell>Инструкция</TableCell>
              <TableCell align="right">Всего</TableCell>
              <TableCell align="right">На полке упак.</TableCell>
              <TableCell align="right">Упаковать</TableCell>
              <TableCell align="right">Готово</TableCell>
              <TableCell align="right">ЧЗ</TableCell>
              <TableCell align="right">Действия</TableCell>
            </TableRow>
          </TableHead>
          <TableBody>
            {task.lines.map((ln) => {
              const displayMeta = productDisplayMetaFromCatalog(ln.product_id, ln, catalogById)
              return (
              <TableRow key={ln.id} data-testid="ff-packaging-line">
                <FfProductLineCells
                  meta={{
                    ...displayMeta,
                    product_name: `${displayMeta.product_name} · ${ln.storage_location_code}`,
                  }}
                  printTestId={`ff-packaging-line-print-${ln.id}`}
                />
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
                  {ln.requires_honest_sign ? (
                    <Stack spacing={0.25} sx={{ alignItems: 'flex-end' }}>
                      <Typography variant="caption" color="text.secondary">
                        {ln.qty_marking_printed > 0
                          ? `напеч. ${ln.qty_marking_printed}`
                          : `дост. ${ln.marking_available_count}`}
                      </Typography>
                    </Stack>
                  ) : (
                    '—'
                  )}
                </TableCell>
                <TableCell align="right">
                  <Stack direction="row" spacing={0.5} sx={{ justifyContent: 'flex-end', flexWrap: 'wrap' }}>
                    {ln.requires_honest_sign && ln.qty_need_pack > 0 && ln.qty_marking_printed < 1 ? (
                      <Button
                        size="small"
                        variant="outlined"
                        disabled={busy || ln.marking_available_count < ln.qty_need_pack}
                        onClick={() =>
                          openPrint({
                            token,
                            lineId: ln.id,
                            qtyNeedPack: ln.qty_need_pack,
                            markingAvailable: ln.marking_available_count,
                            qtyMarkingPrinted: ln.qty_marking_printed,
                            skuCode: ln.sku_code,
                            onPrinted: () => {
                              void (async () => {
                                const res = await fetch(
                                  apiUrl(`/operations/packaging-tasks/${task.id}`),
                                  { headers: authHeaders },
                                )
                                if (res.ok) {
                                  onUpdated((await res.json()) as PackagingTask)
                                }
                              })()
                            },
                          })
                        }
                        data-testid="ff-packaging-print-marking"
                      >
                        Печать ЧЗ
                      </Button>
                    ) : null}
                    {ln.requires_honest_sign && ln.qty_marking_printed > 0 ? (
                      <Button
                        size="small"
                        variant="text"
                        disabled={busy}
                        onClick={() =>
                          openPrint(
                            {
                              token,
                              lineId: ln.id,
                              qtyNeedPack: ln.qty_need_pack,
                              markingAvailable: ln.marking_available_count,
                              qtyMarkingPrinted: ln.qty_marking_printed,
                              skuCode: ln.sku_code,
                              onPrinted: () => {
                                void (async () => {
                                  const res = await fetch(
                                    apiUrl(`/operations/packaging-tasks/${task.id}`),
                                    { headers: authHeaders },
                                  )
                                  if (res.ok) {
                                    onUpdated((await res.json()) as PackagingTask)
                                  }
                                })()
                              },
                            },
                            { reprint: true },
                          )
                        }
                        data-testid="ff-packaging-reprint-marking"
                      >
                        Повтор
                      </Button>
                    ) : null}
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
            )})}
          </TableBody>
        </Table>
      </TableContainer>
      {markingPrintDialog}
      {onClose ? (
        <Stack direction="row" spacing={1} sx={{ justifyContent: 'flex-end' }}>
          {manualTask ? (
            <Button
              color="error"
              variant="outlined"
              disabled={busy}
              onClick={() => void cancelTask()}
              data-testid="ff-packaging-cancel-task"
            >
              Отменить задание
            </Button>
          ) : null}
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

type LocationRow = { id: string; code: string; barcode: string }

function FfCreatePackagingTaskDialog({ open, token, onClose, onCreated }: CreateDialogProps) {
  const { catalogById } = useWbProductCatalog(token, open)
  const authHeaders = {
    Authorization: `Bearer ${token}`,
    'Content-Type': 'application/json',
  }
  const [warehouses, setWarehouses] = useState<WarehouseRow[]>([])
  const [warehouseId, setWarehouseId] = useState('')
  const [locations, setLocations] = useState<LocationRow[]>([])
  const [locationId, setLocationId] = useState('')
  const [rows, setRows] = useState<SortingBalanceRow[]>([])
  const [selected, setSelected] = useState<Record<string, boolean>>({})
  const [qtyByProduct, setQtyByProduct] = useState<Record<string, string>>({})
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (!open) {
      setWarehouseId('')
      setLocationId('')
      setLocations([])
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
      setLocations([])
      setLocationId('')
      setRows([])
      return
    }
    void (async () => {
      const locRes = await fetch(apiUrl(`/warehouses/${warehouseId}/locations`), {
        headers: authHeaders,
      })
      if (!locRes.ok) {
        setError(await readApiErrorMessage(locRes))
        return
      }
      const locList = (await locRes.json()) as LocationRow[]
      const sorted = [...locList].sort((a, b) => {
        if (a.code === '__SORTING__') return -1
        if (b.code === '__SORTING__') return 1
        return a.code.localeCompare(b.code)
      })
      setLocations(sorted)
      const defaultLoc = sorted.find((l) => l.code === '__SORTING__') ?? sorted[0]
      setLocationId(defaultLoc?.id ?? '')
    })()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, warehouseId, token])

  useEffect(() => {
    if (!open || !locationId) {
      setRows([])
      return
    }
    void (async () => {
      const balRes = await fetch(
        apiUrl(`/operations/inventory-balances?storage_location_id=${locationId}`),
        { headers: authHeaders },
      )
      if (!balRes.ok) {
        setError(await readApiErrorMessage(balRes))
        return
      }
      const balances = (await balRes.json()) as SortingBalanceRow[]
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
  }, [open, locationId, token])

  const submit = async () => {
    const lines = rows
      .filter((r) => selected[r.product_id])
      .map((r) => ({
        product_id: r.product_id,
        storage_location_id: locationId,
        quantity: Math.floor(Number(qtyByProduct[r.product_id] ?? '0')),
      }))
      .filter((ln) => ln.quantity >= 1)
    if (!warehouseId || !locationId || lines.length === 0) {
      setError('Выберите склад, место и хотя бы один товар с количеством ≥ 1.')
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

  const locationLabel = (loc: LocationRow) =>
    loc.code === '__SORTING__' ? 'Сортировка' : loc.code

  return (
    <Dialog
      open={open}
      onClose={onClose}
      fullWidth
      maxWidth={false}
      slotProps={{ paper: { sx: { width: 'min(1200px, 96vw)', maxHeight: '92vh' } } }}
      data-testid="ff-packaging-create-dialog"
    >
      <DialogTitle>Создать задание на упаковку</DialogTitle>
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
          {warehouseId ? (
            <FormControl fullWidth size="small">
              <InputLabel id="ff-packaging-loc-label">Место (ячейка)</InputLabel>
              <Select
                labelId="ff-packaging-loc-label"
                label="Место (ячейка)"
                value={locationId}
                onChange={(e) => setLocationId(String(e.target.value))}
                data-testid="ff-packaging-create-location"
              >
                {locations.map((loc) => (
                  <MenuItem key={loc.id} value={loc.id}>
                    {locationLabel(loc)}
                  </MenuItem>
                ))}
              </Select>
            </FormControl>
          ) : null}
          {warehouseId && locationId && rows.length === 0 ? (
            <Typography variant="body2" color="text.secondary" data-testid="ff-packaging-create-empty">
              В выбранном месте нет неупакованного товара.
            </Typography>
          ) : null}
          {rows.length > 0 ? (
            <TableContainer component={Paper} variant="outlined" sx={{ width: '100%', overflowX: 'hidden' }}>
              <Table
                size="small"
                data-testid="ff-packaging-create-table"
                sx={{
                  tableLayout: 'fixed',
                  width: '100%',
                  '& th': { py: 1.25 },
                  '& td': { py: 1.25 },
                }}
              >
                <TableHead>
                  <TableRow>
                    <TableCell padding="checkbox" sx={{ width: 48 }} />
                    <FfProductTableHeadCells />
                    <TableCell align="right" sx={{ width: 120 }}>
                      Неупаковано
                    </TableCell>
                    <TableCell align="right" sx={{ width: 120 }}>
                      В задание
                    </TableCell>
                  </TableRow>
                </TableHead>
                <TableBody>
                  {rows.map((r) => {
                    const displayMeta = productDisplayMetaFromCatalog(r.product_id, r, catalogById)
                    return (
                    <TableRow key={r.product_id} data-testid="ff-packaging-create-row">
                      <TableCell padding="checkbox">
                        <Checkbox
                          checked={Boolean(selected[r.product_id])}
                          onChange={(e) =>
                            setSelected((prev) => ({ ...prev, [r.product_id]: e.target.checked }))
                          }
                        />
                      </TableCell>
                      <FfProductLineCells
                        meta={displayMeta}
                        printTestId={`ff-packaging-create-print-${r.product_id}`}
                      />
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
                  )})}
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
        description="Задания на маркировку и упаковку. Создайте из ячейки или сортировки, либо откройте из отгрузки на МП."
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
    <Dialog
      open={open}
      onClose={onClose}
      fullWidth
      maxWidth={false}
      slotProps={{ paper: { sx: { width: 'min(1200px, 96vw)', maxHeight: '92vh' } } }}
      data-testid="ff-packaging-dialog"
    >
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
