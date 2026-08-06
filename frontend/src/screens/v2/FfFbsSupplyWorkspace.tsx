import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
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
  Divider,
  IconButton,
  LinearProgress,
  MenuItem,
  Paper,
  Select,
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
import { apiUrl } from '../../api'
import { FbsMarkingStatusChip, FbsStickerStatusChip } from '../../components/fbs/FbsChips'
import { ProductPhotoThumb } from '../../components/ProductPhotoThumb'
import { FfPackagingTaskPanel, type PackagingTask } from '../ff/FfPackagingPage'
import { readApiErrorMessage } from '../../utils/readApiErrorMessage'
import { FbsPrintPreviewDialog } from './FbsPrintPreviewDialog'
import { bindFbsIdempotencyKey, buildFbsPickingListPrintHtml, createLatestRequestGuard, metadataKindLabel, normalizeMetadataKind, ordersWord, supportsFbsCommonSupplyQr } from './fbsUx'
import {
  confirmFbsPrintApplied,
  confirmFbsManualPick,
  createFbsPackingBoxes,
  createFbsIdempotencyKey,
  deleteFbsPackingBox,
  deliverFbsSupplyWithPreflightRefresh,
  FbsApiError,
  fetchFbsPrintBatch,
  fetchFbsWorkspace,
  finishFbsSupplyLocally,
  preflightFbsDelivery,
  assignFbsPackingBoxOrders,
  retryFbsSupplyQr,
  resolveFbsPickLocation,
  scanFbsOrderMetadata,
  scanFbsPickLocation,
  scanFbsPickProduct,
  startFbsSupplyWork,
  undoFbsPick,
  unassignFbsPackingBoxOrders,
  type FbsDeliveryPreflight,
  type FbsPickLocation,
  type FbsPrintBatch,
  type FbsWorkspace,
} from './fbsApi'

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
  { key: 'delivery', label: 'Сдача в WB' },
] as const

type StageKey = (typeof STAGES)[number]['key']

type UnassignedPackingGroup = {
  key: string
  productId: string | null
  name: string
  imageUrl: string | null
  orderIds: string[]
  wbOrderIds: number[]
}

function operationKeyStorageName(supplyId: string, action: 'cargo' | 'cargo-delete' | 'delivery', fingerprint = '') {
  return `wms:fbs:${supplyId}:${action}:${fingerprint}`
}

