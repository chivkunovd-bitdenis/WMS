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
  Typography,
} from '@mui/material'
import type { ChipProps } from '@mui/material'
import { apiUrl } from '../../api'
import { readApiErrorMessage } from '../../utils/readApiErrorMessage'
import { FfFbsSectionNav } from './FfFbsSectionNav'
import {
  disableFbsWarehouseBinding,
  fetchFbsSellerOffices,
  fetchFbsSellerWarehouses,
  fetchFbsStockSyncStatus,
  fetchFbsWarehouseBindings,
  STOCK_SYNC_STATUS_LABEL,
  triggerFbsStockSync,
  upsertFbsWarehouseBinding,
  type FbsSellerOffice,
  type FbsSellerWarehouse,
  type FbsStockSyncStatus,
  type FbsStockSyncStatusItem,
  type FbsWarehouseBinding,
} from './fbsApi'

type SellerRow = { id: string; name: string }
type WmsWarehouseRow = { id: string; name: string; code: string }
type InventoryBalanceSummaryRow = { quantity_fbs: number }

type Props = {
  token: string
  authHeaders: (t: string) => Record<string, string>
  sellers: SellerRow[]
}

type SellerWarehouseView = {
  wbId: number
  name: string
  address: string | null
  city: string
  wbStatus: string
  binding: FbsWarehouseBinding | null
  selectedWmsId: string
  isMapped: boolean
  isTechnicalBinding: boolean
  stockSyncEnabled: boolean
  fbsStockTotal: number | null
  lastSyncStatus: string | null
  lastSyncAt: string | null
  lastErrorCode: string | null
}

const STATUS_COLOR: Record<string, ChipProps['color']> = {
  pending: 'warning',
  confirmed: 'success',
  error: 'error',
  conflict: 'warning',
}

function isSyncJob(
  body: { id?: string; bindings_processed?: number },
): body is { id: string; status: string } {
  return typeof body.id === 'string' && body.bindings_processed === undefined
}

function isTechnicalWmsWarehouse(row: WmsWarehouseRow | undefined): boolean {
  if (!row) return false
  return row.code.startsWith('fbs-wb-') || row.name.startsWith('FBS WB ')
}

function StockSyncStatusChip({ status }: { status: string | null }) {
  if (!status) {
    return (
      <Chip size="small" variant="outlined" label="не запускалась" data-testid="fbs-stock-status-chip" />
    )
  }
  return (
    <Chip
      size="small"
      variant="outlined"
      color={STATUS_COLOR[status] ?? 'default'}
      label={STOCK_SYNC_STATUS_LABEL[status] ?? 'требует проверки'}
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
    wb_token_read_only_401:
      'Ключ WB создан «только на чтение». Нужен ключ с правом публикации остатков.',
  }
  return labels[code] ?? 'Синхронизация завершилась с ошибкой'
}

function warehouseStatus(row: FbsSellerWarehouse | undefined): string {
  if (!row) return 'требует настройки'
  if (row.isDeleting) return 'удаляется в WB'
  if (row.isProcessing) return 'обновляется в WB'
  return 'активен в WB'
}

function bindingText(row: SellerWarehouseView): string {
  if (!row.binding || !row.binding.is_active || row.isTechnicalBinding) {
    return 'склад не сопоставлен'
  }
  return row.stockSyncEnabled ? 'публикация включена' : 'готов к публикации'
}

function bindingColor(row: SellerWarehouseView): ChipProps['color'] {
  if (!row.binding || !row.binding.is_active || row.isTechnicalBinding) return 'warning'
  return row.stockSyncEnabled ? 'success' : 'default'
}

function formatFbsStockTotal(value: number | null): string {
  return value == null ? '—' : `${value} шт`
}

