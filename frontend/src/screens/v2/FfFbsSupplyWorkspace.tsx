import { useCallback, useEffect, useMemo, useRef, useState, type KeyboardEvent, type MouseEvent } from 'react'
import {
  Alert,
  Box,
  Button,
  Checkbox,
  Chip,
  CircularProgress,
  Collapse,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  Divider,
  FormControlLabel,
  IconButton,
  InputAdornment,
  LinearProgress,
  Link,
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
import { FfUnloadPickPage } from '../ff/unload-pick/FfUnloadPickPage'
import CloseIcon from '@mui/icons-material/Close'
import DeleteOutlinedIcon from '@mui/icons-material/DeleteOutlined'
import LocalShippingOutlinedIcon from '@mui/icons-material/LocalShippingOutlined'
import MoreVertOutlinedIcon from '@mui/icons-material/MoreVertOutlined'
import PrintOutlinedIcon from '@mui/icons-material/PrintOutlined'
import QrCodeScannerOutlined from '@mui/icons-material/QrCodeScannerOutlined'
import { apiUrl } from '../../api'
import { ProductPhotoThumb } from '../../components/ProductPhotoThumb'
import { DeadlinePill } from '../../components/fbs/FbsChips'
import { type PackagingTask, type PackagingTaskLine } from '../ff/FfPackagingPage'
import { useMarkingCodePrint } from '../../utils/useMarkingCodePrint'
import { readApiErrorMessage } from '../../utils/readApiErrorMessage'
import type { ProductThermalLabelData } from '../../utils/printProductThermalLabel'
import HistoryOutlinedIcon from '@mui/icons-material/HistoryOutlined'
import { FbsSupplyHistoryDialog } from './FbsSupplyHistoryDialog'
import { FbsPrintPreviewDialog } from './FbsPrintPreviewDialog'
import {
  buildFbsPickingListPrintHtml,
  fbsAccessibleStageIndex,
  fbsBoxEditingDisabled,
  fbsBoxOperationsDisabled,
  fbsDeliveryErrorKeepsIdempotencyKey,
  fbsDeliveryConfirmDisabled,
  fbsOrdersAvailableForBox,
  fbsUnassignedPositionQuantity,
  fbsStageAfterWorkspaceRefresh,
  ordersWord,
  summarizeDeliveryChecks,
} from './fbsUx'
import {
  confirmFbsPrintApplied,
  addFbsOrdersToSupply,
  assignFbsPackingBoxOrders,
  clearFbsPackingBox,
  commitFbsKiz,
  createFbsPackingBoxes,
  createFbsIdempotencyKey,
  deleteFbsOrderKiz,
  deleteFbsPackingBox,
  deliverFbsSupply,
  FbsApiError,
  preflightFbsDelivery,
  fetchFbsPrintBatch,
  fetchFbsWorklist,
  fetchFbsWorkspace,
  lookupFbsOrderBySticker,
  printFbsOrderTape,
  removeFbsPackingBoxOrder,
  retryFbsPackingBoxQr,
  retryFbsSupplyQr,
  skipFbsSupplyHonestSign,
  startFbsSupplyWork,
  undoFbsPick,
  updateFbsSupplyPlannedShipmentDate,
  validateFbsKiz,
  type FbsKizLookup,
  type FbsOrderPrintTapeRequest,
  type FbsPrintAsset,
  type FbsPrintBatch,
  type FbsDeliveryPreflight,
  type FbsWorkspace,
  type FbsWorklistOrder,
} from './fbsApi'

type Props = {
  token: string
  authHeaders: (token: string) => Record<string, string>
  supplyId: string | null
  initialWorkspace?: FbsWorkspace | null
  open: boolean; addressStorageEnabled?: boolean
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
/** Хвост внесённого Честного знака — пустой, значит заказ ещё не сканировали. */
function kizTail(order: FbsWorkspace['orders'][number]): string | null {
  const state = order.metadata.states.find(
    (item) =>
      item.kind === 'sgtin' &&
      item.status !== 'missing' &&
      item.status !== 'rejected',
  )
  return state?.value_tail ?? null
}

function hasOperatorKiz(order: FbsWorkspace['orders'][number]) {
  return order.metadata.states.some(
    (state) =>
      state.kind === 'sgtin' &&
      state.source === 'operator' &&
      state.status !== 'missing' &&
      state.status !== 'rejected',
  )
}

// KIZ-01: инлайновый скан «стикер заказа → Честный знак» прямо в списке упаковки,
// без модалки. Логика ошибок/подсказок скана переиспользована из FbsKizScanDialog.tsx
// (тот диалог не меняется и как запасной путь больше не используется).
type KizScannerDebug = {
  length: number
  first8: string
  last8: string
}

type KizScanError = {
  text: string
  debug: KizScannerDebug | null
}

const KIZ_HINT_TEXT: Record<string, string> = {
  keyboard_layout: 'исправлена раскладка',
  gs_substitute: 'восстановлен разделитель',
  aim_prefix: 'убран префикс сканера',
}

/**
 * Человеческий номер стикера WB вида «5694425 3074»: на печатной этикетке
 * хвост из четырёх цифр набран крупно и жирно, по нему стикер и находят глазами
 * в пачке. Показываем так же, иначе оператор сверяет строку целиком.
 *
 * Если пробела нет (старые записи, чужой формат) — отделяем последние четыре
 * знака: это тот же partB, просто записанный слитно.
 */
export function stickerCodeParts(code: string | null): { head: string; tail: string } | null {
  const value = (code ?? '').trim()
  if (!value) return null
  const spaced = value.lastIndexOf(' ')
  if (spaced > 0) {
    return { head: value.slice(0, spaced), tail: value.slice(spaced + 1) }
  }
  if (value.length <= 4) return { head: '', tail: value }
  return { head: value.slice(0, -4), tail: value.slice(-4) }
}

function kizErrorTextByCode(code: string, message: string, context: unknown): string {
  if (code === 'sticker_not_found') return 'Стикер не найден в этой поставке'
  if (code === 'order_frozen') return 'Заказ уже передан в доставку — КИЗ не изменить'
  if (code === 'duplicate_kiz') {
    const details = context as { wb_order_id?: number; created_at?: string } | null
    const order = details?.wb_order_id ? ` в заказ № ${details.wb_order_id}` : ''
    const when = details?.created_at
      ? ` от ${new Date(details.created_at).toLocaleDateString('ru-RU')}`
      : ''
    return `Этот КИЗ уже внесён${order}${when}`
  }
  if (code === 'needs_confirmation') {
    const details = context as { current_kiz?: string } | null
    const current = details?.current_kiz ? ` ${details.current_kiz}` : ''
    return `На этот заказ уже есть ЧЗ${current}. Внести другой КИЗ?`
  }
  if (code === 'not_a_kiz') return 'Это не похоже на Честный знак'
  if (code === 'meta_validation_fail') return `WB не принял: ${message}`
  if (code.startsWith('wb_')) return 'WB недоступен, попробуйте ещё раз'
  return message
}

function kizErrorText(cause: unknown): string {
  if (cause instanceof FbsApiError) {
    return kizErrorTextByCode(cause.code, cause.message, cause.context)
  }
  return cause instanceof Error ? cause.message : 'Не удалось выполнить операцию'
}

function kizScannerDebug(cause: unknown): KizScannerDebug | null {
  if (!(cause instanceof FbsApiError) || cause.code !== 'not_a_kiz') return null
  if (!cause.context || typeof cause.context !== 'object') return null
  const debug = (cause.context as { debug?: unknown }).debug
  if (!debug || typeof debug !== 'object') return null
  const row = debug as { length?: unknown; first8?: unknown; last8?: unknown }
  if (
    typeof row.length !== 'number' ||
    typeof row.first8 !== 'string' ||
    typeof row.last8 !== 'string'
  ) {
    return null
  }
  return { length: row.length, first8: row.first8, last8: row.last8 }
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

async function renderBoxQrDataUrl(value: string): Promise<string> {
  const bwipjs = await import('bwip-js')
  const canvas = document.createElement('canvas')
  bwipjs.toCanvas(canvas, {
    bcid: 'qrcode',
    text: value,
    scale: 5,
    includetext: false,
  })
  return canvas.toDataURL('image/png')
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
  open, addressStorageEnabled = true,
  onClose,
}: Props) {
  const [workspace, setWorkspace] = useState<FbsWorkspace | null>(initialWorkspace ?? null)
  const [stage, setStage] = useState<StageKey>('composition')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [notice, setNotice] = useState<string | null>(null)
  // История заказа открывается прямо из состава поставки: оператор смотрит,
  // что с заказом происходило, там же, где увидел сам заказ.
  const [historyOpen, setHistoryOpen] = useState(false)
  const [printBatch, setPrintBatch] = useState<FbsPrintBatch | null>(null)
  const [printPreviewOpen, setPrintPreviewOpen] = useState(false)
  const [packagingTask, setPackagingTask] = useState<PackagingTask | null>(null)
  const [boxCount, setBoxCount] = useState('1')
  const [boxesWithoutDistribution, setBoxesWithoutDistribution] = useState(false)
  const [boxAssignTarget, setBoxAssignTarget] = useState<string | null>(null)
  const [boxProductSearch, setBoxProductSearch] = useState('')
  const [boxProductQty, setBoxProductQty] = useState<Record<string, string>>({})
  const [boxSelectedPositionIds, setBoxSelectedPositionIds] = useState<Set<string>>(() => new Set())
  const [boxMenu, setBoxMenu] = useState<{ boxId: string; anchorEl: HTMLElement } | null>(null)
  const [expandedBoxIds, setExpandedBoxIds] = useState<Set<string>>(() => new Set())
  const deliveryKeyRef = useRef(createFbsIdempotencyKey())
  const [deliverySubmitted, setDeliverySubmitted] = useState(false)
  const [deliverConfirmOpen, setDeliverConfirmOpen] = useState(false)
  const [deliveryPreflight, setDeliveryPreflight] = useState<FbsDeliveryPreflight | null>(null)
  const [deliveryPreflightLoading, setDeliveryPreflightLoading] = useState(false)
  const [deliveryPreflightError, setDeliveryPreflightError] = useState<string | null>(null)
  const [undoOrderId, setUndoOrderId] = useState<string | null>(null)
  const [retryAction, setRetryAction] = useState<(() => void) | null>(null)
  const [tzLine, setTzLine] = useState<PackagingTaskLine | null>(null)
  const [reprintMenu, setReprintMenu] = useState<{ orderId: string; anchorEl: HTMLElement } | null>(null)
  const [kizUndoOrderId, setKizUndoOrderId] = useState<string | null>(null)
  const [kizScanActive, setKizScanActive] = useState<FbsKizLookup | null>(null)
  const [kizScanValue, setKizScanValue] = useState('')
  // Ссылки на строки заказов: после скана стикера подкручиваем список к нужной,
  // иначе в поставке на 26 позиций оператор не понимает, какая строка ожила.
  const kizRowRefs = useRef<Record<string, HTMLDivElement | null>>({})

  useEffect(() => {
    if (!kizScanActive) return
    kizRowRefs.current[kizScanActive.order_id]?.scrollIntoView({ block: 'center', behavior: 'smooth' })
  }, [kizScanActive])
  const [kizScanBusy, setKizScanBusy] = useState(false)
  const [kizScanError, setKizScanError] = useState<KizScanError | null>(null)
  const [kizScanHints, setKizScanHints] = useState<string[]>([])
  const [kizScanDebugOpen, setKizScanDebugOpen] = useState(false)
  const [kizConfirmTarget, setKizConfirmTarget] = useState<FbsKizLookup | null>(null)
  const kizScanInputRef = useRef<HTMLInputElement | null>(null)
  const [addOrdersOpen, setAddOrdersOpen] = useState(false)
  const [addableOrders, setAddableOrders] = useState<FbsWorklistOrder[]>([])
  const [addableSelected, setAddableSelected] = useState<Set<string>>(() => new Set())
  const [addOrdersBusy, setAddOrdersBusy] = useState(false)
  const [plannedShipmentDateDraft, setPlannedShipmentDateDraft] = useState('')
  const [skipHonestSignOpen, setSkipHonestSignOpen] = useState(false)
  const [skipHonestSignBusy, setSkipHonestSignBusy] = useState(false)
  const { openPrint, dialog: markingPrintDialog } = useMarkingCodePrint()
  const isOzonSupply = workspace?.supply.marketplace === 'ozon'
  const providerName = isOzonSupply ? 'Ozon' : 'WB'
  const boxOperationsDisabled = fbsBoxOperationsDisabled(
    workspace?.supply.marketplace ?? 'wb',
  )

  const load = useCallback(
    async (silent = false) => {
      if (!supplyId) return
      if (!silent) setBusy(true)
      try {
        const next = await fetchFbsWorkspace(token, authHeaders, supplyId)
        setWorkspace(next)
        if (!silent) {
          setStage((current) => fbsStageAfterWorkspaceRefresh(
            next.supply.marketplace,
            current,
            visualStage(next.stage),
          ))
        }
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
    const restoredDeliveryKey = persistentOperationKey(supplyId, 'delivery')
    deliveryKeyRef.current = restoredDeliveryKey
    setPrintBatch(null)
    setBoxCount('1')
    setBoxesWithoutDistribution(false)
    setBoxAssignTarget(null)
    setBoxProductSearch('')
    setBoxProductQty({})
    setBoxSelectedPositionIds(new Set())
    setBoxMenu(null)
    setExpandedBoxIds(new Set())
    setDeliverySubmitted(false)
    setUndoOrderId(null)
    setTzLine(null)
    setReprintMenu(null)
    setAddOrdersOpen(false)
    setAddableOrders([])
    setAddableSelected(new Set())
    setKizScanActive(null)
    setKizScanValue('')
    setKizScanBusy(false)
    setKizScanError(null)
    setKizScanHints([])
    setKizScanDebugOpen(false)
    setKizConfirmTarget(null)
    if (!initialWorkspace) void load()
  }, [open, supplyId, initialWorkspace, load])

  useEffect(() => {
    setNotice(null)
  }, [workspace?.stage])

  useEffect(() => {
    setPlannedShipmentDateDraft(workspace?.supply.planned_shipment_date ?? '')
  }, [workspace?.supply.planned_shipment_date])

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
  }, [open, stage, workspace?.supply.packaging_task_id, workspace?.orders.length, token, authHeaders])

  const run = async (
    operation: () => Promise<FbsWorkspace>,
    success: string,
    onError?: (cause: unknown) => void,
  ) => {
    setBusy(true)
    setError(null)
    setNotice(null)
    setRetryAction(null)
    try {
      const next = await operation()
      setWorkspace(next)
      setStage((current) => fbsStageAfterWorkspaceRefresh(
        next.supply.marketplace,
        current,
        visualStage(next.stage),
      ))
      if (success) setNotice(success)
      return next
    } catch (cause) {
      onError?.(cause)
      setError(cause instanceof Error ? cause.message : 'Операция не выполнена.')
      if (cause instanceof FbsApiError && cause.retryable) {
        setRetryAction(() => () => { void run(operation, success, onError) })
      }
      return null
    } finally {
      setBusy(false)
    }
  }

  const openAddOrders = async () => {
    if (!workspace) return
    setAddOrdersOpen(true)
    setAddOrdersBusy(true)
    setAddableSelected(new Set())
    setError(null)
    try {
      const page = await fetchFbsWorklist(token, authHeaders, {
        seller_id: workspace.supply.seller.id,
        status_group: 'new',
        wb_warehouse_id: String(workspace.supply.wb_warehouse.id),
        limit: 500,
      })
      setAddableOrders(page.items.filter((order) => order.selection_blockers.length === 0))
    } catch (cause) {
      setAddableOrders([])
      setError(cause instanceof Error ? cause.message : 'Не удалось загрузить новые заказы для поставки.')
    } finally {
      setAddOrdersBusy(false)
    }
  }

  const addOrdersToCurrentSupply = async () => {
    if (!workspace || addableSelected.size === 0) return
    setAddOrdersBusy(true)
    setError(null)
    try {
      const next = await addFbsOrdersToSupply(token, authHeaders, workspace.supply.id, {
        order_ids: [...addableSelected],
        idempotency_key: createFbsIdempotencyKey(),
      })
      setWorkspace(next)
      // Добавление заказа — обычное обновление, а не повод вернуть оператора
      // назад. Сервер отдаёт «подбор», пока новый заказ не подобран, и прямой
      // setStage перекидывал человека с упаковки или коробов на подбор. Правило
      // проекта: серверные факты не управляют навигацией в рабочем месте WB.
      setStage((current) => fbsStageAfterWorkspaceRefresh(
        next.supply.marketplace,
        current,
        visualStage(next.stage),
      ))
      setAddOrdersOpen(false)
      setAddableSelected(new Set())
      setNotice('Заказы добавлены в поставку.')
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'Не удалось добавить заказы в поставку.')
    } finally {
      setAddOrdersBusy(false)
    }
  }

  const savePlannedShipmentDate = async () => {
    if (!workspace) return
    const raw = plannedShipmentDateDraft.trim()
    const next = await run(
      () => updateFbsSupplyPlannedShipmentDate(token, authHeaders, workspace.supply.id, raw || null),
      raw ? 'Дата отгрузки сохранена.' : 'Дата отгрузки очищена.',
    )
    if (next) setPlannedShipmentDateDraft(next.supply.planned_shipment_date ?? '')
  }


  // KIZ-01: сканер стреляет в активное поле; пока запрос идёт, поле disabled и фокус
  // теряется — без возврата фокуса следующий скан уходит в никуда. Тот же приём,
  // что и в FbsKizScanDialog.tsx (см. его refocus()).
  const refocusKizInput = useCallback(() => {
    let attempts = 0
    const focus = () => {
      const input = kizScanInputRef.current
      input?.focus()
      attempts += 1
      if (input != null && document.activeElement !== input && attempts < 8) {
        window.setTimeout(focus, 50)
      }
    }
    window.setTimeout(focus, 0)
  }, [])

  const scanKizSticker = useCallback(
    async (raw: string) => {
      if (!workspace) return
      setKizScanBusy(true)
      setKizScanError(null)
      setKizScanHints([])
      setKizScanDebugOpen(false)
      try {
        const found = await lookupFbsOrderBySticker(token, authHeaders, workspace.supply.id, raw)
        if (!found.can_bind) {
          setKizScanError({ text: found.block_reason ?? 'На этот заказ КИЗ внести нельзя', debug: null })
          setKizScanValue('')
          return
        }
        if (found.needs_confirmation) setKizConfirmTarget(found)
        else setKizScanActive(found)
        setKizScanValue('')
      } catch (cause) {
        setKizScanError({ text: kizErrorText(cause), debug: kizScannerDebug(cause) })
        setKizScanValue('')
      } finally {
        setKizScanBusy(false)
        refocusKizInput()
      }
    },
    [workspace, token, authHeaders, refocusKizInput],
  )

  const scanKizCode = useCallback(
    async (raw: string) => {
      if (!kizScanActive) return
      setKizScanBusy(true)
      setKizScanError(null)
      setKizScanHints([])
      setKizScanDebugOpen(false)
      try {
        const validated = await validateFbsKiz(token, authHeaders, kizScanActive.order_id, raw)
        setKizScanHints(validated.hints)
        const results = await commitFbsKiz(
          token,
          authHeaders,
          [{ order_id: kizScanActive.order_id, value: raw, confirmed: kizScanActive.needs_confirmation }],
          createFbsIdempotencyKey(),
        )
        const outcome = results.find((item) => item.order_id === kizScanActive.order_id)
        if (outcome && outcome.status !== 'ok') {
          setKizScanError({
            text: kizErrorTextByCode(outcome.code ?? '', outcome.message ?? 'Не сохранено', null),
            debug: null,
          })
          setKizScanValue('')
          return
        }
        setKizScanActive(null)
        setKizScanValue('')
        await load(true)
      } catch (cause) {
        setKizScanError({ text: kizErrorText(cause), debug: kizScannerDebug(cause) })
        setKizScanValue('')
      } finally {
        setKizScanBusy(false)
        refocusKizInput()
      }
    },
    [kizScanActive, token, authHeaders, refocusKizInput, load],
  )

  const onKizScanEnter = useCallback(
    (event: KeyboardEvent<HTMLInputElement>) => {
      if (event.key !== 'Enter' || kizScanBusy) return
      event.preventDefault()
      const raw = kizScanValue.trim()
      if (!raw) return
      if (kizScanActive) void scanKizCode(raw)
      else void scanKizSticker(raw)
    },
    [kizScanBusy, kizScanValue, kizScanActive, scanKizCode, scanKizSticker],
  )

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
        setError(`${providerName} не вернул готовых этикеток заказов. Печать не открыта.`)
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

  const openBoxQrPreview = async (box: FbsWorkspace['boxes'][number]) => {
    if (boxOperationsDisabled) return
    setBusy(true)
    setError(null)
    try {
      const asset: FbsPrintAsset = {
        id: `box-qr-${box.id}`,
        kind: 'box_qr',
        status: 'ready',
        content_type: 'image/png',
        width_mm: 58,
        height_mm: 40,
        preview_url: await renderBoxQrDataUrl(box.barcode),
        download_url: null,
        checksum: null,
        applied_at: null,
        error: null,
      }
      setPrintBatch({
        requested: 1,
        ready: 1,
        missing: 0,
        failed: 0,
        assets: [asset],
        order_errors: [],
      })
      setPrintPreviewOpen(true)
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'QR короба не подготовлен.')
    } finally {
      setBusy(false)
    }
  }

  // Лента QR всех коробов: то же, что делает кнопка «QR» у отдельного короба,
  // только разом. Берём настоящий стикер грузоместа от WB, свой QR из внутреннего
  // штрихкода рисуем лишь для коробов без грузоместа — как и в одиночной кнопке.
  const openAllBoxQrPreview = async () => {
    if (boxOperationsDisabled) return
    const boxes = workspace?.boxes ?? []
    if (boxes.length === 0) return
    if (isOzonSupply) {
      const assets = [...new Map(boxes.flatMap((box) => box.qr_asset?.status === 'ready' && box.qr_asset.preview_url ? [[box.qr_asset.id, box.qr_asset] as const] : [])).values()]
      if (assets.length === 0) {
        setError('Этикетки Ozon ещё не готовы. Нажмите QR у короба, чтобы собрать заказ и получить этикетки.')
        return
      }
      openAssetPreview(assets)
      return
    }
    const notReady = boxes.filter((box) => box.wb_trbx_id && !box.qr_asset?.preview_url)
    setBusy(true)
    setError(null)
    try {
      const assets: FbsPrintAsset[] = []
      for (const box of boxes) {
        if (box.wb_trbx_id) {
          if (box.qr_asset?.preview_url) assets.push(box.qr_asset)
          continue
        }
        assets.push({
          id: `box-qr-${box.id}`,
          kind: 'box_qr',
          status: 'ready',
          content_type: 'image/png',
          width_mm: 58,
          height_mm: 40,
          preview_url: await renderBoxQrDataUrl(box.barcode),
          download_url: null,
          checksum: null,
          applied_at: null,
          error: null,
        })
      }
      if (assets.length === 0) {
        setError('QR грузомест ещё не получены от WB — откройте QR любого короба, чтобы запросить.')
        return
      }
      if (notReady.length > 0) {
        setNotice(`QR ${notReady.length} коробов ещё не готов — печатаются остальные ${assets.length}.`)
      }
      openAssetPreview(assets)
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'QR коробов не подготовлены.')
    } finally {
      setBusy(false)
    }
  }

  const createBoxes = async () => {
    if (!workspace || boxOperationsDisabled) return
    const count = Math.min(100, Math.max(1, Number(boxCount) || 1))
    const boxMode = !isOzonSupply && boxesWithoutDistribution ? 'no-distribution' : 'distribution'
    const key = persistentOperationKey(workspace.supply.id, 'box-create', `${boxMode}:${count}`)
    const next = await run(
      () => createFbsPackingBoxes(token, authHeaders, workspace.supply.id, {
        count,
        idempotency_key: key,
        without_distribution: !isOzonSupply && boxesWithoutDistribution,
      }),
      '',
    )
    if (next) clearPersistentOperationKey(workspace.supply.id, 'box-create', `${boxMode}:${count}`)
  }

  const assignBoxOrders = async () => {
    if (boxOperationsDisabled || !workspace || !boxAssignTarget || (isOzonSupply ? boxAssignSelectedPositionIds.length === 0 : boxAssignSelectedOrderIds.length === 0)) return
    const next = await run(
      () => assignFbsPackingBoxOrders(token, authHeaders, workspace.supply.id, boxAssignTarget, isOzonSupply ? [] : boxAssignSelectedOrderIds, isOzonSupply ? boxAssignSelectedPositionIds : undefined),
      '',
    )
    if (next) {
      setBoxAssignTarget(null)
      setBoxProductSearch('')
      setBoxProductQty({})
      setBoxSelectedPositionIds(new Set())
      setExpandedBoxIds((current) => new Set(current).add(boxAssignTarget))
      setStage('boxes')
    }
  }

  const removeBoxOrders = async (boxId: string, orderIds: string[], orderProductId?: string) => {
    if (boxOperationsDisabled || !workspace || orderIds.length === 0) return
    await run(
      async () => {
        let next = workspace
        for (const orderId of orderIds) {
          next = await removeFbsPackingBoxOrder(token, authHeaders, workspace.supply.id, boxId, orderId, orderProductId)
        }
        return next
      },
      '',
    )
  }

  const clearBox = async (boxId: string) => {
    if (!workspace || boxOperationsDisabled) return
    setBoxMenu(null)
    await run(
      () => clearFbsPackingBox(token, authHeaders, workspace.supply.id, boxId),
      '',
    )
  }

  const deleteBox = async (boxId: string) => {
    if (!workspace || boxOperationsDisabled) return
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
    if (!workspace || boxOperationsDisabled) return
    const next = await run(
      () => retryFbsPackingBoxQr(token, authHeaders, workspace.supply.id, boxId),
      '',
    )
    if (!next) return
    setStage('boxes')
    const box = next.boxes.find((item) => item.id === boxId)
    if (box?.qr_asset?.status === 'ready' && box.qr_asset.preview_url) openAssetPreview([box.qr_asset])
    else if (isOzonSupply) setNotice(box?.qr_asset?.error?.message ?? 'Этикетки Ozon ещё не готовы — нажмите QR повторно через минуту.')
  }

  const deliver = async () => {
    if (!workspace || deliveryConfirmed) return
    const next = await run(
      () =>
        deliverFbsSupply(token, authHeaders, workspace.supply.id, {
          // RetryAction stores this callback.  Read the current ref at click
          // time so a definitive failure cannot replay the key that the error
          // handler has already replaced.
          idempotency_key: deliveryKeyRef.current,
          confirmed_preflight_version: deliveryPreflight?.version,
      }),
      '',
      (cause) => {
        if (
          cause instanceof FbsApiError
          && fbsDeliveryErrorKeepsIdempotencyKey(cause)
        ) return
        clearPersistentOperationKey(workspace.supply.id, 'delivery')
        const replacementKey = persistentOperationKey(workspace.supply.id, 'delivery')
        deliveryKeyRef.current = replacementKey
      },
    )
    if (next) {
      clearPersistentOperationKey(workspace.supply.id, 'delivery')
      const nextKey = createFbsIdempotencyKey()
      deliveryKeyRef.current = nextKey
      setDeliverySubmitted(true)
      setStage('boxes')
    }
  }

  const openDeliveryConfirmation = async () => {
    if (!workspace) return
    setDeliverConfirmOpen(true)
    setDeliveryPreflight(null)
    setDeliveryPreflightError(null)
    setDeliveryPreflightLoading(true)
    try {
      setDeliveryPreflight(await preflightFbsDelivery(token, authHeaders, workspace.supply.id))
    } catch (cause) {
      setDeliveryPreflightError(
        cause instanceof Error ? cause.message : `Не удалось получить ответ ${providerName}.`,
      )
    } finally {
      setDeliveryPreflightLoading(false)
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
    // Если поставка помечена как честный знак пропущен, требование снято со всей поставки.
    if (workspace?.supply.honest_sign_skipped) return false
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
        sellerId: workspace.supply.seller.id,
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
        sellerId: workspace?.supply.seller.id,
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
      const done = await fetch(apiUrl(`/operations/packaging-tasks/${packagingTask.id}/pack-all-and-complete`), {
        method: 'POST',
        headers: authHeaders(token),
      })
      if (!done.ok) {
        setError(await readApiErrorMessage(done))
        return
      }
      const packed = (await done.json()) as {
        packaging_task: PackagingTask
        warnings?: string[] | null
      }
      setPackagingTask(packed.packaging_task)
      setNotice(
        (packed.warnings?.length ?? 0) > 0
          ? `Упаковка завершена. ${packed.warnings?.join(' ')}`
          : 'Упаковка завершена.',
      )
      await load()
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'Не удалось завершить упаковку.')
    } finally {
      setBusy(false)
    }
  }

  const performSkipHonestSign = async () => {
    if (!workspace) return
    setSkipHonestSignBusy(true)
    setError(null)
    try {
      const next = await skipFbsSupplyHonestSign(token, authHeaders, workspace.supply.id)
      setWorkspace(next)
      setSkipHonestSignOpen(false)
      setNotice('Требование Честного знака снято со всей поставки.')
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'Не удалось снять требование Честного знака.')
    } finally {
      setSkipHonestSignBusy(false)
    }
  }

  const total = workspace?.progress.total ?? 0
  const ready = workspace
    ? workspace.supply.marketplace === 'wb'
      ? total
      : Math.min(
        total,
        workspace.progress.picked,
        workspace.progress.packed,
        workspace.progress.metadata_ready,
        workspace.progress.stickers_ready,
      )
    : 0
  const percent = total ? Math.round((ready / total) * 100) : 0
  const fullTapeOrders = useMemo(() => {
    if (!workspace) return []
    return [...workspace.orders].sort((a, b) => a.tape_order_index - b.tape_order_index)
  }, [workspace])
  const pickingRows = useMemo(() => {
    if (!workspace) return []
    const grouped = new Map<string, {
      key: string
      name: string
      size: string | null
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
    for (const order of fullTapeOrders) {
      const key = order.product.id ?? `unmapped-${order.id}`
      const current = grouped.get(key) ?? {
        key,
        name: order.product.name,
        size: order.product.size,
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
  }, [fullTapeOrders, workspace])
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
      printedAtLabel: new Date().toLocaleString('ru-RU'), addressStorageEnabled,
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
      (Boolean(order.sticker.applied_at) || STICKER_PRINTED_STATUSES.includes(order.sticker.status)) &&
      isOrderMarkingReady(order),
    [],
  )

  const printedOrdersCount = packingOrders.filter(orderPrintDone).length
  const unprintedPackingOrders = packingOrders.filter((order) => !orderPrintDone(order))
  const markingShortOrderIds = new Set(workspace?.marking_pool?.orders_without_code ?? [])
  // Строка скана КИЗ доступна на любой поставке и любом товаре, без оглядки на
  // признак маркировки в карточке и на requiredMeta от WB. Если Честный знак
  // физически наклеен на товаре — значит товар маркированный, и спрашивать об
  // этом систему незачем: раньше признак не доезжал (он читается из строки
  // задания упаковки), строка скана не появлялась и КИЗ не уходили в WB вовсе.
  const anyOrderNeedsHonestSign = packingOrders.length > 0

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
  const accessibleStageIndex = workspace
    ? fbsAccessibleStageIndex({
      marketplace: workspace.supply.marketplace,
      currentStage,
    })
    : currentStageIndex
  const stageIsCurrent = stage === currentStage
  const allPicked = Boolean(workspace && workspace.progress.total > 0 && workspace.progress.picked === workspace.progress.total)
  const deliveryConfirmed = deliverySubmitted
    || workspace?.stage === 'tracking'
    || ['in_delivery', 'done'].includes(workspace?.supply.status ?? '')
  const wbOrderIdByOrderId = new Map((workspace?.orders ?? []).map((order) => [order.id, order.wb_order_id]))
  const deliveryChecks = summarizeDeliveryChecks(deliveryPreflight?.checks ?? [], wbOrderIdByOrderId)
  const packagingEditable = !deliveryConfirmed
  // Короба — рабочая поверхность, а не ступень после упаковки. Серверный stage
  // не гасит действия внутри открытой вкладки; редактирование прекращается
  // только после передачи поставки.
  const boxEditingDisabled = fbsBoxEditingDisabled(
    workspace?.supply.marketplace ?? 'wb',
    deliveryConfirmed,
  )
  const assignedBoxOrderIds = new Set(workspace?.boxes.flatMap((box) => box.assigned_order_ids) ?? [])
  const availableForBox = fbsOrdersAvailableForBox(workspace?.orders ?? [], assignedBoxOrderIds)
  const boxAssignBox = workspace?.boxes.find((box) => box.id === boxAssignTarget)
  const boxAssignName = boxAssignBox?.box_number
  const assignedBoxPositionIds = new Set(workspace?.boxes.flatMap((box) => box.assigned_order_product_ids ?? []) ?? [])
  const ozonPositionRows = (workspace?.orders ?? []).flatMap((order) => order.positions.flatMap((position) => position.id ? [{ order, position, id: position.id }] : []))
  const boxAssignSelectedPositionIds = ozonPositionRows.filter((row) => boxSelectedPositionIds.has(row.id) && !assignedBoxPositionIds.has(row.id)).map((row) => row.id)
  const boxAssignOrderId = boxAssignBox?.assigned_order_ids[0] ?? ozonPositionRows.find((row) => boxAssignSelectedPositionIds.includes(row.id))?.order.id
  const ozonBoxAssignOrders = (workspace?.orders ?? []).map((order) => ({
    order,
    positions: order.positions.filter((position) => position.id && !assignedBoxPositionIds.has(position.id)),
  })).filter(({ order, positions }) => positions.length > 0 && (!boxProductSearch.trim() || `${order.external_order_id} ${positions.map((position) => `${position.name} ${position.seller_article ?? ''} ${position.sku ?? ''}`).join(' ')}`.toLocaleLowerCase('ru').includes(boxProductSearch.trim().toLocaleLowerCase('ru'))))
  const reprintOrder = workspace?.orders.find((order) => order.id === reprintMenu?.orderId) ?? null
  const reprintLine = reprintOrder?.product.id ? packLineByProduct.get(reprintOrder.product.id) : undefined
  const boxMenuBox = workspace?.boxes.find((box) => box.id === boxMenu?.boxId) ?? null
  const boxMenuAssignedCount = boxMenuBox?.assigned_order_ids.length ?? 0
  const boxRouteLabel = isOzonSupply ? 'Ozon' : workspace?.supply.delivery_type === 'pvz' ? 'ПВЗ' : 'Склад / СЦ'
  const hasNoDistributionBoxes = Boolean(workspace?.boxes.some((box) => box.without_distribution))
  const boxDistributedCount = isOzonSupply ? ozonPositionRows.reduce((sum, row) => sum + (assignedBoxPositionIds.has(row.id) ? row.position.quantity : 0), 0) : assignedBoxOrderIds.size
  const boxTotalCount = isOzonSupply ? (workspace?.orders ?? []).reduce((sum, order) => sum + order.positions.reduce((qty, position) => qty + position.quantity, 0), 0) : workspace?.progress.total ?? 0
  const boxRemainingCount = Math.max(0, boxTotalCount - boxDistributedCount)
  const supplyQrAsset = workspace?.supply.barcode_asset ?? null
  const needsSupplyQr = Boolean(workspace?.supply)
  // A cargo-place QR is available per-box whenever WB registered a cargo
  // place for that box — this is no longer PVZ-only (warehouse/SC boxes get
  // one too), so branch on the box's own wb_trbx_id, not delivery_type.
  const hasCargoPlaceBoxes = Boolean(workspace?.boxes.some((box) => box.wb_trbx_id))
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

  /** Почему нельзя перейти к следующему этапу — то же объяснение и для disabled-вкладки, и для кнопки «Далее». */
  function stageBlockedExplanation(fromStage: StageKey): string {
    if (fromStage === 'composition') {
      return 'Начните работу с поставкой, чтобы перейти к подбору.'
    }
    if (fromStage === 'picking') {
      const remaining = Math.max(0, total - (workspace?.progress.picked ?? 0))
      return `Подберите ещё ${remaining} шт., чтобы перейти к упаковке.`
    }
    if (fromStage === 'packing') {
      if (workspace?.supply.marketplace === 'wb') return ''
      const remainingToPack = Math.max(0, total - (workspace?.progress.packed ?? 0))
      if (remainingToPack > 0) return `Нужно упаковать ещё ${remainingToPack} шт., чтобы перейти к коробам.`
      return ''
    }
    return ''
  }

  /**
   * Кнопка перехода к следующему этапу — крупная и заметная, ведёт туда же, куда клик по
   * следующей вкладке, и разблокирована ровно тогда же (см. Tabs.onChange ниже). Когда
   * следующий этап ещё недоступен, кнопка не пропадает, а объясняет, чего не хватает —
   * это важнее самой кнопки.
   */
  function nextStageControl(fromStage: StageKey) {
    const fromIndex = STAGES.findIndex((item) => item.key === fromStage)
    const next = STAGES[fromIndex + 1]
    if (!next) return null
    const unlocked = fromIndex + 1 <= accessibleStageIndex
    const reason = stageBlockedExplanation(fromStage)
    const button = (
      <Button
        variant="contained"
        size="large"
        disabled={!unlocked || busy}
        onClick={() => {
          setStage(next.key)
          setError(null)
          setNotice(null)
        }}
        data-testid={`fbs-stage-next-${fromStage}`}
      >
        {`Далее: ${next.label} →`}
      </Button>
    )
    return (
      <Stack direction="row" sx={{ justifyContent: 'flex-end', mt: 1 }}>
        <Stack spacing={0.75} sx={{ alignItems: 'flex-end', maxWidth: 480 }}>
          {unlocked ? button : (
            <Tooltip title={reason}>
              <span>{button}</span>
            </Tooltip>
          )}
          {!unlocked ? (
            <Typography
              variant="body2"
              color="text.secondary"
              sx={{ textAlign: 'right' }}
              data-testid={`fbs-stage-next-${fromStage}-reason`}
            >
              {reason}
            </Typography>
          ) : null}
        </Stack>
      </Stack>
    )
  }

  const partialRejectionAlert = workspace?.partial_rejection?.rejected_orders?.length ? (
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
      {workspace?.supply.source === 'wb' ? (
        <Alert
          severity="error"
          variant="filled"
          sx={{ borderRadius: 0, fontWeight: 700 }}
          data-testid="fbs-supply-from-seller-cabinet"
        >
          Поставка собрана в кабинете продавца. Работать с ней можно как с обычной,
          но её состав меняет продавец, а не мы — перед передачей сверьте заказы.
        </Alert>
      ) : null}
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
                    ? `${workspace.supply.seller.name}${workspace.supply.wb_supply_id ? ` · № ${providerName} ${workspace.supply.wb_supply_id}` : ''}`
                    : 'Загружаем данные поставки…'}
                </Typography>
              </Box>
              {workspace ? (
                <Stack direction="row" spacing={3} sx={{ flexWrap: 'wrap' }} useFlexGap>
                  <Metric label="Склад WMS" value={workspace.supply.wms_warehouse.name} />
                  <Metric label="Маршрут" value={workspace.supply.delivery_type === 'pvz' ? 'ПВЗ' : 'Склад / СЦ'} />
                  <Stack
                    direction="row"
                    spacing={1}
                    sx={{ alignItems: 'center' }}
                    data-testid="cal-02-fbs-shipment-date-control"
                    data-task-id="CAL-02"
                  >
                    <TextField
                      label="Дата отгрузки"
                      type="date"
                      size="small"
                      value={plannedShipmentDateDraft}
                      onChange={(event) => setPlannedShipmentDateDraft(event.target.value)}
                      disabled={busy}
                      slotProps={{
                        inputLabel: { shrink: true },
                        htmlInput: { 'data-testid': 'cal-02-fbs-shipment-date' },
                      }}
                      sx={{ width: 176 }}
                      data-task-id="CAL-02"
                    />
                    <Button
                      size="small"
                      variant="outlined"
                      onClick={() => void savePlannedShipmentDate()}
                      disabled={busy || plannedShipmentDateDraft === (workspace.supply.planned_shipment_date ?? '')}
                      data-testid="cal-02-fbs-shipment-date-save"
                      data-task-id="CAL-02"
                    >
                      Сохранить
                    </Button>
                    {workspace.supply.planned_shipment_date ? (
                      <Button
                        size="small"
                        variant="text"
                        onClick={() => {
                          setPlannedShipmentDateDraft('')
                          void run(
                            () => updateFbsSupplyPlannedShipmentDate(token, authHeaders, workspace.supply.id, null),
                            'Дата отгрузки очищена.',
                          )
                        }}
                        disabled={busy}
                        data-testid="cal-02-fbs-shipment-date-clear"
                        data-task-id="CAL-02"
                      >
                        Очистить
                      </Button>
                    ) : null}
                  </Stack>
                </Stack>
              ) : null}
            </Stack>
            <Stack direction="row" spacing={1.5} sx={{ alignItems: 'center', mt: 1.25 }}>
              <LinearProgress variant="determinate" value={percent} sx={{ flex: 1, maxWidth: 480, height: 8, borderRadius: 4 }} />
              <Typography variant="caption" sx={{ fontWeight: 750 }}>{ready} из {total} подготовлено к отгрузке</Typography>
              {workspace ? (
                <Stack direction="row" spacing={1} sx={{ alignItems: 'center' }}>
                  <Typography variant="caption" color="text.secondary">
                    Сдать в {isOzonSupply ? 'Ozon' : 'Wildberries'} до {new Date(workspace.supply.nearest_deadline_at).toLocaleString('ru-RU')}
                  </Typography>
                  <DeadlinePill deadlineAt={workspace.supply.nearest_deadline_at} serverNow={workspace.server_now} marketplace={workspace.supply.marketplace} />
                </Stack>
              ) : null}
            </Stack>
          </Box>
          <IconButton onClick={onClose} disabled={busy} aria-label="Закрыть">
            <CloseIcon />
          </IconButton>
        </Stack>
      </Box>

      {/* История поставки нужна на любом этапе, а не только в составе: когда
          что-то пошло не так, оператор смотрит хронологию там, где стоит. */}
      <Box sx={{ px: 2, pb: 1 }}>
        <Button
          size="small"
          variant="text"
          startIcon={<HistoryOutlinedIcon fontSize="small" />}
          onClick={() => setHistoryOpen(true)}
          data-testid="fbs-supply-history-open"
        >
          История поставки
        </Button>
      </Box>

      <Tabs
        value={stage}
        onChange={(_, value) => {
          if (STAGES.findIndex((item) => item.key === value) <= accessibleStageIndex) setStage(value)
          setError(null)
          setNotice(null)
        }}
        variant="scrollable"
        scrollButtons="auto"
        sx={{ px: 2, borderBottom: 1, borderColor: 'divider', bgcolor: 'rgba(91,33,182,.035)' }}
      >
        {STAGES.map((item, index) => {
          const locked = index > accessibleStageIndex
          const tab = (
            <Tab
              key={item.key}
              value={item.key}
              label={index < currentStageIndex ? `${item.label} ✓` : item.label}
              disabled={locked}
            />
          )
          if (!locked) return tab
          return (
            <Tooltip key={item.key} title={stageBlockedExplanation(currentStage)}>
              <span>{tab}</span>
            </Tooltip>
          )
        })}
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
                  <Stack direction="row" spacing={1}>
                    <Button
                      variant="outlined"
                      onClick={() => void openAddOrders()}
                      disabled={!['draft', 'assembling', ...(!isOzonSupply ? ['packed'] : [])].includes(workspace.supply.status)}
                      data-testid="fbs-05-workspace-add-orders"
                    >
                      Добавить заказы
                    </Button>
                    <Button variant="outlined" startIcon={<PrintOutlinedIcon />} onClick={printPickingList} data-testid="fbs-pick-list-print">
                      Печать листа подбора
                    </Button>
                  </Stack>
                </Stack>
                <Divider sx={{ my: 2 }} />
                <Table size="small">
                  <TableHead><TableRow><TableCell>Фото</TableCell><TableCell>{isOzonSupply ? 'Отправление Ozon' : 'Заказ WB'}</TableCell><TableCell>Товар и идентификаторы</TableCell><TableCell>Количество</TableCell><TableCell>Маркировка</TableCell><TableCell>Подбор</TableCell></TableRow></TableHead>
                  <TableBody>
                    {workspace.orders.map((order) => {
                      const positions = order.positions.length ? order.positions : [{ product_id: order.product.id, name: order.product.name, seller_article: order.product.seller_article, sku: order.product.sku, quantity: 1, picked_quantity: order.pick.status === 'picked' ? 1 : 0 }]
                      return <TableRow key={order.id}>
                        <TableCell><ProductPhotoThumb src={order.product.image_url} alt={order.product.name} size={42} previewSize={280} testId={`fbs-composition-photo-${order.id}`} /></TableCell><TableCell><Link component="button" type="button" underline="hover" sx={{ textAlign: 'left' }} onClick={() => setHistoryOpen(true)} data-testid={`fbs-composition-history-${order.id}`}>{isOzonSupply ? order.external_order_id : `№${order.wb_order_id}`}</Link></TableCell>
                        <TableCell><Stack spacing={0.5}>{positions.map((position, index) => <Box key={`${position.sku ?? position.product_id ?? position.name}-${index}`}><Typography variant="body2" sx={{ fontWeight: 700 }}>{position.name}</Typography><Typography variant="caption" color="text.secondary" sx={{ display: 'block' }}>Артикул: {position.seller_article ?? '—'}{position.sku ? ` · SKU: ${position.sku}` : ''}</Typography></Box>)}</Stack></TableCell>
                        <TableCell><Stack spacing={0.5}>{positions.map((position, index) => <Typography key={`${position.sku ?? position.product_id ?? position.name}-${index}`} variant="body2">{order.positions.length ? `${position.picked_quantity} из ${position.quantity} шт.` : '1 шт.'}</Typography>)}</Stack></TableCell>
                        <TableCell>{order.metadata.required.length ? order.metadata.required.join(', ') : 'Не требуется'}</TableCell><TableCell>{order.pick.status === 'picked' ? 'Подобран' : 'Ожидает'}</TableCell>
                      </TableRow>
                    })}
                  </TableBody>
                </Table>
              </Paper>
              {/* Кнопка нужна, пока у поставки нет задания упаковки, — а не пока она
                  в статусе draft. Поставки, зазеркаленные из кабинета WB, рождаются
                  сразу в assembling, минуя draft: раньше кнопка им не показывалась
                  вовсе, задание не создавалось, и вкладка упаковки на них навсегда
                  оставалась заглушкой «Сначала начните работу с поставкой». */}
              {!workspace.supply.packaging_task_id ? (
                <Stack direction="row" sx={{ justifyContent: 'flex-end' }}>
                  <Button variant="contained" size="large" onClick={() => void run(() => startFbsSupplyWork(token, authHeaders, workspace.supply.id), 'Задание создано. Можно переходить к следующему этапу.')}>
                    Начать работу с поставкой
                  </Button>
                </Stack>
              ) : (
                nextStageControl('composition')
              )}
            </Stack>
          ) : null}

          {workspace && stage === 'picking' ? (
            <Stack spacing={2}>
              {!stageIsCurrent ? <Alert severity="success">Подбор завершён. Этот этап доступен только для просмотра.</Alert> : null}
              {allPicked && stageIsCurrent ? <Alert severity="success">Все товары подобраны. Перейдите к упаковке.</Alert> : null}
              <Stack direction="row" sx={{ justifyContent: 'flex-end' }}>
                <Button variant="outlined" startIcon={<PrintOutlinedIcon />} onClick={printPickingList} data-testid="fbs-pick-list-print">
                  Печать листа подбора
                </Button>
              </Stack>
              {/* Тот же экран подбора, что в документе отгрузки: строка идёт от
                  товара, видно где он лежит и сколько снять. Владелец требовал
                  одинаковый инструмент в обоих подборах. */}
              {supplyId ? (
                <Box data-testid="fbs-pick-unified">
                  <FfUnloadPickPage
                    token={token}
                    requestId={supplyId}
                    source="fbs"
                    hideHeader
                    onPaused={onClose}
                    onFinished={() => { void load() }}
                  />
                </Box>
              ) : null}
              {nextStageControl('picking')}
            </Stack>
          ) : null}

          {workspace && stage === 'packing' ? (
            <Stack spacing={2}>
              {!packagingEditable ? <Alert severity="success">Поставка уже передана в WB. Состав менять нельзя, печать этикеток и стикеров доступна.</Alert> : null}
              {packagingTask ? (
                <Paper variant="outlined" sx={{ overflow: 'hidden' }}>
                  <Box sx={{ px: 2, py: 1.75, borderBottom: 1, borderColor: 'divider' }}>
                    <Stack direction={{ xs: 'column', sm: 'row' }} spacing={1.5} sx={{ justifyContent: 'space-between', alignItems: { sm: 'center' } }}>
                      <Box>
                        <Stack direction="row" spacing={1} sx={{ alignItems: 'center', mb: 0.5 }}>
                          <Typography variant="h6">Упаковка и маркировка</Typography>
                          {workspace.supply.honest_sign_skipped ? (
                            <Chip
                              size="small"
                              color="warning"
                              label="Сдаём без Честного знака"
                              data-testid="fbs-honest-sign-skipped-chip"
                            />
                          ) : null}
                        </Stack>
                        <Typography variant="body2" color="text.secondary">
                          Напечатано {printedOrdersCount} из {packingOrders.length} · упаковано {workspace.progress.packed} из {workspace.progress.total}
                        </Typography>
                      </Box>
                      <Stack direction="row" spacing={1}>
                        <Button
                          disabled={busy || packingOrders.length === 0}
                          onClick={() => openBulkOrderMarkingPrint(
                            // L8 (21.08.2026): в ленту идут ВСЕ заказы поставки, а не только
                            // ненапечатанные. Иначе после первой печати (или после зажёванной
                            // бумаги) лента выходила короче листа подбора, и оператор об этом
                            // не знал. Коды Честного знака от этого не жгутся: у заказа, где
                            // код уже выпущен, сервер переиспользует его, а не берёт новый.
                            fullTapeOrders,
                            unprintedPackingOrders.length === 0,
                          )}
                          data-task-id="FBS-21"
                        >
                          Печать всего ({packingOrders.length})
                        </Button>
                        <Button variant="contained" disabled={!packagingEditable || busy} onClick={() => void packEverything()}>
                          Всё упаковано
                        </Button>
                        {!workspace.supply.honest_sign_skipped && packingOrders.length > 0 ? (
                          <Button
                            color="warning"
                            disabled={!packagingEditable || skipHonestSignBusy || busy}
                            onClick={() => setSkipHonestSignOpen(true)}
                            data-testid="fbs-skip-honest-sign"
                          >
                            Сдать без Честного знака
                          </Button>
                        ) : null}
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
                  {anyOrderNeedsHonestSign ? (
                    // KIZ-01: скан живёт прямо на вкладке — стикер заказа подсвечивает
                    // строку активной, следующий скан (Честный знак) привязывает код к
                    // ней и сразу уходит в WB. Окно «Внести КИЗ» для этого больше не нужно.
                    <Box
                      sx={{ px: 2, py: 1.5, borderBottom: 1, borderColor: 'divider', bgcolor: 'action.hover' }}
                      data-testid="fbs-kiz-scan-bar"
                    >
                      <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mb: 1 }}>
                        Внесение КИЗ со стикера — только если Честный знак уже наклеен селлером
                      </Typography>
                      <Stack direction={{ xs: 'column', sm: 'row' }} spacing={1.5} sx={{ alignItems: { sm: 'center' } }}>
                        <TextField
                          inputRef={kizScanInputRef}
                          autoFocus={packagingEditable}
                          size="small"
                          fullWidth
                          autoComplete="off"
                          value={kizScanValue}
                          disabled={!packagingEditable || kizScanBusy}
                          placeholder={kizScanActive ? 'Сканируйте Честный знак' : 'Сканируйте QR стикера заказа'}
                          onChange={(event) => setKizScanValue(event.target.value)}
                          onKeyDown={onKizScanEnter}
                          data-testid="fbs-kiz-scan-input"
                          slotProps={{
                            input: {
                              startAdornment: (
                                <InputAdornment position="start">
                                  <QrCodeScannerOutlined fontSize="small" color="action" />
                                </InputAdornment>
                              ),
                            },
                          }}
                          sx={{ '& input': { fontFamily: 'monospace' } }}
                        />
                        {kizScanActive ? (
                          <Stack direction="row" spacing={1} sx={{ alignItems: 'center', flexShrink: 0 }} data-testid="fbs-kiz-scan-active">
                            <ProductPhotoThumb src={kizScanActive.product.image_url} alt={kizScanActive.product.name} size={32} previewSize={220} />
                            <Box sx={{ minWidth: 0 }}>
                              <Typography variant="body2" noWrap sx={{ fontWeight: 700 }}>
                                {kizScanActive.product.name}
                              </Typography>
                              <Typography variant="caption" color="text.secondary">
                                № {kizScanActive.wb_order_id}
                              </Typography>
                            </Box>
                          </Stack>
                        ) : null}
                      </Stack>
                      <Typography
                        variant="caption"
                        color="text.secondary"
                        sx={{ display: 'block', mt: 0.75 }}
                        data-testid="fbs-kiz-scan-message"
                      >
                        {kizScanActive
                          ? `Заказ № ${kizScanActive.wb_order_id} активен — сканируйте Честный знак, код привяжется и уйдёт в WB.`
                          : 'Сканируйте QR стикера заказа — его строка станет активной, затем сканируйте Честный знак.'}
                      </Typography>
                      {kizScanHints.length > 0 ? (
                        <Typography variant="caption" color="text.secondary" sx={{ display: 'block' }}>
                          {kizScanHints.map((hint) => KIZ_HINT_TEXT[hint] ?? hint).join(' · ')}
                        </Typography>
                      ) : null}
                      {kizScanError ? (
                        <Typography
                          variant="body2"
                          component="div"
                          sx={{ color: 'error.main', mt: 0.5 }}
                          data-testid="fbs-kiz-scan-error"
                        >
                          {kizScanError.text}
                          {kizScanError.debug ? (
                            <>
                              <Link
                                component="button"
                                type="button"
                                variant="body2"
                                color="inherit"
                                underline="hover"
                                onClick={() => setKizScanDebugOpen((current) => !current)}
                                sx={{ ml: 1 }}
                              >
                                Что приехало со сканера
                              </Link>
                              <Collapse in={kizScanDebugOpen}>
                                <Typography variant="caption" component="div" color="text.secondary">
                                  Длина: {kizScanError.debug.length} · начало: {kizScanError.debug.first8 || '—'} · конец:{' '}
                                  {kizScanError.debug.last8 || '—'}
                                </Typography>
                              </Collapse>
                            </>
                          ) : null}
                        </Typography>
                      ) : null}
                    </Box>
                  ) : null}
                  <Stack divider={<Divider flexItem />}>
                    {packingOrders.map((order) => {
                      const line = order.product.id ? packLineByProduct.get(order.product.id) : undefined
                      const printed = orderPrintDone(order)
                      const mutedColor = printed ? 'text.secondary' : 'text.primary'
                      const kizRowActive = kizScanActive?.order_id === order.id
                      const ids = [
                        order.product.seller_article,
                        order.product.barcode,
                        isOzonSupply ? `заказ Ozon ${order.external_order_id ?? '—'}` : `заказ ${order.wb_order_id}`,
                      ].filter(Boolean).join(' · ')
                      // Пустая колонка ЧЗ = заказ ещё не сканировали. Внесённый код
                      // красит строку зелёным, активную (только что отсканированный
                      // стикер) — голубым: оператор видит, куда сейчас ляжет код.
                      const tail = kizTail(order)
                      const stickerParts = stickerCodeParts(order.sticker.code)
                      return (
                        <Stack
                          key={order.id}
                          ref={(node: HTMLDivElement | null) => { kizRowRefs.current[order.id] = node }}
                          direction="row"
                          spacing={1.5}
                          sx={{
                            alignItems: 'center',
                            px: 2,
                            py: 1.25,
                            bgcolor: kizRowActive
                              ? 'info.light'
                              : tail
                                ? 'success.light'
                                : (printed ? 'action.hover' : 'background.paper'),
                            borderLeft: '4px solid',
                            borderLeftColor: kizRowActive ? 'info.main' : (tail ? 'success.main' : 'transparent'),
                          }}
                          data-testid={kizRowActive ? 'fbs-kiz-row-active' : undefined}
                          data-kiz-tail={tail ?? ''}
                        >
                          <ProductPhotoThumb src={order.product.image_url} alt={order.product.name} size={40} previewSize={280} />
                          <Box sx={{ flex: 1, minWidth: 0 }}>
                            <Typography variant="body2" sx={{ fontWeight: 700, color: mutedColor }}>
                              {order.product.name}
                            </Typography>
                            <Typography variant="caption" sx={{ display: 'block', color: printed ? 'text.secondary' : 'text.secondary' }}>
                              {ids}
                              {markingShortOrderIds.has(order.id) ? <Box component="span" sx={{ color: '#854f0b' }}> · ЧЗ не хватило</Box> : null}
                            </Typography>
                          </Box>
                          <Box sx={{ width: 150, flexShrink: 0, textAlign: 'right' }}>
                            <Typography variant="caption" color="text.secondary" sx={{ display: 'block', lineHeight: 1 }}>
                              Стикер
                            </Typography>
                            {stickerParts ? (
                              <Typography
                                sx={{ fontFamily: 'monospace', fontSize: 15, lineHeight: 1.2, color: mutedColor }}
                                data-testid="fbs-sticker-code"
                              >
                                {stickerParts.head ? `${stickerParts.head} ` : ''}
                                <Box component="span" sx={{ fontWeight: 800, fontSize: 22 }}>
                                  {stickerParts.tail}
                                </Box>
                              </Typography>
                            ) : (
                              <Typography sx={{ color: 'text.disabled', fontSize: 15 }}>—</Typography>
                            )}
                          </Box>
                          <Box sx={{ width: 118, flexShrink: 0, textAlign: 'right' }}>
                            <Typography variant="caption" color="text.secondary" sx={{ display: 'block', lineHeight: 1 }}>
                              ЧЗ
                            </Typography>
                            {tail ? (
                              <Typography
                                sx={{ fontFamily: 'monospace', fontWeight: 700, fontSize: 15, color: 'success.dark' }}
                                data-testid="fbs-kiz-tail"
                              >
                                {tail}
                              </Typography>
                            ) : (
                              <Typography sx={{ color: 'text.disabled', fontSize: 15 }}>—</Typography>
                            )}
                          </Box>
                          {printed ? <Typography sx={{ color: 'success.main', fontWeight: 700 }}>✓</Typography> : null}
                          <Stack direction="row" spacing={0.5} sx={{ alignItems: 'center' }}>
                            <Button size="small" variant="outlined" disabled={!line} onClick={() => line && setTzLine(line)}>
                              ТЗ
                            </Button>
                            <Button size="small" variant="outlined" disabled={busy} onClick={() => void requestPrintBatch([order.id])} data-task-id="FBS-09">
                              QR
                            </Button>
                            <IconButton size="small" disabled={busy || !line} onClick={() => line && openOrderMarkingPrint(order, line)} aria-label="Печать ЧЗ и ШК" data-task-id="FBS-10">
                              <PrintOutlinedIcon fontSize="small" />
                            </IconButton>
                            <IconButton
                              size="small"
                              disabled={busy || !line}
                              onClick={(event: MouseEvent<HTMLElement>) => setReprintMenu({ orderId: order.id, anchorEl: event.currentTarget })}
                              aria-label="Перепечатать"
                              data-task-id="FBS-11"
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
              {nextStageControl('packing')}
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
                        {hasNoDistributionBoxes
                          ? `Без распределения · коробов ${workspace.boxes.length}`
                          : `Распределено ${boxDistributedCount} из ${boxTotalCount} шт · осталось ${boxRemainingCount}`}
                      </Typography>
                    </Box>
                    <Stack direction="row" spacing={1} sx={{ alignItems: 'center', flexWrap: 'wrap' }} useFlexGap>
                      <Button
                        startIcon={<PrintOutlinedIcon />}
                        disabled={boxOperationsDisabled || busy || workspace.boxes.length === 0}
                        onClick={() => void openAllBoxQrPreview()}
                        data-testid="fbs-boxes-print-all-qr"
                      >
                        Печать всех QR ({workspace.boxes.length})
                      </Button>
                      {!isOzonSupply ? <FormControlLabel
                        control={(
                          <Checkbox
                            checked={boxesWithoutDistribution}
                            onChange={(event) => setBoxesWithoutDistribution(event.target.checked)}
                            disabled={boxEditingDisabled || assignedBoxOrderIds.size > 0}
                            data-testid="fbs-boxes-without-distribution"
                            data-task-id="FBS-12"
                          />
                        )}
                        label="Без распределения"
                        data-task-id="FBS-12"
                      /> : null}
                      <TextField label="Коробов" value={boxCount} size="small" type="number" disabled={boxEditingDisabled} onChange={(e) => setBoxCount(e.target.value)} slotProps={{ htmlInput: { min: 1, max: 100 } }} sx={{ width: 104 }} data-task-id="FBS-12" />
                      <Button variant="contained" disabled={boxEditingDisabled || !Number(boxCount)} onClick={() => void createBoxes()} data-task-id="FBS-12">Добавить короба</Button>
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
                      positionId?: string
                      quantity: number
                    }>()
                    for (const order of assigned) {
                      if (isOzonSupply) {
                        for (const position of order.positions) {
                          if (!position.id || !box.assigned_order_product_ids?.includes(position.id)) continue
                          grouped.set(position.id, {
                            key: position.id,
                            name: position.name,
                            imageUrl: position.image_url ?? (position.product_id === order.product.id ? order.product.image_url : null),
                            orderIds: [order.id],
                            positionId: position.id,
                            quantity: position.quantity,
                          })
                        }
                        continue
                      }
                      const key = order.product.id ?? order.id
                      const current = grouped.get(key) ?? {
                        key,
                        name: order.product.name,
                        imageUrl: order.product.image_url,
                        orderIds: [],
                        quantity: 0,
                      }
                      current.orderIds.push(order.id)
                      current.quantity += 1
                      grouped.set(key, current)
                    }
                    const boxQuantity = [...grouped.values()].reduce((sum, row) => sum + row.quantity, 0)
                    const remainingOrderQuantity = assigned.reduce((sum, order) => sum + fbsUnassignedPositionQuantity(order.positions, assignedBoxPositionIds), 0)
                    const ozonQrDisabled = isOzonSupply && (assigned.length === 0 || remainingOrderQuantity > 0)
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
                              Короб {box.box_number} <Box component="span" sx={{ color: 'text.secondary' }}>· {boxQuantity} шт</Box>
                            </Typography>
                            {isOzonSupply && assigned.length > 0 ? <Typography variant="caption" color="text.secondary">Ozon №{assigned[0].external_order_id}{remainingOrderQuantity > 0 ? ` · осталось разложить ${remainingOrderQuantity} шт` : ''}</Typography> : null}
                          </Box>
                          <Stack direction="row" spacing={1} sx={{ alignItems: 'center' }}>
                            <Button
                              size="small"
                              disabled={boxOperationsDisabled || busy || ozonQrDisabled}
                              onClick={() => {
                                if (isOzonSupply) {
                                  if (box.qr_asset?.status === 'ready' && box.qr_asset.preview_url) openAssetPreview([box.qr_asset])
                                  else void retryBoxQr(box.id)
                                  return
                                }
                                // Real WB cargo-place QR whenever this box has one linked
                                // (any delivery_type); otherwise fall back to the local
                                // internal-barcode preview (e.g. boxes created before
                                // cargo places were enabled for warehouse/SC).
                                if (box.wb_trbx_id) {
                                  if (box.qr_asset?.preview_url) openAssetPreview([box.qr_asset])
                                  else void retryBoxQr(box.id)
                                  return
                                }
                                void openBoxQrPreview(box)
                              }}
                              data-task-id="FBS-09"
                            >
                              QR
                            </Button>
                            <Button
                              size="small"
                              disabled={boxEditingDisabled || busy || box.without_distribution || box.ozon_assembled}
                              onClick={() => {
                                setBoxAssignTarget(box.id)
                                setBoxProductSearch('')
                                setBoxProductQty({})
                                setBoxSelectedPositionIds(new Set())
                              }}
                              data-task-id="FBS-12"
                            >
                              Добавить товары
                            </Button>
                            <IconButton
                              size="small"
                              disabled={boxEditingDisabled || busy || box.ozon_assembled}
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
                                  <Typography variant="body2" color="text.secondary">{row.quantity} шт</Typography>
                                  <IconButton
                                    size="small"
                                    disabled={boxEditingDisabled || busy || box.ozon_assembled}
                                    onClick={() => void removeBoxOrders(box.id, row.orderIds, row.positionId)}
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
                  <Button
                    variant="contained"
                    size="large"
                    disabled={busy}
                    onClick={() => void openDeliveryConfirmation()}
                    data-testid="fbs-deliver-open"
                  >
                    Передать в {providerName}
                  </Button>
                </Stack>
              ) : null}
              {deliveryConfirmed && needsSupplyQr && supplyQrAsset?.preview_url ? (
                <Paper variant="outlined" sx={{ p: { xs: 2, md: 3 } }} data-testid="fbs-supply-qr">
                  <Stack direction={{ xs: 'column', sm: 'row' }} spacing={2} sx={{ justifyContent: 'space-between', alignItems: { sm: 'center' } }}>
                    <Box>
                      <Typography variant="h6">QR поставки {providerName}</Typography>
                      <Typography variant="body2" color="text.secondary" sx={{ mt: 0.5 }}>
                        Распечатайте QR для сдачи всей поставки.
                      </Typography>
                    </Box>
                    <Button
                      variant="contained"
                      size="large"
                      startIcon={<PrintOutlinedIcon />}
                      onClick={() => openAssetPreview([supplyQrAsset])}
                      data-task-id="FBS-09"
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
              {deliveryConfirmed && hasCargoPlaceBoxes ? (
                <Alert severity="info" data-testid="fbs-supply-qr-pvz" data-task-id="FBS-09">
                  На каждый короб клеится свой QR грузоместа — кнопка «QR» есть в строке каждого короба выше.
                  QR поставки печатается отдельно (см. блок выше) и едет вместе с грузом.
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
      <FbsSupplyHistoryDialog
        token={token}
        supplyId={supplyId}
        open={historyOpen}
        onClose={() => setHistoryOpen(false)}
      />
      <Dialog open={addOrdersOpen} onClose={addOrdersBusy ? undefined : () => setAddOrdersOpen(false)} maxWidth="md" fullWidth>
        <DialogTitle>Добавить заказы в поставку</DialogTitle>
        <DialogContent dividers>
          <Stack spacing={1.5}>
            {addOrdersBusy ? (
              <Stack direction="row" spacing={1.5} sx={{ alignItems: 'center', py: 2 }}>
                <CircularProgress size={20} />
                <Typography variant="body2">Загружаем совместимые новые заказы…</Typography>
              </Stack>
            ) : addableOrders.length === 0 ? (
              <Alert severity="info" data-testid="fbs-05-workspace-no-addable">
                Новых заказов того же селлера и WB-склада нет.
              </Alert>
            ) : (
              <Table size="small" data-testid="fbs-05-workspace-add-orders-table">
                <TableHead>
                  <TableRow>
                    <TableCell padding="checkbox" />
                    <TableCell>Заказ WB</TableCell>
                    <TableCell>Товар</TableCell>
                    <TableCell>Склад</TableCell>
                  </TableRow>
                </TableHead>
                <TableBody>
                  {addableOrders.map((order) => (
                    <TableRow key={order.id} hover>
                      <TableCell padding="checkbox">
                        <Checkbox
                          checked={addableSelected.has(order.id)}
                          onChange={(_, checked) => {
                            setAddableSelected((current) => {
                              const next = new Set(current)
                              if (checked) next.add(order.id)
                              else next.delete(order.id)
                              return next
                            })
                          }}
                        />
                      </TableCell>
                      <TableCell>№{order.wb_order_id}</TableCell>
                      <TableCell>{order.product.name}</TableCell>
                      <TableCell>{order.wb_warehouse.name || `WB ${order.wb_warehouse.id}`}</TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            )}
          </Stack>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setAddOrdersOpen(false)} disabled={addOrdersBusy}>
            Отмена
          </Button>
          <Button
            variant="contained"
            disabled={addOrdersBusy || addableSelected.size === 0}
            onClick={() => void addOrdersToCurrentSupply()}
            data-testid="fbs-05-workspace-add-orders-submit"
          >
            Добавить заказы
          </Button>
        </DialogActions>
      </Dialog>
      <Dialog open={skipHonestSignOpen} onClose={skipHonestSignBusy ? undefined : () => setSkipHonestSignOpen(false)} maxWidth="sm" fullWidth>
        <DialogTitle>Сдать без Честного знака?</DialogTitle>
        <DialogContent>
          <Stack spacing={1.5}>
            <Typography variant="body2">
              Требование маркировки снимается со всей поставки. При отправке:
            </Typography>
            <Stack component="ul" spacing={0.5} sx={{ pl: 3, my: 0 }}>
              <Typography component="li" variant="body2">
                Коды Честного знака по незаполненным заказам в WB не уйдут.
              </Typography>
              <Typography component="li" variant="body2">
                Вывод из оборота в системе Честного знака остаётся на продавце.
              </Typography>
              <Typography component="li" variant="body2">
                Уже отсканированные коды сохранятся и будут отправлены как обычно.
              </Typography>
              <Typography component="li" variant="body2">
                Если Wildberries по заказу требует маркировку обязательной, сдать его без
                кода всё равно не выйдет — это ограничение маркетплейса, а не наше.
              </Typography>
            </Stack>
          </Stack>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setSkipHonestSignOpen(false)} disabled={skipHonestSignBusy}>
            Отмена
          </Button>
          <Button
            variant="contained"
            color="warning"
            disabled={skipHonestSignBusy}
            onClick={() => void performSkipHonestSign()}
            data-testid="fbs-skip-honest-sign-confirm"
          >
            Сдать без Честного знака
          </Button>
        </DialogActions>
      </Dialog>
      {markingPrintDialog}
      {/* KIZ-01: единственный оставшийся модальный шаг скана КИЗ — редкое подтверждение
          замены уже внесённого кода. Основной цикл «стикер → ЧЗ» идёт инлайново на вкладке. */}
      <Dialog open={Boolean(kizConfirmTarget)} onClose={() => { setKizConfirmTarget(null); refocusKizInput() }} maxWidth="xs" fullWidth>
        <DialogTitle>Заказ уже с ЧЗ</DialogTitle>
        <DialogContent>
          <Typography variant="body2">
            На заказ № {kizConfirmTarget?.wb_order_id} уже есть ЧЗ {kizConfirmTarget?.current_kiz?.masked}. Внести другой КИЗ?
          </Typography>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => { setKizConfirmTarget(null); refocusKizInput() }}>Отмена</Button>
          <Button
            variant="contained"
            data-testid="fbs-kiz-confirm-replace"
            onClick={() => {
              setKizScanActive(kizConfirmTarget)
              setKizConfirmTarget(null)
              refocusKizInput()
            }}
          >
            Внести
          </Button>
        </DialogActions>
      </Dialog>
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
          data-task-id="FBS-11"
        >
          Перепечатать
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
        <DialogContent><Typography>{addressStorageEnabled ? 'Товар будет возвращён в исходную ячейку.' : 'Товар будет возвращён в остаток.'} Отменяйте только если в подборе действительно ошибка.</Typography></DialogContent>
        <DialogActions><Button onClick={() => setUndoOrderId(null)}>Не отменять</Button><Button color="error" variant="contained" onClick={() => { const orderId = undoOrderId; setUndoOrderId(null); if (orderId && workspace) void run(() => undoFbsPick(token, authHeaders, workspace.supply.id, orderId, createFbsIdempotencyKey()), addressStorageEnabled ? 'Подбор отменён, остаток возвращён в исходную ячейку.' : 'Подбор отменён, товар возвращён в остаток.') }}>{addressStorageEnabled ? 'Вернуть в ячейку' : 'Вернуть в остаток'}</Button></DialogActions>
      </Dialog>
      <Dialog open={deliverConfirmOpen} onClose={() => setDeliverConfirmOpen(false)} maxWidth="sm" fullWidth>
        <DialogTitle>Передать поставку в {providerName}?</DialogTitle>
        <DialogContent>
          <Typography variant="body2">
            После передачи поставку нельзя будет отменить или вернуть в работу.
          </Typography>
          <Stack spacing={1.5} sx={{ mt: 1.5 }} data-testid="fbs-delivery-marking-status">
            {deliveryPreflightLoading ? (
              <Typography variant="body2" color="text.secondary">
                {`Проверяем готовность поставки в ${providerName}…`}
              </Typography>
            ) : null}
            {deliveryPreflightError ? (
              <Alert
                severity="error"
                action={(
                  <Button size="small" onClick={() => void openDeliveryConfirmation()} data-testid="fbs-preflight-retry">
                    Проверить ещё раз
                  </Button>
                )}
              >
                {deliveryPreflightError}
              </Alert>
            ) : null}
            {deliveryChecks.blockers.length > 0 ? (
              <Alert severity="error">
                <Typography variant="subtitle2">Мешает передаче</Typography>
                {deliveryChecks.blockers.map((line) => (
                  <Typography key={line} variant="body2">{line}</Typography>
                ))}
              </Alert>
            ) : null}
            {deliveryChecks.warnings.length > 0 ? (
              <Alert severity="warning">
                <Typography variant="subtitle2">Передаче не мешает, но проверьте</Typography>
                {deliveryChecks.warnings.map((line) => (
                  <Typography key={line} variant="body2">{line}</Typography>
                ))}
                <Typography variant="caption" color="text.secondary">
                  Стикеры, Честный знак и QR можно напечатать и после передачи.
                </Typography>
              </Alert>
            ) : null}
            {!deliveryPreflightLoading
              && !deliveryPreflightError
              && deliveryChecks.blockers.length === 0
              && deliveryChecks.warnings.length === 0
              && deliveryPreflight ? (
                <Alert severity="success">Все проверки пройдены. Поставку можно передать.</Alert>
              ) : null}
          </Stack>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setDeliverConfirmOpen(false)}>Не передавать</Button>
          <Button
            variant="contained"
            disabled={fbsDeliveryConfirmDisabled(
              workspace?.supply.marketplace ?? 'wb',
              deliveryPreflightLoading,
              deliveryPreflight,
            )}
            onClick={() => {
              setDeliverConfirmOpen(false)
              void deliver()
            }}
            data-testid="fbs-deliver-confirm"
          >
            Передать в {providerName}
          </Button>
        </DialogActions>
      </Dialog>
      <Dialog open={Boolean(boxAssignTarget)} onClose={busy ? undefined : () => setBoxAssignTarget(null)} maxWidth={isOzonSupply ? 'xl' : 'md'} fullWidth slotProps={isOzonSupply ? { paper: { sx: { minHeight: '75vh', maxHeight: '95vh' } } } : undefined}>
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
              {isOzonSupply ? ozonBoxAssignOrders.map(({ order, positions }) => {
                const disabled = busy || Boolean(boxAssignBox?.ozon_assembled) || Boolean(boxAssignOrderId && boxAssignOrderId !== order.id)
                return (
                  <Paper key={order.id} variant="outlined" sx={{ p: 1.5, opacity: disabled ? 0.5 : 1 }} data-testid={`fbs-box-assign-order-${order.id}`}>
                    <Typography variant="subtitle2" sx={{ mb: 1 }}>Ozon №{order.external_order_id}</Typography>
                    <Stack spacing={1}>
                      {positions.map((position) => (
                        <Stack key={position.id} direction="row" spacing={1.25} sx={{ alignItems: 'center' }}>
                          <Checkbox
                            checked={boxSelectedPositionIds.has(position.id!)}
                            disabled={disabled}
                            onChange={(event) => setBoxSelectedPositionIds((current) => {
                              const next = new Set(current)
                              if (event.target.checked) next.add(position.id!)
                              else next.delete(position.id!)
                              return next
                            })}
                            slotProps={{ input: { 'aria-label': `Добавить ${position.name}` } }}
                            data-testid={`fbs-box-assign-position-${position.id}`}
                          />
                          <ProductPhotoThumb src={position.image_url ?? (position.product_id === order.product.id ? order.product.image_url : null)} alt={position.name} size={44} />
                          <Box sx={{ flex: 1, minWidth: 0 }}>
                            <Typography variant="body2" sx={{ fontWeight: 700 }}>{position.name}</Typography>
                            <Typography variant="caption" color="text.secondary">{[position.seller_article, position.sku].filter(Boolean).join(' · ')}</Typography>
                          </Box>
                          <Typography variant="body2" sx={{ whiteSpace: 'nowrap' }}>{position.quantity} шт</Typography>
                        </Stack>
                      ))}
                    </Stack>
                  </Paper>
                )
              }) : boxAssignRows.map((row) => {
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
          <Button variant="contained" disabled={busy || (isOzonSupply ? boxAssignSelectedPositionIds.length === 0 : boxAssignSelectedOrderIds.length === 0)} onClick={() => void assignBoxOrders()}>Добавить</Button>
        </DialogActions>
      </Dialog>
      <Menu
        anchorEl={boxMenu?.anchorEl ?? null}
        open={Boolean(boxMenu)}
        onClose={() => setBoxMenu(null)}
      >
        <MenuItem disabled={!packagingEditable || !boxMenuBox || boxMenuBox.ozon_assembled || boxMenuAssignedCount === 0} onClick={() => { if (boxMenuBox) void clearBox(boxMenuBox.id) }}>
          Очистить
        </MenuItem>
        <MenuItem disabled={!packagingEditable || !boxMenuBox || boxMenuBox.ozon_assembled || boxMenuAssignedCount > 0} onClick={() => { if (boxMenuBox) void deleteBox(boxMenuBox.id) }}>
          Удалить
        </MenuItem>
      </Menu>
    </Dialog>
  )
}
