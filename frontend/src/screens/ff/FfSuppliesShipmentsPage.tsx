import { useCallback, useEffect, useMemo, useRef, useState, type MouseEvent } from 'react'
import { useSearchParams } from 'react-router-dom'
import { useBarcodeScanner } from '../../hooks/useBarcodeScanner'
import { DeleteOutlineOutlined, MoreVertOutlined } from '@mui/icons-material'
import {
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
import { FfProductLineCells, FfProductTableHeadCells } from '../../components/FfProductLineCells'
import { WbProductPickerDialog, type WbProductPickerCatalogRow } from '../../components/WbProductPickerDialog'
import { useWbProductCatalog } from '../../hooks/useWbProductCatalog'
import { apiUrl } from '../../api'
import { WmsDateField } from '../../components/WmsDateField'
import { productDisplayMetaFromCatalog } from '../../types/wbProductCatalog'
import { resolveProductIdByBarcode } from '../../utils/resolveProductByBarcode'
import { readApiErrorMessage } from '../../utils/readApiErrorMessage'
import { PageHeader } from '../../ui/PageHeader'
import type { FfInboundSummary, FfOutboundSummary } from './FfDashboard'
import {
  FfPackagingTaskPanel,
  type PackagingTask,
} from './FfPackagingPage'
import { FfMarketplaceUnloadBoxAddDialog } from './FfMarketplaceUnloadBoxAddDialog'
import { formatHumanDocumentNumber } from './documentDisplay'
import { formatDateTimeLocal } from '../../utils/formatDateTimeLocal'
import { printMarketplaceUnloadWaybill } from '../../utils/printShipmentWaybill'
import { printBarcodeLabel } from '../../utils/printBarcodeLabel'
import { renderBarcodeDataUrl } from '../../utils/renderBarcodeDataUrl'
import {
  printShipmentPackagingSheet,
  type PackagingSheetItem,
} from '../../utils/printShipmentPackagingSheet'
import { resolveProductPrimaryBarcode } from '../../types/wbProductCatalog'

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

type MpUnloadTab = 'products' | 'packaging'

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
  extraLabel: string | null
  ffModified: boolean
}