export function FfFbsStockSyncScreen({ token, authHeaders, sellers }: Props) {
  const [selectedSellerId, setSelectedSellerId] = useState('')
  const [warehouses, setWarehouses] = useState<WmsWarehouseRow[]>([])
  const [sellerWarehouses, setSellerWarehouses] = useState<FbsSellerWarehouse[]>([])
  const [sellerOffices, setSellerOffices] = useState<FbsSellerOffice[]>([])
  const [bindings, setBindings] = useState<FbsWarehouseBinding[]>([])
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [feedback, setFeedback] = useState<string | null>(null)
  const [stockTotalsByWarehouseId, setStockTotalsByWarehouseId] = useState<
    Record<string, number>
  >({})
  const [savingWbId, setSavingWbId] = useState<number | null>(null)

  const [statusOpen, setStatusOpen] = useState(false)
  const [statusLoading, setStatusLoading] = useState(false)
  const [statusData, setStatusData] = useState<FbsStockSyncStatus | null>(null)
  const [statusWbId, setStatusWbId] = useState<number | null>(null)
  const [pendingDisable, setPendingDisable] = useState<SellerWarehouseView | null>(null)

  const wmsById = useMemo(() => {
    const m = new Map<string, WmsWarehouseRow>()
    for (const w of warehouses) m.set(w.id, w)
    return m
  }, [warehouses])

  const physicalWarehouses = useMemo(
    () => warehouses.filter((w) => !isTechnicalWmsWarehouse(w)),
    [warehouses],
  )

  const officeCityById = useMemo(() => {
    const m = new Map<number, string>()
    for (const office of sellerOffices) {
      const city = office.city?.trim()
      if (!city) continue
      if (office.officeId != null) m.set(office.officeId, city)
      if (office.id != null) m.set(office.id, city)
    }
    return m
  }, [sellerOffices])

  const bindingsByWbId = useMemo(() => {
    const m = new Map<number, FbsWarehouseBinding>()
    for (const b of bindings) m.set(b.wb_warehouse_id, b)
    return m
  }, [bindings])

  const rows = useMemo<SellerWarehouseView[]>(() => {
    const byWb = new Map<number, FbsSellerWarehouse | undefined>()
    for (const wh of sellerWarehouses) {
      if (wh.id != null) byWb.set(wh.id, wh)
    }
    for (const binding of bindings) {
      if (!byWb.has(binding.wb_warehouse_id)) {
        byWb.set(binding.wb_warehouse_id, undefined)
      }
    }
    return Array.from(byWb.entries())
      .sort(([a], [b]) => a - b)
      .map(([wbId, wb]) => {
        const binding = bindingsByWbId.get(wbId) ?? null
        const wms = binding ? wmsById.get(binding.wms_warehouse_id) : undefined
        const technical = Boolean(binding && isTechnicalWmsWarehouse(wms))
        const mapped = Boolean(binding?.is_active && wms && !technical)
        const city =
          wb?.officeId != null ? officeCityById.get(wb.officeId) : undefined
        return {
          wbId,
          name: wb?.name?.trim() || `WB ${wbId}`,
          address: wb?.address?.trim() || null,
          city: city || 'город не определён',
          wbStatus: warehouseStatus(wb),
          binding,
          selectedWmsId: mapped && binding ? binding.wms_warehouse_id : '',
          isMapped: mapped,
          isTechnicalBinding: technical,
          stockSyncEnabled: Boolean(mapped && binding?.stock_sync_enabled),
          fbsStockTotal:
            mapped && binding
              ? stockTotalsByWarehouseId[binding.wms_warehouse_id] ?? null
              : null,
          lastSyncStatus: binding?.last_sync_status ?? null,
          lastSyncAt: binding?.last_sync_at ?? null,
          lastErrorCode: binding?.last_error_code ?? null,
        }
      })
  }, [
    bindings,
    bindingsByWbId,
    officeCityById,
    sellerWarehouses,
    stockTotalsByWarehouseId,
    wmsById,
  ])

  const syncableRows = useMemo(
    () => rows.filter((row) => row.isMapped && row.stockSyncEnabled),
    [rows],
  )

  const loadWarehouses = useCallback(async () => {
    const res = await fetch(apiUrl('/warehouses'), { headers: { ...authHeaders(token) } })
    if (!res.ok) throw new Error(await readApiErrorMessage(res))
    setWarehouses((await res.json()) as WmsWarehouseRow[])
  }, [token, authHeaders])

  const loadSellerWarehouseData = useCallback(async () => {
    if (!selectedSellerId) {
      setBindings([])
      setSellerWarehouses([])
      setSellerOffices([])
      return
    }
    setError(null)
    setBusy(true)
    try {
      const bindingRows = await fetchFbsWarehouseBindings(token, authHeaders, selectedSellerId)
      setBindings(bindingRows)
      try {
        const [wbRows, officeRows] = await Promise.all([
          fetchFbsSellerWarehouses(token, authHeaders, selectedSellerId),
          fetchFbsSellerOffices(token, authHeaders, selectedSellerId),
        ])
        setSellerWarehouses(wbRows)
        setSellerOffices(officeRows)
      } catch (e) {
        setSellerWarehouses([])
        setSellerOffices([])
        setError(
          e instanceof Error
            ? e.message
            : 'Склады WB не загружены: подключите токен WB Marketplace или обновите список',
        )
      }
    } catch (e) {
      setBindings([])
      setSellerWarehouses([])
      setSellerOffices([])
      setError(e instanceof Error ? e.message : 'Не удалось загрузить склады селлера')
    } finally {
      setBusy(false)
    }
  }, [token, authHeaders, selectedSellerId])

  const loadStockTotals = useCallback(
    async (bindingRows: FbsWarehouseBinding[]) => {
      if (!selectedSellerId) {
        setStockTotalsByWarehouseId({})
        return
      }
      const physicalBindingRows = bindingRows.filter((binding) => {
        const wms = wmsById.get(binding.wms_warehouse_id)
        return binding.is_active && wms && !isTechnicalWmsWarehouse(wms)
      })
      if (physicalBindingRows.length === 0) {
        setStockTotalsByWarehouseId({})
        return
      }
      const warehouseIds = [...new Set(physicalBindingRows.map((row) => row.wms_warehouse_id))]
      const entries = await Promise.all(
        warehouseIds.map(async (warehouseId) => {
          const qs = new URLSearchParams({
            seller_id: selectedSellerId,
            warehouse_id: warehouseId,
          })
          const res = await fetch(apiUrl(`/operations/inventory-balances/summary?${qs}`), {
            headers: { ...authHeaders(token) },
          })
          if (!res.ok) throw new Error(await readApiErrorMessage(res))
          const summary = (await res.json()) as InventoryBalanceSummaryRow[]
          const total = summary.reduce(
            (sum, row) => sum + Math.max(0, Number(row.quantity_fbs) || 0),
            0,
          )
          return [warehouseId, total] as const
        }),
      )
      setStockTotalsByWarehouseId(Object.fromEntries(entries))
    },
    [authHeaders, selectedSellerId, token, wmsById],
  )

  useEffect(() => {
    const currentExists = sellers.some((s) => s.id === selectedSellerId)
    if (sellers.length > 0 && (!selectedSellerId || !currentExists)) {
      setSelectedSellerId(sellers[0].id)
    }
  }, [sellers, selectedSellerId])

  useEffect(() => {
    void loadWarehouses().catch((e) => {
      setError(e instanceof Error ? e.message : 'Не удалось загрузить склады WMS')
    })
  }, [loadWarehouses])

  useEffect(() => {
    void loadSellerWarehouseData()
  }, [loadSellerWarehouseData])

  useEffect(() => {
    void loadStockTotals(bindings).catch(() => {
      setStockTotalsByWarehouseId({})
    })
  }, [bindings, loadStockTotals])

  const handleBind = useCallback(
    async (row: SellerWarehouseView, wmsWarehouseId: string) => {
      if (!selectedSellerId) return
      if (!wmsWarehouseId) {
        if (row.binding?.is_active) setPendingDisable(row)
        return
      }
      setSavingWbId(row.wbId)
      setError(null)
      try {
        await upsertFbsWarehouseBinding(token, authHeaders, selectedSellerId, row.wbId, {
          wms_warehouse_id: wmsWarehouseId,
          stock_sync_enabled: row.isMapped ? row.stockSyncEnabled : false,
        })
        setFeedback('Склад WB сопоставлен со складом WMS')
        await loadSellerWarehouseData()
      } catch (e) {
        setError(e instanceof Error ? e.message : 'Не удалось сохранить сопоставление')
      } finally {
        setSavingWbId(null)
      }
    },
    [authHeaders, loadSellerWarehouseData, selectedSellerId, token],
  )

  const handleToggleSync = useCallback(
    async (row: SellerWarehouseView) => {
      if (!row.binding || !row.isMapped || !selectedSellerId) return
      setError(null)
      setSavingWbId(row.wbId)
      try {
        await upsertFbsWarehouseBinding(token, authHeaders, selectedSellerId, row.wbId, {
          wms_warehouse_id: row.binding.wms_warehouse_id,
          stock_sync_enabled: !row.stockSyncEnabled,
        })
        setFeedback(!row.stockSyncEnabled ? 'Публикация включена' : 'Публикация выключена')
        await loadSellerWarehouseData()
      } catch (e) {
        setError(e instanceof Error ? e.message : 'Не удалось переключить публикацию')
      } finally {
        setSavingWbId(null)
      }
    },
    [authHeaders, loadSellerWarehouseData, selectedSellerId, token],
  )

  const handleDisable = useCallback(async () => {
    if (!pendingDisable?.binding || !selectedSellerId) return
    setError(null)
    setSavingWbId(pendingDisable.wbId)
    try {
      await disableFbsWarehouseBinding(
        token,
        authHeaders,
        selectedSellerId,
        pendingDisable.wbId,
      )
      setFeedback('Сопоставление отключено')
      setPendingDisable(null)
      await loadSellerWarehouseData()
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Не удалось отключить сопоставление')
    } finally {
      setSavingWbId(null)
    }
  }, [authHeaders, loadSellerWarehouseData, pendingDisable, selectedSellerId, token])

  const handleSync = useCallback(
    async (row?: SellerWarehouseView) => {
      if (!selectedSellerId) return
      if (row && !row.isMapped) {
        setError('Сначала сопоставьте склад WB со складом WMS')
        return
      }
      setError(null)
      setFeedback(null)
      setBusy(true)
      try {
        const result = await triggerFbsStockSync(
          token,
          authHeaders,
          selectedSellerId,
          row?.wbId ?? null,
        )
        if (isSyncJob(result)) {
          setFeedback(`Синхронизация поставлена в очередь (задача ${result.id})`)
        } else {
          setFeedback(
            `Синхронизация: складов ${result.bindings_processed}, товаров ${result.products_targeted}, подтверждено ${result.products_confirmed}, ошибок ${result.errors}`,
          )
        }
        await loadSellerWarehouseData()
      } catch (e) {
        setError(e instanceof Error ? e.message : 'Синхронизация не удалась')
      } finally {
        setBusy(false)
      }
    },
    [authHeaders, loadSellerWarehouseData, selectedSellerId, token],
  )

  const openStatus = useCallback(
    async (row: SellerWarehouseView) => {
      if (!row.binding) return
      setStatusWbId(row.wbId)
      setStatusOpen(true)
      setStatusData(null)
      setStatusLoading(true)
      try {
        const data = await fetchFbsStockSyncStatus(
          token,
          authHeaders,
          selectedSellerId,
          row.wbId,
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
        Склады селлера WB, сопоставление с физическими складами WMS и публикация остатков.
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

      {physicalWarehouses.length === 0 ? (
        <Alert severity="warning" sx={{ mb: 2 }} data-testid="fbs-stock-no-wms">
          Создайте WMS-склад перед сопоставлением складов WB.
        </Alert>
      ) : null}

      <Paper variant="outlined" sx={{ p: 2, mb: 2 }} data-testid="fbs-stock-filters">
        <Stack
          direction={{ xs: 'column', sm: 'row' }}
          spacing={2}
          sx={{ alignItems: { sm: 'center' } }}
        >
          <FormControl size="small" sx={{ minWidth: 240 }}>
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
            onClick={() => void loadSellerWarehouseData()}
            disabled={busy || !selectedSellerId}
            data-testid="fbs-stock-refresh"
          >
            Обновить
          </Button>
          <Button
            variant="contained"
            onClick={() => void handleSync()}
            disabled={busy || !selectedSellerId || syncableRows.length === 0}
            data-testid="fbs-stock-sync-all"
          >
            Выгрузить остатки по включённым складам
          </Button>
          {busy ? <CircularProgress size={20} data-testid="fbs-stock-loading" /> : null}
        </Stack>
      </Paper>

      <TableContainer component={Paper} variant="outlined" data-testid="fbs-stock-bindings-list">
        <Table size="small">
          <TableHead>
            <TableRow>
              <TableCell>Склад WB</TableCell>
              <TableCell>Город</TableCell>
              <TableCell>Адрес</TableCell>
              <TableCell>Состояние</TableCell>
              <TableCell>Склад WMS</TableCell>
              <TableCell>FBS остаток</TableCell>
              <TableCell>Публикация</TableCell>
              <TableCell>Последнее подтверждение</TableCell>
              <TableCell align="right">Действия</TableCell>
            </TableRow>
          </TableHead>
          <TableBody>
            {rows.length === 0 ? (
              <TableRow>
                <TableCell colSpan={9}>
                  <Box sx={{ py: 3, textAlign: 'center' }} data-testid="fbs-stock-bindings-empty">
                    <Typography color="text.secondary">
                      Склады WB не загружены: подключите токен WB Marketplace или обновите список.
                    </Typography>
                  </Box>
                </TableCell>
              </TableRow>
            ) : (
              rows.map((row) => (
                <TableRow key={row.wbId} data-testid="fbs-stock-binding-row">
                  <TableCell>
                    <Typography variant="body2" sx={{ fontWeight: 650 }}>
                      {row.name}
                    </Typography>
                    <Typography variant="caption" color="text.secondary">
                      WB ID {row.wbId}
                    </Typography>
                  </TableCell>
                  <TableCell>{row.city}</TableCell>
                  <TableCell>{row.address || 'адрес не указан'}</TableCell>
                  <TableCell>{row.wbStatus}</TableCell>
                  <TableCell sx={{ minWidth: 230 }}>
                    <FormControl size="small" fullWidth>
                      <InputLabel id={`fbs-stock-wms-label-${row.wbId}`}>Склад WMS</InputLabel>
                      <Select
                        labelId={`fbs-stock-wms-label-${row.wbId}`}
                        label="Склад WMS"
                        value={row.selectedWmsId}
                        onChange={(e) => void handleBind(row, e.target.value)}
                        disabled={savingWbId === row.wbId || physicalWarehouses.length === 0}
                        data-testid="fbs-stock-row-wms-select"
                      >
                        <MenuItem value="">склад не сопоставлен</MenuItem>
                        {physicalWarehouses.map((w) => (
                          <MenuItem key={w.id} value={w.id}>
                            {w.name} ({w.code})
                          </MenuItem>
                        ))}
                      </Select>
                    </FormControl>
                    {row.isTechnicalBinding ? (
                      <Typography variant="caption" color="warning.main">
                        Старый технический склад не используется для публикации.
                      </Typography>
                    ) : null}
                  </TableCell>
                  <TableCell data-testid="fbs-stock-total">
                    {formatFbsStockTotal(row.fbsStockTotal)}
                  </TableCell>
                  <TableCell>
                    <Stack spacing={0.75}>
                      <Chip
                        size="small"
                        variant="outlined"
                        color={bindingColor(row)}
                        label={bindingText(row)}
                        data-testid="fbs-stock-binding-state"
                      />
                      <Stack direction="row" spacing={1} sx={{ alignItems: 'center' }}>
                        <Switch
                          size="small"
                          checked={row.stockSyncEnabled}
                          onChange={() => void handleToggleSync(row)}
                          disabled={!row.isMapped || savingWbId === row.wbId}
                          data-testid="fbs-stock-sync-toggle"
                        />
                        <StockSyncStatusChip status={row.lastSyncStatus} />
                      </Stack>
                      {row.lastErrorCode ? (
                        <Typography variant="caption" color="error">
                          {stockErrorText(row.lastErrorCode)}
                        </Typography>
                      ) : null}
                    </Stack>
                  </TableCell>
                  <TableCell>{formatDt(row.lastSyncAt)}</TableCell>
                  <TableCell align="right">
                    <Stack direction="row" spacing={1} sx={{ justifyContent: 'flex-end' }}>
                      <Button
                        size="small"
                        onClick={() => void handleSync(row)}
                        disabled={busy || !row.isMapped || !row.stockSyncEnabled}
                        data-testid="fbs-stock-sync-one"
                      >
                        Выгрузить
                      </Button>
                      <Button
                        size="small"
                        onClick={() => void openStatus(row)}
                        disabled={!row.binding}
                        data-testid="fbs-stock-status-btn"
                      >
                        Статус
                      </Button>
                      <Button
                        size="small"
                        color="error"
                        onClick={() => setPendingDisable(row)}
                        disabled={!row.binding?.is_active || savingWbId === row.wbId}
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

      <Dialog
        open={pendingDisable !== null}
        onClose={() => setPendingDisable(null)}
        maxWidth="xs"
        fullWidth
      >
        <DialogTitle>Отключить сопоставление складов?</DialogTitle>
        <DialogContent>
          <Typography>
            Новые заказы с этого WB-склада останутся видимыми, но будут заблокированы до
            нового сопоставления со складом WMS.
          </Typography>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setPendingDisable(null)}>Оставить связь</Button>
          <Button color="error" variant="contained" onClick={() => void handleDisable()}>
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
        <DialogTitle>Статус синхронизации — WB {statusWbId ?? '—'}</DialogTitle>
        <DialogContent>
          {statusLoading ? (
            <Box sx={{ py: 4, textAlign: 'center' }}>
              <CircularProgress data-testid="fbs-stock-status-loading" />
            </Box>
          ) : statusData ? (
            <Stack spacing={2}>
              <Stack direction="row" spacing={2} sx={{ alignItems: 'center' }}>
                <Typography variant="body2">Статус сопоставления:</Typography>
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
                    <TableCell>К публикации</TableCell>
                    <TableCell>Подтверждено WB</TableCell>
                    <TableCell>Статус</TableCell>
                    <TableCell>Ошибка</TableCell>
                  </TableRow>
                </TableHead>
                <TableBody>
                  {statusData.items.length === 0 ? (
                    <TableRow>
                      <TableCell colSpan={5}>
                        <Typography color="text.secondary" data-testid="fbs-stock-status-empty">
                          Нет позиций синхронизации
                        </Typography>
                        <Typography variant="caption" color="text.secondary">
                          В выгрузку попадают только товары, у которых включена продажа по FBS.
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
                        <TableCell>{stockErrorText(item.error) ?? '—'}</TableCell>
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
