import { useCallback, useEffect, useMemo, useState } from 'react'
import {
  Alert,
  Box,
  Button,
  Chip,
  CircularProgress,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  FormControl,
  FormControlLabel,
  InputLabel,
  MenuItem,
  Paper,
  Select,
  Stack,
  Switch,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  TextField,
  Typography,
} from '@mui/material'
import type { ChipProps } from '@mui/material'
import { apiUrl } from '../../api'
import { readApiErrorMessage } from '../../utils/readApiErrorMessage'
import { FfFbsSectionNav } from './FfFbsSectionNav'
import {
  disableFbsWarehouseBinding,
  fetchFbsStockSyncStatus,
  fetchFbsWarehouseBindings,
  STOCK_SYNC_STATUS_LABEL,
  triggerFbsStockSync,
  upsertFbsWarehouseBinding,
  type FbsStockSyncStatus,
  type FbsStockSyncStatusItem,
  type FbsWarehouseBinding,
} from './fbsApi'

type SellerRow = { id: string; name: string }
type WmsWarehouseRow = { id: string; name: string; code: string }

type Props = {
  token: string
  authHeaders: (t: string) => Record<string, string>
  sellers: SellerRow[]
}

const STATUS_COLOR: Record<string, ChipProps['color']> = {
  pending: 'warning',
  confirmed: 'success',
  error: 'error',
  conflict: 'warning',
}

function StockSyncStatusChip({ status }: { status: string | null }) {
  if (!status) {
    return <Chip size="small" variant="outlined" label="—" data-testid="fbs-stock-status-chip" />
  }
  return (
    <Chip
      size="small"
      variant="outlined"
      color={STATUS_COLOR[status] ?? 'default'}
      label={STOCK_SYNC_STATUS_LABEL[status] ?? status}
      data-testid="fbs-stock-status-chip"
      data-status={status}
    />
  )
}

function formatDt(value: string | null): string {
  if (!value) return '—'
  const d = new Date(value)
  if (Number.isNaN(d.getTime())) return '—'
  return d.toLocaleString('ru-RU')
}

function stockErrorText(code: string | null): string | null {
  if (!code) return null
  const labels: Record<string, string> = {
    wb_unavailable: 'Wildberries временно недоступен',
    wb_auth_failed: 'Проверьте токен Wildberries',
    readback_mismatch: 'Wildberries принял не все остатки',
    product_mapping_missing: 'Не найден товар для выгрузки',
  }
  return labels[code] ?? 'Синхронизация завершилась с ошибкой'
}

function isSyncJob(
  body: { id?: string; bindings_processed?: number },
): body is { id: string; status: string } {
  return typeof body.id === 'string' && body.bindings_processed === undefined
}

