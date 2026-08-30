import { useCallback, useEffect, useMemo, useRef, useState, type MouseEvent } from 'react'
import { useSearchParams } from 'react-router-dom'
import { useBarcodeScanner } from '../../hooks/useBarcodeScanner'
import {
  ArrowForwardOutlined,
  DeleteOutlineOutlined,
  ExpandMoreOutlined,
  MoreVertOutlined,
} from '@mui/icons-material'
import {
  Accordion,
  AccordionDetails,
  AccordionSummary,
  Alert,
  Box,
  Button,
  Chip,
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
  Tab,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableRow,
  Tabs,
  TextField,
  Tooltip,
  Typography,
  Snackbar,
} from '@mui/material'
import { alpha } from '@mui/material/styles'
import { FfProductLineCells, FfProductTableHeadCells } from '../../components/FfProductLineCells'
import { WbProductPickerDialog, type WbProductPickerCatalogRow } from '../../components/WbProductPickerDialog'
import { useWbProductCatalog } from '../../hooks/useWbProductCatalog'
import { apiUrl } from '../../api'
import { WmsDateField } from '../../components/WmsDateField'
import { MarketplaceChip } from '../../ui-kit'

import { resolveProductIdByBarcode } from '../../utils/resolveProductByBarcode'
import { readApiErrorMessage } from '../../utils/readApiErrorMessage'
import { PageHeader } from '../../ui/PageHeader'
import type { FfInboundSummary, FfOutboundSummary } from './FfDashboard'
import {
  FfPackagingTaskPanel,
  type PackagingTask,
} from './FfPackagingPage'
import { FfMarketplaceUnloadBoxAddDialog } from './FfMarketplaceUnloadBoxAddDialog'
import { FfUnloadPickPage } from './unload-pick/FfUnloadPickPage'
import { BoxImportDialog } from '../../components/BoxImportDialog'
import { BoxLabelPrintDialog } from '../../components/BoxLabelPrintDialog'
import type { LabelSize } from '../../utils/labelSize'
import { formatHumanDocumentNumber } from './documentDisplay'
import { formatDateTimeLocal } from '../../utils/formatDateTimeLocal'
import { printBarcodeLabel } from '../../utils/printBarcodeLabel'
import { renderBarcodeDataUrl } from '../../utils/renderBarcodeDataUrl'
import { createLatestRequestSequence } from '../../utils/latestRequestSequence'

export type FfMarketplaceUnloadSummary = {
  id: string
  document_number?: string | null
  display_number?: string | null
  public_number?: string | null
  human_number?: string | null
  warehouse_id: string
  warehouse_name: string
  status: string
  line_count: number
  seller_id: string | null
  seller_name: string | null
  marketplace?: string
  planned_shipment_date?: string | null
  ff_modified?: boolean
  created_at: string
}

export type FfDiscrepancyActSummary = {
  id: string
  status: string
  line_count: number
  inbound_intake_request_id: string | null
  seller_id: string | null
  seller_name: string | null
  created_at: string
}

type DocLineRow = {
  id: string
  product_id: string
  sku_code: string
  product_name: string
  quantity: number
  picked_qty?: number
  has_discrepancy?: boolean
  inbound_intake_line_id?: string | null
}

type MarketplaceUnloadBoxLine = {
  id: string
  product_id: string
  sku_code: string
  product_name: string
  quantity: number
}

type MarketplaceUnloadBox = {
  id: string
  box_preset: string
  internal_barcode: string | null
  closed_at: string | null
  lines: MarketplaceUnloadBoxLine[]
}

type MarketplaceUnloadPickAllocation = {
  id: string
  product_id: string
  sku_code: string
  product_name: string
  storage_location_id: string
  location_code: string
  quantity: number
}

type LinkedPackagingTask = {
  task_id: string
  status: string
  qty_done: number
  qty_total: number
  is_complete: boolean
}

type MarketplaceUnloadDetail = {
  id: string
  document_number: string | null
  display_number: string | null
  public_number: string | null
  human_number: string | null
  warehouse_id: string
  warehouse_name: string
  status: string
  ff_modified: boolean
  seller_id: string | null
  seller_name: string | null
  marketplace: string
  wb_mp_warehouse_id: number | null
  planned_shipment_date: string | null
  created_at: string | null
  lines: DocLineRow[]
  boxes: MarketplaceUnloadBox[]
  pick_allocations: MarketplaceUnloadPickAllocation[]
  linked_packaging_task: LinkedPackagingTask | null
}

type DiscrepancyActDetail = {
  id: string
  status: string
  inbound_intake_request_id: string | null
  lines: DocLineRow[]
}

type DocKind = 'inbound' | 'outbound' | 'marketplace_unload' | 'discrepancy_act'

type MpUnloadTab = 'plan' | 'pick' | 'packaging'

/** Быстрые фильтры без операционной «Отгрузки» — только «Отгрузки на МП». */
type QuickFilterKind = 'all' | 'inbound' | 'marketplace_unload' | 'discrepancy_act'

type UnifiedRow = {
  kind: DocKind
  id: string
  documentNumber: string | null
  plannedDate: string | null
  createdAt: string | null
  status: string
  lineCount: number
  sellerName: string | null
  marketplace: string | null
  extraLabel: string | null
  ffModified: boolean
}

function statusRu(status: string): string {
  if (status === 'draft') return 'Черновик'
  if (status === 'confirmed') return 'Утверждено'
  if (status === 'approved') return 'Утверждено'
  if (status === 'rejected') return 'Отклонено'
  if (status === 'collecting') return 'На сборке'
  if (status === 'shipped') return 'Отгружено'
  if (status === 'submitted') return 'Запланировано'
  if (status === 'cancelled') return 'Отменено'
  if (status === 'primary_accepted') return 'Принято на складе'
  if (status === 'verifying') return 'Проверка'
  if (status === 'verified') return 'Проверено'
  if (status === 'posted') return 'Проведено'
  return status
}

function docStatusRu(kind: DocKind, status: string): string {
  if (kind === 'discrepancy_act' && status === 'confirmed') return 'Передан на FF'
  return statusRu(status)
}

function kindRu(kind: DocKind): string {
  if (kind === 'inbound') return 'Приёмка'
  if (kind === 'outbound') return 'Отгрузка'
  if (kind === 'marketplace_unload') return 'Отгрузка на МП'
  return 'Расхождение'
}

function formatSignedQty(value: number): string {
  return value > 0 ? `+${value}` : String(value)
}

const mpUnloadSteps: { value: MpUnloadTab; label: string; testId: string }[] = [
  { value: 'plan', label: 'Товары', testId: 'ff-mp-tab-products' },
  // MPFBO-01: «Если план утверждён, вкладка "Подбор" должна становиться доступной».
  // Шаг был потерян 28.06 в коммите 304abf2, когда поле скана ячейки/товара переподписали
  // на короба; бэкенд подбора при этом остался рабочим.
  { value: 'pick', label: 'Подбор', testId: 'ff-mp-tab-pick' },
  { value: 'packaging', label: 'Упаковка', testId: 'ff-mp-tab-packaging' },
]

function mpUnloadStepLabel(step: MpUnloadTab): string {
  return mpUnloadSteps.find((item) => item.value === step)?.label ?? step
}

/** Человеческий размер короба вместо служебного кода пресета («60_40_40»). */
function mpBoxPresetLabel(preset: string): string {
  if (preset === '60_40_40') return '60×40×40 см'
  if (preset === '30_20_30') return '30×20×30 см'
  return preset
}

type ProductPick = { id: string; sku_code: string; name: string }
type AvailableProductPick = ProductPick & { available: number }

export type FfSuppliesShipmentsPageVariant = 'supplies' | 'mp-shipments'

type Props = {
  pageVariant?: FfSuppliesShipmentsPageVariant
  busy: boolean
  error: string | null
  infoNotice: string | null
  onDismissInfoNotice: () => void
  token: string | null
  sellers: { id: string; name: string }[]
  productPicklist: ProductPick[]
  onRefreshFfSupplyExtras: () => Promise<void>
  inboundSummaries: FfInboundSummary[]
  outboundSummaries: FfOutboundSummary[]
  marketplaceUnloadSummaries: FfMarketplaceUnloadSummary[]
  discrepancyActSummaries: FfDiscrepancyActSummary[]
  onOpenInbound: (id: string) => void
  onOpenOutbound: (id: string) => void
  onCreateMpShipment: (
    sellerId: string,
    marketplace: 'wb' | 'ozon',
  ) => Promise<{ id: string } | null>
  onCreateDiverge: () => Promise<{ id: string } | null>
  initialMarketplaceUnloadId?: string | null
  onInitialMarketplaceUnloadOpened?: () => void
  addressStorageEnabled?: boolean
}