function statusRu(status: string): string {
  if (status === 'draft') return 'Черновик'
  if (status === 'confirmed') return 'Утверждено'
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

function kindRu(kind: DocKind): string {
  if (kind === 'inbound') return 'Приёмка'
  if (kind === 'outbound') return 'Отгрузка'
  if (kind === 'marketplace_unload') return 'Отгрузка на МП'
  return 'Расхождение'
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
  onCreateMpShipment: (sellerId: string) => Promise<{ id: string } | null>
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
  const [sortKey, setSortKey] = useState<'planned_desc' | 'planned_asc' | 'created_desc' | 'created_asc'>(
    'created_desc',
  )

  const [docModal, setDocModal] = useState<null | 'marketplace_unload' | 'discrepancy_act'>(null)
  const [docModalId, setDocModalId] = useState<string | null>(null)
  const [mpUnloadTab, setMpUnloadTab] = useState<MpUnloadTab>('products')
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
  const { catalog, catalogById, reload: reloadWbCatalog } = useWbProductCatalog(
    token,
    docModal === 'marketplace_unload',
    mpCatalogSellerId,
  )
  const [confirmDate, setConfirmDate] = useState<string>('')
  const [boxMenuAnchor, setBoxMenuAnchor] = useState<null | HTMLElement>(null)
  const [boxMenuTargetId, setBoxMenuTargetId] = useState<string | null>(null)
  const [boxAddDialogBoxId, setBoxAddDialogBoxId] = useState<string | null>(null)
  const [boxAddSuccessMsg, setBoxAddSuccessMsg] = useState<string | null>(null)
  const mpTabInitForRef = useRef<string | null>(null)

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
    setModalBusy(true)
    setModalError(null)
    try {
      if (docModal === 'marketplace_unload') {
        const res = await fetch(apiUrl(`/operations/marketplace-unload-requests/${docModalId}`), {
          headers: authHeaders,
        })
        if (!res.ok) {
          setModalError(await readApiErrorMessage(res))
          setUnloadDetail(null)
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
        const stockRes = await fetch(
          apiUrl(`/operations/inventory-balances/summary?${stockParams.toString()}`),
          { headers: authHeaders },
        )
        if (stockRes.ok) {
          const stockRows = (await stockRes.json()) as {
            product_id: string
            sku_code: string
            product_name: string
            available: number
          }[]
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
          setWarehouseAvailableProductPicklist([])
        }
        setDivergeDetail(null)
      } else {
        setWarehouseAvailableProductPicklist([])
        const res = await fetch(apiUrl(`/operations/discrepancy-acts/${docModalId}`), {
          headers: authHeaders,
        })
        if (!res.ok) {
          setModalError(await readApiErrorMessage(res))
          setDivergeDetail(null)
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
      setModalError(e instanceof Error ? e.message : 'Не удалось загрузить документ.')
      setUnloadDetail(null)
      setDivergeDetail(null)
    } finally {
      setModalBusy(false)
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
    setUnloadDetail(null)
    setDivergeDetail(null)
    setModalError(null)
    setDocModal('marketplace_unload')
    setDocModalId(openMp)
    const next = new URLSearchParams(searchParams)
    next.delete('open_mp')
    setSearchParams(next, { replace: true })
  }, [isMpShipmentsPage, searchParams, setSearchParams])

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
    setMpUnloadTab('products')
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
    const created = await onCreateMpShipment(mpCreateSellerId)
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
    if (!token || !authHeaders || docModal !== 'marketplace_unload' || !docModalId) {
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
    if (!token || !authHeaders || docModal !== 'marketplace_unload' || !docModalId) {
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
    const raw = (rawInput ?? scanBarcode).trim()
    if (!raw) {
      setModalError('Введите штрихкод готового короба (WHB-…).')
      return
    }
    if (!raw.startsWith('WHB-') && !raw.startsWith('INB-')) {
      setModalError(
        'На этой строке сканируют только готовый короб (WHB-…). Для ячейки или товара откройте «Добавить товары» у короба.',
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
    setBoxMenuAnchor(event.currentTarget)
    setBoxMenuTargetId(boxId)
  }

  const closeBoxMenu = () => {
    setBoxMenuAnchor(null)
    setBoxMenuTargetId(null)
  }

  const printBoxBarcode = (box: MarketplaceUnloadBox) => {
    const barcode = box.internal_barcode?.trim()
    if (!barcode) {
      setModalError('У короба нет штрихкода.')
      return
    }
    printBarcodeLabel({
      title: 'Короб отгрузки',
      barcode,
      barcodeDataUrl: renderBarcodeDataUrl(barcode),
    })
  }

  const printPackagingSheet = () => {
    if (!unloadDetail || unloadDetail.lines.length === 0) {
      setModalError('Нет товаров для печати.')
      return
    }
    const items: PackagingSheetItem[] = unloadDetail.lines.map((ln) => {
      const cat = catalogById.get(ln.product_id)
      return {
        product_name: ln.product_name,
        vendor_code: cat?.wb_vendor_code ?? '',
        sku_code: ln.sku_code,
        barcode: cat ? resolveProductPrimaryBarcode(cat) || null : null,
        wb_nm_id: cat?.wb_nm_id ?? null,
        photo_url: cat?.wb_primary_image_url ?? null,
        instructions: cat?.packaging_instructions ?? null,
      }
    })
    printShipmentPackagingSheet({
      documentNumber: unloadDisplayNumber ?? '—',
      sellerName: unloadDetail.seller_name,
      items,
    })
  }

  const copyBox = async (boxId: string) => {
    if (!token || !authHeaders || docModal !== 'marketplace_unload' || !docModalId) {
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
      await onRefreshFfSupplyExtras()
    } catch (e) {
      setModalError(e instanceof Error ? e.message : 'Не удалось скопировать короб.')
    } finally {
      setModalBusy(false)
    }
  }

  const deleteBox = async (boxId: string) => {
    if (!token || !authHeaders || docModal !== 'marketplace_unload' || !docModalId) {
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
      await onRefreshFfSupplyExtras()
    } catch (e) {
      setModalError(e instanceof Error ? e.message : 'Не удалось удалить короб.')
    } finally {
      setModalBusy(false)
    }
  }

  const removeBoxLine = async (boxId: string, lineId: string) => {
    if (!token || !authHeaders || docModal !== 'marketplace_unload' || !docModalId) {
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

  const mpBoxesReadOnly =
    docModal === 'marketplace_unload' && unloadDetail?.status === 'shipped'

  const mpVisibleBoxes = useMemo(() => {
    const boxes = unloadDetail?.boxes ?? []
    return boxes.filter((box) => box.lines.length > 0 || Boolean(box.internal_barcode?.trim()))
  }, [unloadDetail?.boxes])

  const mpBoxesWithLines = useMemo(
    () => mpVisibleBoxes.filter((box) => box.lines.length > 0),
    [mpVisibleBoxes],
  )

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

  const mpBoxTableHeadCellSx = {
    fontWeight: 600,
    color: 'text.secondary',
    bgcolor: 'transparent',
    borderBottom: 1,
    borderColor: 'divider',
    py: 0.75,
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

  const mpBoxTableSx = {
    tableLayout: 'fixed',
    width: '100%',
  }

  const renderBoxActions = (box: MarketplaceUnloadBox) => {
    const totalQty = box.lines.reduce((sum, ln) => sum + ln.quantity, 0)
    return (
      <Stack direction="row" spacing={0.5} sx={mpBoxActionsSx}>
        <Button
          size="small"
          variant="outlined"
          disabled={modalBusy || mpBoxesReadOnly}
          onClick={() => setBoxAddDialogBoxId(box.id)}
          data-testid={`ff-mp-box-add-products-${box.id}`}
        >
          Наполнить
        </Button>
        <IconButton
          size="small"
          aria-label="Действия с коробом"
          data-testid={`ff-mp-box-menu-${box.id}`}
          disabled={modalBusy}
          onClick={(e) => openBoxMenu(e, box.id)}
        >
          <MoreVertOutlined fontSize="small" />
        </IconButton>
        <IconButton
          size="small"
          aria-label="Печать ШК короба"
          data-testid={`ff-mp-box-print-${box.id}`}
          disabled={modalBusy || !box.internal_barcode}
          onClick={() => printBoxBarcode(box)}
        >
          <Typography variant="caption" sx={{ fontWeight: 700 }}>
            ШК
          </Typography>
        </IconButton>
        <IconButton
          size="small"
          aria-label="Удалить пустой короб"
          data-testid={`ff-mp-box-delete-${box.id}`}
          disabled={modalBusy || totalQty > 0}
          onClick={() => void deleteBox(box.id)}
        >
          <DeleteOutlineOutlined fontSize="small" />
        </IconButton>
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
            <Typography variant="body2" color="text.secondary" sx={{ minWidth: 0 }}>
              {box.box_preset}
              {boxBarcode ? ` · ${boxBarcode}` : ''}
              {!hasLines ? ' · готов к наполнению' : ''}
            </Typography>
          </Box>
          {renderBoxActions(box)}
        </Box>

        {hasLines ? (
          <Box sx={{ ...mpBoxBodySx, ...mpBoxTableWrapSx, mt: 0 }}>
              <Table
                size="small"
                sx={mpBoxTableSx}
                data-testid={tableTestId ?? `ff-mp-box-lines-${box.id}`}
              >
                <TableHead>
                  <TableRow>
                    <TableCell sx={{ ...mpBoxTableHeadCellSx, width: '28%' }}>Артикул</TableCell>
                    <TableCell sx={mpBoxTableHeadCellSx}>Товар</TableCell>
                    <TableCell align="right" sx={{ ...mpBoxTableHeadCellSx, width: 104 }}>
                      В коробе
                    </TableCell>
                    <TableCell align="right" sx={{ ...mpBoxTableHeadCellSx, width: 64 }} />
                  </TableRow>
                </TableHead>
                <TableBody>
                  {box.lines.map((ln) => (
                    <TableRow key={ln.id}>
                      <TableCell sx={{ overflow: 'hidden', textOverflow: 'ellipsis' }}>
                        {ln.sku_code}
                      </TableCell>
                      <TableCell sx={{ overflow: 'hidden', textOverflow: 'ellipsis' }}>
                        {ln.product_name}
                      </TableCell>
                      <TableCell align="right">{ln.quantity}</TableCell>
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
                    </TableRow>
                  ))}
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
    if (!Number.isInteger(q) || q < 1) {
      setModalError('Укажите целое количество ≥ 1.')
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
    setMpUnloadTab('products')
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
    const distributed = unloadDetail.lines.reduce((sum, ln) => sum + (ln.picked_qty ?? 0), 0)
    return {
      planned,
      distributed,
      remaining: planned - distributed,
      packed: unloadDetail.linked_packaging_task
        ? `${unloadDetail.linked_packaging_task.qty_done}/${unloadDetail.linked_packaging_task.qty_total}`
        : null,
    }
  }, [unloadDetail, docModal])

  const draftDoc =
    mpDraft ||
    mpSubmitted ||
    (docModal === 'discrepancy_act' && divergeDetail?.status === 'draft')
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
      mpUnloadTab === 'products' &&
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
      mpUnloadTab === 'products' &&
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
                  {statusRu(row.status)}
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
                <TableCell sx={{ color: 'text.secondary', maxWidth: 200 }}>{row.extraLabel ?? '—'}</TableCell>
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
                  {mpLineDraft ? (
                    <>
                      <FormControl
                        size="small"
                        sx={{ minWidth: 280, width: { xs: '100%', sm: 'auto' } }}
                        disabled={modalBusy || wbMpWarehousesBusy}
                      >
                        <InputLabel id="ff-mp-wb-warehouse-header">Склад WB (маркетплейс)</InputLabel>
                        <Select
                          labelId="ff-mp-wb-warehouse-header"
                          label="Склад WB (маркетплейс)"
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
                  ) : (
                    <Typography variant="body2" color="text.secondary" data-testid="ff-mp-wb-warehouse-readonly">
                      Склад WB:{' '}
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
                  <Typography variant="caption" color="text.secondary">
                    В коробах / распределено
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
                    Осталось
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
                    Упаковано
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
            <Box sx={{ mb: 2 }}>
              <Tabs
                value={mpUnloadTab}
                onChange={(_e, value: MpUnloadTab) => setMpUnloadTab(value)}
                variant="scrollable"
                scrollButtons="auto"
                sx={{ borderBottom: 1, borderColor: 'divider', mb: 2 }}
              >
                <Tab label="Товары" value="products" data-testid="ff-mp-tab-products" />
                <Tab
                  label="Упаковка"
                  value="packaging"
                  disabled={!unloadDetail.linked_packaging_task}
                  data-testid="ff-mp-tab-packaging"
                />

              </Tabs>
              {mpUnloadTab === 'products' ? (
                <Stack spacing={2}>
                  {unloadDetail.seller_name ? (
                    <Typography variant="body2" color="text.secondary">
                      Селлер: <strong>{unloadDetail.seller_name}</strong>
                    </Typography>
                  ) : null}
                  {mpLineDraft && mpDraft ? (
                    <Paper variant="outlined" sx={{ p: 1.5 }} data-testid="ff-mp-add-products-panel">
                      <Typography variant="subtitle2" sx={{ mb: 1.25 }}>
                        Добавление товаров
                      </Typography>
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
                            disabled={modalBusy || !mpLineBarcodeScan.trim()}
                            onClick={() => void addMpLineByBarcode()}
                            data-testid="ff-mp-line-barcode-add"
                          >
                            Добавить по ШК
                          </Button>
                        </Stack>
                        <Button
                          variant="contained"
                          disabled={modalBusy}
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
                          <>
                            <TableCell align="right">Распределено</TableCell>
                            <TableCell align="right">Осталось</TableCell>
                          </>
                        ) : null}
                        {draftDoc ? <TableCell align="right" width={56} /> : null}
                      </TableRow>
                    </TableHead>
                    <TableBody>
                      {(() => {
                        const lines = unloadDetail.lines
                        const productCols = 6
                        const mpCols = mpExecutionPhase ? 2 : 0
                        const emptySpan = productCols + 1 + mpCols + (draftDoc ? 1 : 0)
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
                          const displayMeta = productDisplayMetaFromCatalog(
                            ln.product_id,
                            ln,
                            catalogById,
                          )
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
                                <>
                                  <TableCell
                                    align="right"
                                    data-testid={`ff-mp-line-picked-${ln.id}`}
                                  >
                                    {picked}
                                  </TableCell>
                                  <TableCell
                                    align="right"
                                    data-testid={`ff-mp-line-remaining-${ln.id}`}
                                  >
                                    {remaining}
                                  </TableCell>
                                </>
                              ) : null}
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
                  {unloadDetail.lines.length > 0 ? (
                    <Stack
                      direction="row"
                      spacing={1}
                      useFlexGap
                      data-testid="ff-mp-print-actions"
                      sx={{ mt: 1, flexWrap: 'wrap' }}
                    >
                      <Button
                        variant="outlined"
                        size="small"
                        disabled={modalBusy}
                        data-testid="ff-mp-print-waybill"
                        onClick={() => {
                            const wbName =
                              wbMpWarehouses.find(
                                (w) => w.wb_warehouse_id === unloadDetail.wb_mp_warehouse_id,
                              )?.name ?? null
                            printMarketplaceUnloadWaybill({
                              documentId: unloadDetail.id,
                              statusLabel: statusRu(unloadDetail.status),
                              warehouseName: unloadDetail.warehouse_name,
                              sellerName: unloadDetail.seller_name,
                              wbWarehouseLabel:
                                wbName != null && unloadDetail.wb_mp_warehouse_id != null
                                  ? `${wbName} (${unloadDetail.wb_mp_warehouse_id})`
                                  : null,
                              plannedDate: unloadDetail.planned_shipment_date,
                              createdAt: unloadDetail.created_at
                                ? formatDateTimeLocal(unloadDetail.created_at)
                                : null,
                              lines: unloadDetail.lines.map((ln) => ({
                                sku_code: ln.sku_code,
                                product_name: ln.product_name,
                                quantity: ln.quantity,
                              })),
                              pickAllocations: unloadDetail.pick_allocations.map((a) => ({
                                location_code: a.location_code,
                                sku_code: a.sku_code,
                                quantity: a.quantity,
                              })),
                            })
                          }}
                        >
                          Печать накладной
                        </Button>
                      <Button
                        variant="outlined"
                        size="small"
                        disabled={modalBusy}
                        data-testid="ff-mp-print-tz"
                        onClick={printPackagingSheet}
                      >
                        Печать ТЗ
                      </Button>
                    </Stack>
                  ) : null}
                  <Box data-testid="ff-mp-boxes">
              {(() => {
                const allBoxes = mpVisibleBoxes
                return (
                  <Stack spacing={1.5}>
                    <Typography variant="subtitle2">Сборка в короба</Typography>
                    <Typography variant="body2" color="text.secondary">
                      Сканируйте WHB готового короба, чтобы привязать его к отгрузке. Новые короба
                      создавайте только при необходимости.
                    </Typography>

                    {mpExecutionPhase ? (
                      <Paper variant="outlined" sx={{ p: 1.5 }}>
                        <Stack spacing={1.25}>
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

                          {allBoxes.length > 0 ? (
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
                          ) : null}

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
                              onClick={() => void createBox()}
                              disabled={modalBusy}
                              data-testid="ff-mp-box-batch-create"
                            >
                              {Number(boxBatchCount) === 1 ? 'Создать короб' : 'Создать короба'}
                            </Button>
                          </Stack>
                        </Stack>
                      </Paper>
                    ) : null}

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
                            printBoxBarcode(box)
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
                  </Stack>
                )
              })()}
            </Box>

                </Stack>
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
                      task={packagingTask}
                      hideDocumentHeader
                      onUpdated={(task) => {
                        setPackagingTask(task)
                        void loadDocDetail()
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
                </Box>
              ) : null}
            </Box>
          ) : null}
          {divergeDetail ? (
            <Typography variant="body2" color="text.secondary" sx={{ mb: 1 }}>
              {statusRu(divergeDetail.status)}
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
                <TableCell align="right">План</TableCell>
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
                  const displayMeta = productDisplayMetaFromCatalog(ln.product_id, ln, catalogById)
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
                      <TableCell align="right">{ln.quantity}</TableCell>
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
                      {'available' in p ? ` · доступно ${p.available}` : ''}
                    </MenuItem>
                  ))}
                </Select>
              </FormControl>
              <TextField
                size="small"
                label="Количество"
                type="number"
                slotProps={{ htmlInput: { min: 1 } }}
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
          sx={{ flexWrap: 'wrap', gap: 1, justifyContent: 'space-between' }}
          data-testid="ff-mp-footer-bar"
        >
          <Stack direction="row" spacing={1} sx={{ flexWrap: 'wrap' }}>
            {docModal === 'marketplace_unload' && unloadDetail && (mpDraft || mpSubmitted) ? (
              <>
                <Button
                  variant="contained"
                  color="secondary"
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
                <Button
                  variant="contained"
                  color="primary"
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
                Утвердить заявку
              </Button>
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
        getAvailable={mpPickerGetAvailable}
        filterRow={mpPickerFilterRow}
        emptyMessage="Нет товаров с остатком у выбранного селлера."
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
          readOnly={mpBoxesReadOnly}
          token={token}
          addressStorageEnabled={addressStorageEnabled}
          catalogById={catalogById}
          warehouseStockByProductId={mpStockByProductId}
          onUpdated={async () => {
            await loadDocDetail()
            await onRefreshFfSupplyExtras()
          }}
          onAddSuccess={(quantity) =>
            setBoxAddSuccessMsg(`Добавлено ${quantity} шт`)
          }
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
            Товар из коробов вернётся на сортировку — его нужно будет заново распределить по
            ячейкам или использовать в других документах.
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
    </Box>
  )
}
