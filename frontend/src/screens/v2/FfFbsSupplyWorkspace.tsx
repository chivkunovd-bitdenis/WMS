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
  TableContainer,
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
  clearFbsPackingBox,
  closeFbsPackingBox,
  createFbsPackingBoxes,
  createFbsIdempotencyKey,
  deleteFbsPackingBox,
  deliverFbsSupplyWithPreflightRefresh,
  FbsApiError,
  fetchFbsPrintBatch,
  fetchFbsWorkspace,
  finishFbsSupplyLocally,
  preflightFbsDelivery,
  reopenFbsPackingBox,
  assignFbsPackingBoxOrders,
  retryFbsPackingBoxQr,
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

type ManualPickRow = {
  key: string
  productId: string | null
  productName: string
  imageUrl: string | null
  barcode: string | null
  location: FbsWorkspace['orders'][number]['inventory']['locations'][number] | null
  pendingOrders: FbsWorkspace['orders']
  pickedOrders: FbsWorkspace['orders']
  productRequired: number
  productPicked: number
}

type PersistentAction = 'cargo' | 'cargo-delete' | 'delivery' | 'print-applied'

function operationKeyStorageName(supplyId: string, action: PersistentAction, fingerprint = '') {
  return `wms:fbs:${supplyId}:${action}:${fingerprint}`
}

