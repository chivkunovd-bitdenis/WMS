import {
  useCallback,
  useEffect,
  useRef,
  useState,
  type MouseEvent,
  type ReactNode,
} from 'react'
import { Link as RouterLink, useLocation, useNavigate, useParams } from 'react-router-dom'
import {
  ArticleOutlined,
  MoreVertOutlined,
  PrintOutlined,
  UndoOutlined,
} from '@mui/icons-material'
import {
  Alert,
  Avatar,
  Badge,
  Box,
  Button,
  Chip,
  Checkbox,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  FormControl,
  IconButton,
  InputLabel,
  Link,
  Menu,
  MenuItem,
  Paper,
  Select,
  Stack,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  Tab,
  Tabs,
  TextField,
  Tooltip,
  Typography,
} from '@mui/material'
import { useWbProductCatalog } from '../../hooks/useWbProductCatalog'
import { apiUrl } from '../../api'
import { fetchPendingMarking, pendingMarkingLineCount } from '../../utils/pendingMarkingApi'
import { PageHeader } from '../../ui/PageHeader'
import { productDisplayMetaFromCatalog, resolveProductPrimaryBarcode } from '../../types/wbProductCatalog'
import { readApiErrorMessage } from '../../utils/readApiErrorMessage'
import { displayMetaToProductLabel } from '../../utils/productBarcodePrint'
import { useMarkingCodePrint } from '../../utils/useMarkingCodePrint'
import { formatHumanDocumentNumber } from './documentDisplay'

export type PackagingTaskLine = {
  id: string
  product_id: string
  seller_id?: string | null
  seller_name?: string | null
  sku_code: string
  product_name: string
  storage_location_id: string
  storage_location_code: string
  packaging_instructions: string | null
  requires_honest_sign: boolean
  qty_total: number
  qty_suggested_packed: number
  qty_confirmed_packed: number
  qty_need_pack: number
  qty_packed_in_task: number
  qty_done: number
  qty_marking_printed: number
  qty_marking_external: number
  qty_product_label_printed: number
  marking_available_count: number
  is_complete: boolean
}

export type PackagingTaskEvent = {
  id: string
  event_sequence: number
  action: string
  line_id: string | null
  product_id: string | null
  product_name: string | null
  storage_location_id: string | null
  storage_location_code: string | null
  quantity: number
  note: string | null
  created_by_user_id: string | null
  created_by_user_email: string | null
  created_at: string
  reversed_at: string | null
}

export type PackagingTask = {
  id: string
  document_number: string | null
  display_number?: string | null
  public_number?: string | null
  human_number?: string | null
  warehouse_id: string
  warehouse_name?: string | null
  warehouse_code?: string | null
  seller_id?: string | null
  seller_name?: string | null
  status: string
  marketplace_unload_request_id: string | null
  inbound_intake_request_id: string | null
  is_complete: boolean
  pick_resync_warning?: boolean
  created_at?: string | null
  updated_at?: string | null
  completed_at?: string | null
  completed_by_user_id?: string | null
  lines: PackagingTaskLine[]
  events?: PackagingTaskEvent[]
}

type PackProgress = {
  packaging_task: PackagingTask
  fulfilled_order: {
    id: string
    wb_order_id: number
    pack_status: string
    marking_status: string | null
    sticker_status: string
  } | null
}

type PrintedMarkingCode = {
  id: string
  cis_code: string
  cis_masked: string
  status: string
}

type TaskPanelProps = {
  token: string
  task: PackagingTask
  unloadLabel?: string | null
  /** Hide status chip + «Упаковка» + document numbers when embedded in MP unload modal. */
  hideDocumentHeader?: boolean
  /** Compact operator cards for narrow embedded workspaces such as FBS. */
  compactLayout?: boolean
  /** Keep the standard table but collapse duplicate quantity columns for operator workspaces. */
  simplifiedQuantities?: boolean
  /** Expose the standard product print action even when Honest Sign is not required. */
  alwaysShowPrintAction?: boolean
  /** Add workflow-specific actions to the existing product row without creating a second table. */
  renderLineActions?: (line: PackagingTaskLine) => ReactNode
  /** Separate printing stage: reuses the standard ЧЗ/ШК dialog without packing actions. */
  printOnly?: boolean
  /** Embedded packing stage can keep physical packing free of print controls. */
  hidePrintActions?: boolean
  /** Единое поле скана также принимает штрихкод готового короба (WHB-/INB-);
      состоянием коробов владеет родитель, поэтому скан короба делегируется наверх. */
  onBoxBarcodeScan?: (barcode: string) => void
  onClose?: () => void
  onUpdated: (task: PackagingTask) => void
}

function statusLabel(status: string): string {
  if (status === 'draft') return 'Черновик'
  if (status === 'in_progress') return 'В работе'
  if (status === 'done') return 'Выполнено'
  if (status === 'cancelled') return 'Отменено'
  return status
}

function locationLabel(code?: string | null): string {
  if (!code) return '—'
  return code === '__SORTING__' ? 'Сортировка' : code
}

function taskTotals(task: PackagingTask): { total: number; done: number; remaining: number } {
  const total = task.lines.reduce((sum, line) => sum + line.qty_total, 0)
  const done = task.lines.reduce((sum, line) => sum + line.qty_done, 0)
  return { total, done, remaining: Math.max(0, total - done) }
}

function taskSellerLabel(task: PackagingTask): string {
  return task.seller_name ?? task.lines[0]?.seller_name ?? 'Селлер не указан'
}

function taskPlaceLabel(task: PackagingTask): string {
  const warehouse = task.warehouse_name ?? task.warehouse_code ?? 'Склад'
  const cells = Array.from(new Set(task.lines.map((line) => locationLabel(line.storage_location_code))))
  return `${warehouse} / ${cells.slice(0, 2).join(', ')}${cells.length > 2 ? ` +${cells.length - 2}` : ''}`
}

function taskProductSummary(task: PackagingTask): string {
  const names = task.lines.map((line) => line.product_name || line.sku_code).slice(0, 2)
  return `${names.join(', ')}${task.lines.length > 2 ? ` +${task.lines.length - 2}` : ''}`
}

function parseStrictPositiveInteger(raw: string): number | null {
  const value = raw.trim()
  if (!/^[1-9]\d*$/.test(value)) {
    return null
  }
  return Number(value)
}

function sellerCountLabel(count: number): string {
  const mod10 = count % 10
  const mod100 = count % 100
  if (mod10 === 1 && mod100 !== 11) {
    return `${count} селлер`
  }
  if (mod10 >= 2 && mod10 <= 4 && (mod100 < 12 || mod100 > 14)) {
    return `${count} селлера`
  }
  return `${count} селлеров`
}

function comparePackagingEventsAsc(a: PackagingTaskEvent, b: PackagingTaskEvent): number {
  return a.event_sequence - b.event_sequence
}

/** События без количества. manual_pack и undo_last собираются ниже — им нужно число. */
const PACKAGING_EVENT_LABELS: Record<string, string> = {
  scan_pack: '+1 скан',
  product_label_print: 'Печать этикетки товара',
  prepacked_external: 'Пришло готовым (без печати)',
  cancel: 'Задание отменено',
  complete: 'Задание выполнено',
}

function packagingEventLabel(action: string, quantity: number): string {
  if (action === 'manual_pack') {
    return `+${quantity} вручную`
  }
  if (action === 'undo_last') {
    return `Отмена ${quantity} шт`
  }
  return PACKAGING_EVENT_LABELS[action] ?? action
}

/** Mirrors backend assert_packaging_line_marking_done: marked = printed + external. */
function isLineMarkingIncomplete(ln: PackagingTaskLine): boolean {
  if (!ln.requires_honest_sign) {
    return false
  }
  const done = ln.qty_done
  const marked = ln.qty_marking_printed + (ln.qty_marking_external ?? 0)
  return done > 0 && marked < done
}

/** Progress toward qty_need_pack — for ЧЗ column display and row highlight. */
function isLineMarkingProgressIncomplete(ln: PackagingTaskLine): boolean {
  if (!ln.requires_honest_sign) {
    return false
  }
  const marked = ln.qty_marking_printed + (ln.qty_marking_external ?? 0)
  return marked < ln.qty_need_pack
}

const MARKING_NOT_DONE_MESSAGE =
  'Не хватает напечатанных КМ по заданию на упаковку.'

const PACKAGING_API_MESSAGES_RU: Record<string, string> = {
  unknown_barcode: 'ШК не найден в этом задании. Проверьте товар и выбранное задание.',
  line_already_packed: 'По этому товару всё уже упаковано.',
  undo_not_available: 'Нет действия, которое можно отменить.',
  undo_not_supported: 'Это действие нельзя отменить.',
}

async function readPackagingApiErrorMessage(res: Response): Promise<string> {
  const message = await readApiErrorMessage(res)
  return PACKAGING_API_MESSAGES_RU[message] ?? message
}