export function FfSuppliesShipmentsPage({
  pageVariant = 'supplies',
  busy,
  error,
  infoNotice,
  onDismissInfoNotice,
  token,
  sellers,
  productPicklist,
  onRefreshFfSupplyExtras,
  inboundSummaries,
  outboundSummaries,
  marketplaceUnloadSummaries,
  discrepancyActSummaries,
  onOpenInbound,
  onOpenOutbound,
  onCreateMpShipment,
  onCreateDiverge,
  initialMarketplaceUnloadId = null,
  onInitialMarketplaceUnloadOpened,
  addressStorageEnabled = true,
}: Props) {
  const [searchParams, setSearchParams] = useSearchParams()
  const isMpShipmentsPage = pageVariant === 'mp-shipments'
  const [kind, setKind] = useState<QuickFilterKind>(isMpShipmentsPage ? 'marketplace_unload' : 'all')
  const [sellerFilter, setSellerFilter] = useState<string>('all')
  const [mpCreateSellerId, setMpCreateSellerId] = useState<string>('')
  const [mpCreateMarketplace, setMpCreateMarketplace] = useState<'wb' | 'ozon'>('wb')
  const [sortKey, setSortKey] = useState<'planned_desc' | 'planned_asc' | 'created_desc' | 'created_asc'>(
    'created_desc',
  )

  const [docModal, setDocModal] = useState<null | 'marketplace_unload' | 'discrepancy_act'>(null)
  const [docModalId, setDocModalId] = useState<string | null>(null)
  const [mpUnloadTab, setMpUnloadTab] = useState<MpUnloadTab>('plan')
  const [packagingTask, setPackagingTask] = useState<PackagingTask | null>(null)
  const [packagingTaskError, setPackagingTaskError] = useState<string | null>(null)
  const [modalBusy, setModalBusy] = useState(false)
  const [modalError, setModalError] = useState<string | null>(null)
  const [unloadDetail, setUnloadDetail] = useState<MarketplaceUnloadDetail | null>(null)
  const [divergeDetail, setDivergeDetail] = useState<DiscrepancyActDetail | null>(null)
  const [lineProductId, setLineProductId] = useState<string>('')
  const [lineQty, setLineQty] = useState<string>('1')
  const [boxPreset, setBoxPreset] = useState<'60_40_40' | '30_20_30'>('60_40_40')
  const [boxBatchCount, setBoxBatchCount] = useState<string>('1')
  const [scanBarcode, setScanBarcode] = useState<string>('')
  const [inboundRefLines, setInboundRefLines] = useState<
    { id: string; product_id: string; sku_code: string; product_name: string }[]
  >([])
  const [selectedInboundLineId, setSelectedInboundLineId] = useState<string>('')
  const [warehouseAvailableProductPicklist, setWarehouseAvailableProductPicklist] = useState<
    AvailableProductPick[]
  >([])

  const docProductPicklist =
    docModal === 'marketplace_unload' ? warehouseAvailableProductPicklist : productPicklist
  const [wbMpWarehouses, setWbMpWarehouses] = useState<{ wb_warehouse_id: number; name: string }[]>([])
  const [wbMpWarehousesBusy, setWbMpWarehousesBusy] = useState(false)
  const [mpPickerOpen, setMpPickerOpen] = useState(false)
  const [mpLineBarcodeScan, setMpLineBarcodeScan] = useState('')
  const [mpShipConfirmOpen, setMpShipConfirmOpen] = useState(false)
  const [mpCancelConfirmOpen, setMpCancelConfirmOpen] = useState(false)
  const [mpAttachConfirmOpen, setMpAttachConfirmOpen] = useState(false)
  const [mpAttachOverPlanOpen, setMpAttachOverPlanOpen] = useState(false)
  const [pendingAttachBarcode, setPendingAttachBarcode] = useState<string | null>(null)
  const mpCatalogSellerId = unloadDetail?.seller_id ?? null
  const { catalog, catalogById, getDisplayMeta, reload: reloadWbCatalog } = useWbProductCatalog(
    token,
    docModal === 'marketplace_unload',
    mpCatalogSellerId,
  )
  const [confirmDate, setConfirmDate] = useState<string>('')
  const [boxMenuAnchor, setBoxMenuAnchor] = useState<null | HTMLElement>(null)
  const [boxMenuTargetId, setBoxMenuTargetId] = useState<string | null>(null)
  const [boxAddDialogBoxId, setBoxAddDialogBoxId] = useState<string | null>(null)
  const [boxAddSuccessMsg, setBoxAddSuccessMsg] = useState<string | null>(null)
  const [boxImportOpen, setBoxImportOpen] = useState(false)
  const mpTabInitForRef = useRef<string | null>(null)
  const docDetailRequests = useRef(createLatestRequestSequence())
  // Пункт 2 итерации 2026-08-14: статус документа не должен меняться молча
  // (например «Утверждено» → «На сборке» как побочный эффект скана/создания короба).
  const prevMpStatusRef = useRef<{ id: string; status: string } | null>(null)
  const [statusChangeMsg, setStatusChangeMsg] = useState<string | null>(null)

  const authHeaders = useMemo(
    () => (token ? { Authorization: `Bearer ${token}` } : null),
    [token],
  )

  useEffect(() => {
    if (sellers.length === 0) {
      setMpCreateSellerId('')
      return
    }
    if (mpCreateSellerId && sellers.some((s) => s.id === mpCreateSellerId)) {
      return
    }
    setMpCreateSellerId(sellers[0]!.id)
  }, [sellers, mpCreateSellerId])

  const loadWbMpWarehouses = useCallback(async () => {
    if (!token || !authHeaders) {
      setWbMpWarehouses([])
      return
    }
    setWbMpWarehousesBusy(true)
    try {
      const res = await fetch(apiUrl('/operations/wb-mp-warehouses'), { headers: authHeaders })
      if (!res.ok) {
        setWbMpWarehouses([])
        return
      }
      const rows = (await res.json()) as { wb_warehouse_id: number; name: string }[]
      setWbMpWarehouses(rows.map((r) => ({ wb_warehouse_id: r.wb_warehouse_id, name: r.name })))
    } catch {
      setWbMpWarehouses([])
    } finally {
      setWbMpWarehousesBusy(false)
    }
  }, [token, authHeaders])

  const loadDocDetail = useCallback(async () => {
    if (!token || !authHeaders || !docModal || !docModalId) {
      setUnloadDetail(null)
      setDivergeDetail(null)
      setWarehouseAvailableProductPicklist([])
      return
    }
    // Номер берём ПОСЛЕ проверки. Раньше его брал и холостой вызов, который тут
    // же выходил, — и этим обесценивал уже летящий настоящий запрос: ответ
    // приходил с кодом 200, но отбрасывался как устаревший, и окно документа
    // оставалось пустым навсегда. Так ломалось «Завершить подбор».
    const docDetailRequestId = docDetailRequests.current.next()
    setModalBusy(true)
    setModalError(null)
    try {
      if (docModal === 'marketplace_unload') {
        const res = await fetch(apiUrl(`/operations/marketplace-unload-requests/${docModalId}`), {
          headers: authHeaders,
        })
        if (!docDetailRequests.current.isLatest(docDetailRequestId)) {
          return
        }
        if (!res.ok) {
          const message = await readApiErrorMessage(res)
          if (docDetailRequests.current.isLatest(docDetailRequestId)) {
            setModalError(message)
            setUnloadDetail(null)
          }
          return
        }
        const j = (await res.json()) as {
          id: string
          document_number?: string | null
          display_number?: string | null
          public_number?: string | null
          human_number?: string | null
          warehouse_id: string
          warehouse_name: string
          status: string
          ff_modified?: boolean
          seller_id?: string | null
          seller_name?: string | null
          marketplace?: string
          wb_mp_warehouse_id?: number | null
          planned_shipment_date?: string | null
          created_at?: string
          lines: {
            id: string
            product_id: string
            sku_code: string
            product_name: string
            quantity: number
            picked_qty?: number
            has_discrepancy?: boolean
          }[]
          boxes?: {
            id: string
            box_preset: string
            internal_barcode?: string | null
            closed_at: string | null
            lines: {
              id: string
              product_id: string
              sku_code: string
              product_name: string
              quantity: number
            }[]
          }[]
          pick_allocations?: {
            id: string
            product_id: string
            sku_code: string
            product_name: string
            storage_location_id: string
            location_code: string
            quantity: number
          }[]
          linked_packaging_task?: {
            task_id: string
            status: string
            qty_done: number
            qty_total: number
            is_complete: boolean
          } | null
        }
        if (!docDetailRequests.current.isLatest(docDetailRequestId)) {
          return
        }
        const prevStatusInfo = prevMpStatusRef.current
        if (prevStatusInfo && prevStatusInfo.id === j.id && prevStatusInfo.status !== j.status) {
          setStatusChangeMsg(`Статус документа изменился: «${statusRu(prevStatusInfo.status)}» → «${statusRu(j.status)}».`)
        }
        prevMpStatusRef.current = { id: j.id, status: j.status }
        setUnloadDetail({
          id: j.id,
          document_number: j.document_number ?? null,
          display_number: j.display_number ?? null,
          public_number: j.public_number ?? null,
          human_number: j.human_number ?? null,
          warehouse_id: j.warehouse_id,
          warehouse_name: j.warehouse_name,
          status: j.status,
          ff_modified: Boolean(j.ff_modified),
          seller_id: j.seller_id ?? null,
          seller_name: j.seller_name ?? null,
          marketplace: j.marketplace ?? 'wb',
          wb_mp_warehouse_id: j.wb_mp_warehouse_id ?? null,
          planned_shipment_date: j.planned_shipment_date ?? null,
          created_at: j.created_at ?? null,
          lines: j.lines.map((ln) => ({
            id: ln.id,
            product_id: ln.product_id,
            sku_code: ln.sku_code,
            product_name: ln.product_name,
            quantity: ln.quantity,
            picked_qty: ln.picked_qty ?? 0,
            has_discrepancy: Boolean(ln.has_discrepancy),
            inbound_intake_line_id: null,
          })),
          boxes: (j.boxes ?? []).map((b) => ({
            id: b.id,
            box_preset: b.box_preset,
            internal_barcode: b.internal_barcode ?? null,
            closed_at: b.closed_at,
            lines: (b.lines ?? []).map((ln) => ({
              id: ln.id,
              product_id: ln.product_id,
              sku_code: ln.sku_code,
              product_name: ln.product_name,
              quantity: ln.quantity,
            })),
          })),
          pick_allocations: (j.pick_allocations ?? []).map((a) => ({
            id: a.id,
            product_id: a.product_id,
            sku_code: a.sku_code,
            product_name: a.product_name,
            storage_location_id: a.storage_location_id,
            location_code: a.location_code,
            quantity: a.quantity,
          })),
          linked_packaging_task: j.linked_packaging_task ?? null,
        })
        setConfirmDate(j.planned_shipment_date ?? '')
        const stockParams = new URLSearchParams({ warehouse_id: j.warehouse_id })
        if (j.seller_id) {
          stockParams.set('seller_id', j.seller_id)
        }
        stockParams.set('exclude_request_id', j.id)
        // Эндпоинт требует warehouse_id и seller_id: без seller_id он отвечает 422
        // seller_id_required, а без warehouse_id в запрос уходит строка "null".
        // У свежесозданной отгрузки этих полей может не быть — тогда не стучимся вовсе,
        // иначе 422 превращается в «пустой список» и выглядит как отсутствие товара.
        const stockRes =
          j.warehouse_id && j.seller_id
            ? await fetch(
                apiUrl(
                  `/operations/marketplace-unload-requests/available-products?${stockParams.toString()}`,
                ),
                { headers: authHeaders },
              )
            : null
        if (!docDetailRequests.current.isLatest(docDetailRequestId)) {
          return
        }
        if (stockRes && stockRes.ok) {
          const stockRows = (await stockRes.json()) as {
            product_id: string
            sku_code: string
            product_name: string
            available: number
          }[]
          if (!docDetailRequests.current.isLatest(docDetailRequestId)) {
            return
          }
          setWarehouseAvailableProductPicklist(
            stockRows
              .filter((row) => row.available > 0)
              .map((row) => ({
                id: row.product_id,
                sku_code: row.sku_code,
                name: row.product_name,
                available: row.available,
              })),
          )
        } else {
          // Раньше сбой запроса молча давал пустой список, и это выглядело как «нет остатка».
          // Отличить поломку от честного нуля было невозможно — теперь ошибка видна.
          setWarehouseAvailableProductPicklist([])
          setModalError(
            stockRes
              ? `Не удалось получить остатки для отгрузки (${stockRes.status}). Список товаров может быть пустым не потому, что товара нет.`
              : 'Список товаров не собрать: у отгрузки не заданы склад и селлер. Заполните их и откройте документ заново.',
          )
        }
        setDivergeDetail(null)
      } else {
        setWarehouseAvailableProductPicklist([])
        const res = await fetch(apiUrl(`/operations/discrepancy-acts/${docModalId}`), {
          headers: authHeaders,
        })
        if (!docDetailRequests.current.isLatest(docDetailRequestId)) {
          return
        }
        if (!res.ok) {
          const message = await readApiErrorMessage(res)
          if (docDetailRequests.current.isLatest(docDetailRequestId)) {
            setModalError(message)
            setDivergeDetail(null)
          }
          return
        }
        const j = (await res.json()) as {
          id: string
          status: string
          inbound_intake_request_id: string | null
          lines: {
            id: string
            product_id: string
            sku_code: string
            product_name: string
            quantity: number
            inbound_intake_line_id?: string | null
          }[]
        }
        if (!docDetailRequests.current.isLatest(docDetailRequestId)) {
          return
        }
        setDivergeDetail({
          id: j.id,
          status: j.status,
          inbound_intake_request_id: j.inbound_intake_request_id,
          lines: j.lines.map((ln) => ({
            id: ln.id,
            product_id: ln.product_id,
            sku_code: ln.sku_code,
            product_name: ln.product_name,
            quantity: ln.quantity,
            inbound_intake_line_id: ln.inbound_intake_line_id ?? null,
          })),
        })
        setUnloadDetail(null)
      }
    } catch (e) {
      if (docDetailRequests.current.isLatest(docDetailRequestId)) {
        setModalError(e instanceof Error ? e.message : 'Не удалось загрузить документ.')
        setUnloadDetail(null)
        setDivergeDetail(null)
      }
    } finally {
      if (docDetailRequests.current.isLatest(docDetailRequestId)) {
        setModalBusy(false)
      }
    }
  }, [token, authHeaders, docModal, docModalId])

  useEffect(() => {
    void loadDocDetail()
  }, [loadDocDetail])

  useEffect(() => {
    if (!initialMarketplaceUnloadId) {
      return
    }
    setUnloadDetail(null)
    setDivergeDetail(null)
    setModalError(null)
    setSelectedInboundLineId('')
    setLineProductId('')
    setDocModal('marketplace_unload')
    setDocModalId(initialMarketplaceUnloadId)
    onInitialMarketplaceUnloadOpened?.()
  }, [initialMarketplaceUnloadId, onInitialMarketplaceUnloadOpened])

  useEffect(() => {
    const openMp = searchParams.get('open_mp')
    if (!openMp || !isMpShipmentsPage) {
      return
    }
    // Тот же документ уже открыт: так бывает после «Завершить подбор» —
    // экран подбора просит список открыть документ, из которого сам и запущен.
    // Обнулять данные тут нельзя: идентификатор не меняется, перезагрузка не
    // запустится, и окно останется пустым. Только убираем параметр из адреса.
    if (docModalId === openMp && docModal === 'marketplace_unload') {
      const cleaned = new URLSearchParams(searchParams)
      cleaned.delete('open_mp')
      setSearchParams(cleaned, { replace: true })
      return
    }
    setUnloadDetail(null)
    setDivergeDetail(null)
    setModalError(null)
    setDocModal('marketplace_unload')
    setDocModalId(openMp)
    // Параметр НЕ стираем: пока окно открыто, документ живёт в адресе, и
    // обновление страницы возвращает оператора в тот же документ, а не в журнал.
  }, [docModal, docModalId, isMpShipmentsPage, searchParams, setSearchParams])

  useEffect(() => {
    if (docModal !== 'marketplace_unload' || docModalId == null) {
      return
    }
    void loadWbMpWarehouses()
  }, [docModal, docModalId, loadWbMpWarehouses])

  useEffect(() => {
    if (!token || !authHeaders || docModal !== 'discrepancy_act' || !divergeDetail?.inbound_intake_request_id) {
      setInboundRefLines([])
      setSelectedInboundLineId('')
      return
    }
    const rid = divergeDetail.inbound_intake_request_id
    void (async () => {
      try {
        const res = await fetch(apiUrl(`/operations/inbound-intake-requests/${rid}`), {
          headers: authHeaders,
        })
        if (!res.ok) {
          setInboundRefLines([])
          return
        }
        const j = (await res.json()) as {
          lines: { id: string; product_id: string; sku_code: string; product_name: string }[]
        }
        setInboundRefLines(
          j.lines.map((ln) => ({
            id: ln.id,
            product_id: ln.product_id,
            sku_code: ln.sku_code,
            product_name: ln.product_name,
          })),
        )
      } catch {
        setInboundRefLines([])
      }
    })()
  }, [token, authHeaders, docModal, divergeDetail?.inbound_intake_request_id])

  const closeDocModal = () => {
    docDetailRequests.current.invalidate()
    // Документ закрыт — убираем его из адреса, иначе он откроется снова при
    // следующем заходе по той же ссылке.
    if (searchParams.get('open_mp')) {
      const cleaned = new URLSearchParams(searchParams)
      cleaned.delete('open_mp')
      setSearchParams(cleaned, { replace: true })
    }
    setDocModal(null)
    setDocModalId(null)
    setUnloadDetail(null)
    setDivergeDetail(null)
    setModalError(null)
    setLineProductId('')
    setLineQty('1')
    setBoxPreset('60_40_40')
    setScanBarcode('')
    setInboundRefLines([])
    setSelectedInboundLineId('')
    setWbMpWarehouses([])
    setMpPickerOpen(false)
    setMpLineBarcodeScan('')
    setMpUnloadTab('plan')
    setPackagingTask(null)
    setPackagingTaskError(null)
    mpTabInitForRef.current = null
  }

  const setWbWarehouseForUnload = async (wbMpWarehouseId: number) => {
    if (!token || !authHeaders || docModal !== 'marketplace_unload' || !docModalId) {
      return
    }
    setModalBusy(true)
    setModalError(null)
    try {
      const res = await fetch(apiUrl(`/operations/marketplace-unload-requests/${docModalId}`), {
        method: 'PATCH',
        headers: {
          ...authHeaders,
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ wb_mp_warehouse_id: wbMpWarehouseId }),
      })
      if (!res.ok) {
        setModalError(await readApiErrorMessage(res))
        return
      }
      await loadDocDetail()
      await onRefreshFfSupplyExtras()
      await loadWbMpWarehouses()
    } catch (e) {
      setModalError(e instanceof Error ? e.message : 'Не удалось сохранить склад WB.')
    } finally {
      setModalBusy(false)
    }
  }

  const patchMpPlannedDate = async (iso: string | null) => {
    if (!token || !authHeaders || docModal !== 'marketplace_unload' || !docModalId || !iso) {
      return
    }
    setConfirmDate(iso)
    setModalBusy(true)
    setModalError(null)
    try {
      const res = await fetch(apiUrl(`/operations/marketplace-unload-requests/${docModalId}`), {
        method: 'PATCH',
        headers: { ...authHeaders, 'Content-Type': 'application/json' },
        body: JSON.stringify({ planned_shipment_date: iso }),
      })
      if (!res.ok) {
        setModalError(await readApiErrorMessage(res))
        await loadDocDetail()
        return
      }
      await loadDocDetail()
      await onRefreshFfSupplyExtras()
    } catch (e) {
      setModalError(e instanceof Error ? e.message : 'Не удалось сохранить дату отгрузки.')
    } finally {
      setModalBusy(false)
    }
  }

  const createAndOpenMpShipment = async () => {
    if (!mpCreateSellerId) {
      setModalError('Выберите селлера (ИП) для отгрузки.')
      return
    }
    const created = await onCreateMpShipment(mpCreateSellerId, mpCreateMarketplace)
    if (!created?.id) {
      return
    }
    setUnloadDetail(null)
    setDivergeDetail(null)
    setModalError(null)
    setSelectedInboundLineId('')
    setLineProductId('')
    setDocModal('marketplace_unload')
    setDocModalId(created.id)
  }

  const createAndOpenDiverge = async () => {
    const created = await onCreateDiverge()
    if (!created?.id) {
      return
    }
    setUnloadDetail(null)
    setDivergeDetail(null)
    setModalError(null)
    setSelectedInboundLineId('')
    setLineProductId('')
    setDocModal('discrepancy_act')
    setDocModalId(created.id)
  }

  const createBox = async () => {
    if (
      !token ||
      !authHeaders ||
      docModal !== 'marketplace_unload' ||
      !docModalId ||
      !canUseMpBoxOperationalControls
    ) {
      return
    }
    const count = Number(boxBatchCount)
    if (!Number.isInteger(count) || count < 1 || count > 50) {
      setModalError('Укажите количество коробов от 1 до 50.')
      return
    }
    setModalBusy(true)
    setModalError(null)
    try {
      const res = await fetch(
        apiUrl(`/operations/marketplace-unload-requests/${docModalId}/boxes/batch`),
        {
          method: 'POST',
          headers: {
            ...authHeaders,
            'Content-Type': 'application/json',
          },
          body: JSON.stringify({ count, box_preset: boxPreset }),
        },
      )
      if (!res.ok) {
        setModalError(await readApiErrorMessage(res))
        return
      }
      setScanBarcode('')
      await loadDocDetail()
      await loadPackagingTask()
      await onRefreshFfSupplyExtras()
    } catch (e) {
      setModalError(
        e instanceof Error ? e.message : 'Не удалось создать короб(а).',
      )
    } finally {
      setModalBusy(false)
    }
  }

  const attachBoxByBarcode = async (
    barcode: string,
    allowOverPlan: boolean,
  ): Promise<'ok' | 'over_plan' | 'error'> => {
    if (
      !token ||
      !authHeaders ||
      docModal !== 'marketplace_unload' ||
      !docModalId ||
      !canUseMpBoxOperationalControls
    ) {
      return 'error'
    }
    setModalBusy(true)
    setModalError(null)
    try {
      const attachRes = await fetch(
        apiUrl(`/operations/marketplace-unload-requests/${docModalId}/boxes/attach`),
        {
          method: 'POST',
          headers: { ...authHeaders, 'Content-Type': 'application/json' },
          body: JSON.stringify({
            barcode,
            box_preset: boxPreset,
            allow_over_plan: allowOverPlan,
          }),
        },
      )
      if (attachRes.ok) {
        setScanBarcode('')
        await loadDocDetail()
        await loadPackagingTask()
        await onRefreshFfSupplyExtras()
        return 'ok'
      }
      const attachText = await attachRes.text()
      let attachDetail: string | null = null
      try {
        const attachBody = JSON.parse(attachText) as { detail?: unknown }
        attachDetail =
          typeof attachBody.detail === 'string' ? attachBody.detail : null
      } catch {
        attachDetail = null
      }
      if (attachDetail === 'plan_limit_exceeded' && !allowOverPlan) {
        return 'over_plan'
      }
      setModalError(
        attachDetail ?? attachText.slice(0, 200) ?? 'Не удалось добавить короб.',
      )
      return 'error'
    } catch (e) {
      setModalError(
        e instanceof Error ? e.message : 'Не удалось добавить короб.',
      )
      return 'error'
    } finally {
      setModalBusy(false)
    }
  }

  const requestAttachBoxScan = (rawInput?: string) => {
    if (!canUseMpBoxOperationalControls) {
      return
    }
    const raw = (rawInput ?? scanBarcode).trim()
    if (!raw) {
      setModalError('Введите штрихкод готового короба (WHB-…).')
      return
    }
    if (!raw.startsWith('WHB-') && !raw.startsWith('INB-')) {
      setModalError(
        addressStorageEnabled ? 'На этой строке сканируют только готовый короб (WHB-…). Для ячейки или товара откройте «Добавить товары» у короба.' : 'На этой строке сканируют только готовый короб (WHB-…). Для товара откройте «Добавить товары» у короба.',
      )
      return
    }
    setModalError(null)
    setPendingAttachBarcode(raw)
    setMpAttachConfirmOpen(true)
  }

  const confirmAttachBox = async () => {
    setMpAttachConfirmOpen(false)
    const barcode = pendingAttachBarcode
    if (!barcode) {
      return
    }
    const result = await attachBoxByBarcode(barcode, false)
    if (result === 'over_plan') {
      setMpAttachOverPlanOpen(true)
      return
    }
    setPendingAttachBarcode(null)
  }

  const confirmAttachBoxOverPlan = async () => {
    setMpAttachOverPlanOpen(false)
    const barcode = pendingAttachBarcode
    if (!barcode) {
      return
    }
    setPendingAttachBarcode(null)
    await attachBoxByBarcode(barcode, true)
  }

  const doCollectScan = async () => {
    requestAttachBoxScan()
  }

  const boxById = useMemo(() => {
    const map = new Map<string, MarketplaceUnloadBox>()
    for (const b of unloadDetail?.boxes ?? []) {
      map.set(b.id, b)
    }
    return map
  }, [unloadDetail?.boxes])

  const openBoxMenu = (event: MouseEvent<HTMLElement>, boxId: string) => {
    event.stopPropagation()
    if (!canUseMpBoxDestructiveControls) {
      closeBoxMenu()
      return
    }
    setBoxMenuAnchor(event.currentTarget)
    setBoxMenuTargetId(boxId)
  }

  const closeBoxMenu = () => {
    setBoxMenuAnchor(null)
    setBoxMenuTargetId(null)
  }

  const [printBoxTarget, setPrintBoxTarget] = useState<MarketplaceUnloadBox | null>(null)

  const requestPrintBoxBarcode = (box: MarketplaceUnloadBox) => {
    const barcode = box.internal_barcode?.trim()
    if (!barcode) {
      setModalError('У короба нет штрихкода.')
      return
    }
    setPrintBoxTarget(box)
  }

  const confirmPrintBoxBarcode = (size: LabelSize) => {
    const box = printBoxTarget
    setPrintBoxTarget(null)
    const barcode = box?.internal_barcode?.trim()
    if (!box || !barcode) {
      return
    }
    printBarcodeLabel({
      title: 'Короб отгрузки',
      barcode,
      barcodeDataUrl: renderBarcodeDataUrl(barcode, { variant: 'internalBox' }),
      labelSize: size,
      layout: 'internalBox',
    })
  }

  const copyBox = async (boxId: string) => {
    if (
      !token ||
      !authHeaders ||
      docModal !== 'marketplace_unload' ||
      !docModalId ||
      !canUseMpBoxDestructiveControls
    ) {
      return
    }
    closeBoxMenu()
    setModalBusy(true)
    setModalError(null)
    try {
      const res = await fetch(
        apiUrl(`/operations/marketplace-unload-requests/${docModalId}/boxes/${boxId}/copy`),
        { method: 'POST', headers: authHeaders },
      )
      if (!res.ok) {
        setModalError(await readApiErrorMessage(res))
        return
      }
      await loadDocDetail()
      await loadPackagingTask()
      await onRefreshFfSupplyExtras()
    } catch (e) {
      setModalError(e instanceof Error ? e.message : 'Не удалось скопировать короб.')
    } finally {
      setModalBusy(false)
    }
  }

  const deleteBox = async (boxId: string) => {
    if (
      !token ||
      !authHeaders ||
      docModal !== 'marketplace_unload' ||
      !docModalId ||
      !canUseMpBoxDestructiveControls
    ) {
      return
    }
    closeBoxMenu()
    setModalBusy(true)
    setModalError(null)
    try {
      const res = await fetch(
        apiUrl(`/operations/marketplace-unload-requests/${docModalId}/boxes/${boxId}`),
        { method: 'DELETE', headers: authHeaders },
      )
      if (!res.ok) {
        setModalError(await readApiErrorMessage(res))
        return
      }
      await loadDocDetail()
      await loadPackagingTask()
      await onRefreshFfSupplyExtras()
    } catch (e) {
      setModalError(e instanceof Error ? e.message : 'Не удалось удалить короб.')
    } finally {
      setModalBusy(false)
    }
  }

  const removeBoxLine = async (boxId: string, lineId: string) => {
    if (
      !token ||
      !authHeaders ||
      docModal !== 'marketplace_unload' ||
      !docModalId ||
      !canUseMpBoxDestructiveControls
    ) {
      return
    }
    setModalBusy(true)
    setModalError(null)
    try {
      const res = await fetch(
        apiUrl(
          `/operations/marketplace-unload-requests/${docModalId}/boxes/${boxId}/lines/${lineId}/remove`,
        ),
        {
          method: 'POST',
          headers: { ...authHeaders, 'Content-Type': 'application/json' },
          body: JSON.stringify({}),
        },
      )
      if (!res.ok) {
        setModalError(await readApiErrorMessage(res))
        return
      }
      await loadDocDetail()
      await onRefreshFfSupplyExtras()
    } catch (e) {
      setModalError(e instanceof Error ? e.message : 'Не удалось убрать товар из короба.')
    } finally {
      setModalBusy(false)
    }
  }

  const canUseMpBoxDestructiveControls =
    docModal === 'marketplace_unload' && unloadDetail?.status === 'draft'
  const canUseMpBoxOperationalControls =
    docModal === 'marketplace_unload' &&
    (unloadDetail?.status === 'confirmed' || unloadDetail?.status === 'collecting')

  useEffect(() => {
    if (!canUseMpBoxDestructiveControls) {
      setBoxMenuAnchor(null)
      setBoxMenuTargetId(null)
    }
    if (!canUseMpBoxOperationalControls) {
      setBoxAddDialogBoxId(null)
      setBoxImportOpen(false)
      setPendingAttachBarcode(null)
      setMpAttachConfirmOpen(false)
      setMpAttachOverPlanOpen(false)
    }
  }, [canUseMpBoxDestructiveControls, canUseMpBoxOperationalControls])

  const mpVisibleBoxes = useMemo(() => {
    const boxes = unloadDetail?.boxes ?? []
    return boxes.filter((box) => box.lines.length > 0 || Boolean(box.internal_barcode?.trim()))
  }, [unloadDetail?.boxes])

  const mpBoxesWithLines = useMemo(
    () => mpVisibleBoxes.filter((box) => box.lines.length > 0),
    [mpVisibleBoxes],
  )

  // MPU-04б (18.08): заказчик увидел свёрнутый блок «Короба» и не понял, что там вообще
  // есть содержимое. Счётчик в заголовке — сколько коробов и сколько единиц в них —
  // виден без раскрытия аккордеона.
  const mpBoxesSummary = useMemo(() => {
    const boxCount = mpVisibleBoxes.length
    const unitCount = mpVisibleBoxes.reduce(
      (sum, box) => sum + box.lines.reduce((lineSum, ln) => lineSum + ln.quantity, 0),
      0,
    )
    return { boxCount, unitCount }
  }, [mpVisibleBoxes])

  const mpBoxPanelSx = (hasLines: boolean) => ({
    borderRadius: 1,
    overflow: 'hidden',
    bgcolor: hasLines ? 'background.paper' : 'action.hover',
  })

  const mpBoxHeaderSx = {
    display: 'flex',
    alignItems: { xs: 'stretch', sm: 'flex-start' },
    justifyContent: 'space-between',
    gap: 1,
    flexWrap: 'wrap',
    px: 1.25,
    py: 1,
    bgcolor: 'action.hover',
  }

  const mpBoxBodySx = {
    px: 1.25,
    py: 1,
    bgcolor: 'background.paper',
  }

  const mpBoxActionsSx = {
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'flex-end',
    gap: 0.5,
    flexWrap: 'wrap' as const,
    minWidth: 0,
  }

  const mpBoxTableWrapSx = {
    mt: 1,
    maxWidth: '100%',
    overflowX: 'auto',
  }

  const renderBoxActions = (box: MarketplaceUnloadBox) => {
    const totalQty = box.lines.reduce((sum, ln) => sum + ln.quantity, 0)
    return (
      <Stack direction="row" spacing={0.5} sx={mpBoxActionsSx}>
        {canUseMpBoxOperationalControls ? (
          <>
            <Button
              size="small"
              variant="outlined"
              disabled={modalBusy}
              onClick={() => setBoxAddDialogBoxId(box.id)}
              data-testid={`ff-mp-box-add-products-${box.id}`}
            >
              Наполнить
            </Button>
          </>
        ) : null}
        {canUseMpBoxDestructiveControls ? (
          <IconButton
            size="small"
            aria-label="Действия с коробом"
            data-testid={`ff-mp-box-menu-${box.id}`}
            disabled={modalBusy}
            onClick={(e) => openBoxMenu(e, box.id)}
          >
            <MoreVertOutlined fontSize="small" />
          </IconButton>
        ) : null}
        <IconButton
          size="small"
          aria-label="Печать ШК короба"
          data-testid={`ff-mp-box-print-${box.id}`}
          disabled={modalBusy || !box.internal_barcode}
          onClick={() => requestPrintBoxBarcode(box)}
        >
          <Typography variant="caption" sx={{ fontWeight: 700 }}>
            ШК
          </Typography>
        </IconButton>
        {canUseMpBoxDestructiveControls ? (
          <IconButton
            size="small"
            aria-label="Удалить пустой короб"
            data-testid={`ff-mp-box-delete-${box.id}`}
            disabled={modalBusy || totalQty > 0}
            onClick={() => void deleteBox(box.id)}
          >
            <DeleteOutlineOutlined fontSize="small" />
          </IconButton>
        ) : null}
      </Stack>
    )
  }

  const renderMpBoxCard = (
    box: MarketplaceUnloadBox,
    boxOrdinal: number,
    tableTestId?: string,
  ) => {
    const boxBarcode = box.internal_barcode?.trim()
    const boxLabel = `Короб ${boxOrdinal}`
    const hasLines = box.lines.length > 0

    return (
      <Paper
        key={box.id}
        variant="outlined"
        sx={mpBoxPanelSx(hasLines)}
        data-testid={`ff-mp-box-row-${box.id}`}
      >
        <Box sx={mpBoxHeaderSx} data-testid={`ff-mp-box-header-${box.id}`}>
          <Box sx={{ minWidth: 0, flex: 1 }}>
            <Typography variant="subtitle2" sx={{ fontWeight: 700, lineHeight: 1.25 }}>
              {boxLabel}
            </Typography>
            {/* Дизайн-разбор 2026-08-16: раньше здесь была одна строка «60_40_40 ·
                WHB-2A67351D829F» — служебный код пресета и штрихкод наравне, человек
                это не читает и не называет вслух. Человеческий размер — основная
                подпись, штрихкод — мелкая техническая строка ниже, для сверки со
                сканером, а не для чтения. */}
            <Typography variant="body2" color="text.secondary" sx={{ minWidth: 0 }}>
              {mpBoxPresetLabel(box.box_preset)}
              {!hasLines ? ' · готов к наполнению' : ''}
            </Typography>
            {boxBarcode ? (
              <Typography
                variant="caption"
                color="text.disabled"
                sx={{ display: 'block', fontFamily: 'ui-monospace, SFMono-Regular, Menlo, monospace' }}
              >
                {boxBarcode}
              </Typography>
            ) : null}
          </Box>
          {renderBoxActions(box)}
        </Box>

        {hasLines ? (
          <Box
            sx={{ ...mpBoxBodySx, ...mpBoxTableWrapSx, mt: 0 }}
            data-testid={tableTestId ?? `ff-mp-box-lines-${box.id}`}
          >
            {/* MPU-07 (18.08): раньше строка товара в коробе была обезличенной —
                артикул/название/число. Заказчик просил ту же строку товара, что и
                везде в системе (фото, ШК, артикул продавца, артикул WB, размер) —
                переиспользуем FfProductLineCells/FfProductTableHeadCells, как на
                вкладке «Товары» этого же экрана (ff-supplies-doc-lines) и в
                диалоге наполнения короба. */}
            <Table size="small" sx={{ tableLayout: 'fixed', width: '100%' }}>
              <TableHead>
                <TableRow>
                  <FfProductTableHeadCells showPrint={false} />
                  <TableCell align="right" sx={{ width: 104 }}>
                    В коробе
                  </TableCell>
                  {canUseMpBoxDestructiveControls ? <TableCell sx={{ width: 40 }} /> : null}
                </TableRow>
              </TableHead>
              <TableBody>
                {box.lines.map((ln) => {
                  const displayMeta = getDisplayMeta(ln.product_id, ln)
                  return (
                    <TableRow key={ln.id}>
                      <FfProductLineCells meta={displayMeta} showPrint={false} />
                      <TableCell align="right">{ln.quantity}</TableCell>
                      {canUseMpBoxDestructiveControls ? (
                        <TableCell align="right">
                          <Tooltip title="Убрать из короба">
                            <IconButton
                              size="small"
                              aria-label="Убрать из короба"
                              data-testid={`ff-mp-box-line-remove-${ln.id}`}
                              disabled={modalBusy}
                              onClick={() => void removeBoxLine(box.id, ln.id)}
                            >
                              <DeleteOutlineOutlined fontSize="small" />
                            </IconButton>
                          </Tooltip>
                        </TableCell>
                      ) : null}
                    </TableRow>
                  )
                })}
              </TableBody>
            </Table>
          </Box>
        ) : null}
      </Paper>
    )
  }

  const mpBoxesOrdered = useMemo(() => {
    const withLines = mpBoxesWithLines
    const empty = mpVisibleBoxes.filter((box) => box.lines.length === 0)
    return [...withLines, ...empty]
  }, [mpBoxesWithLines, mpVisibleBoxes])


  const mpHasDiscrepancy = useMemo(() => {
    if (!unloadDetail || docModal !== 'marketplace_unload') {
      return false
    }
    return unloadDetail.lines.some((ln) => (ln.picked_qty ?? 0) !== ln.quantity)
  }, [unloadDetail, docModal])

  const shipMpUnload = async (acknowledgeDiscrepancy = false) => {
    if (!token || !authHeaders || !docModalId) {
      return
    }
    setModalBusy(true)
    setModalError(null)
    try {
      const res = await fetch(
        apiUrl(`/operations/marketplace-unload-requests/${docModalId}/ship`),
        {
          method: 'POST',
          headers: { ...authHeaders, 'Content-Type': 'application/json' },
          body: JSON.stringify({ acknowledge_discrepancy: acknowledgeDiscrepancy }),
        },
      )
      if (!res.ok) {
        const msg = await readApiErrorMessage(res)
        if (msg.includes('distribution_incomplete')) {
          setModalError(
            acknowledgeDiscrepancy
              ? 'Не удалось завершить: нет товаров в коробах или нужно подтверждение расхождения.'
              : 'План и факт не совпадают. Подтвердите расхождение или скорректируйте короба.',
          )
        } else {
          setModalError(msg)
        }
        return
      }
      setMpShipConfirmOpen(false)
      await loadDocDetail()
      await onRefreshFfSupplyExtras()
    } catch (e) {
      setModalError(e instanceof Error ? e.message : 'Не удалось завершить отгрузку.')
    } finally {
      setModalBusy(false)
    }
  }

  const requestShipMpUnload = () => {
    if (!token || !authHeaders || !docModalId) {
      return
    }
    if ((mpCollectSummary?.distributed ?? 0) < 1) {
      setModalError('Добавьте товары в короба перед отгрузкой.')
      return
    }
    if (!mpPackagingComplete) {
      setModalError('Завершите упаковку перед отгрузкой.')
      return
    }
    if (mpHasDiscrepancy) {
      setMpShipConfirmOpen(true)
      return
    }
    void shipMpUnload(false)
  }

  const cancelMpUnload = async () => {
    if (!token || !authHeaders || !docModalId) {
      return
    }
    setModalBusy(true)
    setModalError(null)
    try {
      const res = await fetch(
        apiUrl(`/operations/marketplace-unload-requests/${docModalId}/cancel`),
        { method: 'POST', headers: authHeaders },
      )
      if (!res.ok) {
        setModalError(await readApiErrorMessage(res))
        return
      }
      setMpCancelConfirmOpen(false)
      await loadDocDetail()
      await onRefreshFfSupplyExtras()
    } catch (e) {
      setModalError(e instanceof Error ? e.message : 'Не удалось отменить отгрузку.')
    } finally {
      setModalBusy(false)
    }
  }

  const submitDoc = async () => {
    if (!token || !authHeaders || !docModal || !docModalId) {
      return
    }
    setModalBusy(true)
    setModalError(null)
    try {
      if (docModal === 'marketplace_unload') {
        if (!confirmDate.trim()) {
          setModalError('Укажите дату отгрузки на маркетплейс.')
          setModalBusy(false)
          return
        }
        const res = await fetch(
          apiUrl(`/operations/marketplace-unload-requests/${docModalId}/confirm`),
          {
            method: 'POST',
            headers: { ...authHeaders, 'Content-Type': 'application/json' },
            body: JSON.stringify({ planned_shipment_date: confirmDate.trim() }),
          },
        )
        if (!res.ok) {
          setModalError(await readApiErrorMessage(res))
          return
        }
      } else {
        const res = await fetch(apiUrl(`/operations/discrepancy-acts/${docModalId}/submit`), {
          method: 'POST',
          headers: authHeaders,
        })
        if (!res.ok) {
          setModalError(await readApiErrorMessage(res))
          return
        }
      }
      await loadDocDetail()
      await onRefreshFfSupplyExtras()
    } catch (e) {
      setModalError(e instanceof Error ? e.message : 'Не удалось оформить документ.')
    } finally {
      setModalBusy(false)
    }
  }

  const resolveDiscrepancyAct = async (action: 'approve' | 'reject') => {
    if (!token || !authHeaders || docModal !== 'discrepancy_act' || !docModalId) {
      return
    }
    setModalBusy(true)
    setModalError(null)
    try {
      const res = await fetch(
        apiUrl(`/operations/discrepancy-acts/${docModalId}/${action}`),
        {
          method: 'POST',
          headers: authHeaders,
        },
      )
      if (!res.ok) {
        setModalError(await readApiErrorMessage(res))
        return
      }
      await loadDocDetail()
      await onRefreshFfSupplyExtras()
    } catch (e) {
      setModalError(e instanceof Error ? e.message : 'Не удалось обработать акт.')
    } finally {
      setModalBusy(false)
    }
  }

  const deleteDocLine = async (lineId: string) => {
    if (!token || !authHeaders || !docModal || !docModalId) {
      return
    }
    setModalBusy(true)
    setModalError(null)
    try {
      const path =
        docModal === 'marketplace_unload'
          ? `/operations/marketplace-unload-requests/${docModalId}/lines/${lineId}`
          : `/operations/discrepancy-acts/${docModalId}/lines/${lineId}`
      const res = await fetch(apiUrl(path), {
        method: 'DELETE',
        headers: authHeaders,
      })
      if (!res.ok) {
        setModalError(await readApiErrorMessage(res))
        return
      }
      await loadDocDetail()
      await onRefreshFfSupplyExtras()
    } catch (e) {
      setModalError(e instanceof Error ? e.message : 'Не удалось удалить строку.')
    } finally {
      setModalBusy(false)
    }
  }

  const submitLine = async () => {
    if (!token || !authHeaders || !docModal || !docModalId || !lineProductId) {
      return
    }
    const q = Number(lineQty)
    if (!Number.isInteger(q) || (docModal === 'discrepancy_act' ? q === 0 : q < 1)) {
      setModalError(
        docModal === 'discrepancy_act'
          ? 'Укажите целое расхождение: положительное или отрицательное.'
          : 'Укажите целое количество ≥ 1.',
      )
      return
    }
    setModalBusy(true)
    setModalError(null)
    try {
      const path =
        docModal === 'marketplace_unload'
          ? `/operations/marketplace-unload-requests/${docModalId}/lines`
          : `/operations/discrepancy-acts/${docModalId}/lines`
      const res = await fetch(apiUrl(path), {
        method: 'POST',
        headers: {
          ...authHeaders,
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          product_id: lineProductId,
          quantity: q,
          ...(docModal === 'discrepancy_act' && selectedInboundLineId
            ? { inbound_intake_line_id: selectedInboundLineId }
            : {}),
        }),
      })
      if (!res.ok) {
        setModalError(await readApiErrorMessage(res))
        return
      }
      await loadDocDetail()
      await onRefreshFfSupplyExtras()
      setLineQty('1')
      setSelectedInboundLineId('')
    } catch (e) {
      setModalError(e instanceof Error ? e.message : 'Не удалось добавить строку.')
    } finally {
      setModalBusy(false)
    }
  }

  const sellerOptions = useMemo(() => {
    const s = new Set<string>()
    const sources = isMpShipmentsPage
      ? [marketplaceUnloadSummaries]
      : [inboundSummaries, outboundSummaries, discrepancyActSummaries]
    for (const list of sources) {
      for (const r of list) {
        if ('seller_name' in r && r.seller_name) {
          s.add(r.seller_name)
        }
      }
    }
    return Array.from(s).sort((a, b) => a.localeCompare(b))
  }, [
    isMpShipmentsPage,
    inboundSummaries,
    outboundSummaries,
    marketplaceUnloadSummaries,
    discrepancyActSummaries,
  ])

  const rows = useMemo(() => {
    const all: UnifiedRow[] = isMpShipmentsPage
      ? marketplaceUnloadSummaries.map((r) => ({
          kind: 'marketplace_unload' as const,
          id: r.id,
          documentNumber: formatHumanDocumentNumber(r),
          plannedDate: r.planned_shipment_date ?? null,
          createdAt: r.created_at,
          status: r.status,
          lineCount: r.line_count,
          sellerName: r.seller_name ?? null,
          marketplace: r.marketplace ?? 'wb',
          extraLabel: r.warehouse_name,
          ffModified: Boolean(r.ff_modified),
        }))
      : [
          ...inboundSummaries.map((r) => ({
            kind: 'inbound' as const,
            id: r.id,
            documentNumber: formatHumanDocumentNumber(r),
            plannedDate: r.planned_delivery_date,
            createdAt: r.created_at ?? null,
            status: r.status,
            lineCount: r.line_count,
            sellerName: r.seller_name ?? null,
            marketplace: null,
            extraLabel: null,
            ffModified: false,
          })),
          ...outboundSummaries.map((r) => ({
            kind: 'outbound' as const,
            id: r.id,
            documentNumber: null,
            plannedDate: r.planned_shipment_date ?? r.created_at?.slice(0, 10) ?? null,
            createdAt: r.created_at ?? null,
            status: r.status,
            lineCount: r.line_count,
            sellerName: r.seller_name ?? null,
            marketplace: null,
            extraLabel: null,
            ffModified: false,
          })),
          ...discrepancyActSummaries.map((r) => ({
            kind: 'discrepancy_act' as const,
            id: r.id,
            documentNumber: null,
            plannedDate: null,
            createdAt: r.created_at,
            status: r.status,
            lineCount: r.line_count,
            sellerName: r.seller_name ?? null,
            marketplace: null,
            extraLabel: r.inbound_intake_request_id
              ? `приёмка ${r.inbound_intake_request_id.slice(0, 8)}…`
              : null,
            ffModified: false,
          })),
        ]
    let filtered = isMpShipmentsPage || kind === 'all' ? all : all.filter((x) => x.kind === kind)
    if (sellerFilter !== 'all') {
      filtered = filtered.filter((x) => x.sellerName === sellerFilter)
    }
    const sorted = [...filtered].sort((a, b) => {
      if (sortKey === 'planned_desc') {
        return (b.plannedDate ?? '').localeCompare(a.plannedDate ?? '')
      }
      if (sortKey === 'planned_asc') {
        return (a.plannedDate ?? '').localeCompare(b.plannedDate ?? '')
      }
      if (sortKey === 'created_desc') {
        return (b.createdAt ?? '').localeCompare(a.createdAt ?? '')
      }
      return (a.createdAt ?? '').localeCompare(b.createdAt ?? '')
    })
    return sorted
  }, [
    isMpShipmentsPage,
    inboundSummaries,
    outboundSummaries,
    marketplaceUnloadSummaries,
    discrepancyActSummaries,
    kind,
    sellerFilter,
    sortKey,
  ])

  const docTitle =
    docModal === 'marketplace_unload'
      ? 'Отгрузка на маркетплейс'
      : docModal === 'discrepancy_act'
        ? 'Акт расхождения'
        : ''
  const unloadDisplayNumber = useMemo(
    () => formatHumanDocumentNumber(unloadDetail),
    [unloadDetail],
  )

  const mpDraft = docModal === 'marketplace_unload' && unloadDetail?.status === 'draft'
  const mpSubmitted =
    docModal === 'marketplace_unload' && unloadDetail?.status === 'submitted'
  const mpConfirmed = docModal === 'marketplace_unload' && unloadDetail?.status === 'confirmed'
  const mpCollecting =
    docModal === 'marketplace_unload' && unloadDetail?.status === 'collecting'
  const mpExecutionPhase = mpConfirmed || mpCollecting
  const mpCancellable = mpSubmitted || mpConfirmed || mpCollecting
  const mpPackagingComplete = useMemo(() => {
    const task = unloadDetail?.linked_packaging_task
    if (!task) {
      return false
    }
    return task.status === 'done' || task.is_complete
  }, [unloadDetail?.linked_packaging_task])

  const loadPackagingTask = useCallback(async () => {
    if (!token || !authHeaders || !docModalId || docModal !== 'marketplace_unload') {
      setPackagingTask(null)
      setPackagingTaskError(null)
      return
    }
    if (!unloadDetail?.linked_packaging_task) {
      setPackagingTask(null)
      setPackagingTaskError(null)
      return
    }
    try {
      const res = await fetch(apiUrl(`/operations/packaging-tasks/by-unload/${docModalId}`), {
        headers: authHeaders,
      })
      if (!res.ok) {
        setPackagingTaskError(await readApiErrorMessage(res))
        setPackagingTask(null)
        return
      }
      setPackagingTask((await res.json()) as PackagingTask)
      setPackagingTaskError(null)
    } catch (e) {
      setPackagingTaskError(e instanceof Error ? e.message : 'Не удалось загрузить упаковку.')
      setPackagingTask(null)
    }
  }, [token, authHeaders, docModalId, docModal, unloadDetail?.linked_packaging_task])

  useEffect(() => {
    void loadPackagingTask()
  }, [loadPackagingTask])

  useEffect(() => {
    if (!unloadDetail || docModal !== 'marketplace_unload' || !docModalId) {
      return
    }
    if (mpTabInitForRef.current === docModalId) {
      return
    }
    mpTabInitForRef.current = docModalId
    setMpUnloadTab('plan')
  }, [unloadDetail, docModalId, docModal])

  const mpDateEditable =
    docModal === 'marketplace_unload' &&
    (unloadDetail?.status === 'draft' ||
      unloadDetail?.status === 'submitted' ||
      unloadDetail?.status === 'confirmed')
  const mpCollectSummary = useMemo(() => {
    if (!unloadDetail || docModal !== 'marketplace_unload') {
      return null
    }
    const planned = unloadDetail.lines.reduce((sum, ln) => sum + ln.quantity, 0)
    // MPU-03: ln.picked_qty приходит с бэкенда посчитанным по содержимому коробов
    // (backend/app/api/marketplace_unload_requests.py, _picked_by_product), а подбор
    // с 2026-08-16 короба не трогает вообще — поэтому это поле всегда 0 и счётчик
    // «Подобрано» не сходился с реальным подбором. Настоящий источник — аллокации
    // подбора (unloadDetail.pick_allocations), как и написано в комментарии ниже
    // про «Раньше подпись была...».
    const distributed = unloadDetail.pick_allocations.reduce(
      (sum, alloc) => sum + alloc.quantity,
      0,
    )
    return {
      planned,
      distributed,
      remaining: planned - distributed,
      packed: unloadDetail.linked_packaging_task
        ? `${unloadDetail.linked_packaging_task.qty_done}/${unloadDetail.linked_packaging_task.qty_total}`
        : null,
    }
  }, [unloadDetail, docModal])

  const mpStepEnabled = useCallback(
    (step: MpUnloadTab) => {
      if (!unloadDetail || docModal !== 'marketplace_unload') {
        return false
      }
      if (step === 'plan') {
        return true
      }
      if (step === 'pick') {
        // Подбор открывается после утверждения плана — так требует MPFBO-01.
        return mpSubmitted || mpConfirmed || mpCollecting
      }
      if (step === 'packaging') {
        return Boolean(unloadDetail.linked_packaging_task)
      }
      return false
    },
    [docModal, unloadDetail, mpSubmitted, mpConfirmed, mpCollecting],
  )
  // Соседний шаг вкладок, а не «следующий доступный» — иначе кнопка «Далее» молча
  // перепрыгивает через заблокированный шаг вместо того, чтобы объяснить блокировку
  // (см. mpStepBlockedReason ниже и требование по большим кнопкам переходов 2026-08-17).
  const mpImmediateNextStep = useMemo(() => {
    const currentIdx = mpUnloadSteps.findIndex((step) => step.value === mpUnloadTab)
    if (currentIdx < 0) {
      return null
    }
    return mpUnloadSteps[currentIdx + 1] ?? null
  }, [mpUnloadTab])
  const mpNextStepEnabled = mpImmediateNextStep ? mpStepEnabled(mpImmediateNextStep.value) : false
  /** Тот же текст — и на disabled-вкладке при наведении, и под кнопкой «Далее». */
  const mpStepBlockedReason = useCallback(
    (step: MpUnloadTab): string => {
      if (step === 'pick') {
        return 'Утвердите план поставки, чтобы открыть подбор.'
      }
      if (step === 'packaging') {
        const remaining = mpCollectSummary?.remaining ?? 0
        if (remaining > 0) {
          return `Подберите ещё ${remaining} шт., чтобы перейти к упаковке.`
        }
        return 'Задание на упаковку появится после утверждения плана поставки.'
      }
      return ''
    },
    [mpCollectSummary],
  )
  // Дизайн-разбор 2026-08-16: галочка раньше означала «шаг разблокирован», а не
  // «шаг закончен» — на утверждённой отгрузке с планом 4 и подобрано 0 «Товары ✓»
  // и «Подбор ✓» стояли одновременно, хотя подбор ещё не начинался. Бригадир на
  // складе читает галочку однозначно: «этап закрыт, не проверяю». Здесь — факт
  // завершения по каждому шагу отдельно, а не доступность перехода.
  const mpStepDone = useCallback(
    (step: MpUnloadTab): boolean => {
      if (!unloadDetail || docModal !== 'marketplace_unload') {
        return false
      }
      if (step === 'plan') {
        // План закрыт, когда он больше не редактируется (черновик утверждён).
        return mpSubmitted || mpConfirmed || mpCollecting
      }
      if (step === 'pick') {
        // Подбор закончен, когда подбирать больше нечего — «осталось ноль».
        const planned = mpCollectSummary?.planned ?? 0
        const remaining = mpCollectSummary?.remaining ?? planned
        return planned > 0 && remaining <= 0
      }
      if (step === 'packaging') {
        return Boolean(unloadDetail.linked_packaging_task?.is_complete)
      }
      return false
    },
    [docModal, unloadDetail, mpSubmitted, mpConfirmed, mpCollecting, mpCollectSummary],
  )

  useEffect(() => {
    if (!unloadDetail || docModal !== 'marketplace_unload') {
      return
    }
    if (!mpStepEnabled(mpUnloadTab)) {
      setMpUnloadTab('plan')
    }
  }, [docModal, mpStepEnabled, mpUnloadTab, unloadDetail])

  const draftDoc =
    mpDraft ||
    mpSubmitted ||
    (docModal === 'discrepancy_act' && divergeDetail?.status === 'draft')
  const canDeleteMpUnloadLine = mpDraft
  const mpLineDraft = mpDraft || mpSubmitted

  const mpLineProductIds = useMemo(
    () => new Set(unloadDetail?.lines.map((ln) => ln.product_id) ?? []),
    [unloadDetail?.lines],
  )

  const mpStockByProductId = useMemo(() => {
    const m = new Map<string, number>()
    for (const row of warehouseAvailableProductPicklist) {
      m.set(row.id, row.available)
    }
    return m
  }, [warehouseAvailableProductPicklist])

  const mpPickerFilterRow = useCallback(
    (row: WbProductPickerCatalogRow) => {
      const available = mpStockByProductId.get(row.id) ?? 0
      return available >= 1 || mpLineProductIds.has(row.id)
    },
    [mpLineProductIds, mpStockByProductId],
  )

  const mpPickerGetAvailable = useCallback(
    (productId: string) => mpStockByProductId.get(productId) ?? 0,
    [mpStockByProductId],
  )

  const openMpProductPicker = async () => {
    if (!token || !authHeaders) return
    setModalError(null)
    try {
      if (catalog.length === 0) {
        await reloadWbCatalog()
      }
      setMpPickerOpen(true)
    } catch (e) {
      setModalError(e instanceof Error ? e.message : 'Не удалось загрузить каталог.')
    }
  }

  const postMpLine = async (productId: string, quantity: number) => {
    if (!token || !authHeaders || !docModalId) return false
    const res = await fetch(apiUrl(`/operations/marketplace-unload-requests/${docModalId}/lines`), {
      method: 'POST',
      headers: { ...authHeaders, 'Content-Type': 'application/json' },
      body: JSON.stringify({ product_id: productId, quantity }),
    })
    if (!res.ok) {
      setModalError(await readApiErrorMessage(res))
      return false
    }
    return true
  }

  const addMpLineByBarcode = async (rawInput?: string) => {
    if (!unloadDetail || !docModalId || docModal !== 'marketplace_unload' || !mpDraft) return
    const code = (rawInput ?? mpLineBarcodeScan).trim()
    if (!code) return
    setModalBusy(true)
    setModalError(null)
    try {
      let rows = catalog
      if (rows.length === 0) {
        rows = await reloadWbCatalog()
      }
      const productId = resolveProductIdByBarcode(rows, code)
      if (!productId) {
        setModalError('Товар не найден по штрихкоду или артикулу.')
        return
      }
      const existing = unloadDetail.lines.find((ln) => ln.product_id === productId)
      if (existing) {
        const delRes = await fetch(
          apiUrl(
            `/operations/marketplace-unload-requests/${docModalId}/lines/${existing.id}`,
          ),
          { method: 'DELETE', headers: authHeaders! },
        )
        if (!delRes.ok) {
          setModalError(await readApiErrorMessage(delRes))
          return
        }
        const ok = await postMpLine(productId, existing.quantity + 1)
        if (!ok) return
      } else {
        const ok = await postMpLine(productId, 1)
        if (!ok) return
      }
      setMpLineBarcodeScan('')
      await loadDocDetail()
      await onRefreshFfSupplyExtras()
    } catch (e) {
      setModalError(e instanceof Error ? e.message : 'Не удалось добавить строку по штрихкоду.')
    } finally {
      setModalBusy(false)
    }
  }

  useBarcodeScanner({
    enabled:
      docModal !== null &&
      docModalId !== null &&
      docModal === 'marketplace_unload' &&
      mpUnloadTab === 'plan' &&
      mpLineDraft &&
      mpDraft &&
      boxAddDialogBoxId == null &&
      !mpPickerOpen &&
      !modalBusy,
    onScan: (code) => {
      setMpLineBarcodeScan(code)
      void addMpLineByBarcode(code)
    },
  })

  useBarcodeScanner({
    enabled:
      docModal !== null &&
      docModalId !== null &&
      docModal === 'marketplace_unload' &&
      mpUnloadTab === 'packaging' &&
      mpExecutionPhase &&
      boxAddDialogBoxId == null &&
      !mpPickerOpen &&
      !modalBusy &&
      !mpAttachConfirmOpen &&
      !mpAttachOverPlanOpen,
    onScan: (code) => {
      setScanBarcode(code)
      requestAttachBoxScan(code)
    },
  })

  const applyMpProductPicker = async (mpPickerQtyByProduct: Record<string, number>) => {
    if (!unloadDetail || !docModalId || docModal !== 'marketplace_unload' || !mpDraft) return
    setModalBusy(true)
    setModalError(null)
    try {
      for (const [productId, rawQty] of Object.entries(mpPickerQtyByProduct)) {
        if (mpLineProductIds.has(productId)) continue
        const addQty = Number.isFinite(rawQty) ? Math.floor(rawQty) : 0
        if (addQty <= 0) continue
        const ok = await postMpLine(productId, addQty)
        if (!ok) return
      }
      setMpPickerOpen(false)
      await loadDocDetail()
      await onRefreshFfSupplyExtras()
    } catch (e) {
      setModalError(e instanceof Error ? e.message : 'Не удалось добавить товары.')
    } finally {
      setModalBusy(false)
    }
  }

  const pageTestId = isMpShipmentsPage ? 'ff-mp-shipments-page' : 'ff-supplies-shipments-page'

  return (
    <Box data-testid={pageTestId}>
      <PageHeader
        title={isMpShipmentsPage ? 'Отгрузки на МП' : 'Поставки'}
        description={
          isMpShipmentsPage
            ? 'Документы отгрузки на маркетплейс: план товаров, упаковка, короба и отгрузка.'
            : 'Поставки (селлер → ФФ), операционные отгрузки и акты расхождения. Отгрузки на маркетплейс — в разделе «Отгрузки на МП» слева.'
        }
      />

      {error ? (
        <Alert severity="error" sx={{ mb: 2 }}>
          {error}
        </Alert>
      ) : null}

      {infoNotice ? (
        <Alert severity="success" onClose={onDismissInfoNotice} sx={{ mb: 2 }} data-testid="ff-supplies-info-notice">
          {infoNotice}
        </Alert>
      ) : null}

      <Paper variant="outlined" sx={{ p: 2, mb: 2 }} data-testid="ff-supplies-create-actions">
        <Typography variant="subtitle2" sx={{ mb: 1.5, fontWeight: 700 }}>
          Новые документы
        </Typography>
        <Stack direction={{ xs: 'column', sm: 'row' }} spacing={1.5} sx={{ alignItems: { sm: 'center' } }}>
          {isMpShipmentsPage ? (
            <>
              <FormControl size="small" sx={{ minWidth: 260 }} required>
                <InputLabel id="ff-mp-create-seller-label">Селлер (ИП)</InputLabel>
                <Select
                  labelId="ff-mp-create-seller-label"
                  label="Селлер (ИП)"
                  value={mpCreateSellerId}
                  onChange={(e) => setMpCreateSellerId(String(e.target.value))}
                  data-testid="ff-mp-create-seller-filter"
                >
                  {sellers.map((s) => (
                    <MenuItem key={s.id} value={s.id}>
                      {s.name}
                    </MenuItem>
                  ))}
                </Select>
              </FormControl>
              <FormControl size="small" sx={{ minWidth: 180 }} required>
                <InputLabel id="ff-mp-create-marketplace-label">Маркетплейс</InputLabel>
                <Select
                  labelId="ff-mp-create-marketplace-label"
                  label="Маркетплейс"
                  value={mpCreateMarketplace}
                  onChange={(event) =>
                    setMpCreateMarketplace(event.target.value as 'wb' | 'ozon')
                  }
                  data-testid="ff-mp-create-marketplace"
                >
                  <MenuItem value="wb">Wildberries</MenuItem>
                  <MenuItem value="ozon">Ozon</MenuItem>
                </Select>
              </FormControl>
              <Button
                variant="contained"
                color="primary"
                disabled={busy || !mpCreateSellerId}
                data-testid="ff-create-mp-shipment"
                onClick={() => void createAndOpenMpShipment()}
              >
                Создать отгрузку на МП
              </Button>
            </>
          ) : (
            <Button
              variant="outlined"
              color="secondary"
              disabled={busy}
              data-testid="ff-create-diverge"
              onClick={() => void createAndOpenDiverge()}
            >
              Создать расхождение
            </Button>
          )}
        </Stack>
      </Paper>

      <Paper variant="outlined" sx={{ p: 2, mb: 2 }}>
        <Stack
          direction={{ xs: 'column', md: 'row' }}
          spacing={1.5}
          sx={{ flexWrap: 'wrap', alignItems: { xs: 'stretch', md: 'center' } }}
        >
          {!isMpShipmentsPage ? (
            <Stack direction="row" spacing={1} sx={{ flexWrap: 'wrap' }}>
              <Button
                size="small"
                variant={kind === 'all' ? 'contained' : 'outlined'}
                onClick={() => setKind('all')}
                data-testid="ff-docs-filter-all"
              >
                Все
              </Button>
              <Button
                size="small"
                variant={kind === 'inbound' ? 'contained' : 'outlined'}
                onClick={() => setKind('inbound')}
                data-testid="ff-docs-filter-inbound"
              >
                Поставки
              </Button>
              <Button
                size="small"
                variant={kind === 'discrepancy_act' ? 'contained' : 'outlined'}
                onClick={() => setKind('discrepancy_act')}
                data-testid="ff-docs-filter-diverge"
              >
                Расхождения
              </Button>
            </Stack>
          ) : null}
          <FormControl size="small" sx={{ minWidth: 200 }}>
            <InputLabel id="ff-seller-filter-label">Селлер</InputLabel>
            <Select
              labelId="ff-seller-filter-label"
              label="Селлер"
              value={sellerFilter}
              onChange={(e) => setSellerFilter(String(e.target.value))}
              data-testid="ff-docs-seller-filter"
            >
              <MenuItem value="all">Все</MenuItem>
              {sellerOptions.map((n) => (
                <MenuItem key={n} value={n}>
                  {n}
                </MenuItem>
              ))}
            </Select>
          </FormControl>
          <FormControl size="small" sx={{ minWidth: 220 }}>
            <InputLabel id="ff-sort-label">Сортировка</InputLabel>
            <Select
              labelId="ff-sort-label"
              label="Сортировка"
              value={sortKey}
              onChange={(e) =>
                setSortKey(e.target.value as typeof sortKey)
              }
              data-testid="ff-docs-sort"
            >
              <MenuItem value="planned_desc">Плановая дата ↓</MenuItem>
              <MenuItem value="planned_asc">Плановая дата ↑</MenuItem>
              <MenuItem value="created_desc">Дата создания ↓</MenuItem>
              <MenuItem value="created_asc">Дата создания ↑</MenuItem>
            </Select>
          </FormControl>
        </Stack>
      </Paper>

      <Table size="small">
        <TableHead>
          <TableRow>
            {!isMpShipmentsPage ? <TableCell>Тип</TableCell> : null}
            <TableCell>Номер</TableCell>
            <TableCell>Плановая дата</TableCell>
            <TableCell>Создано</TableCell>
            <TableCell>Статус</TableCell>
            <TableCell>Селлер</TableCell>
            <TableCell>Доп.</TableCell>
            <TableCell align="right">Строк</TableCell>
          </TableRow>
        </TableHead>
        <TableBody>
          {rows.length === 0 ? (
            <TableRow>
              <TableCell colSpan={isMpShipmentsPage ? 7 : 8}>
                <Typography variant="body2" color="text.secondary">
                  Нет документов
                </Typography>
              </TableCell>
            </TableRow>
          ) : (
            rows.map((row) => (
              <TableRow
                key={`${row.kind}-${row.id}`}
                hover
                sx={{
                  cursor: busy ? 'default' : 'pointer',
                  ...(row.kind === 'marketplace_unload' ? { height: 59 } : {}),
                }}
                onClick={() => {
                  if (busy) {
                    return
                  }
                  if (row.kind === 'inbound') {
                    onOpenInbound(row.id)
                  } else if (row.kind === 'outbound') {
                    onOpenOutbound(row.id)
                  } else if (row.kind === 'marketplace_unload') {
                    setUnloadDetail(null)
                    setDivergeDetail(null)
                    setModalError(null)
                    setSelectedInboundLineId('')
                    setLineProductId('')
                    setDocModal('marketplace_unload')
                    setDocModalId(row.id)
                  } else if (row.kind === 'discrepancy_act') {
                    setUnloadDetail(null)
                    setDivergeDetail(null)
                    setModalError(null)
                    setSelectedInboundLineId('')
                    setLineProductId('')
                    setDocModal('discrepancy_act')
                    setDocModalId(row.id)
                  }
                }}
                data-testid="ff-docs-row"
                data-doc-kind={row.kind}
              >
                {!isMpShipmentsPage ? <TableCell>{kindRu(row.kind)}</TableCell> : null}
                <TableCell>{row.documentNumber ?? '—'}</TableCell>
                <TableCell>{row.plannedDate ?? '—'}</TableCell>
                <TableCell>
                  {row.createdAt ? formatDateTimeLocal(row.createdAt) : '—'}
                </TableCell>
                <TableCell>
                  {docStatusRu(row.kind, row.status)}
                  {row.ffModified ? (
                    <Chip
                      size="small"
                      label="Изменено ФФ"
                      color="warning"
                      sx={{ ml: 0.75, verticalAlign: 'middle' }}
                      data-testid="ff-mp-ff-modified-badge"
                    />
                  ) : null}
                </TableCell>
                <TableCell>{row.sellerName ?? '—'}</TableCell>
                <TableCell sx={{ color: 'text.secondary', maxWidth: 200 }}>
                  {row.kind === 'marketplace_unload' ? (
                    <Box
                      sx={{
                        display: 'flex',
                        alignItems: 'center',
                        gap: 0.75,
                        minWidth: 0,
                        minHeight: 45,
                      }}
                    >
                      <Typography variant="body2" color="text.secondary" sx={{ minWidth: 0 }}>
                        {row.extraLabel ?? '—'}
                      </Typography>
                      <MarketplaceChip
                        marketplace={row.marketplace === 'ozon' ? 'ozon' : 'wb'}
                        testId="ff-mp-marketplace-chip"
                      />
                    </Box>
                  ) : (
                    row.extraLabel ?? '—'
                  )}
                </TableCell>
                <TableCell align="right">{row.lineCount}</TableCell>
              </TableRow>
            ))
          )}
        </TableBody>
      </Table>

      <Dialog
        open={docModal !== null && docModalId !== null}
        onClose={closeDocModal}
        fullScreen
      >
        <DialogTitle>{docTitle}</DialogTitle>
        <DialogContent dividers data-testid="ff-supplies-doc-dialog">
          {modalError ? (
            <Alert severity="error" sx={{ mb: 2 }} data-testid="ff-mp-modal-error">
              {modalError}
            </Alert>
          ) : null}
          {modalBusy && !unloadDetail && !divergeDetail ? (
            <Typography variant="body2" color="text.secondary">
              Загрузка…
            </Typography>
          ) : null}
          {unloadDetail ? (
            <>
              <Stack spacing={0.25} sx={{ mb: 1 }}>
                <Typography
                  variant="h5"
                  sx={{ fontWeight: 800, lineHeight: 1.15 }}
                  data-testid="ff-mp-unload-document-number"
                >
                  Отгрузка{unloadDisplayNumber ? ` ${unloadDisplayNumber}` : ''}
                </Typography>
              </Stack>
              <Typography variant="body2" color="text.secondary" sx={{ mb: 1 }}>
                {docModal === 'marketplace_unload' ? (
                  <>
                    Склад ФФ:{' '}
                    <strong data-testid="ff-mp-ff-warehouse-name">
                      {unloadDetail.warehouse_name}
                    </strong>
                  </>
                ) : (
                  <>Склад: {unloadDetail.warehouse_name}</>
                )}
                {' · '}
                {statusRu(unloadDetail.status)}
                {docModal !== 'marketplace_unload' && unloadDetail.planned_shipment_date
                  ? ` · отгрузка ${unloadDetail.planned_shipment_date}`
                  : ''}
              </Typography>
              {docModal === 'marketplace_unload' ? (
                <Stack
                  spacing={1.25}
                  direction={{ xs: 'column', sm: 'row' }}
                  sx={{ mb: 1.5, flexWrap: 'wrap', alignItems: { sm: 'center' } }}
                  data-testid="ff-mp-doc-header-fields"
                >
                  {mpDateEditable ? (
                    <Box sx={{ maxWidth: 280 }}>
                      <WmsDateField
                        label="Дата отгрузки на МП"
                        value={confirmDate || unloadDetail.planned_shipment_date}
                        onChange={(iso) => void patchMpPlannedDate(iso)}
                        disabled={modalBusy}
                        required
                        testId="ff-mp-planned-date"
                      />
                    </Box>
                  ) : unloadDetail.planned_shipment_date ? (
                    <Typography variant="body2" color="text.secondary" data-testid="ff-mp-planned-date-readonly">
                      Дата отгрузки: {unloadDetail.planned_shipment_date}
                    </Typography>
                  ) : null}
                  {mpLineDraft && unloadDetail.marketplace === 'wb' ? (
                    <>
                      <FormControl
                        size="small"
                        sx={{ minWidth: 280, width: { xs: '100%', sm: 'auto' } }}
                        disabled={modalBusy || wbMpWarehousesBusy}
                      >
                        <InputLabel id="ff-mp-wb-warehouse-header">Склад маркетплейса</InputLabel>
                        <Select
                          labelId="ff-mp-wb-warehouse-header"
                          label="Склад маркетплейса"
                          value={unloadDetail.wb_mp_warehouse_id ?? ''}
                          onChange={(e) => {
                            const v = Number(e.target.value)
                            if (Number.isInteger(v) && v > 0) {
                              void setWbWarehouseForUnload(v)
                            }
                          }}
                          data-testid="ff-mp-wb-warehouse-select"
                        >
                          <MenuItem value="">
                            <em>Не выбран</em>
                          </MenuItem>
                          {wbMpWarehouses.map((w) => (
                            <MenuItem key={w.wb_warehouse_id} value={w.wb_warehouse_id}>
                              {w.name} ({w.wb_warehouse_id})
                            </MenuItem>
                          ))}
                        </Select>
                      </FormControl>
                      {unloadDetail.wb_mp_warehouse_id == null ? (
                        <Typography variant="caption" color="text.secondary" sx={{ lineHeight: 1.25 }}>
                          Можно создать черновик без склада WB. Для «Утвердить» нужно выбрать склад,
                          когда он появится.
                        </Typography>
                      ) : null}
                    </>
                  ) : unloadDetail.marketplace === 'ozon' ? (
                    <Typography
                      variant="body2"
                      color="text.secondary"
                      data-testid="ff-mp-marketplace-warehouse-blocked"
                    >
                      Склад маркетплейса: Ozon определяет для конкретной поставки. Связь коробов с грузоместами и ТГМ заблокирована: кабинет недоступен.
                    </Typography>
                  ) : (
                    <Typography variant="body2" color="text.secondary" data-testid="ff-mp-wb-warehouse-readonly">
                      Склад маркетплейса:{' '}
                      {wbMpWarehouses.find(
                        (w) => w.wb_warehouse_id === unloadDetail.wb_mp_warehouse_id,
                      )?.name ?? unloadDetail.wb_mp_warehouse_id ?? '—'}
                    </Typography>
                  )}
                </Stack>
              ) : null}
            </>
          ) : null}
          {unloadDetail?.ff_modified ? (
            <Alert severity="warning" sx={{ mb: 1 }} data-testid="ff-mp-ff-modified-notice">
              Состав изменён на складе после планирования селлером.
            </Alert>
          ) : null}
          {docModal === 'marketplace_unload' && mpCollectSummary ? (
            <Paper
              variant="outlined"
              sx={{ mb: 2, p: 1.5, bgcolor: 'action.hover' }}
              data-testid="ff-mp-shipment-summary"
            >
              <Box
                sx={{
                  display: 'grid',
                  gap: 1,
                  gridTemplateColumns: {
                    xs: 'repeat(2, minmax(0, 1fr))',
                    md: 'repeat(4, minmax(0, 1fr))',
                  },
                }}
              >
                <Box>
                  <Typography variant="caption" color="text.secondary">
                    План
                  </Typography>
                  <Typography variant="body2" sx={{ fontWeight: 700 }} data-testid="ff-mp-shipment-summary-planned">
                    {mpCollectSummary.planned}
                  </Typography>
                </Box>
                <Box>
                  {/* Раньше подпись была «В коробах / распределено» — короб тут ни при чём:
                      подбор с 2026-08-16 коробов не трогает вообще, это чистое количество
                      подобранного со склада. Старая подпись рядом с «Упаковано» из другого
                      знаменателя (сколько из уже подобранного упаковано) читалась как одно
                      противоречивое число — развели подписями, что к чему относится. */}
                  <Typography variant="caption" color="text.secondary">
                    Подобрано
                  </Typography>
                  <Typography
                    variant="body2"
                    sx={{ fontWeight: 700 }}
                    data-testid="ff-mp-shipment-summary-distributed"
                  >
                    {mpCollectSummary.distributed}
                  </Typography>
                </Box>
                <Box>
                  <Typography variant="caption" color="text.secondary">
                    Осталось подобрать
                  </Typography>
                  <Typography
                    variant="body2"
                    sx={{
                      fontWeight: 700,
                      color: mpCollectSummary.remaining !== 0 ? 'warning.main' : 'text.primary',
                    }}
                    data-testid="ff-mp-shipment-summary-remaining"
                  >
                    {mpCollectSummary.remaining}
                  </Typography>
                </Box>
                <Box>
                  <Typography variant="caption" color="text.secondary">
                    Упаковано (из подобранного)
                  </Typography>
                  <Typography
                    variant="body2"
                    sx={{ fontWeight: 700 }}
                    data-testid="ff-mp-shipment-summary-packed"
                  >
                    {mpCollectSummary.packed ?? '—'}
                  </Typography>
                </Box>
              </Box>
            </Paper>
          ) : null}
          {docModal === 'marketplace_unload' && unloadDetail ? (
            <Box sx={{ mb: 2 }} data-testid="ff-mp-process">
              <Tabs
                value={mpUnloadTab}
                onChange={(_e, value: MpUnloadTab) => {
                  if (mpStepEnabled(value)) {
                    setMpUnloadTab(value)
                  }
                }}
                variant="scrollable"
                scrollButtons="auto"
                sx={{ borderBottom: 1, borderColor: 'divider', mb: 2 }}
                data-testid="ff-mp-process-tabs"
              >
                {mpUnloadSteps.map((step) => {
                  // Три разных состояния шага не сжимаются в один суффикс:
                  // ✓ — фактически закончен; … — доступен, но работа ещё идёт;
                  // без значка и серым (disabled) — пока недоступен.
                  const done = mpStepDone(step.value)
                  const enabled = mpStepEnabled(step.value)
                  const label = done ? `${step.label} ✓` : enabled ? `${step.label} …` : step.label
                  const tab = (
                    <Tab
                      key={step.value}
                      // Пункт 1 итерации 2026-08-14: назад можно, вперёд нельзя — как в FBS
                      // (frontend/src/screens/v2/FfFbsSupplyWorkspace.tsx, STAGES/currentStageIndex).
                      label={label}
                      value={step.value}
                      disabled={!enabled}
                      data-testid={step.testId}
                    />
                  )
                  if (enabled) return tab
                  // Disabled-таб MUI без обёртки <span> не показывает Tooltip.
                  return (
                    <Tooltip key={step.value} title={mpStepBlockedReason(step.value)}>
                      <span>{tab}</span>
                    </Tooltip>
                  )
                })}
              </Tabs>
              {mpUnloadTab === 'plan' ? (
                <Stack spacing={2} data-testid="ff-mp-tab-plan-panel">
                  {unloadDetail.seller_name ? (
                    <Typography variant="body2" color="text.secondary">
                      Селлер: <strong>{unloadDetail.seller_name}</strong>
                    </Typography>
                  ) : null}
                  {mpLineDraft ? (
                    <Paper variant="outlined" sx={{ p: 1.5 }} data-testid="ff-mp-add-products-panel">
                      <Typography variant="subtitle2" sx={{ mb: 1.25 }}>
                        Добавление товаров
                      </Typography>
                      {/* MPFBO-01: элемент не исчезает, а объясняет, почему недоступен —
                          иначе оператор не понимает, потерял он кнопку или система сломалась. */}
                      {!mpDraft ? (
                        <Typography
                          variant="body2"
                          color="text.secondary"
                          sx={{ mb: 1.25 }}
                          data-testid="ff-mp-add-products-locked"
                        >
                          Состав можно менять только в черновике — план уже утверждён.
                        </Typography>
                      ) : null}
                      <Stack
                        direction={{ xs: 'column', sm: 'row' }}
                        spacing={1}
                        sx={{ flexWrap: 'wrap' }}
                      >
                        <Stack
                          direction={{ xs: 'column', sm: 'row' }}
                          spacing={1}
                          sx={{ width: { xs: '100%', sm: 'auto' }, flexGrow: 1 }}
                          data-testid="ff-mp-line-barcode-row"
                        >
                          <TextField
                            size="small"
                            label="Штрихкод / артикул"
                            value={mpLineBarcodeScan}
                            disabled={modalBusy}
                            onChange={(e) => setMpLineBarcodeScan(e.target.value)}
                            onKeyDown={(e) => {
                              if (e.key === 'Enter') {
                                e.preventDefault()
                                void addMpLineByBarcode()
                              }
                            }}
                            slotProps={{ htmlInput: { 'data-testid': 'ff-mp-line-barcode-scan' } }}
                            sx={{ minWidth: 220, flexGrow: 1 }}
                          />
                          <Button
                            variant="outlined"
                            disabled={modalBusy || !mpDraft || !mpLineBarcodeScan.trim()}
                            onClick={() => void addMpLineByBarcode()}
                            data-testid="ff-mp-line-barcode-add"
                          >
                            Добавить по ШК
                          </Button>
                        </Stack>
                        <Button
                          variant="contained"
                          disabled={modalBusy || !mpDraft}
                          onClick={() => void openMpProductPicker()}
                          data-testid="ff-mp-add-products"
                        >
                          Добавить товары
                        </Button>
                      </Stack>
                    </Paper>
                  ) : null}
                  <Table
                    size="small"
                    data-testid="ff-supplies-doc-lines"
                    sx={{ tableLayout: 'fixed', width: '100%' }}
                  >
                    <TableHead>
                      <TableRow>
                        <FfProductTableHeadCells showPrint={false} />
                        <TableCell align="right">План</TableCell>
                        {mpExecutionPhase ? (
                          <TableCell align="right">Осталось</TableCell>
                        ) : null}
                        {canDeleteMpUnloadLine ? <TableCell align="right" width={56} /> : null}
                      </TableRow>
                    </TableHead>
                    <TableBody>
                      {(() => {
                        const lines = unloadDetail.lines
                        const productCols = 6
                        const mpCols = mpExecutionPhase ? 1 : 0
                        const emptySpan = productCols + 1 + mpCols + (canDeleteMpUnloadLine ? 1 : 0)
                        if (lines.length === 0) {
                          return (
                            <TableRow>
                              <TableCell colSpan={emptySpan}>
                                <Typography variant="body2" color="text.secondary">
                                  Пока нет строк
                                </Typography>
                              </TableCell>
                            </TableRow>
                          )
                        }
                        return lines.map((ln) => {
                          const picked = ln.picked_qty ?? 0
                          const remaining = ln.quantity - picked
                          const lineShowsDiscrepancy =
                            unloadDetail.status === 'shipped' && Boolean(ln.has_discrepancy)
                          const displayMeta = getDisplayMeta(ln.product_id, ln)
                          return (
                            <TableRow
                              key={ln.id}
                              sx={
                                lineShowsDiscrepancy
                                  ? { '& .MuiTableCell-root': { color: 'error.main' } }
                                  : undefined
                              }
                              data-testid={
                                lineShowsDiscrepancy
                                  ? `ff-mp-line-discrepancy-${ln.id}`
                                  : `ff-mp-line-row-${ln.id}`
                              }
                            >
                              <FfProductLineCells
                                meta={displayMeta}
                                showPrint={false}
                              />
                              <TableCell align="right" data-testid={`ff-mp-line-plan-${ln.id}`}>
                                {ln.quantity}
                              </TableCell>
                              {mpExecutionPhase ? (
                                <TableCell
                                  align="right"
                                  data-testid={`ff-mp-line-remaining-${ln.id}`}
                                >
                                  {remaining}
                                </TableCell>
                              ) : null}
                              {canDeleteMpUnloadLine ? (
                                <TableCell align="right">
                                  <Tooltip title="Удалить строку">
                                    <IconButton
                                      size="small"
                                      aria-label="Удалить строку"
                                      data-testid={`ff-supplies-line-delete-${ln.id}`}
                                      disabled={modalBusy}
                                      onClick={(e) => {
                                        e.stopPropagation()
                                        void deleteDocLine(ln.id)
                                      }}
                                    >
                                      <DeleteOutlineOutlined fontSize="small" />
                                    </IconButton>
                                  </Tooltip>
                                </TableCell>
                              ) : null}
                            </TableRow>
                          )
                        })
                      })()}
                    </TableBody>
                  </Table>
                </Stack>
              ) : null}
              {mpUnloadTab === 'pick' && unloadDetail && token && authHeaders ? (
                <Box data-testid="ff-mp-tab-pick-panel">
                  {/* Новый подбор с ячеек — согласованный экран варианта А —
                      показывается прямо здесь, во вкладке документа. Отдельной
                      страницей его открывать не надо: оператор работает внутри
                      отгрузки. Старая панель осталась в FfMpUnloadPickPanel.tsx. */}
                  <FfUnloadPickPage
                    token={token}
                    requestId={unloadDetail.id}
                    // Подбор идёт внутри окна документа, поэтому его завершение
                    // переводит на упаковку, а не уводит на список отгрузок.
                    onFinished={() => setMpUnloadTab('packaging')}
                  />
                </Box>
              ) : null}
              {mpUnloadTab === 'packaging' ? (
                <Box data-testid="ff-mp-tab-packaging-panel">
                  {packagingTaskError ? (
                    <Alert severity="error" sx={{ mb: 2 }}>
                      {packagingTaskError}
                    </Alert>
                  ) : null}
                  {packagingTask && token ? (
                    <FfPackagingTaskPanel
                      token={token}
                      task={packagingTask} addressStorageEnabled={addressStorageEnabled}
                      hideDocumentHeader
                      compactLayout
                      // Пункт 10 итерации 2026-08-14: единое поле скана на упаковке различает
                      // короб и товар — скан короба делегируется существующему флоу привязки.
                      onBoxBarcodeScan={requestAttachBoxScan}
                      onUpdated={(task) => {
                        const changedStage =
                          task.status !== packagingTask.status ||
                          task.is_complete !== packagingTask.is_complete
                        setPackagingTask(task)
                        if (changedStage) {
                          void loadDocDetail()
                        }
                      }}
                    />
                  ) : unloadDetail?.linked_packaging_task ? (
                    <Typography
                      variant="body2"
                      color="text.secondary"
                      data-testid="ff-mp-packaging-task-created"
                    >
                      Задание на упаковку создано.
                    </Typography>
                  ) : (
                    <Typography
                      variant="body2"
                      color="text.secondary"
                      data-testid="ff-mp-packaging-empty"
                    >
                      Задание на упаковку ещё не создано.
                    </Typography>
                  )}
                  <Accordion
                    disableGutters
                    variant="outlined"
                    sx={{ mt: 2 }}
                    data-testid="ff-mp-boxes-accordion"
                  >
                    <AccordionSummary
                      expandIcon={<ExpandMoreOutlined />}
                      data-testid="ff-mp-boxes-summary"
                      sx={{
                        bgcolor: (theme) => alpha(theme.palette.primary.main, 0.08),
                      }}
                    >
                      {/* Пункт 12 итерации 2026-08-14: числа «распределено/план» уже есть в шапке
                          (ff-mp-shipment-summary) — здесь не дублируем, только заголовок раздела.
                          MPU-04б (18.08): заказчик не видел, что блок вообще раскрывается и что
                          внутри есть содержимое — счётчики коробов и единиц в них по образцу
                          «Короба и грузоместа» на приёмке (FfInboundRequestView).
                          MPU-08 (18.08): заголовок сливался с фоном, заказчик просил несколько
                          раз сделать его заметным — лёгкая подложка фирменным цветом темы
                          (primary, 8% непрозрачности) и жирный заголовок, не полная заливка. */}
                      <Stack direction="row" spacing={1.5} sx={{ alignItems: 'center', flexWrap: 'wrap' }}>
                        <Typography variant="subtitle2" sx={{ fontWeight: 700 }}>
                          Короба
                        </Typography>
                        <Chip
                          size="small"
                          label={`Коробов: ${mpBoxesSummary.boxCount}`}
                          data-testid="ff-mp-boxes-count-chip"
                        />
                        <Chip
                          size="small"
                          label={`Единиц: ${mpBoxesSummary.unitCount}`}
                          data-testid="ff-mp-boxes-units-chip"
                        />
                      </Stack>
                    </AccordionSummary>
                    <AccordionDetails>
                      <Stack spacing={1.25} data-testid="ff-mp-boxes">
                        {canUseMpBoxOperationalControls ? (
                          <Box
                            sx={{
                              display: 'grid',
                              gap: 1,
                              gridTemplateColumns: { xs: 'minmax(0, 1fr)', sm: 'minmax(0, 1fr) auto' },
                              alignItems: 'start',
                            }}
                          >
                            <TextField
                              size="small"
                              label="Штрихкод готового короба (WHB-…)"
                              value={scanBarcode}
                              onChange={(e) => setScanBarcode(e.target.value)}
                              onKeyDown={(e) => {
                                if (e.key === 'Enter') {
                                  e.preventDefault()
                                  void doCollectScan()
                                }
                              }}
                              disabled={modalBusy}
                              fullWidth
                              slotProps={{ htmlInput: { 'data-testid': 'ff-mp-pick-scan-input' } }}
                              data-testid="ff-mp-pick-scan-field"
                              sx={{ minWidth: 0 }}
                            />
                            <Button
                              variant="outlined"
                              size="medium"
                              sx={{ whiteSpace: 'nowrap' }}
                              onClick={() => void doCollectScan()}
                              disabled={modalBusy}
                              data-testid="ff-mp-pick-scan"
                            >
                              Привязать
                            </Button>
                          </Box>
                        ) : null}

                        {mpVisibleBoxes.length > 0 ? (
                          <Stack spacing={1.5}>
                            {mpBoxesOrdered.map((b, idx) =>
                              renderMpBoxCard(
                                b,
                                idx + 1,
                                idx === 0 && b.lines.length > 0
                                  ? 'ff-mp-open-box-lines'
                                  : `ff-mp-box-lines-${b.id}`,
                              ),
                            )}
                          </Stack>
                        ) : (
                          <Typography variant="body2" color="text.secondary">
                            Короба появятся после создания или скана готового короба.
                          </Typography>
                        )}

                        {canUseMpBoxOperationalControls ? (
                          <Stack
                            direction="row"
                            spacing={1}
                            sx={{ alignItems: 'center', flexWrap: 'wrap', pt: 0.5 }}
                          >
                            <TextField
                              size="small"
                              label="Кол-во коробов"
                              type="number"
                              value={boxBatchCount}
                              onChange={(e) => setBoxBatchCount(e.target.value)}
                              slotProps={{ htmlInput: { min: 1, max: 50 } }}
                              sx={{ width: 120 }}
                              disabled={modalBusy}
                              data-testid="ff-mp-box-batch-count"
                            />
                            <FormControl size="small" sx={{ minWidth: 160 }}>
                              <InputLabel id="ff-mp-box-preset">Пресет</InputLabel>
                              <Select
                                labelId="ff-mp-box-preset"
                                label="Пресет"
                                value={boxPreset}
                                onChange={(e) =>
                                  setBoxPreset(String(e.target.value) as '60_40_40' | '30_20_30')
                                }
                                data-testid="ff-mp-box-preset"
                                disabled={modalBusy}
                              >
                                <MenuItem value="60_40_40">60×40×40</MenuItem>
                                <MenuItem value="30_20_30">30×20×30</MenuItem>
                              </Select>
                            </FormControl>
                            <Button
                              variant="outlined"
                              size="small"
                              onClick={() => setBoxImportOpen(true)}
                              disabled={modalBusy}
                              data-testid="ff-mp-import-boxes"
                            >
                              Загрузить по накладной
                            </Button>
                            <Button
                              variant="outlined"
                              size="small"
                              onClick={() => void createBox()}
                              disabled={modalBusy}
                              data-testid="ff-mp-box-batch-create"
                            >
                              {Number(boxBatchCount) === 1 ? 'Создать короб' : 'Создать короба'}
                            </Button>
                          </Stack>
                        ) : null}
                      </Stack>
                    </AccordionDetails>
                  </Accordion>
                    {canUseMpBoxDestructiveControls ? (
                      <Menu
                        anchorEl={boxMenuAnchor}
                        open={Boolean(boxMenuAnchor)}
                        onClose={closeBoxMenu}
                        data-testid="ff-mp-box-menu"
                      >
                        <MenuItem
                          data-testid="ff-mp-box-menu-print"
                          disabled={!boxMenuTargetId || !boxById.get(boxMenuTargetId ?? '')?.internal_barcode}
                          onClick={() => {
                            const box = boxMenuTargetId ? boxById.get(boxMenuTargetId) : null
                            if (box) {
                              requestPrintBoxBarcode(box)
                            }
                            closeBoxMenu()
                          }}
                        >
                          Печать ШК
                        </MenuItem>
                        <MenuItem
                          data-testid="ff-mp-box-menu-copy"
                          disabled={!boxMenuTargetId || modalBusy}
                          onClick={() => {
                            if (boxMenuTargetId) {
                              void copyBox(boxMenuTargetId)
                            }
                          }}
                        >
                          Копировать в новый короб
                        </MenuItem>
                        <MenuItem
                          data-testid="ff-mp-box-menu-delete"
                          disabled={
                            !boxMenuTargetId ||
                            modalBusy ||
                            (boxMenuTargetId
                              ? (boxById.get(boxMenuTargetId)?.lines.reduce(
                                  (s, ln) => s + ln.quantity,
                                  0,
                                ) ?? 0) > 0
                              : true)
                          }
                          onClick={() => {
                            if (boxMenuTargetId) {
                              void deleteBox(boxMenuTargetId)
                            }
                          }}
                        >
                          Удалить короб
                        </MenuItem>
                      </Menu>
                    ) : null}
                </Box>
              ) : null}
            </Box>
          ) : null}
          {divergeDetail ? (
            <Typography variant="body2" color="text.secondary" sx={{ mb: 1 }}>
              {docStatusRu('discrepancy_act', divergeDetail.status)}
              {divergeDetail.inbound_intake_request_id
                ? ` · приёмка ${divergeDetail.inbound_intake_request_id.slice(0, 8)}…`
                : ''}
            </Typography>
          ) : null}
          {docModal !== 'marketplace_unload' ? (
          <Table size="small" data-testid="ff-supplies-doc-lines" sx={{ tableLayout: 'fixed', width: '100%' }}>
            <TableHead>
              <TableRow>
                <FfProductTableHeadCells showPrint={false} />
                <TableCell>Строка приёмки</TableCell>
                <TableCell align="right">Расхождение</TableCell>
                {draftDoc ? <TableCell align="right" width={56} /> : null}
              </TableRow>
            </TableHead>
            <TableBody>
              {(() => {
                const lines = divergeDetail?.lines ?? []
                const emptySpan = 6 + 1 + 1 + (draftDoc ? 1 : 0)
                if (lines.length === 0) {
                  return (
                    <TableRow>
                      <TableCell colSpan={emptySpan}>
                        <Typography variant="body2" color="text.secondary">
                          Пока нет строк
                        </Typography>
                      </TableCell>
                    </TableRow>
                  )
                }
                return lines.map((ln) => {
                  const displayMeta = getDisplayMeta(ln.product_id, ln)
                  return (
                    <TableRow
                      key={ln.id}
                      sx={
                        ln.has_discrepancy
                          ? { '& .MuiTableCell-root': { color: 'error.main' } }
                          : undefined
                      }
                    >
                      <FfProductLineCells meta={displayMeta} showPrint={false} />
                      <TableCell sx={{ color: 'text.secondary', fontSize: 13 }}>
                        {ln.inbound_intake_line_id
                          ? `${ln.inbound_intake_line_id.slice(0, 8)}…`
                          : '—'}
                      </TableCell>
                      <TableCell align="right">{formatSignedQty(ln.quantity)}</TableCell>
                      {draftDoc ? (
                        <TableCell align="right">
                          <Tooltip title="Удалить строку">
                            <IconButton
                              size="small"
                              aria-label="Удалить строку"
                              data-testid={`ff-supplies-line-delete-${ln.id}`}
                              disabled={modalBusy}
                              onClick={(e) => {
                                e.stopPropagation()
                                void deleteDocLine(ln.id)
                              }}
                            >
                              <DeleteOutlineOutlined fontSize="small" />
                            </IconButton>
                          </Tooltip>
                        </TableCell>
                      ) : null}
                    </TableRow>
                  )
                })
              })()}
            </TableBody>
          </Table>
          ) : null}
          {draftDoc && docModal === 'discrepancy_act' && docProductPicklist.length > 0 ? (
            <Stack spacing={1.5} sx={{ mt: 2 }}>
              {docModal === 'discrepancy_act' && inboundRefLines.length > 0 ? (
                <FormControl fullWidth size="small">
                  <InputLabel id="ff-doc-inbound-line">Строка приёмки (опционально)</InputLabel>
                  <Select
                    labelId="ff-doc-inbound-line"
                    label="Строка приёмки (опционально)"
                    value={selectedInboundLineId}
                    onChange={(e) => {
                      const v = String(e.target.value)
                      setSelectedInboundLineId(v)
                      const pick = inboundRefLines.find((x) => x.id === v)
                      setLineProductId(pick ? pick.product_id : '')
                    }}
                    data-testid="ff-supplies-inbound-line"
                  >
                    <MenuItem value="">Без привязки к строке приёмки</MenuItem>
                    {inboundRefLines.map((ln) => (
                      <MenuItem key={ln.id} value={ln.id}>
                        {ln.sku_code} — план {ln.product_name.slice(0, 40)}
                        {ln.product_name.length > 40 ? '…' : ''}
                      </MenuItem>
                    ))}
                  </Select>
                </FormControl>
              ) : null}
              <FormControl fullWidth size="small">
                <InputLabel id="ff-doc-line-product">Товар</InputLabel>
                <Select
                  labelId="ff-doc-line-product"
                  label="Товар"
                  value={lineProductId}
                  onChange={(e) => setLineProductId(String(e.target.value))}
                  data-testid="ff-supplies-line-product"
                  disabled={Boolean(selectedInboundLineId)}
                >
                  <MenuItem value="" disabled>
                    Выберите SKU
                  </MenuItem>
                  {docProductPicklist.map((p) => (
                    <MenuItem key={p.id} value={p.id}>
                      {p.sku_code} — {p.name}
                      {'available' in p ? ` · доступно для FBO ${p.available}` : ''}
                    </MenuItem>
                  ))}
                </Select>
              </FormControl>
              <TextField
                size="small"
                label="Расхождение"
                type="number"
                slotProps={{ htmlInput: { step: 1 } }}
                value={lineQty}
                onChange={(e) => setLineQty(e.target.value)}
                data-testid="ff-supplies-line-qty"
              />
              <Button
                variant="contained"
                disabled={modalBusy || !lineProductId}
                onClick={() => void submitLine()}
                data-testid="ff-supplies-line-add"
              >
                Добавить строку
              </Button>
            </Stack>
          ) : null}
          {draftDoc && docModal === 'discrepancy_act' && docProductPicklist.length === 0 ? (
            <Typography variant="caption" color="text.secondary" sx={{ mt: 1, display: 'block' }}>
              Добавьте товары в каталоге, чтобы оформить строки.
            </Typography>
          ) : null}
        </DialogContent>
        <DialogActions
          sx={{ flexWrap: 'wrap', gap: 1 }}
          data-testid="ff-mp-footer-bar"
        >
          <Stack direction="row" spacing={1} sx={{ flexWrap: 'wrap' }}>
            {docModal === 'marketplace_unload' && unloadDetail && (mpDraft || mpSubmitted) ? (
              <>
                <Button
                  variant="contained"
                  color="secondary"
                  size="large"
                  disabled={
                    modalBusy ||
                    !confirmDate.trim() ||
                    unloadDetail.wb_mp_warehouse_id == null ||
                    unloadDetail.lines.length < 1
                  }
                  onClick={() => void submitDoc()}
                  data-testid="ff-supplies-doc-submit"
                >
                  Утвердить
                </Button>
                {mpSubmitted ? (
                  <Button
                    variant="outlined"
                    color="error"
                    disabled={modalBusy}
                    onClick={() => setMpCancelConfirmOpen(true)}
                    data-testid="ff-mp-cancel-unload"
                  >
                    Отменить отгрузку
                  </Button>
                ) : null}
              </>
            ) : null}
            {docModal === 'marketplace_unload' && unloadDetail && mpExecutionPhase ? (
              <>
                {mpImmediateNextStep ? (
                  <Stack spacing={0.5} sx={{ alignItems: 'flex-start', maxWidth: 420 }}>
                    {mpNextStepEnabled ? (
                      <Button
                        variant="contained"
                        color="primary"
                        size="large"
                        endIcon={<ArrowForwardOutlined />}
                        disabled={modalBusy}
                        onClick={() => setMpUnloadTab(mpImmediateNextStep.value)}
                        data-testid="ff-mp-next-step"
                      >
                        Далее: {mpUnloadStepLabel(mpImmediateNextStep.value)}
                      </Button>
                    ) : (
                      <>
                        <Tooltip title={mpStepBlockedReason(mpImmediateNextStep.value)}>
                          <span>
                            <Button
                              variant="contained"
                              color="primary"
                              size="large"
                              endIcon={<ArrowForwardOutlined />}
                              disabled
                              data-testid="ff-mp-next-step"
                            >
                              Далее: {mpUnloadStepLabel(mpImmediateNextStep.value)}
                            </Button>
                          </span>
                        </Tooltip>
                        <Typography
                          variant="body2"
                          color="text.secondary"
                          data-testid="ff-mp-next-step-reason"
                        >
                          {mpStepBlockedReason(mpImmediateNextStep.value)}
                        </Typography>
                      </>
                    )}
                  </Stack>
                ) : (
                  <Button
                    variant="contained"
                    color="primary"
                    size="large"
                    disabled={
                      modalBusy ||
                      (mpCollectSummary?.distributed ?? 0) < 1 ||
                      !mpPackagingComplete
                    }
                    onClick={() => requestShipMpUnload()}
                    data-testid="ff-mp-ship"
                  >
                    Завершить
                  </Button>
                )}
                {mpCancellable ? (
                  <Button
                    variant="outlined"
                    color="error"
                    disabled={modalBusy}
                    onClick={() => setMpCancelConfirmOpen(true)}
                    data-testid="ff-mp-cancel-unload"
                  >
                    Отменить отгрузку
                  </Button>
                ) : null}
              </>
            ) : null}
            {draftDoc && docModal !== 'marketplace_unload' ? (
              <Button
                variant="contained"
                color="secondary"
                disabled={modalBusy}
                onClick={() => void submitDoc()}
                data-testid="ff-supplies-doc-submit"
              >
                Передать на FF
              </Button>
            ) : null}
            {docModal === 'discrepancy_act' && divergeDetail?.status === 'confirmed' ? (
              <>
                <Button
                  variant="contained"
                  color="primary"
                  disabled={modalBusy}
                  onClick={() => void resolveDiscrepancyAct('approve')}
                  data-testid="ff-discrepancy-act-approve"
                >
                  Утвердить акт
                </Button>
                <Button
                  variant="outlined"
                  color="error"
                  disabled={modalBusy}
                  onClick={() => void resolveDiscrepancyAct('reject')}
                  data-testid="ff-discrepancy-act-reject"
                >
                  Отклонить
                </Button>
              </>
            ) : null}
          </Stack>
          <Button onClick={closeDocModal} data-testid="ff-supplies-doc-close">
            Закрыть
          </Button>
        </DialogActions>
      </Dialog>

      <WbProductPickerDialog
        open={mpPickerOpen}
        busy={modalBusy}
        catalog={catalog}
        disabledProductIds={mpLineProductIds}
        testIdPrefix="ff-mp-picker"
        variant="ff"
        qtyColumnLabel="Кол-во в отгрузку"
        applyLabel="Добавить в отгрузку"
        inDraftMessage="Товар уже добавлен в отгрузку"
        showAvailableColumn
        availableColumnLabel="Доступно FBO"
        getAvailable={mpPickerGetAvailable}
        filterRow={mpPickerFilterRow}
        // Остаток ищется строго по складу документа: JOIN StorageLocation по warehouse_id.
        // Пустой список чаще всего значит «отгрузка создана не на том складе», поэтому
        // склад назван прямо в сообщении — иначе оператор упирается в тупик без подсказки.
        emptyMessage={
          unloadDetail?.warehouse_name
            ? `На складе «${unloadDetail.warehouse_name}» нет свободного остатка по этому селлеру. Проверьте, тот ли склад указан в отгрузке.`
            : 'Нет свободного остатка по этому селлеру на складе отгрузки.'
        }
        onClose={() => setMpPickerOpen(false)}
        onApply={applyMpProductPicker}
      />
      {token &&
      docModalId &&
      docModal === 'marketplace_unload' &&
      boxAddDialogBoxId &&
      boxById.get(boxAddDialogBoxId) ? (
        <FfMarketplaceUnloadBoxAddDialog
          open
          onClose={() => setBoxAddDialogBoxId(null)}
          requestId={docModalId}
          boxId={boxAddDialogBoxId}
          boxLabel={
            (() => {
              const idx = mpBoxesOrdered.findIndex((b) => b.id === boxAddDialogBoxId)
              const ordinal = idx >= 0 ? idx + 1 : null
              const barcode = boxById.get(boxAddDialogBoxId)?.internal_barcode?.trim()
              if (ordinal != null) {
                return barcode ? `Короб ${ordinal} · ${barcode}` : `Короб ${ordinal}`
              }
              return barcode ?? 'Короб'
            })()
          }
          readOnly={!canUseMpBoxOperationalControls}
          token={token}
          addressStorageEnabled={addressStorageEnabled}
          catalogById={catalogById}
          warehouseStockByProductId={mpStockByProductId}
          onUpdated={async () => {
            await loadDocDetail()
            await loadPackagingTask()
            await onRefreshFfSupplyExtras()
          }}
          onAddSuccess={(quantity) =>
            setBoxAddSuccessMsg(`Добавлено ${quantity} шт`)
          }
          onProductScanned={(line) =>
            setUnloadDetail((current) => {
              if (!current) return current
              return {
                ...current,
                boxes: current.boxes.map((box) => {
                  if (box.id !== boxAddDialogBoxId) return box
                  const exists = box.lines.some((item) => item.id === line.id)
                  return {
                    ...box,
                    lines: exists
                      ? box.lines.map((item) => (item.id === line.id ? line : item))
                      : [...box.lines, line],
                  }
                }),
              }
            })
          }
        />
      ) : null}
      {boxImportOpen && canUseMpBoxOperationalControls && docModalId && token ? (
        <BoxImportDialog
          open={boxImportOpen}
          token={token}
          requestId={docModalId}
          importBasePath={`/operations/marketplace-unload-requests/${docModalId}/import-boxes`}
          testIdPrefix="ff-mp-box-import"
          mpBoxPreset={boxPreset}
          onClose={() => setBoxImportOpen(false)}
          onApplied={async (message) => {
            setBoxAddSuccessMsg(message)
            await loadDocDetail()
            await loadPackagingTask()
            await onRefreshFfSupplyExtras()
          }}
        />
      ) : null}
      <Snackbar
        open={boxAddSuccessMsg !== null}
        autoHideDuration={2500}
        onClose={() => setBoxAddSuccessMsg(null)}
        anchorOrigin={{ vertical: 'bottom', horizontal: 'center' }}
      >
        <Alert
          severity="success"
          variant="filled"
          onClose={() => setBoxAddSuccessMsg(null)}
          data-testid="ff-mp-box-add-success-snackbar"
          sx={{ width: '100%' }}
        >
          {boxAddSuccessMsg}
        </Alert>
      </Snackbar>
      {/* Пункт 2 итерации 2026-08-14: смена статуса документа больше не проходит молча. */}
      <Snackbar
        open={statusChangeMsg !== null}
        autoHideDuration={4000}
        onClose={() => setStatusChangeMsg(null)}
        anchorOrigin={{ vertical: 'bottom', horizontal: 'center' }}
      >
        <Alert
          severity="info"
          variant="filled"
          onClose={() => setStatusChangeMsg(null)}
          data-testid="ff-mp-status-change-snackbar"
          sx={{ width: '100%' }}
        >
          {statusChangeMsg}
        </Alert>
      </Snackbar>
      <Dialog
        open={mpShipConfirmOpen}
        onClose={() => setMpShipConfirmOpen(false)}
        data-testid="ff-mp-ship-discrepancy-dialog"
      >
        <DialogTitle>Есть расхождения, точно провести?</DialogTitle>
        <DialogContent>
          <Typography variant="body2">
            Распределено по коробам {mpCollectSummary?.distributed ?? 0} из{' '}
            {mpCollectSummary?.planned ?? 0} по плану. Отгрузка будет проведена с расхождением.
          </Typography>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setMpShipConfirmOpen(false)} disabled={modalBusy}>
            Отмена
          </Button>
          <Button
            variant="contained"
            color="warning"
            disabled={modalBusy}
            onClick={() => void shipMpUnload(true)}
            data-testid="ff-mp-ship-ack-discrepancy"
          >
            Завершить
          </Button>
        </DialogActions>
      </Dialog>
      <Dialog
        open={mpAttachConfirmOpen}
        onClose={() => {
          setMpAttachConfirmOpen(false)
          setPendingAttachBarcode(null)
        }}
        data-testid="ff-mp-attach-box-dialog"
      >
        <DialogTitle>Добавить готовый короб?</DialogTitle>
        <DialogContent>
          <Typography variant="body2">
            Весь короб будет добавлен в отгрузку со всем содержимым.
          </Typography>
        </DialogContent>
        <DialogActions>
          <Button
            onClick={() => {
              setMpAttachConfirmOpen(false)
              setPendingAttachBarcode(null)
            }}
            disabled={modalBusy}
          >
            Отмена
          </Button>
          <Button
            variant="contained"
            disabled={modalBusy}
            onClick={() => void confirmAttachBox()}
            data-testid="ff-mp-attach-box-confirm"
          >
            Добавить
          </Button>
        </DialogActions>
      </Dialog>
      <Dialog
        open={mpAttachOverPlanOpen}
        onClose={() => {
          setMpAttachOverPlanOpen(false)
          setPendingAttachBarcode(null)
        }}
        data-testid="ff-mp-attach-over-plan-dialog"
      >
        <DialogTitle>Больше, чем в плане</DialogTitle>
        <DialogContent>
          <Typography variant="body2">
            В коробе больше товара, чем осталось по плану отгрузки. Добавить всё содержимое короба?
          </Typography>
        </DialogContent>
        <DialogActions>
          <Button
            onClick={() => {
              setMpAttachOverPlanOpen(false)
              setPendingAttachBarcode(null)
            }}
            disabled={modalBusy}
          >
            Отмена
          </Button>
          <Button
            variant="contained"
            color="warning"
            disabled={modalBusy}
            onClick={() => void confirmAttachBoxOverPlan()}
            data-testid="ff-mp-attach-over-plan-confirm"
          >
            Добавить всё
          </Button>
        </DialogActions>
      </Dialog>
      <Dialog
        open={mpCancelConfirmOpen}
        onClose={() => setMpCancelConfirmOpen(false)}
        data-testid="ff-mp-cancel-unload-dialog"
      >
        <DialogTitle>Отменить отгрузку?</DialogTitle>
        <DialogContent>
          <Typography variant="body2">
            {addressStorageEnabled ? 'Товар из коробов вернётся на сортировку — его нужно будет заново распределить по ячейкам или использовать в других документах.' : 'Товар из коробов вернётся в остаток — его можно будет использовать в других документах.'}
          </Typography>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setMpCancelConfirmOpen(false)} disabled={modalBusy}>
            Назад
          </Button>
          <Button
            variant="contained"
            color="error"
            disabled={modalBusy}
            onClick={() => void cancelMpUnload()}
            data-testid="ff-mp-cancel-unload-confirm"
          >
            Отменить отгрузку
          </Button>
        </DialogActions>
      </Dialog>
      <BoxLabelPrintDialog
        open={printBoxTarget !== null}
        title="Печать штрихкода короба"
        busy={modalBusy}
        onClose={() => setPrintBoxTarget(null)}
        onConfirm={confirmPrintBoxBarcode}
        testId="ff-mp-box-print-dialog"
      />
    </Box>
  )
}
