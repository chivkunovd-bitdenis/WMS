import { useCallback, useEffect, useMemo, useState } from 'react'
import {
  Alert,
  Box,
  Button,
  Checkbox,
  Chip,
  CircularProgress,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  Divider,
  IconButton,
  LinearProgress,
  Paper,
  Stack,
  Tab,
  Tabs,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableRow,
  TextField,
  Typography,
} from '@mui/material'
import CloseIcon from '@mui/icons-material/Close'
import DeleteOutlinedIcon from '@mui/icons-material/DeleteOutlined'
import LocalShippingOutlinedIcon from '@mui/icons-material/LocalShippingOutlined'
import PrintOutlinedIcon from '@mui/icons-material/PrintOutlined'
import RefreshOutlinedIcon from '@mui/icons-material/RefreshOutlined'
import { apiUrl } from '../../api'
import { FbsMarkingStatusChip, FbsStickerStatusChip } from '../../components/fbs/FbsChips'
import { ProductPhotoThumb } from '../../components/ProductPhotoThumb'
import { FfPackagingTaskPanel, type PackagingTask } from '../ff/FfPackagingPage'
import { readApiErrorMessage } from '../../utils/readApiErrorMessage'
import { FbsPrintPreviewDialog } from './FbsPrintPreviewDialog'
import { buildFbsPickingListPrintHtml, metadataKindLabel, normalizeMetadataKind, ordersWord } from './fbsUx'
import {
  confirmFbsPrintApplied,
  confirmFbsManualPick,
  assignFbsPackingBoxOrders,
  createFbsPackingBoxes,
  createFbsIdempotencyKey,
  deleteFbsPackingBox,
  deliverFbsSupply,
  FbsApiError,
  fetchFbsPrintBatch,
  fetchFbsWorkspace,
  preflightFbsDelivery,
  removeFbsPackingBoxOrder,
  retryFbsPackingBoxQr,
  retryFbsSupplyQr,
  scanFbsOrderMetadata,
  scanFbsPickLocation,
  scanFbsPickProduct,
  selectFbsManualPickLocation,
  startFbsSupplyWork,
  undoFbsPick,
  type FbsDeliveryPreflight,
  type FbsPickLocation,
  type FbsPrintBatch,
  type FbsWorkspace,
} from './fbsApi'
import { printBarcodeLabel } from '../../utils/printBarcodeLabel'
import { renderBarcodeDataUrl } from '../../utils/renderBarcodeDataUrl'

type Props = {
  token: string
  authHeaders: (token: string) => Record<string, string>
  supplyId: string | null
  initialWorkspace?: FbsWorkspace | null
  open: boolean
  onClose: () => void
}

const STAGES = [
  { key: 'composition', label: 'Состав' },
  { key: 'picking', label: 'Подбор' },
  { key: 'packing', label: 'Упаковка и маркировка' },
  { key: 'boxes', label: 'Упаковка в короба' },
  { key: 'delivery', label: 'QR поставки' },
] as const

type StageKey = (typeof STAGES)[number]['key']

function operationKeyStorageName(supplyId: string, action: 'box-create' | 'box-delete' | 'delivery', fingerprint = '') {
  return `wms:fbs:${supplyId}:${action}:${fingerprint}`
}

function persistentOperationKey(supplyId: string, action: 'box-create' | 'box-delete' | 'delivery', fingerprint = '') {
  const storageName = operationKeyStorageName(supplyId, action, fingerprint)
  try {
    const existing = window.sessionStorage.getItem(storageName)
    if (existing) return existing
    const created = createFbsIdempotencyKey()
    window.sessionStorage.setItem(storageName, created)
    return created
  } catch {
    return createFbsIdempotencyKey()
  }
}

function clearPersistentOperationKey(supplyId: string, action: 'box-create' | 'box-delete' | 'delivery', fingerprint = '') {
  try {
    window.sessionStorage.removeItem(operationKeyStorageName(supplyId, action, fingerprint))
  } catch {
    // Storage may be unavailable in a hardened browser; server-side protection still applies.
  }
}

function visualStage(stage: FbsWorkspace['stage']): StageKey {
  if (stage === 'order_stickers') return 'packing'
  if (stage === 'handoff_prep') return 'boxes'
  return stage === 'tracking' ? 'delivery' : stage
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <Box>
      <Typography variant="caption" color="text.secondary">
        {label}
      </Typography>
      <Typography variant="body2" sx={{ fontWeight: 750 }}>
        {value}
      </Typography>
    </Box>
  )
}

