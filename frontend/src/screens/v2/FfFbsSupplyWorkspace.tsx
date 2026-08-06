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
  FormControlLabel,
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
import RefreshOutlinedIcon from '@mui/icons-material/RefreshOutlined'
import { apiUrl } from '../../api'
import { FfPackagingTaskPanel, type PackagingTask } from '../ff/FfPackagingPage'
import { readApiErrorMessage } from '../../utils/readApiErrorMessage'
import { FbsPrintPreviewDialog } from './FbsPrintPreviewDialog'
import { buildFbsPickingListPrintHtml, metadataKindLabel, normalizeMetadataKind, ordersWord } from './fbsUx'
import {
  confirmFbsPrintApplied,
  createFbsCargoPlaces,
  createFbsIdempotencyKey,
  deleteFbsCargoPlaces,
  deliverFbsSupply,
  FbsApiError,
  fetchFbsCargoPlaces,
  fetchFbsPrintBatch,
  fetchFbsWorkspace,
  preflightFbsCargoPlaces,
  preflightFbsDelivery,
  retryFbsSupplyQr,
  scanFbsOrderMetadata,
  scanFbsPickLocation,
  scanFbsPickProduct,
  startFbsSupplyWork,
  syncFbsSupplyTracking,
  undoFbsPick,
  type FbsCargoPlaceDraft,
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
  { key: 'order_stickers', label: 'Стикеры WB' },
  { key: 'handoff_prep', label: 'Подготовка к сдаче' },
  { key: 'delivery', label: 'Передача и статусы' },
] as const

