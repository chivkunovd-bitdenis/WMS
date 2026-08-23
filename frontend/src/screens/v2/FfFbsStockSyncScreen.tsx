import { useCallback, useEffect, useMemo, useState, type MouseEvent } from 'react'
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
  IconButton,
  InputLabel,
  Menu,
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
  Tooltip,
  Typography,
} from '@mui/material'
import type { ChipProps } from '@mui/material'
import MoreVertIcon from '@mui/icons-material/MoreVert'
import { apiUrl } from '../../api'
import { useWarehouseContext } from '../../contexts/WarehouseContext'
import { readApiErrorMessage } from '../../utils/readApiErrorMessage'
import { FbsStockAllocationDialog } from './FbsStockAllocationDialog'
import { FfFbsSectionNav } from './FfFbsSectionNav'
import { EmptyState, WarehouseContextSwitch } from '../../ui-kit'
import {
  disableFbsWarehouseBinding,
  FbsApiError,
  fetchFbsBindingStockPool,
  fetchFbsSellerOffices,
  fetchFbsSellerWarehouses,
  fetchFbsStockSyncStatus,
  fetchFbsWarehouseBindings,
  setFbsBindingStockPoolQuantity,
  STOCK_SYNC_STATUS_LABEL,
  triggerFbsStockSync,
  upsertFbsWarehouseBinding,
  type FbsSellerOffice,
  type FbsSellerWarehouse,
  type FbsStockPoolProduct,
  type FbsStockSyncStatus,
  type FbsStockSyncStatusItem,
  type FbsWarehouseBinding,
} from './fbsApi'

type SellerRow = { id: string; name: string }
type WmsWarehouseRow = { id: string; name: string; code: string }
type InventoryBalanceSummaryRow = { quantity: number }

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
  allocatedPoolTotal: number
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
    unsafe_zero_blocked:
      'Остаток не опубликован: защита не даёт обнулить остаток в кабинете продавца. Проверьте наличие товара на складе и запустите синхронизацию заново.',
    unsafe_stock_unknown:
      'Остаток не опубликован: не удалось надёжно посчитать доступное количество для этого товара.',
  }
  return labels[code] ?? 'Синхронизация завершилась с ошибкой'
}

// Человеческое сообщение для сбоя загрузки складов/офисов селлера с Wildberries
// (GET .../warehouses, .../offices). Бэкенд для многих кодов wb_* отдаёт общий
// текст «Ошибка Wildberries.» (см. backend/app/api/fbs_errors.py:139-146,
// fbs_error_message — код не найден в словаре FBS_ERROR_MESSAGES_RU, поэтому
// используется заглушка для всех kодов с префиксом wb_). Код ошибки при этом
// до фронта доезжает (структурированный envelope {code, message}), поэтому
// различаем причины здесь, не трогая бэкенд.
// У селлера один ключ WB на всё — второй ключ не запрашиваем никогда.
function sellerWarehousesLoadErrorMessage(e: unknown): string {
  if (e instanceof FbsApiError) {
    if (e.code === 'missing_marketplace_token') {
      return 'У селлера не подключён ключ Wildberries. Откройте карточку селлера и добавьте ключ WB.'
    }
    if (e.code === 'seller_not_found') {
      return 'Селлер не найден.'
    }
    if (/_(401|403)$/.test(e.code)) {
      return 'Wildberries не принял ключ селлера (нет прав на этот запрос). Перевыпустите ключ WB в личном кабинете продавца со всеми правами и сохраните его в карточке селлера.'
    }
    if (e.code === 'wb_transport_error') {
      return 'Не удалось связаться с Wildberries — сервер не ответил. Проверьте соединение и нажмите «Обновить».'
    }
    if (e.code.startsWith('wb_')) {
      return 'Wildberries вернул ошибку при загрузке списка складов. Нажмите «Обновить»; если повторится — перевыпустите ключ WB в личном кабинете продавца со всеми правами.'
    }
    return e.message
  }
  return e instanceof Error ? e.message : 'Не удалось загрузить склады WB'
}

function warehouseStatus(row: FbsSellerWarehouse | undefined): string {
  if (!row) return 'требует настройки'
  if (row.isDeleting) return 'удаляется в WB'
  if (row.isProcessing) return 'обновляется в WB'
  return 'активен в WB'
}