function persistentOperationKey(supplyId: string, action: PersistentAction, fingerprint = '') {
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

function clearPersistentOperationKey(supplyId: string, action: PersistentAction, fingerprint = '') {
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

function boxesWord(count: number) {
  const lastTwo = Math.abs(count) % 100
  if (lastTwo >= 11 && lastTwo <= 14) return 'коробов'
  const last = lastTwo % 10
  if (last === 1) return 'короб'
  if (last >= 2 && last <= 4) return 'короба'
  return 'коробов'
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
  const [loadingWorkspace, setLoadingWorkspace] = useState(false)
  const [pendingActions, setPendingActions] = useState<Set<string>>(() => new Set())
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
  const [cargoCount, setCargoCount] = useState('1')
  const [packingBoxTargetByProduct, setPackingBoxTargetByProduct] = useState<Record<string, string>>({})
  const [packingBoxQtyByProduct, setPackingBoxQtyByProduct] = useState<Record<string, string>>({})
  const [packingBoxClearTarget, setPackingBoxClearTarget] = useState<string | null>(null)
  const [packingBoxDeleteTarget, setPackingBoxDeleteTarget] = useState<string | null>(null)
  const [deliveryPreflight, setDeliveryPreflight] = useState<FbsDeliveryPreflight | null>(null)
  const [deliveryKey, setDeliveryKey] = useState(createFbsIdempotencyKey)
  const [deliveryConfirmOpen, setDeliveryConfirmOpen] = useState(false)
  const [deliverySubmitted, setDeliverySubmitted] = useState(false)
  const [undoOrderId, setUndoOrderId] = useState<string | null>(null)
  const [retryAction, setRetryAction] = useState<(() => void) | null>(null)
  const workspaceRequestGuard = useRef(createLatestRequestGuard()).current
  const pendingActionsRef = useRef<Set<string>>(new Set())

  const setActionPending = useCallback((actionKey: string, pending: boolean) => {
    const next = new Set(pendingActionsRef.current)
    if (pending) next.add(actionKey)
    else next.delete(actionKey)
    pendingActionsRef.current = next
    setPendingActions(next)
  }, [])

  const load = useCallback(
    async (silent = false) => {
      if (!supplyId) return
      const requestGeneration = workspaceRequestGuard.begin()
      if (!silent) setLoadingWorkspace(true)
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
        if (!silent && workspaceRequestGuard.isCurrent(requestGeneration)) setLoadingWorkspace(false)
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
    setMetadataOrderId('')
    setMetadataValue('')
    setMetadataDialogOpen(false)
    setPackingBoxTargetByProduct({})
    setPackingBoxQtyByProduct({})
    setPackingBoxClearTarget(null)
    setPackingBoxDeleteTarget(null)
    setDeliveryConfirmOpen(false)
    setDeliverySubmitted(false)
    setUndoOrderId(null)
    pendingActionsRef.current = new Set()
    setPendingActions(new Set())
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
    setNotice(null)
  }, [workspace?.stage])

  useEffect(() => {
    if (!open || !supplyId || !['picking', 'delivery'].includes(stage)) return
    const timer = window.setInterval(() => {
      if (document.visibilityState === 'visible' && pendingActionsRef.current.size === 0) void load(true)
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

  const executeAction = async <T,>(
    actionKey: string,
    operation: () => Promise<T>,
    fallbackError: string,
    onSuccess?: (result: T) => void | Promise<void>,
  ): Promise<T | null> => {
    if (pendingActionsRef.current.has(actionKey)) return null
    setActionPending(actionKey, true)
    setError(null)
    setRetryAction(null)
    try {
      const result = await operation()
      await onSuccess?.(result)
      return result
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : fallbackError)
      if (cause instanceof FbsApiError && cause.retryable) {
        setRetryAction(() => () => { void executeAction(actionKey, operation, fallbackError, onSuccess) })
      }
      return null
    } finally {
      setActionPending(actionKey, false)
    }
  }

  const run = async (
    actionKey: string,
    operation: () => Promise<FbsWorkspace>,
    success: string,
    preserveVisibleStage = false,
  ) => {
    workspaceRequestGuard.invalidate()
    setNotice(null)
    return executeAction(actionKey, operation, 'Операция не выполнена.', (next) => {
      setWorkspace(next)
      if (!preserveVisibleStage) setStage(visualStage(next.stage))
      if (success) setNotice(success)
    })
  }

  const scanLocation = async () => {
    if (!workspace || !locationBarcode.trim()) return
    const result = await executeAction(
      'scan-location',
      () => scanFbsPickLocation(
        token,
        authHeaders,
        workspace.supply.id,
        locationBarcode.trim(),
      ),
      'Ячейка не подтверждена.',
      (next) => {
        setPickLocation(next)
        setProductBarcode('')
      },
    )
    if (!result) return
  }

  const scanProduct = async () => {
    if (!workspace || !pickLocation || !productBarcode.trim()) return
    const key = createFbsIdempotencyKey()
    const next = await run(
      'scan-product',
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

  const manualPickRow = async (row: ManualPickRow) => {
    if (!workspace || !row.location || !row.productId || row.pendingOrders.length === 0) return
    const idempotencyKeys = row.pendingOrders.map(() => createFbsIdempotencyKey())
    const next = await executeAction(
      `manual-pick:${row.key}`,
      async () => {
        const resolved = await resolveFbsPickLocation(
          token,
          authHeaders,
          workspace.supply.id,
          { location_id: row.location!.id },
        )
        let latest: FbsWorkspace | null = null
        for (const [index, order] of row.pendingOrders.entries()) {
          latest = await confirmFbsManualPick(token, authHeaders, workspace.supply.id, {
            location_id: resolved.id,
            product_id: row.productId!,
            order_id: order.id,
            idempotency_key: idempotencyKeys[index]!,
          })
        }
        return latest!
      },
      'Не удалось подтвердить ручной подбор.',
      (updated) => {
        setWorkspace(updated)
        setStage(visualStage(updated.stage))
        setNotice(`${row.pendingOrders.length} шт. товара снято с ячейки ${row.location!.code}.`)
      },
    )
    if (!next) {
      await load(true)
      return
    }
  }

  const scanMetadata = async () => {
    if (!workspace || !metadataOrderId || metadataValue.length === 0) return
    const orderId = metadataOrderId
    const value = metadataValue
    const idempotencyKey = createFbsIdempotencyKey()
    const saved = await executeAction(
      `metadata:${orderId}`,
      () => scanFbsOrderMetadata(token, authHeaders, orderId, {
          kind: metadataKind,
          raw_value: value,
          idempotency_key: idempotencyKey,
        }),
      'Идентификатор не сохранён.',
      async () => {
        setMetadataValue('')
        await load(true)
        setMetadataDialogOpen(false)
        setNotice('Идентификатор передан на серверную проверку WB.')
      },
    )
    if (!saved) return
  }

  const requestPrintBatch = async (orderIds?: string[], retryMissing = false) => {
    if (!workspace) return
    const actionKey = `print-sticker:${orderIds?.join(',') ?? 'all'}:${retryMissing ? 'retry' : 'initial'}`
    const batch = await executeAction(
      actionKey,
      () => fetchFbsPrintBatch(token, authHeaders, workspace.supply.id, {
        kind: 'order_sticker',
        order_ids: orderIds ?? workspace.orders.map((order) => order.id),
        retry_missing: retryMissing,
      }),
      'Стикеры не получены.',
      (nextBatch) => {
        setPrintBatch(nextBatch)
        if (nextBatch.ready === 0) {
          setError('WB не вернул ни одного готового стикера. Печать не открыта.')
        } else {
          setPrintPreviewOpen(true)
        }
      },
    )
    if (!batch) return
  }

  const confirmPrintApplied = async (assetId: string) => {
    if (!workspace) return
    const idempotencyKey = persistentOperationKey(workspace.supply.id, 'print-applied', assetId)
    const applied = await executeAction(
      `print-applied:${assetId}`,
      () => confirmFbsPrintApplied(token, authHeaders, assetId, idempotencyKey),
      'Нанесение не подтверждено.',
      async () => {
        clearPersistentOperationKey(workspace.supply.id, 'print-applied', assetId)
        setPrintBatch((current) => current ? {
          ...current,
          assets: current.assets.map((asset) => asset.id === assetId
            ? { ...asset, applied_at: new Date().toISOString() }
            : asset),
        } : current)
        await load(true)
      },
    )
    if (!applied) throw new Error('Нанесение не подтверждено.')
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
    const fingerprint = String(count)
    const idempotencyKey = persistentOperationKey(workspace.supply.id, 'cargo', fingerprint)
    const next = await run(
      'box-create',
      bindFbsIdempotencyKey(idempotencyKey, (stableKey) => createFbsPackingBoxes(token, authHeaders, workspace.supply.id, {
        count,
        idempotency_key: stableKey,
      })),
      count === 1 ? 'Короб создан.' : `Создано коробов: ${count}.`,
      true,
    )
    if (next) clearPersistentOperationKey(workspace.supply.id, 'cargo', fingerprint)
  }

  const assignPackingGroup = async (group: UnassignedPackingGroup) => {
    if (!workspace) return
    const firstOpenBox = workspace.packing_boxes.find((box) => box.status === 'open')
    if (!firstOpenBox) return
    const requestedBoxId = packingBoxTargetByProduct[group.key]
    const selectedOpenBox = workspace.packing_boxes.find((box) => box.id === requestedBoxId && box.status === 'open')
    const boxId = selectedOpenBox?.id ?? firstOpenBox.id
    const rawQty = Number(packingBoxQtyByProduct[group.key] || 1)
    const qty = Math.max(1, Math.min(group.orderIds.length, Number.isFinite(rawQty) ? Math.floor(rawQty) : 1))
    const orderIds = group.orderIds.slice(0, qty)
    const idempotencyKey = createFbsIdempotencyKey()
    const next = await run(
      `box-assign:${group.key}`,
      bindFbsIdempotencyKey(idempotencyKey, (stableKey) => assignFbsPackingBoxOrders(token, authHeaders, workspace.supply.id, boxId, {
        order_ids: orderIds,
        idempotency_key: stableKey,
      })),
      `${qty} ${qty === 1 ? 'товар добавлен' : 'товара добавлено'} в короб.`,
      true,
    )
    if (next) setPackingBoxQtyByProduct((current) => ({ ...current, [group.key]: '1' }))
  }

  const unassignPackingBoxOrder = async (boxId: string, orderId: string) => {
    if (!workspace) return
    const idempotencyKey = createFbsIdempotencyKey()
    await run(
      `box-unassign:${orderId}`,
      bindFbsIdempotencyKey(idempotencyKey, (stableKey) => unassignFbsPackingBoxOrders(token, authHeaders, workspace.supply.id, boxId, {
        order_ids: [orderId],
        idempotency_key: stableKey,
      })),
      'Товар убран из короба.',
      true,
    )
  }

  const changePackingBoxState = async (boxId: string, action: 'close' | 'reopen') => {
    if (!workspace) return
    const idempotencyKey = createFbsIdempotencyKey()
    const operation = action === 'close' ? closeFbsPackingBox : reopenFbsPackingBox
    await run(
      `box-${action}:${boxId}`,
      bindFbsIdempotencyKey(idempotencyKey, (stableKey) => operation(token, authHeaders, workspace.supply.id, boxId, stableKey)),
      action === 'close' ? 'Короб закрыт.' : 'Короб снова открыт для изменений.',
      true,
    )
  }

  const clearLocalPackingBox = async () => {
    if (!workspace || !packingBoxClearTarget) return
    const boxId = packingBoxClearTarget
    const idempotencyKey = createFbsIdempotencyKey()
    const next = await run(
      `box-clear:${boxId}`,
      bindFbsIdempotencyKey(idempotencyKey, (stableKey) => clearFbsPackingBox(token, authHeaders, workspace.supply.id, boxId, stableKey)),
      'Короб очищен. Товары возвращены в список нераспределённых.',
      true,
    )
    if (next) setPackingBoxClearTarget(null)
  }

  const retryPackingBoxQr = async (boxId: string) => {
    if (!workspace) return
    const idempotencyKey = createFbsIdempotencyKey()
    await run(
      `box-qr:${boxId}`,
      bindFbsIdempotencyKey(idempotencyKey, (stableKey) => retryFbsPackingBoxQr(token, authHeaders, workspace.supply.id, boxId, stableKey)),
      'QR короба получен.',
      true,
    )
  }

  const deleteLocalPackingBox = async () => {
    if (!workspace || !packingBoxDeleteTarget) return
    const boxId = packingBoxDeleteTarget
    const idempotencyKey = persistentOperationKey(workspace.supply.id, 'cargo-delete', boxId)
    const next = await run(
      `box-delete:${boxId}`,
      bindFbsIdempotencyKey(idempotencyKey, (stableKey) => deleteFbsPackingBox(token, authHeaders, workspace.supply.id, boxId, stableKey)),
      'Пустой короб удалён.',
      true,
    )
    if (next) {
      clearPersistentOperationKey(workspace.supply.id, 'cargo-delete', boxId)
      setPackingBoxDeleteTarget(null)
    }
  }

  const checkDelivery = async () => {
    if (!workspace) return
    const next = await executeAction(
      'delivery-check',
      () => preflightFbsDelivery(token, authHeaders, workspace.supply.id),
      'Проверка готовности к передаче не выполнена.',
      (preflight) => {
        setDeliveryPreflight(preflight)
        setNotice(preflight.can_deliver ? 'Поставка готова к передаче в WB.' : 'Перед передачей устраните найденные блокеры.')
      },
    )
    if (!next) return
  }

  const deliver = async () => {
    if (!workspace || !deliveryPreflight?.can_deliver) return
    workspaceRequestGuard.invalidate()
    setNotice(null)
    const result = await executeAction(
      'delivery-submit',
      () => deliverFbsSupplyWithPreflightRefresh(token, authHeaders, workspace.supply.id, {
        idempotency_key: deliveryKey,
        confirmed_preflight_version: deliveryPreflight.version,
      }),
      'Поставка не передана в WB.',
      (deliveryResult) => {
        setDeliveryConfirmOpen(false)
        if (deliveryResult.kind === 'stale_preflight') {
          setDeliveryPreflight(deliveryResult.preflight)
          setNotice('Проверка WB изменилась. Просмотрите результат и повторно подтвердите передачу.')
          return
        }
        const next = deliveryResult.workspace
        setWorkspace(next)
        setStage(visualStage(next.stage))
        clearPersistentOperationKey(workspace.supply.id, 'delivery')
        setDeliveryKey(createFbsIdempotencyKey())
        setDeliveryPreflight(null)
        setDeliverySubmitted(true)
      },
    )
    if (!result) return
  }

  const finishLocalWork = async () => {
    if (!workspace) return
    const idempotencyKey = createFbsIdempotencyKey()
    await run(
      'local-finish',
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
      `pick-undo:${orderId}`,
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
  const manualPickingRows = useMemo<ManualPickRow[]>(() => {
    if (!workspace) return []
    const groups = new Map<string, {
      key: string
      productId: string | null
      productName: string
      imageUrl: string | null
      barcode: string | null
      orders: FbsWorkspace['orders']
      locations: Map<string, FbsWorkspace['orders'][number]['inventory']['locations'][number]>
    }>()
    for (const order of workspace.orders) {
      const key = order.product.id ?? `unmapped-${order.id}`
      const group: {
        key: string
        productId: string | null
        productName: string
        imageUrl: string | null
        barcode: string | null
        orders: FbsWorkspace['orders']
        locations: Map<string, FbsWorkspace['orders'][number]['inventory']['locations'][number]>
      } = groups.get(key) ?? {
        key,
        productId: order.product.id,
        productName: order.product.name,
        imageUrl: order.product.image_url,
        barcode: order.product.barcode,
        orders: [],
        locations: new Map(),
      }
      group.orders.push(order)
      for (const location of order.inventory.locations) {
        const current = group.locations.get(location.id)
        if (!current || location.available_unpacked > current.available_unpacked) {
          group.locations.set(location.id, location)
        }
      }
      groups.set(key, group)
    }

    const rows: ManualPickRow[] = []
    for (const group of groups.values()) {
      const picked = group.orders.filter((order) => order.pick.status === 'picked')
      const pending = group.orders.filter((order) => order.pick.status !== 'picked')
      const rowsByLocation = new Map<string, ManualPickRow>()
      const locationsByCode = new Map([...group.locations.values()].map((location) => [location.code, location]))
      const ensureRow = (location: ManualPickRow['location'], fallbackKey: string) => {
        const key = `${group.key}:${location?.id ?? fallbackKey}`
        const current = rowsByLocation.get(key)
        if (current) return current
        const created: ManualPickRow = {
          key,
          productId: group.productId,
          productName: group.productName,
          imageUrl: group.imageUrl,
          barcode: group.barcode,
          location,
          pendingOrders: [],
          pickedOrders: [],
          productRequired: group.orders.length,
          productPicked: picked.length,
        }
        rowsByLocation.set(key, created)
        return created
      }

      for (const order of picked) {
        const locationCode = order.pick.location_code
        const location = locationCode ? locationsByCode.get(locationCode) ?? null : null
        ensureRow(location, `picked-${locationCode ?? 'unknown'}`).pickedOrders.push(order)
      }

      let pendingOffset = 0
      for (const location of group.locations.values()) {
        if (pendingOffset >= pending.length) break
        const take = Math.min(location.available_unpacked, pending.length - pendingOffset)
        if (take <= 0) continue
        ensureRow(location, location.id).pendingOrders.push(...pending.slice(pendingOffset, pendingOffset + take))
        pendingOffset += take
      }
      if (pendingOffset < pending.length) {
        ensureRow(null, 'no-location').pendingOrders.push(...pending.slice(pendingOffset))
      }
      rows.push(...rowsByLocation.values())
    }
    return rows
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
  const metadataOrder = workspace?.orders.find((order) => order.id === metadataOrderId) ?? null
  const openPackingBoxes = workspace?.packing_boxes.filter((box) => box.status === 'open') ?? []
  const allPicked = Boolean(workspace && workspace.progress.total > 0 && workspace.progress.picked === workspace.progress.total)
  const deliveryConfirmed = deliverySubmitted
    || workspace?.stage === 'local_finish'
    || workspace?.stage === 'tracking'
    || ['in_delivery', 'done'].includes(workspace?.supply.status ?? '')
  const packingEditable = Boolean(workspace && !deliveryConfirmed)
  const routeQrAssets = workspace?.supply.delivery_type === 'pvz'
    ? workspace.packing_boxes.map((box) => box.qr_asset).filter((asset): asset is NonNullable<typeof asset> => Boolean(asset))
    : workspace?.supply.barcode_asset ? [workspace.supply.barcode_asset] : []
  const requiredRouteQrCount = workspace?.supply.delivery_type === 'pvz' ? workspace.packing_boxes.length : 1
  const allRouteQrReady = Boolean(workspace && routeQrAssets.length === requiredRouteQrCount && routeQrAssets.every((asset) => asset.status === 'ready' && asset.preview_url))
  const allRouteQrApplied = Boolean(workspace && routeQrAssets.length === requiredRouteQrCount && routeQrAssets.every((asset) => Boolean(asset.applied_at)))
  const packingReady = Boolean(
    workspace
    && workspace.packing_boxes.length > 0
    && workspace.unassigned_order_ids.length === 0
    && workspace.packing_boxes.every((box) => box.status === 'closed')
    && (workspace.supply.delivery_type !== 'pvz' || workspace.packing_boxes.every(
      (box) => Boolean(box.wb_trbx_id && box.qr_asset?.status === 'ready' && box.qr_asset.preview_url),
    )),
  )
  const deliveryStageUnlocked = Boolean(workspace && currentStage === 'packing' && packingReady)
  const maxReachableStageIndex = deliveryStageUnlocked
    ? Math.max(currentStageIndex, STAGES.findIndex((item) => item.key === 'delivery'))
    : currentStageIndex
  const stageIsCurrent = stage === currentStage || (stage === 'delivery' && deliveryStageUnlocked)
  const hasPendingAction = pendingActions.size > 0
  const requestedBoxCount = workspace ? Math.max(1, Math.min(workspace.orders.length, Number(cargoCount) || 1)) : 1

  return (
    <Dialog
      open={open}
      onClose={onClose}
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
          <IconButton onClick={onClose} aria-label="Закрыть">
            <CloseIcon />
          </IconButton>
        </Stack>
      </Box>

      <Tabs
        value={stage}
        onChange={(_, value) => {
          if (STAGES.findIndex((item) => item.key === value) <= maxReachableStageIndex) setStage(value)
          setError(null)
          setNotice(null)
        }}
        variant="scrollable"
        scrollButtons="auto"
        sx={{ px: 2, borderBottom: 1, borderColor: 'divider', bgcolor: 'rgba(91,33,182,.035)' }}
      >
        {STAGES.map((item, index) => (
          <Tab key={item.key} value={item.key} label={index < currentStageIndex ? `${item.label} ✓` : item.label} disabled={index > maxReachableStageIndex} />
        ))}
      </Tabs>

      {loadingWorkspace || hasPendingAction ? <LinearProgress /> : null}
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
                  <TableHead><TableRow><TableCell>Заказ WB</TableCell><TableCell>Товар</TableCell><TableCell align="right">Количество</TableCell><TableCell>Маркировка</TableCell><TableCell>Подбор</TableCell></TableRow></TableHead>
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
                        <TableCell align="right">1 шт.</TableCell>
                        <TableCell>{order.metadata.required.length ? order.metadata.required.join(', ') : 'Не требуется'}</TableCell>
                        <TableCell>{order.pick.status === 'picked' ? 'Подобран' : 'Ожидает'}</TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </Paper>
              <Stack direction="row" sx={{ justifyContent: 'flex-end' }}>
                <Button variant="contained" size="large" disabled={!stageIsCurrent || pendingActions.has('supply-start')} onClick={() => void run('supply-start', () => startFbsSupplyWork(token, authHeaders, workspace.supply.id), 'Задание создано. Можно начинать подбор.')} data-testid="fbs-start-work">
                  Начать работу с поставкой
                </Button>
              </Stack>
            </Stack>
          ) : null}

          {workspace && stage === 'picking' ? (
            <Stack spacing={2}>
              {!stageIsCurrent ? <Alert severity="success">Подбор завершён. Этот этап доступен только для просмотра.</Alert> : null}
              <Paper variant="outlined" sx={{ p: 2 }} data-testid="fbs-scanner-picking">
                <Typography variant="subtitle1" gutterBottom>Сканирование подбора</Typography>
                <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>Сначала отсканируйте ячейку, затем товар.</Typography>
                <Stack direction={{ xs: 'column', md: 'row' }} spacing={1.5}><TextField label="Штрихкод ячейки" value={locationBarcode} onChange={(e) => setLocationBarcode(e.target.value)} disabled={!stageIsCurrent || allPicked || pendingActions.has('scan-location')} onKeyDown={(e) => { if (e.key === 'Enter') void scanLocation() }} /><Button variant="outlined" onClick={() => void scanLocation()} disabled={!stageIsCurrent || allPicked || pendingActions.has('scan-location')} data-testid="fbs-scan-location">Подтвердить ячейку</Button><TextField label="Штрихкод товара" value={productBarcode} onChange={(e) => setProductBarcode(e.target.value)} disabled={!stageIsCurrent || !pickLocation || allPicked || pendingActions.has('scan-product')} onKeyDown={(e) => { if (e.key === 'Enter') void scanProduct() }} sx={{ flex: 1 }} /><Button variant="contained" onClick={() => void scanProduct()} disabled={!stageIsCurrent || !pickLocation || !productBarcode.trim() || allPicked || pendingActions.has('scan-product')} data-testid="fbs-scan-product">Подобрать товар</Button></Stack>
                {pickLocation ? <Alert severity="success" sx={{ mt: 2 }}>Ячейка {pickLocation.code} подтверждена · {pickLocation.warehouse_name}</Alert> : null}
              </Paper>
              <Paper variant="outlined" sx={{ overflow: 'hidden' }} data-testid="fbs-manual-picking">
                <Stack direction={{ xs: 'column', sm: 'row' }} spacing={1.5} sx={{ justifyContent: 'space-between', alignItems: { sm: 'flex-start' }, mb: 2 }}>
                  <Box sx={{ px: 2.5, pt: 2.5 }}><Typography variant="h6">Подбор из ячеек</Typography><Typography variant="body2" color="text.secondary">Снимите рассчитанное количество с указанной ячейки. Если нужны две ячейки, каждая показана отдельной строкой. Сканер для этого не требуется.</Typography></Box>
                  <Button sx={{ mt: 2.5, mr: 2.5 }} variant="outlined" startIcon={<PrintOutlinedIcon />} onClick={printPickingList} data-testid="fbs-pick-list-print">Печать листа подбора</Button>
                </Stack>
                <Table size="small">
                  <TableHead><TableRow><TableCell>Товар</TableCell><TableCell sx={{ width: 250 }}>Ячейка и количество</TableCell><TableCell sx={{ width: 150 }}>Выполнено</TableCell><TableCell align="right" sx={{ width: 280 }}>Действие</TableCell></TableRow></TableHead>
                  <TableBody>{manualPickingRows.map((row) => {
                    const actionKey = `manual-pick:${row.key}`
                    const undoOrder = row.pickedOrders.find((order) => order.pack.status !== 'packed')
                    return <TableRow key={row.key} data-testid={`fbs-manual-pick-${row.key}`}>
                      <TableCell><Stack direction="row" spacing={1.5} sx={{ alignItems: 'center' }}><ProductPhotoThumb src={row.imageUrl} alt={row.productName} size={52} previewSize={280} /><Box><Typography variant="body2" sx={{ fontWeight: 700 }}>{row.productName}</Typography><Typography variant="caption" color="text.secondary">{row.barcode ?? 'ШК не указан'}</Typography></Box></Stack></TableCell>
                      <TableCell>{row.location ? <Stack spacing={0.35}><Typography variant="body2" sx={{ fontWeight: 700 }}>{row.location.code}</Typography><Typography variant="body2" sx={{ fontWeight: 700 }} data-testid={`fbs-manual-pick-qty-${row.key}`}>К снятию: {row.pendingOrders.length} шт.</Typography><Typography variant="caption" color="text.secondary">Доступно в ячейке: {row.location.available_unpacked} шт.</Typography></Stack> : <Stack spacing={0.35}><Typography variant="body2" color="error.main">Нет доступной ячейки</Typography><Typography variant="body2" sx={{ fontWeight: 700 }}>К снятию: {row.pendingOrders.length} шт.</Typography></Stack>}</TableCell>
                      <TableCell><Typography variant="body2" sx={{ fontWeight: 700 }}>{row.productPicked} из {row.productRequired}</Typography>{row.pickedOrders.length ? <Typography variant="caption" color="text.secondary">В этой ячейке: {row.pickedOrders.length} шт.</Typography> : null}</TableCell>
                      <TableCell align="right"><Stack direction="row" spacing={0.5} sx={{ justifyContent: 'flex-end', flexWrap: 'wrap' }}>{row.pendingOrders.length ? <Button size="small" variant="contained" disabled={!stageIsCurrent || pendingActions.has(actionKey) || !row.location || !row.productId} onClick={() => void manualPickRow(row)} data-testid={`fbs-manual-pick-submit-${row.key}`}>Снять {row.pendingOrders.length} шт. с ячейки</Button> : <Chip size="small" color="success" label="Снято" />}{undoOrder ? <Button size="small" color="inherit" disabled={deliveryConfirmed || pendingActions.has(`pick-undo:${undoOrder.id}`)} onClick={() => setUndoOrderId(undoOrder.id)} data-testid={`fbs-pick-undo-${undoOrder.id}`}>Вернуть 1 шт. в ячейку</Button> : null}</Stack></TableCell>
                    </TableRow>
                  })}</TableBody>
                </Table>
                {allPicked ? <Alert severity="success" sx={{ m: 2 }}>Все товары подобраны. Можно переходить к упаковке.</Alert> : null}
              </Paper>
            </Stack>
          ) : null}

          {workspace && stage === 'packing' ? (
            <Stack spacing={2}>
              {!packingEditable ? <Alert severity="success">Поставка уже передана в WB. Упаковка доступна только для просмотра.</Alert> : null}
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
                      return <Stack spacing={0.75} sx={{ alignItems: 'flex-end' }}>{lineOrders.map((order) => <Box key={order.id} data-testid={`fbs-order-marking-${order.id}`}><Stack direction="row" spacing={0.5} sx={{ justifyContent: 'flex-end', alignItems: 'center', flexWrap: 'wrap' }}><Typography variant="caption" sx={{ fontWeight: 700 }}>WB №{order.wb_order_id}</Typography><FbsMarkingStatusChip required={order.metadata.required} states={order.metadata.states} /><FbsStickerStatusChip status={order.sticker.status} />{order.metadata.required.length ? <Button size="small" variant="outlined" disabled={!packingEditable || pendingActions.has(`metadata:${order.id}`)} onClick={() => { setMetadataOrderId(order.id); setMetadataKind(normalizeMetadataKind(order.metadata.required[0])); setMetadataValue(''); setMetadataDialogOpen(true) }} data-testid={`fbs-metadata-open-${order.id}`}>Ввести {metadataKindLabel(order.metadata.required[0]!)}</Button> : null}<Button size="small" variant="contained" startIcon={<PrintOutlinedIcon />} disabled={!packingEditable || pendingActions.has(`print-sticker:${order.id}:initial`)} onClick={() => void requestPrintBatch([order.id])} data-testid={`fbs-order-sticker-print-${order.id}`}>Стикер WB</Button></Stack></Box>)}</Stack>
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
              {printBatch ? <Paper variant="outlined" sx={{ p: 2 }}><Typography variant="body2">Готово: {printBatch.ready}{printBatch.missing ? ` · Не получено: ${printBatch.missing}` : ''}{printBatch.failed ? ` · Ошибок: ${printBatch.failed}` : ''}</Typography><Button variant="outlined" disabled={printBatch.ready === 0} sx={{ mt: 1 }} onClick={() => setPrintPreviewOpen(true)}>Открыть предпросмотр и печать</Button>{printBatch.missing ? <Button variant="text" disabled={!packingEditable || pendingActions.has('print-sticker:all:retry')} sx={{ mt: 1, ml: 1 }} onClick={() => void requestPrintBatch(undefined, true)}>Получить недостающие</Button> : null}{printBatch.order_errors.map((item) => <Alert key={item.order_id} severity="error" sx={{ mt: 1 }}>Заказ WB №{item.wb_order_id}: {item.message}</Alert>)}</Paper> : null}
            </Stack>
          ) : null}

          {workspace && stage === 'packing' ? (
            <Paper variant="outlined" sx={{ overflow: 'hidden' }} data-testid="fbs-packing-boxes">
              <Box sx={{ px: { xs: 2, md: 3 }, py: 2.5, borderBottom: 1, borderColor: 'divider' }}>
                <Stack direction={{ xs: 'column', sm: 'row' }} spacing={1.5} sx={{ justifyContent: 'space-between', alignItems: { sm: 'center' } }}>
                  <Box>
                    <Stack direction="row" spacing={1} sx={{ alignItems: 'center', mb: 0.5 }}>
                      <Typography variant="h6">Короба</Typography>
                      <Chip size="small" variant="outlined" label={workspace.supply.delivery_type === 'pvz' ? 'ПВЗ' : 'Склад / СЦ'} />
                    </Stack>
                    <Typography variant="body2" color="text.secondary">
                      Сначала упакуйте товары, затем распределите их по физическим коробам. Товар исчезает из списка после добавления в короб.
                    </Typography>
                  </Box>
                  <Stack direction="row" spacing={1} sx={{ alignItems: 'center' }}>
                    <TextField label="Количество коробов" type="number" size="small" value={cargoCount} onChange={(event) => setCargoCount(event.target.value)} disabled={pendingActions.has('box-create')} slotProps={{ htmlInput: { min: 1, max: workspace.orders.length } }} sx={{ width: 150 }} data-testid="fbs-box-count" />
                    <Button variant={workspace.packing_boxes.length ? 'outlined' : 'contained'} disabled={!packingEditable || pendingActions.has('box-create')} onClick={() => void createLocalPackingBoxes()} data-testid="fbs-boxes-create">{pendingActions.has('box-create') ? workspace.supply.delivery_type === 'pvz' ? 'Создаём короба и получаем QR…' : 'Создаём короба…' : workspace.packing_boxes.length ? requestedBoxCount === 1 ? 'Добавить короб' : `Добавить ${requestedBoxCount} ${boxesWord(requestedBoxCount)}` : `Создать ${requestedBoxCount} ${boxesWord(requestedBoxCount)}`}</Button>
                  </Stack>
                </Stack>
              </Box>
              {workspace.packing_boxes.length === 0 ? (
                <Box sx={{ p: { xs: 2, md: 3 } }}>
                  <Typography variant="subtitle1" sx={{ fontWeight: 700 }}>Создать физические короба</Typography>
                  <Typography variant="body2" color="text.secondary" sx={{ mt: 0.5, mb: 2 }}>
                    Для ПВЗ WMS одновременно запросит у WB отдельный QR для каждого короба. Для склада или СЦ короба останутся внутренними, без печати лишних кодов.
                  </Typography>
                  <Alert severity="info">Укажите количество в заголовке блока и создайте короба. После создания здесь появится распределение товаров.</Alert>
                </Box>
              ) : (
                <>
                  <Box sx={{ borderBottom: 1, borderColor: 'divider' }}>
                    <Box sx={{ px: { xs: 2, md: 3 }, pt: 2.5, pb: 1 }}><Typography variant="subtitle1" sx={{ fontWeight: 700 }}>Не распределено</Typography></Box>
                    {unassignedPackingGroups.length === 0 ? <Alert severity="success" sx={{ mx: { xs: 2, md: 3 }, mb: 2.5 }}>Все упакованные товары распределены по коробам.</Alert> : (
                      <TableContainer sx={{ overflowX: 'auto' }}><Table size="small" sx={{ minWidth: 820 }} data-testid="fbs-unassigned-box-items">
                        <TableHead><TableRow><TableCell>Товар</TableCell><TableCell>Осталось</TableCell><TableCell>Короб</TableCell><TableCell>Количество</TableCell><TableCell align="right">Действие</TableCell></TableRow></TableHead>
                        <TableBody>{unassignedPackingGroups.map((group) => {
                          const selectedOpenBox = openPackingBoxes.find((box) => box.id === packingBoxTargetByProduct[group.key])
                          return <TableRow key={group.key} data-testid={`fbs-unassigned-${group.key}`}>
                            <TableCell><Stack direction="row" spacing={1.25} sx={{ alignItems: 'center' }}><ProductPhotoThumb src={group.imageUrl} alt={group.name} size={44} previewSize={280} /><Box><Typography variant="body2" sx={{ fontWeight: 700 }}>{group.name}</Typography><Typography variant="caption" color="text.secondary">Заказы WB: {group.wbOrderIds.map((id) => `№${id}`).join(', ')}</Typography></Box></Stack></TableCell>
                            <TableCell>{group.orderIds.length} шт.</TableCell>
                            <TableCell><Select size="small" value={selectedOpenBox?.id ?? openPackingBoxes[0]?.id ?? ''} disabled={!packingEditable || pendingActions.has(`box-assign:${group.key}`) || openPackingBoxes.length === 0} onChange={(event) => setPackingBoxTargetByProduct((current) => ({ ...current, [group.key]: String(event.target.value) }))} inputProps={{ 'aria-label': `Короб для товара ${group.name}` }} sx={{ minWidth: 135 }}>{openPackingBoxes.map((box) => <MenuItem key={box.id} value={box.id}>Короб {box.box_number}</MenuItem>)}</Select></TableCell>
                            <TableCell><TextField size="small" type="number" value={packingBoxQtyByProduct[group.key] || '1'} onChange={(event) => setPackingBoxQtyByProduct((current) => ({ ...current, [group.key]: event.target.value }))} disabled={pendingActions.has(`box-assign:${group.key}`)} slotProps={{ htmlInput: { min: 1, max: group.orderIds.length, 'aria-label': `Количество товара ${group.name}` } }} sx={{ width: 95 }} /></TableCell>
                            <TableCell align="right"><Button variant="contained" size="small" disabled={!packingEditable || pendingActions.has(`box-assign:${group.key}`) || openPackingBoxes.length === 0} onClick={() => void assignPackingGroup(group)} data-testid={`fbs-box-assign-${group.key}`}>Положить в короб</Button></TableCell>
                          </TableRow>
                        })}</TableBody>
                      </Table></TableContainer>
                    )}
                    {unassignedPackingGroups.length > 0 && openPackingBoxes.length === 0 ? <Alert severity="warning" sx={{ mx: { xs: 2, md: 3 }, mb: 2.5 }}>Все короба закрыты. Откройте нужный короб повторно, чтобы продолжить распределение.</Alert> : null}
                  </Box>
                  <TableContainer sx={{ overflowX: 'auto' }}><Table size="small" sx={{ minWidth: 1120 }} data-testid="fbs-boxes-table">
                    <TableHead><TableRow><TableCell sx={{ width: 110 }}>Короб</TableCell><TableCell>Состав</TableCell><TableCell align="right" sx={{ width: 100 }}>Количество</TableCell><TableCell sx={{ width: 110 }}>Состояние</TableCell><TableCell sx={{ width: 190 }}>QR WB</TableCell><TableCell align="right" sx={{ width: 330 }}>Действия</TableCell></TableRow></TableHead>
                    <TableBody>{workspace.packing_boxes.map((box) => (
                      <TableRow key={box.id} data-testid={`fbs-box-${box.id}`}>
                        <TableCell><Typography variant="subtitle2">Короб {box.box_number}</Typography></TableCell>
                        <TableCell>{box.orders.length ? <Stack spacing={0.75}>{box.orders.map((item) => <Stack key={item.id} direction="row" spacing={1} sx={{ alignItems: 'center', justifyContent: 'space-between' }}><Stack direction="row" spacing={1} sx={{ alignItems: 'center', minWidth: 0 }}><ProductPhotoThumb src={item.image_url} alt={item.product_name} size={40} previewSize={280} /><Box sx={{ minWidth: 0 }}><Typography variant="body2" sx={{ fontWeight: 700 }}>{item.product_name}</Typography><Typography variant="caption" color="text.secondary">Заказ WB №{item.wb_order_id} · {item.quantity} шт.</Typography></Box></Stack><Button size="small" color="inherit" disabled={!packingEditable || pendingActions.has(`box-unassign:${item.id}`) || box.status === 'closed'} onClick={() => void unassignPackingBoxOrder(box.id, item.id)} data-testid={`fbs-box-unassign-${item.id}`}>Убрать</Button></Stack>)}</Stack> : <Typography variant="body2" color="text.secondary">Короб пуст</Typography>}</TableCell>
                        <TableCell align="right">{box.items_count}</TableCell>
                        <TableCell><Chip size="small" variant="outlined" color={box.status === 'closed' ? 'success' : 'default'} label={box.status === 'closed' ? 'Закрыт' : 'Открыт'} /></TableCell>
                        <TableCell>{workspace.supply.delivery_type === 'pvz' ? <Stack spacing={0.5} sx={{ alignItems: 'flex-start' }}>{box.wb_trbx_id ? <Typography variant="caption" color="text.secondary">WB ID: {box.wb_trbx_id}</Typography> : null}{box.qr_asset?.status === 'ready' && box.qr_asset.preview_url ? <><Chip size="small" color="success" label="QR готов" /><Button size="small" startIcon={<PrintOutlinedIcon />} onClick={() => box.qr_asset && openAssetPreview([box.qr_asset])} data-testid={`fbs-box-qr-print-${box.id}`}>Печать QR</Button></> : box.wb_trbx_id ? <><Typography variant="caption" color="error.main" sx={{ fontWeight: 700 }}>Короб создан, QR получить не удалось</Typography>{box.qr_asset?.error?.message ? <Typography variant="caption" color="text.secondary">{box.qr_asset.error.message}</Typography> : null}<Button size="small" disabled={pendingActions.has(`box-qr:${box.id}`)} onClick={() => void retryPackingBoxQr(box.id)} data-testid={`fbs-box-qr-retry-${box.id}`}>Получить QR повторно</Button></> : <Typography variant="caption" color="error.main">Грузоместо WB не создано</Typography>}</Stack> : <Chip size="small" variant="outlined" label="Не требуется" />}</TableCell>
                        <TableCell align="right"><Stack direction="row" spacing={0.5} sx={{ justifyContent: 'flex-end', flexWrap: 'wrap' }}>
                          {box.status === 'closed' ? <Button size="small" variant="outlined" disabled={!packingEditable || pendingActions.has(`box-reopen:${box.id}`)} onClick={() => void changePackingBoxState(box.id, 'reopen')} data-testid={`fbs-box-reopen-${box.id}`}>Открыть повторно</Button> : <Button size="small" variant="outlined" disabled={!packingEditable || pendingActions.has(`box-close:${box.id}`) || box.items_count === 0} onClick={() => void changePackingBoxState(box.id, 'close')} data-testid={`fbs-box-close-${box.id}`}>Закрыть</Button>}
                          <Button size="small" color="inherit" disabled={!packingEditable || box.status === 'closed' || box.items_count === 0} onClick={() => setPackingBoxClearTarget(box.id)} data-testid={`fbs-box-clear-${box.id}`}>Очистить</Button>
                          <IconButton size="small" color="error" aria-label={`Удалить короб ${box.box_number}`} disabled={!packingEditable || box.status === 'closed' || box.items_count > 0} onClick={() => setPackingBoxDeleteTarget(box.id)} data-testid={`fbs-box-delete-${box.id}`}><DeleteOutlinedIcon fontSize="small" /></IconButton>
                        </Stack></TableCell>
                      </TableRow>
                    ))}</TableBody>
                  </Table></TableContainer>
                  <Box sx={{ px: { xs: 2, md: 3 }, py: 2 }}>
                    {packingReady ? <Stack direction={{ xs: 'column', sm: 'row' }} spacing={2} sx={{ alignItems: { sm: 'center' }, justifyContent: 'space-between' }}><Alert severity="success" data-testid="fbs-packing-ready">Все товары распределены, короба закрыты{workspace.supply.delivery_type === 'pvz' ? ', QR коробов получены' : ''}. Поставка готова к сдаче.</Alert><Button variant="contained" size="large" onClick={() => setStage('delivery')} data-testid="fbs-go-delivery">Перейти к сдаче</Button></Stack> : <Typography variant="body2" color="text.secondary">Для перехода к сдаче создайте короба, распределите все товары и закройте каждый короб{workspace.supply.delivery_type === 'pvz' ? ', затем получите QR WB для каждого короба' : ''}.</Typography>}
                  </Box>
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
                      <Typography variant="h6">Проверка перед сдачей</Typography>
                      <Stack direction="row" spacing={1} sx={{ mt: 1, flexWrap: 'wrap' }} useFlexGap>
                        <Chip size="small" variant="outlined" label={`Маршрут: ${workspace.supply.delivery_type === 'pvz' ? 'ПВЗ' : 'Склад / СЦ'}`} />
                        <Chip size="small" variant="outlined" label={`Заказов: ${workspace.orders.length}`} />
                        <Chip size="small" variant="outlined" label={`Физических коробов: ${workspace.packing_boxes.length}`} />
                      </Stack>
                      <Typography variant="body2" color="text.secondary" sx={{ mt: 0.5 }}>
                        Проверьте упаковку, маркировку и закрытие коробов. Передача в WB выполняется отдельным подтверждённым действием.
                      </Typography>
                    </Box>
                    <Button variant="contained" size="large" disabled={!stageIsCurrent || pendingActions.has('delivery-check')} onClick={() => void checkDelivery()} data-testid="fbs-delivery-prepare">
                      Проверить готовность
                    </Button>
                  </Stack>
                  {deliveryPreflight ? <Stack spacing={1} sx={{ mt: 2 }}>{deliveryPreflight.checks.map((check) => <Alert key={`${check.code}-${check.order_id ?? ''}`} severity={check.ok ? 'success' : 'error'}>{check.message}</Alert>)}{deliveryPreflight.can_deliver ? <Stack direction="row" sx={{ justifyContent: 'flex-end', pt: 1 }}><Button variant="contained" size="large" disabled={pendingActions.has('delivery-submit')} onClick={() => setDeliveryConfirmOpen(true)} data-testid="fbs-delivery-confirm-open">Передать поставку в WB</Button></Stack> : null}</Stack> : null}
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
                      data-testid="fbs-supply-qr-print"
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
                    <Button variant="contained" size="large" startIcon={<PrintOutlinedIcon />} disabled={!allRouteQrReady} onClick={() => openAssetPreview(routeQrAssets)} data-testid="fbs-all-box-qr-print">
                      Печать всех QR коробов
                    </Button>
                  </Stack>
                  <Stack direction="row" spacing={1} sx={{ mt: 2, flexWrap: 'wrap' }} useFlexGap>
                    {workspace.packing_boxes.map((box) => (
                      <Chip
                        key={box.id}
                        size="small"
                        color={box.qr_asset?.applied_at ? 'success' : box.qr_asset?.preview_url ? 'warning' : 'error'}
                        label={`Короб ${box.box_number}: ${box.qr_asset?.applied_at ? 'QR нанесён' : box.qr_asset?.preview_url ? 'готов к печати' : 'QR не получен'}`}
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
                      disabled={pendingActions.has('supply-qr-retry')}
                      data-testid="fbs-supply-qr-retry"
                      onClick={() => void run('supply-qr-retry', () => retryFbsSupplyQr(token, authHeaders, workspace.supply.id), 'QR поставки получен.')}
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
                    <Button variant="contained" size="large" disabled={!stageIsCurrent || pendingActions.has('local-finish') || !allRouteQrApplied} onClick={() => void finishLocalWork()} data-testid="fbs-local-finish">
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
      <Dialog open={metadataDialogOpen} onClose={pendingActions.has(`metadata:${metadataOrderId}`) ? undefined : () => setMetadataDialogOpen(false)} maxWidth="sm" fullWidth data-testid="fbs-marking-dialog">
        <DialogTitle>Маркировка заказа WB{metadataOrder ? ` №${metadataOrder.wb_order_id}` : ''}</DialogTitle>
        <DialogContent>
          <Stack spacing={2} sx={{ pt: 1 }}>
            {metadataOrder ? <Stack direction="row" spacing={1.25} sx={{ alignItems: 'center' }}><ProductPhotoThumb src={metadataOrder.product.image_url} alt={metadataOrder.product.name} size={48} previewSize={280} /><Box><Typography variant="body2" sx={{ fontWeight: 700 }}>{metadataOrder.product.name}</Typography><Typography variant="caption" color="text.secondary">Введите обязательный {metadataKindLabel(metadataKind)} для проверки.</Typography></Box></Stack> : null}
            <Stack direction={{ xs: 'column', sm: 'row' }} spacing={1.5} sx={{ alignItems: { sm: 'center' } }}>
              <Chip label={metadataKindLabel(metadataKind)} />
              <TextField autoFocus fullWidth label={`Сканированный ${metadataKindLabel(metadataKind)}`} value={metadataValue} onChange={(event) => setMetadataValue(event.target.value)} disabled={pendingActions.has(`metadata:${metadataOrderId}`)} onKeyDown={(event) => { if (event.key === 'Enter' && metadataValue.length > 0) void scanMetadata() }} slotProps={{ htmlInput: { 'data-testid': metadataOrderId ? `fbs-metadata-input-${metadataOrderId}` : 'fbs-metadata-input' } }} />
            </Stack>
          </Stack>
        </DialogContent>
        <DialogActions><Button onClick={() => setMetadataDialogOpen(false)} disabled={pendingActions.has(`metadata:${metadataOrderId}`)}>Отмена</Button><Button variant="contained" onClick={() => void scanMetadata()} disabled={pendingActions.has(`metadata:${metadataOrderId}`) || !metadataOrderId || metadataValue.length === 0} data-testid={metadataOrderId ? `fbs-metadata-submit-${metadataOrderId}` : 'fbs-metadata-submit'}>Проверить</Button></DialogActions>
      </Dialog>
      <Dialog open={Boolean(undoOrderId)} onClose={() => setUndoOrderId(null)} maxWidth="xs" fullWidth>
        <DialogTitle>Отменить подбор?</DialogTitle>
        <DialogContent><Typography>Товар будет возвращён в исходную ячейку. Отменяйте только если в подборе действительно ошибка.</Typography></DialogContent>
        <DialogActions><Button onClick={() => setUndoOrderId(null)}>Не отменять</Button><Button color="error" variant="contained" onClick={undoPickedOrder}>Вернуть в ячейку</Button></DialogActions>
      </Dialog>
      <Dialog open={Boolean(packingBoxClearTarget)} onClose={packingBoxClearTarget && pendingActions.has(`box-clear:${packingBoxClearTarget}`) ? undefined : () => setPackingBoxClearTarget(null)} maxWidth="xs" fullWidth>
        <DialogTitle>Очистить короб?</DialogTitle>
        <DialogContent><Alert severity="warning">Все товары из короба вернутся в список нераспределённых. Сам короб останется.</Alert></DialogContent>
        <DialogActions><Button onClick={() => setPackingBoxClearTarget(null)} disabled={Boolean(packingBoxClearTarget && pendingActions.has(`box-clear:${packingBoxClearTarget}`))}>Не очищать</Button><Button color="error" variant="contained" onClick={() => void clearLocalPackingBox()} disabled={Boolean(packingBoxClearTarget && pendingActions.has(`box-clear:${packingBoxClearTarget}`))} data-testid="fbs-box-clear-confirm">Очистить короб</Button></DialogActions>
      </Dialog>
      <Dialog open={Boolean(packingBoxDeleteTarget)} onClose={packingBoxDeleteTarget && pendingActions.has(`box-delete:${packingBoxDeleteTarget}`) ? undefined : () => setPackingBoxDeleteTarget(null)} maxWidth="xs" fullWidth>
        <DialogTitle>Удалить пустой короб?</DialogTitle>
        <DialogContent>
          <Alert severity="warning">Удалить можно только пустой короб. Если внутри есть товары, сначала уберите их из короба.</Alert>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setPackingBoxDeleteTarget(null)} disabled={Boolean(packingBoxDeleteTarget && pendingActions.has(`box-delete:${packingBoxDeleteTarget}`))}>Не удалять</Button>
          <Button color="error" variant="contained" onClick={() => void deleteLocalPackingBox()} disabled={Boolean(packingBoxDeleteTarget && pendingActions.has(`box-delete:${packingBoxDeleteTarget}`))} data-testid="fbs-box-delete-confirm">Удалить короб</Button>
        </DialogActions>
      </Dialog>
      <Dialog open={deliveryConfirmOpen} onClose={() => setDeliveryConfirmOpen(false)} maxWidth="sm" fullWidth>
        <DialogTitle>Передать поставку в WB?</DialogTitle>
        <DialogContent>{workspace ? <Stack spacing={1} data-testid="fbs-delivery-summary"><Typography>Поставка: {workspace.supply.name}</Typography><Typography>Селлер: {workspace.supply.seller.name}</Typography><Typography>Маршрут: {workspace.supply.delivery_type === 'pvz' ? 'ПВЗ' : 'Склад / СЦ'}</Typography><Typography>Заказов: {workspace.orders.length} · физических коробов: {workspace.packing_boxes.length}</Typography><Alert severity="warning">После передачи в WB нельзя менять состав и распределение по коробам. QR, обязательный для маршрута, появится на этом же экране до локального завершения работы.</Alert></Stack> : null}</DialogContent>
        <DialogActions><Button onClick={() => setDeliveryConfirmOpen(false)} disabled={pendingActions.has('delivery-submit')}>Отмена</Button><Button variant="contained" disabled={pendingActions.has('delivery-submit')} onClick={() => void deliver()} data-testid="fbs-delivery-confirm">Передать в WB</Button></DialogActions>
      </Dialog>
    </Dialog>
  )
}
