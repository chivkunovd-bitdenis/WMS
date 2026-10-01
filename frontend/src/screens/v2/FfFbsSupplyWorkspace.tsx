import { createPortal } from 'react-dom'
import { createPackingScanController, makePackingScanDeps, routePackingScan } from './fbsSequentialPacking'
import { FbsScanPrintToggles } from './FbsScanPrintToggles'
import { ErrorBoundary } from '../../components/errors/ErrorBoundary'
import { confirmDiscardChanges } from '../../utils/confirmDiscardChanges'
import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState, type KeyboardEvent, type MouseEvent } from 'react'
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
import { alpha } from '@mui/material/styles'
import { FfUnloadPickPage } from '../ff/unload-pick/FfUnloadPickPage'
import CloseIcon from '@mui/icons-material/Close'
import ErrorOutlineIcon from '@mui/icons-material/ErrorOutlined'
import DeleteOutlinedIcon from '@mui/icons-material/DeleteOutlined'
import LocalShippingOutlinedIcon from '@mui/icons-material/LocalShippingOutlined'
import MoreVertOutlinedIcon from '@mui/icons-material/MoreVertOutlined'
import PrintOutlinedIcon from '@mui/icons-material/PrintOutlined'
import QrCodeScannerOutlined from '@mui/icons-material/QrCodeScannerOutlined'
import ReplayOutlinedIcon from '@mui/icons-material/ReplayOutlined'
import { apiUrl } from '../../api'
import { ProductPhotoThumb } from '../../components/ProductPhotoThumb'
import { DeadlinePill } from '../../components/fbs/FbsChips'
import { type PackagingTask, type PackagingTaskLine } from '../ff/FfPackagingPage'
import { useMarkingCodePrint } from '../../utils/useMarkingCodePrint'
import { printMarkingCodeLabels, printMarkingCodeTape } from '../../utils/printMarkingCodeLabel'
import { startAutoKizReprintPrint } from '../../utils/kizReprintPrint'
import { readApiErrorMessage } from '../../utils/readApiErrorMessage'
import { playScanError, playScanSuccess } from '../../utils/scanFeedback'
import { useScanIntake } from '../../hooks/useScanIntake'
import type { ProductThermalLabelData } from '../../utils/printProductThermalLabel'
import { resolveProductBarcodeOptions } from '../../types/wbProductCatalog'
import HistoryOutlinedIcon from '@mui/icons-material/HistoryOutlined'
import { FbsSupplyHistoryDialog } from './FbsSupplyHistoryDialog'
import { FbsPrintPreviewDialog } from './FbsPrintPreviewDialog'
import { FbsTransferSupplyDialog, makeFbsTransferSupplyDeps } from './FbsTransferSupplyDialog'
import { FbsAssemblySupplyFrame, type FbsAssemblyFrameControl } from './FbsAssemblySupplyFrame'
import { fbsAssemblySupplyTitle, fbsCodeBelongsToSupply } from './fbsSupplyAssembly'
import { readFbsWorkspaceStage, saveFbsWorkspaceStage } from './fbsWorkspaceStage'
import { fbsMenuReprintRequest, hasOperatorKiz } from './fbsMenuReprint'
import {
  buildFbsPickingListPrintHtml,
  fbsBuildPickingRows,
  productBarcodeOptionsForPosition,
  fbsPickSourceLabels,
  fbsAccessibleStageIndex,
  fbsErrorText,
  fbsSameStickerScan,
  fbsOrderMarkingAccepted,
  fbsMarkingPresentation,
  fbsMarkingVerdictsSummary,
  fbsBoxEditingDisabled,
  fbsBoxProductProgress,
  fbsBoxOperationsDisabled,
  fbsDeliveryErrorKeepsIdempotencyKey,
  fbsDeliveryConfirmDisabled,
  fbsOrdersAvailableForBox,
  fbsOzonAutoBoxesPlan,
  fbsOzonBoxLabelReady,
  fbsOzonLabelFailuresText,
  fbsUnassignedPositionQuantity,
  fbsStageAfterWorkspaceRefresh,
  ordersWord,
  summarizeDeliveryChecks,
} from './fbsUx'
import {
  confirmFbsPrintApplied,
  addFbsOrdersToSupply,
  assignFbsPackingBoxOrders,
  autoAssignFbsOzonBoxes,
  clearFbsPackingBox,
  claimFbsDirectKizPrint,
  claimFbsScanAutoPrintReprint,
  claimFbsScanAutoPrintTarget,
  commitFbsKiz,
  fbsKizOrderNumber,
  syncFbsOrderMarkings,
  syncFbsSupplyMarkings,
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
  getFbsPickOptions,
  lookupFbsOrderBySticker,
  markFbsDirectKizPrintStarted,
  markFbsScanAutoPrintTargetStarted,
  printFbsOrderTape,
  releaseFbsDirectKizPrintClaim,
  releaseFbsScanAutoPrintTargetClaim,
  removeFbsPackingBoxOrder,
  retryFbsPackingBoxQr,
  retryFbsSupplyQr,
  setFbsSupplyBoxesWithoutDistribution,
  saveFbsDirectKizReprint,
  scanFbsProductForAutoPrint,
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
  type FbsScanAutoPrintReprintClaim,
  type FbsWorkspace,
  type FbsWorklistOrder,
} from './fbsApi'
import {
  FbsKizAutoPrintQueue,
  startClaimedAutomaticPrint,
} from './fbsKizAutoReprint'
import {
  claimFbsPendingProductScan,
  completeFbsPendingProductScan,
  fbsPendingProductScanComplete,
  loadFbsScanPrintPreferences,
  mergeFbsBufferedHardwareScan,
  peekFbsPendingProductScan,
  printFbsOrderQrAsset,
  productScanPrintPlan,
  saveFbsScanPrintPreferences,
  updateFbsPendingProductScan,
  type FbsScanPrintPreferences,
} from './fbsScanAutoPrint'

