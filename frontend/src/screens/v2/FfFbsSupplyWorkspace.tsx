import { useCallback, useEffect, useMemo, useState, type MouseEvent } from 'react'
import {
  Alert,
  Box,
  Button,
  CircularProgress,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  Divider,
  IconButton,
  LinearProgress,
  Menu,
  MenuItem,
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
  Tooltip,
  Typography,
} from '@mui/material'
import CloseIcon from '@mui/icons-material/Close'
import DeleteOutlinedIcon from '@mui/icons-material/DeleteOutlined'
import LocalShippingOutlinedIcon from '@mui/icons-material/LocalShippingOutlined'
import MoreVertOutlinedIcon from '@mui/icons-material/MoreVertOutlined'
import PrintOutlinedIcon from '@mui/icons-material/PrintOutlined'
import { apiUrl } from '../../api'
import { ProductPhotoThumb } from '../../components/ProductPhotoThumb'
import { type PackagingTask, type PackagingTaskLine } from '../ff/FfPackagingPage'
import { useMarkingCodePrint } from '../../utils/useMarkingCodePrint'
import { readApiErrorMessage } from '../../utils/readApiErrorMessage'
import type { ProductThermalLabelData } from '../../utils/printProductThermalLabel'
import { FbsKizScanDialog } from './FbsKizScanDialog'
import { FbsPrintPreviewDialog } from './FbsPrintPreviewDialog'
import { buildFbsPickingListPrintHtml, ordersWord } from './fbsUx'
import {
  confirmFbsPrintApplied,
  confirmFbsManualPick,
  assignFbsPackingBoxOrders,
  clearFbsPackingBox,
  createFbsPackingBoxes,
  createFbsIdempotencyKey,
  deleteFbsOrderKiz,
  deleteFbsPackingBox,
  deliverFbsSupply,
  FbsApiError,
  fetchFbsPrintBatch,
  fetchFbsWorkspace,
  printFbsOrderTape,
  removeFbsPackingBoxOrder,
  retryFbsPackingBoxQr,
  retryFbsSupplyQr,
  scanFbsPickLocation,
  scanFbsPickProduct,
  selectFbsManualPickLocation,
  startFbsSupplyWork,
  undoFbsPick,
  type FbsOrderPrintTapeRequest,
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
  { key: 'boxes', label: 'Короба' },
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
  if (stage === 'handoff_prep' || stage === 'delivery' || stage === 'tracking') return 'boxes'
  return stage
}

const MARKING_ACCEPTED_STATUSES = ['accepted', 'assigned', 'pending', 'allowed_without_check', 'ok']
const STICKER_PRINTED_STATUSES = ['print_opened', 'applied']

function isOrderMarkingReady(order: FbsWorkspace['orders'][number]) {
  if (order.metadata.required.length === 0) return true
  const accepted = order.metadata.states.filter((state) => MARKING_ACCEPTED_STATUSES.includes(state.status))
  return accepted.length >= order.metadata.required.length
}

// КИЗ, внесённый оператором со стикера, — в отличие от напечатанного нами из пула.
function hasOperatorKiz(order: FbsWorkspace['orders'][number]) {
  return order.metadata.states.some(
    (state) =>
      state.kind === 'sgtin' &&
      state.source === 'operator' &&
      state.status !== 'missing' &&
      state.status !== 'rejected',
  )
}