export function FfPackagingTaskPanel({
  token,
  task,
  unloadLabel,
  hideDocumentHeader = false,
  alwaysShowPrintAction = false,
  renderLineActions,
  printOnly = false,
  hidePrintActions = false,
  onBoxBarcodeScan,
  onClose,
  onUpdated,
}: TaskPanelProps) {
  const { catalogById } = useWbProductCatalog(token)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [defectDialogOpen, setDefectDialogOpen] = useState(false)
  const [defectLineId, setDefectLineId] = useState<string | null>(null)
  const [defectCodes, setDefectCodes] = useState<PrintedMarkingCode[]>([])
  const [defectSelectedCodeId, setDefectSelectedCodeId] = useState('')
  const [defectReason, setDefectReason] = useState('')
  const [defectDialogBusy, setDefectDialogBusy] = useState(false)
  const [defectDialogError, setDefectDialogError] = useState<string | null>(null)
  const [lineMenuAnchor, setLineMenuAnchor] = useState<null | HTMLElement>(null)
  const [lineMenuLine, setLineMenuLine] = useState<PackagingTaskLine | null>(null)
  const [scannerValue, setScannerValue] = useState('')
  const [scannerFeedback, setScannerFeedback] = useState<string | null>(null)
  const [focusedLineId, setFocusedLineId] = useState<string | null>(null)
  const [manualQtyByLine, setManualQtyByLine] = useState<Record<string, string>>({})
  const [manualErrorByLine, setManualErrorByLine] = useState<Record<string, string>>({})
  const [undoConfirmEvent, setUndoConfirmEvent] = useState<PackagingTaskEvent | null>(null)
  const scannerRef = useRef<HTMLInputElement | null>(null)
  const { openPrint, dialog: markingPrintDialog } = useMarkingCodePrint()

  const authHeaders = {
    Authorization: `Bearer ${token}`,
    'Content-Type': 'application/json',
  }

  const productLabelForLine = (ln: PackagingTaskLine) =>
    displayMetaToProductLabel(productDisplayMetaFromCatalog(ln.product_id, ln, catalogById))

  const lineBarcodeForScan = (ln: PackagingTaskLine) => {
    const displayMeta = productDisplayMetaFromCatalog(ln.product_id, ln, catalogById)
    return resolveProductPrimaryBarcode(displayMeta) || ln.sku_code
  }

  const lineRemaining = (ln: PackagingTaskLine) =>
    Math.max(0, ln.qty_need_pack - ln.qty_packed_in_task)

  const panelTotals = taskTotals(task)
  const taskEditable = task.status !== 'done' && task.status !== 'cancelled'
  const isMpUnloadTask = Boolean(task.marketplace_unload_request_id)
  const pickResyncWarningText = isMpUnloadTask
    ? 'Состав коробов изменился. Количества в задании пересчитаны; уже упакованное в задании сохранено — проверьте строки.'
    : 'Подбор по ячейкам изменился. Количества в задании пересчитаны; уже упакованное в задании сохранено — проверьте строки.'
  const orderedEvents = (task.events ?? []).slice().sort(comparePackagingEventsAsc)
  const reversibleEvents = orderedEvents.filter(
    (event) =>
      (event.action === 'scan_pack' || event.action === 'manual_pack') &&
      event.reversed_at === null,
  )
  const lastReversibleEvent = reversibleEvents[reversibleEvents.length - 1] ?? null
  const canUndo = taskEditable && reversibleEvents.length > 0 && !printOnly && !isMpUnloadTask

  useEffect(() => {
    if (taskEditable && !printOnly) {
      scannerRef.current?.focus()
    }
  }, [task.id, taskEditable, printOnly])

  const refreshTask = async () => {
    const res = await fetch(apiUrl(`/operations/packaging-tasks/${task.id}`), { headers: authHeaders })
    if (res.ok) {
      onUpdated((await res.json()) as PackagingTask)
    }
  }

  const markProductLabelPrinted = async (ln: PackagingTaskLine) => {
    const quantity = Math.max(1, ln.qty_need_pack || ln.qty_done || 1)
    const res = await fetch(
      apiUrl(`/operations/packaging-tasks/${task.id}/lines/${ln.id}/product-label-printed`),
      {
        method: 'POST',
        headers: { ...authHeaders, 'Content-Type': 'application/json' },
        body: JSON.stringify({ quantity }),
      },
    )
    if (res.ok) {
      onUpdated((await res.json()) as PackagingTask)
      return
    }
    setError(await readApiErrorMessage(res))
  }

  const openLinePrint = (ln: PackagingTaskLine, opts?: { reprint?: boolean }) => {
    openPrint(
      {
        token,
        lineId: ln.id,
        productId: ln.product_id,
        documentNumber: formatHumanDocumentNumber(task),
        qtyNeedPack: ln.qty_need_pack,
        markingAvailable: ln.marking_available_count,
        qtyMarkingPrinted: ln.qty_marking_printed,
        requiresHonestSign: ln.requires_honest_sign,
        skuCode: ln.sku_code,
        productName: ln.product_name,
        productLabel: productLabelForLine(ln),
        packagingInstructions: ln.packaging_instructions,
        onPrinted: () => {
          void markProductLabelPrinted(ln).finally(() => {
            void refreshTask()
          })
        },
      },
      { reprint: opts?.reprint },
    )
  }

  const confirmPacked = async (lineId: string) => {
    setBusy(true)
    setError(null)
    try {
      const res = await fetch(
        apiUrl(`/operations/packaging-tasks/${task.id}/lines/${lineId}/confirm-packed`),
        { method: 'POST', headers: authHeaders, body: JSON.stringify({}) },
      )
      if (!res.ok) {
        setError(await readPackagingApiErrorMessage(res))
        return
      }
      onUpdated((await res.json()) as PackagingTask)
    } finally {
      setBusy(false)
    }
  }

  const markPrepackedExternal = async (lineId: string, qty: number) => {
    setBusy(true)
    setError(null)
    try {
      const res = await fetch(
        apiUrl(`/operations/packaging-tasks/${task.id}/lines/${lineId}/mark-prepacked`),
        {
          method: 'POST',
          headers: authHeaders,
          body: JSON.stringify({ quantity: qty }),
        },
      )
      if (!res.ok) {
        setError(await readPackagingApiErrorMessage(res))
        return
      }
      onUpdated((await res.json()) as PackagingTask)
    } finally {
      setBusy(false)
    }
  }

  const packQty = async (lineId: string, qty: number) => {
    setBusy(true)
    setError(null)
    setScannerFeedback(null)
    try {
      const res = await fetch(
        apiUrl(`/operations/packaging-tasks/${task.id}/lines/${lineId}/pack`),
        {
          method: 'POST',
          headers: authHeaders,
          body: JSON.stringify({ quantity: qty }),
        },
      )
      if (!res.ok) {
        setError(await readPackagingApiErrorMessage(res))
        return
      }
      const progress = (await res.json()) as PackProgress
      onUpdated(progress.packaging_task)
      const line = task.lines.find((ln) => ln.id === lineId)
      setScannerFeedback(`Добавлено вручную: ${qty} шт${line ? ` · ${line.product_name}` : ''}`)
    } finally {
      setBusy(false)
      window.setTimeout(() => scannerRef.current?.focus(), 0)
    }
  }

  const submitScanner = async () => {
    const barcode = scannerValue.trim()
    if (!barcode) {
      setError('Отсканируйте ШК товара.')
      scannerRef.current?.focus()
      return
    }
    if (isMpUnloadTask) {
      // Единое поле различает короб (WHB-/INB-) и товар по формату строки.
      if (barcode.startsWith('WHB-') || barcode.startsWith('INB-')) {
        setScannerValue('')
        setError(null)
        onBoxBarcodeScan?.(barcode)
        window.setTimeout(() => scannerRef.current?.focus(), 0)
        return
      }
      const matchingLine = task.lines.find((ln) => {
        const lineBarcode = lineBarcodeForScan(ln)
        return barcode === lineBarcode || barcode === ln.sku_code
      })
      if (!matchingLine) {
        setError('ШК не найден в этом задании. Проверьте товар и выбранную отгрузку.')
        scannerRef.current?.focus()
        return
      }
      const remaining = lineRemaining(matchingLine)
      if (remaining < 1) {
        setFocusedLineId(matchingLine.id)
        setScannerValue('')
        setError(null)
        setScannerFeedback(`По этому товару уже упаковано всё: ${matchingLine.product_name}`)
        window.setTimeout(() => scannerRef.current?.focus(), 0)
        return
      }
      setFocusedLineId(matchingLine.id)
      setScannerValue('')
      setError(null)
      await packQty(matchingLine.id, 1)
      return
    }
    const packedBefore = new Map(task.lines.map((ln) => [ln.id, ln.qty_packed_in_task]))
    setBusy(true)
    setError(null)
    setScannerFeedback(null)
    try {
      const res = await fetch(apiUrl(`/operations/packaging-tasks/${task.id}/scan`), {
        method: 'POST',
        headers: authHeaders,
        body: JSON.stringify({ barcode }),
      })
      if (!res.ok) {
        setError(await readPackagingApiErrorMessage(res))
        return
      }
      const progress = (await res.json()) as PackProgress
      onUpdated(progress.packaging_task)
      setScannerValue('')
      const changedLine = progress.packaging_task.lines.find(
        (ln) => ln.qty_packed_in_task > (packedBefore.get(ln.id) ?? 0),
      )
      setScannerFeedback(`+1 упаковано${changedLine ? `: ${changedLine.product_name}` : ''}`)
    } finally {
      setBusy(false)
      window.setTimeout(() => scannerRef.current?.focus(), 0)
    }
  }

  const submitManualQty = async (ln: PackagingTaskLine) => {
    const raw = (manualQtyByLine[ln.id] ?? '').trim()
    const remaining = lineRemaining(ln)
    let message: string | null = null
    if (!raw || raw === '0') {
      message = 'Введите количество больше 0'
    } else if (parseStrictPositiveInteger(raw) === null) {
      message = 'Введите целое число'
    } else if (Number(raw) > remaining) {
      message = 'По этому товару уже упаковано всё количество'
    }
    if (message) {
      setManualErrorByLine((prev) => ({ ...prev, [ln.id]: message }))
      return
    }
    setManualErrorByLine((prev) => ({ ...prev, [ln.id]: '' }))
    await packQty(ln.id, Number(raw))
    setManualQtyByLine((prev) => ({ ...prev, [ln.id]: '' }))
  }

  const performUndoLast = async (confirmedEvent: PackagingTaskEvent | null = lastReversibleEvent) => {
    setUndoConfirmEvent(null)
    setBusy(true)
    setError(null)
    setScannerFeedback(null)
    try {
      const res = await fetch(apiUrl(`/operations/packaging-tasks/${task.id}/undo-last`), {
        method: 'POST',
        headers: authHeaders,
      })
      if (!res.ok) {
        setError(await readPackagingApiErrorMessage(res))
        return
      }
      onUpdated((await res.json()) as PackagingTask)
      const productLabel = confirmedEvent?.product_name ? ` · ${confirmedEvent.product_name}` : ''
      setScannerFeedback(
        confirmedEvent
          ? `Отменено: ${confirmedEvent.quantity} шт${productLabel}`
          : 'Последнее действие отменено',
      )
    } finally {
      setBusy(false)
      window.setTimeout(() => scannerRef.current?.focus(), 0)
    }
  }

  const requestUndoLast = () => {
    if (!lastReversibleEvent) {
      return
    }
    if (lastReversibleEvent.action === 'manual_pack' && lastReversibleEvent.quantity > 1) {
      setUndoConfirmEvent(lastReversibleEvent)
      return
    }
    void performUndoLast(lastReversibleEvent)
  }

  const resetDefectDialog = () => {
    setDefectDialogOpen(false)
    setDefectLineId(null)
    setDefectCodes([])
    setDefectSelectedCodeId('')
    setDefectReason('')
    setDefectDialogError(null)
  }

  const closeDefectDialog = () => {
    if (defectDialogBusy) {
      return
    }
    resetDefectDialog()
  }

  const openDefectDialog = async (lineId: string) => {
    setBusy(true)
    setError(null)
    try {
      const codesRes = await fetch(
        apiUrl(`/operations/marking-codes/packaging-task-lines/${lineId}/printed-codes`),
        { headers: authHeaders },
      )
      if (!codesRes.ok) {
        setError(await readPackagingApiErrorMessage(codesRes))
        return
      }
      const codes = ((await codesRes.json()) as { codes: PrintedMarkingCode[] }).codes
      if (codes.length < 1) {
        setError('Нет напечатанных КМ для этой строки')
        return
      }
      setDefectLineId(lineId)
      setDefectCodes(codes)
      setDefectSelectedCodeId(codes[0].id)
      setDefectReason('')
      setDefectDialogError(null)
      setDefectDialogOpen(true)
    } finally {
      setBusy(false)
    }
  }

  const submitDefectMarking = async () => {
    if (!defectLineId || !defectSelectedCodeId) {
      return
    }
    setDefectDialogBusy(true)
    setDefectDialogError(null)
    try {
      const reasonTrimmed = defectReason.trim()
      const defectRes = await fetch(
        apiUrl(`/operations/marking-codes/codes/${defectSelectedCodeId}/defect`),
        {
          method: 'POST',
          headers: authHeaders,
          body: JSON.stringify({
            packaging_task_line_id: defectLineId,
            reason: reasonTrimmed || null,
          }),
        },
      )
      if (!defectRes.ok) {
        setDefectDialogError(await readPackagingApiErrorMessage(defectRes))
        return
      }
      await refreshTask()
      resetDefectDialog()
    } finally {
      setDefectDialogBusy(false)
    }
  }

  const cancelTask = async () => {
    if (!window.confirm('Отменить задание на упаковку?')) {
      return
    }
    setBusy(true)
    setError(null)
    try {
      const res = await fetch(apiUrl(`/operations/packaging-tasks/${task.id}/cancel`), {
        method: 'POST',
        headers: authHeaders,
      })
      if (!res.ok) {
        setError(await readPackagingApiErrorMessage(res))
        return
      }
      onUpdated((await res.json()) as PackagingTask)
      onClose?.()
    } finally {
      setBusy(false)
    }
  }

  const incompleteMarkingLines = task.lines.filter(isLineMarkingIncomplete)
  const hasIncompleteMarking = incompleteMarkingLines.length > 0
  const hasIncompletePacking = task.lines.some(
    (line) => line.qty_packed_in_task < line.qty_need_pack,
  )

  const completeTask = async () => {
    if (panelTotals.remaining > 0) {
      setError(`Сначала упакуйте все строки. Осталось ${panelTotals.remaining} шт.`)
      scannerRef.current?.focus()
      return
    }
    if (hasIncompleteMarking) {
      setError(MARKING_NOT_DONE_MESSAGE)
      return
    }
    setBusy(true)
    setError(null)
    try {
      const res = await fetch(apiUrl(`/operations/packaging-tasks/${task.id}/complete`), {
        method: 'POST',
        headers: authHeaders,
        body: JSON.stringify({ acknowledge_all_packed: false }),
      })
      if (!res.ok) {
        setError(await readPackagingApiErrorMessage(res))
        return
      }
      onUpdated((await res.json()) as PackagingTask)
    } finally {
      setBusy(false)
    }
  }

  const manualTask =
    !task.marketplace_unload_request_id &&
    task.status !== 'done' &&
    task.status !== 'cancelled'

  const lineHasOverflowActions = (ln: PackagingTaskLine) =>
    ln.requires_honest_sign && ln.qty_marking_printed > 0

  const openLineMenu = (event: MouseEvent<HTMLElement>, ln: PackagingTaskLine) => {
    event.stopPropagation()
    setLineMenuAnchor(event.currentTarget)
    setLineMenuLine(ln)
  }

  const closeLineMenu = () => {
    setLineMenuAnchor(null)
    setLineMenuLine(null)
  }

  const displayDocumentNumber = formatHumanDocumentNumber(task)

  return (
    <Stack spacing={2} data-testid="ff-packaging-task-panel" sx={{ maxWidth: '100%', overflowX: 'hidden' }}>
      {hideDocumentHeader ? null : (
        <Stack direction="row" spacing={2} sx={{ alignItems: 'flex-start', flexWrap: 'wrap' }}>
          <Stack spacing={0.25} sx={{ minWidth: 0 }}>
            <Typography variant="body2" sx={{ fontWeight: 700 }} data-testid="ff-packaging-task-status">
              {statusLabel(task.status)}
            </Typography>
            {displayDocumentNumber ? (
              <Typography
                variant="caption"
                color="text.secondary"
                data-testid="ff-packaging-document-number"
              >
                {displayDocumentNumber}
              </Typography>
            ) : null}
          </Stack>
          {task.marketplace_unload_request_id && unloadLabel ? (
            <Link
              component={RouterLink}
              to={`/ff/mp-shipments?open_mp=${task.marketplace_unload_request_id}`}
              variant="body2"
              data-testid="ff-packaging-linked-unload"
            >
              Отгрузка: {unloadLabel}
            </Link>
          ) : unloadLabel ? (
            <Typography variant="body2" color="text.secondary" data-testid="ff-packaging-linked-unload">
              Отгрузка: {unloadLabel}
            </Typography>
          ) : null}
        </Stack>
      )}
      {error ? (
        <Alert severity="error" data-testid="ff-packaging-error">
          {error}
        </Alert>
      ) : null}
      {task.pick_resync_warning ? (
        <Alert severity="warning" data-testid="ff-packaging-pick-resync-warning">
          {pickResyncWarningText}
        </Alert>
      ) : null}
      <Paper variant="outlined" sx={{ p: 2 }} data-testid="ff-packaging-work-context">
        <Box
          sx={{
            display: 'grid',
            gridTemplateColumns: { xs: '1fr', md: '1.2fr 1.4fr 0.8fr' },
            gap: 1.5,
            alignItems: 'center',
          }}
        >
          <Box sx={{ minWidth: 0 }}>
            <Typography variant="caption" color="text.secondary">Селлер</Typography>
            <Typography variant="body2" sx={{ fontWeight: 700, overflowWrap: 'anywhere' }} data-testid="ff-packaging-task-seller">
              {taskSellerLabel(task)}
            </Typography>
          </Box>
          <Box sx={{ minWidth: 0 }}>
            <Typography variant="caption" color="text.secondary">Склад / ячейка</Typography>
            <Typography variant="body2" sx={{ fontWeight: 700, overflowWrap: 'anywhere' }} data-testid="ff-packaging-task-place">
              {taskPlaceLabel(task)}
            </Typography>
          </Box>
          <Box sx={{ minWidth: 0 }}>
            <Typography variant="caption" color="text.secondary">Прогресс</Typography>
            <Typography variant="body2" sx={{ fontWeight: 700 }} data-testid="ff-packaging-task-progress">
              Готово {panelTotals.done} / Осталось {panelTotals.remaining}
            </Typography>
          </Box>
        </Box>
      </Paper>
      {taskEditable && !printOnly ? (
        <Paper variant="outlined" sx={{ p: 2 }} data-testid="ff-packaging-scanner-panel">
          <Stack direction={{ xs: 'column', md: 'row' }} spacing={1.5} sx={{ alignItems: { xs: 'stretch', md: 'flex-start' } }}>
            <TextField
              inputRef={scannerRef}
              label={isMpUnloadTask ? 'Сканируйте ШК товара для поиска строки' : 'Сканируйте ШК товара'}
              value={scannerValue}
              onChange={(e) => setScannerValue(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter') {
                  e.preventDefault()
                  void submitScanner()
                }
              }}
              disabled={busy}
              size="small"
              fullWidth
              data-testid="ff-packaging-scanner-field"
              slotProps={{
                htmlInput: {
                  'data-testid': 'ff-packaging-scanner-input',
                },
              }}
            />
            <Button
              variant="contained"
              disabled={busy}
              onClick={() => void submitScanner()}
              data-testid="ff-packaging-scan-submit"
              sx={{ minWidth: isMpUnloadTask ? 140 : 120 }}
            >
              {isMpUnloadTask ? 'Найти строку' : '+1'}
            </Button>
            {isMpUnloadTask ? null : (
              <Button
                variant="outlined"
                color="inherit"
                startIcon={<UndoOutlined fontSize="small" />}
                disabled={busy || !canUndo}
                onClick={requestUndoLast}
                data-testid="ff-packaging-undo-last"
                sx={{ minWidth: 190 }}
              >
                Отменить последнее
              </Button>
            )}
          </Stack>
          <Typography
            variant="caption"
            color="text.secondary"
            sx={{ display: 'block', mt: 1 }}
            data-testid="ff-packaging-scan-status"
          >
            {isMpUnloadTask
              ? 'Сканер активен — пикните ШК товара или короба (WHB-…).'
              : 'Сканер активен — пикните ШК товара.'}
          </Typography>
          {scannerFeedback ? (
            <Alert severity="success" sx={{ mt: 1.5 }} data-testid="ff-packaging-scan-feedback">
              {scannerFeedback}
            </Alert>
          ) : null}
        </Paper>
      ) : null}
      {isMpUnloadTask ? (
        <TableContainer component={Paper} variant="outlined" data-testid="ff-packaging-lines-table">
          <Table size="small" sx={{ tableLayout: 'fixed', width: '100%' }}>
            <TableHead>
              <TableRow>
                <TableCell sx={{ width: '30%' }}>Товар / SKU</TableCell>
                <TableCell sx={{ width: '18%' }}>ШК</TableCell>
                <TableCell align="center" sx={{ width: 64 }}>ТЗ</TableCell>
                <TableCell sx={{ width: '16%' }}>ЧЗ</TableCell>
                <TableCell sx={{ width: '16%' }}>ШК печати</TableCell>
                <TableCell align="right" sx={{ width: 120 }}>Упаковано</TableCell>
                <TableCell align="right" sx={{ width: 96 }}>Печать</TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {task.lines.map((ln) => {
                const displayMeta = productDisplayMetaFromCatalog(ln.product_id, ln, catalogById)
                const barcode = lineBarcodeForScan(ln)
                const remaining = lineRemaining(ln)
                const markingProgressIncomplete = isLineMarkingProgressIncomplete(ln)
                const hasInstructions = Boolean(ln.packaging_instructions?.trim())
                const barcodeReady = Boolean(barcode?.trim())
                const productLabelNeed = Math.max(ln.qty_need_pack, ln.qty_done)
                const productLabelPrinted = Math.min(
                  ln.qty_product_label_printed ?? 0,
                  productLabelNeed,
                )
                const barcodeStatusLabel = barcodeReady
                  ? `напечатано ${productLabelPrinted}/${productLabelNeed}`
                  : 'нет ШК'
                return (
                  <TableRow
                    key={ln.id}
                    data-testid={markingProgressIncomplete ? 'ff-packaging-line-marking-incomplete' : 'ff-packaging-line'}
                    selected={focusedLineId === ln.id}
                    sx={markingProgressIncomplete ? { bgcolor: 'warning.light' } : undefined}
                  >
                    <TableCell sx={{ overflow: 'hidden', textOverflow: 'ellipsis' }}>
                      <Typography variant="body2" sx={{ fontWeight: 700 }} noWrap data-testid="ff-packaging-compact-product-name">
                        {displayMeta.product_name}
                      </Typography>
                      <Typography variant="caption" color="text.secondary" noWrap>
                        SKU: {displayMeta.sku_code}
                      </Typography>
                    </TableCell>
                    <TableCell sx={{ overflow: 'hidden', textOverflow: 'ellipsis' }}>
                      <Typography variant="body2" noWrap data-testid={`ff-packaging-line-barcode-${ln.id}`}>
                        {barcode || '—'}
                      </Typography>
                    </TableCell>
                    <TableCell align="center">
                      <Tooltip title={hasInstructions ? ln.packaging_instructions : 'ТЗ не задано'}>
                        <span>
                          <IconButton
                            size="small"
                            disabled={!hasInstructions}
                            data-testid={`ff-packaging-line-tz-${ln.id}`}
                            aria-label={hasInstructions ? 'Показать ТЗ упаковки' : 'ТЗ упаковки не задано'}
                          >
                            <ArticleOutlined fontSize="small" color={hasInstructions ? 'primary' : 'disabled'} />
                          </IconButton>
                        </span>
                      </Tooltip>
                    </TableCell>
                    <TableCell>
                      {ln.requires_honest_sign ? (
                        <Chip
                          size="small"
                          color={markingProgressIncomplete ? 'warning' : 'success'}
                          variant={markingProgressIncomplete ? 'outlined' : 'filled'}
                          label={`${ln.qty_marking_printed + (ln.qty_marking_external ?? 0)}/${ln.qty_need_pack}`}
                          data-testid={`ff-packaging-marking-progress-${ln.id}`}
                        />
                      ) : (
                        <Chip size="small" variant="outlined" label="не требуется" />
                      )}
                    </TableCell>
                    <TableCell>
                      <Chip
                        size="small"
                        // GLOBAL-02: оранжевый значит «мешает работать». Печать товарного ШК
                        // завершение упаковки не блокирует, поэтому «напечатано 0/2» — это
                        // нейтральный факт, а не тревога. Тревога только когда ШК вообще нет.
                        color={
                          !barcodeReady ? 'warning' : productLabelPrinted > 0 ? 'success' : 'default'
                        }
                        variant="outlined"
                        label={barcodeStatusLabel}
                        data-testid={`ff-packaging-barcode-status-${ln.id}`}
                      />
                    </TableCell>
                    <TableCell align="right" data-testid={`ff-packaging-line-progress-${ln.id}`}>
                      {ln.qty_done}/{ln.qty_total}
                      {remaining > 0 ? (
                        <Typography variant="caption" color="text.secondary" sx={{ display: 'block' }}>
                          осталось {remaining}
                        </Typography>
                      ) : null}
                    </TableCell>
                    <TableCell align="right">
                      {!hidePrintActions ? (
                        <IconButton
                          size="small"
                          aria-label={`Печать товара ${displayMeta.product_name}`}
                          onClick={() => openLinePrint(ln)}
                          data-testid={`ff-packaging-line-print-${ln.id}`}
                          disabled={!barcodeReady && !ln.requires_honest_sign}
                        >
                          <PrintOutlined fontSize="small" />
                        </IconButton>
                      ) : null}
                      {taskEditable && remaining > 0 ? (
                        <Tooltip title="Обычная упаковка: печать кода маркировки нужна отдельным шагом.">
                          <span>
                            <Button
                              size="small"
                              variant="outlined"
                              disabled={busy}
                              onClick={() => void packQty(ln.id, remaining)}
                              data-testid={`ff-packaging-line-mark-packed-${ln.id}`}
                              data-task-id="MPFBO-03"
                              sx={{ minWidth: 0, ml: 0.5 }}
                            >
                              Упаковано
                            </Button>
                          </span>
                        </Tooltip>
                      ) : null}
                      {taskEditable && remaining > 0 ? (
                        <Tooltip title="Товар пришёл уже упакованным и промаркированным — печать не нужна.">
                          <span>
                            <Button
                              size="small"
                              disabled={busy}
                              onClick={() => void markPrepackedExternal(ln.id, remaining)}
                              data-testid={`ff-packaging-line-prepacked-${ln.id}`}
                              data-task-id="MPFBO-03"
                              sx={{ minWidth: 0, ml: 0.5 }}
                            >
                              Пришло готовым
                            </Button>
                          </span>
                        </Tooltip>
                      ) : null}
                      {lineHasOverflowActions(ln) ? (
                        <IconButton
                          size="small"
                          aria-label="Дополнительные действия"
                          disabled={busy}
                          onClick={(e) => openLineMenu(e, ln)}
                          data-testid={`ff-packaging-line-menu-btn-${ln.id}`}
                        >
                          <MoreVertOutlined fontSize="small" />
                        </IconButton>
                      ) : null}
                      {renderLineActions?.(ln)}
                    </TableCell>
                  </TableRow>
                )
              })}
            </TableBody>
          </Table>
        </TableContainer>
      ) : (
        <Stack spacing={1.5} data-testid="ff-packaging-lines-compact">
          {task.lines.map((ln) => {
            const displayMeta = productDisplayMetaFromCatalog(ln.product_id, ln, catalogById)
            const barcode = lineBarcodeForScan(ln)
            const remaining = lineRemaining(ln)
            const markingProgressIncomplete = isLineMarkingProgressIncomplete(ln)
            const manualError = manualErrorByLine[ln.id]
            return (
              <Paper
                key={ln.id}
                variant="outlined"
                data-testid={markingProgressIncomplete ? 'ff-packaging-line-marking-incomplete' : 'ff-packaging-line'}
                sx={{ p: 1.5, bgcolor: markingProgressIncomplete ? 'warning.light' : 'background.paper' }}
              >
                <Box
                  sx={{
                    display: 'grid',
                    gridTemplateColumns: { xs: '1fr', md: 'minmax(300px, 1fr) minmax(220px, 0.7fr) minmax(260px, 0.8fr)' },
                    gap: 1.5,
                    alignItems: 'center',
                  }}
                >
                  <Stack direction="row" spacing={1.25} sx={{ minWidth: 0, alignItems: 'center' }}>
                    <Avatar
                      variant="rounded"
                      src={displayMeta.wb_primary_image_url ?? undefined}
                      alt={displayMeta.product_name}
                      sx={{ width: 56, height: 56, flex: '0 0 auto' }}
                    />
                    <Box sx={{ minWidth: 0 }}>
                      <Typography variant="body2" sx={{ fontWeight: 700, overflowWrap: 'anywhere' }} data-testid="ff-packaging-compact-product-name">
                        {displayMeta.product_name}
                      </Typography>
                      <Typography variant="caption" color="text.secondary" sx={{ display: 'block', overflowWrap: 'anywhere' }}>
                        SKU: {displayMeta.sku_code} · ШК: {barcode}
                      </Typography>
                      <Typography variant="caption" color="text.secondary" sx={{ display: 'block', overflowWrap: 'anywhere' }}>
                        Селлер: {ln.seller_name ?? displayMeta.seller_name ?? '—'} · Ячейка: {locationLabel(ln.storage_location_code)}
                      </Typography>
                    </Box>
                  </Stack>
                  <Stack spacing={0.5} sx={{ minWidth: 0 }}>
                    <Typography variant="body2" sx={{ fontWeight: 700 }} data-testid={`ff-packaging-line-progress-${ln.id}`}>
                      Готово {ln.qty_done} / Осталось {remaining} / Всего {ln.qty_total}
                    </Typography>
                    <Typography variant="caption" color="text.secondary" sx={{ overflowWrap: 'anywhere' }} data-testid="ff-packaging-instructions">
                      ТЗ: {ln.packaging_instructions?.trim() || 'не задано'}
                    </Typography>
                    {ln.requires_honest_sign ? (
                      <Typography variant="caption" color={markingProgressIncomplete ? 'warning.dark' : 'success.main'} data-testid={`ff-packaging-marking-progress-${ln.id}`}>
                        ЧЗ: напечатано {ln.qty_marking_printed} / нужно {ln.qty_need_pack}; в пуле {ln.marking_available_count}
                      </Typography>
                    ) : (
                      <Typography variant="caption" color="text.secondary">ЧЗ не требуется</Typography>
                    )}
                  </Stack>
                  <Stack spacing={1} sx={{ alignItems: { xs: 'stretch', md: 'flex-end' } }}>
                    {taskEditable && !printOnly ? (
                      <Stack direction="row" spacing={0.75} sx={{ justifyContent: { xs: 'flex-start', md: 'flex-end' }, flexWrap: 'wrap' }}>
                        <TextField
                          size="small"
                          label="+N"
                          value={manualQtyByLine[ln.id] ?? ''}
                          error={Boolean(manualError)}
                          helperText={manualError || ' '}
                          onChange={(e) => {
                            setManualQtyByLine((prev) => ({ ...prev, [ln.id]: e.target.value }))
                            setManualErrorByLine((prev) => ({ ...prev, [ln.id]: '' }))
                          }}
                          disabled={busy || remaining < 1}
                          slotProps={{
                            htmlInput: {
                              inputMode: 'numeric',
                              'data-testid': `ff-packaging-manual-qty-${ln.id}`,
                            },
                          }}
                          sx={{ width: 92 }}
                        />
                        <Button
                          size="small"
                          variant="outlined"
                          disabled={busy || remaining < 1}
                          onClick={() => void submitManualQty(ln)}
                          data-testid="ff-packaging-pack-btn"
                          sx={{ minWidth: 64, alignSelf: 'flex-start' }}
                        >
                          +N
                        </Button>
                      </Stack>
                    ) : null}
                    <Stack direction="row" spacing={0.5} sx={{ justifyContent: { xs: 'flex-start', md: 'flex-end' }, flexWrap: 'wrap' }}>
                      {!hidePrintActions && (alwaysShowPrintAction || printOnly || ln.requires_honest_sign) ? (
                        <IconButton
                          size="small"
                          aria-label={`Печать товара ${displayMeta.product_name}`}
                          onClick={() => openLinePrint(ln)}
                          data-testid={`ff-packaging-line-print-${ln.id}`}
                        >
                          <PrintOutlined fontSize="small" />
                        </IconButton>
                      ) : null}
                      {!hidePrintActions && ln.requires_honest_sign && ln.qty_need_pack > 0 && ln.qty_marking_printed < 1 ? (
                        <Button
                          size="small"
                          variant="outlined"
                          disabled={busy || ln.marking_available_count < 1}
                          onClick={() => openLinePrint(ln)}
                          data-testid="ff-packaging-print-marking"
                        >
                          Печать ЧЗ
                        </Button>
                      ) : null}
                      {lineHasOverflowActions(ln) ? (
                        <IconButton
                          size="small"
                          aria-label="Дополнительные действия"
                          disabled={busy}
                          onClick={(e) => openLineMenu(e, ln)}
                          data-testid={`ff-packaging-line-menu-btn-${ln.id}`}
                        >
                          <MoreVertOutlined fontSize="small" />
                        </IconButton>
                      ) : null}
                      {ln.qty_confirmed_packed < ln.qty_suggested_packed ? (
                        <Button
                          size="small"
                          disabled={busy || !taskEditable || ln.qty_suggested_packed < 1}
                          onClick={() => void confirmPacked(ln.id)}
                          data-testid="ff-packaging-confirm-shelf"
                        >
                          С полки
                        </Button>
                      ) : null}
                      {renderLineActions?.(ln)}
                    </Stack>
                  </Stack>
                </Box>
              </Paper>
            )
          })}
        </Stack>
      )}
      {taskEditable ? (
        <Paper variant="outlined" sx={{ p: 2 }} data-testid="ff-packaging-complete-panel">
          <Stack spacing={1.5}>
            {hasIncompleteMarking && !isMpUnloadTask ? (
              <Alert severity="warning" data-testid="ff-packaging-marking-incomplete-warning">
                {MARKING_NOT_DONE_MESSAGE}
                {incompleteMarkingLines.map((ln) => (
                  <Typography
                    key={ln.id}
                    variant="body2"
                    sx={{ mt: 0.5 }}
                    data-testid="ff-packaging-marking-incomplete-line"
                  >
                    {ln.product_name} ({ln.sku_code}): напечатано {ln.qty_marking_printed} из{' '}
                    {ln.qty_done}
                  </Typography>
                ))}
              </Alert>
            ) : null}
            {isMpUnloadTask && (hasIncompletePacking || hasIncompleteMarking) ? (
              <Typography variant="body2" color="text.secondary" data-testid="ff-packaging-complete-blocker">
                Завершение станет доступно после печати обязательных ЧЗ/ШК и распределения товара по коробам.
              </Typography>
            ) : null}
            <Button
              variant="contained"
              color="success"
              disabled={
                busy ||
                hasIncompleteMarking ||
                hasIncompletePacking
              }
              onClick={() => void completeTask()}
              data-testid="ff-packaging-complete"
              sx={{ alignSelf: 'flex-start' }}
            >
              Завершить упаковку
            </Button>
          </Stack>
        </Paper>
      ) : null}
      {(task.events ?? []).length > 0 ? (
        <Paper variant="outlined" sx={{ p: 2 }} data-testid="ff-packaging-history">
          <Stack spacing={0.75}>
            <Typography variant="subtitle2" sx={{ fontWeight: 700 }}>
              История
            </Typography>
            {orderedEvents.slice().reverse().slice(0, 8).map((event) => (
              <Typography key={event.id} variant="body2" color="text.secondary" sx={{ overflowWrap: 'anywhere' }}>
                {packagingEventLabel(event.action, event.quantity)} · {event.product_name ?? 'задание'} · {event.created_by_user_email ?? 'оператор'} ·{' '}
                {new Date(event.created_at).toLocaleString('ru-RU')}
              </Typography>
            ))}
          </Stack>
        </Paper>
      ) : null}
      <Dialog
        open={Boolean(undoConfirmEvent)}
        onClose={busy ? undefined : () => setUndoConfirmEvent(null)}
        maxWidth="xs"
        fullWidth
        data-testid="ff-packaging-undo-confirm-dialog"
      >
        <DialogTitle>Отменить ручное добавление?</DialogTitle>
        <DialogContent>
          <Typography variant="body2" data-testid="ff-packaging-undo-confirm-message">
            Из задания будет снято {undoConfirmEvent?.quantity ?? 0} шт
            {undoConfirmEvent?.product_name ? ` · ${undoConfirmEvent.product_name}` : ''}.
            Количество вернётся в «Осталось». Подтвердите только если оператор добавил
            количество ошибочно.
          </Typography>
        </DialogContent>
        <DialogActions>
          <Button
            onClick={() => setUndoConfirmEvent(null)}
            disabled={busy}
            data-testid="ff-packaging-undo-confirm-cancel"
          >
            Не отменять
          </Button>
          <Button
            color="error"
            variant="contained"
            disabled={busy}
            onClick={() => void performUndoLast(undoConfirmEvent)}
            data-testid="ff-packaging-undo-confirm-submit"
          >
            Отменить +{undoConfirmEvent?.quantity ?? 0}
          </Button>
        </DialogActions>
      </Dialog>
      {markingPrintDialog}
      <Menu
        anchorEl={lineMenuAnchor}
        open={Boolean(lineMenuAnchor)}
        onClose={closeLineMenu}
        data-testid="ff-packaging-line-menu"
      >
        {lineMenuLine &&
        lineMenuLine.requires_honest_sign &&
        !isMpUnloadTask &&
        lineMenuLine.qty_marking_printed > 0 ? (
          <MenuItem
            disabled={busy}
            onClick={() => {
              closeLineMenu()
              openLinePrint(lineMenuLine, { reprint: true })
            }}
            data-testid="ff-packaging-reprint-marking"
          >
            Повтор
          </MenuItem>
        ) : null}
        {lineMenuLine &&
        lineMenuLine.requires_honest_sign &&
        lineMenuLine.qty_marking_printed > 0 ? (
          <MenuItem
            disabled={busy}
            onClick={() => {
              closeLineMenu()
              void openDefectDialog(lineMenuLine.id)
            }}
            data-testid="ff-packaging-defect-marking"
          >
            Брак
          </MenuItem>
        ) : null}
      </Menu>
      <Dialog
        open={defectDialogOpen}
        onClose={closeDefectDialog}
        maxWidth="sm"
        fullWidth
        data-testid="ff-packaging-defect-dialog"
      >
        <DialogTitle>Отметить брак КМ</DialogTitle>
        <DialogContent>
          <Stack spacing={2} sx={{ pt: 1 }}>
            {defectDialogError ? (
              <Alert severity="error" data-testid="ff-packaging-defect-dialog-error">
                {defectDialogError}
              </Alert>
            ) : null}
            <FormControl fullWidth disabled={defectDialogBusy || defectCodes.length < 1}>
              <InputLabel id="ff-packaging-defect-code-label">КМ</InputLabel>
              <Select
                labelId="ff-packaging-defect-code-label"
                label="КМ"
                value={defectSelectedCodeId}
                onChange={(e) => setDefectSelectedCodeId(e.target.value)}
                data-testid="ff-packaging-defect-code-select"
              >
                {defectCodes.map((code) => (
                  <MenuItem
                    key={code.id}
                    value={code.id}
                    sx={{ fontFamily: 'ui-monospace, SFMono-Regular, Menlo, monospace' }}
                  >
                    {code.cis_code}
                  </MenuItem>
                ))}
              </Select>
            </FormControl>
            <TextField
              label="Причина брака"
              value={defectReason}
              onChange={(e) => setDefectReason(e.target.value)}
              disabled={defectDialogBusy}
              multiline
              minRows={2}
              slotProps={{ htmlInput: { maxLength: 512 } }}
              data-testid="ff-packaging-defect-reason"
            />
          </Stack>
        </DialogContent>
        <DialogActions>
          <Button onClick={closeDefectDialog} disabled={defectDialogBusy}>
            Отмена
          </Button>
          <Button
            variant="contained"
            color="warning"
            disabled={defectDialogBusy || !defectSelectedCodeId}
            onClick={() => void submitDefectMarking()}
            data-testid="ff-packaging-defect-confirm"
          >
            Подтвердить брак
          </Button>
        </DialogActions>
      </Dialog>
      {onClose ? (
        <Stack direction="row" spacing={1} sx={{ justifyContent: 'flex-end' }}>
          {manualTask ? (
            <Button
              color="error"
              variant="outlined"
              disabled={busy}
              onClick={() => void cancelTask()}
              data-testid="ff-packaging-cancel-task"
            >
              Отменить задание
            </Button>
          ) : null}
          <Button onClick={onClose} data-testid="ff-packaging-close">
            Закрыть
          </Button>
        </Stack>
      ) : null}
    </Stack>
  )
}