type RowStateInfo = { label: string; color: ChipProps['color']; detail?: string }

// Короткая метка (2-3 слова) для узкой колонки строки; подробности — в detail,
// который показывается во всплывающей подсказке по наведению, а не текстом в строке.
function rowStateInfo(row: SellerWarehouseView): RowStateInfo {
  if (!row.binding || !row.binding.is_active || row.isTechnicalBinding) {
    return { label: 'склад не сопоставлен', color: 'warning' }
  }
  if (!row.stockSyncEnabled) {
    return {
      label: 'публикация выключена',
      color: 'default',
      detail: row.lastErrorCode
        ? stockErrorText(row.lastErrorCode) ?? 'Синхронизация завершилась с ошибкой'
        : undefined,
    }
  }
  if (row.lastErrorCode) {
    return {
      label: 'ошибка публикации',
      color: 'error',
      detail: stockErrorText(row.lastErrorCode) ?? 'Синхронизация завершилась с ошибкой',
    }
  }
  if (row.lastSyncStatus === 'confirmed') {
    return { label: 'публикация включена', color: 'success', detail: 'Wildberries подтвердил остаток' }
  }
  if (row.lastSyncStatus === 'pending') {
    return {
      label: 'публикация включена',
      color: 'warning',
      detail: 'Ждём подтверждения от Wildberries',
    }
  }
  if (row.lastSyncStatus === 'conflict') {
    return {
      label: 'публикация включена',
      color: 'warning',
      detail: 'Wildberries вернул расхождение по остатку',
    }
  }
  if (row.lastSyncStatus === 'nothing_to_publish') {
    return {
      label: 'нечего публиковать',
      color: 'warning',
      detail:
        'Ни по одному товару не задано распределение остатка на этот склад — нажмите «Остатки» и укажите количество',
    }
  }
  return {
    label: 'публикация включена',
    color: 'default',
    detail: 'Синхронизация ещё не запускалась',
  }
}

function formatFbsStockTotal(value: number | null): string {
  return value == null ? '—' : `${value} шт`
}