type StageKey = (typeof STAGES)[number]['key']

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
  const [printBatch, setPrintBatch] = useState<FbsPrintBatch | null>(null)
  const [printPreviewOpen, setPrintPreviewOpen] = useState(false)
  const [packagingTask, setPackagingTask] = useState<PackagingTask | null>(null)
  const [cargoCount, setCargoCount] = useState('1')
  const [measurementsConfirmed, setMeasurementsConfirmed] = useState(false)
  const [cargoDeleteTarget, setCargoDeleteTarget] = useState<string | null>(null)
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
    setMeasurementsConfirmed(false)
    setCargoDeleteTarget(null)
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

  const cargoDrafts = (): FbsCargoPlaceDraft[] => {
    const maxCount = Math.max(1, (workspace?.orders.length ?? 0) + 1)
    const count = Math.min(maxCount, Math.max(1, Number(cargoCount) || 1))
    return Array.from({ length: count }, (_, index) => ({
      client_id: `box-${index + 1}`,
      length_mm: null,
      width_mm: null,
      height_mm: null,
      weight_g: null,
      measurements_confirmed: measurementsConfirmed,
    }))
  }

  const createCargo = async () => {
    if (!workspace || !measurementsConfirmed || workspace.cargo_places.length > 0) return
    const boxes = cargoDrafts()
    const cargoFingerprint = encodeURIComponent(JSON.stringify(boxes))
    const cargoKey = persistentOperationKey(workspace.supply.id, 'cargo', cargoFingerprint)
    setBusy(true)
    setError(null)
    try {
      const preflight = await preflightFbsCargoPlaces(token, authHeaders, workspace.supply.id, {
        count: boxes.length,
        boxes,
      })
      if (!preflight.compatible) {
        setError(preflight.issues.map((issue) => issue.message).join(' '))
        return
      }
      await createFbsCargoPlaces(token, authHeaders, workspace.supply.id, {
        count: boxes.length,
        boxes,
        idempotency_key: cargoKey,
      })
      await load(true)
      clearPersistentOperationKey(workspace.supply.id, 'cargo', cargoFingerprint)
      setNotice('Грузоместа созданы в WB. Проверьте и нанесите QR.')
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'Грузоместа не созданы.')
    } finally {
      setBusy(false)
    }
  }

  const refreshCargoQr = async () => {
    if (!workspace) return
    setBusy(true)
    setError(null)
    setRetryAction(null)
    try {
      await fetchFbsCargoPlaces(token, authHeaders, workspace.supply.id)
      await load(true)
      setNotice('QR грузомест обновлены.')
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'Не удалось получить QR грузомест.')
      if (cause instanceof FbsApiError && cause.retryable) {
        setRetryAction(() => () => { void refreshCargoQr() })
      }
    } finally {
      setBusy(false)
    }
  }

  const deleteCargo = async () => {
    if (!workspace || !cargoDeleteTarget) return
    const fingerprint = encodeURIComponent(cargoDeleteTarget)
    const deleteKey = persistentOperationKey(workspace.supply.id, 'cargo-delete', fingerprint)
    setBusy(true)
    setError(null)
    setRetryAction(null)
    try {
      await deleteFbsCargoPlaces(token, authHeaders, workspace.supply.id, {
        wb_trbx_ids: [cargoDeleteTarget],
        idempotency_key: deleteKey,
      })
      clearPersistentOperationKey(workspace.supply.id, 'cargo-delete', fingerprint)
      setCargoDeleteTarget(null)
      await load(true)
      setNotice('Грузоместо удалено из WB.')
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'Грузоместо не удалено.')
      if (cause instanceof FbsApiError && cause.retryable) {
        setRetryAction(() => () => { void deleteCargo() })
      }
    } finally {
      setBusy(false)
    }
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
    () => workspace?.blockers.filter((blocker) => blocker.stage === stage) ?? [],
    [workspace, stage],
  )
  const currentStage = workspace ? visualStage(workspace.stage) : 'composition'
  const currentStageIndex = STAGES.findIndex((item) => item.key === currentStage)
  const stageIsCurrent = stage === currentStage
  const requiredMetadataOrders = workspace?.orders.filter((order) => order.metadata.required.length > 0) ?? []
  const allPicked = Boolean(workspace && workspace.progress.total > 0 && workspace.progress.picked === workspace.progress.total)
  const maxCargoCount = Math.max(1, (workspace?.orders.length ?? 0) + 1)
  const normalizedCargoCount = Math.min(maxCargoCount, Math.max(1, Number(cargoCount) || 1))
  const cargoCountIsValid = Number.isInteger(Number(cargoCount))
    && Number(cargoCount) >= 1
    && Number(cargoCount) <= maxCargoCount
  const changeCargoCount = (next: number) => setCargoCount(String(Math.min(maxCargoCount, Math.max(1, next))))
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
    in_delivery: 'Передан в доставку',
    done: 'Завершён',
  }[value] ?? 'Статус уточняется')
  const deliveryConfirmed = deliverySubmitted
    || workspace?.stage === 'tracking'
    || ['in_delivery', 'done'].includes(workspace?.supply.status ?? '')

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
                  <TableHead><TableRow><TableCell>Заказ WB</TableCell><TableCell>Товар</TableCell><TableCell>Маркировка</TableCell><TableCell>Подбор</TableCell></TableRow></TableHead>
                  <TableBody>
                    {workspace.orders.map((order) => (
                      <TableRow key={order.id}>
                        <TableCell>№{order.wb_order_id}</TableCell>
                        <TableCell>{order.product.name}<Typography variant="caption" color="text.secondary" sx={{ display: 'block' }}>{order.product.barcode ?? 'ШК не указан'}</Typography></TableCell>
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

          {workspace && stage === 'order_stickers' ? (
            <Stack spacing={2}>
              {!stageIsCurrent ? <Alert severity="success">Стикеры подготовлены. Этот этап доступен только для просмотра.</Alert> : null}
              <Paper variant="outlined" sx={{ p: 2 }}>
                <Typography variant="h6">Печать стикеров заказов WB</Typography>
                <Typography variant="body2" color="text.secondary">Получите все стикеры, проверьте предпросмотр, распечатайте и подтвердите нанесение.</Typography>
                <Table size="small" sx={{ my: 2 }}><TableHead><TableRow><TableCell>Заказ WB</TableCell><TableCell>Товар</TableCell><TableCell>Состояние</TableCell></TableRow></TableHead><TableBody>{workspace.orders.map((order) => <TableRow key={order.id}><TableCell>№{order.wb_order_id}</TableCell><TableCell>{order.product.name}</TableCell><TableCell>{rawStatusLabel(order.sticker.status)}</TableCell></TableRow>)}</TableBody></Table>
                <Stack direction="row" spacing={1} sx={{ justifyContent: 'flex-end', flexWrap: 'wrap' }} useFlexGap><Button variant="contained" startIcon={<PrintOutlinedIcon />} disabled={!stageIsCurrent} onClick={() => void requestPrintBatch()}>Получить все стикеры</Button>{printBatch?.missing ? <Button variant="text" disabled={!stageIsCurrent} onClick={() => void requestPrintBatch(undefined, true)}>Повторить отсутствующие</Button> : null}</Stack>
              </Paper>
              {printBatch ? <Paper variant="outlined" sx={{ p: 2 }}><Typography variant="body2">Готово: {printBatch.ready}{printBatch.missing ? ` · Не получено: ${printBatch.missing}` : ''}{printBatch.failed ? ` · Ошибок: ${printBatch.failed}` : ''}</Typography><Button variant="outlined" disabled={printBatch.ready === 0} sx={{ mt: 1 }} onClick={() => setPrintPreviewOpen(true)}>Открыть предпросмотр и печать</Button>{printBatch.order_errors.map((item) => <Alert key={item.order_id} severity="error" sx={{ mt: 1 }}>Заказ WB №{item.wb_order_id}: {item.message}</Alert>)}</Paper> : null}
            </Stack>
          ) : null}

          {workspace && stage === 'handoff_prep' ? (
            workspace.supply.delivery_type === 'pvz' ? (
              <Stack spacing={2}>
                {deliveryConfirmed ? <Alert severity="success">Поставка уже передана WB. Грузоместа доступны только для просмотра и печати.</Alert> : null}
                {workspace.cargo_places.length === 0 ? (
                  <Paper variant="outlined" sx={{ overflow: 'hidden' }}>
                    <Box sx={{ px: { xs: 2, md: 3 }, py: 2.5, borderBottom: 1, borderColor: 'divider' }}>
                      <Stack direction="row" spacing={1} sx={{ alignItems: 'center', mb: 0.5 }}>
                        <Typography variant="h6">Грузоместа</Typography>
                        <Chip label="Сдача в ПВЗ" color="primary" size="small" variant="outlined" />
                      </Stack>
                      <Typography variant="body2" color="text.secondary">
                        Укажите количество физических коробов. WB создаст отдельное грузоместо с QR-кодом для каждого короба.
                      </Typography>
                    </Box>

                    <Box sx={{ px: { xs: 2, md: 3 }, py: 2.5 }}>
                      <Stack direction={{ xs: 'column', md: 'row' }} spacing={3} sx={{ alignItems: { md: 'flex-start' } }}>
                        <Box sx={{ flex: 1 }}>
                          <Typography variant="subtitle1" sx={{ fontWeight: 750 }}>
                            Количество коробов
                          </Typography>
                          <Typography variant="body2" color="text.secondary" sx={{ mb: 1.5 }}>
                            Распределять заказы между грузоместами не нужно. Допустимо до {maxCargoCount} грузомест для этой поставки.
                          </Typography>
                          <Stack direction="row" spacing={1} sx={{ alignItems: 'center' }}>
                            <Button
                              variant="outlined"
                              aria-label="Уменьшить количество коробов"
                              data-testid="fbs-cargo-decrement"
                              disabled={!stageIsCurrent || normalizedCargoCount <= 1}
                              onClick={() => changeCargoCount(normalizedCargoCount - 1)}
                              sx={{ minWidth: 44, fontSize: 22, lineHeight: 1 }}
                            >
                              −
                            </Button>
                            <TextField
                              value={cargoCount}
                              type="number"
                              size="small"
                              slotProps={{ htmlInput: { min: 1, max: maxCargoCount, 'aria-label': 'Количество физических коробов' } }}
                              disabled={!stageIsCurrent}
                              onChange={(event) => setCargoCount(event.target.value)}
                              onBlur={() => changeCargoCount(normalizedCargoCount)}
                              data-testid="fbs-cargo-count"
                              sx={{ width: 96, '& input': { textAlign: 'center', fontWeight: 750 } }}
                            />
                            <Button
                              variant="outlined"
                              aria-label="Увеличить количество коробов"
                              data-testid="fbs-cargo-increment"
                              disabled={!stageIsCurrent || normalizedCargoCount >= maxCargoCount}
                              onClick={() => changeCargoCount(normalizedCargoCount + 1)}
                              sx={{ minWidth: 44, fontSize: 22, lineHeight: 1 }}
                            >
                              +
                            </Button>
                          </Stack>
                        </Box>

                        <Box sx={{ flex: 1.15, p: 2, bgcolor: 'action.hover', borderRadius: 2 }}>
                          <Typography variant="subtitle2">Перед созданием</Typography>
                          <FormControlLabel
                            sx={{ mt: 0.5, alignItems: 'flex-start' }}
                            control={(
                              <Checkbox
                                checked={measurementsConfirmed}
                                disabled={!stageIsCurrent}
                                onChange={(_, value) => setMeasurementsConfirmed(value)}
                                data-testid="fbs-cargo-limits-confirmed"
                              />
                            )}
                            label={(
                              <Typography variant="body2" sx={{ pt: 0.75 }}>
                                Проверил каждый короб: сторона не больше 60 см, сумма сторон не больше 140 см, вес не больше 5 кг.
                              </Typography>
                            )}
                          />
                        </Box>
                      </Stack>

                      <Stack direction="row" sx={{ justifyContent: 'flex-end', mt: 2.5 }}>
                        <Button
                          variant="contained"
                          size="large"
                          disabled={!stageIsCurrent || !measurementsConfirmed || !cargoCountIsValid}
                          onClick={() => void createCargo()}
                          data-testid="fbs-cargo-create"
                        >
                          Создать {normalizedCargoCount} {normalizedCargoCount === 1 ? 'грузоместо' : 'грузоместа'}
                        </Button>
                      </Stack>
                    </Box>
                  </Paper>
                ) : (
                  <Paper variant="outlined" sx={{ overflow: 'hidden' }} data-testid="fbs-cargo-table">
                    <Box sx={{ px: { xs: 2, md: 3 }, py: 2.25, borderBottom: 1, borderColor: 'divider' }}>
                      <Stack direction={{ xs: 'column', sm: 'row' }} spacing={1.5} sx={{ justifyContent: 'space-between', alignItems: { sm: 'center' } }}>
                        <Box>
                          <Stack direction="row" spacing={1} sx={{ alignItems: 'center' }}>
                            <Typography variant="h6">Грузоместа</Typography>
                            <Chip label={`${workspace.cargo_places.length} создано`} color="success" size="small" />
                          </Stack>
                          <Typography variant="body2" color="text.secondary">
                            Распечатайте QR и наклейте каждый код на отдельный физический короб.
                          </Typography>
                        </Box>
                        {workspace.cargo_places.some((place) => place.qr_asset?.preview_url) ? (
                          <Button
                            variant="outlined"
                            startIcon={<PrintOutlinedIcon />}
                            data-testid="fbs-cargo-print-all"
                            onClick={() => openAssetPreview(workspace.cargo_places.flatMap((place) => place.qr_asset ? [place.qr_asset] : []))}
                          >
                            Печать всех QR
                          </Button>
                        ) : null}
                      </Stack>
                    </Box>
                    {workspace.cargo_places.some((place) => !place.qr_asset?.preview_url) ? (
                      <Alert
                        severity="warning"
                        sx={{ m: 2 }}
                        action={<Button color="inherit" size="small" disabled={busy} onClick={() => void refreshCargoQr()}>Получить ещё раз</Button>}
                      >
                        WB ещё не отдал все QR. Повторный запрос получает коды и не создаёт новые грузоместа.
                      </Alert>
                    ) : null}
                    <Table size="small">
                      <TableHead>
                        <TableRow>
                          <TableCell>Грузоместо</TableCell>
                          <TableCell>Номер WB</TableCell>
                          <TableCell>QR-код</TableCell>
                          <TableCell align="right">Действие</TableCell>
                        </TableRow>
                      </TableHead>
                      <TableBody>
                        {workspace.cargo_places.map((place, index) => (
                          <TableRow key={place.id}>
                            <TableCell sx={{ fontWeight: 700 }}>Короб {index + 1}</TableCell>
                            <TableCell>{place.wb_trbx_id}</TableCell>
                            <TableCell>
                              <Chip
                                size="small"
                                color={place.qr_asset?.preview_url ? 'success' : 'warning'}
                                label={place.qr_asset?.preview_url ? 'Готов' : 'Ожидается'}
                              />
                            </TableCell>
                            <TableCell align="right">
                              <Stack direction="row" spacing={0.5} sx={{ justifyContent: 'flex-end' }}>
                                <Button
                                  size="small"
                                  startIcon={<PrintOutlinedIcon />}
                                  disabled={!place.qr_asset?.preview_url}
                                  onClick={() => place.qr_asset && openAssetPreview([place.qr_asset])}
                                >
                                  Печать QR
                                </Button>
                                <IconButton
                                  size="small"
                                  color="error"
                                  aria-label={`Удалить короб ${index + 1}`}
                                  data-testid={`fbs-cargo-delete-${place.wb_trbx_id}`}
                                  disabled={deliveryConfirmed || busy}
                                  onClick={() => setCargoDeleteTarget(place.wb_trbx_id)}
                                >
                                  <DeleteOutlinedIcon fontSize="small" />
                                </IconButton>
                              </Stack>
                            </TableCell>
                          </TableRow>
                        ))}
                      </TableBody>
                    </Table>
                  </Paper>
                )}
              </Stack>
            ) : (
              <Paper variant="outlined" sx={{ p: { xs: 2, md: 3 } }} data-testid="fbs-warehouse-handoff">
                <Stack direction={{ xs: 'column', md: 'row' }} spacing={3} sx={{ alignItems: { md: 'flex-start' } }}>
                  <Box sx={{ flex: 1 }}>
                    <Stack direction="row" spacing={1} sx={{ alignItems: 'center', mb: 0.75 }}>
                      <Typography variant="h6">Сдача на склад или СЦ</Typography>
                      <Chip label="Без грузомест WB" size="small" color="success" variant="outlined" />
                    </Stack>
                    <Typography variant="body2" color="text.secondary">
                      Для этого маршрута создавать короба в WMS и распределять по ним заказы не нужно. Физически упакуйте поставку и переходите к передаче.
                    </Typography>
                  </Box>
                  <Box sx={{ minWidth: { md: 320 }, p: 2, bgcolor: 'action.hover', borderRadius: 2 }}>
                    <Typography variant="subtitle2">Что будет дальше</Typography>
                    <Typography variant="body2" color="text.secondary" sx={{ mt: 0.5 }}>
                      После подтверждённой передачи WB сформирует один общий QR поставки. Он появится на следующем этапе — там же будет печать и безопасный повтор получения.
                    </Typography>
                  </Box>
                </Stack>
                {workspace.supply.planned_destination ? (
                  <Alert severity="info" sx={{ mt: 2 }}>
                    Место сдачи: {workspace.supply.planned_destination.name}, зона {workspace.supply.planned_destination.zone}
                  </Alert>
                ) : null}
              </Paper>
            )
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
              {workspace.supply.delivery_type === 'warehouse_sc' && deliveryConfirmed && !workspace.supply.barcode_asset?.preview_url ? (
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
              <Paper variant="outlined" sx={{ p: 2 }}><Stack direction="row" sx={{ justifyContent: 'space-between' }}><Box><Typography variant="h6">Статусы WB</Typography><Typography variant="body2" color="text.secondary">Последняя синхронизация: {workspace.last_wb_sync_at ? new Date(workspace.last_wb_sync_at).toLocaleString('ru-RU') : 'ещё не выполнялась'}</Typography>{workspace.wb_sync_stale ? <Chip label="Данные устарели" color="warning" size="small" sx={{ mt: 1 }} /> : null}</Box><Button disabled={busy || ['done', 'cancelled', 'defect'].includes(workspace.supply.status)} onClick={() => void run(() => syncFbsSupplyTracking(token, authHeaders, workspace.supply.id), 'Статусы Wildberries обновлены.')} startIcon={<RefreshOutlinedIcon />}>{workspace.supply.status === 'done' ? 'Статусы зафиксированы' : 'Обновить статусы'}</Button></Stack><Table size="small" sx={{ mt: 2 }}><TableHead><TableRow><TableCell>Заказ WB</TableCell><TableCell>Товар</TableCell><TableCell>Результат WB</TableCell><TableCell>Повтор / причина</TableCell></TableRow></TableHead><TableBody>{(workspace.tracking_summary?.orders ?? workspace.orders.map((order) => ({ order_id: order.id, wb_order_id: order.wb_order_id, tracking_label: order.wb_status ?? order.status, wb_status: order.wb_status, local_status: order.status }))).map((tracking) => { const order = workspace.orders.find((item) => item.id === tracking.order_id); const rejected = workspace.partial_rejection?.rejected_orders.find((item) => item.order_id === tracking.order_id); return <TableRow key={tracking.order_id}><TableCell>№{tracking.wb_order_id}</TableCell><TableCell>{order?.product.name ?? 'Товар не сопоставлен'}</TableCell><TableCell>{rawStatusLabel(tracking.tracking_label)}</TableCell><TableCell>{rejected?.reason ?? (tracking.tracking_label.includes('reject') ? 'Требуется повторная проверка' : '—')}</TableCell></TableRow> })}</TableBody></Table></Paper>
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
        <DialogActions><Button onClick={() => setUndoOrderId(null)}>Не отменять</Button><Button color="error" variant="contained" onClick={() => { const orderId = undoOrderId; setUndoOrderId(null); if (orderId && workspace) void run(() => undoFbsPick(token, authHeaders, workspace.supply.id, orderId, createFbsIdempotencyKey()), 'Подбор отменён, остаток возвращён в исходную ячейку.') }}>Вернуть в ячейку</Button></DialogActions>
      </Dialog>
      <Dialog open={Boolean(cargoDeleteTarget)} onClose={busy ? undefined : () => setCargoDeleteTarget(null)} maxWidth="xs" fullWidth>
        <DialogTitle>Удалить грузоместо?</DialogTitle>
        <DialogContent>
          <Stack spacing={1.5}>
            <Typography>
              Короб {(workspace?.cargo_places.findIndex((place) => place.wb_trbx_id === cargoDeleteTarget) ?? -1) + 1} и его QR будут удалены из поставки WB.
            </Typography>
            <Alert severity="warning">
              Используйте это, если физический короб создали по ошибке. Заказы перераспределять не нужно — они не привязаны к грузоместу.
            </Alert>
          </Stack>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setCargoDeleteTarget(null)} disabled={busy}>Не удалять</Button>
          <Button color="error" variant="contained" onClick={() => void deleteCargo()} disabled={busy} data-testid="fbs-cargo-delete-confirm">
            Удалить из WB
          </Button>
        </DialogActions>
      </Dialog>
      <Dialog open={deliveryConfirmOpen} onClose={() => setDeliveryConfirmOpen(false)} maxWidth="sm" fullWidth>
        <DialogTitle>Подтвердить передачу в WB?</DialogTitle>
        <DialogContent>{workspace ? <Stack spacing={1}><Typography>Поставка: {workspace.supply.name}</Typography><Typography>Селлер: {workspace.supply.seller.name}</Typography><Typography>Маршрут: {workspace.supply.delivery_type === 'pvz' ? 'ПВЗ' : 'Склад / СЦ'}</Typography><Typography>Заказов: {workspace.orders.length}{workspace.supply.delivery_type === 'pvz' ? ` · грузомест: ${workspace.cargo_places.length}` : ''}</Typography><Alert severity="warning">Это отправит подтверждение передачи в WB.</Alert></Stack> : null}</DialogContent>
        <DialogActions><Button onClick={() => setDeliveryConfirmOpen(false)}>Отмена</Button><Button variant="contained" onClick={() => { setDeliveryConfirmOpen(false); void deliver() }}>Передать в WB</Button></DialogActions>
      </Dialog>
    </Dialog>
  )
}