function productLabelFromOrder(order: FbsWorkspace['orders'][number]): ProductThermalLabelData {
  return {
    product_name: order.product.name,
    sku_code: order.product.seller_article ?? `WB-${order.wb_order_id}`,
    wb_vendor_code: order.product.seller_article,
    wb_size: order.product.size,
    barcode: order.product.barcode ?? '',
  }
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
  const [printBatch, setPrintBatch] = useState<FbsPrintBatch | null>(null)
  const [printPreviewOpen, setPrintPreviewOpen] = useState(false)
  const [packagingTask, setPackagingTask] = useState<PackagingTask | null>(null)
  const [manualPickLocationRows, setManualPickLocationRows] = useState<Record<string, string[]>>({})
  const [boxCount, setBoxCount] = useState('1')
  const [boxAssignTarget, setBoxAssignTarget] = useState<string | null>(null)
  const [boxProductSearch, setBoxProductSearch] = useState('')
  const [boxProductQty, setBoxProductQty] = useState<Record<string, string>>({})
  const [boxMenu, setBoxMenu] = useState<{ boxId: string; anchorEl: HTMLElement } | null>(null)
  const [expandedBoxIds, setExpandedBoxIds] = useState<Set<string>>(() => new Set())
  const [deliveryKey, setDeliveryKey] = useState(createFbsIdempotencyKey)
  const [deliverySubmitted, setDeliverySubmitted] = useState(false)
  const [undoOrderId, setUndoOrderId] = useState<string | null>(null)
  const [retryAction, setRetryAction] = useState<(() => void) | null>(null)
  const [tzLine, setTzLine] = useState<PackagingTaskLine | null>(null)
  const [reprintMenu, setReprintMenu] = useState<{ orderId: string; anchorEl: HTMLElement } | null>(null)
  const [kizOpen, setKizOpen] = useState(false)
  const [kizUndoOrderId, setKizUndoOrderId] = useState<string | null>(null)
  const { openPrint, dialog: markingPrintDialog } = useMarkingCodePrint()

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
    setPrintBatch(null)
    setPickLocation(null)
    setManualPickLocationRows({})
    setBoxCount('1')
    setBoxAssignTarget(null)
    setBoxProductSearch('')
    setBoxProductQty({})
    setBoxMenu(null)
    setExpandedBoxIds(new Set())
    setDeliverySubmitted(false)
    setUndoOrderId(null)
    setTzLine(null)
    setReprintMenu(null)
    if (!initialWorkspace) void load()
  }, [open, supplyId, initialWorkspace, load])

  useEffect(() => {
    setNotice(null)
  }, [workspace?.stage])

  useEffect(() => {
    if (!open || !supplyId || !['picking', 'boxes'].includes(stage)) return
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
      '',
    )
    if (next) clearPersistentOperationKey(workspace.supply.id, 'box-create', String(count))
  }

  const assignBoxOrders = async () => {
    if (!workspace || !boxAssignTarget || boxAssignSelectedOrderIds.length === 0) return
    const next = await run(
      () => assignFbsPackingBoxOrders(token, authHeaders, workspace.supply.id, boxAssignTarget, boxAssignSelectedOrderIds),
      '',
    )
    if (next) {
      setBoxAssignTarget(null)
      setBoxProductSearch('')
      setBoxProductQty({})
      setExpandedBoxIds((current) => new Set(current).add(boxAssignTarget))
      setStage('boxes')
    }
  }

  const removeBoxOrders = async (boxId: string, orderIds: string[]) => {
    if (!workspace || orderIds.length === 0) return
    await run(
      async () => {
        let next = workspace
        for (const orderId of orderIds) {
          next = await removeFbsPackingBoxOrder(token, authHeaders, workspace.supply.id, boxId, orderId)
        }
        return next
      },
      '',
    )
  }

  const clearBox = async (boxId: string) => {
    if (!workspace) return
    setBoxMenu(null)
    await run(
      () => clearFbsPackingBox(token, authHeaders, workspace.supply.id, boxId),
      '',
    )
  }

  const deleteBox = async (boxId: string) => {
    if (!workspace) return
    setBoxMenu(null)
    const key = persistentOperationKey(workspace.supply.id, 'box-delete', boxId)
    const next = await run(
      () => deleteFbsPackingBox(token, authHeaders, workspace.supply.id, boxId, key),
      '',
    )
    if (next) {
      clearPersistentOperationKey(workspace.supply.id, 'box-delete', boxId)
      setExpandedBoxIds((current) => {
        const nextIds = new Set(current)
        nextIds.delete(boxId)
        return nextIds
      })
    }
  }

  const retryBoxQr = async (boxId: string) => {
    if (!workspace) return
    const next = await run(
      () => retryFbsPackingBoxQr(token, authHeaders, workspace.supply.id, boxId),
      '',
    )
    if (!next) return
    setStage('boxes')
    const box = next.boxes.find((item) => item.id === boxId)
    if (box?.qr_asset?.preview_url) openAssetPreview([box.qr_asset])
  }

  const deliver = async () => {
    if (!workspace || deliveryConfirmed) return
    const next = await run(
      () =>
        deliverFbsSupply(token, authHeaders, workspace.supply.id, {
          idempotency_key: deliveryKey,
        }),
      '',
    )
    if (next) {
      clearPersistentOperationKey(workspace.supply.id, 'delivery')
      setDeliveryKey(createFbsIdempotencyKey())
      setDeliverySubmitted(true)
      setStage('boxes')
    }
  }

  const refreshPackagingTask = useCallback(async () => {
    const taskId = workspace?.supply.packaging_task_id
    if (!taskId) return
    try {
      const response = await fetch(apiUrl(`/operations/packaging-tasks/${taskId}`), { headers: { ...authHeaders(token) } })
      if (response.ok) setPackagingTask((await response.json()) as PackagingTask)
    } catch {
      // Обновление задания не критично: следующая загрузка workspace синхронизирует состояние.
    }
    await load(true)
  }, [workspace?.supply.packaging_task_id, token, authHeaders, load])

  const requiresOrderHonestSign = (order: FbsWorkspace['orders'][number]) => {
    const line = order.product.id ? packLineByProduct.get(order.product.id) : undefined
    return Boolean(line?.requires_honest_sign || order.metadata.required.includes('sgtin'))
  }

  const markingAvailableForOrders = (orders: Array<FbsWorkspace['orders'][number]>) => {
    const seen = new Set<string>()
    let total = 0
    for (const order of orders) {
      if (!requiresOrderHonestSign(order) || !order.product.id || seen.has(order.product.id)) continue
      seen.add(order.product.id)
      total += packLineByProduct.get(order.product.id)?.marking_available_count ?? 0
    }
    return total
  }

  const openBulkOrderMarkingPrint = (orders: Array<FbsWorkspace['orders'][number]>, reprint = false) => {
    if (!workspace || orders.length === 0) return
    const firstOrder = orders[0]
    const firstLine = firstOrder?.product.id ? packLineByProduct.get(firstOrder.product.id) : undefined
    if (!firstOrder || !firstOrder.product.id) return
    const anyHonestSign = orders.some(requiresOrderHonestSign)
    const tapeOrders = orders.map((order) => ({
      orderId: order.id,
      wbOrderId: order.wb_order_id,
      requiresHonestSign: requiresOrderHonestSign(order),
      productLabel: productLabelFromOrder(order),
    }))
    openPrint(
      {
        token,
        productId: firstOrder.product.id,
        documentNumber: workspace.supply.name,
        qtyNeedPack: anyHonestSign ? tapeOrders.filter((order) => order.requiresHonestSign).length : tapeOrders.length,
        markingAvailable: markingAvailableForOrders(orders),
        qtyMarkingPrinted: orders.filter(orderPrintDone).length,
        requiresHonestSign: anyHonestSign,
        skuCode: firstLine?.sku_code ?? firstOrder.product.seller_article ?? `WB-${firstOrder.wb_order_id}`,
        productName: workspace.supply.name,
        productLabel: productLabelFromOrder(firstOrder),
        fbsTape: {
          orders: tapeOrders,
          includeOrderQr: true,
          print: ({ layout, allowPartial, reprint: printReprint }) => {
            const body: FbsOrderPrintTapeRequest = {
              order_ids: orders.map((order) => order.id),
              layout_json: layout,
              allow_partial: allowPartial,
              include_order_qr: true,
              reprint: printReprint,
            }
            return printFbsOrderTape(token, authHeaders, workspace.supply.id, body)
          },
          confirmQrApplied: async (asset) => {
            await confirmFbsPrintApplied(token, authHeaders, asset.id, createFbsIdempotencyKey())
          },
        },
        onPrinted: () => { void refreshPackagingTask() },
      },
      { reprint },
    )
  }

  /** Печать ЧЗ и ШК заказа через стандартный конструктор системы. */
  const openOrderMarkingPrint = (order: FbsWorkspace['orders'][number], line: PackagingTaskLine, reprint = false) => {
    if (!workspace) return
    openPrint(
      {
        token,
        lineId: line.id,
        productId: line.product_id,
        documentNumber: workspace?.supply.name ?? null,
        qtyNeedPack: requiresOrderHonestSign(order) ? 1 : 0,
        markingAvailable: requiresOrderHonestSign(order) ? line.marking_available_count : 0,
        qtyMarkingPrinted: orderPrintDone(order) ? 1 : 0,
        requiresHonestSign: requiresOrderHonestSign(order),
        skuCode: line.sku_code,
        productName: line.product_name,
        packagingInstructions: line.packaging_instructions,
        productLabel: productLabelFromOrder(order),
        fbsTape: {
          orders: [{
            orderId: order.id,
            wbOrderId: order.wb_order_id,
            requiresHonestSign: requiresOrderHonestSign(order),
            productLabel: productLabelFromOrder(order),
          }],
          includeOrderQr: false,
          print: ({ layout, allowPartial, reprint: printReprint }) => {
            const body: FbsOrderPrintTapeRequest = {
              order_ids: [order.id],
              layout_json: layout,
              allow_partial: allowPartial,
              include_order_qr: false,
              reprint: printReprint,
            }
            return printFbsOrderTape(token, authHeaders, workspace.supply.id, body)
          },
          confirmQrApplied: async (asset) => {
            await confirmFbsPrintApplied(token, authHeaders, asset.id, createFbsIdempotencyKey())
          },
        },
        onPrinted: () => { void refreshPackagingTask() },
      },
      { reprint },
    )
  }

  /** Одно действие вместо подтверждения упаковки на каждом товаре. */
  const packEverything = async () => {
    if (!packagingTask) return
    setBusy(true)
    setError(null)
    setNotice(null)
    try {
      let current = packagingTask
      for (const line of current.lines) {
        const remaining = line.qty_need_pack - line.qty_packed_in_task
        if (remaining <= 0) continue
        const response = await fetch(apiUrl(`/operations/packaging-tasks/${current.id}/lines/${line.id}/pack`), {
          method: 'POST',
          headers: { ...authHeaders(token), 'Content-Type': 'application/json' },
          body: JSON.stringify({ quantity: remaining }),
        })
        if (!response.ok) {
          setError(await readApiErrorMessage(response))
          return
        }
        current = ((await response.json()) as { packaging_task: PackagingTask }).packaging_task
      }
      const done = await fetch(apiUrl(`/operations/packaging-tasks/${current.id}/complete`), {
        method: 'POST',
        headers: { ...authHeaders(token), 'Content-Type': 'application/json' },
        body: JSON.stringify({ acknowledge_all_packed: false }),
      })
      if (!done.ok) {
        setError(await readApiErrorMessage(done))
        return
      }
      setPackagingTask((await done.json()) as PackagingTask)
      setNotice('Упаковка завершена.')
      await load()
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'Не удалось завершить упаковку.')
    } finally {
      setBusy(false)
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
      stickerCodes: Array<string | null>
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
        stickerCodes: [],
        marking: order.metadata.required.length ? order.metadata.required.join(', ') : 'Не требуется',
        nearestDeadline: order.deadline_at,
      }
      current.required += 1
      if (order.pick.status === 'picked') current.picked += 1
      current.wbOrders.push(order.wb_order_id)
      current.stickerCodes.push(order.sticker.code)
      const locations = order.inventory.locations
        .filter((location) => location.available_unpacked > 0)
        .map((location) => `${location.code}: ${location.available_unpacked}`)
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
        if (location.available_unpacked <= 0) continue
        const current = locations.get(location.id)
        if (!current || location.available_unpacked > current.available) {
          locations.set(location.id, { id: location.id, code: location.code, available: location.available_unpacked })
        }
      }
      const sortedLocations = [...locations.values()].sort((a, b) => a.code.localeCompare(b.code))
      if (sortedLocations.length === 0) return []
      const autoLocationIds: string[] = []
      let remainingOrders = orders.length
      for (const location of sortedLocations) {
        if (remainingOrders <= 0) break
        autoLocationIds.push(location.id)
        remainingOrders -= Math.min(location.available, remainingOrders)
      }
      const validLocationIds = new Set(sortedLocations.map((location) => location.id))
      const configuredLocationIds = manualPickLocationRows[productId]
      const manualDistribution = Boolean(configuredLocationIds)
      const selectedLocationIds = (configuredLocationIds ?? autoLocationIds).filter((locationId, index, list) =>
        validLocationIds.has(locationId) && list.indexOf(locationId) === index,
      )
      if (selectedLocationIds.length === 0) selectedLocationIds.push(sortedLocations[0].id)
      let orderIndex = 0
      return selectedLocationIds.flatMap((locationId, rowIndex) => {
        const location = sortedLocations.find((item) => item.id === locationId) ?? sortedLocations[0]
        const remainingForRows = orders.length - orderIndex
        if (remainingForRows <= 0) return []
        const laterRows = selectedLocationIds.length - rowIndex - 1
        const maxForThisRow = manualDistribution
          ? Math.max(1, remainingForRows - laterRows)
          : remainingForRows
        const count = Math.min(location.available, maxForThisRow)
        if (count <= 0) return []
        const orderIds = orders.slice(orderIndex, orderIndex + count).map((order) => order.id)
        orderIndex += count
        const selectedByOtherRows = new Set(selectedLocationIds.filter((_, index) => index !== rowIndex))
        const locationOptions = sortedLocations.filter((item) => item.id === location.id || !selectedByOtherRows.has(item.id))
        const nextLocation = sortedLocations.find((item) => !selectedLocationIds.includes(item.id))
        const canAddLocationRow =
          rowIndex === selectedLocationIds.length - 1 &&
          selectedLocationIds.length < Math.min(orders.length, sortedLocations.length)
        return [{
          productId,
          rowIndex,
          selectedLocationIds,
          location,
          locationOptions,
          nextLocationId: canAddLocationRow ? nextLocation?.id ?? null : null,
          orderIds,
          product: orders[0].product,
          identifiers: [orders[0].product.seller_article, orders[0].product.barcode].filter(Boolean).join(' · '),
        }]
      })
    })
  }, [manualPickLocationRows, workspace])
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
  const packLineByProduct = useMemo(() => {
    const map = new Map<string, PackagingTaskLine>()
    for (const line of packagingTask?.lines ?? []) map.set(line.product_id, line)
    return map
  }, [packagingTask])

  /** Строка упаковки — один заказ. Заказы одного товара идут подряд. */
  const packingOrders = useMemo(() => {
    if (!workspace) return []
    return [...workspace.orders].sort((a, b) => {
      const byName = a.product.name.localeCompare(b.product.name, 'ru')
      if (byName !== 0) return byName
      return a.wb_order_id - b.wb_order_id
    })
  }, [workspace])

  const orderPrintDone = useCallback(
    (order: FbsWorkspace['orders'][number]) =>
      STICKER_PRINTED_STATUSES.includes(order.sticker.status) && isOrderMarkingReady(order),
    [],
  )

  const printedOrdersCount = packingOrders.filter(orderPrintDone).length
  const unprintedPackingOrders = packingOrders.filter((order) => !orderPrintDone(order))
  const markingShortOrderIds = new Set(workspace?.marking_pool?.orders_without_code ?? [])

  const stageBlockers = useMemo(() => {
    if (stage === 'packing') {
      return workspace?.blockers.filter((blocker) => blocker.stage === 'packing' || blocker.stage === 'order_stickers') ?? []
    }
    if (stage === 'boxes') {
      return []
    }
    const backendStage = stage
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
  const assignedBoxOrderIds = new Set(workspace?.boxes.flatMap((box) => box.assigned_order_ids) ?? [])
  const availableForBox = (workspace?.orders ?? []).filter(
    (order) => order.pack.status === 'packed' && !assignedBoxOrderIds.has(order.id),
  )
  const boxAssignName = workspace?.boxes.find((box) => box.id === boxAssignTarget)?.box_number
  const reprintOrder = workspace?.orders.find((order) => order.id === reprintMenu?.orderId) ?? null
  const reprintLine = reprintOrder?.product.id ? packLineByProduct.get(reprintOrder.product.id) : undefined
  const boxMenuBox = workspace?.boxes.find((box) => box.id === boxMenu?.boxId) ?? null
  const boxMenuAssignedCount = boxMenuBox?.assigned_order_ids.length ?? 0
  const boxRouteLabel = workspace?.supply.delivery_type === 'pvz' ? 'ПВЗ' : 'Склад / СЦ'
  const boxDistributedCount = assignedBoxOrderIds.size
  const boxTotalCount = workspace?.progress.total ?? 0
  const boxRemainingCount = Math.max(0, boxTotalCount - boxDistributedCount)
  const supplyQrAsset = workspace?.supply.barcode_asset ?? null
  const needsSupplyQr = workspace?.supply.delivery_type === 'warehouse_sc'
  const boxAssignRows = useMemo(() => {
    const grouped = new Map<string, {
      key: string
      name: string
      imageUrl: string | null
      identifiers: string
      orders: Array<FbsWorkspace['orders'][number]>
    }>()
    for (const order of availableForBox) {
      const key = order.product.id ?? order.id
      const identifiers = [order.product.seller_article, order.product.barcode].filter(Boolean).join(' · ')
      const current = grouped.get(key) ?? {
        key,
        name: order.product.name,
        imageUrl: order.product.image_url,
        identifiers,
        orders: [],
      }
      current.orders.push(order)
      grouped.set(key, current)
    }
    const query = boxProductSearch.trim().toLocaleLowerCase('ru')
    return [...grouped.values()]
      .map((row) => ({
        ...row,
        orders: [...row.orders].sort((a, b) => a.wb_order_id - b.wb_order_id),
      }))
      .filter((row) => {
        if (!query) return true
        return `${row.name} ${row.identifiers}`.toLocaleLowerCase('ru').includes(query)
      })
      .sort((a, b) => a.name.localeCompare(b.name, 'ru'))
  }, [availableForBox, boxProductSearch])
  const boxAssignSelectedOrderIds = boxAssignRows.flatMap((row) => {
    const qty = Math.min(row.orders.length, Math.max(0, Number(boxProductQty[row.key]) || 0))
    return row.orders.slice(0, qty).map((order) => order.id)
  })

  useEffect(() => {
    if (!workspace || stage !== 'boxes') return
    setExpandedBoxIds((current) => {
      const validIds = new Set(workspace.boxes.map((box) => box.id))
      const next = new Set([...current].filter((id) => validIds.has(id)))
      if (next.size === 0) {
        const first = workspace.boxes.find((box) => box.assigned_order_ids.length > 0) ?? workspace.boxes[0]
        if (first) next.add(first.id)
      }
      return next
    })
  }, [workspace, stage])

  const partialRejectionAlert = workspace?.partial_rejection ? (
    <Alert severity="warning" sx={{ mb: 2 }} data-testid="fbs-partial-rejection">
      <Typography variant="subtitle2">
        WB подтвердил только часть заказов
      </Typography>
      <Typography variant="body2" sx={{ mt: 0.5 }}>
        Вошли в поставку:{' '}
        {workspace.partial_rejection.accepted_orders.length
          ? workspace.partial_rejection.accepted_orders.map((order) => `№${order.wb_order_id}`).join(', ')
          : 'нет'}
      </Typography>
      <Typography variant="body2">
        Не вошли:{' '}
        {workspace.partial_rejection.rejected_orders.length
          ? workspace.partial_rejection.rejected_orders
            .map((order) => `№${order.wb_order_id} — ${order.reason ?? 'WB не подтвердил заказ'}`)
            .join('; ')
          : 'нет'}
      </Typography>
    </Alert>
  ) : null

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
          {partialRejectionAlert}

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
                {manualPickRows.length === 0 ? <Alert severity="info">Нет товаров, ожидающих ручного подбора из ячеек.</Alert> : (
                  <Stack spacing={1}>
                    {manualPickRows.map((row) => (
                      <Stack
                        key={`${row.productId}-${row.rowIndex}-${row.location.id}`}
                        direction={{ xs: 'column', md: 'row' }}
                        spacing={1.5}
                        sx={{ alignItems: { md: 'center' }, p: 1.25, bgcolor: 'action.hover', borderRadius: 1.5 }}
                      >
                        <ProductPhotoThumb src={row.product.image_url} alt={row.product.name} size={44} />
                        <Box sx={{ flex: 1, minWidth: 0 }}>
                          <Typography variant="body2" sx={{ fontWeight: 700 }}>{row.product.name}</Typography>
                          {row.identifiers ? <Typography variant="caption" color="text.secondary">{row.identifiers}</Typography> : null}
                        </Box>
                        <Stack direction="row" spacing={0.75} sx={{ width: { xs: '100%', md: 232 } }}>
                          <TextField
                            select
                            size="small"
                            label="Ячейка"
                            value={row.location.id}
                            disabled={!stageIsCurrent || busy}
                            onChange={(event) => {
                              const locationId = String(event.target.value)
                              setManualPickLocationRows((current) => {
                                const currentRows = current[row.productId] ?? row.selectedLocationIds
                                const nextRows = [...currentRows]
                                nextRows[row.rowIndex] = locationId
                                return { ...current, [row.productId]: nextRows }
                              })
                            }}
                            sx={{ flex: 1 }}
                          >
                            {row.locationOptions.map((location) => (
                              <MenuItem key={location.id} value={location.id}>{location.code}</MenuItem>
                            ))}
                          </TextField>
                          <Button
                            size="small"
                            variant="outlined"
                            disabled={!stageIsCurrent || busy || !row.nextLocationId}
                            aria-label="Добавить ячейку"
                            onClick={() => {
                              if (!row.nextLocationId) return
                              setManualPickLocationRows((current) => {
                                const currentRows = current[row.productId] ?? row.selectedLocationIds
                                return { ...current, [row.productId]: [...currentRows, row.nextLocationId!] }
                              })
                            }}
                            sx={{ minWidth: 38, px: 0 }}
                          >
                            +
                          </Button>
                        </Stack>
                        <Box sx={{ minWidth: { md: 150 } }}>
                          <Typography variant="body2">К снятию: {row.orderIds.length} шт.</Typography>
                          <Typography variant="caption" color="text.secondary">Доступно: {row.location.available} шт.</Typography>
                        </Box>
                        <Button
                          variant="contained"
                          size="small"
                          disabled={!stageIsCurrent || busy}
                          onClick={() => void pickFromCell(row.location.id, row.productId, row.orderIds)}
                        >
                          Снять {row.orderIds.length} шт.
                        </Button>
                      </Stack>
                    ))}
                  </Stack>
                )}
              </Paper>
            </Stack>
          ) : null}

          {workspace && stage === 'packing' ? (
            <Stack spacing={2}>
              {!packagingEditable ? <Alert severity="success">Поставка уже передана в WB. Упаковка доступна только для просмотра.</Alert> : null}
              {packagingTask ? (
                <Paper variant="outlined" sx={{ overflow: 'hidden' }}>
                  <Box sx={{ px: 2, py: 1.75, borderBottom: 1, borderColor: 'divider' }}>
                    <Stack direction={{ xs: 'column', sm: 'row' }} spacing={1.5} sx={{ justifyContent: 'space-between', alignItems: { sm: 'center' } }}>
                      <Box>
                        <Typography variant="h6">Упаковка и маркировка</Typography>
                        <Typography variant="body2" color="text.secondary">
                          Напечатано {printedOrdersCount} из {packingOrders.length} · упаковано {workspace.progress.packed} из {workspace.progress.total}
                        </Typography>
                      </Box>
                      <Stack direction="row" spacing={1}>
                        <Tooltip title="Только если Честный знак уже наклеен селлером">
                          <span>
                            <Button disabled={!packagingEditable || busy} onClick={() => setKizOpen(true)} data-testid="fbs-kiz-open">
                              Внести КИЗ
                            </Button>
                          </span>
                        </Tooltip>
                        <Button disabled={!packagingEditable || busy || unprintedPackingOrders.length === 0} onClick={() => openBulkOrderMarkingPrint(unprintedPackingOrders)}>
                          Печать всего
                        </Button>
                        <Button variant="contained" disabled={!packagingEditable || busy} onClick={() => void packEverything()}>
                          Всё упаковано
                        </Button>
                      </Stack>
                    </Stack>
                  </Box>
                  {workspace.marking_pool && workspace.marking_pool.shortage > 0 ? (
                    <Box sx={{ px: 2, py: 1.25, bgcolor: '#fdf4e7', borderBottom: 1, borderColor: 'divider' }}>
                      <Typography variant="body2" sx={{ color: '#854f0b' }}>
                        Не хватает Честных знаков: нужно {workspace.marking_pool.required}, в пуле {workspace.marking_pool.available}
                      </Typography>
                    </Box>
                  ) : null}
                  <Stack divider={<Divider flexItem />}>
                    {packingOrders.map((order) => {
                      const line = order.product.id ? packLineByProduct.get(order.product.id) : undefined
                      const printed = orderPrintDone(order)
                      const mutedColor = printed ? 'text.secondary' : 'text.primary'
                      const ids = [
                        order.product.seller_article,
                        order.product.barcode,
                        `заказ ${order.wb_order_id}`,
                      ].filter(Boolean).join(' · ')
                      return (
                        <Stack
                          key={order.id}
                          direction="row"
                          spacing={1.5}
                          sx={{
                            alignItems: 'center',
                            px: 2,
                            py: 1.25,
                            bgcolor: printed ? 'action.hover' : 'background.paper',
                          }}
                        >
                          <ProductPhotoThumb src={order.product.image_url} alt={order.product.name} size={40} previewSize={280} />
                          <Box sx={{ flex: 1, minWidth: 0 }}>
                            <Typography variant="body2" sx={{ fontWeight: 700, color: mutedColor }}>
                              {order.product.name}
                            </Typography>
                            <Typography variant="caption" sx={{ display: 'block', color: printed ? 'text.secondary' : 'text.secondary' }}>
                              {ids}
                              {hasOperatorKiz(order) ? ' · КИЗ' : ''}
                              {markingShortOrderIds.has(order.id) ? <Box component="span" sx={{ color: '#854f0b' }}> · ЧЗ не хватило</Box> : null}
                            </Typography>
                          </Box>
                          {printed ? <Typography sx={{ color: 'success.main', fontWeight: 700 }}>✓</Typography> : null}
                          <Stack direction="row" spacing={0.5} sx={{ alignItems: 'center' }}>
                            <Button size="small" variant="outlined" disabled={!line} onClick={() => line && setTzLine(line)}>
                              ТЗ
                            </Button>
                            <Button size="small" variant="outlined" disabled={!packagingEditable || busy} onClick={() => void requestPrintBatch([order.id])}>
                              QR
                            </Button>
                            <IconButton size="small" disabled={!packagingEditable || busy || !line} onClick={() => line && openOrderMarkingPrint(order, line)} aria-label="Печать ЧЗ и ШК">
                              <PrintOutlinedIcon fontSize="small" />
                            </IconButton>
                            <IconButton
                              size="small"
                              disabled={!packagingEditable || busy || !line}
                              onClick={(event: MouseEvent<HTMLElement>) => setReprintMenu({ orderId: order.id, anchorEl: event.currentTarget })}
                              aria-label="Перепечатка"
                            >
                              <MoreVertOutlinedIcon fontSize="small" />
                            </IconButton>
                          </Stack>
                        </Stack>
                      )
                    })}
                  </Stack>
                </Paper>
              ) : (
                <Alert severity="info">{workspace.supply.packaging_task_id ? 'Загружаем существующее задание упаковки…' : 'Сначала начните работу с поставкой — сервер создаст единственное задание упаковки.'}</Alert>
              )}
            </Stack>
          ) : null}

          {workspace && stage === 'boxes' ? (
            <Stack spacing={2}>
              <Paper variant="outlined" sx={{ overflow: 'hidden' }} data-testid="fbs-boxes">
                <Box sx={{ px: 2.5, py: 2, borderBottom: 1, borderColor: 'divider' }}>
                  <Stack direction={{ xs: 'column', sm: 'row' }} spacing={1.5} sx={{ justifyContent: 'space-between', alignItems: { sm: 'center' } }}>
                    <Box>
                      <Typography variant="h6">Короба · {boxRouteLabel}</Typography>
                      <Typography variant="body2" color="text.secondary">
                        Распределено {boxDistributedCount} из {boxTotalCount} шт · осталось {boxRemainingCount}
                      </Typography>
                    </Box>
                    <Stack direction="row" spacing={1} sx={{ alignItems: 'center' }}>
                      <TextField label="Коробов" value={boxCount} size="small" type="number" disabled={!stageIsCurrent || !packagingEditable} onChange={(e) => setBoxCount(e.target.value)} slotProps={{ htmlInput: { min: 1, max: 100 } }} sx={{ width: 104 }} />
                      <Button variant="contained" disabled={!stageIsCurrent || !packagingEditable || !Number(boxCount)} onClick={() => void createBoxes()}>Добавить короба</Button>
                    </Stack>
                  </Stack>
                </Box>
                <Stack divider={<Divider flexItem />}>
                  {workspace.boxes.map((box) => {
                    const assigned = workspace.orders.filter((order) => box.assigned_order_ids.includes(order.id))
                    const expanded = expandedBoxIds.has(box.id)
                    const grouped = new Map<string, {
                      key: string
                      name: string
                      imageUrl: string | null
                      orderIds: string[]
                    }>()
                    for (const order of assigned) {
                      const key = order.product.id ?? order.id
                      const current = grouped.get(key) ?? {
                        key,
                        name: order.product.name,
                        imageUrl: order.product.image_url,
                        orderIds: [],
                      }
                      current.orderIds.push(order.id)
                      grouped.set(key, current)
                    }
                    return (
                      <Box key={box.id}>
                        <Stack direction="row" spacing={1.5} sx={{ alignItems: 'center', px: 2, py: 1.25 }}>
                          <Box
                            component="span"
                            sx={{ color: 'text.secondary', cursor: 'pointer', width: 18, textAlign: 'center' }}
                            onClick={() => setExpandedBoxIds((current) => {
                              const next = new Set(current)
                              if (next.has(box.id)) next.delete(box.id)
                              else next.add(box.id)
                              return next
                            })}
                          >
                            {expanded ? '▾' : '▸'}
                          </Box>
                          <Box sx={{ flex: 1, minWidth: 0 }}>
                            <Typography variant="body2" sx={{ fontWeight: 500 }}>
                              Короб {box.box_number} <Box component="span" sx={{ color: 'text.secondary' }}>· {assigned.length} шт</Box>
                            </Typography>
                          </Box>
                          <Stack direction="row" spacing={1} sx={{ alignItems: 'center' }}>
                            {workspace.supply.delivery_type === 'pvz' ? (
                              <Button
                                size="small"
                                disabled={busy}
                                onClick={() => box.qr_asset?.preview_url ? openAssetPreview([box.qr_asset]) : void retryBoxQr(box.id)}
                              >
                                QR
                              </Button>
                            ) : null}
                            <Button
                              size="small"
                              disabled={!stageIsCurrent || !packagingEditable || busy}
                              onClick={() => {
                                setBoxAssignTarget(box.id)
                                setBoxProductSearch('')
                                setBoxProductQty({})
                              }}
                            >
                              Добавить товары
                            </Button>
                            <IconButton
                              size="small"
                              disabled={!packagingEditable || busy}
                              onClick={(event: MouseEvent<HTMLElement>) => setBoxMenu({ boxId: box.id, anchorEl: event.currentTarget })}
                              aria-label={`Действия короба ${box.box_number}`}
                            >
                              <MoreVertOutlinedIcon fontSize="small" />
                            </IconButton>
                          </Stack>
                        </Stack>
                        {expanded && grouped.size > 0 ? (
                          <Box sx={{ px: 2, pb: 1.25, pl: { md: 5 } }}>
                            <Stack spacing={1}>
                              {[...grouped.values()].map((row) => (
                                <Stack key={row.key} direction="row" spacing={1.25} sx={{ alignItems: 'center' }}>
                                  <ProductPhotoThumb src={row.imageUrl} alt={row.name} size={36} />
                                  <Box sx={{ flex: 1, minWidth: 0 }}>
                                    <Typography variant="body2">{row.name}</Typography>
                                  </Box>
                                  <Typography variant="body2" color="text.secondary">{row.orderIds.length} шт</Typography>
                                  <IconButton
                                    size="small"
                                    disabled={!stageIsCurrent || !packagingEditable || busy}
                                    onClick={() => void removeBoxOrders(box.id, row.orderIds)}
                                    aria-label={`Убрать ${row.name} из короба ${box.box_number}`}
                                  >
                                    <DeleteOutlinedIcon fontSize="small" />
                                  </IconButton>
                                </Stack>
                              ))}
                            </Stack>
                          </Box>
                        ) : null}
                      </Box>
                    )
                  })}
                </Stack>
              </Paper>
              {!deliveryConfirmed ? (
                <Stack direction="row" sx={{ justifyContent: 'flex-end' }}>
                  <Button variant="contained" size="large" disabled={busy} onClick={() => void deliver()}>
                    Передать в WB
                  </Button>
                </Stack>
              ) : null}
              {deliveryConfirmed && needsSupplyQr && supplyQrAsset?.preview_url ? (
                <Paper variant="outlined" sx={{ p: { xs: 2, md: 3 } }} data-testid="fbs-supply-qr">
                  <Stack direction={{ xs: 'column', sm: 'row' }} spacing={2} sx={{ justifyContent: 'space-between', alignItems: { sm: 'center' } }}>
                    <Box>
                      <Typography variant="h6">QR поставки WB</Typography>
                      <Typography variant="body2" color="text.secondary" sx={{ mt: 0.5 }}>
                        Распечатайте QR для сдачи всей поставки.
                      </Typography>
                    </Box>
                    <Button
                      variant="contained"
                      size="large"
                      startIcon={<PrintOutlinedIcon />}
                      onClick={() => openAssetPreview([supplyQrAsset])}
                    >
                      Печать QR поставки
                    </Button>
                  </Stack>
                </Paper>
              ) : null}
              {deliveryConfirmed && needsSupplyQr && !supplyQrAsset?.preview_url ? (
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
                      Получить QR повторно
                    </Button>
                  )}
                >
                  Поставка передана, QR получить не удалось
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
      {markingPrintDialog}
      {workspace ? (
        <FbsKizScanDialog
          token={token}
          authHeaders={authHeaders}
          supplyId={workspace.supply.id}
          open={kizOpen}
          onClose={() => setKizOpen(false)}
          onCommitted={() => void load(true)}
        />
      ) : null}
      <Dialog open={Boolean(kizUndoOrderId)} onClose={() => setKizUndoOrderId(null)} maxWidth="xs" fullWidth>
        <DialogTitle>Отменить КИЗ?</DialogTitle>
        <DialogContent>
          <Typography variant="body2">
            Привязка снимется у нас и в WB. Отменяйте только если КИЗ внесён по ошибке.
          </Typography>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setKizUndoOrderId(null)}>Не отменять</Button>
          <Button
            color="error"
            variant="contained"
            onClick={() => {
              const orderId = kizUndoOrderId
              setKizUndoOrderId(null)
              if (!orderId || !workspace) return
              void run(async () => {
                await deleteFbsOrderKiz(token, authHeaders, orderId)
                return fetchFbsWorkspace(token, authHeaders, workspace.supply.id)
              }, 'КИЗ отменён.')
            }}
          >
            Отменить КИЗ
          </Button>
        </DialogActions>
      </Dialog>
      <Menu
        anchorEl={reprintMenu?.anchorEl ?? null}
        open={Boolean(reprintMenu)}
        onClose={() => setReprintMenu(null)}
      >
        <MenuItem
          disabled={!reprintOrder || !reprintLine}
          onClick={() => {
            if (reprintOrder && reprintLine) openOrderMarkingPrint(reprintOrder, reprintLine, true)
            setReprintMenu(null)
          }}
        >
          Перепечатка
        </MenuItem>
        {reprintOrder && hasOperatorKiz(reprintOrder) ? (
          <MenuItem
            data-testid="fbs-kiz-undo"
            onClick={() => {
              setKizUndoOrderId(reprintMenu?.orderId ?? null)
              setReprintMenu(null)
            }}
          >
            Отменить КИЗ
          </MenuItem>
        ) : null}
      </Menu>
      <Dialog open={Boolean(tzLine)} onClose={() => setTzLine(null)} maxWidth="sm" fullWidth>
        <DialogTitle>ТЗ на упаковку</DialogTitle>
        <DialogContent dividers>
          <Typography variant="body2" sx={{ whiteSpace: 'pre-wrap' }}>
            {tzLine?.packaging_instructions ?? ''}
          </Typography>
        </DialogContent>
      </Dialog>
      <Dialog open={Boolean(undoOrderId)} onClose={() => setUndoOrderId(null)} maxWidth="xs" fullWidth>
        <DialogTitle>Отменить подбор?</DialogTitle>
        <DialogContent><Typography>Товар будет возвращён в исходную ячейку. Отменяйте только если в подборе действительно ошибка.</Typography></DialogContent>
        <DialogActions><Button onClick={() => setUndoOrderId(null)}>Не отменять</Button><Button color="error" variant="contained" onClick={() => { const orderId = undoOrderId; setUndoOrderId(null); if (orderId && workspace) void run(() => undoFbsPick(token, authHeaders, workspace.supply.id, orderId, createFbsIdempotencyKey()), 'Подбор отменён, остаток возвращён в исходную ячейку.') }}>Вернуть в ячейку</Button></DialogActions>
      </Dialog>
      <Dialog open={Boolean(boxAssignTarget)} onClose={busy ? undefined : () => setBoxAssignTarget(null)} maxWidth="md" fullWidth>
        <DialogTitle>Добавить товары в короб {boxAssignName}</DialogTitle>
        <DialogContent dividers>
          <Stack spacing={1.5} sx={{ pt: 1 }}>
            <TextField
              autoFocus
              fullWidth
              size="small"
              label="Поиск по товару"
              value={boxProductSearch}
              onChange={(event) => setBoxProductSearch(event.target.value)}
              disabled={busy}
            />
            <Stack spacing={1}>
              {boxAssignRows.map((row) => {
                const value = boxProductQty[row.key] ?? ''
                return (
                  <Stack key={row.key} direction="row" spacing={1.25} sx={{ alignItems: 'center' }}>
                    <ProductPhotoThumb src={row.imageUrl} alt={row.name} size={44} />
                    <Box sx={{ flex: 1, minWidth: 0 }}>
                      <Typography variant="body2" sx={{ fontWeight: 700 }}>{row.name}</Typography>
                      <Typography variant="caption" color="text.secondary">{row.identifiers}</Typography>
                    </Box>
                    <TextField
                      size="small"
                      type="number"
                      value={value}
                      disabled={busy}
                      onChange={(event) => {
                        const next = Math.min(row.orders.length, Math.max(0, Number(event.target.value) || 0))
                        setBoxProductQty((current) => ({ ...current, [row.key]: next > 0 ? String(next) : '' }))
                      }}
                      slotProps={{ htmlInput: { min: 0, max: row.orders.length } }}
                      sx={{ width: 96 }}
                    />
                  </Stack>
                )
              })}
            </Stack>
          </Stack>
        </DialogContent>
        <DialogActions>
          <Button variant="contained" disabled={busy || boxAssignSelectedOrderIds.length === 0} onClick={() => void assignBoxOrders()}>Добавить</Button>
        </DialogActions>
      </Dialog>
      <Menu
        anchorEl={boxMenu?.anchorEl ?? null}
        open={Boolean(boxMenu)}
        onClose={() => setBoxMenu(null)}
      >
        <MenuItem disabled={!packagingEditable || !boxMenuBox || boxMenuAssignedCount === 0} onClick={() => { if (boxMenuBox) void clearBox(boxMenuBox.id) }}>
          Очистить
        </MenuItem>
        <MenuItem disabled={!packagingEditable || !boxMenuBox || boxMenuAssignedCount > 0} onClick={() => { if (boxMenuBox) void deleteBox(boxMenuBox.id) }}>
          Удалить
        </MenuItem>
      </Menu>
    </Dialog>
  )
}