export function FfFbsStockSyncScreen({ token, authHeaders, sellers }: Props) {
  const {
    warehouses,
    selectedWarehouseId: selectedOperationalWarehouseId,
    setWarehouses: setContextWarehouses,
    selectWarehouse,
  } = useWarehouseContext('fulfillment')
  const [selectedSellerId, setSelectedSellerId] = useState('')
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

  const [poolOpen, setPoolOpen] = useState(false)
  const [poolLoading, setPoolLoading] = useState(false)
  const [poolRow, setPoolRow] = useState<SellerWarehouseView | null>(null)
  const [poolItems, setPoolItems] = useState<FbsStockPoolProduct[]>([])
  const [poolDrafts, setPoolDrafts] = useState<Record<string, string>>({})
  const [poolSavingAll, setPoolSavingAll] = useState(false)
  const [poolError, setPoolError] = useState<string | null>(null)
  const [rowMenuAnchor, setRowMenuAnchor] = useState<{ wbId: number; el: HTMLElement } | null>(
    null,
  )

  const wmsById = useMemo(() => {
    const m = new Map<string, WmsWarehouseRow>()
    for (const w of warehouses) m.set(w.id, w)
    return m
  }, [warehouses])

  const physicalWarehouses = useMemo(
    () => warehouses.filter((w) => !isTechnicalWmsWarehouse(w)),
    [warehouses],
  )

  const operationalWarehouseOptions = useMemo(
    () => physicalWarehouses.map((warehouse) => ({ id: warehouse.id, name: warehouse.name })),
    [physicalWarehouses],
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
          allocatedPoolTotal: binding?.allocated_pool_total ?? 0,
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
    () =>
      rows.filter(
        (row) =>
          row.isMapped &&
          row.stockSyncEnabled &&
          row.selectedWmsId === selectedOperationalWarehouseId,
      ),
    [rows, selectedOperationalWarehouseId],
  )

  const visibleRows = useMemo(
    () =>
      rows.filter((row) => row.isMapped && row.selectedWmsId === selectedOperationalWarehouseId),
    [rows, selectedOperationalWarehouseId],
  )

  const hasOperationalWarehouses = physicalWarehouses.length > 0

  const loadWarehouses = useCallback(async () => {
    const res = await fetch(apiUrl('/warehouses'), { headers: { ...authHeaders(token) } })
    if (!res.ok) throw new Error(await readApiErrorMessage(res))
    setContextWarehouses((await res.json()) as WmsWarehouseRow[])
  }, [authHeaders, setContextWarehouses, token])

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
        setError(sellerWarehousesLoadErrorMessage(e))
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
            (sum, row) => sum + Math.max(0, Number(row.quantity) || 0),
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
          setFeedback('Синхронизация поставлена в очередь')
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

  const openPool = useCallback(
    async (row: SellerWarehouseView) => {
      if (!row.binding || !selectedSellerId) return
      setPoolRow(row)
      setPoolOpen(true)
      setPoolError(null)
      setPoolItems([])
      setPoolLoading(true)
      try {
        const items = await fetchFbsBindingStockPool(token, authHeaders, selectedSellerId, row.wbId)
        setPoolItems(items)
        setPoolDrafts(
          Object.fromEntries(items.map((it) => [it.product_id, String(it.allocated_this_binding)])),
        )
      } catch (e) {
        setPoolError(e instanceof Error ? e.message : 'Не удалось загрузить распределение пула')
      } finally {
        setPoolLoading(false)
      }
    },
    [authHeaders, selectedSellerId, token],
  )

  const handleSaveAllPoolChanges = useCallback(async () => {
    if (!poolRow || !selectedSellerId) return
    const dirtyItems = poolItems.filter((item) => {
      const draft = poolDrafts[item.product_id]
      return draft !== undefined && draft !== String(item.allocated_this_binding)
    })
    if (dirtyItems.length === 0) return
    for (const item of dirtyItems) {
      const draft = poolDrafts[item.product_id] ?? ''
      const quantity = Number(draft)
      if (!Number.isFinite(quantity) || quantity < 0 || !Number.isInteger(quantity)) {
        setPoolError(`«${item.name}»: количество должно быть целым числом не меньше нуля`)
        return
      }
    }
    setPoolError(null)
    setPoolSavingAll(true)
    try {
      for (const item of dirtyItems) {
        const quantity = Number(poolDrafts[item.product_id])
        await setFbsBindingStockPoolQuantity(
          token,
          authHeaders,
          selectedSellerId,
          poolRow.wbId,
          item.product_id,
          quantity,
        )
      }
      setFeedback('Изменения остатков по складу сохранены')
      const items = await fetchFbsBindingStockPool(token, authHeaders, selectedSellerId, poolRow.wbId)
      setPoolItems(items)
      setPoolDrafts(
        Object.fromEntries(items.map((it) => [it.product_id, String(it.allocated_this_binding)])),
      )
      await loadSellerWarehouseData()
    } catch (e) {
      setPoolError(e instanceof Error ? e.message : 'Не удалось сохранить распределение')
    } finally {
      setPoolSavingAll(false)
    }
  }, [authHeaders, loadSellerWarehouseData, poolDrafts, poolItems, poolRow, selectedSellerId, token])

  const handlePoolDraftChange = useCallback((productId: string, value: string) => {
    setPoolDrafts((prev) => ({ ...prev, [productId]: value }))
  }, [])

  return (
    <Box
      data-testid="fbs-stock-sync-screen"
      sx={{
        minWidth: 0,
        width: '100%',
        maxWidth: 'calc(100vw - 308px)',
        boxSizing: 'border-box',
        overflowX: 'hidden',
      }}
    >
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

      {!hasOperationalWarehouses ? (
        <Box sx={{ mb: 2 }} data-testid="fbs-stock-no-wms">
          <EmptyState
            title="Нет рабочего склада"
            hint="Попросите администратора добавить рабочий склад. Служебные склады Wildberries здесь не считаются."
          />
        </Box>
      ) : (
        <>

          <WarehouseContextSwitch
            options={operationalWarehouseOptions}
            value={selectedOperationalWarehouseId}
            onChange={selectWarehouse}
            loading={busy && physicalWarehouses.length === 0}
            testId="fbs-stock-warehouse-context"
          />

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
            Выгрузить остатки
          </Button>
          {busy ? <CircularProgress size={20} data-testid="fbs-stock-loading" /> : null}
        </Stack>
          </Paper>

          <TableContainer
        component={Paper}
        variant="outlined"
        data-testid="fbs-stock-bindings-list"
        sx={{ overflowX: 'auto' }}
      >
        <Table
          size="small"
          sx={{
            tableLayout: 'fixed',
            width: '100%',
            minWidth: 760,
            '& th, & td': {
              px: 1,
              py: 1.25,
              verticalAlign: 'top',
            },
          }}
        >
          <TableHead>
            <TableRow>
              <TableCell sx={{ width: '18%' }}>Склад WB</TableCell>
              <TableCell sx={{ width: '24%' }}>Склад WMS</TableCell>
              <TableCell align="right" sx={{ width: '8%' }}>Остаток WMS</TableCell>
              <TableCell sx={{ width: '25%' }}>Публикация</TableCell>
              <TableCell sx={{ width: '7%' }}>Последняя синхронизация</TableCell>
              <TableCell align="right" sx={{ width: '18%' }}>Действия</TableCell>
            </TableRow>
          </TableHead>
          <TableBody>
            {visibleRows.length === 0 ? (
              <TableRow>
                <TableCell colSpan={6}>
                  <EmptyState
                    title={error ? 'Список складов не загрузился' : 'На выбранном складе нет привязок'}
                    hint={error ? 'Причина указана выше.' : 'Выберите другой склад или добавьте привязку склада WB.'}
                    testId="fbs-stock-bindings-empty"
                  />
                </TableCell>
              </TableRow>
            ) : (
              visibleRows.map((row) => {
                const rowState = rowStateInfo(row)
                return (
                <TableRow key={row.wbId} data-testid="fbs-stock-binding-row">
                  <TableCell sx={{ overflow: 'hidden' }}>
                    <Tooltip title={row.name}>
                      <Typography variant="body2" noWrap sx={{ fontWeight: 650 }}>
                        {row.name}
                      </Typography>
                    </Tooltip>
                    {row.city !== 'город не определён' ? (
                      <Typography variant="caption" color="text.secondary" noWrap sx={{ display: 'block' }}>
                        {row.city}
                      </Typography>
                    ) : null}
                    {/* WB ID не нужен оператору визуально (он отличает склады по названию и
                        городу), но остаётся в разметке — на него опирается фиксация склада
                        в существующих сценариях. */}
                    <Typography
                      component="span"
                      sx={{
                        position: 'absolute',
                        width: '1px',
                        height: '1px',
                        overflow: 'hidden',
                        clip: 'rect(0 0 0 0)',
                        whiteSpace: 'nowrap',
                      }}
                    >
                      WB ID {row.wbId}
                    </Typography>
                  </TableCell>
                  <TableCell>
                    <FormControl size="small" fullWidth>
                      <InputLabel id={`fbs-stock-wms-label-${row.wbId}`}>Склад WMS</InputLabel>
                      <Select
                        labelId={`fbs-stock-wms-label-${row.wbId}`}
                        label="Склад WMS"
                        value={row.selectedWmsId}
                        onChange={(e) => void handleBind(row, e.target.value)}
                        disabled={savingWbId === row.wbId || physicalWarehouses.length === 0}
                        data-testid="fbs-stock-row-wms-select"
                        renderValue={(value) => {
                          const selectedWarehouse = wmsById.get(value as string)
                          const label = selectedWarehouse
                            ? `${selectedWarehouse.name} (${selectedWarehouse.code})`
                            : 'склад не сопоставлен'
                          return (
                            <Tooltip title={label}>
                              <Box component="span" sx={{ display: 'block', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                                {label}
                              </Box>
                            </Tooltip>
                          )
                        }}
                        sx={{
                          '& .MuiSelect-select': {
                            overflow: 'hidden',
                            textOverflow: 'ellipsis',
                            whiteSpace: 'nowrap',
                          },
                        }}
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
                  <TableCell align="right" data-testid="fbs-stock-total">
                    {formatFbsStockTotal(row.fbsStockTotal)}
                  </TableCell>
                  <TableCell sx={{ overflow: 'hidden' }}>
                    <Stack spacing={0.5}>
                      <Stack direction="row" spacing={1} sx={{ alignItems: 'center', minWidth: 0 }}>
                        <Switch
                          size="small"
                          checked={row.stockSyncEnabled}
                          onChange={() => void handleToggleSync(row)}
                          disabled={!row.isMapped || savingWbId === row.wbId}
                          data-testid="fbs-stock-sync-toggle"
                        />
                        <Tooltip title={rowState.detail ?? ''} disableHoverListener={!rowState.detail}>
                          <Typography
                            variant="body2"
                            noWrap
                            sx={{ fontWeight: 600, minWidth: 0 }}
                            color={
                              rowState.color === 'error'
                                ? 'error.main'
                                : rowState.color === 'success'
                                  ? 'success.main'
                                  : rowState.color === 'warning'
                                    ? 'warning.main'
                                    : 'text.secondary'
                            }
                            data-testid="fbs-stock-binding-state"
                          >
                            {rowState.label}
                          </Typography>
                        </Tooltip>
                      </Stack>
                      {row.allocatedPoolTotal > 0 ? (
                        <Typography variant="caption" color="text.secondary" noWrap sx={{ display: 'block' }}>
                          Выделено: {row.allocatedPoolTotal} шт
                        </Typography>
                      ) : null}
                    </Stack>
                  </TableCell>
                  <TableCell>{formatDt(row.lastSyncAt)}</TableCell>
                  <TableCell align="right">
                    <Stack direction="row" spacing={0.5} sx={{ justifyContent: 'flex-end', alignItems: 'center' }}>
                      <Button
                        size="small"
                        variant="outlined"
                        onClick={() => void openPool(row)}
                        disabled={!row.binding}
                        data-testid="fbs-stock-pool-btn"
                        sx={{ minWidth: 0, px: 1 }}
                      >
                        Остатки
                      </Button>
                      <IconButton
                        size="small"
                        aria-label="Ещё действия по складу"
                        onClick={(e: MouseEvent<HTMLElement>) =>
                          setRowMenuAnchor({ wbId: row.wbId, el: e.currentTarget })
                        }
                        data-testid="fbs-stock-row-menu-btn"
                      >
                        <MoreVertIcon fontSize="small" />
                      </IconButton>
                      <Menu
                        anchorEl={rowMenuAnchor?.wbId === row.wbId ? rowMenuAnchor.el : null}
                        open={rowMenuAnchor?.wbId === row.wbId}
                        onClose={() => setRowMenuAnchor(null)}
                      >
                        <MenuItem
                          onClick={() => {
                            setRowMenuAnchor(null)
                            void handleSync(row)
                          }}
                          disabled={busy || !row.isMapped || !row.stockSyncEnabled}
                          data-testid="fbs-stock-sync-one"
                        >
                          Выгрузить остатки сейчас
                        </MenuItem>
                        <MenuItem
                          onClick={() => {
                            setRowMenuAnchor(null)
                            void openStatus(row)
                          }}
                          disabled={!row.binding}
                          data-testid="fbs-stock-status-btn"
                        >
                          Статус синхронизации
                        </MenuItem>
                        <MenuItem
                          onClick={() => {
                            setRowMenuAnchor(null)
                            setPendingDisable(row)
                          }}
                          disabled={!row.binding?.is_active || savingWbId === row.wbId}
                          data-testid="fbs-stock-disable-binding"
                          sx={{ color: 'error.main' }}
                        >
                          Отключить сопоставление
                        </MenuItem>
                      </Menu>
                    </Stack>
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

      <FbsStockAllocationDialog
        open={poolOpen}
        loading={poolLoading}
        saving={poolSavingAll}
        error={poolError}
        onErrorClose={() => setPoolError(null)}
        warehouseName={poolRow?.name ?? ''}
        wbId={poolRow?.wbId ?? null}
        items={poolItems}
        drafts={poolDrafts}
        onDraftChange={handlePoolDraftChange}
        onSave={() => void handleSaveAllPoolChanges()}
        onClose={() => setPoolOpen(false)}
      />
    </Box>
  )
}