type PageProps = {
  token: string
}

type WarehouseRow = { id: string; name: string; code: string }

type SortingBalanceRow = {
  product_id: string
  sku_code: string
  product_name: string
  seller_id?: string | null
  seller_name?: string | null
  packaging_instructions?: string | null
  requires_honest_sign?: boolean
  quantity_unpacked: number
}

type CreateDialogProps = {
  open: boolean
  token: string
  onClose: () => void
  onCreated: (task: PackagingTask) => void
}

type LocationRow = { id: string; code: string; barcode: string }

type PackagingTaskStatusFilter = 'open' | 'done' | 'cancelled'

function FfCreatePackagingTaskDialog({ open, token, onClose, onCreated }: CreateDialogProps) {
  const { catalogById } = useWbProductCatalog(token, open)
  const authHeaders = {
    Authorization: `Bearer ${token}`,
    'Content-Type': 'application/json',
  }
  const [warehouses, setWarehouses] = useState<WarehouseRow[]>([])
  const [warehouseId, setWarehouseId] = useState('')
  const [locations, setLocations] = useState<LocationRow[]>([])
  const [locationId, setLocationId] = useState('')
  const [rows, setRows] = useState<SortingBalanceRow[]>([])
  const [selected, setSelected] = useState<Record<string, boolean>>({})
  const [qtyByProduct, setQtyByProduct] = useState<Record<string, string>>({})
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (!open) {
      setWarehouseId('')
      setLocationId('')
      setLocations([])
      setRows([])
      setSelected({})
      setQtyByProduct({})
      setError(null)
      return
    }
    void (async () => {
      const res = await fetch(apiUrl('/warehouses'), { headers: authHeaders })
      if (!res.ok) {
        setError(await readApiErrorMessage(res))
        return
      }
      const list = (await res.json()) as WarehouseRow[]
      setWarehouses(list)
    })()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, token])

  useEffect(() => {
    if (!open || !warehouseId) {
      setLocations([])
      setLocationId('')
      setRows([])
      setSelected({})
      setQtyByProduct({})
      return
    }
    void (async () => {
      const locRes = await fetch(apiUrl(`/warehouses/${warehouseId}/locations`), {
        headers: authHeaders,
      })
      if (!locRes.ok) {
        setError(await readApiErrorMessage(locRes))
        return
      }
      const locList = (await locRes.json()) as LocationRow[]
      const sorted = [...locList].sort((a, b) => {
        if (a.code === '__SORTING__') return -1
        if (b.code === '__SORTING__') return 1
        return a.code.localeCompare(b.code)
      })
      setLocations(sorted)
      setLocationId('')
      setRows([])
      setSelected({})
      setQtyByProduct({})
    })()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, warehouseId, token])

  useEffect(() => {
    if (!open || !locationId) {
      setRows([])
      setSelected({})
      setQtyByProduct({})
      return
    }
    void (async () => {
      const balRes = await fetch(
        apiUrl(`/operations/inventory-balances?storage_location_id=${locationId}`),
        { headers: authHeaders },
      )
      if (!balRes.ok) {
        setError(await readApiErrorMessage(balRes))
        return
      }
      const balances = (await balRes.json()) as SortingBalanceRow[]
      const unpacked = balances.filter((b) => b.quantity_unpacked > 0)
      setRows(unpacked)
      const qty: Record<string, string> = {}
      for (const b of unpacked) {
        qty[b.product_id] = String(b.quantity_unpacked)
      }
      setSelected({})
      setQtyByProduct(qty)
    })()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, locationId, token])

  const selectedRows = rows.filter((row) => selected[row.product_id])
  const selectedSellerKeys = Array.from(
    new Set(selectedRows.map((row) => row.seller_id ?? '__NO_SELLER__')),
  )
  const selectedSellerCount = selectedSellerKeys.length
  const hasMixedSellerSelection = selectedSellerKeys.length > 1
  const selectedQtyTotal = selectedRows.reduce((sum, row) => {
    const parsed = parseStrictPositiveInteger(qtyByProduct[row.product_id] ?? '')
    return sum + (parsed ?? 0)
  }, 0)
  const selectedRowErrors = new Map<string, string>()
  for (const row of selectedRows) {
    const raw = qtyByProduct[row.product_id] ?? ''
    const parsed = parseStrictPositiveInteger(raw)
    if (parsed === null) {
      selectedRowErrors.set(row.product_id, 'Введите целое число')
    } else if (parsed > row.quantity_unpacked) {
      selectedRowErrors.set(row.product_id, 'Нельзя больше остатка')
    }
  }
  const createBlocked =
    busy ||
    !warehouseId ||
    !locationId ||
    selectedRows.length < 1 ||
    hasMixedSellerSelection ||
    selectedRowErrors.size > 0

  const submit = async () => {
    if (!warehouseId || !locationId || selectedRows.length === 0) {
      setError('Выберите склад, место и хотя бы один товар с количеством больше 0.')
      return
    }
    if (hasMixedSellerSelection) {
      setError('Нельзя создать одно задание для разных селлеров. Выберите товары одного селлера.')
      return
    }
    if (selectedRowErrors.size > 0) {
      setError('Проверьте количество: нужно целое число от 1 до доступного остатка.')
      return
    }
    const lines = selectedRows.map((r) => ({
      product_id: r.product_id,
      storage_location_id: locationId,
      quantity: parseStrictPositiveInteger(qtyByProduct[r.product_id] ?? '') ?? 0,
    }))
    setBusy(true)
    setError(null)
    try {
      const res = await fetch(apiUrl('/operations/packaging-tasks'), {
        method: 'POST',
        headers: authHeaders,
        body: JSON.stringify({ warehouse_id: warehouseId, lines }),
      })
      if (!res.ok) {
        setError(await readPackagingApiErrorMessage(res))
        return
      }
      onCreated((await res.json()) as PackagingTask)
      onClose()
    } finally {
      setBusy(false)
    }
  }

  return (
    <Dialog
      open={open}
      onClose={onClose}
      fullWidth
      maxWidth={false}
      slotProps={{
        paper: {
          sx: {
            width: 'min(1120px, calc(100vw - 64px))',
            maxWidth: 'calc(100vw - 64px)',
            maxHeight: '92vh',
            boxSizing: 'border-box',
          },
        },
      }}
      data-testid="ff-packaging-create-dialog"
    >
      <DialogTitle>Создать задание на упаковку</DialogTitle>
      <DialogContent>
        <Stack spacing={2} sx={{ mt: 1 }}>
          {error ? <Alert severity="error">{error}</Alert> : null}
          <FormControl fullWidth size="small">
            <InputLabel id="ff-packaging-wh-label">Склад</InputLabel>
            <Select
              labelId="ff-packaging-wh-label"
              label="Склад"
              value={warehouseId}
              onChange={(e) => setWarehouseId(String(e.target.value))}
              data-testid="ff-packaging-create-warehouse"
            >
              {warehouses.map((w) => (
                <MenuItem key={w.id} value={w.id}>
                  {w.name}
                </MenuItem>
              ))}
            </Select>
          </FormControl>
          {warehouseId ? (
            <FormControl fullWidth size="small">
              <InputLabel id="ff-packaging-loc-label">Место (ячейка)</InputLabel>
              <Select
                labelId="ff-packaging-loc-label"
                label="Место (ячейка)"
                value={locationId}
                onChange={(e) => setLocationId(String(e.target.value))}
                data-testid="ff-packaging-create-location"
              >
                {locations.map((loc) => (
                  <MenuItem key={loc.id} value={loc.id}>
                    {locationLabel(loc.code)}
                  </MenuItem>
                ))}
              </Select>
            </FormControl>
          ) : null}
          {warehouseId && locationId && rows.length === 0 ? (
            <Typography variant="body2" color="text.secondary" data-testid="ff-packaging-create-empty">
              В этой ячейке нет товара для упаковки.
            </Typography>
          ) : null}
          {rows.length > 0 ? (
            <Alert severity={hasMixedSellerSelection ? 'error' : 'info'} data-testid="ff-packaging-create-summary">
              {hasMixedSellerSelection
                ? 'Нельзя создать одно задание для разных селлеров. Выберите товары одного селлера.'
                : `Выбрано ${selectedRows.length} строк / ${selectedQtyTotal} шт. / ${sellerCountLabel(selectedSellerCount)}`}
            </Alert>
          ) : null}
          {rows.length > 0 ? (
            <TableContainer component={Paper} variant="outlined" sx={{ width: '100%', overflowX: 'hidden' }}>
              <Table
                size="small"
                data-testid="ff-packaging-create-table"
                sx={{
                  tableLayout: 'fixed',
                  width: '100%',
                  '& th': { py: 1.25 },
                  '& td': { py: 1.25 },
                }}
              >
                <TableHead>
                  <TableRow>
                    <TableCell padding="checkbox" sx={{ width: 44 }} />
                    <TableCell>Товар / селлер / ТЗ</TableCell>
                    <TableCell align="right" sx={{ width: 104 }}>
                      Неупаковано
                    </TableCell>
                    <TableCell align="right" sx={{ width: 112 }}>
                      В задание
                    </TableCell>
                  </TableRow>
                </TableHead>
                <TableBody>
                  {rows.map((r) => {
                    const displayMeta = productDisplayMetaFromCatalog(r.product_id, r, catalogById)
                    const primaryBarcode = resolveProductPrimaryBarcode(displayMeta) || r.sku_code
                    return (
                      <TableRow key={r.product_id} data-testid="ff-packaging-create-row">
                        <TableCell padding="checkbox">
                          <Checkbox
                            checked={Boolean(selected[r.product_id])}
                            onChange={(e) =>
                              setSelected((prev) => ({ ...prev, [r.product_id]: e.target.checked }))
                            }
                            data-testid={`ff-packaging-create-row-select-${r.product_id}`}
                          />
                        </TableCell>
                        <TableCell sx={{ minWidth: 0 }}>
                          <Stack direction="row" spacing={1.25} sx={{ alignItems: 'flex-start', minWidth: 0 }}>
                            <Avatar
                              variant="rounded"
                              src={displayMeta.wb_primary_image_url ?? undefined}
                              alt={displayMeta.product_name}
                              sx={{ width: 42, height: 42, flex: '0 0 auto' }}
                            />
                            <Box sx={{ minWidth: 0 }}>
                              <Typography variant="body2" sx={{ fontWeight: 700, overflowWrap: 'anywhere' }}>
                                {displayMeta.product_name}
                              </Typography>
                              <Typography variant="caption" color="text.secondary" sx={{ display: 'block', overflowWrap: 'anywhere' }}>
                                SKU: {displayMeta.sku_code} · ШК: {primaryBarcode}
                                {displayMeta.wb_nm_id ? ` · WB: ${displayMeta.wb_nm_id}` : ''}
                              </Typography>
                              <Typography variant="caption" color="text.secondary" sx={{ display: 'block', overflowWrap: 'anywhere' }}>
                                Селлер: {r.seller_name ?? displayMeta.seller_name ?? '—'}
                              </Typography>
                              <Typography variant="caption" color="text.secondary" sx={{ display: 'block', overflowWrap: 'anywhere' }}>
                                ТЗ: {r.packaging_instructions?.trim() || 'не задано'}
                              </Typography>
                            </Box>
                          </Stack>
                        </TableCell>
                        <TableCell align="right">{r.quantity_unpacked}</TableCell>
                        <TableCell align="right">
                          <TextField
                            size="small"
                            value={qtyByProduct[r.product_id] ?? ''}
                            error={selectedRowErrors.has(r.product_id)}
                            helperText={selectedRowErrors.get(r.product_id) ?? ' '}
                            onChange={(e) =>
                              setQtyByProduct((prev) => ({
                                ...prev,
                                [r.product_id]: e.target.value,
                              }))
                            }
                            slotProps={{
                              htmlInput: {
                                inputMode: 'numeric',
                                'data-testid': `ff-packaging-create-qty-${r.product_id}`,
                              },
                            }}
                            sx={{ width: 84 }}
                          />
                        </TableCell>
                      </TableRow>
                    )
                  })}
                </TableBody>
              </Table>
            </TableContainer>
          ) : null}
        </Stack>
      </DialogContent>
      <DialogActions>
        <Button onClick={onClose} disabled={busy}>
          Отмена
        </Button>
        <Button
          variant="contained"
          disabled={createBlocked}
          onClick={() => void submit()}
          data-testid="ff-packaging-create-submit"
        >
          Создать
        </Button>
      </DialogActions>
    </Dialog>
  )
}

