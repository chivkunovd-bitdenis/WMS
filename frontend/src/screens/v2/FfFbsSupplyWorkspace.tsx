import { useCallback, useEffect, useMemo, useState } from 'react'
import {
  Alert,
  Box,
  Button,
  Checkbox,
  Chip,
  CircularProgress,
  Dialog,
  DialogContent,
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
import LocalShippingOutlinedIcon from '@mui/icons-material/LocalShippingOutlined'
import PrintOutlinedIcon from '@mui/icons-material/PrintOutlined'
import RefreshOutlinedIcon from '@mui/icons-material/RefreshOutlined'
import { apiUrl } from '../../api'
import { FfPackagingTaskPanel, type PackagingTask } from '../ff/FfPackagingPage'
import { readApiErrorMessage } from '../../utils/readApiErrorMessage'
import { FbsPrintPreviewDialog } from './FbsPrintPreviewDialog'
import {
  confirmFbsPrintApplied,
  createFbsCargoPlaces,
  createFbsIdempotencyKey,
  deliverFbsSupply,
  fetchFbsPrintBatch,
  fetchFbsWorkspace,
  preflightFbsCargoPlaces,
  preflightFbsDelivery,
  scanFbsOrderMetadata,
  scanFbsPickLocation,
  scanFbsPickProduct,
  startFbsSupplyWork,
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
  const [selectedPrintOrderIds, setSelectedPrintOrderIds] = useState<Set<string>>(new Set())
  const [packagingTask, setPackagingTask] = useState<PackagingTask | null>(null)
  const [cargoCount, setCargoCount] = useState('1')
  const [cargoLength, setCargoLength] = useState('400')
  const [cargoWidth, setCargoWidth] = useState('300')
  const [cargoHeight, setCargoHeight] = useState('200')
  const [cargoWeight, setCargoWeight] = useState('2000')
  const [measurementsConfirmed, setMeasurementsConfirmed] = useState(false)
  const [deliveryPreflight, setDeliveryPreflight] = useState<FbsDeliveryPreflight | null>(null)
  const [deliveryKey, setDeliveryKey] = useState(createFbsIdempotencyKey)

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
    setDeliveryKey(createFbsIdempotencyKey())
    setDeliveryPreflight(null)
    setPrintBatch(null)
    setSelectedPrintOrderIds(new Set())
    setPickLocation(null)
    if (!initialWorkspace) void load()
  }, [open, supplyId, initialWorkspace, load])

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
    try {
      const next = await operation()
      setWorkspace(next)
      setStage(visualStage(next.stage))
      setNotice(success)
      return next
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'Операция не выполнена.')
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
    setNotice('Физическое нанесение стикера подтверждено.')
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
      setError('Нет готового QR для preview — окно печати не открыто.')
      return
    }
    setPrintPreviewOpen(true)
  }

  const cargoDrafts = (): FbsCargoPlaceDraft[] => {
    const count = Math.max(1, Number(cargoCount) || 1)
    const numeric = (value: string) => (value.trim() ? Number(value) || null : null)
    return Array.from({ length: count }, (_, index) => ({
      client_id: `box-${index + 1}`,
      length_mm: numeric(cargoLength),
      width_mm: numeric(cargoWidth),
      height_mm: numeric(cargoHeight),
      weight_g: numeric(cargoWeight),
      measurements_confirmed: measurementsConfirmed,
    }))
  }

  const createCargo = async () => {
    if (!workspace) return
    const boxes = cargoDrafts()
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
        idempotency_key: createFbsIdempotencyKey(),
      })
      await load(true)
      setNotice('Грузоместа созданы в WB. Проверьте и нанесите QR.')
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'Грузоместа не созданы.')
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
      'WB подтвердил передачу поставки в доставку.',
    )
    if (next) {
      setDeliveryKey(createFbsIdempotencyKey())
      setDeliveryPreflight(null)
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
  const stageBlockers = useMemo(
    () => workspace?.blockers.filter((blocker) => blocker.stage === stage) ?? [],
    [workspace, stage],
  )

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
                    ? `${workspace.supply.wb_supply_id} · ${workspace.supply.seller.name}`
                    : 'Загружаем данные поставки…'}
                </Typography>
              </Box>
              {workspace ? (
                <Stack direction="row" spacing={3} sx={{ flexWrap: 'wrap' }} useFlexGap>
                  <Metric label="Склад WB" value={workspace.supply.wb_warehouse.name ?? `ID ${workspace.supply.wb_warehouse.id}`} />
                  <Metric label="Склад WMS" value={workspace.supply.wms_warehouse.name} />
                  <Metric label="Маршрут" value={workspace.supply.delivery_type === 'pvz' ? 'ПВЗ' : 'Склад / СЦ'} />
                  <Metric label="Блокеров" value={String(workspace.blockers.length)} />
                </Stack>
              ) : null}
            </Stack>
            <Stack direction="row" spacing={1.5} sx={{ alignItems: 'center', mt: 1.25 }}>
              <LinearProgress variant="determinate" value={percent} sx={{ flex: 1, maxWidth: 480, height: 8, borderRadius: 4 }} />
              <Typography variant="caption" sx={{ fontWeight: 750 }}>{percent}% готово</Typography>
              {workspace ? (
                <Typography variant="caption" color="text.secondary">
                  Дедлайн {new Date(workspace.supply.nearest_deadline_at).toLocaleString('ru-RU')}
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
          setStage(value)
          setError(null)
          setNotice(null)
        }}
        variant="scrollable"
        scrollButtons="auto"
        sx={{ px: 2, borderBottom: 1, borderColor: 'divider', bgcolor: 'rgba(91,33,182,.035)' }}
      >
        {STAGES.map((item) => (
          <Tab key={item.key} value={item.key} label={item.label} />
        ))}
      </Tabs>

      {busy ? <LinearProgress /> : null}
      <DialogContent sx={{ p: 0, bgcolor: '#f4f6fb' }}>
        <Box sx={{ p: { xs: 1.5, md: 2.5 }, minHeight: '100%' }}>
          {error ? <Alert severity="error" sx={{ mb: 2 }}>{error}</Alert> : null}
          {notice ? <Alert severity="success" sx={{ mb: 2 }}>{notice}</Alert> : null}
          {stageBlockers.length ? (
            <Alert severity="warning" sx={{ mb: 2 }}>
              <Typography variant="subtitle2">Что блокирует следующий шаг</Typography>
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
                <Typography variant="h6">Состав поставки</Typography>
                <Typography variant="body2" color="text.secondary">
                  {workspace.orders.length} заказов · состав подтверждён WB одной операцией
                </Typography>
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
                <Button variant="contained" size="large" onClick={() => void run(() => startFbsSupplyWork(token, authHeaders, workspace.supply.id), 'Задание создано. Можно начинать подбор.')}>
                  Начать работу с поставкой
                </Button>
              </Stack>
            </Stack>
          ) : null}

          {workspace && stage === 'picking' ? (
            <Stack spacing={2}>
              <Paper variant="outlined" sx={{ p: 2 }}>
                <Typography variant="h6">Сканирование подбора</Typography>
                <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
                  Сначала подтвердите ячейку, затем сканируйте товары. Прогресс хранится на сервере.
                </Typography>
                <Stack direction={{ xs: 'column', md: 'row' }} spacing={1.5}>
                  <TextField label="Штрихкод ячейки" value={locationBarcode} onChange={(e) => setLocationBarcode(e.target.value)} onKeyDown={(e) => { if (e.key === 'Enter') void scanLocation() }} />
                  <Button variant="outlined" onClick={() => void scanLocation()}>Подтвердить ячейку</Button>
                  <TextField label="Штрихкод товара" value={productBarcode} onChange={(e) => setProductBarcode(e.target.value)} disabled={!pickLocation} onKeyDown={(e) => { if (e.key === 'Enter') void scanProduct() }} sx={{ flex: 1 }} />
                  <Button variant="contained" onClick={() => void scanProduct()} disabled={!pickLocation || !productBarcode.trim()}>Подобрать товар</Button>
                </Stack>
                {pickLocation ? <Alert severity="success" sx={{ mt: 2 }}>Ячейка {pickLocation.code} подтверждена · {pickLocation.warehouse_name}</Alert> : null}
              </Paper>
              <Paper variant="outlined" sx={{ p: 2 }}>
                <Typography variant="subtitle1" gutterBottom>Товары в подборе: {workspace.progress.picked}/{workspace.progress.total}</Typography>
                <Table size="small">
                  <TableHead><TableRow><TableCell>Товар</TableCell><TableCell>Ячейки и остаток</TableCell><TableCell>Нужно / подобрано</TableCell><TableCell>Заказы WB</TableCell><TableCell>Маркировка</TableCell><TableCell>Дедлайн</TableCell></TableRow></TableHead>
                  <TableBody>{pickingRows.map((row) => <TableRow key={row.key}><TableCell><Stack direction="row" spacing={1.5} sx={{ alignItems: 'center' }}>{row.imageUrl ? <Box component="img" src={row.imageUrl} alt="" sx={{ width: 52, height: 52, objectFit: 'contain', borderRadius: 1 }} /> : null}<Box><Typography variant="body2" sx={{ fontWeight: 700 }}>{row.name}</Typography><Typography variant="caption" color="text.secondary">{row.identifiers.join(' · ') || 'Идентификаторы не указаны'}</Typography></Box></Stack></TableCell><TableCell>{row.locations.length ? row.locations.join(', ') : 'Ячейка не назначена'}</TableCell><TableCell>{row.required} / {row.picked}</TableCell><TableCell>{row.wbOrders.map((id) => `№${id}`).join(', ')}</TableCell><TableCell>{row.marking}</TableCell><TableCell>{new Date(row.nearestDeadline).toLocaleString('ru-RU')}</TableCell></TableRow>)}</TableBody>
                </Table>
                <Divider sx={{ my: 2 }} />
                <Typography variant="subtitle2" gutterBottom>Отмена подбора по заказу</Typography>
                <Stack direction="row" spacing={1} sx={{ flexWrap: 'wrap' }} useFlexGap>{workspace.orders.filter((order) => order.pick.status === 'picked').map((order) => <Button key={order.id} size="small" variant="outlined" disabled={order.pack.status === 'packed'} onClick={() => void run(() => undoFbsPick(token, authHeaders, workspace.supply.id, order.id, createFbsIdempotencyKey()), 'Подбор отменён, остаток возвращён в исходную ячейку.')}>Отменить №{order.wb_order_id}</Button>)}</Stack>
              </Paper>
            </Stack>
          ) : null}

          {workspace && stage === 'packing' ? (
            <Stack spacing={2}>
              {packagingTask ? (
                <Paper variant="outlined" sx={{ p: 2 }}><FfPackagingTaskPanel token={token} task={packagingTask} unloadLabel={workspace.supply.name} hideDocumentHeader onUpdated={setPackagingTask} /></Paper>
              ) : (
                <Alert severity="info">{workspace.supply.packaging_task_id ? 'Загружаем существующее задание упаковки…' : 'Сначала начните работу с поставкой — сервер создаст единственное задание упаковки.'}</Alert>
              )}
              <Paper variant="outlined" sx={{ p: 2 }}>
                <Typography variant="h6">Идентификаторы заказа WB</Typography>
                <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>Сканирование сохраняет исходную строку без trim, включая GS-разделители.</Typography>
                <Stack direction={{ xs: 'column', md: 'row' }} spacing={1.5}>
                  <Select displayEmpty value={metadataOrderId} onChange={(e) => setMetadataOrderId(String(e.target.value))} sx={{ minWidth: 190 }}><MenuItem value="">Выберите заказ</MenuItem>{workspace.orders.map((order) => <MenuItem key={order.id} value={order.id}>№{order.wb_order_id}</MenuItem>)}</Select>
                  <Select value={metadataKind} onChange={(e) => setMetadataKind(String(e.target.value))} sx={{ minWidth: 140 }}><MenuItem value="sgtin">КИЗ / SGTIN</MenuItem><MenuItem value="uin">УИН</MenuItem><MenuItem value="imei">IMEI</MenuItem><MenuItem value="gtin">GTIN</MenuItem></Select>
                  <TextField label="Отсканированное значение" value={metadataValue} onChange={(e) => setMetadataValue(e.target.value)} sx={{ flex: 1 }} />
                  <Button variant="contained" onClick={() => void scanMetadata()} disabled={!metadataOrderId || metadataValue.length === 0}>Передать на проверку</Button>
                </Stack>
                <Table size="small" sx={{ mt: 2 }}>
                  <TableHead><TableRow><TableCell>Заказ WB</TableCell><TableCell>Что требуется</TableCell><TableCell>Фактическое состояние</TableCell></TableRow></TableHead>
                  <TableBody>{workspace.orders.map((order) => <TableRow key={order.id}><TableCell>№{order.wb_order_id}</TableCell><TableCell>{order.metadata.required.length ? order.metadata.required.join(', ') : 'Не требуется'}</TableCell><TableCell>{order.metadata.states.length ? order.metadata.states.map((state) => `${state.kind}: ${state.status}${state.reason ? ` (${state.reason})` : ''}`).join('; ') : 'Данные ещё не переданы'}</TableCell></TableRow>)}</TableBody>
                </Table>
              </Paper>
            </Stack>
          ) : null}

          {workspace && stage === 'order_stickers' ? (
            <Stack spacing={2}>
              <Paper variant="outlined" sx={{ p: 2 }}>
                <Typography variant="h6">Печать стикеров заказов WB</Typography>
                <Typography variant="body2" color="text.secondary">Выберите один или несколько заказов либо запросите все. Preview всегда показывается до системного окна печати.</Typography>
                <Table size="small" sx={{ my: 2 }}><TableHead><TableRow><TableCell padding="checkbox"><Checkbox checked={selectedPrintOrderIds.size === workspace.orders.length && workspace.orders.length > 0} indeterminate={selectedPrintOrderIds.size > 0 && selectedPrintOrderIds.size < workspace.orders.length} onChange={(_, checked) => setSelectedPrintOrderIds(checked ? new Set(workspace.orders.map((order) => order.id)) : new Set())} /></TableCell><TableCell>Заказ WB</TableCell><TableCell>Товар</TableCell><TableCell>Состояние</TableCell></TableRow></TableHead><TableBody>{workspace.orders.map((order) => <TableRow key={order.id}><TableCell padding="checkbox"><Checkbox checked={selectedPrintOrderIds.has(order.id)} onChange={() => setSelectedPrintOrderIds((current) => { const next = new Set(current); if (next.has(order.id)) next.delete(order.id); else next.add(order.id); return next })} /></TableCell><TableCell>№{order.wb_order_id}</TableCell><TableCell>{order.product.name}</TableCell><TableCell>{order.sticker.status}</TableCell></TableRow>)}</TableBody></Table>
                <Stack direction="row" spacing={1} sx={{ justifyContent: 'flex-end', flexWrap: 'wrap' }} useFlexGap><Button variant="outlined" disabled={selectedPrintOrderIds.size === 0} onClick={() => void requestPrintBatch([...selectedPrintOrderIds])}>Получить выбранные</Button><Button variant="outlined" onClick={() => void requestPrintBatch(undefined, true)}>Повторить отсутствующие</Button><Button variant="contained" startIcon={<PrintOutlinedIcon />} onClick={() => void requestPrintBatch()}>Получить все</Button></Stack>
              </Paper>
              {printBatch ? <Paper variant="outlined" sx={{ p: 2 }}><Stack direction="row" spacing={1} sx={{ mb: 2 }}><Chip label={`Готово ${printBatch.ready}`} color="success" /><Chip label={`Нет ${printBatch.missing}`} color={printBatch.missing ? 'warning' : 'default'} /><Chip label={`Ошибок ${printBatch.failed}`} color={printBatch.failed ? 'error' : 'default'} /></Stack><Button variant="outlined" disabled={printBatch.ready === 0} onClick={() => setPrintPreviewOpen(true)}>Открыть preview и печать</Button>{printBatch.order_errors.map((item) => <Alert key={item.order_id} severity="error" sx={{ mt: 1 }}>Заказ WB №{item.wb_order_id}: {item.message}</Alert>)}</Paper> : null}
            </Stack>
          ) : null}

          {workspace && stage === 'handoff_prep' ? (
            workspace.supply.delivery_type === 'pvz' ? (
              <Stack spacing={2}>
                <Paper variant="outlined" sx={{ p: 2 }}><Typography variant="h6">Грузоместа для сдачи в ПВЗ</Typography><Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>Укажите физические короба. Заказы к грузоместам не привязываются.</Typography><Stack direction={{ xs: 'column', lg: 'row' }} spacing={1.5}><TextField label="Коробов" type="number" value={cargoCount} onChange={(e) => setCargoCount(e.target.value)} sx={{ width: 110 }} /><TextField label="Длина, мм" value={cargoLength} onChange={(e) => setCargoLength(e.target.value)} /><TextField label="Ширина, мм" value={cargoWidth} onChange={(e) => setCargoWidth(e.target.value)} /><TextField label="Высота, мм" value={cargoHeight} onChange={(e) => setCargoHeight(e.target.value)} /><TextField label="Вес, г" value={cargoWeight} onChange={(e) => setCargoWeight(e.target.value)} /></Stack><FormControlLabel sx={{ mt: 1 }} control={<Checkbox checked={measurementsConfirmed} onChange={(_, value) => setMeasurementsConfirmed(value)} />} label="Подтверждаю введённые вручную размеры" /><Stack direction="row" sx={{ justifyContent: 'flex-end' }}><Button variant="contained" onClick={() => void createCargo()}>Проверить и создать грузоместа</Button></Stack></Paper>
                {workspace.cargo_places.some((place) => place.qr_asset) ? <Stack direction="row" sx={{ justifyContent: 'flex-end' }}><Button startIcon={<PrintOutlinedIcon />} onClick={() => openAssetPreview(workspace.cargo_places.flatMap((place) => place.qr_asset ? [place.qr_asset] : []))}>Печать всех QR грузомест WB</Button></Stack> : null}
                <Box sx={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill,minmax(250px,1fr))', gap: 2 }}>{workspace.cargo_places.map((place) => <Paper key={place.id} variant="outlined" sx={{ p: 2 }}><Typography variant="subtitle2">{place.wb_trbx_id}</Typography><Typography variant="body2" color="text.secondary">{place.length_mm ?? '?'}×{place.width_mm ?? '?'}×{place.height_mm ?? '?'} мм · {place.weight_g ?? '?'} г</Typography>{place.qr_asset ? <Button sx={{ mt: 2 }} disabled={!place.qr_asset.preview_url} onClick={() => openAssetPreview([place.qr_asset!])}>Печать QR грузоместа WB</Button> : <Alert severity="warning" sx={{ mt: 1 }}>QR ещё не готов</Alert>}</Paper>)}</Box>
              </Stack>
            ) : (
              <Paper variant="outlined" sx={{ p: 3 }}><Typography variant="h6">Сдача на склад или СЦ</Typography><Typography variant="body2" color="text.secondary">Грузоместа WB для этого маршрута не создаются. После подтверждённого deliver здесь появится QR поставки.</Typography>{workspace.supply.planned_destination ? <Alert severity="info" sx={{ mt: 2 }}>Внутренний план: {workspace.supply.planned_destination.name}, зона {workspace.supply.planned_destination.zone}</Alert> : null}</Paper>
            )
          ) : null}

          {workspace && stage === 'delivery' ? (
            <Stack spacing={2}>
              <Paper variant="outlined" sx={{ p: 2 }}><Stack direction="row" sx={{ justifyContent: 'space-between', alignItems: 'center' }}><Box><Typography variant="h6">Передача в доставку</Typography><Typography variant="body2" color="text.secondary">Перед каждой передачей выполняется свежая серверная проверка WB.</Typography></Box><Button variant="outlined" startIcon={<RefreshOutlinedIcon />} onClick={() => void checkDelivery()}>Проверить готовность</Button></Stack>{deliveryPreflight ? <Stack spacing={1} sx={{ mt: 2 }}>{deliveryPreflight.checks.map((check) => <Alert key={`${check.code}-${check.order_id ?? ''}`} severity={check.ok ? 'success' : 'error'}>{check.message}</Alert>)}<Stack direction="row" sx={{ justifyContent: 'flex-end' }}><Button variant="contained" size="large" disabled={!deliveryPreflight.can_deliver} onClick={() => void deliver()}>Передать в доставку</Button></Stack></Stack> : null}</Paper>
              {workspace.supply.barcode_asset?.preview_url ? <Paper variant="outlined" sx={{ p: 2, maxWidth: 420 }}><Typography variant="h6">QR поставки WB</Typography><Button sx={{ mt: 1 }} startIcon={<PrintOutlinedIcon />} onClick={() => openAssetPreview([workspace.supply.barcode_asset!])}>Печать QR поставки WB</Button></Paper> : null}
              <Paper variant="outlined" sx={{ p: 2 }}><Stack direction="row" sx={{ justifyContent: 'space-between' }}><Box><Typography variant="h6">Статусы WB</Typography><Typography variant="body2" color="text.secondary">Последняя синхронизация: {workspace.last_wb_sync_at ? new Date(workspace.last_wb_sync_at).toLocaleString('ru-RU') : 'ещё не выполнялась'}</Typography>{workspace.wb_sync_stale ? <Chip label="Данные устарели" color="warning" size="small" sx={{ mt: 1 }} /> : null}</Box><Button onClick={() => void load()} startIcon={<RefreshOutlinedIcon />}>Обновить статусы</Button></Stack><Table size="small" sx={{ mt: 2 }}><TableHead><TableRow><TableCell>Заказ WB</TableCell><TableCell>Товар</TableCell><TableCell>Результат WB</TableCell><TableCell>Повтор / причина</TableCell></TableRow></TableHead><TableBody>{(workspace.tracking_summary?.orders ?? workspace.orders.map((order) => ({ order_id: order.id, wb_order_id: order.wb_order_id, tracking_label: order.wb_status ?? order.status, wb_status: order.wb_status, local_status: order.status }))).map((tracking) => { const order = workspace.orders.find((item) => item.id === tracking.order_id); const rejected = workspace.partial_rejection?.rejected_orders.find((item) => item.order_id === tracking.order_id); return <TableRow key={tracking.order_id}><TableCell>№{tracking.wb_order_id}</TableCell><TableCell>{order?.product.name ?? 'Товар не сопоставлен'}</TableCell><TableCell>{tracking.tracking_label}</TableCell><TableCell>{rejected?.reason ?? (tracking.tracking_label.includes('reject') ? 'Требуется повторная проверка' : '—')}</TableCell></TableRow> })}</TableBody></Table></Paper>
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
    </Dialog>
  )
}