function persistentOperationKey(supplyId: string, action: 'cargo' | 'cargo-delete' | 'delivery', fingerprint = '') {
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

function clearPersistentOperationKey(supplyId: string, action: 'cargo' | 'cargo-delete' | 'delivery', fingerprint = '') {
  try {
    window.sessionStorage.removeItem(operationKeyStorageName(supplyId, action, fingerprint))
  } catch {
    // Storage may be unavailable in a hardened browser; server-side protection still applies.
  }
}

function visualStage(stage: FbsWorkspace['stage']): StageKey {
  if (stage === 'local_finish' || stage === 'tracking') return 'delivery'
  if (stage === 'order_stickers' || stage === 'handoff_prep') return 'packing'
  return stage
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
  const [manualLocationByOrder, setManualLocationByOrder] = useState<Record<string, string>>({})
  const [metadataOrderId, setMetadataOrderId] = useState('')
  const [metadataKind, setMetadataKind] = useState('sgtin')
  const [metadataValue, setMetadataValue] = useState('')
  const [printBatch, setPrintBatch] = useState<FbsPrintBatch | null>(null)
  const [printPreviewOpen, setPrintPreviewOpen] = useState(false)
  const [packagingTask, setPackagingTask] = useState<PackagingTask | null>(null)
  const [cargoCount, setCargoCount] = useState('1')
  const [packingBoxTargetByProduct, setPackingBoxTargetByProduct] = useState<Record<string, string>>({})
  const [packingBoxQtyByProduct, setPackingBoxQtyByProduct] = useState<Record<string, string>>({})
  const [packingBoxDeleteTarget, setPackingBoxDeleteTarget] = useState<string | null>(null)
  const [deliveryPreflight, setDeliveryPreflight] = useState<FbsDeliveryPreflight | null>(null)
  const [deliveryKey, setDeliveryKey] = useState(createFbsIdempotencyKey)
  const [deliveryConfirmOpen, setDeliveryConfirmOpen] = useState(false)
  const [deliverySubmitted, setDeliverySubmitted] = useState(false)
  const [undoOrderId, setUndoOrderId] = useState<string | null>(null)
  const [retryAction, setRetryAction] = useState<(() => void) | null>(null)
  const workspaceRequestGuard = useRef(createLatestRequestGuard()).current

  const load = useCallback(
    async (silent = false) => {
      if (!supplyId) return
      const requestGeneration = workspaceRequestGuard.begin()
      if (!silent) setBusy(true)
      try {
        const next = await fetchFbsWorkspace(token, authHeaders, supplyId)
        if (!workspaceRequestGuard.isCurrent(requestGeneration)) return
        setWorkspace(next)
        if (!silent) setStage(visualStage(next.stage))
      } catch (cause) {
        if (!silent && workspaceRequestGuard.isCurrent(requestGeneration)) {
          setError(cause instanceof Error ? cause.message : 'Не удалось загрузить поставку.')
        }
      } finally {
        if (!silent && workspaceRequestGuard.isCurrent(requestGeneration)) setBusy(false)
      }
    },
    [supplyId, token, authHeaders, workspaceRequestGuard],
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
    setManualLocationByOrder({})
    setMetadataOrderId('')
    setMetadataValue('')
    setPackingBoxTargetByProduct({})
    setPackingBoxQtyByProduct({})
    setPackingBoxDeleteTarget(null)
    setDeliveryConfirmOpen(false)
    setDeliverySubmitted(false)
    setUndoOrderId(null)
    if (!initialWorkspace) void load()
    return () => workspaceRequestGuard.invalidate()
  }, [open, supplyId, initialWorkspace, load, workspaceRequestGuard])

  useEffect(() => {
    const requiredOrder = workspace?.orders.find((order) => order.metadata.required.length > 0)
    if (!requiredOrder || metadataOrderId) return
    setMetadataOrderId(requiredOrder.id)
    setMetadataKind(normalizeMetadataKind(requiredOrder.metadata.required[0]))
  }, [workspace, metadataOrderId])

  useEffect(() => {
    if (!workspace) return
    setManualLocationByOrder((current) => {
      const next = { ...current }
      for (const order of workspace.orders) {
        if (!next[order.id] && order.inventory.locations[0]) {
          next[order.id] = order.inventory.locations[0].id
        }
      }
      return next
    })
  }, [workspace])

  useEffect(() => {
    setNotice(null)
  }, [workspace?.stage])

  useEffect(() => {
    if (!open || !supplyId || !['picking', 'delivery'].includes(stage)) return
    const timer = window.setInterval(() => {
      if (document.visibilityState === 'visible' && !busy) void load(true)
    }, 15_000)
    return () => window.clearInterval(timer)
  }, [open, supplyId, stage, busy, load])

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
    workspaceRequestGuard.invalidate()
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

  const manualPickOrder = async (order: FbsWorkspace['orders'][number]) => {
    if (!workspace) return
    const locationId = manualLocationByOrder[order.id]
    const location = order.inventory.locations.find((item) => item.id === locationId)
    if (!location || !order.product.id) return
    setBusy(true)
    setError(null)
    try {
      const resolved = await resolveFbsPickLocation(
        token,
        authHeaders,
        workspace.supply.id,
        { location_id: location.id },
      )
      const next = await confirmFbsManualPick(token, authHeaders, workspace.supply.id, {
        location_id: resolved.id,
        product_id: order.product.id,
        order_id: order.id,
        idempotency_key: createFbsIdempotencyKey(),
      })
      setWorkspace(next)
      setStage(visualStage(next.stage))
      setNotice(`Заказ WB №${order.wb_order_id} снят с ячейки ${location.code}.`)
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'Не удалось подтвердить ручной подбор.')
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

  const createLocalPackingBoxes = async (requestedCount?: number) => {
    if (!workspace) return
    const count = Math.max(1, Math.min(workspace.orders.length, requestedCount ?? (Number(cargoCount) || 1)))
    const idempotencyKey = createFbsIdempotencyKey()
    await run(
      bindFbsIdempotencyKey(idempotencyKey, (stableKey) => createFbsPackingBoxes(token, authHeaders, workspace.supply.id, {
        count,
        idempotency_key: stableKey,
      })),
      count === 1 ? 'Короб создан.' : `Создано коробов: ${count}.`,
    )
  }

  const assignPackingGroup = async (group: UnassignedPackingGroup) => {
    if (!workspace || workspace.packing_boxes.length === 0) return
    const boxId = packingBoxTargetByProduct[group.key] || workspace.packing_boxes[0].id
    const rawQty = Number(packingBoxQtyByProduct[group.key] || 1)
    const qty = Math.max(1, Math.min(group.orderIds.length, Number.isFinite(rawQty) ? Math.floor(rawQty) : 1))
    const orderIds = group.orderIds.slice(0, qty)
    const idempotencyKey = createFbsIdempotencyKey()
    const next = await run(
      bindFbsIdempotencyKey(idempotencyKey, (stableKey) => assignFbsPackingBoxOrders(token, authHeaders, workspace.supply.id, boxId, {
        order_ids: orderIds,
        idempotency_key: stableKey,
      })),
      `${qty} ${qty === 1 ? 'товар добавлен' : 'товара добавлено'} в короб.`,
    )
    if (next) setPackingBoxQtyByProduct((current) => ({ ...current, [group.key]: '1' }))
  }

  const unassignPackingBoxOrder = async (boxId: string, orderId: string) => {
    if (!workspace) return
    const idempotencyKey = createFbsIdempotencyKey()
    await run(
      bindFbsIdempotencyKey(idempotencyKey, (stableKey) => unassignFbsPackingBoxOrders(token, authHeaders, workspace.supply.id, boxId, {
        order_ids: [orderId],
        idempotency_key: stableKey,
      })),
      'Товар убран из короба.',
    )
  }

  const deleteLocalPackingBox = async () => {
    if (!workspace || !packingBoxDeleteTarget) return
    const boxId = packingBoxDeleteTarget
    const idempotencyKey = createFbsIdempotencyKey()
    const next = await run(
      bindFbsIdempotencyKey(idempotencyKey, (stableKey) => deleteFbsPackingBox(token, authHeaders, workspace.supply.id, boxId, stableKey)),
      'Пустой короб удалён.',
    )
    if (next) setPackingBoxDeleteTarget(null)
  }

  const checkDelivery = async () => {
    if (!workspace) return
    setBusy(true)
    setError(null)
    try {
      const next = await preflightFbsDelivery(token, authHeaders, workspace.supply.id)
      setDeliveryPreflight(next)
      if (next.can_deliver) setDeliveryConfirmOpen(true)
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'Проверка готовности к фиксации не выполнена.')
    } finally {
      setBusy(false)
    }
  }

  const deliver = async () => {
    if (!workspace || !deliveryPreflight?.can_deliver) return
    workspaceRequestGuard.invalidate()
    setBusy(true)
    setError(null)
    setNotice(null)
    try {
      const result = await deliverFbsSupplyWithPreflightRefresh(token, authHeaders, workspace.supply.id, {
        idempotency_key: deliveryKey,
        confirmed_preflight_version: deliveryPreflight.version,
      })
      if (result.kind === 'stale_preflight') {
        setDeliveryPreflight(result.preflight)
        setNotice('Проверка WB изменилась. Просмотрите результат и повторно подтвердите фиксацию состава.')
        return
      }
      const next = result.workspace
      setWorkspace(next)
      setStage(visualStage(next.stage))
      clearPersistentOperationKey(workspace.supply.id, 'delivery')
      setDeliveryKey(createFbsIdempotencyKey())
      setDeliveryPreflight(null)
      setDeliverySubmitted(true)
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'Состав поставки не зафиксирован в WB.')
    } finally {
      setBusy(false)
    }
  }

  const finishLocalWork = async () => {
    if (!workspace) return
    const idempotencyKey = createFbsIdempotencyKey()
    await run(
      bindFbsIdempotencyKey(idempotencyKey, (stableKey) => finishFbsSupplyLocally(token, authHeaders, workspace.supply.id, stableKey)),
      'Работа с поставкой завершена.',
    )
  }

  const undoPickedOrder = () => {
    const orderId = undoOrderId
    setUndoOrderId(null)
    if (!orderId || !workspace) return
    const idempotencyKey = createFbsIdempotencyKey()
    void run(
      bindFbsIdempotencyKey(idempotencyKey, (stableKey) => undoFbsPick(token, authHeaders, workspace.supply.id, orderId, stableKey)),
      'Подбор отменён, остаток возвращён в исходную ячейку.',
    )
  }

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
  const unassignedPackingGroups = useMemo(() => {
    if (!workspace) return []
    const unassigned = new Set(workspace.unassigned_order_ids)
    const grouped = new Map<string, UnassignedPackingGroup>()
    for (const order of workspace.orders) {
      if (!unassigned.has(order.id) || order.pack.status !== 'packed') continue
      const key = order.product.id ?? `order-${order.id}`
      const row = grouped.get(key) ?? {
        key,
        productId: order.product.id,
        name: order.product.name,
        imageUrl: order.product.image_url,
        orderIds: [],
        wbOrderIds: [],
      }
      row.orderIds.push(order.id)
      row.wbOrderIds.push(order.wb_order_id)
      grouped.set(key, row)
    }
    return [...grouped.values()]
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
  const stageBlockers = useMemo(
    () => workspace?.blockers.filter((blocker) => visualStage(blocker.stage as FbsWorkspace['stage']) === stage) ?? [],
    [workspace, stage],
  )
  const currentStage = workspace ? visualStage(workspace.stage) : 'composition'
  const currentStageIndex = STAGES.findIndex((item) => item.key === currentStage)
  const stageIsCurrent = stage === currentStage
  const requiredMetadataOrders = workspace?.orders.filter((order) => order.metadata.required.length > 0) ?? []
  const allPicked = Boolean(workspace && workspace.progress.total > 0 && workspace.progress.picked === workspace.progress.total)
  const rawStatusLabel = (value: string) => ({
    waiting: 'Ожидает WB',
    accepted: 'WB принял',
    applied: 'Нанесён',
    ready: 'Готов',
    error: 'Ошибка',
    missing: 'Не хватает',
    checking: 'Проверяется',
    ok: 'Проверен',
    assigned: 'Принят',
    rejected: 'Отклонён WB',
    replacement_required: 'Нужен новый код',
    in_delivery: 'Состав зафиксирован в WB',
    done: 'Завершён',
  }[value] ?? 'Статус уточняется')
  const deliveryConfirmed = deliverySubmitted
    || workspace?.stage === 'local_finish'
    || workspace?.stage === 'tracking'
    || ['in_delivery', 'done'].includes(workspace?.supply.status ?? '')
  const routeQrAssets = workspace?.supply.delivery_type === 'pvz'
    ? workspace.packing_boxes.map((box) => box.qr_asset).filter((asset): asset is NonNullable<typeof asset> => Boolean(asset))
    : workspace?.supply.barcode_asset ? [workspace.supply.barcode_asset] : []
  const allRouteQrReady = Boolean(workspace && routeQrAssets.length > 0 && routeQrAssets.every((asset) => asset.status === 'ready' && asset.preview_url))
  const allRouteQrApplied = Boolean(workspace && routeQrAssets.length > 0 && routeQrAssets.every((asset) => Boolean(asset.applied_at)))

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
            {workspace ? (
              <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mt: 1.25 }}>
                Сдать в Wildberries до {new Date(workspace.supply.nearest_deadline_at).toLocaleString('ru-RU')}
              </Typography>
            ) : null}
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
                  <TableHead><TableRow><TableCell>Заказ WB</TableCell><TableCell>Товар</TableCell><TableCell>Маркировка</TableCell><TableCell>Подбор</TableCell></TableRow></TableHead>
                  <TableBody>
                    {workspace.orders.map((order) => (
                      <TableRow key={order.id}>
                        <TableCell>№{order.wb_order_id}</TableCell>
                        <TableCell>
                          <Stack direction="row" spacing={1.5} sx={{ alignItems: 'center', minWidth: 0 }}>
                            <ProductPhotoThumb src={order.product.image_url} alt={order.product.name} size={56} previewSize={320} testId={`fbs-composition-photo-${order.id}`} />
                            <Box sx={{ minWidth: 0 }}>
                              <Typography variant="body2" sx={{ fontWeight: 700 }}>{order.product.name}</Typography>
                              <Typography variant="caption" color="text.secondary" sx={{ display: 'block' }}>{order.product.seller_article ?? 'Артикул не указан'}{order.product.wb_article ? ` · WB ${order.product.wb_article}` : ''}</Typography>
                              <Typography variant="caption" color="text.secondary" sx={{ display: 'block' }}>{order.product.barcode ?? 'ШК не указан'}</Typography>
                            </Box>
                          </Stack>
                        </TableCell>
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
              <Paper variant="outlined" sx={{ overflow: 'hidden' }} data-testid="fbs-manual-picking">
                <Stack direction={{ xs: 'column', sm: 'row' }} spacing={1.5} sx={{ justifyContent: 'space-between', alignItems: { sm: 'flex-start' }, mb: 2 }}>
                  <Box sx={{ px: 2.5, pt: 2.5 }}><Typography variant="h6">Подбор из ячеек</Typography><Typography variant="body2" color="text.secondary">Выберите ячейку и подтвердите снятие товара. Сканер для этого не требуется.</Typography></Box>
                  <Button sx={{ mt: 2.5, mr: 2.5 }} variant="outlined" startIcon={<PrintOutlinedIcon />} onClick={printPickingList} data-testid="fbs-pick-list-print">Печать листа подбора</Button>
                </Stack>
                <Table size="small">
                  <TableHead><TableRow><TableCell>Товар</TableCell><TableCell sx={{ width: 280 }}>Ячейка</TableCell><TableCell align="right" sx={{ width: 210 }}>Действие</TableCell></TableRow></TableHead>
                  <TableBody>{workspace.orders.map((order) => {
                    const picked = order.pick.status === 'picked'
                    return <TableRow key={order.id} data-testid={`fbs-manual-pick-${order.id}`}>
                      <TableCell><Stack direction="row" spacing={1.5} sx={{ alignItems: 'center' }}><ProductPhotoThumb src={order.product.image_url} alt={order.product.name} size={52} previewSize={280} /><Box><Typography variant="body2" sx={{ fontWeight: 700 }}>{order.product.name}</Typography><Typography variant="caption" color="text.secondary">Заказ WB №{order.wb_order_id} · {order.product.barcode ?? 'ШК не указан'}</Typography></Box></Stack></TableCell>
                      <TableCell>{picked ? <Chip color="success" size="small" label={order.pick.location_code ? `Снято: ${order.pick.location_code}` : 'Товар снят'} /> : order.inventory.locations.length ? <Select fullWidth size="small" value={manualLocationByOrder[order.id] ?? ''} disabled={!stageIsCurrent || busy} onChange={(event) => setManualLocationByOrder((current) => ({ ...current, [order.id]: String(event.target.value) }))} inputProps={{ 'aria-label': `Ячейка для заказа WB №${order.wb_order_id}` }}>{order.inventory.locations.map((location) => <MenuItem key={location.id} value={location.id}>{location.code} · доступно {location.available_unpacked}</MenuItem>)}</Select> : <Typography variant="body2" color="error.main">Нет доступной ячейки</Typography>}</TableCell>
                      <TableCell align="right">{picked ? <Button size="small" color="inherit" disabled={!stageIsCurrent || order.pack.status === 'packed' || busy} onClick={() => setUndoOrderId(order.id)}>Вернуть в ячейку</Button> : <Button size="small" variant="contained" disabled={!stageIsCurrent || busy || !manualLocationByOrder[order.id] || !order.product.id} onClick={() => void manualPickOrder(order)}>Снять с ячейки</Button>}</TableCell>
                    </TableRow>
                  })}</TableBody>
                </Table>
                {allPicked ? <Alert severity="success" sx={{ m: 2 }}>Все товары подобраны. Можно переходить к упаковке.</Alert> : null}
              </Paper>
              <Paper component="details" variant="outlined" sx={{ p: 2 }}>
                <Typography component="summary" variant="subtitle2" sx={{ cursor: 'pointer', userSelect: 'none' }}>Подбор сканером</Typography>
                <Typography variant="body2" color="text.secondary" sx={{ mt: 1, mb: 2 }}>Сначала отсканируйте ячейку, затем товар.</Typography>
                <Stack direction={{ xs: 'column', md: 'row' }} spacing={1.5}><TextField label="Штрихкод ячейки" value={locationBarcode} onChange={(e) => setLocationBarcode(e.target.value)} disabled={!stageIsCurrent || allPicked} onKeyDown={(e) => { if (e.key === 'Enter') void scanLocation() }} /><Button variant="outlined" onClick={() => void scanLocation()} disabled={!stageIsCurrent || allPicked}>Подтвердить ячейку</Button><TextField label="Штрихкод товара" value={productBarcode} onChange={(e) => setProductBarcode(e.target.value)} disabled={!stageIsCurrent || !pickLocation || allPicked} onKeyDown={(e) => { if (e.key === 'Enter') void scanProduct() }} sx={{ flex: 1 }} /><Button variant="contained" onClick={() => void scanProduct()} disabled={!stageIsCurrent || !pickLocation || !productBarcode.trim() || allPicked}>Подобрать товар</Button></Stack>
                {pickLocation ? <Alert severity="success" sx={{ mt: 2 }}>Ячейка {pickLocation.code} подтверждена · {pickLocation.warehouse_name}</Alert> : null}
              </Paper>
            </Stack>
          ) : null}

          {workspace && stage === 'packing' ? (
            <Stack spacing={2}>
              {!stageIsCurrent ? <Alert severity="success">Упаковка завершена. Этот этап доступен только для просмотра.</Alert> : null}
              {packagingTask ? (
                <Paper variant="outlined" sx={{ p: 2 }}>
                  <FfPackagingTaskPanel
                    token={token}
                    task={packagingTask}
                    unloadLabel={workspace.supply.name}
                    hideDocumentHeader
                    compactLayout
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
              {requiredMetadataOrders.length ? <Paper variant="outlined" sx={{ p: 2 }}>
                <Typography variant="h6">Идентификаторы заказа WB</Typography>
                <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>Отсканируйте требуемый идентификатор. Тип уже выбран для заказа.</Typography>
                <Stack direction={{ xs: 'column', md: 'row' }} spacing={1.5}>
                  <Select displayEmpty value={metadataOrderId} disabled={!stageIsCurrent} onChange={(e) => { const id = String(e.target.value); const order = requiredMetadataOrders.find((item) => item.id === id); setMetadataOrderId(id); setMetadataKind(normalizeMetadataKind(order?.metadata.required[0])) }} sx={{ minWidth: 190 }}><MenuItem value="">Выберите заказ</MenuItem>{requiredMetadataOrders.map((order) => <MenuItem key={order.id} value={order.id}>№{order.wb_order_id}</MenuItem>)}</Select>
                  <Chip label={metadataKindLabel(metadataKind)} />
                  <TextField label="Отсканированный идентификатор" value={metadataValue} onChange={(e) => setMetadataValue(e.target.value)} disabled={!stageIsCurrent} sx={{ flex: 1 }} />
                  <Button variant="contained" onClick={() => void scanMetadata()} disabled={!stageIsCurrent || !metadataOrderId || metadataValue.length === 0}>Проверить</Button>
                </Stack>
                <Table size="small" sx={{ mt: 2 }}>
                  <TableHead><TableRow><TableCell>Заказ WB</TableCell><TableCell>Что требуется</TableCell><TableCell>Фактическое состояние</TableCell></TableRow></TableHead>
                  <TableBody>{requiredMetadataOrders.map((order) => <TableRow key={order.id}><TableCell>№{order.wb_order_id}</TableCell><TableCell>{order.metadata.required.map(metadataKindLabel).join(', ')}</TableCell><TableCell>{order.metadata.states.length ? order.metadata.states.map((state) => `${metadataKindLabel(state.kind)}: ${rawStatusLabel(state.status)}${state.reason ? ` (${state.reason})` : ''}`).join('; ') : 'Данные ещё не переданы'}</TableCell></TableRow>)}</TableBody>
                </Table>
              </Paper> : null}
            </Stack>
          ) : null}

          {workspace && stage === 'packing' ? (
            <Stack spacing={2}>
              <Paper variant="outlined" sx={{ p: 2 }}>
                <Typography variant="h6">Печать стикеров заказов WB</Typography>
                <Typography variant="body2" color="text.secondary">Стикер WB и обязательная маркировка — разные проверки. Распечатайте стикеры WB и подтвердите нанесение на каждый товар.</Typography>
                <Table size="small" sx={{ my: 2 }}>
                  <TableHead><TableRow><TableCell>Заказ WB</TableCell><TableCell>Товар</TableCell><TableCell>Стикер WB</TableCell><TableCell>Маркировка</TableCell></TableRow></TableHead>
                  <TableBody>{workspace.orders.map((order) => <TableRow key={order.id}><TableCell>№{order.wb_order_id}</TableCell><TableCell>{order.product.name}</TableCell><TableCell><FbsStickerStatusChip status={order.sticker.status} /></TableCell><TableCell><FbsMarkingStatusChip required={order.metadata.required} states={order.metadata.states} /></TableCell></TableRow>)}</TableBody>
                </Table>
                <Stack direction="row" spacing={1} sx={{ justifyContent: 'flex-end', flexWrap: 'wrap' }} useFlexGap><Button variant="contained" startIcon={<PrintOutlinedIcon />} disabled={!stageIsCurrent} onClick={() => void requestPrintBatch()}>Получить и распечатать стикеры</Button>{printBatch?.missing ? <Button variant="text" disabled={!stageIsCurrent} onClick={() => void requestPrintBatch(undefined, true)}>Получить недостающие</Button> : null}</Stack>
              </Paper>
              {printBatch ? <Paper variant="outlined" sx={{ p: 2 }}><Typography variant="body2">Готово: {printBatch.ready}{printBatch.missing ? ` · Не получено: ${printBatch.missing}` : ''}{printBatch.failed ? ` · Ошибок: ${printBatch.failed}` : ''}</Typography><Button variant="outlined" disabled={printBatch.ready === 0} sx={{ mt: 1 }} onClick={() => setPrintPreviewOpen(true)}>Открыть предпросмотр и печать</Button>{printBatch.order_errors.map((item) => <Alert key={item.order_id} severity="error" sx={{ mt: 1 }}>Заказ WB №{item.wb_order_id}: {item.message}</Alert>)}</Paper> : null}
            </Stack>
          ) : null}

          {workspace && stage === 'packing' ? (
            <Paper variant="outlined" sx={{ overflow: 'hidden' }} data-testid="fbs-packing-boxes">
              <Box sx={{ px: { xs: 2, md: 3 }, py: 2.5, borderBottom: 1, borderColor: 'divider' }}>
                <Stack direction={{ xs: 'column', sm: 'row' }} spacing={1.5} sx={{ justifyContent: 'space-between', alignItems: { sm: 'center' } }}>
                  <Box>
                    <Stack direction="row" spacing={1} sx={{ alignItems: 'center', mb: 0.5 }}>
                      <Typography variant="h6">Короба</Typography>
                      <Chip size="small" variant="outlined" label={workspace.supply.delivery_type === 'pvz' ? 'QR коробов от WB' : 'Без QR коробов WB'} />
                    </Stack>
                    <Typography variant="body2" color="text.secondary">
                      Сначала упакуйте товары, затем распределите их по физическим коробам. Товар исчезает из списка после добавления в короб.
                    </Typography>
                  </Box>
                  {workspace.packing_boxes.length ? <Button variant="outlined" disabled={!stageIsCurrent || busy} onClick={() => void createLocalPackingBoxes(1)}>Добавить короб</Button> : null}
                </Stack>
              </Box>
              {workspace.packing_boxes.length === 0 ? (
                <Box sx={{ p: { xs: 2, md: 3 } }}>
                  <Typography variant="subtitle1" sx={{ fontWeight: 700 }}>Создать физические короба</Typography>
                  <Typography variant="body2" color="text.secondary" sx={{ mt: 0.5, mb: 2 }}>
                    Для ПВЗ WMS одновременно запросит у WB отдельный QR для каждого короба. Для склада или СЦ короба останутся внутренними, без печати лишних кодов.
                  </Typography>
                  <Stack direction="row" spacing={1.5} sx={{ alignItems: 'center' }}>
                    <TextField label="Количество коробов" type="number" size="small" value={cargoCount} onChange={(event) => setCargoCount(event.target.value)} slotProps={{ htmlInput: { min: 1, max: workspace.orders.length } }} sx={{ width: 190 }} />
                    <Button variant="contained" disabled={!stageIsCurrent || busy} onClick={() => void createLocalPackingBoxes()} data-testid="fbs-boxes-create">Создать короба</Button>
                  </Stack>
                </Box>
              ) : (
                <>
                  <Box sx={{ p: { xs: 2, md: 3 }, bgcolor: 'rgba(91, 33, 182, 0.035)', borderBottom: 1, borderColor: 'divider' }}>
                    <Typography variant="subtitle1" sx={{ fontWeight: 700, mb: 1.5 }}>Не распределено</Typography>
                    {unassignedPackingGroups.length === 0 ? <Alert severity="success">Все упакованные товары распределены по коробам.</Alert> : (
                      <Stack spacing={1}>
                        {unassignedPackingGroups.map((group) => (
                          <Paper key={group.key} variant="outlined" sx={{ p: 1.5 }}>
                            <Stack direction={{ xs: 'column', lg: 'row' }} spacing={1.5} sx={{ alignItems: { lg: 'center' } }}>
                              <Stack direction="row" spacing={1.25} sx={{ alignItems: 'center', flex: 1, minWidth: 0 }}>
                                <ProductPhotoThumb src={group.imageUrl} alt={group.name} size={48} previewSize={280} />
                                <Box><Typography variant="body2" sx={{ fontWeight: 700 }}>{group.name}</Typography><Typography variant="caption" color="text.secondary">Не распределено: {group.orderIds.length}</Typography></Box>
                              </Stack>
                              <Select size="small" value={packingBoxTargetByProduct[group.key] || workspace.packing_boxes[0].id} onChange={(event) => setPackingBoxTargetByProduct((current) => ({ ...current, [group.key]: String(event.target.value) }))} inputProps={{ 'aria-label': `Короб для товара ${group.name}` }} sx={{ minWidth: 150 }}>
                                {workspace.packing_boxes.map((box) => <MenuItem key={box.id} value={box.id}>Короб {box.box_number}</MenuItem>)}
                              </Select>
                              <TextField size="small" type="number" label="Количество" value={packingBoxQtyByProduct[group.key] || '1'} onChange={(event) => setPackingBoxQtyByProduct((current) => ({ ...current, [group.key]: event.target.value }))} slotProps={{ htmlInput: { min: 1, max: group.orderIds.length } }} sx={{ width: 125 }} />
                              <Button variant="contained" disabled={!stageIsCurrent || busy} onClick={() => void assignPackingGroup(group)}>Положить в короб</Button>
                            </Stack>
                          </Paper>
                        ))}
                      </Stack>
                    )}
                  </Box>
                  <Table size="small" data-testid="fbs-boxes-table">
                    <TableHead><TableRow><TableCell sx={{ width: 140 }}>Короб</TableCell><TableCell>Состав</TableCell><TableCell sx={{ width: 170 }}>QR короба</TableCell><TableCell align="right" sx={{ width: 190 }}>Действия</TableCell></TableRow></TableHead>
                    <TableBody>{workspace.packing_boxes.map((box) => (
                      <TableRow key={box.id}>
                        <TableCell><Typography variant="subtitle2">Короб {box.box_number}</Typography><Typography variant="caption" color="text.secondary">Товаров: {box.items_count}</Typography></TableCell>
                        <TableCell>{box.orders.length ? <Stack spacing={0.5}>{box.orders.map((item) => <Stack key={item.id} direction="row" spacing={1} sx={{ alignItems: 'center', justifyContent: 'space-between' }}><Typography variant="body2">{item.product_name} · заказ WB №{item.wb_order_id}</Typography><Button size="small" color="inherit" disabled={!stageIsCurrent || busy} onClick={() => void unassignPackingBoxOrder(box.id, item.id)}>Убрать</Button></Stack>)}</Stack> : <Typography variant="body2" color="text.secondary">Короб пуст</Typography>}</TableCell>
                        <TableCell>{workspace.supply.delivery_type === 'pvz' ? <Chip size="small" color={box.qr_asset?.preview_url ? 'success' : 'warning'} label={box.qr_asset?.preview_url ? 'QR готов' : 'QR ожидается'} /> : <Chip size="small" variant="outlined" label="Не требуется" />}</TableCell>
                        <TableCell align="right"><Stack direction="row" spacing={0.5} sx={{ justifyContent: 'flex-end' }}>{workspace.supply.delivery_type === 'pvz' ? <Button size="small" startIcon={<PrintOutlinedIcon />} disabled={!box.qr_asset?.preview_url} onClick={() => box.qr_asset && openAssetPreview([box.qr_asset])}>Печать QR</Button> : null}<IconButton size="small" color="error" aria-label={`Удалить короб ${box.box_number}`} disabled={!stageIsCurrent || busy || box.items_count > 0} onClick={() => setPackingBoxDeleteTarget(box.id)}><DeleteOutlinedIcon fontSize="small" /></IconButton></Stack></TableCell>
                      </TableRow>
                    ))}</TableBody>
                  </Table>
                </>
              )}
            </Paper>
          ) : null}
          {workspace && stage === 'delivery' ? (
            <Stack spacing={2}>
              {workspace.supply.operator_finished_at ? (
                <Alert severity="success">
                  Работа с поставкой завершена {new Date(workspace.supply.operator_finished_at).toLocaleString('ru-RU')}. Она будет перемещаться по статусам автоматически.
                </Alert>
              ) : !deliveryConfirmed ? (
                <Paper variant="outlined" sx={{ p: { xs: 2, md: 3 } }}>
                  <Stack direction={{ xs: 'column', md: 'row' }} spacing={2} sx={{ justifyContent: 'space-between', alignItems: { md: 'center' } }}>
                    <Box sx={{ maxWidth: 760 }}>
                      <Typography variant="h6">Зафиксировать состав поставки в WB</Typography>
                      <Typography variant="body2" color="text.secondary" sx={{ mt: 0.5 }}>
                        WMS проверит готовность автоматически. После фиксации состав менять нельзя — на этом же экране появятся QR, необходимые для сдачи.
                      </Typography>
                    </Box>
                    <Button variant="contained" size="large" disabled={!stageIsCurrent || busy} onClick={() => void checkDelivery()} data-testid="fbs-delivery-prepare">
                      Зафиксировать поставку в WB
                    </Button>
                  </Stack>
                  {deliveryPreflight && !deliveryPreflight.can_deliver ? (
                    <Stack spacing={1} sx={{ mt: 2 }}>
                      {deliveryPreflight.checks.filter((check) => !check.ok).map((check) => (
                        <Alert key={`${check.code}-${check.order_id ?? ''}`} severity="error">{check.message}</Alert>
                      ))}
                    </Stack>
                  ) : null}
                </Paper>
              ) : <Alert severity="success">Состав поставки зафиксирован в WB. Подготовьте обязательные QR и завершите работу.</Alert>}
              {supportsFbsCommonSupplyQr(workspace.supply) && workspace.supply.barcode_asset?.preview_url ? (
                <Paper variant="outlined" sx={{ p: { xs: 2, md: 3 } }} data-testid="fbs-supply-qr">
                  <Stack direction={{ xs: 'column', sm: 'row' }} spacing={2} sx={{ justifyContent: 'space-between', alignItems: { sm: 'center' } }}>
                    <Box>
                      <Stack direction="row" spacing={1} sx={{ alignItems: 'center' }}>
                        <Typography variant="h6">Общий QR поставки WB</Typography>
                        <Chip label="Готов к печати" color="success" size="small" />
                      </Stack>
                      <Typography variant="body2" color="text.secondary" sx={{ mt: 0.5 }}>
                        Распечатайте и нанесите этот QR на поставку до завершения работы.
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
              {workspace.supply.delivery_type === 'pvz' && deliveryConfirmed ? (
                <Paper variant="outlined" sx={{ p: { xs: 2, md: 3 } }} data-testid="fbs-delivery-box-qr">
                  <Stack direction={{ xs: 'column', sm: 'row' }} spacing={2} sx={{ justifyContent: 'space-between', alignItems: { sm: 'center' } }}>
                    <Box>
                      <Typography variant="h6">QR коробов WB</Typography>
                      <Typography variant="body2" color="text.secondary" sx={{ mt: 0.5 }}>
                        Для сдачи в ПВЗ распечатайте и нанесите отдельный QR на каждый физический короб.
                      </Typography>
                    </Box>
                    <Button variant="contained" size="large" startIcon={<PrintOutlinedIcon />} disabled={!allRouteQrReady} onClick={() => openAssetPreview(routeQrAssets)}>
                      Печать всех QR коробов
                    </Button>
                  </Stack>
                  <Stack direction="row" spacing={1} sx={{ mt: 2, flexWrap: 'wrap' }} useFlexGap>
                    {workspace.packing_boxes.map((box) => (
                      <Chip
                        key={box.id}
                        size="small"
                        color={box.qr_asset?.applied_at ? 'success' : box.qr_asset?.preview_url ? 'warning' : 'default'}
                        label={`Короб ${box.box_number}: ${box.qr_asset?.applied_at ? 'QR нанесён' : box.qr_asset?.preview_url ? 'готов к печати' : 'QR ожидается'}`}
                      />
                    ))}
                  </Stack>
                </Paper>
              ) : null}
              {supportsFbsCommonSupplyQr(workspace.supply) && deliveryConfirmed && !workspace.supply.barcode_asset?.preview_url ? (
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
                  Состав уже зафиксирован, но WB не вернул общий QR. Повтор получает только QR и не фиксирует состав заново.
                </Alert>
              ) : null}
              {workspace.wb_sync_stale ? (
                <Alert severity="warning">
                  WB ещё не подтвердил актуальный статус. WMS проверит его автоматически; вручную обновлять ничего не нужно.
                </Alert>
              ) : null}
              {deliveryConfirmed && !workspace.supply.operator_finished_at ? (
                <Paper variant="outlined" sx={{ p: { xs: 2, md: 3 } }}>
                  <Stack direction={{ xs: 'column', md: 'row' }} spacing={2} sx={{ justifyContent: 'space-between', alignItems: { md: 'center' } }}>
                    <Box>
                      <Typography variant="h6">Завершить работу с поставкой</Typography>
                      <Typography variant="body2" color="text.secondary" sx={{ mt: 0.5 }}>
                        {allRouteQrApplied
                          ? 'Все обязательные QR подтверждены. После завершения поставка уйдёт в автоматическое отслеживание.'
                          : 'Сначала откройте QR на печать и подтвердите его нанесение.'}
                      </Typography>
                    </Box>
                    <Button variant="contained" size="large" disabled={!stageIsCurrent || busy || !allRouteQrApplied} onClick={() => void finishLocalWork()} data-testid="fbs-local-finish">
                      Завершить работу с поставкой
                    </Button>
                  </Stack>
                </Paper>
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
      <Dialog open={Boolean(undoOrderId)} onClose={() => setUndoOrderId(null)} maxWidth="xs" fullWidth>
        <DialogTitle>Отменить подбор?</DialogTitle>
        <DialogContent><Typography>Товар будет возвращён в исходную ячейку. Отменяйте только если в подборе действительно ошибка.</Typography></DialogContent>
        <DialogActions><Button onClick={() => setUndoOrderId(null)}>Не отменять</Button><Button color="error" variant="contained" onClick={undoPickedOrder}>Вернуть в ячейку</Button></DialogActions>
      </Dialog>
      <Dialog open={Boolean(packingBoxDeleteTarget)} onClose={busy ? undefined : () => setPackingBoxDeleteTarget(null)} maxWidth="xs" fullWidth>
        <DialogTitle>Удалить пустой короб?</DialogTitle>
        <DialogContent>
          <Alert severity="warning">Удалить можно только пустой короб. Если внутри есть товары, сначала уберите их из короба.</Alert>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setPackingBoxDeleteTarget(null)} disabled={busy}>Не удалять</Button>
          <Button color="error" variant="contained" onClick={() => void deleteLocalPackingBox()} disabled={busy} data-testid="fbs-box-delete-confirm">Удалить короб</Button>
        </DialogActions>
      </Dialog>
      <Dialog open={deliveryConfirmOpen} onClose={() => setDeliveryConfirmOpen(false)} maxWidth="sm" fullWidth>
        <DialogTitle>Зафиксировать состав поставки?</DialogTitle>
        <DialogContent>{workspace ? <Stack spacing={1}><Typography>Поставка: {workspace.supply.name}</Typography><Typography>Селлер: {workspace.supply.seller.name}</Typography><Typography>Маршрут: {workspace.supply.delivery_type === 'pvz' ? 'ПВЗ' : 'Склад / СЦ'}</Typography><Typography>Заказов: {workspace.orders.length}{workspace.supply.delivery_type === 'pvz' ? ` · коробов: ${workspace.packing_boxes.length}` : ''}</Typography><Alert severity="warning">После фиксации в WB нельзя менять состав и распределение по коробам. Это ещё не означает физическую сдачу поставки.</Alert></Stack> : null}</DialogContent>
        <DialogActions><Button onClick={() => setDeliveryConfirmOpen(false)}>Отмена</Button><Button variant="contained" onClick={() => { setDeliveryConfirmOpen(false); void deliver() }}>Зафиксировать в WB</Button></DialogActions>
      </Dialog>
    </Dialog>
  )
}