export function FfFbsStockSyncScreen({ token, authHeaders, sellers }: Props) {
  const [selectedSellerId, setSelectedSellerId] = useState('')
  const [warehouses, setWarehouses] = useState<WmsWarehouseRow[]>([])
  const [bindings, setBindings] = useState<FbsWarehouseBinding[]>([])
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [feedback, setFeedback] = useState<string | null>(null)

  const [addOpen, setAddOpen] = useState(false)
  const [addWbId, setAddWbId] = useState('')
  const [addWmsId, setAddWmsId] = useState('')
  const [addSyncEnabled, setAddSyncEnabled] = useState(true)
  const [saving, setSaving] = useState(false)

  const [statusOpen, setStatusOpen] = useState(false)
  const [statusLoading, setStatusLoading] = useState(false)
  const [statusData, setStatusData] = useState<FbsStockSyncStatus | null>(null)
  const [statusWbId, setStatusWbId] = useState<number | null>(null)
  const [pendingDisable, setPendingDisable] = useState<FbsWarehouseBinding | null>(null)

  const wmsNameById = useMemo(() => {
    const m = new Map<string, string>()
    for (const w of warehouses) m.set(w.id, `${w.name} (${w.code})`)
    return m
  }, [warehouses])

  const activeBindings = useMemo(
    () => bindings.filter((b) => b.is_active),
    [bindings],
  )

  const loadWarehouses = useCallback(async () => {
    const res = await fetch(apiUrl('/warehouses'), { headers: { ...authHeaders(token) } })
    if (!res.ok) throw new Error(await readApiErrorMessage(res))
    setWarehouses((await res.json()) as WmsWarehouseRow[])
  }, [token, authHeaders])

  const loadBindings = useCallback(async () => {
    if (!selectedSellerId) {
      setBindings([])
      return
    }
    setError(null)
    setBusy(true)
    try {
      const rows = await fetchFbsWarehouseBindings(token, authHeaders, selectedSellerId)
      setBindings(rows)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Не удалось загрузить привязки')
      setBindings([])
    } finally {
      setBusy(false)
    }
  }, [token, authHeaders, selectedSellerId])

  useEffect(() => {
    if (sellers.length > 0 && !selectedSellerId) {
      setSelectedSellerId(sellers[0].id)
    }
  }, [sellers, selectedSellerId])

  useEffect(() => {
    void loadWarehouses().catch((e) => {
      setError(e instanceof Error ? e.message : 'Не удалось загрузить склады WMS')
    })
  }, [loadWarehouses])

  useEffect(() => {
    void loadBindings()
  }, [loadBindings])

  const handleAddBinding = useCallback(async () => {
    const wbId = Number(addWbId)
    if (!selectedSellerId || !addWmsId || !Number.isFinite(wbId) || wbId <= 0) {
      setError('Укажите селлера, ID склада WB и склад WMS')
      return
    }
    setSaving(true)
    setError(null)
    try {
      await upsertFbsWarehouseBinding(token, authHeaders, selectedSellerId, wbId, {
        wms_warehouse_id: addWmsId,
        stock_sync_enabled: addSyncEnabled,
      })
      setAddOpen(false)
      setFeedback('Привязка сохранена')
      await loadBindings()
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Не удалось сохранить привязку')
    } finally {
      setSaving(false)
    }
  }, [
    addSyncEnabled,
    addWbId,
    addWmsId,
    authHeaders,
    loadBindings,
    selectedSellerId,
    token,
  ])

  const handleToggleSync = useCallback(
    async (row: FbsWarehouseBinding) => {
      setError(null)
      try {
        await upsertFbsWarehouseBinding(
          token,
          authHeaders,
          selectedSellerId,
          row.wb_warehouse_id,
          {
            wms_warehouse_id: row.wms_warehouse_id,
            stock_sync_enabled: !row.stock_sync_enabled,
          },
        )
        await loadBindings()
      } catch (e) {
        setError(e instanceof Error ? e.message : 'Не удалось переключить синхронизацию')
      }
    },
    [authHeaders, loadBindings, selectedSellerId, token],
  )

  const handleDisable = useCallback(
    async (row: FbsWarehouseBinding) => {
      setError(null)
      try {
        await disableFbsWarehouseBinding(
          token,
          authHeaders,
          selectedSellerId,
          row.wb_warehouse_id,
        )
        setFeedback('Привязка отключена')
        setPendingDisable(null)
        await loadBindings()
      } catch (e) {
        setError(e instanceof Error ? e.message : 'Не удалось отключить привязку')
      }
    },
    [authHeaders, loadBindings, selectedSellerId, token],
  )

  const handleSync = useCallback(
    async (wbWarehouseId?: number) => {
      if (!selectedSellerId) return
      setError(null)
      setFeedback(null)
      setBusy(true)
      try {
        const result = await triggerFbsStockSync(
          token,
          authHeaders,
          selectedSellerId,
          wbWarehouseId ?? null,
        )
        if (isSyncJob(result)) {
          setFeedback(`Синхронизация поставлена в очередь (задача ${result.id})`)
        } else {
          setFeedback(
            `Синхронизация: обработано ${result.bindings_processed}, целевых ${result.products_targeted}, подтверждено ${result.products_confirmed}, ошибок ${result.errors}`,
          )
        }
        await loadBindings()
      } catch (e) {
        setError(e instanceof Error ? e.message : 'Синхронизация не удалась')
      } finally {
        setBusy(false)
      }
    },
    [authHeaders, loadBindings, selectedSellerId, token],
  )

  const openStatus = useCallback(
    async (wbWarehouseId: number) => {
      setStatusWbId(wbWarehouseId)
      setStatusOpen(true)
      setStatusData(null)
      setStatusLoading(true)
      try {
        const data = await fetchFbsStockSyncStatus(
          token,
          authHeaders,
          selectedSellerId,
          wbWarehouseId,
        )
        setStatusData(data)
      } catch (e) {
        setError(e instanceof Error ? e.message : 'Не удалось загрузить статус')
        setStatusOpen(false)
      } finally {
        setStatusLoading(false)
      }
    },
    [authHeaders, selectedSellerId, token],
  )

  return (
    <Box data-testid="fbs-stock-sync-screen">
      <Typography variant="h5" gutterBottom>
        FBS
      </Typography>
      <Typography variant="body2" color="text.secondary" sx={{ mb: 1 }}>
        Привязка складов Wildberries к складам WMS и ручная выгрузка остатков.
      </Typography>

      <FfFbsSectionNav showStockSync />

      {error ? (
        <Alert
          severity="error"
          sx={{ mb: 2 }}
          data-testid="fbs-stock-error"
          onClose={() => setError(null)}
        >
          {error}
        </Alert>
      ) : null}

      {feedback ? (
        <Alert
          severity="info"
          sx={{ mb: 2 }}
          data-testid="fbs-stock-sync-feedback"
          onClose={() => setFeedback(null)}
        >
          {feedback}
        </Alert>
      ) : null}

      <Paper variant="outlined" sx={{ p: 2, mb: 2 }} data-testid="fbs-stock-filters">
        <Stack
          direction={{ xs: 'column', sm: 'row' }}
          spacing={2}
          sx={{ alignItems: { sm: 'center' } }}
        >
          <FormControl size="small" sx={{ minWidth: 220 }}>
            <InputLabel id="fbs-stock-seller-label">Селлер</InputLabel>
            <Select
              labelId="fbs-stock-seller-label"
              label="Селлер"
              value={selectedSellerId}
              onChange={(e) => setSelectedSellerId(e.target.value)}
              data-testid="fbs-stock-seller-filter"
            >
              {sellers.map((s) => (
                <MenuItem key={s.id} value={s.id}>
                  {s.name}
                </MenuItem>
              ))}
            </Select>
          </FormControl>
          <Button
            variant="outlined"
            onClick={() => void loadBindings()}
            disabled={busy || !selectedSellerId}
            data-testid="fbs-stock-refresh"
          >
            Обновить
          </Button>
          <Button
            variant="contained"
            onClick={() => setAddOpen(true)}
            disabled={!selectedSellerId}
            data-testid="fbs-stock-add-binding"
          >
            Добавить привязку
          </Button>
          <Button
            variant="contained"
            color="secondary"
            onClick={() => void handleSync()}
            disabled={busy || !selectedSellerId || activeBindings.length === 0}
            data-testid="fbs-stock-sync-all"
          >
            Выгрузить остатки по всем складам
          </Button>
          {busy ? <CircularProgress size={20} data-testid="fbs-stock-loading" /> : null}
        </Stack>
      </Paper>

      <TableContainer component={Paper} variant="outlined" data-testid="fbs-stock-bindings-list">
        <Table size="small">
          <TableHead>
            <TableRow>
              <TableCell>Склад Wildberries</TableCell>
              <TableCell>Склад WMS</TableCell>
              <TableCell>Выгружать остатки</TableCell>
              <TableCell>Последний статус</TableCell>
              <TableCell>Обновлено</TableCell>
              <TableCell align="right">Действия</TableCell>
            </TableRow>
          </TableHead>
          <TableBody>
            {activeBindings.length === 0 ? (
              <TableRow>
                <TableCell colSpan={6}>
                  <Box sx={{ py: 3, textAlign: 'center' }} data-testid="fbs-stock-bindings-empty">
                    <Typography color="text.secondary">
                      Нет активных привязок. Добавьте склад WB и выберите склад WMS.
                    </Typography>
                  </Box>
                </TableCell>
              </TableRow>
            ) : (
              activeBindings.map((row) => (
                <TableRow key={row.id} data-testid="fbs-stock-binding-row">
                  <TableCell>{row.wb_warehouse_id}</TableCell>
                  <TableCell>
                    {wmsNameById.get(row.wms_warehouse_id) ?? row.wms_warehouse_id}
                  </TableCell>
                  <TableCell>
                    <Switch
                      size="small"
                      checked={row.stock_sync_enabled}
                      onChange={() => void handleToggleSync(row)}
                      data-testid="fbs-stock-sync-toggle"
                    />
                  </TableCell>
                  <TableCell>
                    <StockSyncStatusChip status={row.last_sync_status} />
                    {row.last_error_code ? (
                      <Typography variant="caption" color="error" sx={{ display: 'block' }}>
                        {stockErrorText(row.last_error_code)}
                      </Typography>
                    ) : null}
                  </TableCell>
                  <TableCell>{formatDt(row.last_sync_at)}</TableCell>
                  <TableCell align="right">
                    <Stack direction="row" spacing={1} sx={{ justifyContent: 'flex-end' }}>
                      <Button
                        size="small"
                        onClick={() => void handleSync(row.wb_warehouse_id)}
                        disabled={busy}
                        data-testid="fbs-stock-sync-one"
                      >
                        Выгрузить остатки
                      </Button>
                      <Button
                        size="small"
                        onClick={() => void openStatus(row.wb_warehouse_id)}
                        data-testid="fbs-stock-status-btn"
                      >
                        Статус
                      </Button>
                      <Button
                        size="small"
                        color="error"
                        onClick={() => setPendingDisable(row)}
                        data-testid="fbs-stock-disable-binding"
                      >
                        Отключить
                      </Button>
                    </Stack>
                  </TableCell>
                </TableRow>
              ))
            )}
          </TableBody>
        </Table>
      </TableContainer>

      <Dialog open={addOpen} onClose={() => setAddOpen(false)} maxWidth="sm" fullWidth>
        <DialogTitle>Связать склад Wildberries со складом WMS</DialogTitle>
        <DialogContent>
          <Stack spacing={2} sx={{ mt: 1 }}>
            <TextField
              label="Номер склада Wildberries"
              type="number"
              value={addWbId}
              onChange={(e) => setAddWbId(e.target.value)}
              helperText="Номер указан в кабинете продавца Wildberries"
              slotProps={{ htmlInput: { 'data-testid': 'fbs-stock-add-wb-id' } }}
            />
            <FormControl fullWidth>
              <InputLabel id="fbs-stock-add-wms-label">Склад WMS</InputLabel>
              <Select
                labelId="fbs-stock-add-wms-label"
                label="Склад WMS"
                value={addWmsId}
                onChange={(e) => setAddWmsId(e.target.value)}
                data-testid="fbs-stock-add-wms-select"
              >
                {warehouses.map((w) => (
                  <MenuItem key={w.id} value={w.id}>
                    {w.name} ({w.code})
                  </MenuItem>
                ))}
              </Select>
            </FormControl>
            <FormControlLabel
              control={
                <Switch
                  checked={addSyncEnabled}
                  onChange={(e) => setAddSyncEnabled(e.target.checked)}
                />
              }
              label="Автоматически выгружать остатки"
            />
          </Stack>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setAddOpen(false)}>Отмена</Button>
          <Button
            variant="contained"
            onClick={() => void handleAddBinding()}
            disabled={saving}
            data-testid="fbs-stock-add-save"
          >
            Сохранить
          </Button>
        </DialogActions>
      </Dialog>

      <Dialog
        open={pendingDisable !== null}
        onClose={() => setPendingDisable(null)}
        maxWidth="xs"
        fullWidth
      >
        <DialogTitle>Отключить связь складов?</DialogTitle>
        <DialogContent>
          <Typography>
            Новые заказы с этого склада перестанут попадать в правильный склад WMS, а остатки
            больше не будут выгружаться в Wildberries.
          </Typography>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setPendingDisable(null)}>Оставить связь</Button>
          <Button
            color="error"
            variant="contained"
            onClick={() => pendingDisable && void handleDisable(pendingDisable)}
          >
            Отключить
          </Button>
        </DialogActions>
      </Dialog>

      <Dialog
        open={statusOpen}
        onClose={() => setStatusOpen(false)}
        maxWidth="md"
        fullWidth
        data-testid="fbs-stock-status-panel"
      >
        <DialogTitle>
          Статус синхронизации — WB {statusWbId ?? '—'}
        </DialogTitle>
        <DialogContent>
          {statusLoading ? (
            <Box sx={{ py: 4, textAlign: 'center' }}>
              <CircularProgress data-testid="fbs-stock-status-loading" />
            </Box>
          ) : statusData ? (
            <Stack spacing={2}>
              <Stack direction="row" spacing={2} sx={{ alignItems: 'center' }}>
                <Typography variant="body2">Статус привязки:</Typography>
                <StockSyncStatusChip status={statusData.binding_last_sync_status} />
                {statusData.binding_last_error_code ? (
                  <Typography variant="caption" color="error">
                    {stockErrorText(statusData.binding_last_error_code)}
                  </Typography>
                ) : null}
              </Stack>
              <Table size="small">
                <TableHead>
                  <TableRow>
                    <TableCell>Товар Wildberries</TableCell>
                    <TableCell>Цель</TableCell>
                    <TableCell>Подтверждено</TableCell>
                    <TableCell>Статус</TableCell>
                    <TableCell>Ошибка</TableCell>
                  </TableRow>
                </TableHead>
                <TableBody>
                  {statusData.items.length === 0 ? (
                    <TableRow>
                      <TableCell colSpan={5}>
                        <Typography
                          color="text.secondary"
                          data-testid="fbs-stock-status-empty"
                        >
                          Нет позиций синхронизации
                        </Typography>
                      </TableCell>
                    </TableRow>
                  ) : (
                    statusData.items.map((item: FbsStockSyncStatusItem) => (
                      <TableRow key={item.chrt_id} data-testid="fbs-stock-status-row">
                        <TableCell>
                          <Typography variant="body2">Товар WB</Typography>
                          <Typography variant="caption" color="text.secondary">
                            ID {item.chrt_id}
                          </Typography>
                        </TableCell>
                        <TableCell>{item.target ?? '—'}</TableCell>
                        <TableCell>{item.confirmed ?? '—'}</TableCell>
                        <TableCell>
                          <StockSyncStatusChip status={item.status} />
                        </TableCell>
                        <TableCell>{item.error ?? '—'}</TableCell>
                      </TableRow>
                    ))
                  )}
                </TableBody>
              </Table>
            </Stack>
          ) : null}
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setStatusOpen(false)}>Закрыть</Button>
        </DialogActions>
      </Dialog>
    </Box>
  )
}