export function FfPackagingPage({ token }: PageProps) {
  const location = useLocation()
  const navigate = useNavigate()
  const { taskId: routeTaskId } = useParams<{ taskId?: string }>()
  const [tasks, setTasks] = useState<PackagingTask[]>([])
  const [selected, setSelected] = useState<PackagingTask | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [createOpen, setCreateOpen] = useState(false)
  const [pendingMarkingCount, setPendingMarkingCount] = useState(0)
  const [statusFilter, setStatusFilter] = useState<PackagingTaskStatusFilter>('open')
  const [search, setSearch] = useState('')

  const loadTaskById = useCallback(
    async (taskId: string) => {
      const res = await fetch(apiUrl(`/operations/packaging-tasks/${taskId}`), {
        headers: { Authorization: `Bearer ${token}` },
      })
      if (!res.ok) {
        setError(await readPackagingApiErrorMessage(res))
        return
      }
      setSelected((await res.json()) as PackagingTask)
    },
    [token],
  )

  const load = useCallback(async () => {
    const params = new URLSearchParams({ status: statusFilter })
    const trimmedSearch = search.trim()
    if (trimmedSearch) {
      params.set('search', trimmedSearch)
    }
    const res = await fetch(apiUrl(`/operations/packaging-tasks?${params}`), {
      headers: { Authorization: `Bearer ${token}` },
    })
    if (!res.ok) {
      setError(await readPackagingApiErrorMessage(res))
    } else {
      setTasks((await res.json()) as PackagingTask[])
    }
    try {
      const pending = await fetchPendingMarking(token)
      setPendingMarkingCount(pendingMarkingLineCount(pending))
    } catch {
      setPendingMarkingCount(0)
    }
  }, [search, statusFilter, token])

  useEffect(() => {
    void load()
  }, [load])

  useEffect(() => {
    const state = location.state as { taskId?: string } | null
    const nextTaskId = routeTaskId ?? state?.taskId
    if (nextTaskId) {
      void loadTaskById(nextTaskId)
    } else {
      setSelected(null)
    }
  }, [location.state, loadTaskById, routeTaskId])

  const openTask = (task: PackagingTask) => {
    setSelected(task)
    navigate(`/app/ff/packaging/${task.id}`)
  }

  const closeTask = () => {
    setSelected(null)
    navigate('/app/ff/packaging', { replace: true })
  }

  return (
    <Box data-testid="ff-packaging-page" sx={{ minWidth: 0, maxWidth: '100%' }}>
      <PageHeader
        title="Упаковка"
        description="Задания на маркировку и упаковку. Создайте из ячейки или сортировки, либо откройте из отгрузки на МП."
      />
      <Stack direction="row" spacing={1} sx={{ justifyContent: 'flex-end', mb: 2, alignItems: 'center' }}>
        <Badge badgeContent={pendingMarkingCount} color="warning" data-testid="ff-packaging-pending-badge">
          <Button
            component={RouterLink}
            to="/app/ff/packaging/pending-marking"
            variant="outlined"
            data-testid="ff-packaging-pending-link"
          >
            Осталось промаркировать
          </Button>
        </Badge>
        <Button
          variant="contained"
          onClick={() => setCreateOpen(true)}
          data-testid="ff-packaging-create-open"
        >
          Создать задание
        </Button>
      </Stack>
      {error ? <Alert severity="error">{error}</Alert> : null}
      {selected ? (
        <FfPackagingTaskPanel
          token={token}
          task={selected}
          onClose={closeTask}
          onUpdated={(t) => {
            setSelected(t)
            void load()
          }}
        />
      ) : (
        <Paper variant="outlined" data-testid="ff-packaging-queue" sx={{ overflowX: 'hidden' }}>
          <Stack spacing={1.5} sx={{ p: 2, pb: 1 }}>
            <Tabs
              value={statusFilter}
              onChange={(_event, value: PackagingTaskStatusFilter) => {
                setStatusFilter(value)
                setSelected(null)
                navigate('/app/ff/packaging', { replace: true })
              }}
              variant="scrollable"
              allowScrollButtonsMobile
              data-testid="ff-packaging-status-tabs"
            >
              <Tab label="Открытые" value="open" data-testid="ff-packaging-tab-open" />
              <Tab label="Выполненные" value="done" data-testid="ff-packaging-tab-done" />
              <Tab label="Отменённые" value="cancelled" data-testid="ff-packaging-tab-cancelled" />
            </Tabs>
            <TextField
              size="small"
              label="Поиск по номеру, товару, селлеру или ячейке"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              data-testid="ff-packaging-history-search"
            />
          </Stack>
          <TableContainer sx={{ width: '100%', overflowX: 'auto' }}>
            <Table
              size="small"
              sx={{
                width: '100%',
                minWidth: 0,
                tableLayout: 'fixed',
                '& th, & td': { overflowWrap: 'anywhere' },
              }}
            >
              <TableHead>
                <TableRow>
                  <TableCell sx={{ width: 92 }}>Номер</TableCell>
                  <TableCell sx={{ width: 104 }}>Статус</TableCell>
                  <TableCell sx={{ width: 150 }}>Селлер</TableCell>
                  <TableCell sx={{ width: 180 }}>Склад / ячейка</TableCell>
                  <TableCell>Товар</TableCell>
                  <TableCell align="right" sx={{ width: 84 }}>Прогресс</TableCell>
                  <TableCell sx={{ width: 116 }}>Источник</TableCell>
                </TableRow>
              </TableHead>
              <TableBody>
                {tasks.length === 0 ? (
                  <TableRow>
                    <TableCell colSpan={7}>
                      <Typography variant="body2" color="text.secondary">
                        {statusFilter === 'open'
                          ? 'Нет открытых заданий.'
                          : statusFilter === 'done'
                            ? 'Нет выполненных заданий.'
                            : 'Нет отменённых заданий.'}
                      </Typography>
                    </TableCell>
                  </TableRow>
                ) : (
                  tasks.map((t) => {
                    const totals = taskTotals(t)
                    return (
                      <TableRow
                        key={t.id}
                        hover
                        role="button"
                        tabIndex={0}
                        sx={{ cursor: 'pointer' }}
                        onClick={() => openTask(t)}
                        onKeyDown={(e) => {
                          if (e.key === 'Enter' || e.key === ' ') {
                            e.preventDefault()
                            openTask(t)
                          }
                        }}
                        data-testid="ff-packaging-queue-row"
                      >
                        <TableCell>{formatHumanDocumentNumber(t) ?? '—'}</TableCell>
                        <TableCell>{statusLabel(t.status)}</TableCell>
                        <TableCell sx={{ maxWidth: 180, overflowWrap: 'anywhere' }}>
                          {taskSellerLabel(t)}
                        </TableCell>
                        <TableCell sx={{ maxWidth: 220, overflowWrap: 'anywhere' }}>
                          {taskPlaceLabel(t)}
                        </TableCell>
                        <TableCell sx={{ maxWidth: 260, overflowWrap: 'anywhere' }}>
                          {taskProductSummary(t)}
                        </TableCell>
                        <TableCell align="right">
                          {totals.done}/{totals.total}
                        </TableCell>
                        <TableCell>{t.marketplace_unload_request_id ? 'Отгрузка МП' : 'Ручное'}</TableCell>
                      </TableRow>
                    )
                  })
                )}
              </TableBody>
            </Table>
          </TableContainer>
        </Paper>
      )}
      <FfCreatePackagingTaskDialog
        open={createOpen}
        token={token}
        onClose={() => setCreateOpen(false)}
        onCreated={(task) => {
          setSelected(task)
          navigate(`/app/ff/packaging/${task.id}`)
          void load()
        }}
      />
    </Box>
  )
}