export function FfFbsSupplyWorkspace({
  token,
  authHeaders,
  supplyId,
  initialWorkspace,
  open,
  onClose,
}: Props) {
  const [workspace, setWorkspace] = useState<FbsWorkspace | null>(initialWorkspace ?? null)
  const [stage, setStage] = useState<StageKey>('composition')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [notice, setNotice] = useState<string | null>(null)
  const [locationBarcode, setLocationBarcode] = useState('')
  const [productBarcode, setProductBarcode] = useState('')
  const [pickLocation, setPickLocation] = useState<FbsPickLocation | null>(null)
  const [metadataOrderId, setMetadataOrderId] = useState('')
  const [metadataKind, setMetadataKind] = useState('sgtin')
  const [metadataValue, setMetadataValue] = useState('')
  const [metadataDialogOpen, setMetadataDialogOpen] = useState(false)
  const [printBatch, setPrintBatch] = useState<FbsPrintBatch | null>(null)
  const [printPreviewOpen, setPrintPreviewOpen] = useState(false)
  const [packagingTask, setPackagingTask] = useState<PackagingTask | null>(null)
  const [boxCount, setBoxCount] = useState('1')
  const [boxDeleteTarget, setBoxDeleteTarget] = useState<string | null>(null)
  const [boxAssignTarget, setBoxAssignTarget] = useState<string | null>(null)
  const [selectedBoxOrderIds, setSelectedBoxOrderIds] = useState<string[]>([])
  const [deliveryPreflight, setDeliveryPreflight] = useState<FbsDeliveryPreflight | null>(null)
  const [deliveryKey, setDeliveryKey] = useState(createFbsIdempotencyKey)
  const [deliveryConfirmOpen, setDeliveryConfirmOpen] = useState(false)
  const [deliverySubmitted, setDeliverySubmitted] = useState(false)
  const [undoOrderId, setUndoOrderId] = useState<string | null>(null)
  const [retryAction, setRetryAction] = useState<(() => void) | null>(null)

  const load = useCallback(
    async (silent = false) => {
      if (!supplyId) return
      if (!silent) setBusy(true)
      try {
        const next = await fetchFbsWorkspace(token, authHeaders, supplyId)
        setWorkspace(next)
        if (!silent) setStage(visualStage(next.stage))
      } catch (cause) {
        if (!silent) setError(cause instanceof Error ? cause.message : 'Не удалось загрузить поставку.')
      } finally {
        if (!silent) setBusy(false)
      }
    },
    [supplyId, token, authHeaders],
  )

  useEffect(() => {
    if (!open || !supplyId) return
    setError(null)
    setNotice(null)
    setWorkspace(initialWorkspace ?? null)
    setStage(initialWorkspace ? visualStage(initialWorkspace.stage) : 'composition')
    setDeliveryKey(persistentOperationKey(supplyId, 'delivery'))
    setDeliveryPreflight(null)
    setPrintBatch(null)
    setPickLocation(null)
    setMetadataOrderId('')
    setMetadataValue('')
    setMetadataDialogOpen(false)
    setBoxCount('1')
    setBoxDeleteTarget(null)
    setBoxAssignTarget(null)
    setSelectedBoxOrderIds([])
    setDeliveryConfirmOpen(false)
    setDeliverySubmitted(false)
    setUndoOrderId(null)
    if (!initialWorkspace) void load()
  }, [open, supplyId, initialWorkspace, load])

  useEffect(() => {
    const requiredOrder = workspace?.orders.find((order) => order.metadata.required.length > 0)
    if (!requiredOrder || metadataOrderId) return
    setMetadataOrderId(requiredOrder.id)
    setMetadataKind(normalizeMetadataKind(requiredOrder.metadata.required[0]))
  }, [workspace, metadataOrderId])

  useEffect(() => {
    setNotice(null)
  }, [workspace?.stage])

  useEffect(() => {
    if (!open || !supplyId || !['picking', 'delivery'].includes(stage)) return
    const timer = window.setInterval(() => {
      if (document.visibilityState === 'visible') void load(true)
    }, 15_000)
    return () => window.clearInterval(timer)
  }, [open, supplyId, stage, load])

  useEffect(() => {
    const taskId = workspace?.supply.packaging_task_id
    if (!open || stage !== 'packing' || !taskId) {
      setPackagingTask(null)
      return
    }
    let active = true
    void fetch(apiUrl(`/operations/packaging-tasks/${taskId}`), {
      headers: { ...authHeaders(token) },
    }).then(async (response) => {
      if (!active) return
      if (!response.ok) {
        setError(await readApiErrorMessage(response))
        return
      }
      setPackagingTask((await response.json()) as PackagingTask)
    })
    return () => {
      active = false
    }
  }, [open, stage, workspace?.supply.packaging_task_id, token, authHeaders])

  const run = async (operation: () => Promise<FbsWorkspace>, success: string) => {
    setBusy(true)
    setError(null)
    setNotice(null)
    setRetryAction(null)
    try {
      const next = await operation()
      setWorkspace(next)
      setStage(visualStage(next.stage))
      if (success) setNotice(success)
      return next
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'Операция не выполнена.')
      if (cause instanceof FbsApiError && cause.retryable) {
        setRetryAction(() => () => { void run(operation, success) })
      }
      return null
    } finally {
      setBusy(false)
    }
  }

  const scanLocation = async () => {
    if (!workspace || !locationBarcode.trim()) return
    setBusy(true)
    setError(null)
    try {
      const result = await scanFbsPickLocation(
        token,
        authHeaders,
        workspace.supply.id,
        locationBarcode.trim(),
      )
      setPickLocation(result)
      setProductBarcode('')
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'Ячейка не подтверждена.')
    } finally {
      setBusy(false)
    }
  }

  const scanProduct = async () => {
    if (!workspace || !pickLocation || !productBarcode.trim()) return
    const key = createFbsIdempotencyKey()
    const next = await run(
      () =>
        scanFbsPickProduct(token, authHeaders, workspace.supply.id, {
          location_id: pickLocation.id,
          product_barcode: productBarcode.trim(),
          idempotency_key: key,
        }),
      'Товар подобран. Прогресс синхронизирован для всех операторов.',
    )
    if (next) setProductBarcode('')
  }

  const pickFromCell = async (locationId: string, productId: string, orderIds: string[]) => {
    if (!workspace || orderIds.length === 0) return
    setBusy(true)
    setError(null)
    setNotice(null)
    try {
      await selectFbsManualPickLocation(token, authHeaders, workspace.supply.id, locationId)
      let next = workspace
      for (const orderId of orderIds) {
        next = await confirmFbsManualPick(token, authHeaders, workspace.supply.id, {
          location_id: locationId,
          product_id: productId,
          order_id: orderId,
          idempotency_key: createFbsIdempotencyKey(),
        })
      }
      setWorkspace(next)
      setStage(visualStage(next.stage))
      setNotice(`Снято из ячейки: ${orderIds.length} шт.`)
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'Не удалось подтвердить подбор из ячейки.')
    } finally {
      setBusy(false)
    }
  }

  const scanMetadata = async () => {
    if (!workspace || !metadataOrderId || metadataValue.length === 0) return
    setBusy(true)
    setError(null)
    try {
      await scanFbsOrderMetadata(token, authHeaders, metadataOrderId, {
        kind: metadataKind,
        raw_value: metadataValue,
        idempotency_key: createFbsIdempotencyKey(),
      })
      setMetadataValue('')
      await load(true)
      setMetadataDialogOpen(false)
      setNotice('Идентификатор передан на серверную проверку WB.')
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'Идентификатор не сохранён.')
    } finally {
      setBusy(false)
    }
  }

  const requestPrintBatch = async (orderIds?: string[], retryMissing = false) => {
    if (!workspace) return
    setBusy(true)
    setError(null)
    try {
      const batch = await fetchFbsPrintBatch(token, authHeaders, workspace.supply.id, {
        kind: 'order_sticker',
        order_ids: orderIds ?? workspace.orders.map((order) => order.id),
        retry_missing: retryMissing,
      })
      setPrintBatch(batch)
      if (batch.ready === 0) {
        setError('WB не вернул ни одного готового стикера. Печать не открыта.')
      } else {
        setPrintPreviewOpen(true)
      }
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'Стикеры не получены.')
    } finally {
      setBusy(false)
    }
  }

  const confirmPrintApplied = async (assetId: string) => {
    await confirmFbsPrintApplied(token, authHeaders, assetId, createFbsIdempotencyKey())
    setPrintBatch((current) => current ? {
      ...current,
      assets: current.assets.map((asset) => asset.id === assetId
        ? { ...asset, applied_at: new Date().toISOString() }
        : asset),
    } : current)
    await load(true)
  }

  const openAssetPreview = (assets: Array<NonNullable<FbsWorkspace['supply']['barcode_asset']>>) => {
    const readyAssets = assets.filter((asset) => asset.status === 'ready' && asset.preview_url)
    const failedAssets = assets.filter((asset) => asset.status === 'error')
    setPrintBatch({
      requested: assets.length,
      ready: readyAssets.length,
      missing: assets.length - readyAssets.length - failedAssets.length,
      failed: failedAssets.length,
      assets,
      order_errors: [],
    })
    if (readyAssets.length === 0) {
      setError('Нет готового QR для предпросмотра — окно печати не открыто.')
      return
    }
    setPrintPreviewOpen(true)
  }

  const createBoxes = async () => {
    if (!workspace) return
    const count = Math.min(100, Math.max(1, Number(boxCount) || 1))
    const key = persistentOperationKey(workspace.supply.id, 'box-create', String(count))
    const next = await run(
      () => createFbsPackingBoxes(token, authHeaders, workspace.supply.id, { count, idempotency_key: key }),
      `${count === 1 ? 'Короб создан.' : `Создано коробов: ${count}.`}`,
    )
    if (next) clearPersistentOperationKey(workspace.supply.id, 'box-create', String(count))
  }

  const assignBoxOrders = async () => {
    if (!workspace || !boxAssignTarget || selectedBoxOrderIds.length === 0) return
    const next = await run(
      () => assignFbsPackingBoxOrders(token, authHeaders, workspace.supply.id, boxAssignTarget, selectedBoxOrderIds),
      'Товары распределены по коробу.',
    )
    if (next) {
      setBoxAssignTarget(null)
      setSelectedBoxOrderIds([])
    }
  }

  const removeBoxOrder = async (boxId: string, orderId: string) => {
    if (!workspace) return
    await run(
      () => removeFbsPackingBoxOrder(token, authHeaders, workspace.supply.id, boxId, orderId),
      'Товар возвращён в список для распределения.',
    )
  }

  const deleteBox = async () => {
    if (!workspace || !boxDeleteTarget) return
    const key = persistentOperationKey(workspace.supply.id, 'box-delete', boxDeleteTarget)
    const next = await run(
      () => deleteFbsPackingBox(token, authHeaders, workspace.supply.id, boxDeleteTarget, key),
      'Пустой короб удалён.',
    )
    if (next) {
      clearPersistentOperationKey(workspace.supply.id, 'box-delete', boxDeleteTarget)
      setBoxDeleteTarget(null)
    }
  }

  const retryBoxQr = async (boxId: string) => {
    if (!workspace) return
    await run(
      () => retryFbsPackingBoxQr(token, authHeaders, workspace.supply.id, boxId),
      'QR короба обновлён.',
    )
  }

  const checkDelivery = async () => {
    if (!workspace) return
    setBusy(true)
    setError(null)
    try {
      setDeliveryPreflight(
        await preflightFbsDelivery(token, authHeaders, workspace.supply.id),
      )
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'Проверка передачи не выполнена.')
    } finally {
      setBusy(false)
    }
  }

  const deliver = async () => {
    if (!workspace || !deliveryPreflight?.can_deliver) return
    const next = await run(
      () =>
        deliverFbsSupply(token, authHeaders, workspace.supply.id, {
          idempotency_key: deliveryKey,
          confirmed_preflight_version: deliveryPreflight.version,
        }),
      '',
    )
    if (next) {
      clearPersistentOperationKey(workspace.supply.id, 'delivery')
      setDeliveryKey(createFbsIdempotencyKey())
      setDeliveryPreflight(null)
      setDeliverySubmitted(true)
    }
  }

  const total = workspace?.progress.total ?? 0
  const ready = workspace
    ? Math.min(
        total,
        workspace.progress.picked,
        workspace.progress.packed,
        workspace.progress.metadata_ready,
        workspace.progress.stickers_ready,
      )
    : 0
  const percent = total ? Math.round((ready / total) * 100) : 0
  const pickingRows = useMemo(() => {
    if (!workspace) return []
    const grouped = new Map<string, {
      key: string
      name: string
      imageUrl: string | null
      identifiers: string[]
      locations: string[]
      required: number
      picked: number
      wbOrders: number[]
      marking: string
      nearestDeadline: string
    }>()
    for (const order of workspace.orders) {
      const key = order.product.id ?? `unmapped-${order.id}`
      const current = grouped.get(key) ?? {
        key,
        name: order.product.name,
        imageUrl: order.product.image_url,
        identifiers: [order.product.seller_article, order.product.wb_article ? `WB ${order.product.wb_article}` : null, order.product.barcode].filter((value): value is string => Boolean(value)),
        locations: [],
        required: 0,
        picked: 0,
        wbOrders: [],
        marking: order.metadata.required.length ? order.metadata.required.join(', ') : 'Не требуется',
        nearestDeadline: order.deadline_at,
      }
      current.required += 1
      if (order.pick.status === 'picked') current.picked += 1
      current.wbOrders.push(order.wb_order_id)
      const locations = order.inventory.locations.map((location) => `${location.code}: ${location.available_unpacked}`)
      current.locations = [...new Set([...current.locations, ...locations])]
      if (new Date(order.deadline_at).getTime() < new Date(current.nearestDeadline).getTime()) current.nearestDeadline = order.deadline_at
      grouped.set(key, current)
    }
    return [...grouped.values()]
  }, [workspace])
  const manualPickRows = useMemo(() => {
    if (!workspace) return []
    const byProduct = new Map<string, typeof workspace.orders>()
    for (const order of workspace.orders) {
      if (!order.product.id || order.pick.status === 'picked' || order.pack.status === 'packed') continue
      const current = byProduct.get(order.product.id) ?? []
      current.push(order)
      byProduct.set(order.product.id, current)
    }
    return [...byProduct.entries()].flatMap(([productId, orders]) => {
      const locations = new Map<string, { id: string; code: string; available: number }>()
      for (const order of orders) for (const location of order.inventory.locations) {
        const current = locations.get(location.id)
        if (!current || location.available_unpacked > current.available) {
          locations.set(location.id, { id: location.id, code: location.code, available: location.available_unpacked })
        }
      }
      let index = 0
      return [...locations.values()].sort((a, b) => a.code.localeCompare(b.code)).flatMap((location) => {
        const count = Math.min(location.available, orders.length - index)
        if (count <= 0) return []
        const orderIds = orders.slice(index, index + count).map((order) => order.id)
        index += count
        return [{ productId, location, orderIds, product: orders[0].product }]
      })
    })
  }, [workspace])
  const printPickingList = () => {
    if (!workspace) return
    const printWindow = window.open('', '_blank')
    if (!printWindow) {
      setError('Браузер заблокировал окно печати. Разрешите всплывающие окна и повторите.')
      return
    }
    printWindow.opener = null
    printWindow.document.open()
    printWindow.document.write(buildFbsPickingListPrintHtml({
      supplyName: workspace.supply.name,
      wbSupplyId: workspace.supply.wb_supply_id,
      sellerName: workspace.supply.seller.name,
      wmsWarehouseName: workspace.supply.wms_warehouse.name,
      routeLabel: workspace.supply.delivery_type === 'pvz' ? 'ПВЗ' : 'Склад / СЦ',
      deadlineLabel: new Date(workspace.supply.nearest_deadline_at).toLocaleString('ru-RU'),
      printedAtLabel: new Date().toLocaleString('ru-RU'),
      rows: pickingRows,
    }))
    printWindow.document.close()
  }
  const stageBlockers = useMemo(() => {
    if (stage === 'packing') {
      return workspace?.blockers.filter((blocker) => blocker.stage === 'packing' || blocker.stage === 'order_stickers') ?? []
    }
    const backendStage = stage === 'boxes' ? 'handoff_prep' : stage
    return workspace?.blockers.filter((blocker) => blocker.stage === backendStage) ?? []
  }, [workspace, stage])
  const currentStage = workspace ? visualStage(workspace.stage) : 'composition'
  const currentStageIndex = STAGES.findIndex((item) => item.key === currentStage)
  const stageIsCurrent = stage === currentStage
  const allPicked = Boolean(workspace && workspace.progress.total > 0 && workspace.progress.picked === workspace.progress.total)
  const deliveryConfirmed = deliverySubmitted
    || workspace?.stage === 'tracking'
    || ['in_delivery', 'done'].includes(workspace?.supply.status ?? '')
  const packagingEditable = !deliveryConfirmed
  const metadataOrder = workspace?.orders.find((order) => order.id === metadataOrderId)
  const assignedBoxOrderIds = new Set(workspace?.boxes.flatMap((box) => box.assigned_order_ids) ?? [])
  const availableForBox = (workspace?.orders ?? []).filter(
    (order) => order.pack.status === 'packed' && !assignedBoxOrderIds.has(order.id),
  )
  const boxAssignName = workspace?.boxes.find((box) => box.id === boxAssignTarget)?.box_number

  return (
    <Dialog
      open={open}
      onClose={busy ? undefined : onClose}
      maxWidth={false}
      fullScreen={false}
      slotProps={{ paper: { sx: { width: 'min(1500px, 98vw)', height: '94vh', m: 1 } } }}
      data-testid="fbs-workspace"
    >
      <Box sx={{ px: 2.5, py: 2, borderBottom: 1, borderColor: 'divider', bgcolor: '#fff' }}>
        <Stack direction="row" spacing={2} sx={{ alignItems: 'flex-start' }}>
          <LocalShippingOutlinedIcon color="primary" sx={{ mt: 0.4 }} />
          <Box sx={{ flex: 1, minWidth: 0 }}>
            <Stack direction={{ xs: 'column', lg: 'row' }} sx={{ justifyContent: 'space-between', gap: 1 }}>
              <Box>
                <Typography variant="h6">
                  {workspace?.supply.name ?? 'Рабочее пространство FBS'}
                </Typography>
                <Typography variant="body2" color="text.secondary">
                  {workspace
                    ? `${workspace.supply.seller.name}${workspace.supply.wb_supply_id ? ` · № WB ${workspace.supply.wb_supply_id}` : ''}`
                    : 'Загружаем данные поставки…'}
                </Typography>
              </Box>
              {workspace ? (
                <Stack direction="row" spacing={3} sx={{ flexWrap: 'wrap' }} useFlexGap>
                  <Metric label="Склад WMS" value={workspace.supply.wms_warehouse.name} />
                  <Metric label="Маршрут" value={workspace.supply.delivery_type === 'pvz' ? 'ПВЗ' : 'Склад / СЦ'} />
                </Stack>
              ) : null}
            </Stack>
            <Stack direction="row" spacing={1.5} sx={{ alignItems: 'center', mt: 1.25 }}>
              <LinearProgress variant="determinate" value={percent} sx={{ flex: 1, maxWidth: 480, height: 8, borderRadius: 4 }} />
              <Typography variant="caption" sx={{ fontWeight: 750 }}>{ready} из {total} подготовлено к отгрузке</Typography>
              {workspace ? (
                <Typography variant="caption" color="text.secondary">
                  Сдать в Wildberries до {new Date(workspace.supply.nearest_deadline_at).toLocaleString('ru-RU')}
                </Typography>
              ) : null}
            </Stack>
          </Box>
          <IconButton onClick={onClose} disabled={busy} aria-label="Закрыть">
            <CloseIcon />
          </IconButton>
        </Stack>
      </Box>

      <Tabs
        value={stage}
        onChange={(_, value) => {
          if (STAGES.findIndex((item) => item.key === value) <= currentStageIndex) setStage(value)
          setError(null)
          setNotice(null)
        }}
        variant="scrollable"
        scrollButtons="auto"
        sx={{ px: 2, borderBottom: 1, borderColor: 'divider', bgcolor: 'rgba(91,33,182,.035)' }}
      >
        {STAGES.map((item, index) => (
          <Tab key={item.key} value={item.key} label={index < currentStageIndex ? `${item.label} ✓` : item.label} disabled={index > currentStageIndex} />
        ))}
      </Tabs>

      {busy ? <LinearProgress /> : null}
      <DialogContent sx={{ p: 0, bgcolor: '#f4f6fb' }}>
        <Box sx={{ p: { xs: 1.5, md: 2.5 }, minHeight: '100%' }}>
          {error ? <Alert severity="error" sx={{ mb: 2 }} action={retryAction ? <Button color="inherit" size="small" onClick={retryAction}>Повторить</Button> : undefined}>{error}</Alert> : null}
          {notice ? <Alert severity="success" sx={{ mb: 2 }}>{notice}</Alert> : null}
          {stageIsCurrent && stageBlockers.length ? (
            <Alert severity="warning" sx={{ mb: 2 }}>
              <Typography variant="subtitle2">Что нужно исправить</Typography>
              {stageBlockers.map((blocker) => (
                <Typography key={`${blocker.code}-${blocker.order_id ?? ''}`} variant="body2">
                  {blocker.message}
                </Typography>
              ))}
            </Alert>
          ) : null}

          {!workspace ? (
            <Stack spacing={2} sx={{ alignItems: 'center', justifyContent: 'center', py: 10 }}>
              <CircularProgress />
              <Typography>Загружаем актуальное состояние поставки…</Typography>
            </Stack>
          ) : null}

          {workspace && stage === 'composition' ? (
            <Stack spacing={2}>
              <Paper variant="outlined" sx={{ p: 2 }}>
                <Stack direction={{ xs: 'column', sm: 'row' }} spacing={1.5} sx={{ justifyContent: 'space-between', alignItems: { sm: 'center' } }}>
                  <Box>
                    <Typography variant="h6">Состав поставки</Typography>
                    <Typography variant="body2" color="text.secondary">
                      {workspace.orders.length} {ordersWord(workspace.orders.length)} в поставке
                    </Typography>
                  </Box>
                  <Button variant="outlined" startIcon={<PrintOutlinedIcon />} onClick={printPickingList} data-testid="fbs-pick-list-print">
                    Печать листа подбора
                  </Button>
                </Stack>
                <Divider sx={{ my: 2 }} />
                <Table size="small">
                  <TableHead><TableRow><TableCell>Фото</TableCell><TableCell>Заказ WB</TableCell><TableCell>Товар и идентификаторы</TableCell><TableCell>Количество</TableCell><TableCell>Маркировка</TableCell><TableCell>Подбор</TableCell></TableRow></TableHead>
                  <TableBody>
                    {workspace.orders.map((order) => (
                      <TableRow key={order.id}>
                        <TableCell><ProductPhotoThumb src={order.product.image_url} alt={order.product.name} size={42} previewSize={280} testId={`fbs-composition-photo-${order.id}`} /></TableCell>
                        <TableCell>№{order.wb_order_id}</TableCell>
                        <TableCell><Typography variant="body2" sx={{ fontWeight: 700 }}>{order.product.name}</Typography><Typography variant="caption" color="text.secondary" sx={{ display: 'block' }}>Артикул: {order.product.seller_article ?? '—'}{order.product.barcode ? ` · ШК: ${order.product.barcode}` : ''}</Typography></TableCell>
                        <TableCell>1 шт.</TableCell>
                        <TableCell>{order.metadata.required.length ? order.metadata.required.join(', ') : 'Не требуется'}</TableCell>
                        <TableCell>{order.pick.status === 'picked' ? 'Подобран' : 'Ожидает'}</TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </Paper>
              <Stack direction="row" sx={{ justifyContent: 'flex-end' }}>
                <Button variant="contained" size="large" disabled={!stageIsCurrent} onClick={() => void run(() => startFbsSupplyWork(token, authHeaders, workspace.supply.id), 'Задание создано. Можно начинать подбор.')}>
                  Начать работу с поставкой
                </Button>
              </Stack>
            </Stack>
          ) : null}

          {workspace && stage === 'picking' ? (
            <Stack spacing={2}>
              {!stageIsCurrent ? <Alert severity="success">Подбор завершён. Этот этап доступен только для просмотра.</Alert> : null}
              <Paper variant="outlined" sx={{ p: 2 }}>
                <Stack direction={{ xs: 'column', sm: 'row' }} spacing={1.5} sx={{ justifyContent: 'space-between', alignItems: { sm: 'flex-start' }, mb: 2 }}>
                  <Box>
                    <Typography variant="h6">Сканирование подбора</Typography>
                    <Typography variant="body2" color="text.secondary">
                      Сначала подтвердите ячейку, затем сканируйте товары. Прогресс хранится на сервере.
                    </Typography>
                  </Box>
                  <Button variant="outlined" startIcon={<PrintOutlinedIcon />} onClick={printPickingList} data-testid="fbs-pick-list-print">
                    Печать листа подбора
                  </Button>
                </Stack>
                <Stack direction={{ xs: 'column', md: 'row' }} spacing={1.5}>
                  <TextField label="Штрихкод ячейки" value={locationBarcode} onChange={(e) => setLocationBarcode(e.target.value)} disabled={!stageIsCurrent || allPicked} onKeyDown={(e) => { if (e.key === 'Enter') void scanLocation() }} />
                  <Button variant="outlined" onClick={() => void scanLocation()} disabled={!stageIsCurrent || allPicked}>Подтвердить ячейку</Button>
                  <TextField label="Штрихкод товара" value={productBarcode} onChange={(e) => setProductBarcode(e.target.value)} disabled={!stageIsCurrent || !pickLocation || allPicked} onKeyDown={(e) => { if (e.key === 'Enter') void scanProduct() }} sx={{ flex: 1 }} />
                  <Button variant="contained" onClick={() => void scanProduct()} disabled={!stageIsCurrent || !pickLocation || !productBarcode.trim() || allPicked}>Подобрать товар</Button>
                </Stack>
                {pickLocation ? <Alert severity="success" sx={{ mt: 2 }}>Ячейка {pickLocation.code} подтверждена · {pickLocation.warehouse_name}</Alert> : null}
                {allPicked ? <Alert severity="success" sx={{ mt: 2 }}>Все товары подобраны. Перейдите к упаковке.</Alert> : null}
              </Paper>
              <Paper variant="outlined" sx={{ p: 2 }} data-testid="fbs-manual-picking">
                <Typography variant="h6">Подбор из ячеек</Typography>
                <Typography variant="body2" color="text.secondary" sx={{ mb: 1.5 }}>Сканер остаётся доступен выше. Здесь можно снять требуемое количество из конкретной ячейки вручную.</Typography>
                {manualPickRows.length === 0 ? <Alert severity="info">Нет товаров, ожидающих ручного подбора из ячеек.</Alert> : <Stack spacing={1}>{manualPickRows.map((row) => <Stack key={`${row.productId}-${row.location.id}`} direction={{ xs: 'column', md: 'row' }} spacing={1.5} sx={{ alignItems: { md: 'center' }, p: 1.25, bgcolor: 'action.hover', borderRadius: 1.5 }}><ProductPhotoThumb src={row.product.image_url} alt={row.product.name} size={44} /><Box sx={{ flex: 1 }}><Typography variant="body2" sx={{ fontWeight: 700 }}>{row.product.name}</Typography><Typography variant="caption" color="text.secondary">Ячейка {row.location.code} · к снятию {row.orderIds.length} шт. · доступно {row.location.available} шт.</Typography></Box><Button variant="contained" size="small" disabled={!stageIsCurrent || busy} onClick={() => void pickFromCell(row.location.id, row.productId, row.orderIds)}>Снять {row.orderIds.length} шт.</Button></Stack>)}</Stack>}
              </Paper>
              <Paper variant="outlined" sx={{ p: 2 }}>
                <Typography variant="subtitle1" gutterBottom>Товары в подборе: {workspace.progress.picked}/{workspace.progress.total}</Typography>
                <Table size="small">
                  <TableHead><TableRow><TableCell>Товар</TableCell><TableCell>Точная ячейка</TableCell><TableCell>Взять</TableCell><TableCell>Подобрано</TableCell></TableRow></TableHead>
                  <TableBody>{pickingRows.map((row) => <TableRow key={row.key}><TableCell><Stack direction="row" spacing={1.5} sx={{ alignItems: 'center' }}>{row.imageUrl ? <Box component="img" src={row.imageUrl} alt="" sx={{ width: 52, height: 52, objectFit: 'contain', borderRadius: 1 }} /> : null}<Box><Typography variant="body2" sx={{ fontWeight: 700 }}>{row.name}</Typography><details><summary style={{ cursor: 'pointer', color: '#5b21b6' }}>Подробнее</summary><Typography variant="caption" color="text.secondary" sx={{ display: 'block' }}>{row.identifiers.join(' · ') || 'Идентификаторы не указаны'} · заказы {row.wbOrders.map((id) => `№${id}`).join(', ')}</Typography>{row.marking !== 'Не требуется' ? <Typography variant="caption" color="text.secondary" sx={{ display: 'block' }}>Маркировка: {row.marking}</Typography> : null}<Typography variant="caption" color="text.secondary" sx={{ display: 'block' }}>Отгрузить до {new Date(row.nearestDeadline).toLocaleString('ru-RU')}</Typography></details></Box></Stack></TableCell><TableCell>{row.locations.length ? row.locations.join(', ') : 'Ячейка не назначена'}</TableCell><TableCell>{row.required}</TableCell><TableCell>{row.picked} из {row.required}</TableCell></TableRow>)}</TableBody>
                </Table>
                <Divider sx={{ my: 2 }} />
                {stageIsCurrent && workspace.orders.some((order) => order.pick.status === 'picked' && order.pack.status !== 'packed') ? <Button size="small" variant="text" onClick={() => setUndoOrderId(workspace.orders.find((order) => order.pick.status === 'picked' && order.pack.status !== 'packed')?.id ?? null)}>Исправить ошибку подбора</Button> : null}
              </Paper>
            </Stack>
          ) : null}

          {workspace && stage === 'packing' ? (
            <Stack spacing={2}>
              {!packagingEditable ? <Alert severity="success">Поставка уже передана в WB. Упаковка доступна только для просмотра.</Alert> : null}
              {packagingTask ? (
                <Paper variant="outlined" sx={{ p: 2 }}>
                  <Box sx={{ mb: 2 }}>
                    <Typography variant="h6">Упаковка и маркировка</Typography>
                    <Typography variant="body2" color="text.secondary">В одной строке доступны обычная печать товара, обязательная маркировка и отдельный стикер заказа WB.</Typography>
                  </Box>
                  <FfPackagingTaskPanel
                    token={token}
                    task={packagingTask}
                    unloadLabel={workspace.supply.name}
                    hideDocumentHeader
                    simplifiedQuantities
                    alwaysShowPrintAction
                    renderLineActions={(line) => {
                      const lineOrders = workspace.orders.filter((order) => order.product.id === line.product_id)
                      return (
                        <Stack spacing={0.75} sx={{ alignItems: 'flex-end' }}>
                          {lineOrders.map((order) => (
                            <Box key={order.id} data-testid={`fbs-order-marking-${order.id}`}>
                              <Stack direction="row" spacing={0.5} sx={{ justifyContent: 'flex-end', alignItems: 'center', flexWrap: 'wrap' }}>
                                <Typography variant="caption" sx={{ fontWeight: 700 }}>WB №{order.wb_order_id}</Typography>
                                <FbsMarkingStatusChip required={order.metadata.required} states={order.metadata.states} />
                                <FbsStickerStatusChip status={order.sticker.status} />
                                {order.metadata.required.length ? (
                                  <Button
                                    size="small"
                                    variant="outlined"
                                    disabled={!packagingEditable || busy}
                                    onClick={() => {
                                      setMetadataOrderId(order.id)
                                      setMetadataKind(normalizeMetadataKind(order.metadata.required[0]))
                                      setMetadataValue('')
                                      setMetadataDialogOpen(true)
                                    }}
                                    data-testid={`fbs-metadata-open-${order.id}`}
                                  >
                                    Ввести {metadataKindLabel(order.metadata.required[0])}
                                  </Button>
                                ) : null}
                                <Button
                                  size="small"
                                  variant="contained"
                                  startIcon={<PrintOutlinedIcon />}
                                  disabled={!packagingEditable || busy}
                                  onClick={() => void requestPrintBatch([order.id])}
                                  data-testid={`fbs-order-sticker-print-${order.id}`}
                                >
                                  Стикер WB
                                </Button>
                              </Stack>
                            </Box>
                          ))}
                        </Stack>
                      )
                    }}
                    onUpdated={(nextTask) => {
                      setPackagingTask(nextTask)
                      if (nextTask.status === 'done') {
                        void load()
                      }
                    }}
                  />
                </Paper>
              ) : (
                <Alert severity="info">{workspace.supply.packaging_task_id ? 'Загружаем существующее задание упаковки…' : 'Сначала начните работу с поставкой — сервер создаст единственное задание упаковки.'}</Alert>
              )}
              {printBatch ? <Paper variant="outlined" sx={{ p: 2 }}><Typography variant="body2">Готово: {printBatch.ready}{printBatch.missing ? ` · Не получено: ${printBatch.missing}` : ''}{printBatch.failed ? ` · Ошибок: ${printBatch.failed}` : ''}</Typography><Button variant="outlined" disabled={printBatch.ready === 0} sx={{ mt: 1 }} onClick={() => setPrintPreviewOpen(true)}>Открыть предпросмотр и печать</Button>{printBatch.missing ? <Button variant="text" disabled={!packagingEditable || busy} sx={{ mt: 1, ml: 1 }} onClick={() => void requestPrintBatch(undefined, true)}>Получить недостающие</Button> : null}{printBatch.order_errors.map((item) => <Alert key={item.order_id} severity="error" sx={{ mt: 1 }}>Заказ WB №{item.wb_order_id}: {item.message}</Alert>)}</Paper> : null}
            </Stack>
          ) : null}

          {workspace && stage === 'boxes' ? (
            <Stack spacing={2}>
              <Paper variant="outlined" sx={{ overflow: 'hidden' }} data-testid="fbs-boxes">
                <Box sx={{ px: 2.5, py: 2, borderBottom: 1, borderColor: 'divider' }}>
                  <Stack direction={{ xs: 'column', sm: 'row' }} spacing={1.5} sx={{ justifyContent: 'space-between', alignItems: { sm: 'center' } }}>
                    <Box><Typography variant="h6">Упаковка в короба</Typography><Typography variant="body2" color="text.secondary">Создайте короб и добавьте в него только уже упакованные товары.</Typography></Box>
                    <Stack direction="row" spacing={1}><TextField label="Коробов" value={boxCount} size="small" type="number" disabled={!stageIsCurrent} onChange={(e) => setBoxCount(e.target.value)} slotProps={{ htmlInput: { min: 1, max: 100 } }} sx={{ width: 104 }} /><Button variant="contained" disabled={!stageIsCurrent || !Number(boxCount)} onClick={() => void createBoxes()}>Добавить короб</Button></Stack>
                  </Stack>
                </Box>
                {workspace.boxes.length === 0 ? <Typography color="text.secondary" sx={{ p: 3 }}>Коробов пока нет.</Typography> : <Stack divider={<Divider flexItem />}>
                  {workspace.boxes.map((box) => {
                    const assigned = workspace.orders.filter((order) => box.assigned_order_ids.includes(order.id))
                    return <Box key={box.id} sx={{ p: 2.5 }}><Stack direction={{ xs: 'column', md: 'row' }} spacing={1.5} sx={{ justifyContent: 'space-between', alignItems: { md: 'center' } }}><Box><Typography sx={{ fontWeight: 750 }}>Короб {box.box_number}</Typography><Typography variant="caption" color="text.secondary">ШК: {box.barcode} · {assigned.length} {ordersWord(assigned.length)}</Typography></Box><Stack direction="row" spacing={1} useFlexGap sx={{ flexWrap: 'wrap' }}><Button size="small" onClick={() => printBarcodeLabel({ title: `Короб FBS ${box.box_number}`, barcode: box.barcode, barcodeDataUrl: renderBarcodeDataUrl(box.barcode) })}>Печать ШК</Button><Button size="small" variant="contained" disabled={!stageIsCurrent} onClick={() => { setBoxAssignTarget(box.id); setSelectedBoxOrderIds([]) }}>Добавить товар</Button>{workspace.supply.delivery_type === 'pvz' ? (box.qr_asset?.preview_url ? <Button size="small" onClick={() => openAssetPreview([box.qr_asset!])}>Печать QR</Button> : <Button size="small" disabled={!stageIsCurrent} onClick={() => void retryBoxQr(box.id)}>Получить QR</Button>) : null}<IconButton size="small" color="error" disabled={busy || assigned.length > 0} onClick={() => setBoxDeleteTarget(box.id)} aria-label={`Удалить короб ${box.box_number}`}><DeleteOutlinedIcon fontSize="small" /></IconButton></Stack></Stack>
                    {assigned.length ? <Stack spacing={1} sx={{ mt: 1.5, pl: { md: 2 } }}>{assigned.map((order) => <Stack key={order.id} direction="row" spacing={1.25} sx={{ alignItems: 'center', p: 1, bgcolor: 'action.hover', borderRadius: 1.5 }}><ProductPhotoThumb src={order.product.image_url} alt={order.product.name} size={36} /><Box sx={{ flex: 1, minWidth: 0 }}><Typography variant="body2" sx={{ fontWeight: 700 }}>{order.product.name}</Typography><Typography variant="caption" color="text.secondary">Заказ WB №{order.wb_order_id} · 1 шт.</Typography></Box><Button size="small" disabled={!stageIsCurrent} onClick={() => void removeBoxOrder(box.id, order.id)}>Убрать</Button></Stack>)}</Stack> : <Typography variant="body2" color="text.secondary" sx={{ mt: 1.5 }}>Добавьте товары в этот короб.</Typography>}</Box>
                  })}
                </Stack>}
              </Paper>
            </Stack>
          ) : null}

          {workspace && stage === 'delivery' ? (
            <Stack spacing={2}>
              {!deliveryConfirmed ? (
                <Paper variant="outlined" sx={{ p: 2 }}><Stack direction="row" sx={{ justifyContent: 'space-between', alignItems: 'center' }}><Box><Typography variant="h6">Передача в доставку</Typography><Typography variant="body2" color="text.secondary">Перед каждой передачей выполняется свежая серверная проверка WB.</Typography></Box><Button variant="outlined" startIcon={<RefreshOutlinedIcon />} onClick={() => void checkDelivery()}>Проверить готовность</Button></Stack>{deliveryPreflight ? <Stack spacing={1} sx={{ mt: 2 }}>{deliveryPreflight.checks.map((check) => <Alert key={`${check.code}-${check.order_id ?? ''}`} severity={check.ok ? 'success' : 'error'}>{check.message}</Alert>)}<Stack direction="row" sx={{ justifyContent: 'flex-end' }}><Button variant="contained" size="large" disabled={!stageIsCurrent || !deliveryPreflight.can_deliver} onClick={() => setDeliveryConfirmOpen(true)}>Подтвердить передачу WB</Button></Stack></Stack> : null}</Paper>
              ) : (
                <Alert severity="success">WB подтвердил передачу поставки в доставку.</Alert>
              )}
              {workspace.supply.barcode_asset?.preview_url ? (
                <Paper variant="outlined" sx={{ p: { xs: 2, md: 3 } }} data-testid="fbs-supply-qr">
                  <Stack direction={{ xs: 'column', sm: 'row' }} spacing={2} sx={{ justifyContent: 'space-between', alignItems: { sm: 'center' } }}>
                    <Box>
                      <Stack direction="row" spacing={1} sx={{ alignItems: 'center' }}>
                        <Typography variant="h6">Общий QR поставки WB</Typography>
                        <Chip label="Готов к печати" color="success" size="small" />
                      </Stack>
                      <Typography variant="body2" color="text.secondary" sx={{ mt: 0.5 }}>
                        WB сформировал QR после подтверждения передачи. Распечатайте его для сдачи всей поставки.
                      </Typography>
                    </Box>
                    <Button
                      variant="contained"
                      size="large"
                      startIcon={<PrintOutlinedIcon />}
                      onClick={() => openAssetPreview([workspace.supply.barcode_asset!])}
                    >
                      Печать QR поставки
                    </Button>
                  </Stack>
                </Paper>
              ) : null}
              {deliveryConfirmed && !workspace.supply.barcode_asset?.preview_url ? (
                <Alert
                  severity="warning"
                  action={(
                    <Button
                      color="inherit"
                      size="small"
                      disabled={busy}
                      data-testid="fbs-supply-qr-retry"
                      onClick={() => void run(() => retryFbsSupplyQr(token, authHeaders, workspace.supply.id), 'QR поставки получен.')}
                    >
                      Получить QR ещё раз
                    </Button>
                  )}
                >
                  Поставка уже передана, но WB не вернул общий QR. Повтор получает только QR и не передаёт поставку повторно.
                </Alert>
              ) : null}
            </Stack>
          ) : null}
        </Box>
      </DialogContent>
      <FbsPrintPreviewDialog
        token={token}
        authHeaders={authHeaders}
        batch={printBatch}
        open={printPreviewOpen}
        onClose={() => setPrintPreviewOpen(false)}
        onApplied={(asset) => confirmPrintApplied(asset.id)}
      />
      <Dialog open={metadataDialogOpen} onClose={busy ? undefined : () => setMetadataDialogOpen(false)} maxWidth="sm" fullWidth data-testid="fbs-marking-dialog">
        <DialogTitle>Маркировка заказа WB{metadataOrder ? ` №${metadataOrder.wb_order_id}` : ''}</DialogTitle>
        <DialogContent>
          <Stack spacing={2} sx={{ pt: 1 }}>
            {metadataOrder ? (
              <Stack direction="row" spacing={1.25} sx={{ alignItems: 'center' }}>
                <ProductPhotoThumb src={metadataOrder.product.image_url} alt={metadataOrder.product.name} size={48} previewSize={280} />
                <Box>
                  <Typography variant="body2" sx={{ fontWeight: 700 }}>{metadataOrder.product.name}</Typography>
                  <Typography variant="caption" color="text.secondary">Введите обязательный {metadataKindLabel(metadataKind)} для проверки.</Typography>
                </Box>
              </Stack>
            ) : null}
            <Stack direction={{ xs: 'column', sm: 'row' }} spacing={1.5} sx={{ alignItems: { sm: 'center' } }}>
              <Chip label={metadataKindLabel(metadataKind)} />
              <TextField
                autoFocus
                fullWidth
                label={`Сканированный ${metadataKindLabel(metadataKind)}`}
                value={metadataValue}
                onChange={(event) => setMetadataValue(event.target.value)}
                disabled={busy}
                onKeyDown={(event) => { if (event.key === 'Enter' && metadataValue.length > 0) void scanMetadata() }}
                slotProps={{ htmlInput: { 'data-testid': metadataOrderId ? `fbs-metadata-input-${metadataOrderId}` : 'fbs-metadata-input' } }}
              />
            </Stack>
          </Stack>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setMetadataDialogOpen(false)} disabled={busy}>Отмена</Button>
          <Button variant="contained" onClick={() => void scanMetadata()} disabled={busy || !metadataOrderId || metadataValue.length === 0} data-testid={metadataOrderId ? `fbs-metadata-submit-${metadataOrderId}` : 'fbs-metadata-submit'}>Проверить</Button>
        </DialogActions>
      </Dialog>
      <Dialog open={Boolean(undoOrderId)} onClose={() => setUndoOrderId(null)} maxWidth="xs" fullWidth>
        <DialogTitle>Отменить подбор?</DialogTitle>
        <DialogContent><Typography>Товар будет возвращён в исходную ячейку. Отменяйте только если в подборе действительно ошибка.</Typography></DialogContent>
        <DialogActions><Button onClick={() => setUndoOrderId(null)}>Не отменять</Button><Button color="error" variant="contained" onClick={() => { const orderId = undoOrderId; setUndoOrderId(null); if (orderId && workspace) void run(() => undoFbsPick(token, authHeaders, workspace.supply.id, orderId, createFbsIdempotencyKey()), 'Подбор отменён, остаток возвращён в исходную ячейку.') }}>Вернуть в ячейку</Button></DialogActions>
      </Dialog>
      <Dialog open={Boolean(boxAssignTarget)} onClose={busy ? undefined : () => setBoxAssignTarget(null)} maxWidth="md" fullWidth>
        <DialogTitle>Добавить товары в короб {boxAssignName}</DialogTitle>
        <DialogContent dividers>
          {availableForBox.length === 0 ? <Alert severity="info">Все упакованные товары уже распределены по коробам.</Alert> : <Stack spacing={1}>{availableForBox.map((order) => <Stack key={order.id} direction="row" spacing={1.25} sx={{ alignItems: 'center', p: 1, borderRadius: 1.5, bgcolor: selectedBoxOrderIds.includes(order.id) ? 'primary.50' : 'action.hover' }}><Checkbox checked={selectedBoxOrderIds.includes(order.id)} onChange={(_, checked) => setSelectedBoxOrderIds((current) => checked ? [...current, order.id] : current.filter((id) => id !== order.id))} /><ProductPhotoThumb src={order.product.image_url} alt={order.product.name} size={44} /><Box sx={{ flex: 1 }}><Typography variant="body2" sx={{ fontWeight: 700 }}>{order.product.name}</Typography><Typography variant="caption" color="text.secondary">Заказ WB №{order.wb_order_id} · 1 шт.</Typography></Box></Stack>)}</Stack>}
        </DialogContent>
        <DialogActions><Button onClick={() => setBoxAssignTarget(null)}>Отмена</Button><Button variant="contained" disabled={busy || selectedBoxOrderIds.length === 0} onClick={() => void assignBoxOrders()}>Добавить {selectedBoxOrderIds.length || ''} {selectedBoxOrderIds.length === 1 ? 'товар' : 'товара'}</Button></DialogActions>
      </Dialog>
      <Dialog open={Boolean(boxDeleteTarget)} onClose={busy ? undefined : () => setBoxDeleteTarget(null)} maxWidth="xs" fullWidth>
        <DialogTitle>Удалить пустой короб?</DialogTitle>
        <DialogContent>
          <Stack spacing={1.5}>
            <Typography>Удалить можно только короб без товаров. Если товар уже добавлен, сначала уберите его из короба.</Typography>
          </Stack>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setBoxDeleteTarget(null)} disabled={busy}>Не удалять</Button>
          <Button color="error" variant="contained" onClick={() => void deleteBox()} disabled={busy} data-testid="fbs-box-delete-confirm">
            Удалить короб
          </Button>
        </DialogActions>
      </Dialog>
      <Dialog open={deliveryConfirmOpen} onClose={() => setDeliveryConfirmOpen(false)} maxWidth="sm" fullWidth>
        <DialogTitle>Подтвердить передачу в WB?</DialogTitle>
        <DialogContent>{workspace ? <Stack spacing={1}><Typography>Поставка: {workspace.supply.name}</Typography><Typography>Селлер: {workspace.supply.seller.name}</Typography><Typography>Маршрут: {workspace.supply.delivery_type === 'pvz' ? 'ПВЗ' : 'Склад / СЦ'}</Typography><Typography>Заказов: {workspace.orders.length} · коробов: {workspace.boxes.length}</Typography><Alert severity="warning">Это отправит подтверждение передачи в WB.</Alert></Stack> : null}</DialogContent>
        <DialogActions><Button onClick={() => setDeliveryConfirmOpen(false)}>Отмена</Button><Button variant="contained" onClick={() => { setDeliveryConfirmOpen(false); void deliver() }}>Передать в WB</Button></DialogActions>
      </Dialog>
    </Dialog>
  )
}