type Props = {
  token: string
  authHeaders: (token: string) => Record<string, string>
  supplyId: string | null
  initialWorkspace?: FbsWorkspace | null
  open: boolean; addressStorageEnabled?: boolean
  onClose: () => void
  onDirtyChange?: (dirty: boolean) => void
  /**
   * WMS-574: карточка встроена рамкой поставки в окно групповой сборки —
   * показывает только упаковку и короба этой поставки. Не передан — обычная
   * карточка поставки, всё как было.
   */
  assemblyFrame?: FbsAssemblyFrameControl
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

const STICKER_PRINTED_STATUSES = ['print_opened', 'applied']

/**
 * WMS-575: поле скана выключается на время запроса и теряет фокус, а ловушка
 * фокуса окна MUI переводит его на контейнер окна карточки. Это не выбор
 * оператора, поэтому право вернуть фокус в поле сохраняется.
 */
function isWorkspaceFocusFallback(element: Element | null | undefined): boolean {
  return element instanceof HTMLElement
    && element.classList.contains('MuiDialog-container')
    && element.closest('[data-testid="fbs-workspace"]') !== null
}

/** Хвост кода маркировки для строки — так же, как его режет сервер (последние 8 знаков). */
function kizValueTail(value: string): string {
  // Python str.strip() снимает и разделители \x1c–\x1f, JS trim() — нет.
  // eslint-disable-next-line no-control-regex
  const cleaned = value.replace(/^[\s\x1c-\x1f]+|[\s\x1c-\x1f]+$/g, '')
  return cleaned.length > 8 ? cleaned.slice(-8) : cleaned
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

function hasRemovableKiz(order: FbsWorkspace['orders'][number], marketplace: 'wb' | 'ozon') {
  return order.metadata.states.some(
    (state) =>
      state.kind === 'sgtin' &&
      (state.source === 'operator' || (marketplace === 'wb' && state.source === 'pool')) &&
      state.status !== 'missing' &&
      (marketplace === 'wb' || state.status !== 'rejected'),
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

type QueuedPackingScan = {
  raw: string
  preferences: FbsScanPrintPreferences
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

type PackingSizeOrder = {
  product: { size: string | null }
  positions: Array<{ size?: string | null }>
}

/**
 * Размеры строки упаковки. У WB размер один на заказ, у Ozon свой у каждой
 * позиции отправления, поэтому там список идёт в том же порядке, что и позиции
 * на экране: размер первой позиции нельзя показывать за весь заказ.
 */
export function fbsPackingSizes(order: PackingSizeOrder, isOzon: boolean): Array<string | null> {
  const clean = (value: string | null | undefined) => {
    const text = (value ?? '').trim()
    return text ? text : null
  }
  if (isOzon) return order.positions.map((position) => clean(position.size))
  return [clean(order.product.size)]
}

/** Столбец «Размер» нужен, когда размер есть хотя бы у одной показанной строки. */
export function fbsPackingShowsSize(orders: PackingSizeOrder[], isOzon: boolean): boolean {
  return orders.some((order) => fbsPackingSizes(order, isOzon).some((size) => size !== null))
}

function PackingSizeCell({ value, withCaption, valueColor }: {
  value: string | null
  withCaption: boolean
  valueColor: string
}) {
  return (
    <Box sx={{ width: 76, flexShrink: 0, textAlign: 'right' }} data-testid="fbs-packing-size">
      {withCaption ? (
        <Typography variant="caption" color="text.secondary" sx={{ display: 'block', lineHeight: 1 }}>
          Размер
        </Typography>
      ) : null}
      {/* «универсальный» и «44/46/48/50/52/54» — одно слово без пробелов: без переноса
          в любом месте оно вылезает из колонки на соседний текст. */}
      <Typography variant="body2" sx={{ color: value ? valueColor : 'text.disabled', overflowWrap: 'anywhere' }}>
        {value ?? '—'}
      </Typography>
    </Box>
  )
}

function kizErrorTextByCode(code: string, message: string, context: unknown, provider = 'WB'): string {
  if (code === 'sticker_not_found') return 'Номер или стикер заказа не найден в этой поставке'
  if (code === 'sticker_ambiguous') return 'Скан совпал с несколькими заказами. Введите номер отправления.'
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
  if (code === 'meta_validation_fail') return `${provider} не принял: ${message}`
  return fbsErrorText(message)
}

function kizErrorText(cause: unknown, provider = 'WB'): string {
  if (cause instanceof FbsApiError) {
    return kizErrorTextByCode(cause.code, cause.message, cause.context, provider)
  }
  return cause instanceof Error ? fbsErrorText(cause.message) : 'Не удалось выполнить операцию'
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

function productBarcodeOptionsForOrder(
  order: FbsWorkspace['orders'][number],
  marketplace: 'wb' | 'ozon',
) {
  const options = resolveProductBarcodeOptions({
    wb_primary_barcode: order.product.barcode,
    marketplace_bindings: order.product.marketplace_bindings,
  })
  // An Ozon label must never silently fall back to a WB barcode.  An absent
  // Ozon barcode stays absent and the established dialog explains that it
  // cannot print one; the operator can correct the product binding first.
  return marketplace === 'ozon'
    ? options.filter((option) => option.marketplace === 'ozon')
    : options
}

function productLabelFromPosition(
  order: FbsWorkspace['orders'][number],
  position: FbsWorkspace['orders'][number]['positions'][number],
  marketplace: 'wb' | 'ozon',
): ProductThermalLabelData {
  const barcode = productBarcodeOptionsForPosition(position, marketplace)[0]?.barcode ?? ''
  return {
    product_name: position.name,
    sku_code: position.sku ?? position.seller_article ?? order.product.sku ?? `WMS-${order.id}`,
    wb_vendor_code: position.seller_article,
    wb_size: position.size,
    wb_color: position.color,
    wb_brand: position.brand,
    wb_composition: position.composition,
    seller_name: order.seller.name,
    barcode,
  }
}

function productLabelsFromOrder(
  order: FbsWorkspace['orders'][number],
  marketplace: 'wb' | 'ozon',
) {
  if (marketplace !== 'ozon' || order.positions.length === 0) {
    return [{ productLabel: productLabelFromOrder(order, marketplace), copies: 1 }]
  }
  return order.positions.map((position) => ({
    positionId: position.id ?? undefined,
    productLabel: productLabelFromPosition(order, position, marketplace),
    copies: Math.max(1, position.quantity),
  }))
}

function productLabelFromOrder(
  order: FbsWorkspace['orders'][number],
  marketplace: 'wb' | 'ozon',
): ProductThermalLabelData {
  const position = marketplace === 'ozon' ? order.positions[0] : undefined
  const barcode = productBarcodeOptionsForOrder(order, marketplace)[0]?.barcode
    ?? (marketplace === 'ozon' ? '' : order.product.barcode ?? '')
  return {
    product_name: position?.name ?? order.product.name,
    sku_code: position?.sku ?? position?.seller_article ?? order.product.sku ?? order.product.seller_article
      ?? (marketplace === 'ozon' ? `Ozon-${order.external_order_id ?? order.id}` : `WB-${order.wb_order_id}`),
    wb_vendor_code: marketplace === 'ozon'
      ? position?.seller_article ?? null
      : position?.seller_article ?? order.product.seller_article,
    wb_size: position?.size ?? order.product.size,
    wb_color: position?.color ?? order.product.color,
    wb_brand: position?.brand ?? order.product.brand,
    wb_composition: position?.composition ?? order.product.composition,
    seller_name: order.seller.name,
    barcode,
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
  onDirtyChange,
  assemblyFrame,
}: Props) {
  const [workspace, setWorkspace] = useState<FbsWorkspace | null>(initialWorkspace ?? null)
  const [selectedStage, setStage] = useState<StageKey>('composition')
  // WMS-574: рамка окна сборки всегда на упаковке и не трогает запомненную
  // вкладку карточки этой поставки.
  const stage: StageKey = assemblyFrame ? assemblyFrame.stage ?? 'packing' : selectedStage
  const selectStage = (next: StageKey) => {
    if (assemblyFrame) return
    if (supplyId) saveFbsWorkspaceStage(supplyId, next)
    setStage(next)
  }
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [notice, setNotice] = useState<string | null>(null)
  // История заказа открывается прямо из состава поставки: оператор смотрит,
  // что с заказом происходило, там же, где увидел сам заказ.
  const [historyOpen, setHistoryOpen] = useState(false)
  const [printBatch, setPrintBatch] = useState<FbsPrintBatch | null>(null)
  const [printPreviewOpen, setPrintPreviewOpen] = useState(false)
  const [packagingTask, setPackagingTask] = useState<PackagingTask | null>(null)
  const [packingSelectedIds, setPackingSelectedIds] = useState<Set<string>>(() => new Set())
  // WMS-562: перенос выбранных на упаковке заказов в другую поставку WB.
  const [transferDialogOpen, setTransferDialogOpen] = useState(false)
  const [clearMarkingOrders, setClearMarkingOrders] = useState<FbsWorkspace['orders'] | null>(null)
  const [boxCount, setBoxCount] = useState('1')
  const [boxAssignTarget, setBoxAssignTarget] = useState<string | null>(null)
  const [boxProductSearch, setBoxProductSearch] = useState('')
  const [boxProductQty, setBoxProductQty] = useState<Record<string, string>>({})
  const [boxSelectedPositionIds, setBoxSelectedPositionIds] = useState<Set<string>>(() => new Set())
  const [boxMenu, setBoxMenu] = useState<{ boxId: string; anchorEl: HTMLElement } | null>(null)
  const [expandedBoxIds, setExpandedBoxIds] = useState<Set<string>>(() => new Set())
  // WMS-526: ход «Создать автоматически» в тексте кнопки; ref держит одно выполнение на двойной клик.
  const [ozonAutoBoxesProgress, setOzonAutoBoxesProgress] = useState<string | null>(null)
  const ozonAutoBoxesRunningRef = useRef(false)
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
  // Последний распознанный скан поднимается первой строкой и сразу подсвечивается:
  // оператор видит результат до печати и фонового перечитывания вердикта WB.
  const [recentlyScannedOrderId, setRecentlyScannedOrderId] = useState<string | null>(null)
  const [kizScanBusy, setKizScanBusy] = useState(false)
  const [kizScanError, setKizScanError] = useState<KizScanError | null>(null)
  const [kizScanHints, setKizScanHints] = useState<string[]>([])
  const [kizScanDebugOpen, setKizScanDebugOpen] = useState(false)
  const [scanPrintPreferences, setScanPrintPreferences] = useState<FbsScanPrintPreferences>({
    printQr: false,
    printChz: false,
    reprintChz: false,
  })
  const [kizConfirmValue, setKizConfirmValue] = useState<string | null>(null)
  const [kizScanNotice, setKizScanNotice] = useState<string | null>(null)
  const [kizConfirmTarget, setKizConfirmTarget] = useState<FbsKizLookup | null>(null)
  const kizScanInputRef = useRef<HTMLInputElement | null>(null)
  const kizRowInputRef = useRef<HTMLInputElement | null>(null)
  const kizRowTargetRef = useRef<FbsKizLookup | null>(null)
  const kizRowCommitGateRef = useRef<Promise<void> | null>(null)
  const kizSelectedStickerRef = useRef('')
  const activeProductScanBarcodeRef = useRef<string | null>(null)
  const kizAutoPrintQueueRef = useRef(new FbsKizAutoPrintQueue())
  const pendingDirectReprintKeysRef = useRef(new Map<string, string>())
  const queuedPackingScansRef = useRef<QueuedPackingScan[]>([])
  const busyHardwareScanBufferRef = useRef('')
  const busyHardwareCaptureEnabledRef = useRef(false)
  const scannerShouldRefocusRef = useRef(false)
  // WMS-575: скан принимает вся вкладка (useScanIntake ниже). Поле скана и
  // слушатель документа отдают код в один и тот же приём acceptPackingScan.
  const acceptPackingScanRef = useRef<(raw: string) => void>(() => undefined)
  // WMS-574: действия рамки окна сборки внутри приёма скана. В обычной карточке
  // они пустые, и приём скана идёт ровно как раньше.
  const assemblyPlaceOrderRef = useRef<((orderId: string, releaseKizWait: boolean, boxId: string | null) => Promise<void>) | null>(null)
  const assemblyScanErrorTextRef = useRef<((cause: unknown, raw: string) => string | null) | null>(null)
  // Короб, открытый в момент скана: код несёт его с собой до назначения, даже
  // если оператор тем временем переключил короб или завершил работу (R22).
  const assemblyOpenBoxIdRef = useRef<string | null>(null)
  const assemblyScanBoxesRef = useRef<Array<{ code: string; boxId: string | null; at: number }>>([])
  const assemblyTakeScanBoxRef = useRef<((raw: string) => string | null) | null>(null)
  // Идёт ли сейчас скан и какой заказ ждёт ЧЗ — чтобы не запоминать короб для
  // повторного скана того же стикера: он только снимает выбор.
  const assemblyScanStateRef = useRef<{ active: boolean; busy: boolean }>({ active: false, busy: false })
  const assemblyAfterPackAllRef = useRef<((snapshot: FbsWorkspace | null) => Promise<void>) | null>(null)
  const assemblyEscapeRef = useRef<() => boolean>(() => false)
  const assemblyBoxCreatingRef = useRef(false)
  const [assemblyOpenBoxId, setAssemblyOpenBoxId] = useState<string | null>(null)
  const [assemblyBoxHint, setAssemblyBoxHint] = useState<string | null>(null)
  const [assemblyStarting, setAssemblyStarting] = useState(false)
  const [assemblyBoxCreating, setAssemblyBoxCreating] = useState(false)
  const packingScanListeningRef = useRef(false)
  // Хвост ЧЗ, сохранённого ответом commit, — пока перечитывание поставки не
  // принесло его в строку. Ключ — заказ.
  const [kizCommittedTails, setKizCommittedTails] = useState<Record<string, string>>({})
  const [queuedPackingScanVersion, setQueuedPackingScanVersion] = useState(0)
  const [addOrdersOpen, setAddOrdersOpen] = useState(false)
  const [addableOrders, setAddableOrders] = useState<FbsWorklistOrder[]>([])
  const [addableSelected, setAddableSelected] = useState<Set<string>>(() => new Set())
  const [addOrdersBusy, setAddOrdersBusy] = useState(false)
  const [plannedShipmentDateDraft, setPlannedShipmentDateDraft] = useState('')
  const [skipHonestSignOpen, setSkipHonestSignOpen] = useState(false)
  const [skipHonestSignBusy, setSkipHonestSignBusy] = useState(false)
  const { openPrint, dialog: markingPrintDialog } = useMarkingCodePrint()
  const boxAssignmentDirty = Object.values(boxProductQty).some((value) => Boolean(value.trim())) ||
    boxSelectedPositionIds.size > 0
  const unsavedInput = open && (
    plannedShipmentDateDraft !== (workspace?.supply.planned_shipment_date ?? '') ||
    boxCount !== '1' || boxAssignmentDirty || addableSelected.size > 0 ||
    Boolean(kizScanValue.trim() || kizScanActive || kizConfirmTarget)
  )
  useEffect(() => {
    onDirtyChange?.(unsavedInput)
    return () => onDirtyChange?.(false)
  }, [unsavedInput, onDirtyChange])
  const requestClose = () => {
    if (confirmDiscardChanges(unsavedInput)) {
      onDirtyChange?.(false)
      onClose()
    }
  }
  const closeBoxAssignment = () => {
    if (!confirmDiscardChanges(boxAssignmentDirty)) return
    setBoxProductQty({})
    setBoxSelectedPositionIds(new Set())
    setBoxAssignTarget(null)
  }
  const closeAddOrders = () => {
    if (!confirmDiscardChanges(addableSelected.size > 0)) return
    setAddableSelected(new Set())
    setAddOrdersOpen(false)
  }

  // WMS-631 R4: WB packing scans go through one mechanism in the supply and in the assembly.
  const useSequentialPacking = workspace?.supply.marketplace === 'wb'
  const assemblyWbPacking = useSequentialPacking && Boolean(assemblyFrame?.registerScanner)
  const ordinaryWbPacking = useSequentialPacking && !assemblyFrame?.registerScanner
  const sequentialOpenRef = useRef(false)
  sequentialOpenRef.current = useSequentialPacking && open && stage === 'packing'
    && (assemblyFrame?.registerScanner ? Boolean(assemblyFrame.visible) : true)
  const scanPrintPreferencesRef = useRef(scanPrintPreferences)
  scanPrintPreferencesRef.current = scanPrintPreferences
  useEffect(() => () => { sequentialOpenRef.current = false }, [])
  const sequentialWorkspaceRef = useRef(workspace)
  sequentialWorkspaceRef.current = workspace
  const sequentialFrameRef = useRef(assemblyFrame)
  sequentialFrameRef.current = assemblyFrame
  const [, setSequentialScanVersion] = useState(0)
  const sequentialRefreshRef = useRef<() => void>(() => undefined)
  const sequentialScanner = useMemo(() => {
    if (!workspace || !useSequentialPacking) return null
    const controller = createPackingScanController(makePackingScanDeps(token, authHeaders,
      () => sequentialWorkspaceRef.current!,
      () => { setSequentialScanVersion((version) => version + 1); sequentialFrameRef.current?.onScanChange?.() },
      () => sequentialRefreshRef.current(),
      () => sequentialOpenRef.current && sequentialWorkspaceRef.current?.supply.id === supplyId,
      () => assemblyOpenBoxIdRef.current,
      (orderId, value) => setKizCommittedTails((current) => ({ ...current, [orderId]: kizValueTail(value) })),
      (orderId) => {
        setRecentlyScannedOrderId(orderId)
        const selectedSupplyId = sequentialWorkspaceRef.current?.supply.id
        if (selectedSupplyId) sequentialFrameRef.current?.onPromotePackingOrder?.(selectedSupplyId, orderId)
      },
      // R3: the assembly bar saves the shared checkboxes; the supply keeps them in its state too.
      () => (sequentialFrameRef.current?.registerScanner
        ? loadFbsScanPrintPreferences(token)
        : scanPrintPreferencesRef.current),
    ))
    return {
      ...controller,
      hasSelectedRow: () => Boolean(kizRowInputRef.current && kizRowTargetRef.current),
      hasPending: () => Boolean(kizRowInputRef.current && kizRowTargetRef.current) || controller.hasPending(),
      view: () => kizRowInputRef.current && kizRowTargetRef.current
        ? { orderId: kizRowTargetRef.current.order_id, name: kizRowTargetRef.current.product.name, needsKiz: true, target: kizRowTargetRef.current }
        : controller.view(),
      // R20: Escape in the row field leaves it; otherwise it drops the started scan.
      canCancel: () => Boolean(kizRowInputRef.current && kizRowTargetRef.current) || Boolean(controller.canCancel?.()),
      cancel: async () => {
        if (kizRowInputRef.current && kizRowTargetRef.current) {
          kizRowInputRef.current.blur()
          return true
        }
        return controller.cancel!()
      },
      scan: async (raw: string) => {
        const target = kizRowInputRef.current && kizRowTargetRef.current
        if (!target) return controller.scan(raw)
        setKizScanValue('')
        kizRowInputRef.current?.blur()
        // The same bind -> native WMS Print -> pack sequence as product scans.
        await controller.scanOrder!(target.order_id, raw, target)
        // Blur already released the explicit selection. A later focus belongs
        // to the next scan and must not be cleared by this completed request.
        sequentialFrameRef.current?.onScanChange?.()
      },
    }
  // The controller owns one immutable supply; refreshed rows do not discard a pending KIZ.
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [token, supplyId, workspace?.supply.id, open, useSequentialPacking])
  const ordinaryWbPackingRef = useRef(false)
  ordinaryWbPackingRef.current = ordinaryWbPacking
  const runUnifiedScanRef = useRef<(raw: string) => Promise<void>>(async () => undefined)
  const cancelUnifiedScanRef = useRef<() => Promise<void>>(async () => undefined)
  const undoUnifiedScanRef = useRef<() => Promise<void>>(async () => undefined)
  // The supply bar shows the row field target or the selection waiting for its KIZ.
  const unifiedView = ordinaryWbPacking ? sequentialScanner?.view() ?? null : null
  const shownKizTarget = kizScanActive ?? (unifiedView?.needsKiz ? unifiedView.target ?? null : null)
  const registerSequentialScanner = assemblyFrame?.registerScanner
  const unifiedStickerAttempts = useRef(new Set<string>())
  useEffect(() => { unifiedStickerAttempts.current.clear() }, [open, supplyId])
  useEffect(() => {
    if (!supplyId || !registerSequentialScanner) return
    registerSequentialScanner(supplyId, sequentialScanner)
    return () => registerSequentialScanner(supplyId, null)
  }, [supplyId, sequentialScanner, registerSequentialScanner])
  const isOzonSupply = workspace?.supply.marketplace === 'ozon'
  const boxesWithoutDistribution = !isOzonSupply && Boolean(workspace?.supply.boxes_without_distribution)
  const providerName = isOzonSupply ? 'Ozon' : 'WB'
  const boxOperationsDisabled = fbsBoxOperationsDisabled(
    workspace?.supply.marketplace ?? 'wb',
  )
  const workspaceOpenGeneration = useRef(0)
  useEffect(() => {
    workspaceOpenGeneration.current += 1
    return () => { workspaceOpenGeneration.current += 1 }
  }, [open, supplyId])
  // Поставка, чей состав сейчас на экране. Ответ обязан назвать её сам: иначе
  // сохранённое «Повторить» из прежней поставки занимает номер записи уже в новом
  // открытии и её состав ложится на открытую поставку (WMS-477).
  const shownSupplyId = useRef<string | null>(initialWorkspace?.supply.id ?? null)
  useEffect(() => {
    shownSupplyId.current = workspace?.supply.id ?? null
  }, [workspace])

  // Тихое обновление раз в 15 с идёт рядом с действиями оператора, и ответы
  // возвращаются в произвольном порядке. Номер занимается в начале обращения,
  // а применить свой ответ вправе только последнее из начатых: поэтому поздний
  // снимок не возвращает вердикт, который на экране уже сменился, и не убирает
  // заказ, добавленный после старта чтения (WMS-477).
  const workspaceWriteSeq = useRef(0)
  const beginWorkspaceWrite = useCallback(() => {
    const seq = ++workspaceWriteSeq.current
    const generation = workspaceOpenGeneration.current
    return {
      isCurrent: () => workspaceOpenGeneration.current === generation,
      isLatest: () => seq === workspaceWriteSeq.current,
      matchesShownSupply: (next: FbsWorkspace) => next.supply.id === shownSupplyId.current,
    }
  }, [])
  // Ответ может идти дольше 15 с. Пока прежнее тихое обновление не вернулось,
  // следующее не запускаем: иначе каждый ответ устаревает к своему приходу и
  // строки не обновляются вообще.
  const silentRefreshInFlight = useRef(false)

  const load = useCallback(
    // onApplied вызывается только снимком, который действительно лёг на экран:
    // по нему вызвавший вправе назвать оператору итог своей операции (WMS-477).
    async (silent = false, onApplied?: (applied: FbsWorkspace) => void) => {
      if (!open || !supplyId) return
      const write = beginWorkspaceWrite()
      if (!silent) setBusy(true)
      try {
        const next = await fetchFbsWorkspace(token, authHeaders, supplyId)
        if (!write.isCurrent()) return
        if (!write.isLatest()) return next
        setWorkspace(next)
        onApplied?.(next)
        if (!silent) {
          setStage((current) => readFbsWorkspaceStage(supplyId) ?? fbsStageAfterWorkspaceRefresh(
            next.supply.marketplace,
            current,
            visualStage(next.stage),
          ))
        }
        return next
      } catch (cause) {
        if (write.isCurrent() && !silent) setError(cause instanceof Error ? fbsErrorText(cause.message) : 'Не удалось загрузить поставку.')
      } finally {
        if (write.isCurrent() && !silent) setBusy(false)
      }
    },
    [open, supplyId, token, authHeaders, beginWorkspaceWrite],
  )

  useEffect(() => {
    if (!open || !supplyId) return
    setBusy(false)
    setError(null)
    setNotice(null)
    // «Повторить» держит операцию прежней поставки. Оставленная кнопка либо
    // отправила бы её из открытой поставки, либо висела бы мёртвой.
    setRetryAction(null)
    setWorkspace(initialWorkspace ?? null)
    setStage(readFbsWorkspaceStage(supplyId) ?? (initialWorkspace ? visualStage(initialWorkspace.stage) : 'composition'))
    const restoredDeliveryKey = persistentOperationKey(supplyId, 'delivery')
    deliveryKeyRef.current = restoredDeliveryKey
    setPrintBatch(null)
    setPackingSelectedIds(new Set())
    setTransferDialogOpen(false)
    setClearMarkingOrders(null)
    setBoxCount('1')
    setBoxAssignTarget(null)
    setBoxProductSearch('')
    setBoxProductQty({})
    setBoxSelectedPositionIds(new Set())
    setBoxMenu(null)
    setExpandedBoxIds(new Set())
    setOzonAutoBoxesProgress(null)
    setDeliverySubmitted(false)
    setUndoOrderId(null)
    setTzLine(null)
    setReprintMenu(null)
    setAddOrdersOpen(false)
    setAddOrdersBusy(false)
    setAddableOrders([])
    setAddableSelected(new Set())
    // Занятость диалогов принадлежит прежнему открытию: ответ той поставки её
    // уже не снимет, а у открытого окна снятия ЧЗ обе кнопки и закрытие
    // отключены по занятости — оператор остался бы без выхода.
    setSkipHonestSignOpen(false)
    setSkipHonestSignBusy(false)
    setKizScanActive(null)
    kizRowInputRef.current = null
    kizSelectedStickerRef.current = ''
    activeProductScanBarcodeRef.current = null
    queuedPackingScansRef.current = []
    busyHardwareScanBufferRef.current = ''
    busyHardwareCaptureEnabledRef.current = false
    scannerShouldRefocusRef.current = false
    pendingDirectReprintKeysRef.current.clear()
    setKizScanValue('')
    setKizScanBusy(false)
    setKizScanError(null)
    setKizScanHints([])
    setKizScanDebugOpen(false)
    setKizConfirmTarget(null)
    setKizConfirmValue(null)
    setKizScanNotice(null)
    setKizCommittedTails({})
    if (!initialWorkspace) void load()
  }, [open, supplyId, initialWorkspace, load])

  useEffect(() => {
    setNotice(null)
  }, [workspace?.stage])

  useEffect(() => {
    setPlannedShipmentDateDraft(workspace?.supply.planned_shipment_date ?? '')
  }, [workspace?.supply.planned_shipment_date])

  useEffect(() => {
    setScanPrintPreferences(loadFbsScanPrintPreferences(token))
  }, [token])

  // The baseline scanner input is disabled while its request is running.
  // Native scanners then emit into document.body, so buffer only that case and
  // feed the same ordered queue. Ozon retains its pre-WMS-514 behaviour.
  // WMS-575: пока вкладку слушает useScanIntake, коды ловит он, где бы ни был
  // фокус, и этот буфер не нужен — иначе он собрал бы те же символы второй раз
  // и подставил их в поле.
  useLayoutEffect(() => {
    const captureScope = (
      !isOzonSupply
      && open
      && stage === 'packing'
      && !packingScanListeningRef.current
      && busyHardwareCaptureEnabledRef.current
    )
    if (!captureScope) {
      busyHardwareScanBufferRef.current = ''
      return
    }
    if (!kizScanBusy) {
      const prefix = busyHardwareScanBufferRef.current
      busyHardwareScanBufferRef.current = ''
      busyHardwareCaptureEnabledRef.current = false
      if (prefix) {
        setKizScanValue((current) => mergeFbsBufferedHardwareScan(prefix, current))
      }
      return
    }
    const onBusyHardwareKey = (event: globalThis.KeyboardEvent) => {
      if (event.ctrlKey || event.metaKey || event.altKey) return
      const target = event.target
      if (
        target !== document.body
        && target !== document.documentElement
      ) return
      if (event.key === 'Enter') {
        const raw = busyHardwareScanBufferRef.current.replace(/[ \t\r\n\v\f]+$/, '')
        busyHardwareScanBufferRef.current = ''
        if (!raw) return
        event.preventDefault()
        scannerShouldRefocusRef.current = true
        queuedPackingScansRef.current.push({ raw, preferences: { ...scanPrintPreferences } })
        setQueuedPackingScanVersion((current) => current + 1)
        return
      }
      if (event.key.length === 1) busyHardwareScanBufferRef.current += event.key
    }
    document.addEventListener('keydown', onBusyHardwareKey)
    return () => document.removeEventListener('keydown', onBusyHardwareKey)
  }, [kizScanBusy, isOzonSupply, open, stage, scanPrintPreferences])

  useEffect(() => {
    if (!kizScanBusy) return
    const onFocusIn = (event: FocusEvent) => {
      const target = event.target
      if (target === kizScanInputRef.current) return
      if (
        target instanceof HTMLIFrameElement
        && target.getAttribute('aria-hidden') === 'true'
      ) return
      if (isWorkspaceFocusFallback(target as Element | null)) return
      if (target instanceof HTMLElement && target !== document.body) {
        scannerShouldRefocusRef.current = false
      }
    }
    document.addEventListener('focusin', onFocusIn)
    return () => document.removeEventListener('focusin', onFocusIn)
  }, [kizScanBusy])

  // Тихое обновление раз в 15 с при видимом окне. На «Упаковке и маркировке»
  // (WMS-477) так сами зеленеют строки, чей Честный знак WB подтвердил в фоне;
  // load(true) не трогает вкладку, полосу прогресса и состояние скана.
  useEffect(() => {
    if (!open || !supplyId || !['picking', 'packing', 'boxes'].includes(stage)) return
    const timer = window.setInterval(() => {
      if (document.visibilityState !== 'visible' || silentRefreshInFlight.current) return
      silentRefreshInFlight.current = true
      void load(true).finally(() => { silentRefreshInFlight.current = false })
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
        setError(fbsErrorText(await readApiErrorMessage(response)))
        return
      }
      setPackagingTask((await response.json()) as PackagingTask)
    })
    return () => {
      active = false
    }
  }, [open, stage, workspace?.supply.packaging_task_id, workspace?.orders.length, token, authHeaders])

  // Пересечение запросов не даёт применить свой ответ, но и чужой свежим не
  // делает: чтение, начатое позже нашей записи, могло прочитать базу до неё.
  // Поэтому вместо собственного снимка просим новое чтение — оно начинается
  // после успеха операции, поэтому видит его и отменяет все начатые раньше.
  const refreshAfterLostRace = (onApplied?: (applied: FbsWorkspace) => void) => {
    void load(true, onApplied)
  }

  const run = async (
    operation: () => Promise<FbsWorkspace>,
    // Текст успеха может зависеть от ответа (WMS-477: «подтверждено X из Y»);
    // функция сохраняется и для «Повторить», чтобы повтор дал то же уведомление.
    success: string | ((next: FbsWorkspace) => string),
    onError?: (cause: unknown) => void,
  ) => {
    const write = beginWorkspaceWrite()
    setBusy(true)
    setError(null)
    setNotice(null)
    setRetryAction(null)
    try {
      const next = await operation()
      // Пока шёл запрос, могли открыть другую поставку: ни её строки, ни её
      // уведомление и занятость чужой ответ не подменяет. Ответ, назвавший
      // не показанную поставку, чужой независимо от номера записи.
      if (!write.isCurrent() || !write.matchesShownSupply(next)) return null
      // Операция прошла, но её снимок мог устареть, пока шёл запрос: строки
      // на экране им не откатываем. Вызвавшему ответ возвращаем в любом случае —
      // ему нужен факт успеха.
      const applied = write.isLatest()
      if (applied) {
        setWorkspace(next)
        setStage((current) => readFbsWorkspaceStage(next.supply.id) ?? fbsStageAfterWorkspaceRefresh(
          next.supply.marketplace,
          current,
          visualStage(next.stage),
        ))
      } else {
        // Снимок проиграл гонку, но операция сохранена: строки восстановит новое
        // чтение. Итог, считаемый по ответу, называем по его снимку и только если
        // тот лёг на экран этой же поставки: по отброшенному ответу «подтверждено
        // 1 из 1» спорило бы со строкой «WB не принял ЧЗ» (WMS-477, R2).
        const retell = typeof success === 'string' ? null : success
        refreshAfterLostRace((fresh) => {
          if (retell && write.isCurrent() && write.matchesShownSupply(fresh)) setNotice(retell(fresh))
        })
      }
      // Действие выполнено, поэтому о нём говорим всегда. Текст, посчитанный по
      // ответу, ждёт восстановительного чтения, если свой снимок отброшен.
      let message = ''
      if (typeof success === 'string') message = success
      else if (applied) message = success(next)
      if (message) setNotice(message)
      return next
    } catch (cause) {
      if (!write.isCurrent()) return null
      onError?.(cause)
      setError(cause instanceof Error ? fbsErrorText(cause.message) : 'Операция не выполнена.')
      if (cause instanceof FbsApiError && cause.retryable) {
        // Кнопка живёт в общем Alert окна. Повторяем только пока открыта та же
        // поставка, в которой ошибка возникла: иначе нажатие отправило бы её
        // операцию, а ответ лёг бы на состав открытой сейчас поставки.
        setRetryAction(() => () => { if (write.isCurrent()) void run(operation, success, onError) })
      }
      return null
    } finally {
      if (write.isCurrent()) setBusy(false)
    }
  }

  // The unified list has no per-supply Start button. Prepare the missing
  // marketplace stickers on entry, without waiting for the first product scan.
  useEffect(() => {
    if (!open || stage !== 'packing' || !assemblyFrame?.visible || !registerSequentialScanner || !workspace || isOzonSupply) return
    const missing = workspace.orders.filter((order) => !order.sticker.code && !unifiedStickerAttempts.current.has(order.id))
    if (!missing.length) return
    for (const order of missing) unifiedStickerAttempts.current.add(order.id)
    const write = beginWorkspaceWrite()
    void fetchFbsPrintBatch(token, authHeaders, workspace.supply.id, {
      kind: 'order_sticker', order_ids: missing.map((order) => order.id), retry_missing: true,
    }).then((batch) => {
      if (!write.isCurrent()) return
      if (batch.order_errors.length) setError(batch.order_errors.map((item) => item.message).join(' '))
      void load(true)
    }).catch((cause: unknown) => {
      if (write.isCurrent()) setError(cause instanceof Error ? fbsErrorText(cause.message) : 'Стикеры не получены.')
    })
  }, [open, stage, assemblyFrame?.visible, registerSequentialScanner, workspace, isOzonSupply, token, authHeaders, beginWorkspaceWrite, load])

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
      setError(cause instanceof Error ? fbsErrorText(cause.message) : 'Не удалось загрузить новые заказы для поставки.')
    } finally {
      setAddOrdersBusy(false)
    }
  }

  const addOrdersToCurrentSupply = async () => {
    if (!workspace || addableSelected.size === 0) return
    const write = beginWorkspaceWrite()
    setAddOrdersBusy(true)
    setError(null)
    try {
      const next = await addFbsOrdersToSupply(token, authHeaders, workspace.supply.id, {
        order_ids: [...addableSelected],
        idempotency_key: createFbsIdempotencyKey(),
      })
      if (!write.isCurrent() || !write.matchesShownSupply(next)) return
      // Заказы добавлены в любом случае: закрываем окно и говорим об этом.
      // Снимок применяем, только если он не старше показанного, иначе читаем
      // состав заново: старший ответ мог прочитать базу до нашей записи.
      if (write.isLatest()) {
        setWorkspace(next)
        // Добавление заказа — обычное обновление, а не повод вернуть оператора
        // назад. Сервер отдаёт «подбор», пока новый заказ не подобран, и прямой
        // setStage перекидывал человека с упаковки или коробов на подбор. Правило
        // проекта: серверные факты не управляют навигацией в рабочем месте WB.
        setStage((current) => readFbsWorkspaceStage(next.supply.id) ?? fbsStageAfterWorkspaceRefresh(
          next.supply.marketplace,
          current,
          visualStage(next.stage),
        ))
      } else refreshAfterLostRace()
      setAddOrdersOpen(false)
      setAddableSelected(new Set())
      setNotice('Заказы добавлены в поставку.')
    } catch (cause) {
      if (!write.isCurrent()) return
      setError(cause instanceof Error ? fbsErrorText(cause.message) : 'Не удалось добавить заказы в поставку.')
    } finally {
      if (write.isCurrent()) setAddOrdersBusy(false)
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


  // Return focus only while the scanner still owns it. A delayed print must
  // never pull the operator out of another control they deliberately chose.
  const refocusKizInput = useCallback((force = false) => {
    const attempt = (retriesLeft: number, delayMs: number) => window.setTimeout(() => {
      if (!force && !scannerShouldRefocusRef.current) return
      const input = kizScanInputRef.current
      // WMS-575: поле выключено на время запроса и включается только следующей
      // перерисовкой, а фокус в выключенное поле не встаёт — проверено в
      // браузере: focus() приходил раньше перерисовки, и курсор оставался на
      // контейнере окна. Ждём, пока поле включится.
      if (input?.disabled && retriesLeft > 0) {
        attempt(retriesLeft - 1, 16)
        return
      }
      const active = document.activeElement
      const hiddenPrintFrame = (
        active instanceof HTMLIFrameElement
        && active.getAttribute('aria-hidden') === 'true'
      )
      if (
        input
        && (
          force
          || active == null
          || active === document.body
          || active === input
          || hiddenPrintFrame
          || isWorkspaceFocusFallback(active)
        )
      ) {
        input.focus({ preventScroll: true })
      }
      scannerShouldRefocusRef.current = false
    }, delayMs)
    attempt(30, 0)
  }, [])

  const scanIdleCode = useCallback(
    async (raw: string, preferences: FbsScanPrintPreferences) => {
      if (!workspace) return
      // WMS-574 R22: в рамке окна сборки — короб, открытый в момент этого скана.
      const assemblyBoxAtScan = assemblyTakeScanBoxRef.current?.(raw) ?? null
      busyHardwareCaptureEnabledRef.current = (
        !isOzonSupply
        && (preferences.printQr || preferences.printChz || preferences.reprintChz)
      )
      setKizScanBusy(true)
      setKizScanError(null)
      setKizScanHints([])
      setKizScanDebugOpen(false)
      setKizScanNotice(null)
      try {
        // Classification priority 2: a known order sticker wins before a full
        // KIZ or product barcode, even when no automatic print mode is active.
        let stickerNotFound: unknown = null
        try {
          const found = await lookupFbsOrderBySticker(token, authHeaders, workspace.supply.id, raw)
          if (!found.can_bind) {
            setKizScanError({ text: fbsErrorText(found.block_reason ?? 'На этот заказ ЧЗ внести нельзя'), debug: null })
            playScanError()
            return
          }
          if (!workspace.orders.some((order) => order.id === found.order_id)) await load(true)
          kizSelectedStickerRef.current = raw
          setRecentlyScannedOrderId(found.order_id)
          if (found.needs_confirmation) setKizConfirmTarget(found)
          else setKizScanActive(found)
          activeProductScanBarcodeRef.current = null
          // WMS-575: строка заказа ожила — звук сразу, по ответу lookup.
          playScanSuccess()
          // WMS-574 Д8, Д9: в рамке окна сборки найденный заказ ложится в открытый короб.
          if (assemblyPlaceOrderRef.current) await assemblyPlaceOrderRef.current(found.order_id, !found.needs_confirmation, assemblyBoxAtScan)
          return
        } catch (cause) {
          if (!(cause instanceof FbsApiError) || cause.code !== 'sticker_not_found') {
            throw cause
          }
          stickerNotFound = cause
        }

        // Ozon and the all-off state stay on the pre-WMS-514 path. In
        // particular, no product endpoint, selection, event or hidden attempt
        // exists when all three checkboxes are off.
        if (
          isOzonSupply
          || (!preferences.printQr && !preferences.printChz && !preferences.reprintChz)
        ) throw stickerNotFound

        // Classification priority 3: direct exact-KIZ reprint.  A normal
        // product barcode receives not_a_kiz and continues to priority 4.
        if (preferences.reprintChz) {
          const idempotencyKey = pendingDirectReprintKeysRef.current.get(raw)
            ?? createFbsIdempotencyKey()
          pendingDirectReprintKeysRef.current.set(raw, idempotencyKey)
          try {
            const row = await saveFbsDirectKizReprint(
              token,
              authHeaders,
              workspace.supply.id,
              raw,
              idempotencyKey,
            )
            let directPrintStarted = false
            const printAttemptKey = createFbsIdempotencyKey()
            const queued = await kizAutoPrintQueueRef.current.enqueue(
              {
                attemptId: `direct:${row.id}:${printAttemptKey}`,
                orderId: row.id,
                kiz: row.kiz,
                enabled: true,
              },
              async () => {
                const result = await startAutoKizReprintPrint(
                  row,
                  printAttemptKey,
                  (codes) => printMarkingCodeLabels(codes, { duplicateCopies: 1 }),
                  {
                    claim: (_saved, attemptKey) => claimFbsDirectKizPrint(
                      token, authHeaders, workspace.supply.id, row.id, attemptKey,
                    ),
                    markStarted: () => markFbsDirectKizPrintStarted(
                      token, authHeaders, workspace.supply.id, row.id,
                    ),
                    releaseClaim: (_saved, attemptKey) => releaseFbsDirectKizPrintClaim(
                      token, authHeaders, workspace.supply.id, row.id, attemptKey,
                    ),
                  },
                )
                directPrintStarted = result.printStarted
              },
            )
            pendingDirectReprintKeysRef.current.delete(raw)
            setKizScanNotice(
              queued && directPrintStarted
                ? 'Точная копия ЧЗ отправлена в печать.'
                : 'Этот скан ЧЗ уже был отправлен в печать; повторная копия не создана.',
            )
            playScanSuccess()
            return
          } catch (cause) {
            if (cause instanceof FbsApiError && cause.code === 'not_a_kiz') {
              pendingDirectReprintKeysRef.current.delete(raw)
            } else {
              throw cause
            }
          }
        }

        // Classification priority 4: deterministic product-unit selection.
        const attempt = claimFbsPendingProductScan(
          token,
          workspace.supply.id,
          raw,
          preferences,
          createFbsIdempotencyKey,
        )
        const plan = productScanPrintPlan(attempt.preferences)
        const result = await scanFbsProductForAutoPrint(
          token,
          authHeaders,
          workspace.supply.id,
          {
            barcode: raw,
            idempotency_key: attempt.idempotencyKey,
            print_qr: plan.printQr,
            print_chz: plan.printChz,
            reprint_chz: plan.reprintChz,
          },
        )
        if (
          (attempt.scanId && attempt.scanId !== result.scan_id)
          || (attempt.orderId && attempt.orderId !== result.order_id)
        ) throw new Error('Сервер вернул другой заказ для незавершённого скана.')
        attempt.scanId = result.scan_id
        attempt.orderId = result.order_id
        updateFbsPendingProductScan(token, workspace.supply.id, attempt)
        setRecentlyScannedOrderId(result.order_id)
        // WMS-575, Д5: заказ выбран сервером — звук по ответу scan-auto-print.
        // Печать идёт своей очередью ниже; её сбой даст сигнал ошибки отдельно.
        playScanSuccess()
        // WMS-574 Д8: в рамке окна сборки выбранный заказ ложится в открытый короб.
        if (assemblyPlaceOrderRef.current) await assemblyPlaceOrderRef.current(result.order_id, false, assemblyBoxAtScan)

        const qrStartedBefore = attempt.qrStarted
        const chzStartedBefore = attempt.chzStarted
        let reprintAlreadyStarted = false
        let waitingForReprintKiz = plan.reprintChz && !attempt.chzStarted
        if (waitingForReprintKiz && result.reprint_recovery?.status === 'started') {
          attempt.chzStarted = true
          updateFbsPendingProductScan(token, workspace.supply.id, attempt)
          reprintAlreadyStarted = true
          waitingForReprintKiz = false
        }

        const printErrors: string[] = []
        if (plan.printQr && !attempt.qrStarted) {
          if (!result.qr_asset) {
            printErrors.push('Стикер QR заказа не получен.')
          } else {
            try {
              const printAttemptKey = createFbsIdempotencyKey()
              await kizAutoPrintQueueRef.current.enqueue(
                {
                  attemptId: `${result.scan_id}:qr:${printAttemptKey}`,
                  orderId: result.order_id,
                  kiz: result.qr_asset.id,
                  enabled: true,
                },
                async () => {
                  const printResult = await startClaimedAutomaticPrint(
                    printAttemptKey,
                    async () => printFbsOrderQrAsset(token, result.qr_asset!),
                    {
                      claim: (attemptKey) => claimFbsScanAutoPrintTarget(
                        token,
                        authHeaders,
                        workspace.supply.id,
                        result.scan_id,
                        'qr',
                        attemptKey,
                      ),
                      markStarted: (attemptKey) => markFbsScanAutoPrintTargetStarted(
                        token,
                        authHeaders,
                        workspace.supply.id,
                        result.scan_id,
                        'qr',
                        attemptKey,
                      ),
                      releaseClaim: (attemptKey) => releaseFbsScanAutoPrintTargetClaim(
                        token,
                        authHeaders,
                        workspace.supply.id,
                        result.scan_id,
                        'qr',
                        attemptKey,
                      ),
                    },
                  )
                  if (!printResult.started) {
                    throw new Error('Сервер не подтвердил запуск печати QR.')
                  }
                },
              )
              attempt.qrStarted = true
              updateFbsPendingProductScan(token, workspace.supply.id, attempt)
            } catch (cause) {
              printErrors.push(cause instanceof Error ? cause.message : 'Не удалось запустить печать QR.')
            }
          }
        }
        if (plan.printChz && !result.requires_honest_sign) {
          attempt.chzStarted = true
          updateFbsPendingProductScan(token, workspace.supply.id, attempt)
        } else if (plan.printChz && !attempt.chzStarted) {
          const printed = result.printed_codes[0]
          if (!printed) {
            printErrors.push(
              result.shortage > 0
                ? 'Не хватает ЧЗ для выбранной единицы.'
                : 'ЧЗ выбранной единицы не подготовлен.',
            )
          } else {
            try {
              const printAttemptKey = createFbsIdempotencyKey()
              await kizAutoPrintQueueRef.current.enqueue(
                {
                  attemptId: `${result.scan_id}:chz:${printAttemptKey}`,
                  orderId: result.order_id,
                  kiz: printed.cis_code,
                  enabled: true,
                },
                async (kiz) => {
                  const printResult = await startClaimedAutomaticPrint(
                    printAttemptKey,
                    async () => printMarkingCodeTape(
                      [{ cis: kiz, codeId: printed.id, hasLabelArtifact: printed.has_label_artifact }],
                      { units: [{ block: 'cz', copies: 1 }] },
                      undefined,
                      { authToken: token },
                    ),
                    {
                      claim: (attemptKey) => claimFbsScanAutoPrintTarget(
                        token,
                        authHeaders,
                        workspace.supply.id,
                        result.scan_id,
                        'chz',
                        attemptKey,
                      ),
                      markStarted: (attemptKey) => markFbsScanAutoPrintTargetStarted(
                        token,
                        authHeaders,
                        workspace.supply.id,
                        result.scan_id,
                        'chz',
                        attemptKey,
                      ),
                      releaseClaim: (attemptKey) => releaseFbsScanAutoPrintTargetClaim(
                        token,
                        authHeaders,
                        workspace.supply.id,
                        result.scan_id,
                        'chz',
                        attemptKey,
                      ),
                    },
                  )
                  if (!printResult.started) {
                    throw new Error('Сервер не подтвердил запуск печати ЧЗ.')
                  }
                },
              )
              attempt.chzStarted = true
              updateFbsPendingProductScan(token, workspace.supply.id, attempt)
            } catch (cause) {
              printErrors.push(cause instanceof Error ? cause.message : 'Не удалось запустить печать ЧЗ.')
            }
          }
        }
        if (waitingForReprintKiz) {
          const recovery = result.reprint_recovery
          if (recovery?.status === 'available') {
            try {
              const printAttemptKey = createFbsIdempotencyKey()
              await kizAutoPrintQueueRef.current.enqueue(
                {
                  attemptId: `${result.scan_id}:reprint:${printAttemptKey}`,
                  orderId: result.order_id,
                  // Printable bytes are returned only by the atomic claim
                  // inside this queued job; the product response never carries
                  // a stale KIZ across the recovery→claim boundary.
                  kiz: result.scan_id,
                  enabled: true,
                },
                async () => {
                  const printResult = await startClaimedAutomaticPrint<FbsScanAutoPrintReprintClaim>(
                    printAttemptKey,
                    async (claim) => {
                      if (!claim.kiz) {
                        throw new Error('Сервер не подтвердил канонический ЧЗ для перепечати.')
                      }
                      await printMarkingCodeLabels([claim.kiz], { duplicateCopies: 1 })
                    },
                    {
                      claim: (attemptKey) => claimFbsScanAutoPrintReprint(
                        token,
                        authHeaders,
                        workspace.supply.id,
                        result.scan_id,
                        attemptKey,
                      ),
                      markStarted: (attemptKey) => markFbsScanAutoPrintTargetStarted(
                        token,
                        authHeaders,
                        workspace.supply.id,
                        result.scan_id,
                        'chz',
                        attemptKey,
                      ),
                      releaseClaim: (attemptKey) => releaseFbsScanAutoPrintTargetClaim(
                        token,
                        authHeaders,
                        workspace.supply.id,
                        result.scan_id,
                        'chz',
                        attemptKey,
                      ),
                    },
                  )
                  if (!printResult.started) {
                    throw new Error('Сервер не подтвердил запуск перепечати ЧЗ.')
                  }
                },
              )
              attempt.chzStarted = true
              updateFbsPendingProductScan(token, workspace.supply.id, attempt)
              waitingForReprintKiz = false
            } catch (cause) {
              printErrors.push(cause instanceof Error ? cause.message : 'Не удалось запустить перепечать ЧЗ.')
            }
          } else if (recovery?.status === 'outcome_unknown') {
            printErrors.push('Исход предыдущего запуска перепечати ЧЗ неизвестен; автоматический повтор остановлен.')
          } else {
            if (!result.binding_target) {
              throw new Error('Сервер не вернул выбранный заказ для скана ЧЗ.')
            }
            kizSelectedStickerRef.current = ''
            activeProductScanBarcodeRef.current = raw
            // Product selection must not bypass the existing replacement
            // confirmation when this exact order already has a KIZ.
            if (result.binding_target.needs_confirmation) {
              setKizConfirmTarget(result.binding_target)
            } else {
              setKizScanActive(result.binding_target)
            }
          }
        }
        printErrors.push(...result.order_errors.map((item) => item.message))

        const attemptComplete = fbsPendingProductScanComplete(attempt)
        if (attemptComplete) {
          completeFbsPendingProductScan(token, workspace.supply.id, raw)
        }

        if (printErrors.length > 0) {
          setKizScanError({
            text: `Заказ WB № ${result.wb_order_id} выбран. ${printErrors.join(' ')}`,
            debug: null,
          })
          playScanError()
          return
        }
        const sent = [
          plan.printQr && !qrStartedBefore && attempt.qrStarted ? 'QR' : null,
          (plan.printChz || plan.reprintChz)
            && !chzStartedBefore
            && attempt.chzStarted
            && !reprintAlreadyStarted
            ? 'ЧЗ'
            : null,
        ]
          .filter(Boolean)
          .join(' → ')
        setKizScanNotice(
          waitingForReprintKiz
            ? `${sent ? `${sent} заказа WB № ${result.wb_order_id} отправлен в печать. ` : ''}Выбран заказ WB № ${result.wb_order_id}; сканируйте полный ЧЗ.`
            : sent
            ? `${sent} заказа WB № ${result.wb_order_id} отправлены в печать.`
            : reprintAlreadyStarted
            ? `Перепечать ЧЗ заказа WB № ${result.wb_order_id} уже была запущена; повторная копия не создана.`
            : `Выбран заказ WB № ${result.wb_order_id}; автоматическая печать выключена.`,
        )
        // Перечитывание поставки догоняет в фоне и не держит следующий скан (Д5).
        if (plan.printChz) void load(true)
      } catch (cause) {
        setKizScanError({
          // WMS-574 R16: код не из активной поставки окна сборки называет её номер WB.
          text: assemblyScanErrorTextRef.current?.(cause, raw) ?? kizErrorText(cause, providerName),
          debug: kizScannerDebug(cause),
        })
        playScanError()
      } finally {
        setKizScanBusy(false)
        refocusKizInput()
      }
    },
    [workspace, token, authHeaders, load, providerName, refocusKizInput, isOzonSupply],
  )

  const scanKizCode = useCallback(
    async (
      raw: string,
      confirmed = false,
      preferences: FbsScanPrintPreferences = scanPrintPreferences,
    ) => {
      if (!kizScanActive) return
      if (kizRowCommitGateRef.current) return
      // Прямой выбор строки заменяет только выбор заказа стикером. Подтверждение
      // прежнего КИЗ и запись остаются в общем сценарии validate/commit.
      if (kizRowInputRef.current && kizScanActive.current_kiz && !confirmed) {
        setKizConfirmValue(raw)
        setKizConfirmTarget(kizScanActive)
        return
      }
      const productBarcode = activeProductScanBarcodeRef.current
      const pendingProductAttempt = productBarcode && workspace?.supply.id
        ? peekFbsPendingProductScan(token, workspace.supply.id, productBarcode)
        : null
      // Выбор конкретной строки меняет только способ выбора заказа. Настройки
      // печати остаются теми же, что и в штатном сценарии сканирования.
      const effectivePreferences = pendingProductAttempt?.preferences ?? preferences
      const scan = {
        attemptId: createFbsIdempotencyKey(),
        orderId: kizScanActive.order_id,
        enabled: !isOzonSupply && effectivePreferences.reprintChz,
        workspaceGeneration: workspaceOpenGeneration.current,
      }
      busyHardwareCaptureEnabledRef.current = (
        !isOzonSupply
        && (
          effectivePreferences.printQr
          || effectivePreferences.printChz
          || effectivePreferences.reprintChz
        )
      )
      setKizScanBusy(true)
      setKizScanError(null)
      setKizScanHints([])
      setKizScanDebugOpen(false)
      setKizScanNotice(null)
      let releaseRowCommit: (() => void) | undefined
      if (kizRowInputRef.current) {
        kizRowCommitGateRef.current = new Promise<void>((resolve) => { releaseRowCommit = resolve })
      }
      try {
        const validated = await validateFbsKiz(token, authHeaders, kizScanActive.order_id, raw)
        setKizScanHints(validated.hints)
        if (assemblyWbPacking && workspace && !workspace.supply.packaging_task_id) {
          const started = await startFbsSupplyWork(token, authHeaders, workspace.supply.id)
          if (!started.supply.packaging_task_id) throw new Error('Не удалось начать работу с поставкой. Повторите скан.')
          setWorkspace(started)
        }
        const results = await commitFbsKiz(
          token,
          authHeaders,
          [{
            order_id: kizScanActive.order_id,
            value: raw,
            confirmed: confirmed || kizScanActive.needs_confirmation,
            ...(pendingProductAttempt?.scanId
              ? { scan_auto_print_id: pendingProductAttempt.scanId }
              : {}),
          }],
          scan.attemptId,
        )
        const outcome = results.find((item) => item.order_id === kizScanActive.order_id)
        if (!outcome) throw new Error('Сервер не подтвердил сохранение кода')
        if (outcome.status !== 'ok') {
          if (outcome.code === 'needs_confirmation' && isOzonSupply) {
            setKizConfirmValue(raw)
            setKizConfirmTarget(kizScanActive)
            playScanSuccess()
            return
          }
          setKizScanError({
            text: kizErrorTextByCode(outcome.code ?? '', outcome.message ?? 'Не сохранено', null, providerName),
            debug: null,
          })
          playScanError()
          // Перечитывание — в фоне: следующий скан его не ждёт (WMS-575, Д5).
          void load(true)
          return
        }
        // WMS-575, Д5: код сохранён — хвост в строке и звук сразу, по ответу
        // commit. Перечитывание поставки и вердикт WB догоняют ниже, в фоне.
        if (outcome.bound_kiz) {
          const committedTail = kizValueTail(outcome.bound_kiz)
          setKizCommittedTails((current) => ({ ...current, [kizScanActive.order_id]: committedTail }))
        }
        playScanSuccess()
        let boundReprintStarted = false
        if (outcome.newly_bound === true && scan.enabled) {
          const durableScanId = pendingProductAttempt?.scanId
          if (!durableScanId && !outcome.bound_kiz) {
            setKizScanError({
              text: `ЧЗ для заказа ${fbsKizOrderNumber(kizScanActive)} сохранён, но перепечатка не запущена: сервер не вернул сохранённый код.`,
              debug: null,
            })
          } else {
            try {
              const printAttemptKey = createFbsIdempotencyKey()
              boundReprintStarted = await kizAutoPrintQueueRef.current.enqueue(
                {
                  ...scan,
                  attemptId: durableScanId
                    ? `${durableScanId}:reprint:${printAttemptKey}`
                    : scan.attemptId,
                  kiz: durableScanId ? durableScanId : outcome.bound_kiz!,
                },
                async (kiz) => {
                  if (!durableScanId || !workspace?.supply.id) {
                    await printMarkingCodeLabels([kiz], { duplicateCopies: 1 })
                    return
                  }
                  const printResult = await startClaimedAutomaticPrint<FbsScanAutoPrintReprintClaim>(
                    printAttemptKey,
                    async (claim) => {
                      if (!claim.kiz) {
                        throw new Error('Сервер не подтвердил канонический ЧЗ для перепечати.')
                      }
                      await printMarkingCodeLabels([claim.kiz], { duplicateCopies: 1 })
                    },
                    {
                      claim: (attemptKey) => claimFbsScanAutoPrintReprint(
                        token,
                        authHeaders,
                        workspace.supply.id,
                        durableScanId,
                        attemptKey,
                      ),
                      markStarted: (attemptKey) => markFbsScanAutoPrintTargetStarted(
                        token,
                        authHeaders,
                        workspace.supply.id,
                        durableScanId,
                        'chz',
                        attemptKey,
                      ),
                      releaseClaim: (attemptKey) => releaseFbsScanAutoPrintTargetClaim(
                        token,
                        authHeaders,
                        workspace.supply.id,
                        durableScanId,
                        'chz',
                        attemptKey,
                      ),
                    },
                  )
                  if (!printResult.started) {
                    throw new Error('Сервер не подтвердил запуск перепечати ЧЗ.')
                  }
                },
              )
            } catch (cause) {
              if (workspaceOpenGeneration.current !== scan.workspaceGeneration) return
              const reason = cause instanceof Error ? fbsErrorText(cause.message) : 'Не удалось запустить печать ЧЗ.'
              setKizScanError({
                text: `ЧЗ для заказа ${fbsKizOrderNumber(kizScanActive)} сохранён, но не напечатан: ${reason}`,
                debug: null,
              })
            }
          }
        }
        setKizScanNotice(isOzonSupply
          ? outcome.meta_status === 'accepted'
            ? `Код принят Ozon · ${fbsKizOrderNumber(kizScanActive)}`
            : `Код сохранён · Ozon проверяет · ${fbsKizOrderNumber(kizScanActive)}`
          : null)
        if (productBarcode && workspace?.supply.id) {
          if (pendingProductAttempt) {
            if (boundReprintStarted) {
              pendingProductAttempt.chzStarted = true
              updateFbsPendingProductScan(token, workspace.supply.id, pendingProductAttempt)
            }
            if (fbsPendingProductScanComplete(pendingProductAttempt)) {
              completeFbsPendingProductScan(token, workspace.supply.id, productBarcode)
            }
          }
          activeProductScanBarcodeRef.current = null
        }
        if (kizRowInputRef.current) {
          kizRowInputRef.current.blur()
          kizRowInputRef.current = null
        }
        setKizScanActive(null)
        kizSelectedStickerRef.current = ''
        const savedOrderId = kizScanActive.order_id
        const savedOrderNumber = fbsKizOrderNumber(kizScanActive)
        // Перечитывание поставки и вердикт WB приходят, когда придут, и не
        // держат следующий скан (WMS-575, Д5): вкладка освобождается сразу.
        void (async () => {
          try {
            const refreshed = await load(true)
            if (!isOzonSupply) {
              const savedOrder = refreshed?.orders.find((order) => order.id === savedOrderId)
              const verdict = fbsMarkingPresentation(savedOrder?.metadata.states.find((state) => state.kind === 'sgtin'), providerName)
              if (verdict.label) {
                const text = `${verdict.label}${verdict.reason ? `: ${verdict.reason}` : ''} · ${savedOrderNumber}`
                if (verdict.tone === 'error') {
                  setKizScanError({ text, debug: null })
                  playScanError()
                } else setKizScanNotice(text)
              }
            }
          } finally {
            setKizCommittedTails((current) => {
              if (!(savedOrderId in current)) return current
              const next = { ...current }
              delete next[savedOrderId]
              return next
            })
          }
        })()
      } catch (cause) {
        setKizScanError({ text: kizErrorText(cause, providerName), debug: kizScannerDebug(cause) })
        playScanError()
        void load(true)
      } finally {
        if (releaseRowCommit) {
          kizRowCommitGateRef.current = null
          releaseRowCommit()
        }
        setKizScanBusy(false)
        refocusKizInput()
      }
    },
    [kizScanActive, token, authHeaders, refocusKizInput, load, isOzonSupply, providerName, scanPrintPreferences, workspace, assemblyWbPacking],
  )
  // WMS-403: keep the original scanner reset; WMS-514 additionally closes only
  // its own pending product attempt so a later physical scan is a new action.
  const dropKizScanActive = useCallback(() => {
    const productBarcode = activeProductScanBarcodeRef.current
    if (productBarcode && workspace?.supply.id) {
      // Reset is an explicit cancellation of the selected product unit. A
      // later physical scan must receive a fresh request id/snapshot instead
      // of reviving the cancelled attempt forever.
      completeFbsPendingProductScan(token, workspace.supply.id, productBarcode)
    }
    kizRowInputRef.current?.blur()
    kizRowInputRef.current = null
    setKizScanActive(null)
    kizSelectedStickerRef.current = ''
    activeProductScanBarcodeRef.current = null
    setKizScanValue('')
    setKizScanError(null)
    setKizScanHints([])
    setKizScanNotice(null)
    setKizScanDebugOpen(false)
    setKizConfirmTarget(null)
    setKizConfirmValue(null)
    refocusKizInput(true)
  }, [refocusKizInput, token, workspace?.supply.id])

  useLayoutEffect(() => {
    kizRowTargetRef.current = kizScanActive
  }, [kizScanActive])
  useEffect(() => { sequentialFrameRef.current?.onScanChange?.() }, [kizScanActive])

  const dismissKizConfirmation = useCallback(() => {
    if (kizRowInputRef.current) {
      dropKizScanActive()
      return
    }
    const productBarcode = activeProductScanBarcodeRef.current
    if (productBarcode && workspace?.supply.id) {
      completeFbsPendingProductScan(token, workspace.supply.id, productBarcode)
      activeProductScanBarcodeRef.current = null
    }
    setKizConfirmTarget(null)
    refocusKizInput(true)
  }, [dropKizScanActive, refocusKizInput, token, workspace?.supply.id])

  const onKizScanEnter = useCallback(
    (event: KeyboardEvent<HTMLInputElement>) => {
      if (event.key === 'Escape' && ordinaryWbPacking) {
        if (sequentialScanner?.canCancel?.()) {
          event.preventDefault()
          event.stopPropagation()
          void cancelUnifiedScanRef.current()
        }
        return
      }
      if (event.key === 'Escape' && kizScanActive) {
        event.preventDefault()
        event.stopPropagation()
        dropKizScanActive()
        return
      }
      if (event.key !== 'Enter') return
      event.preventDefault()
      const raw = kizScanValue.replace(/[ \t\r\n\v\f]+$/, '')
      if (!raw) return
      if (assemblyWbPacking) {
        document.dispatchEvent(new CustomEvent('fbs-packing-row-scan', { detail: raw }))
        setKizScanValue('')
        return
      }
      if (ordinaryWbPacking) {
        // The row target is read synchronously by the controller before any blur.
        setKizScanValue('')
        acceptPackingScanRef.current(raw)
        return
      }
      // Detach the accepted hardware payload synchronously. No async branch is
      // allowed to clear this state later, otherwise a fast following scan is
      // concatenated with or erased by the previous request.
      setKizScanValue('')
      scannerShouldRefocusRef.current = (
        document.activeElement == null
        || document.activeElement === document.body
        || document.activeElement === kizScanInputRef.current
        || document.activeElement === kizRowInputRef.current
      )
      const scanInput = kizRowInputRef.current ?? kizScanInputRef.current
      if (scanInput && document.activeElement === scanInput) {
        // Move the hardware target to body before the busy render disables the
        // original field. The document buffer can then receive every byte of
        // a scanner burst that starts before the first request completes.
        scanInput.blur()
      }
      acceptPackingScanRef.current(raw)
    },
    [kizScanValue, kizScanActive, dropKizScanActive, assemblyWbPacking, ordinaryWbPacking, sequentialScanner],
  )

  // WMS-631 R4: the ordinary WB supply sends every scan to the assembly mechanism.
  runUnifiedScanRef.current = async (raw: string) => {
    if (!sequentialScanner) return
    setKizScanBusy(true)
    setKizScanError(null)
    setKizScanHints([])
    setKizScanNotice(null)
    setKizScanDebugOpen(false)
    try {
      await routePackingScan([sequentialScanner], raw)
      playScanSuccess()
    } catch (cause) {
      setKizScanError({
        text: cause instanceof Error ? fbsErrorText(cause.message) : 'Не удалось обработать скан.',
        debug: kizScannerDebug(cause),
      })
      playScanError()
    } finally {
      setKizScanBusy(false)
      refocusKizInput()
    }
  }
  // R19: «Назад» undoes the newest scan; a failure stays in the history.
  undoUnifiedScanRef.current = async () => {
    if (!sequentialScanner?.undo) return
    setKizScanBusy(true)
    setKizScanError(null)
    try {
      await sequentialScanner.undo()
    } catch (cause) {
      setKizScanError({ text: cause instanceof Error ? fbsErrorText(cause.message) : 'Не удалось отменить скан.', debug: null })
      playScanError()
    } finally {
      setKizScanBusy(false)
      refocusKizInput(true)
    }
  }
  // R20: Escape (or «Сбросить») drops the started scan and frees its order.
  cancelUnifiedScanRef.current = async () => {
    if (!sequentialScanner?.cancel) return
    setKizScanError(null)
    try {
      await sequentialScanner.cancel()
    } catch (cause) {
      setKizScanError({ text: cause instanceof Error ? fbsErrorText(cause.message) : 'Не удалось снять выбор.', debug: null })
      playScanError()
    } finally {
      refocusKizInput(true)
    }
  }
  useEffect(() => {
    if (!ordinaryWbPacking || !open || stage !== 'packing') return
    const onKeyDown = (event: globalThis.KeyboardEvent) => {
      if (event.key !== 'Escape' || !sequentialScanner?.canCancel?.()) return
      event.preventDefault()
      event.stopPropagation()
      void cancelUnifiedScanRef.current()
    }
    document.addEventListener('keydown', onKeyDown, true)
    return () => document.removeEventListener('keydown', onKeyDown, true)
  }, [ordinaryWbPacking, open, stage, sequentialScanner])

  // Один приём кода для поля скана и для слушателя всей вкладки (WMS-575):
  // что делает скан, решает прежняя логика — ожидание ЧЗ, поиск стикера,
  // галки WMS-514; код, пришедший во время обработки, ждёт в очереди.
  const acceptPackingScan = useCallback(
    (raw: string) => {
      const preferences = { ...scanPrintPreferences }
      if (kizScanBusy) {
        queuedPackingScansRef.current.push({ raw, preferences })
        setQueuedPackingScanVersion((current) => current + 1)
        return
      }
      if (ordinaryWbPacking) {
        void runUnifiedScanRef.current(raw)
        return
      }
      if (kizScanActive && fbsSameStickerScan(raw, kizSelectedStickerRef.current)) {
        dropKizScanActive()
        playScanSuccess()
        return
      }
      if (kizScanActive) void scanKizCode(raw, false, preferences)
      else void scanIdleCode(raw, preferences)
    },
    [kizScanBusy, kizScanActive, scanKizCode, scanIdleCode, dropKizScanActive, scanPrintPreferences, ordinaryWbPacking],
  )
  useLayoutEffect(() => {
    acceptPackingScanRef.current = acceptPackingScan
  }, [acceptPackingScan])

  // Код со сканера, пойманный слушателем вкладки, где бы ни стоял фокус.
  const acceptHardwarePackingScan = useCallback((code: string) => {
    const raw = code.replace(/[ \t\r\n\v\f]+$/, '')
    if (!raw) return
    const active = document.activeElement
    // Фокус возвращается в поле, только если он и был у поля (или нигде):
    // кнопку, которую оператор выбрал сам, сканер у него не отнимает.
    scannerShouldRefocusRef.current = (
      active == null
      || active === document.body
      || active === kizScanInputRef.current
      || active === kizRowInputRef.current
      || isWorkspaceFocusFallback(active)
    )
    if (active === kizRowInputRef.current) {
      setKizScanValue('')
      // WMS-631: the unified controller reads the row target first and blurs it itself.
      if (!ordinaryWbPackingRef.current) kizRowInputRef.current?.blur()
    }
    acceptPackingScanRef.current(raw)
  }, [])

  useEffect(() => {
    if (kizScanBusy) return
    const next = queuedPackingScansRef.current.shift()
    if (!next) return
    setQueuedPackingScanVersion((current) => current + 1)
    if (ordinaryWbPacking) {
      void runUnifiedScanRef.current(next.raw)
      return
    }
    // WMS-575: код из очереди разбирается по состоянию на момент обработки,
    // как обычный скан. Сканер дважды прочитал стикер, пока шёл поиск: первый
    // выбрал заказ, второй — тот же стикер — снимает выбор, а не уходит как ЧЗ.
    if (kizScanActive && fbsSameStickerScan(next.raw, kizSelectedStickerRef.current)) {
      dropKizScanActive()
      playScanSuccess()
      return
    }
    if (kizScanActive) void scanKizCode(next.raw, false, next.preferences)
    else void scanIdleCode(next.raw, next.preferences)
  }, [kizScanBusy, kizScanActive, queuedPackingScanVersion, scanIdleCode, scanKizCode, dropKizScanActive, ordinaryWbPacking])

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
      setError(cause instanceof Error ? fbsErrorText(cause.message) : 'Стикеры не получены.')
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
      setError(cause instanceof Error ? fbsErrorText(cause.message) : 'QR короба не подготовлен.')
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
        setError('Этикетки Ozon ещё не готовы. Соберите заказ в коробе и получите этикетку.')
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
      setError(cause instanceof Error ? fbsErrorText(cause.message) : 'QR коробов не подготовлены.')
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
    if (next) {
      clearPersistentOperationKey(workspace.supply.id, 'box-create', `${boxMode}:${count}`)
      setBoxCount('1')
    }
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
      selectStage('boxes')
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
      // WMS-526 R12: причина отказа сохраняется у заказа на сервере — перечитываем
      // снимок, чтобы красная строка у коробов заказа появилась сразу.
      isOzonSupply ? () => refreshAfterLostRace() : undefined,
    )
    if (!next) return
    selectStage('boxes')
    const box = next.boxes.find((item) => item.id === boxId)
    if (box?.qr_asset?.status === 'ready' && box.qr_asset.preview_url) openAssetPreview([box.qr_asset])
    else if (isOzonSupply) setNotice(box?.qr_asset?.error?.message ?? 'Этикетка Ozon ещё не готова — повторите получение через минуту.')
  }

  // WMS-526: одна серверная операция раскладывает каждую неразложенную позицию
  // Ozon в свой новый короб; затем этикетки запрашиваются тем же запросом, что у
  // кнопки короба «Собрать и получить этикетку», — по одному на заказ, по очереди.
  // Сбой заказа не останавливает остальные; окна печати не открываются.
  const autoCreateOzonBoxes = async () => {
    if (!workspace || !isOzonSupply || boxEditingDisabled || ozonAutoBoxesRunningRef.current) return
    ozonAutoBoxesRunningRef.current = true
    const session = beginWorkspaceWrite()
    const supplyIdAtStart = workspace.supply.id
    setBusy(true)
    setError(null)
    setNotice(null)
    setRetryAction(null)
    setOzonAutoBoxesProgress('Раскладка…')
    // Ответ ложится на экран, только если открыта та же поставка и он последний
    // из начатых; иначе состав восстановит новое чтение, как в run().
    const applyResponse = (write: ReturnType<typeof beginWorkspaceWrite>, next: FbsWorkspace) => {
      if (!write.isCurrent() || !write.matchesShownSupply(next)) return false
      if (write.isLatest()) setWorkspace(next)
      else refreshAfterLostRace()
      return true
    }
    try {
      let write = beginWorkspaceWrite()
      let assigned: FbsWorkspace & { created_boxes: number }
      try {
        assigned = await autoAssignFbsOzonBoxes(token, authHeaders, supplyIdAtStart)
      } catch (cause) {
        if (write.isCurrent()) setError(cause instanceof Error ? fbsErrorText(cause.message) : 'Короба не созданы.')
        return
      }
      if (!applyResponse(write, assigned)) return
      // Число коробов, созданных именно этим вызовом, называет сервер: разница
      // со своим снимком ошиблась бы, если короба добавил другой оператор.
      const created = assigned.created_boxes
      const { labelTargets } = fbsOzonAutoBoxesPlan(assigned.orders, assigned.boxes)
      let received = 0
      const failures: Array<{ externalOrderId: string | null; reason: string }> = []
      for (const [index, target] of labelTargets.entries()) {
        setOzonAutoBoxesProgress(`Этикетки ${index + 1} из ${labelTargets.length}`)
        write = beginWorkspaceWrite()
        try {
          const next = await retryFbsPackingBoxQr(token, authHeaders, supplyIdAtStart, target.boxId)
          if (!applyResponse(write, next)) return
          const ready = next.boxes.some((box) => box.assigned_order_ids.includes(target.orderId) && fbsOzonBoxLabelReady(box))
          if (ready) received += 1
          else failures.push({ externalOrderId: target.externalOrderId, reason: 'Этикетка Ozon ещё не готова — повторите получение через минуту.' })
        } catch (cause) {
          if (!write.isCurrent()) return
          failures.push({
            externalOrderId: target.externalOrderId,
            reason: cause instanceof Error ? fbsErrorText(cause.message) : 'Этикетка не получена.',
          })
        }
      }
      setNotice(`Создано коробов: ${created}. Этикетки Ozon получены для заказов: ${received}.`)
      if (failures.length > 0) {
        setError(fbsOzonLabelFailuresText(failures))
        // Неудачный запрос не вернул снимок, а сборка могла успеть изменить заказ.
        refreshAfterLostRace()
      }
    } finally {
      ozonAutoBoxesRunningRef.current = false
      if (session.isCurrent()) {
        setBusy(false)
        setOzonAutoBoxesProgress(null)
      }
    }
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
      selectStage('boxes')
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
        cause instanceof Error ? fbsErrorText(cause.message) : `Не удалось получить ответ ${providerName}.`,
      )
    } finally {
      setDeliveryPreflightLoading(false)
    }
  }

  const refreshPackagingTask = useCallback(async () => {
    const taskId = workspace?.supply.packaging_task_id
    if (!taskId) {
      await load(true)
      return
    }
    try {
      const response = await fetch(apiUrl(`/operations/packaging-tasks/${taskId}`), { headers: { ...authHeaders(token) } })
      if (response.ok) setPackagingTask((await response.json()) as PackagingTask)
    } catch {
      // Обновление задания не критично: следующая загрузка workspace синхронизирует состояние.
    }
    await load(true)
  }, [workspace?.supply.packaging_task_id, token, authHeaders, load])

  const requiresOrderHonestSign = (order: FbsWorkspace['orders'][number]) => {
    // Пропуск снимает выдачу новых ЧЗ, но сохранённый код можно печатать повторно.
    if (workspace?.supply.honest_sign_skipped) {
      return order.metadata.states.some((state) => state.kind === 'sgtin' && Boolean(state.value_tail))
    }
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

  const markingShortageForOrders = (orders: FbsWorkspace['orders']) => {
    const needed = new Map<string, number>()
    for (const order of orders) {
      if (requiresOrderHonestSign(order) && order.product.id && !kizTail(order)) {
        needed.set(order.product.id, (needed.get(order.product.id) ?? 0) + 1)
      }
    }
    return [...needed].reduce((sum, [productId, quantity]) =>
      sum + Math.max(0, quantity - (packLineByProduct.get(productId)?.marking_available_count ?? 0)), 0)
  }

  const openBulkOrderMarkingPrint = (orders: Array<FbsWorkspace['orders'][number]>, reprint = false) => {
    if (!workspace || orders.length === 0) return
    const firstOrder = orders[0]
    const firstProductId = firstOrder?.product.id
      ?? (isOzonSupply ? firstOrder?.positions.find((position) => position.product_id)?.product_id : null)
    const firstLine = firstProductId ? packLineByProduct.get(firstProductId) : undefined
    if (!firstOrder || !firstProductId) return
    const firstOzonPosition = isOzonSupply ? firstOrder.positions[0] : undefined
    const anyHonestSign = orders.some(requiresOrderHonestSign)
    const tapeOrders = orders.map((order) => ({
      orderId: order.id,
      wbOrderId: order.wb_order_id,
      marketplace: workspace.supply.marketplace,
      requiresHonestSign: requiresOrderHonestSign(order),
      productLabel: productLabelFromOrder(order, workspace.supply.marketplace),
      productLabels: productLabelsFromOrder(order, workspace.supply.marketplace),
    }))
    openPrint(
      {
        token,
        productId: firstProductId,
        sellerId: workspace.supply.seller.id,
        documentNumber: workspace.supply.name,
        qtyNeedPack: anyHonestSign ? tapeOrders.filter((order) => order.requiresHonestSign).length : tapeOrders.length,
        markingAvailable: markingAvailableForOrders(orders),
        qtyMarkingPrinted: orders.filter(orderPrintDone).length,
        requiresHonestSign: anyHonestSign,
        skuCode: firstOzonPosition?.sku ?? firstOzonPosition?.seller_article ?? firstLine?.sku_code ?? firstOrder.product.seller_article
          ?? (isOzonSupply ? `Ozon-${firstOrder.external_order_id ?? firstOrder.id}` : `WB-${firstOrder.wb_order_id}`),
        productName: firstOzonPosition?.name ?? workspace.supply.name,
        productLabel: productLabelFromOrder(firstOrder, workspace.supply.marketplace),
        productBarcodeOptions: isOzonSupply && firstOzonPosition
          ? productBarcodeOptionsForPosition(firstOzonPosition, 'ozon')
          : productBarcodeOptionsForOrder(firstOrder, workspace.supply.marketplace),
        fbsTape: {
          orders: tapeOrders,
          selectedBarcodeOrderId: isOzonSupply ? firstOrder.id : undefined,
          selectedBarcodePositionId: isOzonSupply ? firstOzonPosition?.id ?? undefined : undefined,
          markingShortage: markingShortageForOrders(orders),
          includeOrderQr: !isOzonSupply,
          print: ({ layout, allowPartial, reprint: printReprint }) => {
            const body: FbsOrderPrintTapeRequest = {
              order_ids: orders.map((order) => order.id),
              layout_json: layout,
              allow_partial: allowPartial,
              include_order_qr: !isOzonSupply,
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

  const clearSelectedMarking = async () => {
    if (!clearMarkingOrders || !workspace) return
    setBusy(true)
    setError(null)
    setNotice(null)
    let cleared = 0
    try {
      // Первый отказ WB останавливает операцию; повтор затрагивает только
      // оставшиеся выбранные заказы. Успешно снятые коды остаются void.
      for (const order of clearMarkingOrders) {
        if (!order.metadata.states.some((state) => state.kind === 'sgtin' && state.value_tail)) continue
        try {
          await deleteFbsOrderKiz(token, authHeaders, order.id)
        } catch (cause) {
          const message = cause instanceof Error ? fbsErrorText(cause.message) : 'Операция не выполнена.'
          setError(`Заказ № ${order.wb_order_id}: ${message} Очистка остановлена. Очищено: ${cleared}.`)
          return
        }
        cleared += 1
        setPackingSelectedIds((current) => {
          const next = new Set(current)
          next.delete(order.id)
          return next
        })
      }
      setNotice(`ЧЗ очищены у ${cleared} заказов.`)
    } finally {
      setClearMarkingOrders(null)
      try {
        // DELETE removes both the WB value and the saved WMS snapshot. Reload the
        // workspace immediately so the old tail cannot remain in the open row
        // until the next 15-second background refresh.
        await Promise.all([refreshPackagingTask(), load(true)])
      } finally {
        setBusy(false)
      }
    }
  }

  /** Печать ЧЗ и ШК заказа через стандартный конструктор системы. */
  const openOrderMarkingPrint = (
    order: FbsWorkspace['orders'][number],
    line?: PackagingTaskLine,
    reprint = false,
    reprintMarkingId?: string,
  ) => {
    const productId = order.product.id
      ?? (workspace?.supply.marketplace === 'ozon'
        ? order.positions.find((position) => position.product_id)?.product_id
        : null)
    if (!workspace || !productId) return
    const ozonPosition = workspace.supply.marketplace === 'ozon' ? order.positions[0] : undefined
    // WMS-575: явная перепечатка конкретного уже внесённого кода («Перепечатать ЧЗ»,
    // «Перепечатать» у кода оператора) печатает именно этот ЧЗ, даже если товару
    // маркировка не обязательна: иначе окно печати выключало перепечатку и брало
    // шаблон без ЧЗ. Обычная печать (без id кода) решает по обязательности, как раньше.
    const printsHonestSign = requiresOrderHonestSign(order) || Boolean(reprintMarkingId)
    openPrint(
      {
        token,
        lineId: line?.id,
        productId,
        sellerId: workspace?.supply.seller.id,
        documentNumber: workspace?.supply.name ?? null,
        qtyNeedPack: printsHonestSign ? 1 : 0,
        markingAvailable: printsHonestSign ? (line?.marking_available_count ?? 0) : 0,
        qtyMarkingPrinted: orderPrintDone(order) ? 1 : 0,
        requiresHonestSign: printsHonestSign,
        skuCode: ozonPosition?.sku ?? ozonPosition?.seller_article ?? line?.sku_code ?? order.product.sku ?? order.product.seller_article
          ?? (workspace.supply.marketplace === 'ozon' ? `Ozon-${order.external_order_id ?? order.id}` : `WB-${order.wb_order_id}`),
        productName: ozonPosition?.name ?? line?.product_name ?? order.product.name,
        packagingInstructions: line?.packaging_instructions,
        productLabel: productLabelFromOrder(order, workspace.supply.marketplace),
        productBarcodeOptions: workspace.supply.marketplace === 'ozon' && ozonPosition
          ? productBarcodeOptionsForPosition(ozonPosition, 'ozon')
          : productBarcodeOptionsForOrder(order, workspace.supply.marketplace),
        fbsTape: {
          orders: [{
            orderId: order.id,
            wbOrderId: order.wb_order_id,
            marketplace: workspace.supply.marketplace,
            requiresHonestSign: printsHonestSign,
            productLabel: productLabelFromOrder(order, workspace.supply.marketplace),
            productLabels: productLabelsFromOrder(order, workspace.supply.marketplace),
          }],
          selectedBarcodeOrderId: workspace.supply.marketplace === 'ozon' ? order.id : undefined,
          selectedBarcodePositionId: workspace.supply.marketplace === 'ozon' ? ozonPosition?.id ?? undefined : undefined,
          markingShortage: markingShortageForOrders([order]),
          includeOrderQr: false,
          print: ({ layout, allowPartial, reprint: printReprint }) => {
            const body: FbsOrderPrintTapeRequest = {
              order_ids: [order.id],
              layout_json: layout,
              allow_partial: allowPartial,
              include_order_qr: false,
              reprint: printReprint,
              reprint_marking_ids: reprintMarkingId ? [reprintMarkingId] : undefined,
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
        headers: { ...authHeaders(token), 'Content-Type': 'application/json' },
        body: JSON.stringify({ order_ids: packingOrders.map((order) => order.id) }),
      })
      if (!done.ok) {
        setError(fbsErrorText(await readApiErrorMessage(done)))
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
      const refreshed = await load()
      // WMS-574 R24: в рамке окна сборки заказы без короба ложатся в открытый короб.
      if (assemblyAfterPackAllRef.current) await assemblyAfterPackAllRef.current(refreshed ?? null)
    } catch (cause) {
      setError(cause instanceof Error ? fbsErrorText(cause.message) : 'Не удалось завершить упаковку.')
    } finally {
      setBusy(false)
    }
  }

  sequentialRefreshRef.current = () => { void load(true); void refreshPackagingTask() }

  const performSkipHonestSign = async () => {
    if (!workspace) return
    const write = beginWorkspaceWrite()
    setSkipHonestSignBusy(true)
    setError(null)
    try {
      const next = await skipFbsSupplyHonestSign(token, authHeaders, workspace.supply.id)
      if (!write.isCurrent() || !write.matchesShownSupply(next)) return
      // Требование снято на сервере; спорным остаётся только снимок состава.
      if (write.isLatest()) setWorkspace(next)
      else refreshAfterLostRace()
      setSkipHonestSignOpen(false)
      setNotice('Требование Честного знака снято со всей поставки.')
    } catch (cause) {
      if (!write.isCurrent()) return
      setError(cause instanceof Error ? fbsErrorText(cause.message) : 'Не удалось снять требование Честного знака.')
    } finally {
      if (write.isCurrent()) setSkipHonestSignBusy(false)
    }
  }

  // WMS-477: «Проверить в WB» — один запрос по поставке, ответ перерисовывает
  // строки; ошибка WB уходит в общий красный Alert окна через run().
  const checkMarkingsInWb = () => {
    if (!workspace) return
    void run(
      () => syncFbsSupplyMarkings(token, authHeaders, workspace.supply.id),
      (next) => {
        const { confirmed, withCode } = fbsMarkingVerdictsSummary(next.orders)
        return `Проверено в WB: подтверждено ${confirmed} из ${withCode}.`
      },
    )
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
  // WMS-580: лист подбора и лента «Печать всего»/«Печать выбранного» должны идти
  // в одной последовательности — общая сборка fbsBuildPickingRows (fbsUx.ts)
  // отдаёт и отсортированный по tape_order_index список (для ленты), и строки
  // листа, построенные группировкой по этому же списку, так что расхождение
  // между ними структурно невозможно (регрессия чинилась трижды за один день
  // 23.08.2026 — см. docs/requirements/WMS-580.md).
  const { sortedOrders: fullTapeOrders, rows: pickingRows } = useMemo(() => {
    if (!workspace) return { sortedOrders: [], rows: [] }
    return fbsBuildPickingRows(workspace.orders, isOzonSupply)
  }, [workspace, isOzonSupply])
  const printPickingList = async () => {
    if (!workspace) return
    const printWindow = window.open('', '_blank')
    if (!printWindow) {
      setError('Браузер заблокировал окно печати. Разрешите всплывающие окна и повторите.')
      return
    }
    printWindow.opener = null
    setError(null)
    printWindow.document.write('<title>Лист подбора</title><p style="font:14px Arial,sans-serif">Готовим лист подбора…</p>')
    // WMS-528: где брать — ячейки и тара по убыванию остатка, ровно на покрытие подбора.
    // Без ответа сервера лист печатается с прежними ячейками, печать не блокируется.
    let rows: typeof pickingRows = pickingRows
    try {
      // Подобранное берём из того же свежего ответа, что и места: экран мог не перечитаться после подбора.
      const options = new Map((await getFbsPickOptions(token, authHeaders, workspace.supply.id))
        .map((option) => [option.product_id, option]))
      rows = pickingRows.map((row) => {
        const option = options.get(row.key)
        if (!option) return row
        const picked = Math.min(option.picked_qty, row.required)
        return { ...row, picked, locations: fbsPickSourceLabels(option.locations, row.required - picked) }
      })
    } catch {
      rows = pickingRows.map((row) => (row.locations.length ? row : { ...row, locations: ['—'] }))
      setError('Не удалось получить ячейки и тару — лист подбора напечатан без них.')
    }
    if (printWindow.closed) return
    printWindow.document.open()
    printWindow.document.write(buildFbsPickingListPrintHtml({
      supplyName: workspace.supply.name,
      wbSupplyId: workspace.supply.wb_supply_id,
      sellerName: workspace.supply.seller.name,
      wmsWarehouseName: workspace.supply.wms_warehouse.name,
      routeLabel: workspace.supply.delivery_type === 'pvz' ? 'ПВЗ' : 'Склад / СЦ',
      deadlineLabel: new Date(workspace.supply.nearest_deadline_at).toLocaleString('ru-RU'),
      printedAtLabel: new Date().toLocaleString('ru-RU'),
      rows,
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
      if (a.id === recentlyScannedOrderId) return -1
      if (b.id === recentlyScannedOrderId) return 1
      const byName = a.product.name.localeCompare(b.product.name, 'ru')
      if (byName !== 0) return byName
      return a.wb_order_id - b.wb_order_id
    })
  }, [workspace, recentlyScannedOrderId])

  // WB ставит ЧЗ в optional, поэтому после «Очистить ЧЗ» проверка «метки приняты»
  // проходит по пустому списку. Без кода заказ не напечатан, иначе «Печать всего»
  // уходит в перепечатку, и сервер молча отвечает nothing_to_reprint.
  const orderPrintDone = (order: FbsWorkspace['orders'][number]) =>
    (Boolean(order.sticker.applied_at) || STICKER_PRINTED_STATUSES.includes(order.sticker.status)) &&
    fbsOrderMarkingAccepted(order.metadata) &&
    (isOzonSupply
      || !requiresOrderHonestSign(order)
      || order.metadata.states.some((state) => state.kind === 'sgtin' && Boolean(state.value_tail)))

  const packingShowsSize = fbsPackingShowsSize(packingOrders, isOzonSupply)
  // Слот «Доступно ЧЗ» занимает место во всех строках вкладки, если он нужен хотя бы
  // одной: иначе строка без ЧЗ раздвигает блок товара и размер со стикером уезжают вправо.
  const packingShowsMarkingAvailable = packingOrders.some(requiresOrderHonestSign)
  const printedOrdersCount = packingOrders.filter(orderPrintDone).length
  // Выбор сохраняет тот же порядок, что и исходная лента / лист подбора.
  const selectedPackingOrders = fullTapeOrders.filter((order) => packingSelectedIds.has(order.id))
  const printPackingOrders = selectedPackingOrders.length ? selectedPackingOrders : fullTapeOrders
  const markingNeededByProduct = new Map<string, number>()
  for (const order of packingOrders) {
    const hasWorkingCode = order.metadata.states.some((state) => state.kind === 'sgtin'
      && ['assigned', 'sending', 'pending', 'accepted', 'allowed_without_check'].includes(state.status))
    if (order.product.id && requiresOrderHonestSign(order) && !hasWorkingCode) {
      markingNeededByProduct.set(order.product.id, (markingNeededByProduct.get(order.product.id) ?? 0) + 1)
    }
  }
  const clearableSelectedCount = selectedPackingOrders.filter((order) =>
    order.metadata.states.some((state) => state.kind === 'sgtin' && state.value_tail),
  ).length
  // WMS-477: пока ни у одного заказа нет кода, спрашивать WB не о чем.
  const packingOrdersWithCode = fbsMarkingVerdictsSummary(packingOrders).withCode
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
  const cancelledDeliveryOrders = isOzonSupply ? [] : deliveryPreflight?.cancelled_orders ?? []
  const deliveryConfirmLabel = cancelledDeliveryOrders.length > 0
    ? 'Передать без этих заказов'
    : `Передать в ${providerName}`
  const ozonDeliveryRoute = workspace?.orders.find((order) => Boolean(order.delivery_route))?.delivery_route
  const workspaceRouteLabel = isOzonSupply
    ? ozonDeliveryRoute ?? 'Метод доставки Ozon не указан'
    : workspace?.supply.delivery_type === 'pvz' ? 'ПВЗ' : 'Склад / СЦ'
  const packagingEditable = !deliveryConfirmed
  // WMS-575: вкладка «Упаковка и маркировка» принимает скан, где бы ни стоял
  // курсор, — ровно тогда, когда на ней есть рабочее поле скана.
  // WMS-574 R22: код со сканера пришёл — запоминаем, какой короб рамки был открыт.
  // Записи идут по порядку прихода: у каждого принятого скана свой короб, даже
  // если коды одинаковые (три одинаковые вещи подряд). Старые записи — по возрасту.
  const rememberAssemblyScanBox = useCallback((code: string) => {
    const raw = code.replace(/[ \t\r\n\v\f]+$/, '')
    const now = Date.now()
    const state = assemblyScanStateRef.current
    if (state.active && !state.busy && fbsSameStickerScan(raw, kizSelectedStickerRef.current)) return
    assemblyScanBoxesRef.current = [
      ...assemblyScanBoxesRef.current.filter((entry) => now - entry.at < 60_000),
      { code: raw, boxId: assemblyOpenBoxIdRef.current, at: now },
    ]
  }, [])
  const packingScanIntake = useScanIntake({
    enabled: open
      && !assemblyWbPacking
      && stage === 'packing'
      && Boolean(workspace)
      && Boolean(packagingTask)
      && anyOrderNeedsHonestSign
      && packagingEditable
      // WMS-574: в окне сборки сканер слушает только активная рамка на открытой вкладке.
      && (!assemblyFrame || (assemblyFrame.active && assemblyFrame.visible)),
    onScan: acceptHardwarePackingScan,
    // На сервер — те же символы, что легли бы в поле скана, с разделителем GS:
    // раскладку ЧЗ и стикера чинит сервер полной таблицей, как до WMS-575.
    emitRaw: true,
    // WMS-574 R22: в рамке запоминаем открытый короб в момент, когда код пришёл.
    onReceived: assemblyFrame ? rememberAssemblyScanBox : undefined,
  })
  useLayoutEffect(() => {
    packingScanListeningRef.current = packingScanIntake.listening
  }, [packingScanIntake.listening])
  // Короба — рабочая поверхность, а не ступень после упаковки. Серверный stage
  // не гасит действия внутри открытой вкладки; редактирование прекращается
  // только после передачи поставки.
  const boxEditingDisabled = fbsBoxEditingDisabled(
    workspace?.supply.marketplace ?? 'wb',
    deliveryConfirmed,
  )
  const assignedBoxOrderIds = new Set(workspace?.boxes.flatMap((box) => box.assigned_order_ids) ?? [])
  const boxProductProgress = fbsBoxProductProgress(workspace?.orders ?? [], assignedBoxOrderIds, boxProductQty)
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
  const hasNoDistributionBoxes = boxesWithoutDistribution
  const boxDistributedCount = isOzonSupply ? ozonPositionRows.reduce((sum, row) => sum + (assignedBoxPositionIds.has(row.id) ? row.position.quantity : 0), 0) : assignedBoxOrderIds.size
  const boxTotalCount = isOzonSupply ? (workspace?.orders ?? []).reduce((sum, order) => sum + order.positions.reduce((qty, position) => qty + position.quantity, 0), 0) : workspace?.progress.total ?? 0
  const boxRemainingCount = Math.max(0, boxTotalCount - boxDistributedCount)
  const ozonAutoBoxesPlan = isOzonSupply && workspace ? fbsOzonAutoBoxesPlan(workspace.orders, workspace.boxes) : null
  const ozonAutoBoxesNothingToDo = !ozonAutoBoxesPlan
    || (ozonAutoBoxesPlan.unassignedPositions === 0 && ozonAutoBoxesPlan.labelTargets.length === 0)
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
          selectStage(next.key)
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

  // ── WMS-574: рамка поставки в окне групповой сборки ─────────────────────
  // Всё ниже работает только при assemblyFrame. Запросы — те же функции, что
  // у кнопок карточки: start-work, создание короба, назначение в короб, QR.

  // R17, R19: новый короб — тот же запрос, что «Добавить короба» при числе 1,
  // с тем же сохраняемым ключом повтора; он становится открытым. WMS-589:
  // создание короба само не запрашивает и не печатает QR — печать запускают
  // только явные кнопки QR/«Печать всех QR» либо правила авто-печати скана.
  const createAssemblyBox = async (snapshot?: FbsWorkspace) => {
    const current = snapshot ?? workspace
    if (!current || boxOperationsDisabled || assemblyBoxCreatingRef.current) return
    assemblyBoxCreatingRef.current = true
    setAssemblyBoxCreating(true)
    try {
      const withoutDistribution = !isOzonSupply && Boolean(current.supply.boxes_without_distribution)
      const fingerprint = `${withoutDistribution ? 'no-distribution' : 'distribution'}:1`
      const key = persistentOperationKey(current.supply.id, 'box-create', fingerprint)
      const before = new Set(current.boxes.map((box) => box.id))
      const next = await run(
        () => createFbsPackingBoxes(token, authHeaders, current.supply.id, {
          count: 1,
          idempotency_key: key,
          without_distribution: withoutDistribution,
        }),
        '',
      )
      if (!next) return
      clearPersistentOperationKey(current.supply.id, 'box-create', fingerprint)
      const byNumber = [...next.boxes].sort((a, b) => b.box_number - a.box_number)
      const created = byNumber.find((box) => !before.has(box.id)) ?? byNumber[0]
      if (!created) return
      setAssemblyOpenBoxId(created.id)
      setAssemblyBoxHint(null)
    } finally {
      assemblyBoxCreatingRef.current = false
      setAssemblyBoxCreating(false)
    }
  }

  // R13, R17: start-work — только если у поставки нет задания упаковки (Д6);
  // затем открывается последний короб, а если коробов нет — создаётся первый.
  const startAssemblyWork = async () => {
    if (!assemblyFrame || !workspace || assemblyStarting) return
    setAssemblyStarting(true)
    try {
      let current = workspace
      if (!current.supply.packaging_task_id) {
        const next = await run(() => startFbsSupplyWork(token, authHeaders, current.supply.id), '')
        if (!next) return
        current = next
      }
      assemblyFrame.onActivate()
      setAssemblyBoxHint(null)
      const last = [...current.boxes].sort((a, b) => b.box_number - a.box_number)[0]
      if (last) {
        setAssemblyOpenBoxId(last.id)
        return
      }
      if (!boxEditingDisabled) await createAssemblyBox(current)
    } finally {
      setAssemblyStarting(false)
    }
  }

  // R20: открыть и закрыть короб можно всегда; запросов нет.
  const toggleAssemblyBox = (boxId: string) => {
    setAssemblyBoxHint(null)
    setAssemblyOpenBoxId((current) => (current === boxId ? null : boxId))
  }

  /** Ответ назначения в короб ложится так же, как ответы других действий карточки. */
  const assignToAssemblyBox = async (current: FbsWorkspace, boxId: string, orderIds: string[]) => {
    const write = beginWorkspaceWrite()
    const next = await assignFbsPackingBoxOrders(token, authHeaders, current.supply.id, boxId, orderIds)
    if (!write.isCurrent() || !write.matchesShownSupply(next)) return null
    if (write.isLatest()) setWorkspace(next)
    else refreshAfterLostRace()
    return next
  }

  useLayoutEffect(() => {
    if (!assemblyFrame) {
      assemblyPlaceOrderRef.current = null
      assemblyScanErrorTextRef.current = null
      assemblyAfterPackAllRef.current = null
      assemblyTakeScanBoxRef.current = null
      assemblyOpenBoxIdRef.current = null
      assemblyEscapeRef.current = () => false
      return
    }
    const current = workspace
    const openBoxId = current?.boxes.some((box) => box.id === assemblyOpenBoxId) ? assemblyOpenBoxId : null
    assemblyOpenBoxIdRef.current = openBoxId
    // Короб этого скана: запомненный при приёме кода, а для кода, набранного
    // в поле руками, — открытый сейчас, в начале обработки.
    assemblyScanStateRef.current = { active: Boolean(kizScanActive), busy: kizScanBusy }
    assemblyTakeScanBoxRef.current = (raw) => {
      const code = raw.replace(/[ \t\r\n\v\f]+$/, '')
      const entries = assemblyScanBoxesRef.current
      // Самая ранняя запись этого кода — скан, пришедший первым; удаляется только она.
      const position = entries.findIndex((entry) => entry.code === code)
      if (position < 0) return openBoxId
      assemblyScanBoxesRef.current = entries.filter((_, index) => index !== position)
      return entries[position].boxId
    }
    // Д8, Д9, R22–R24: заказ, найденный сканом, — в короб, открытый в момент
    // скана, если ещё ни в каком коробе не лежит; заказу без обязательного ЧЗ
    // ждать ЧЗ незачем.
    assemblyPlaceOrderRef.current = async (orderId, releaseKizWait, boxId) => {
      if (!current) return
      let orders = current.orders
      const alreadyBoxed = current.boxes.some((box) => box.assigned_order_ids.includes(orderId))
      if (!alreadyBoxed) {
        if (!boxId || !current.boxes.some((box) => box.id === boxId)) {
          setAssemblyBoxHint('Откройте или создайте короб.')
          return
        }
        try {
          const next = await assignToAssemblyBox(current, boxId, [orderId])
          if (next) orders = next.orders
        } catch (cause) {
          setKizScanError({ text: cause instanceof Error ? fbsErrorText(cause.message) : 'Заказ не положен в короб.', debug: null })
          playScanError()
          return
        }
      }
      setAssemblyBoxHint(null)
      if (!releaseKizWait) return
      const order = orders.find((one) => one.id === orderId)
      if (order && !requiresOrderHonestSign(order)) dropKizScanActive()
    }
    // R16, Д19: «Этого товара нет в поставке» — только если сервер не нашёл
    // код в поставке и это не ШК товара её заказа и не ЧЗ такого товара;
    // иначе — прежний текст карточки.
    assemblyScanErrorTextRef.current = (cause, raw) => {
      if (!current || !(cause instanceof FbsApiError)) return null
      if (cause.code !== 'sticker_not_found' && cause.code !== 'scan_product_not_found') return null
      if (fbsCodeBelongsToSupply(raw, current)) return null
      return `Этого товара нет в поставке ${current.supply.wb_supply_id ?? current.supply.name}`
    }
    // R24: после «Всё упаковано» заказы без короба — в открытый короб, если он есть.
    assemblyAfterPackAllRef.current = async (snapshot) => {
      const fresh = snapshot ?? current
      if (!fresh || !openBoxId || !fresh.boxes.some((box) => box.id === openBoxId)) return
      const boxed = new Set(fresh.boxes.flatMap((box) => box.assigned_order_ids))
      const orderIds = fbsOrdersAvailableForBox(fresh.orders, boxed).map((order) => order.id)
      if (orderIds.length === 0) return
      try {
        await assignToAssemblyBox(fresh, openBoxId, orderIds)
      } catch (cause) {
        setError(cause instanceof Error ? fbsErrorText(cause.message) : 'Заказы не положены в короб.')
      }
    }
    assemblyEscapeRef.current = () => {
      if (!kizScanActive && !kizScanBusy) return false
      if (!kizScanBusy) dropKizScanActive()
      return true
    }
  })

  const assemblyActive = Boolean(assemblyFrame?.active)
  const assemblyRegisterEscape = assemblyFrame?.registerEscape
  // R15: работа с поставкой завершена — её открытый короб закрывается.
  useEffect(() => {
    if (!assemblyRegisterEscape || assemblyActive) return
    setAssemblyOpenBoxId(null)
    setAssemblyBoxHint(null)
  }, [assemblyActive, assemblyRegisterEscape])
  useEffect(() => {
    if (!assemblyRegisterEscape || !assemblyActive) return
    assemblyRegisterEscape(() => assemblyEscapeRef.current())
    return () => assemblyRegisterEscape(null)
  }, [assemblyActive, assemblyRegisterEscape])
  const assemblyWorkspaceChange = assemblyFrame?.onWorkspaceChange
  useEffect(() => {
    if (workspace && assemblyWorkspaceChange) assemblyWorkspaceChange(workspace)
  }, [workspace, assemblyWorkspaceChange])

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
            .map((order) => `№${order.wb_order_id} — ${fbsErrorText(order.reason ?? 'WB не подтвердил заказ')}`)
            .join('; ')
          : 'нет'}
      </Typography>
    </Alert>
  ) : null

  // Части карточки, которые показывает и рамка поставки в окне сборки (WMS-574).
  // Разметка та же; в обычной карточке они стоят на прежних местах.
  const workspaceMessages = (
    <>
          {error ? <Alert severity="error" sx={{ mb: 2 }} action={retryAction ? <Button color="inherit" size="small" onClick={retryAction}>Повторить</Button> : undefined}>{error}</Alert> : null}
          {notice ? <Alert severity="success" sx={{ mb: 2 }}>{notice}</Alert> : null}
          {stageIsCurrent && stageBlockers.length ? (
            <Alert severity="warning" sx={{ mb: 2 }}>
              <Typography variant="subtitle2">Что нужно исправить</Typography>
              {stageBlockers.map((blocker) => (
                <Typography key={`${blocker.code}-${blocker.order_id ?? ''}`} variant="body2">
                  {fbsErrorText(blocker.message)}
                </Typography>
              ))}
            </Alert>
          ) : null}
          {partialRejectionAlert}
    </>
  )

  const packingRows = workspace ? (
                  <Stack
                    divider={<Divider flexItem />}
                    sx={{ order: assemblyFrame?.promotedSupplyId === supplyId ? -1 : 0 }}
                  >
                    {packingOrders.map((order) => {
                      const line = order.product.id ? packLineByProduct.get(order.product.id) : undefined
                      const printed = orderPrintDone(order)
                      const needsHonestSign = requiresOrderHonestSign(order)
                      const markingNeeded = order.product.id ? markingNeededByProduct.get(order.product.id) ?? 0 : Number(needsHonestSign)
                      const markingAvailable = line?.marking_available_count ?? 0
                      const markingShortage = needsHonestSign && markingAvailable < markingNeeded
                      const mutedColor = printed ? 'text.secondary' : 'text.primary'
                      const kizRowActive = (sequentialScanner?.view()?.orderId ?? kizScanActive?.order_id) === order.id
                      const scanHighlighted = kizRowActive || recentlyScannedOrderId === order.id
                      const ozonPositions = isOzonSupply ? order.positions : []
                      const ids = (isOzonSupply
                        ? [
                          `отправление Ozon ${order.external_order_id ?? '—'}`,
                        ]
                        : [
                          order.product.seller_article,
                          order.product.barcode,
                          `заказ ${order.wb_order_id}`,
                        ]).filter(Boolean).join(' · ')
                      const czStates = order.metadata.states.filter((state) => state.kind === 'sgtin' && state.status !== 'missing')
                      const acceptedCz = czStates.filter((state) => state.status === 'accepted').length
                      const czRejected = czStates.some((state) => state.status === 'rejected' || state.status === 'replacement_required')
                      const czReady = order.metadata.delivery_allowed && czStates.every((state) => state.status === 'accepted')
                      const markingState = isOzonSupply
                        ? czStates.find((state) => state.status === 'rejected' || state.status === 'replacement_required')
                          ?? czStates.find((state) => state.status !== 'accepted') ?? czStates[0]
                        : order.metadata.states.find((state) => state.kind === 'sgtin')
                      const markingView = fbsMarkingPresentation(markingState, providerName)
                      if (isOzonSupply && !czReady && markingView.tone === 'success') {
                        markingView.tone = 'neutral'
                        markingView.label = 'Ozon ещё не подтвердил все коды'
                      }
                      const markingColor = markingView.tone === 'success' ? 'success.dark'
                        : markingView.tone === 'error' ? 'error.main' : 'text.secondary'
                      // Хвост ЧЗ, только что сохранённого сканом, виден сразу по
                      // ответу commit — до перечитывания поставки (WMS-575).
                      const tail = kizCommittedTails[order.id] ?? markingState?.value_tail ?? null
                      const stickerParts = stickerCodeParts(order.sticker.code)
                      const rowSizes = packingShowsSize ? fbsPackingSizes(order, isOzonSupply) : []
                      return (
                        <Stack
                          key={order.id}
                          direction="row"
                          spacing={1.5}
                          sx={{
                            alignItems: 'center',
                            px: 2,
                            py: 1.25,
                            bgcolor: markingView.tone === 'error'
                              ? (theme) => alpha(theme.palette.error.main, 0.08)
                              : scanHighlighted ? 'success.light'
                                : markingView.tone === 'success' ? 'success.light'
                                  : (printed ? 'action.hover' : 'background.paper'),
                            borderLeft: '4px solid',
                            borderLeftColor: markingShortage || markingView.tone === 'error' ? 'error.main'
                              : scanHighlighted ? 'success.main' : markingView.tone === 'success' ? 'success.main' : 'transparent',
                          }}
                          data-testid={kizRowActive ? 'fbs-kiz-row-active' : undefined}
                          data-scan-highlighted={scanHighlighted ? 'true' : undefined}
                          data-kiz-tail={tail ?? ''}
                          data-marking-tone={markingView.tone}
                          data-order-id={order.id}
                        >
                          <Checkbox
                            checked={packingSelectedIds.has(order.id)}
                            disabled={busy}
                            onChange={(_, checked) => setPackingSelectedIds((current) => {
                              const next = new Set(current)
                              if (checked) next.add(order.id)
                              else next.delete(order.id)
                              return next
                            })}
                            slotProps={{ input: { 'aria-label': `Выбрать заказ ${isOzonSupply ? order.external_order_id : order.wb_order_id}` } }}
                            data-testid="fbs-packing-select-order"
                          />
                          <ProductPhotoThumb src={order.product.image_url} alt={order.product.name} size={40} previewSize={280} />
                          <Box sx={{ flex: 1, minWidth: 0 }}>
                            {isOzonSupply ? (
                              <Stack spacing={0.5}>
                                {ozonPositions.map((position, index) => (
                                  <Stack
                                    key={position.id ?? position.product_id ?? position.name}
                                    direction="row"
                                    spacing={1}
                                    sx={{ alignItems: 'flex-start' }}
                                  >
                                    <Box sx={{ flex: 1, minWidth: 0 }}>
                                      <Typography variant="body2" sx={{ fontWeight: 700, color: mutedColor }}>
                                        {position.name}
                                      </Typography>
                                      <Typography variant="caption" sx={{ display: 'block', color: 'text.secondary' }}>
                                        {[position.seller_article, position.sku ? `SKU ${position.sku}` : null, productBarcodeOptionsForPosition(position, 'ozon')[0]?.barcode, ids]
                                          .filter(Boolean)
                                          .join(' · ')}
                                      </Typography>
                                    </Box>
                                    {packingShowsSize ? (
                                      <PackingSizeCell value={rowSizes[index] ?? null} withCaption={index === 0} valueColor={mutedColor} />
                                    ) : null}
                                  </Stack>
                                ))}
                              </Stack>
                            ) : <Stack direction="row" spacing={1} sx={{ alignItems: 'flex-start' }}>
                              <Box sx={{ flex: 1, minWidth: 0 }}>
                                <Typography variant="body2" sx={{ fontWeight: 700, color: mutedColor }}>
                                  {order.product.name}
                                </Typography>
                                <Typography variant="caption" sx={{ display: 'block', color: 'text.secondary' }}>
                                  {ids}
                                </Typography>
                              </Box>
                              {packingShowsSize ? (
                                <PackingSizeCell value={rowSizes[0] ?? null} withCaption valueColor={mutedColor} />
                              ) : null}
                            </Stack>}
                            {markingShortOrderIds.has(order.id) ? <Typography variant="caption" sx={{ display: 'block', color: 'error.main' }}>ЧЗ не хватило</Typography> : null}
                            {markingView.label ? (
                              <Typography variant="caption" sx={{ display: 'block', color: markingColor }} data-testid="fbs-packing-marking-status">
                                {markingView.tone === 'error' ? (
                                  <Tooltip title={markingView.reason ?? markingView.label}>
                                    <ErrorOutlineIcon fontSize="inherit" tabIndex={0} aria-label={markingView.reason ?? markingView.label}
                                      sx={{ verticalAlign: 'text-bottom', mr: 0.5 }} data-testid="fbs-kiz-rejection-hint" />
                                  </Tooltip>
                                ) : null}
                                {markingView.label}{markingView.reason ? `: ${markingView.reason}` : ''}
                              </Typography>
                            ) : null}
                          </Box>
                          {packingShowsMarkingAvailable ? (
                            <Box
                              sx={{ width: 118, flexShrink: 0, textAlign: 'right', color: markingShortage ? 'error.main' : 'text.secondary' }}
                              data-testid={needsHonestSign ? 'fbs-packing-marking-available' : undefined}
                            >
                              {needsHonestSign ? (
                                <>
                                  <Typography variant="caption" sx={{ display: 'block' }}>Доступно ЧЗ</Typography>
                                  <Typography variant="body2" sx={{ fontWeight: markingShortage ? 700 : 400 }}>{markingAvailable} · нужно {markingNeeded}</Typography>
                                </>
                              ) : null}
                            </Box>
                          ) : null}
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
                          <Box sx={{ width: !isOzonSupply && packagingEditable ? 150 : 118, flexShrink: 0, textAlign: 'right' }}>
                            <Typography variant="caption" color="text.secondary" sx={{ display: 'block', lineHeight: 1 }}>
                              ЧЗ
                            </Typography>
                            <Stack direction="row" spacing={0.25} sx={{ alignItems: 'center', justifyContent: 'flex-end' }}>
                              {hasOperatorKiz(markingState, isOzonSupply ? 'ozon' : 'wb') ? (
                                <Tooltip title="Перепечатать ЧЗ">
                                  <IconButton
                                    size="small"
                                    disabled={busy || kizScanBusy}
                                    aria-label="Перепечатать КИЗ"
                                    onClick={() => openOrderMarkingPrint(order, line, true, markingState?.id ?? undefined)}
                                    data-testid="fbs-kiz-reprint-inline"
                                  >
                                    <ReplayOutlinedIcon fontSize="small" />
                                  </IconButton>
                                </Tooltip>
                              ) : null}
                              {!isOzonSupply && packagingEditable ? (
                                <TextField
                                  variant="standard"
                                  size="small"
                                  autoComplete="off"
                                  disabled={busy || kizScanBusy}
                                  value={kizRowActive && kizRowInputRef.current === document.activeElement ? kizScanValue : tail ?? ''}
                                  placeholder={tail ?? '—'}
                                  onFocus={(event) => {
                                    const previousProduct = activeProductScanBarcodeRef.current
                                    if (previousProduct) completeFbsPendingProductScan(token, workspace.supply.id, previousProduct)
                                    activeProductScanBarcodeRef.current = null
                                    kizSelectedStickerRef.current = ''
                                    kizRowInputRef.current = event.target as HTMLInputElement
                                    setKizScanValue('')
                                    setKizScanError(null)
                                    setKizScanHints([])
                                    setKizScanNotice(null)
                                    setKizScanActive({
                                      order_id: order.id,
                                      wb_order_id: order.wb_order_id,
                                      product: order.product,
                                      current_kiz: tail ? { masked: tail, meta_status: markingState?.status ?? '', from_pool: markingState?.source === 'pool' } : null,
                                      needs_confirmation: false,
                                      can_bind: true,
                                      block_reason: null,
                                    })
                                  }}
                                  onChange={(event) => setKizScanValue(event.target.value)}
                                  onBlur={(event) => {
                                    // В единой упаковке выбор строки действует только
                                    // пока курсор в поле. Принятый скан уже держит свой target.
                                    if (useSequentialPacking || (event.relatedTarget instanceof HTMLInputElement
                                      && (event.relatedTarget.dataset.testid === 'fbs-kiz-row-input'
                                        || event.relatedTarget.dataset.packingScan === 'true'))) {
                                      kizRowInputRef.current = null
                                      kizRowTargetRef.current = null
                                      setKizScanActive(null)
                                      setKizScanValue('')
                                    }
                                  }}
                                  onKeyDown={onKizScanEnter}
                                  slotProps={{ htmlInput: { 'aria-label': `КИЗ заказа ${order.wb_order_id}`, 'data-testid': 'fbs-kiz-row-input', 'data-packing-scan': assemblyWbPacking ? 'true' : undefined } }}
                                  sx={{ minWidth: 0, flex: 1, '& input': { fontFamily: 'monospace', fontWeight: 700, fontSize: 15, textAlign: 'right', color: markingColor } }}
                                />
                              ) : tail ? (
                                <Typography
                                  sx={{ fontFamily: 'monospace', fontWeight: 700, fontSize: 15, color: markingColor }}
                                  data-testid="fbs-kiz-tail"
                                >
                                  {tail}
                                </Typography>
                              ) : (
                                <Typography sx={{ color: 'text.disabled', fontSize: 15 }}>—</Typography>
                              )}
                              {!isOzonSupply && hasRemovableKiz(order, 'wb') ? (
                                <IconButton size="small" disabled={busy || kizScanBusy} aria-label="Отменить КИЗ"
                                  onClick={() => setKizUndoOrderId(order.id)} data-testid="fbs-kiz-undo-inline">
                                  <CloseIcon fontSize="small" />
                                </IconButton>
                              ) : null}
                            </Stack>
                            {isOzonSupply && czStates.length > 0 ? <>
                              <Typography variant="caption" sx={{ display: 'block', color: czRejected ? 'error.main' : 'text.secondary' }} data-testid="fbs-ozon-kiz-status">
                                {czRejected ? 'Ozon не подтвердил коды' : `Принято Ozon: ${acceptedCz}${czReady ? ' · все коды' : ''}`}
                                {!czRejected && czStates.some((state) => state.status !== 'accepted') ? ' · проверяется' : ''}
                              </Typography>
                              <Button size="small" disabled={kizScanBusy} onClick={async () => {
                                setKizScanBusy(true)
                                setKizScanError(null)
                                try {
                                  await syncFbsOrderMarkings(token, authHeaders, order.id)
                                  await load(true)
                                  setKizScanNotice(null)
                                } catch (cause) {
                                  setKizScanError({ text: kizErrorText(cause, providerName), debug: null })
                                } finally { setKizScanBusy(false); refocusKizInput(true) }
                              }}>Проверить ЧЗ</Button>
                            </> : null}
                          </Box>
                          <Typography sx={{ width: 16, flexShrink: 0, textAlign: 'center', color: 'success.main', fontWeight: 700 }}>
                            {printed ? '✓' : ''}
                          </Typography>
                          <Stack direction="row" spacing={0.5} sx={{ alignItems: 'center' }}>
                            <Button size="small" variant="outlined" disabled={!line} onClick={() => line && setTzLine(line)}>
                              ТЗ
                            </Button>
                            {!isOzonSupply ? (
                              <Button size="small" variant="outlined" disabled={busy} onClick={() => void requestPrintBatch([order.id])} data-task-id="FBS-09">
                                QR
                              </Button>
                            ) : null}
                            <IconButton size="small" disabled={busy || (!order.product.id && !(isOzonSupply && order.positions.some((position) => position.product_id)))} onClick={() => openOrderMarkingPrint(order, line)} aria-label="Печать ЧЗ и ШК" data-task-id="FBS-10">
                              <PrintOutlinedIcon fontSize="small" />
                            </IconButton>
                            <IconButton
                              size="small"
                              disabled={busy || (!order.product.id && !(isOzonSupply && order.positions.some((position) => position.product_id)))}
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
  ) : null

  const packingPanel = workspace ? (
    <>
              {packagingTask || deliveryConfirmed || assemblyWbPacking ? (
                <Paper variant="outlined" sx={assemblyFrame ? { overflow: 'hidden', border: 0, borderRadius: 0 } : { overflow: 'hidden' }}>
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
                      <Stack direction="row" spacing={1} sx={{ flexWrap: 'wrap' }}>
                        <Button
                          disabled={busy || packingOrders.length === 0}
                          onClick={() => setPackingSelectedIds(selectedPackingOrders.length === packingOrders.length
                            ? new Set()
                            : new Set(packingOrders.map((order) => order.id)))}
                          data-testid="fbs-packing-select-all"
                        >
                          {selectedPackingOrders.length === packingOrders.length && packingOrders.length > 0 ? 'Снять выбор' : 'Выбрать всё'}
                        </Button>
                        <Button
                          disabled={busy || packingOrders.length === 0}
                          onClick={() => openBulkOrderMarkingPrint(
                            printPackingOrders,
                            printPackingOrders.every(orderPrintDone),
                          )}
                          data-task-id="FBS-21"
                        >
                          {selectedPackingOrders.length ? `Печать выбранного (${selectedPackingOrders.length})` : `Печать всего (${packingOrders.length})`}
                        </Button>
                        {!isOzonSupply && packagingEditable ? (
                          <Button
                            disabled={busy || packingOrdersWithCode === 0}
                            onClick={checkMarkingsInWb}
                            data-testid="fbs-packing-check-wb"
                          >
                            Проверить в WB
                          </Button>
                        ) : null}
                        {!isOzonSupply && selectedPackingOrders.length > 0 ? (
                          <Button color="error" disabled={!packagingEditable || busy || clearableSelectedCount === 0} onClick={() => setClearMarkingOrders([...selectedPackingOrders])} data-testid="fbs-packing-clear-selected">
                            Очистить ЧЗ
                          </Button>
                        ) : null}
                        {!isOzonSupply && selectedPackingOrders.length > 0 ? (
                          <Button
                            disabled={!packagingEditable || busy}
                            onClick={() => setTransferDialogOpen(true)}
                            data-testid="fbs-packing-transfer-supply"
                          >
                            Перенести в другую поставку
                          </Button>
                        ) : null}

                        <Button variant="contained" disabled={!packagingEditable || busy || !packagingTask} onClick={() => void packEverything()}>
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
                  {!assemblyWbPacking && anyOrderNeedsHonestSign ? (
                    // KIZ-01: скан живёт прямо на вкладке — стикер заказа подсвечивает
                    // строку активной, следующий скан (Честный знак) привязывает код к
                    // ней и сразу уходит в WB. Окно «Внести КИЗ» для этого больше не нужно.
                    <Box
                      sx={{ px: 2, py: 1.5, borderBottom: 1, borderColor: 'divider', bgcolor: 'action.hover' }}
                      data-testid="fbs-kiz-scan-bar"
                      ref={packingScanIntake.bindRoot}
                    >
                      <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mb: 1 }}>
                        {assemblyFrame
                          ? 'Сканы принимает только активная поставка'
                          : 'Внесение КИЗ со стикера — только если Честный знак уже наклеен селлером'}
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
                          placeholder={shownKizTarget ? 'Сканируйте Честный знак' : (isOzonSupply ? 'Номер отправления или штрихкод Ozon' : 'Сканируйте QR стикера заказа')}
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
                        {!isOzonSupply ? (
                          <FbsScanPrintToggles value={scanPrintPreferences} onChange={(next) => {
                            setScanPrintPreferences(next)
                            saveFbsScanPrintPreferences(token, next)
                          }} undo={ordinaryWbPacking ? {
                            disabled: kizScanBusy || sequentialScanner?.lastStep?.() == null,
                            onClick: () => void undoUnifiedScanRef.current(),
                          } : undefined} />
                        ) : null}
                        {shownKizTarget ? (
                          <Stack direction="row" spacing={1} sx={{ alignItems: 'center', flexShrink: 0 }} data-testid="fbs-kiz-scan-active">
                            <ProductPhotoThumb src={shownKizTarget.product.image_url} alt={shownKizTarget.product.name} size={32} previewSize={220} />
                            <Box sx={{ minWidth: 0 }}>
                              <Typography variant="body2" noWrap sx={{ fontWeight: 700 }}>
                                {shownKizTarget.product.name}
                              </Typography>
                              <Typography variant="caption" color="text.secondary">
                                {providerName} № {fbsKizOrderNumber(shownKizTarget)}
                              </Typography>
                            </Box>
                            <Button size="small" startIcon={<CloseIcon fontSize="small" />} onClick={ordinaryWbPacking ? () => void cancelUnifiedScanRef.current() : dropKizScanActive}
                              disabled={kizScanBusy} data-testid="fbs-kiz-scan-reset">
                              Сбросить
                            </Button>
                          </Stack>
                        ) : null}
                      </Stack>
                      <Typography
                        variant="caption"
                        color="text.secondary"
                        sx={{ display: 'block', mt: 0.75 }}
                        data-testid="fbs-kiz-scan-message"
                      >
                        {shownKizTarget
                          ? `Заказ ${providerName} № ${fbsKizOrderNumber(shownKizTarget)} активен — сканируйте Честный знак, код уйдёт на проверку в ${providerName}.`
                          : isOzonSupply ? 'Введите номер отправления или сканируйте штрихкод Ozon, затем Честный знак каждой единицы товара.' : 'Сканируйте QR стикера заказа — его строка станет активной, затем сканируйте Честный знак.'}
                      </Typography>
                      {kizScanNotice ? <Typography variant="caption" sx={{ display: 'block' }} data-testid="fbs-kiz-scan-result">{kizScanNotice}</Typography> : null}
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
                      {assemblyFrame && assemblyBoxHint ? (
                        <Typography variant="body2" sx={{ color: 'error.main', mt: 0.5 }} data-testid="fbs-assembly-box-hint">
                          {assemblyBoxHint}
                        </Typography>
                      ) : null}
                    </Box>
                  ) : null}
                  {assemblyFrame?.registerScanner ? null : packingRows}
                </Paper>
              ) : (
                <Alert severity="info">{workspace.supply.packaging_task_id ? 'Загружаем существующее задание упаковки…' : 'Сначала начните работу с поставкой — сервер создаст единственное задание упаковки.'}</Alert>
              )}
    </>
  ) : null

  const renderBoxRow = (
    workspace: FbsWorkspace,
    box: FbsWorkspace['boxes'][number],
    frame?: { open: boolean; onToggle: () => void },
  ) => {
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
                              {frame?.open ? <Box component="span" sx={{ color: 'success.dark', fontWeight: 700 }}> · открыт — сканы идут сюда</Box> : null}
                            </Typography>
                            {frame && box.wb_trbx_id ? <Typography variant="caption" color="text.secondary" sx={{ display: 'block' }}>Грузоместо WB {box.wb_trbx_id}</Typography> : null}
                            {isOzonSupply && assigned.length > 0 ? <Typography variant="caption" color="text.secondary">Ozon №{assigned[0].external_order_id}{remainingOrderQuantity > 0 ? ` · осталось разложить ${remainingOrderQuantity} шт` : ''}</Typography> : null}
                            {isOzonSupply && assigned.length > 0 && box.ozon_label_error ? (
                              <Typography variant="caption" color="error" sx={{ display: 'block', overflowWrap: 'anywhere' }} data-testid={`fbs-box-ozon-label-error-${box.id}`}>
                                Ozon не отдал этикетку: {box.ozon_label_error.message || box.ozon_label_error.code}
                              </Typography>
                            ) : null}
                          </Box>
                          <Stack direction="row" spacing={1} sx={{ alignItems: 'center' }}>
                            {frame ? (
                              <Button size="small" onClick={frame.onToggle} data-testid={`fbs-assembly-box-toggle-${box.id}`}>
                                {frame.open ? 'Закрыть короб' : 'Открыть короб'}
                              </Button>
                            ) : null}
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
                              {isOzonSupply
                                ? box.ozon_assembled ? 'Этикетка Ozon' : 'Собрать и получить этикетку'
                                : 'QR'}
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
  }

  // QR всей переданной поставки — вкладка «Короба» и рамка окна сборки (WMS-574).
  const supplyQrAfterDelivery = workspace ? (
    <>
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
    </>
  ) : null

  const workspaceDialogs = (
    <>
      <ErrorBoundary component="FbsPrintPreviewDialog"><FbsPrintPreviewDialog
        token={token}
        authHeaders={authHeaders}
        batch={printBatch}
        open={printPreviewOpen}
        onClose={() => setPrintPreviewOpen(false)}
        onApplied={(asset) => confirmPrintApplied(asset.id)}
      /></ErrorBoundary>
      <ErrorBoundary component="FbsSupplyHistoryDialog"><FbsSupplyHistoryDialog
        token={token}
        supplyId={supplyId}
        open={historyOpen}
        onClose={() => setHistoryOpen(false)}
      /></ErrorBoundary>
      {workspace ? (
        <ErrorBoundary component="FbsTransferSupplyDialog">
          <FbsTransferSupplyDialog
            open={transferDialogOpen}
            orderIds={selectedPackingOrders.map((order) => order.id)}
            currentSupplyId={workspace.supply.id}
            onClose={() => setTransferDialogOpen(false)}
            onTransferred={(result) => {
              if (shownSupplyId.current !== workspace.supply.id) return
              // WMS-581 R5: после переноса в новую поставку окно показывает ссылку и закрывается по «ОК».
              if (result.state === 'confirmed' && !result.target_created) setTransferDialogOpen(false)
              setPackingSelectedIds((current) => {
                if (result.transferred_order_ids.length === 0) return current
                const next = new Set(current)
                for (const id of result.transferred_order_ids) next.delete(id)
                return next
              })
              setNotice(result.message
                ?? `Перенесено ${result.transferred_order_ids.length} ${ordersWord(result.transferred_order_ids.length)}.${result.pending_order_ids.length ? ` Ожидают подтверждения: ${result.pending_order_ids.length}.` : ''}${result.failed_order_ids.length ? ` Не перенесены: ${result.failed_order_ids.length}.` : ''}`)
              void load(true)
            }}
            deps={makeFbsTransferSupplyDeps(token, authHeaders, workspace.supply.id)}
          />
        </ErrorBoundary>
      ) : null}
      <Dialog open={addOrdersOpen} onClose={addOrdersBusy ? undefined : closeAddOrders} maxWidth="md" fullWidth>
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
          <Button onClick={closeAddOrders} disabled={addOrdersBusy}>
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
      <Dialog open={clearMarkingOrders !== null} onClose={() => { if (!busy) setClearMarkingOrders(null) }} maxWidth="sm" fullWidth>
        <DialogTitle>Очистить ЧЗ у выбранных заказов?</DialogTitle>
        <DialogContent>
          <Typography variant="body2" sx={{ mb: 2 }}>
            Привязки снимутся у нас и в WB. Коды из пула вернутся в свободные — этикетки с ними нужно уничтожить. Внешние и уже введённые в оборот коды в пул не вернутся. Затем можно внести правильные коды. Упаковка и остаток товара не изменятся.
          </Typography>
          <Stack spacing={1} data-testid="fbs-packing-clear-preview">
            {clearMarkingOrders?.map((order) => (
              <Typography key={order.id} variant="body2">
                № {order.wb_order_id} · {order.product.name} · {order.metadata.states.find((state) => state.kind === 'sgtin' && state.value_tail)?.value_tail ?? 'ЧЗ не привязан — без изменений'}
              </Typography>
            ))}
          </Stack>
        </DialogContent>
        <DialogActions>
          <Button disabled={busy} onClick={() => setClearMarkingOrders(null)}>Отмена</Button>
          <Button color="error" variant="contained" disabled={busy} onClick={() => void clearSelectedMarking()} data-testid="fbs-packing-clear-confirm">Очистить ЧЗ</Button>
        </DialogActions>
      </Dialog>
      {markingPrintDialog}
      {/* KIZ-01: единственный оставшийся модальный шаг скана КИЗ — редкое подтверждение
          замены уже внесённого кода. Основной цикл «стикер → ЧЗ» идёт инлайново на вкладке. */}
      <Dialog open={Boolean(kizConfirmTarget)} onClose={dismissKizConfirmation} maxWidth="xs" fullWidth>
        <DialogTitle>Заказ уже с ЧЗ</DialogTitle>
        <DialogContent>
          <Typography variant="body2">
            {isOzonSupply
              ? `На позицию заказа Ozon № ${kizConfirmTarget ? fbsKizOrderNumber(kizConfirmTarget) : '—'} уже внесены коды. Заменить последний код этой позиции?`
              : `На заказ № ${kizConfirmTarget?.wb_order_id} уже есть ЧЗ ${kizConfirmTarget?.current_kiz?.masked}. Внести другой КИЗ?`}
          </Typography>
        </DialogContent>
        <DialogActions>
          <Button onClick={dismissKizConfirmation}>Отмена</Button>
          <Button
            variant="contained"
            data-testid="fbs-kiz-confirm-replace"
            onClick={() => {
              if (kizConfirmValue !== null) void scanKizCode(kizConfirmValue, true)
              else setKizScanActive(kizConfirmTarget)
              setKizConfirmValue(null)
              setKizConfirmTarget(null)
              refocusKizInput(true)
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
          disabled={!reprintOrder?.product.id}
          onClick={() => {
            // После «Очистить ЧЗ» у заказа нет кода — перепечатывать нечего, печатаем новый ЧЗ.
            // Код оператора WB — точная копия этого кода, как «Перепечатать ЧЗ» (WMS-575, R10).
            if (reprintOrder) {
              const request = fbsMenuReprintRequest(
                reprintOrder,
                isOzonSupply ? 'ozon' : 'wb',
                orderPrintDone(reprintOrder),
              )
              openOrderMarkingPrint(reprintOrder, reprintLine, request.reprint, request.reprintMarkingId)
            }
            setReprintMenu(null)
          }}
          data-task-id="FBS-11"
        >
          Перепечатать
        </MenuItem>
        {reprintOrder && hasRemovableKiz(reprintOrder, isOzonSupply ? 'ozon' : 'wb') ? (
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
        <DialogTitle>{isOzonSupply ? 'Передать собранные отправления в Ozon?' : `Передать поставку в ${providerName}?`}</DialogTitle>
        <DialogContent>
          <Typography variant="body2">
            {isOzonSupply
              ? 'WMS создаст и подтвердит перевозку Ozon из уже собранных отправлений. После подтверждения поставку нельзя будет вернуть в работу.'
              : 'После передачи поставку нельзя будет отменить или вернуть в работу.'}
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
                <Typography variant="subtitle2">Можно передать с этими предупреждениями</Typography>
                {deliveryChecks.warnings.map((line) => (
                  <Typography key={line} variant="body2">{line}</Typography>
                ))}
                <Typography variant="caption" color="text.secondary">
                  Проверьте список. Чтобы продолжить, нажмите «{deliveryConfirmLabel}».
                  {isOzonSupply
                    ? 'Этикетки отправлений Ozon получают при сборке коробов; это подтверждение создаёт перевозку Ozon.'
                    : 'Стикеры, Честный знак и QR можно напечатать и после передачи.'}
                </Typography>
              </Alert>
            ) : null}
            {cancelledDeliveryOrders.length > 0 ? (
              <Alert severity="warning">
                <Typography variant="subtitle2">Отменённые заказы</Typography>
                <Typography variant="body2">Выньте эти товары из коробов перед передачей. Они будут исключены из поставки.</Typography>
                {cancelledDeliveryOrders.map((order) => (
                  <Typography key={order.order_id} variant="body2">
                    WB {order.wb_order_id} · {order.article ?? 'Артикул не указан'}
                    {order.product_name ? ` · ${order.product_name}` : ''}
                    {' · '}{order.boxes.length > 0
                      ? order.boxes.map((box) => `Короб ${box.box_number} (${box.box_barcode})`).join(', ')
                      : 'Короб не назначен'}
                  </Typography>
                ))}
              </Alert>
            ) : null}
            {!deliveryPreflightLoading
              && !deliveryPreflightError
              && deliveryChecks.blockers.length === 0
              && deliveryChecks.warnings.length === 0
              && cancelledDeliveryOrders.length === 0
              && deliveryPreflight ? (
                <Alert severity="success">{isOzonSupply
                  ? 'Проверки пройдены. Перевозку Ozon можно создать и подтвердить.'
                  : 'Все проверки пройдены. Поставку можно передать.'}</Alert>
              ) : null}
          </Stack>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setDeliverConfirmOpen(false)}>{cancelledDeliveryOrders.length > 0 ? 'Вернуться и поправить' : 'Не передавать'}</Button>
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
            {deliveryConfirmLabel}
          </Button>
        </DialogActions>
      </Dialog>
      <Dialog open={Boolean(boxAssignTarget)} onClose={busy ? undefined : closeBoxAssignment} maxWidth={isOzonSupply ? 'xl' : 'md'} fullWidth slotProps={isOzonSupply ? { paper: { sx: { minHeight: '75vh', maxHeight: '95vh' } } } : undefined}>
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
                const progress = boxProductProgress.get(row.key)!
                return (
                  <Stack key={row.key} direction="row" spacing={1.25} sx={{ alignItems: 'center' }}>
                    <ProductPhotoThumb src={row.imageUrl} alt={row.name} size={44} />
                    <Box sx={{ flex: 1, minWidth: 0 }}>
                      <Typography variant="body2" sx={{ fontWeight: 700 }}>{row.name}</Typography>
                      <Typography variant="caption" color="text.secondary">{row.identifiers}</Typography>
                    </Box>
                    <Stack spacing={0.5} sx={{ alignItems: 'flex-end', flexShrink: 0 }}>
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
                      <Typography variant="caption" color="text.secondary" sx={{ whiteSpace: 'nowrap' }} data-testid={`fbs-box-product-progress-${row.key}`}>
                        План: {progress.planned} · Осталось: {progress.remaining}
                      </Typography>
                    </Stack>
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
    </>
  )

  // Shared with the individual supply: identical controls and operations.
  const boxesPanel = workspace ? (
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
                        {isOzonSupply
                          ? `Печать всех этикеток Ozon (${workspace.boxes.length})`
                          : `Печать всех QR (${workspace.boxes.length})`}
                      </Button>
                      {isOzonSupply ? (
                        <Button
                          disabled={boxEditingDisabled || busy || ozonAutoBoxesNothingToDo}
                          onClick={() => void autoCreateOzonBoxes()}
                          data-testid="fbs-boxes-ozon-auto-create"
                        >
                          {ozonAutoBoxesProgress ?? 'Создать автоматически'}
                        </Button>
                      ) : null}
                      {!isOzonSupply ? <FormControlLabel
                        control={(
                          <Checkbox
                            checked={boxesWithoutDistribution}
                            onChange={(event) => {
                              const enabled = event.target.checked
                              void run(() => setFbsSupplyBoxesWithoutDistribution(token, authHeaders, workspace.supply.id, enabled), '')
                            }}
                            disabled={boxEditingDisabled || busy || assignedBoxOrderIds.size > 0}
                            data-testid="fbs-boxes-without-distribution"
                            data-task-id="FBS-12"
                          />
                        )}
                        label="Без распределения"
                        data-task-id="FBS-12"
                      /> : null}
                      <TextField label="Коробов" value={boxCount} size="small" type="number" disabled={boxEditingDisabled} onChange={(e) => setBoxCount(e.target.value)} slotProps={{ htmlInput: { min: 1, max: 100 } }} sx={{ width: 104 }} data-task-id="FBS-12" />
                      <Button variant="contained" disabled={boxEditingDisabled || !Number(boxCount) || ozonAutoBoxesProgress !== null} onClick={() => void createBoxes()} data-task-id="FBS-12">Добавить короба</Button>
                    </Stack>
                  </Stack>
                </Box>
                <Stack divider={<Divider flexItem />}>
                  {workspace.boxes.map((box) => renderBoxRow(workspace, box))}
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
              {supplyQrAfterDelivery}
            </Stack>
  ) : null

  // WMS-574: рамка поставки в окне групповой сборки — та же упаковка, те же
  // короба и окна этой карточки, только в раскладке макета (FbsAssemblySupplyFrame).
  if (assemblyFrame) {
    const frameMessages = error || notice || (stageIsCurrent && stageBlockers.length) || partialRejectionAlert || !packagingEditable
      ? (
        <>
          {workspaceMessages}
          {!packagingEditable ? <Alert severity="success" sx={{ mb: 2 }}>Поставка уже передана в WB. Состав менять нельзя, печать этикеток и стикеров доступна.</Alert> : null}
        </>
      )
      : null
    if (stage === 'boxes') {
      return <Stack spacing={1.5} data-testid={`fbs-assembly-boxes-panel-${supplyId}`}>
        {workspace ? <Typography variant="subtitle1" sx={{ fontWeight: 700 }}>
          {fbsAssemblySupplyTitle(workspace)}
        </Typography> : <LinearProgress />}
        {frameMessages}
        {boxesPanel}
        {workspaceDialogs}
      </Stack>
    }
    if (assemblyFrame.registerScanner && !isOzonSupply) {
      return <>
        {assemblyFrame.packingHost ? createPortal(packingRows, assemblyFrame.packingHost) : null}
        {frameMessages}
        {kizScanError ? <Alert severity="error">{kizScanError.text}</Alert> : null}
        {workspaceDialogs}
      </>
    }
    return (
      <>
      {assemblyFrame.packingHost ? createPortal(packingRows, assemblyFrame.packingHost) : null}
      <FbsAssemblySupplyFrame
        supplyId={supplyId ?? ''}
        title={workspace ? `${fbsAssemblySupplyTitle(workspace)} · ${workspaceRouteLabel}` : 'Загружаем данные поставки…'}
        packed={workspace?.progress.packed ?? 0}
        total={workspace?.progress.total ?? 0}
        honestSignSkipped={Boolean(workspace?.supply.honest_sign_skipped)}
        transferred={deliveryConfirmed}
        active={assemblyFrame.active}
        expanded={assemblyFrame.active || assemblyFrame.expanded}
        busy={busy}
        starting={assemblyStarting}
        onToggleExpanded={assemblyFrame.onToggleExpanded}
        onStart={() => void startAssemblyWork()}
        onFinish={assemblyFrame.onDeactivate}
        transfer={workspace && !deliveryConfirmed
          ? { label: `Передать в ${providerName}`, disabled: busy, onClick: () => void openDeliveryConfirmation() }
          : null}
        messages={frameMessages}
        packing={workspace
          ? packagingTask || deliveryConfirmed ? packingPanel : <Box sx={{ p: 2 }}>{packingPanel}</Box>
          : null}
        afterBoxes={deliveryConfirmed && (needsSupplyQr || hasCargoPlaceBoxes) ? supplyQrAfterDelivery : null}
        boxes={workspace
          ? {
            routeLabel: boxRouteLabel,
            rows: workspace.boxes.map((box) => renderBoxRow(workspace, box, {
              open: assemblyOpenBoxId === box.id,
              onToggle: () => toggleAssemblyBox(box.id),
            })),
            printAllLabel: `Печать всех QR (${workspace.boxes.length})`,
            printAllDisabled: boxOperationsDisabled || busy || workspace.boxes.length === 0,
            onPrintAll: () => void openAllBoxQrPreview(),
            createDisabled: boxEditingDisabled || assemblyBoxCreating,
            creating: assemblyBoxCreating,
            onCreate: () => void createAssemblyBox(),
          }
          : null}
      >
        {workspaceDialogs}
      </FbsAssemblySupplyFrame>
      </>
    )
  }

  return (
    <Dialog
      open={open}
      onClose={busy ? undefined : (_event, reason) => {
        if (reason === 'escapeKeyDown' && (kizScanActive || kizScanBusy)) {
          if (!kizScanBusy) dropKizScanActive()
          return
        }
        requestClose()
      }}
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
                  <Metric label={isOzonSupply ? 'Метод доставки Ozon' : 'Маршрут'} value={workspaceRouteLabel} />
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
          <IconButton onClick={requestClose} disabled={busy} aria-label="Закрыть">
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
          if (STAGES.findIndex((item) => item.key === value) <= accessibleStageIndex) selectStage(value)
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
          {workspaceMessages}

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
                    <Button variant="outlined" startIcon={<PrintOutlinedIcon />} onClick={() => void printPickingList()} data-testid="fbs-pick-list-print">
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
                <Button variant="outlined" startIcon={<PrintOutlinedIcon />} onClick={() => void printPickingList()} data-testid="fbs-pick-list-print">
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
                    onPaused={requestClose}
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
              {packingPanel}
              {nextStageControl('packing')}
            </Stack>
          ) : null}

          {workspace && stage === 'boxes' ? boxesPanel : null}
        </Box>
      </DialogContent>
      {workspaceDialogs}
    </Dialog>
  )
}