type DialogProps = {
  open: boolean
  token: string
  unloadId: string
  unloadLabel: string
  onClose: () => void
}

export function FfPackagingTaskDialog({
  open,
  token,
  unloadId,
  unloadLabel,
  onClose,
}: DialogProps) {
  const [task, setTask] = useState<PackagingTask | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (!open) {
      setTask(null)
      return
    }
    void (async () => {
      const res = await fetch(apiUrl(`/operations/packaging-tasks/by-unload/${unloadId}`), {
        headers: { Authorization: `Bearer ${token}` },
      })
      if (!res.ok) {
        setError(await readPackagingApiErrorMessage(res))
        return
      }
      setTask((await res.json()) as PackagingTask)
    })()
  }, [open, token, unloadId])

  return (
    <Dialog
      open={open}
      onClose={onClose}
      fullWidth
      maxWidth={false}
      slotProps={{ paper: { sx: { width: 'min(1200px, 96vw)', maxHeight: '92vh' } } }}
      data-testid="ff-packaging-dialog"
    >
      <DialogTitle>Задание на упаковку</DialogTitle>
      <DialogContent>
        {error ? <Alert severity="error">{error}</Alert> : null}
        {task ? (
          <FfPackagingTaskPanel
            token={token}
            task={task}
            unloadLabel={unloadLabel}
            onUpdated={setTask}
          />
        ) : null}
      </DialogContent>
      <DialogActions>
        <Button onClick={onClose} data-testid="ff-packaging-dialog-close">
          Вернуться к отгрузке
        </Button>
      </DialogActions>
    </Dialog>
  )
}
