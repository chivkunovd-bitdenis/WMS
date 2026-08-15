import { useCallback, useEffect, useMemo, useRef, useState, type FocusEvent, type KeyboardEvent } from 'react'
import { useBarcodeScanner } from '../../hooks/useBarcodeScanner'
import EditOutlined from '@mui/icons-material/EditOutlined'
import ExpandMoreOutlined from '@mui/icons-material/ExpandMoreOutlined'
import PrintOutlined from '@mui/icons-material/PrintOutlined'
import StraightenOutlined from '@mui/icons-material/StraightenOutlined'
import {
  Accordion,
  AccordionDetails,
  AccordionSummary,
  Alert,
  Box,
  Button,
  Chip,
  CircularProgress,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  FormControl,
  FormControlLabel,
  GlobalStyles,
  IconButton,
  InputLabel,
  MenuItem,
  Paper,
  Select,
  Snackbar,
  Stack,
  Switch,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  TextField,
  Tooltip,
  Typography,
} from '@mui/material'
import { alpha } from '@mui/material/styles'
import { apiUrl } from '../../api'
import { FfProductMarkingPrintProvider } from '../../components/FfProductMarkingPrintProvider'
import { ProductBarcodePrintButton } from '../../components/ProductBarcodePrintButton'
import { ProductPhotoThumb } from '../../components/ProductPhotoThumb'
import { WbProductPickerDialog } from '../../components/WbProductPickerDialog'
import { WmsDateField } from '../../components/WmsDateField'
import {
  formatProductBarcodeDisplay,
  productDisplayMetaFromCatalog,
  type ProductLineDisplayMeta,
  type WbProductCatalogRow,
} from '../../types/wbProductCatalog'
import { printBarcodeLabel } from '../../utils/printBarcodeLabel'
import { printInboundSupplyWaybill } from '../../utils/printShipmentWaybill'
import { readApiErrorMessage } from '../../utils/readApiErrorMessage'
import { inboundOperationTypeLabel } from '../../utils/inboundOperationType'
import { FfInboundBoxAddDialog } from './FfInboundBoxAddDialog'
import { FfInboundSortingPanel } from './FfInboundSortingPanel'
import { BoxImportDialog } from '../../components/BoxImportDialog'
import {
  buildInboundDiscrepancyLines,
  buildInboundReceivingTotals,
  effectiveActualQty,
  inboundStatusRu,
  integerQtyError,
  isDoneStatus,
  isReceivingStatus,
  isSortingStatus,
  looseQtyFromDisplayedTotal,
  parseIntegerQty,
  scanErrorMessageRu,
} from './inboundReceivingHelpers'
import { suggestNextLocationCode } from '../../utils/suggestNextLocationCode'
import { renderBarcodeDataUrl } from '../../utils/renderBarcodeDataUrl'
import { resolveProductIdByBarcode } from '../../utils/resolveProductByBarcode'
import { formatHumanDocumentNumber } from './documentDisplay'

type LocationRow = { id: string; code: string; warehouse_id: string; barcode: string }
type WarehouseRow = { id: string; name: string; code: string }
type SellerRow = { id: string; name: string }

type InboundBoxLine = {
  id: string
  product_id: string
  sku_code: string
  product_name: string
  quantity: number
  posted_qty?: number
  remaining_qty?: number
}

type InboundBox = {
  id: string
  box_number: number
  internal_barcode: string
  label_printed_at: string | null
  intake_opened_at: string | null
  intake_closed_at: string | null
  is_open: boolean
  remaining_qty?: number
  lines: InboundBoxLine[]
}

type InboundCargoPlace = {
  id: string
  place_number: number
  internal_barcode: string
  label_printed_at: string | null
  created_at: string
}

type InboundLine = {
  id: string
  product_id: string
  sku_code: string
  product_name: string
  wb_barcode: string | null
  requires_honest_sign: boolean
  length_mm: number | null
  width_mm: number | null
  height_mm: number | null
  weight_g: number | null
  volume_liters: number | null
  added_by_fulfillment: boolean
  expected_qty: number
  actual_qty: number | null
  effective_actual_qty?: number | null
  posted_qty: number
  storage_location_id: string | null
  storage_location_code: string | null
}

type DiscrepancyActLine = {
  id: string
  product_id: string
  sku_code: string
  product_name: string
  quantity: number
  inbound_intake_line_id: string | null
}

type DiscrepancyActDetail = {
  id: string
  status: string
  inbound_intake_request_id: string | null
  created_at: string
  lines: DiscrepancyActLine[]
}

function discrepancyActStatusRu(status: string): string {
  if (status === 'draft') return 'Черновик'
  if (status === 'confirmed') return 'Передан на FF'
  if (status === 'approved') return 'Утверждено'
  if (status === 'rejected') return 'Отклонено'
  return status
}

function discrepancyActTitle(createdAt: string): string {
  const date = new Date(createdAt)
  if (Number.isNaN(date.getTime())) return 'Акт расхождения'
  return `Акт от ${new Intl.DateTimeFormat('ru-RU', {
    day: '2-digit',
    month: '2-digit',
    year: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  }).format(date)}`
}

function signedQty(value: number): string {
  return value > 0 ? `+${value}` : String(value)
}

type InboundProductLineCellProps = {
  meta: ProductLineDisplayMeta
  productId: string
  printTestId: string
}

function InboundProductLineCell({ meta, productId, printTestId }: InboundProductLineCellProps) {
  const barcode = formatProductBarcodeDisplay(meta)

  return (
    <TableCell sx={{ minWidth: 0, overflow: 'hidden' }}>
      <Stack direction="row" spacing={1} sx={{ alignItems: 'center', minWidth: 0 }}>
        <Box sx={{ flex: '0 0 44px', display: 'flex' }}>
          <ProductPhotoThumb
            src={meta.wb_primary_image_url}
            alt={meta.product_name}
            testId="ff-inbound-line-photo"
          />
        </Box>
        <Box sx={{ flex: '1 1 auto', minWidth: 0 }}>
          <Typography
            variant="body2"
            sx={{
              fontWeight: 700,
              overflow: 'hidden',
              textOverflow: 'ellipsis',
              whiteSpace: 'nowrap',
            }}
            title={meta.product_name}
            data-testid="ff-inbound-line-product-name"
          >
            {meta.product_name}
          </Typography>
          <Stack
            direction={{ xs: 'column', sm: 'row' }}
            spacing={{ xs: 0, sm: 1 }}
            sx={{ minWidth: 0 }}
          >
            <Typography
              variant="caption"
              color="text.secondary"
              sx={{
                flex: '1 1 0',
                minWidth: 0,
                overflow: 'hidden',
                textOverflow: 'ellipsis',
                whiteSpace: 'nowrap',
              }}
              title={meta.sku_code}
              data-testid="ff-inbound-line-sku"
            >
              SKU {meta.sku_code}
            </Typography>
            <Typography
              variant="caption"
              color="text.secondary"
              sx={{
                flex: '1 1 0',
                minWidth: 0,
                overflow: 'hidden',
                textOverflow: 'ellipsis',
                whiteSpace: 'nowrap',
              }}
              title={barcode !== '—' ? barcode : undefined}
              data-testid="ff-inbound-line-barcode"
            >
              ШК {barcode}
            </Typography>
          </Stack>
        </Box>
        <Box sx={{ flex: '0 0 40px', display: 'flex', justifyContent: 'center' }}>
          <ProductBarcodePrintButton
            meta={meta}
            testId={printTestId}
            productId={productId}
            printSource="catalog"
          />
        </Box>
      </Stack>
    </TableCell>
  )
}

type InboundDetail = {
  id: string
  document_number: string | null
  display_number?: string | null
  public_number?: string | null
  human_number?: string | null
  warehouse_id: string
  status: string
  operation_type: 'inbound' | 'return'
  planned_delivery_date: string | null
  planned_box_count: number | null
  actual_box_count: number | null
  boxes_discrepancy: boolean
  has_discrepancy: boolean
  seller_id?: string | null
  seller_name?: string | null
  created_at?: string | null
  distribution_completed_at: string | null
  sorting_remaining_qty?: number
  boxes: InboundBox[]
  cargo_places: InboundCargoPlace[]
  lines: InboundLine[]
}

type DistributionLineOut = {
  id: string
  product_id: string
  storage_location_id: string
  storage_location_code: string
  quantity: number
  created_at: string
}

type DistributionLineDraft = {
  box_id: string
  product_id: string
  storage_location_id: string
  quantity: string
}

type CellLocationHint = {
  storage_location_id: string
  storage_location_code: string
  quantity: number
  reserved: number
  available: number
}

export type WbCatalogRow = WbProductCatalogRow

export type InboundRequestWorkspace = 'reception' | 'sorting' | 'full'

function inboundWorkspaceTitle(workspace: InboundRequestWorkspace): string {
  return workspace === 'sorting' ? 'Сортировка' : 'Приёмка'
}

function formatLineDiscrepancy(expectedQty: number, actualQty: number): string | null {
  const delta = actualQty - expectedQty
  if (delta > 0) {
    return `Излишек ${delta}`
  }
  if (delta < 0) {
    return `Недостача ${Math.abs(delta)}`
  }
  return null
}

function inboundStatusChipColor(
  status: string,
): 'default' | 'primary' | 'secondary' | 'success' | 'warning' | 'info' {
  if (status === 'draft') return 'default'
  if (status === 'submitted') return 'info'
  if (isReceivingStatus(status)) return 'warning'
  if (isSortingStatus(status)) return 'secondary'
  if (isDoneStatus(status)) return 'success'
  return 'primary'
}

type Props = {
  token: string
  requestId: string
  isFulfillmentAdmin: boolean
  workspace?: InboundRequestWorkspace
  sellers?: SellerRow[]
  onClose: () => void
  addressStorageEnabled?: boolean
}

export function FfInboundRequestView({
  token,
  requestId,
  isFulfillmentAdmin,
  workspace = 'full',
  onClose,
  addressStorageEnabled = true,
}: Props) {
  const authHeaders = useMemo(() => ({ Authorization: `Bearer ${token}` }), [token])

  const [detail, setDetail] = useState<InboundDetail | null>(null)
  const [catalog, setCatalog] = useState<WbCatalogRow[] | null>(null)
  const [locations, setLocations] = useState<LocationRow[]>([])
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [actualDraftByLineId, setActualDraftByLineId] = useState<Record<string, string>>({})
  const [actualDraftErrorByLineId, setActualDraftErrorByLineId] = useState<Record<string, string>>({})
  const actualDraftRef = useRef(actualDraftByLineId)
  const actualInputRefs = useRef<Record<string, HTMLInputElement | null>>({})

  const [distOpen, setDistOpen] = useState(false)
  const [distBusy, setDistBusy] = useState(false)
  const [distError, setDistError] = useState<string | null>(null)
  const [distLines, setDistLines] = useState<DistributionLineDraft[]>([])
  const [cellHintsByProductId, setCellHintsByProductId] = useState<Record<string, CellLocationHint[]>>({})

  const [pickerOpen, setPickerOpen] = useState(false)
  const [pickerInitialSearch, setPickerInitialSearch] = useState('')
  const [dimensionsLine, setDimensionsLine] = useState<InboundLine | null>(null)
  const [dimensionDraft, setDimensionDraft] = useState({ length: '', width: '', height: '', weight: '' })
  const [dimensionError, setDimensionError] = useState<string | null>(null)
  const [returnAutoPrint, setReturnAutoPrint] = useState(false)

  const [plannedDateDraft, setPlannedDateDraft] = useState<string>('')
  const [manualEditLineId, setManualEditLineId] = useState<string | null>(null)
  const [boxAddDialogBoxId, setBoxAddDialogBoxId] = useState<string | null>(null)
  const [finishConfirmOpen, setFinishConfirmOpen] = useState(false)
  const [scanToastError, setScanToastError] = useState<string | null>(null)
  const [scanAddBarcode, setScanAddBarcode] = useState<string | null>(null)
  const [importSuccessMsg, setImportSuccessMsg] = useState<string | null>(null)
  const [boxImportOpen, setBoxImportOpen] = useState(false)
  const [packagesExpanded, setPackagesExpanded] = useState(false)
  const [cargoDialogOpen, setCargoDialogOpen] = useState(false)
  const [cargoCount, setCargoCount] = useState('1')
  const [cargoError, setCargoError] = useState<string | null>(null)
  const [closeConfirmOpen, setCloseConfirmOpen] = useState(false)
  const [saveSuccessMsg, setSaveSuccessMsg] = useState<string | null>(null)
  const [newLocationCode, setNewLocationCode] = useState('')
  const [requestWarehouse, setRequestWarehouse] = useState<WarehouseRow | null>(null)
  const [linkedDiscrepancyActs, setLinkedDiscrepancyActs] = useState<DiscrepancyActDetail[]>([])
  const [discrepancyActsBusy, setDiscrepancyActsBusy] = useState(false)
  const [discrepancyActsError, setDiscrepancyActsError] = useState<string | null>(null)
  const loadDetailSeq = useRef(0)

  const sortingView = workspace === 'sorting'
  const plannedDateFieldEnabled = false
  const waybillPrintEnabled = false
  const boxImportEnabled = false
  const documentDistributionEnabled = false
  const receptionClosed =
    detail != null && (isSortingStatus(detail.status) || isDoneStatus(detail.status))
  const receivingActive =
    detail != null &&
    (detail.status === 'submitted' || isReceivingStatus(detail.status))
  const isReturnOperation = detail?.operation_type === 'return'
  const operationTypeLabel = inboundOperationTypeLabel(detail?.operation_type)
  const showInboundLinesTable = !sortingView || receptionClosed

  // Глобальный скан: панель приёмки видна и диалог короба не открыт
  useBarcodeScanner({
    enabled:
      isFulfillmentAdmin &&
      !sortingView &&
      receivingActive &&
      boxAddDialogBoxId == null &&
      !pickerOpen &&
      dimensionsLine == null,
    onScan: (code) => {
      void scanToReceiving(code)
    },
  })

  useBarcodeScanner({
    enabled:
      isFulfillmentAdmin &&
      !sortingView &&
      detail?.status === 'draft' &&
      boxAddDialogBoxId == null &&
      !pickerOpen &&
      dimensionsLine == null,
    onScan: (code) => {
      void addLineByBarcode(code)
    },
  })
  const defaultPutawayBoxId = useMemo(() => {
    const withQty = (detail?.boxes ?? []).filter((b) =>
      b.lines.some((ln) => ln.quantity > 0),
    )
    if (withQty.length === 1) {
      return withQty[0]!.id
    }
    return ''
  }, [detail?.boxes])

  const sortingRemainingTotal = useMemo(() => {
    if (!detail) return 0
    if (detail.sorting_remaining_qty != null) {
      return detail.sorting_remaining_qty
    }
    return detail.lines.reduce((sum, ln) => {
      const accepted = ln.actual_qty ?? 0
      return sum + Math.max(0, accepted - ln.posted_qty)
    }, 0)
  }, [detail])

  const processTitle = inboundWorkspaceTitle(workspace)
  const displayDocumentNumber = useMemo(
    () => formatHumanDocumentNumber(detail),
    [detail],
  )

  const receivingTotals = useMemo(
    () =>
      buildInboundReceivingTotals(
        detail?.lines ?? [],
        detail?.boxes ?? [],
        detail?.status,
        detail?.planned_box_count ?? null,
      ),
    [detail?.boxes, detail?.lines, detail?.planned_box_count, detail?.status],
  )

  const discrepancyLines = useMemo(
    () => buildInboundDiscrepancyLines(detail?.lines ?? [], detail?.boxes ?? [], detail?.status),
    [detail?.boxes, detail?.lines, detail?.status],
  )

  const focusActualInput = (lineId: string) => {
    window.setTimeout(() => {
      actualInputRefs.current[lineId]?.focus()
      actualInputRefs.current[lineId]?.select()
    }, 0)
  }

  const loadDetail = useCallback(async (): Promise<InboundDetail> => {
    const seq = ++loadDetailSeq.current
    const res = await fetch(apiUrl(`/operations/inbound-intake-requests/${requestId}`), {
      headers: authHeaders,
    })
    if (!res.ok) {
      throw new Error(await readApiErrorMessage(res))
    }
    const data = (await res.json()) as InboundDetail
    if (seq === loadDetailSeq.current) {
      setDetail(data)
    }
    return data
  }, [authHeaders, requestId])

  const loadLinkedDiscrepancyActs = useCallback(async (): Promise<void> => {
    if (!isFulfillmentAdmin) {
      setLinkedDiscrepancyActs([])
      setDiscrepancyActsError(null)
      return
    }
    setDiscrepancyActsBusy(true)
    setDiscrepancyActsError(null)
    try {
      const listRes = await fetch(apiUrl('/operations/discrepancy-acts'), {
        headers: authHeaders,
      })
      if (!listRes.ok) {
        setDiscrepancyActsError(await readApiErrorMessage(listRes))
        setLinkedDiscrepancyActs([])
        return
      }
      const summaries = (await listRes.json()) as {
        id: string
        inbound_intake_request_id: string | null
      }[]
      const linked = summaries.filter((row) => row.inbound_intake_request_id === requestId)
      const details = await Promise.all(
        linked.map(async (row) => {
          const detailRes = await fetch(apiUrl(`/operations/discrepancy-acts/${row.id}`), {
            headers: authHeaders,
          })
          if (!detailRes.ok) {
            throw new Error(await readApiErrorMessage(detailRes))
          }
          return (await detailRes.json()) as DiscrepancyActDetail
        }),
      )
      setLinkedDiscrepancyActs(details)
    } catch (e) {
      setDiscrepancyActsError(e instanceof Error ? e.message : 'Не удалось загрузить акты расхождения.')
      setLinkedDiscrepancyActs([])
    } finally {
      setDiscrepancyActsBusy(false)
    }
  }, [authHeaders, isFulfillmentAdmin, requestId])

  const fetchCatalogRows = useCallback(async (): Promise<WbCatalogRow[]> => {
    const query = detail?.seller_id ? `?seller_id=${detail.seller_id}` : ''
    const res = await fetch(apiUrl(`/products/linked-wb-catalog${query}`), { headers: authHeaders })
    if (!res.ok) {
      throw new Error(await readApiErrorMessage(res))
    }
    return (await res.json()) as WbCatalogRow[]
  }, [authHeaders, detail?.seller_id])

  const loadCatalog = useCallback(async () => {
    setCatalog(await fetchCatalogRows())
  }, [fetchCatalogRows])

  const loadLocations = useCallback(
    async (warehouseId: string) => {
      const res = await fetch(
        apiUrl(`/warehouses/${warehouseId}/locations?exclude_sorting_zone=true`),
        { headers: authHeaders },
      )
      if (!res.ok) {
        setLocations([])
        setDistError('Не удалось загрузить список ячеек склада.')
        return
      }
      const rows = (await res.json()) as LocationRow[]
      setLocations(rows)
      if (rows.length === 0) {
        setDistError(null)
        setNewLocationCode(suggestNextLocationCode([]))
      }
    },
    [authHeaders],
  )

  const createWarehouseLocation = async () => {
    const code = newLocationCode.trim()
    if (!detail?.warehouse_id || !code) {
      setDistError('Укажите код ячейки (например A-01).')
      return
    }
    setDistBusy(true)
    setDistError(null)
    try {
      const res = await fetch(apiUrl(`/warehouses/${detail.warehouse_id}/locations`), {
        method: 'POST',
        headers: { ...authHeaders, 'Content-Type': 'application/json' },
        body: JSON.stringify({ code }),
      })
      if (!res.ok) {
        setDistError(await readApiErrorMessage(res))
        return
      }
      const created = (await res.json()) as LocationRow
      await loadLocations(detail.warehouse_id)
      setNewLocationCode(suggestNextLocationCode(locations.map((l) => l.code).concat(created.code)))
    } catch (e) {
      setDistError(e instanceof Error ? e.message : 'Не удалось создать ячейку.')
    } finally {
      setDistBusy(false)
    }
  }

  const loadCellHints = useCallback(
    async (productId: string) => {
      if (!detail?.warehouse_id || !productId) return
      try {
        const params = new URLSearchParams({
          product_id: productId,
          warehouse_id: detail.warehouse_id,
        })
        const res = await fetch(
          apiUrl(`/operations/inventory-balances/locations-by-product?${params}`),
          { headers: authHeaders },
        )
        if (!res.ok) return
        const rows = (await res.json()) as CellLocationHint[]
        setCellHintsByProductId((prev) => {
          if (prev[productId] !== undefined) return prev
          return { ...prev, [productId]: rows }
        })
      } catch {
        setCellHintsByProductId((prev) => {
          if (prev[productId] !== undefined) return prev
          return { ...prev, [productId]: [] }
        })
      }
    },
    [authHeaders, detail?.warehouse_id],
  )

  const loadDistribution = useCallback(async () => {
    if (!detail) return
    setDistError(null)
    try {
      const res = await fetch(
        apiUrl(`/operations/inbound-intake-requests/${requestId}/distribution-lines`),
        { headers: authHeaders },
      )
      if (!res.ok) {
        setDistLines([])
        return
      }
      const rows = (await res.json()) as DistributionLineOut[]
      setDistLines(
        rows.map((r) => ({
          box_id: (r as { box_id?: string | null }).box_id ?? defaultPutawayBoxId,
          product_id: r.product_id,
          storage_location_id: r.storage_location_id,
          quantity: String(r.quantity),
        })),
      )
    } catch (e) {
      setDistLines([])
      setDistError(e instanceof Error ? e.message : 'Не удалось загрузить распределение.')
    }
  }, [authHeaders, defaultPutawayBoxId, detail, requestId])

  useEffect(() => {
    let cancelled = false
    setBusy(true)
    setError(null)
    void (async () => {
      try {
        await loadDetail()
        if (!cancelled) {
          setBusy(false)
        }
      } catch (e) {
        if (!cancelled) {
          setBusy(false)
          setError(e instanceof Error ? e.message : 'Не удалось загрузить заявку.')
        }
      }
    })()
    return () => {
      cancelled = true
    }
  }, [loadDetail])

  useEffect(() => {
    void loadLinkedDiscrepancyActs()
  }, [loadLinkedDiscrepancyActs])

  useEffect(() => {
    if (!detail) {
      return
    }
    void loadCatalog()
  }, [detail, loadCatalog])

  useEffect(() => {
    setPlannedDateDraft(detail?.planned_delivery_date ?? '')
  }, [detail?.planned_delivery_date])

  useEffect(() => {
    if (!detail) {
      setActualDraftByLineId({})
      return
    }
    const boxes = detail.boxes ?? []
    setActualDraftByLineId((prev) => {
      const next: Record<string, string> = {}
      for (const ln of detail.lines) {
        const existing = prev[ln.id]
        if (existing !== undefined && manualEditLineId === ln.id) {
          next[ln.id] = existing
          continue
        }
        next[ln.id] = String(effectiveActualQty(ln, boxes, detail.status))
      }
      return next
    })
    setActualDraftErrorByLineId((prev) => {
      const next: Record<string, string> = {}
      for (const ln of detail.lines) {
        if (manualEditLineId === ln.id && prev[ln.id]) {
          next[ln.id] = prev[ln.id]!
        }
      }
      return next
    })
  }, [detail, manualEditLineId])

  useEffect(() => {
    actualDraftRef.current = actualDraftByLineId
  }, [actualDraftByLineId])

  useEffect(() => {
    if (!detail) {
      setLocations([])
      setRequestWarehouse(null)
      return
    }
    // For verified stage we need the cell directory to assign storage locations.
    if (!detail.warehouse_id) {
      setLocations([])
      setRequestWarehouse(null)
      return
    }
    void loadLocations(detail.warehouse_id)
    void (async () => {
      const res = await fetch(apiUrl('/warehouses'), { headers: authHeaders })
      if (!res.ok) {
        setRequestWarehouse(null)
        return
      }
      const rows = (await res.json()) as WarehouseRow[]
      setRequestWarehouse(rows.find((w) => w.id === detail.warehouse_id) ?? null)
    })()
  }, [authHeaders, detail?.warehouse_id, loadLocations, detail])

  useEffect(() => {
    if (!detail) {
      setDistOpen(false)
      setDistLines([])
      return
    }
    if (!isFulfillmentAdmin) {
      setDistOpen(false)
      setDistLines([])
      return
    }
    if (!isSortingStatus(detail.status)) {
      setDistOpen(false)
      setDistLines([])
      return
    }
    if (workspace === 'reception') {
      setDistOpen(false)
      setDistLines([])
      return
    }
    if (workspace === 'sorting') {
      setDistOpen(false)
      return
    }
    void loadDistribution()
  }, [detail, isFulfillmentAdmin, loadDistribution, workspace])

  useEffect(() => {
    if (!distOpen || !isSortingStatus(detail?.status ?? '')) return
    for (const row of distLines) {
      if (row.product_id) void loadCellHints(row.product_id)
    }
  }, [distOpen, detail?.status, distLines, loadCellHints])

  useEffect(() => {
    if (!error) return
    document
      .querySelector('[data-testid="ff-inbound-doc-error"]')
      ?.scrollIntoView({ behavior: 'smooth', block: 'nearest' })
  }, [error])

  const catalogById = useMemo(() => {
    const m = new Map<string, WbCatalogRow>()
    if (catalog) {
      for (const r of catalog) {
        m.set(r.id, r)
      }
    }
    return m
  }, [catalog])

  const lineProductIds = useMemo(
    () => new Set(detail?.lines.map((l) => l.product_id) ?? []),
    [detail],
  )

  const pickerDisabledProductIds = useMemo(() => {
    if (detail?.status !== 'draft') {
      return new Set<string>()
    }
    return lineProductIds
  }, [detail?.status, lineProductIds])

  const draftLocked = detail != null && detail.status !== 'draft'

  const acceptedQtyByProductId = useMemo(() => {
    const m = new Map<string, number>()
    if (!detail) return m
    const boxes = detail.boxes ?? []
    for (const ln of detail.lines) {
      m.set(ln.product_id, effectiveActualQty(ln, boxes, detail.status))
    }
    return m
  }, [detail])

  const hasLineDiscrepancy = useMemo(() => {
    if (!detail) return false
    const boxes = detail.boxes ?? []
    return detail.lines.some(
      (ln) => effectiveActualQty(ln, boxes, detail.status) !== ln.expected_qty,
    )
  }, [detail])

  const distributableProducts = useMemo(() => {
    if (!detail) return []
    const boxes = detail.boxes ?? []
    const rows = detail.lines
      .map((ln) => ({
        product_id: ln.product_id,
        sku_code: ln.sku_code,
        product_name: ln.product_name,
        accepted_qty: effectiveActualQty(ln, boxes, detail.status),
      }))
      .filter((x) => x.accepted_qty > 0)
    const seen = new Set<string>()
    const uniq: typeof rows = []
    for (const r of rows) {
      if (seen.has(r.product_id)) continue
      seen.add(r.product_id)
      uniq.push(r)
    }
    return uniq.sort((a, b) => a.sku_code.localeCompare(b.sku_code))
  }, [detail])

  const distSumByProductId = useMemo(() => {
    const m = new Map<string, number>()
    for (const r of distLines) {
      const pid = r.product_id
      if (!pid) continue
      const q = Math.floor(Number(r.quantity))
      if (!Number.isFinite(q) || q <= 0) continue
      m.set(pid, (m.get(pid) ?? 0) + q)
    }
    return m
  }, [distLines])

  const distRemainingByProductId = useMemo(() => {
    const m = new Map<string, number>()
    for (const p of distributableProducts) {
      const accepted = p.accepted_qty
      const used = distSumByProductId.get(p.product_id) ?? 0
      m.set(p.product_id, Math.max(accepted - used, 0))
    }
    return m
  }, [distributableProducts, distSumByProductId])

  const noCellRemainingLines = useMemo(
    () =>
      distributableProducts
        .map((p) => ({
          ...p,
          remaining: distRemainingByProductId.get(p.product_id) ?? p.accepted_qty,
        }))
        .filter((p) => p.remaining > 0),
    [distributableProducts, distRemainingByProductId],
  )

  const hasNoCellPending = noCellRemainingLines.length > 0

  const distributionCompleted = Boolean(detail?.distribution_completed_at)
  const distributionEditable = isFulfillmentAdmin && !distributionCompleted
  const canReopenDistribution =
    Boolean(detail) &&
    distributionCompleted &&
    isSortingStatus(detail!.status) &&
    detail!.lines.every((ln) => ln.posted_qty === 0)

  const validateDistributionDraft = (): string | null => {
    if (!detail) return 'Заявка не загружена.'
    // пустые строки черновика игнорируем; завершение без полного распределения блокируется отдельно
    const acceptedByProductId = new Map(distributableProducts.map((p) => [p.product_id, p.accepted_qty]))
    const sumByProductId = new Map<string, number>()

    for (const [idx, r] of distLines.entries()) {
      const rowLabel = `Строка ${idx + 1}`
      const hasAny = Boolean(r.product_id || r.storage_location_id || r.quantity)
      if (!hasAny) continue

      if (!r.product_id) return `${rowLabel}: выбери товар.`
      const accepted = acceptedByProductId.get(r.product_id)
      if (accepted == null) return `${rowLabel}: товар не относится к заявке.`
      if (accepted <= 0) return `${rowLabel}: товар не принят (0).`

      if (!r.storage_location_id) return `${rowLabel}: выбери ячейку.`

      const q = Math.floor(Number(r.quantity))
      if (!Number.isFinite(q) || q <= 0) return `${rowLabel}: количество должно быть целым числом > 0.`

      const nextSum = (sumByProductId.get(r.product_id) ?? 0) + q
      if (nextSum > accepted) {
        return `${rowLabel}: превышение. По товару можно максимум ${accepted}, указано суммарно ${nextSum}.`
      }
      sumByProductId.set(r.product_id, nextSum)
    }
    return null
  }

  const saveDistribution = async () => {
    if (!detail) return
    setDistBusy(true)
    setDistError(null)
    try {
      const vErr = validateDistributionDraft()
      if (vErr) {
        setDistError(vErr)
        return
      }
      const payload = distLines
        .filter((r) => r.product_id && r.storage_location_id && r.quantity)
        .map((r) => {
          const boxId = r.box_id || defaultPutawayBoxId
          return {
            box_id: boxId || null,
            product_id: r.product_id,
            storage_location_id: r.storage_location_id,
            quantity: Math.floor(Number(r.quantity)),
          }
        })
        .filter((r) => Number.isFinite(r.quantity) && r.quantity > 0)
      const res = await fetch(
        apiUrl(`/operations/inbound-intake-requests/${requestId}/distribution-lines`),
        {
          method: 'PUT',
          headers: { ...authHeaders, 'Content-Type': 'application/json' },
          body: JSON.stringify(payload),
        },
      )
      if (!res.ok) {
        const code = await readApiErrorMessage(res)
        if (code === 'qty_exceeds_accepted') {
          setDistError('Превышено принятие: суммарно по товару нельзя распределить больше, чем принято по заявке.')
        } else if (code === 'product_not_on_request') {
          setDistError('Нельзя распределять товар, которого нет в этой заявке.')
        } else if (code === 'product_not_accepted') {
          setDistError('Нельзя распределять товар с принятым количеством 0.')
        } else {
          setDistError(code)
        }
        return
      }
      const rows = (await res.json()) as DistributionLineOut[]
      setDistLines(
        rows.map((r) => ({
          box_id: (r as { box_id?: string | null }).box_id ?? defaultPutawayBoxId,
          product_id: r.product_id,
          storage_location_id: r.storage_location_id,
          quantity: String(r.quantity),
        })),
      )
      setDistOpen(true)
    } catch (e) {
      setDistError(e instanceof Error ? e.message : 'Не удалось сохранить распределение.')
    } finally {
      setDistBusy(false)
    }
  }

  const reopenDistribution = async () => {
    if (!detail) return
    setDistBusy(true)
    setDistError(null)
    try {
      const res = await fetch(
        apiUrl(`/operations/inbound-intake-requests/${requestId}/distribution-reopen`),
        { method: 'POST', headers: authHeaders },
      )
      if (!res.ok) {
        setDistError(await readApiErrorMessage(res))
        return
      }
      await loadDetail()
      await loadDistribution()
      setDistOpen(true)
    } catch (e) {
      setDistError(e instanceof Error ? e.message : 'Не удалось открыть распределение.')
    } finally {
      setDistBusy(false)
    }
  }

  const completeDistribution = async () => {
    if (!detail) return
    if (distLines.every((r) => !r.product_id || !r.storage_location_id || !r.quantity)) {
      setDistError('Добавьте хотя бы одну строку с товаром, ячейкой и количеством.')
      setDistOpen(true)
      return
    }
    setDistBusy(true)
    setDistError(null)
    try {
      const vErr = validateDistributionDraft()
      if (vErr) {
        setDistError(vErr)
        return
      }
      // Always persist draft first; completion must lock what is actually saved.
      const payload = distLines
        .filter((r) => r.product_id && r.storage_location_id && r.quantity)
        .map((r) => {
          const boxId = r.box_id || defaultPutawayBoxId
          return {
            box_id: boxId || null,
            product_id: r.product_id,
            storage_location_id: r.storage_location_id,
            quantity: Math.floor(Number(r.quantity)),
          }
        })
        .filter((r) => Number.isFinite(r.quantity) && r.quantity > 0)
      const putRes = await fetch(
        apiUrl(`/operations/inbound-intake-requests/${requestId}/distribution-lines`),
        {
          method: 'PUT',
          headers: { ...authHeaders, 'Content-Type': 'application/json' },
          body: JSON.stringify(payload),
        },
      )
      if (!putRes.ok) {
        const code = await readApiErrorMessage(putRes)
        setDistError(code)
        return
      }
      const savedRows = (await putRes.json()) as DistributionLineOut[]
      setDistLines(
        savedRows.map((r) => ({
          box_id: (r as { box_id?: string | null }).box_id ?? defaultPutawayBoxId,
          product_id: r.product_id,
          storage_location_id: r.storage_location_id,
          quantity: String(r.quantity),
        })),
      )
      const res = await fetch(
        apiUrl(`/operations/inbound-intake-requests/${requestId}/distribution-complete`),
        { method: 'POST', headers: authHeaders },
      )
      if (!res.ok) {
        const code = await readApiErrorMessage(res)
        setDistError(code)
        return
      }
      await loadDetail()
      await loadDistribution()
      setDistOpen(true)
    } catch (e) {
      setDistError(e instanceof Error ? e.message : 'Не удалось завершить распределение.')
    } finally {
      setDistBusy(false)
    }
  }

  const formatLineDimensions = (line: InboundLine): string => {
    const parts: string[] = []
    if (line.length_mm != null && line.width_mm != null && line.height_mm != null) {
      parts.push(`${line.length_mm}×${line.width_mm}×${line.height_mm} мм`)
      if (line.volume_liters != null) {
        parts.push(`${line.volume_liters.toFixed(2)} л`)
      }
    }
    if (line.weight_g != null) {
      parts.push(`${(line.weight_g / 1000).toFixed(2)} кг`)
    }
    return parts.length > 0 ? parts.join(' · ') : '—'
  }

  const openDimensionsEditor = (line: InboundLine) => {
    setDimensionsLine(line)
    setDimensionDraft({
      length: line.length_mm != null ? String(line.length_mm) : '',
      width: line.width_mm != null ? String(line.width_mm) : '',
      height: line.height_mm != null ? String(line.height_mm) : '',
      weight: line.weight_g != null ? String(line.weight_g) : '',
    })
    setDimensionError(null)
  }

  const printReturnBarcodeForLine = (line: InboundLine) => {
    const barcode = line.wb_barcode?.trim()
    if (!barcode) {
      setScanToastError('У товара нет ШК WB для печати.')
      return
    }
    const captureWindow = window as unknown as {
      __WMS_CAPTURE_PRINT_HTML__?: boolean
      __WMS_LAST_PRINT_HTML__?: string
    }
    if (captureWindow.__WMS_CAPTURE_PRINT_HTML__) {
      captureWindow.__WMS_LAST_PRINT_HTML__ = `${line.product_name}\n${barcode}`
      return
    }
    printBarcodeLabel({
      title: line.product_name,
      barcode,
      barcodeDataUrl: renderBarcodeDataUrl(barcode),
    })
  }

  const addReceivedProductFact = async (
    productId: string,
    qty: number,
  ): Promise<InboundLine | null> => {
    const res = await fetch(apiUrl(`/operations/inbound-intake-requests/${requestId}/receiving/lines`), {
      method: 'POST',
      headers: { ...authHeaders, 'Content-Type': 'application/json' },
      body: JSON.stringify({ product_id: productId, actual_qty: qty, source: 'seller_catalog' }),
    })
    if (!res.ok) {
      setError(scanErrorMessageRu(await readApiErrorMessage(res)))
      return null
    }
    return (await res.json()) as InboundLine
  }

  const saveDimensions = async () => {
    if (!dimensionsLine) return
    const dimRaw = [dimensionDraft.length, dimensionDraft.width, dimensionDraft.height]
    const hasAnyDimension = dimRaw.some((v) => v.trim() !== '')
    const hasAllDimensions = dimRaw.every((v) => v.trim() !== '')
    if (hasAnyDimension && !hasAllDimensions) {
      setDimensionError('Для габаритов укажите длину, ширину и высоту вместе.')
      return
    }
    const length = hasAllDimensions ? Math.floor(Number(dimensionDraft.length)) : null
    const width = hasAllDimensions ? Math.floor(Number(dimensionDraft.width)) : null
    const height = hasAllDimensions ? Math.floor(Number(dimensionDraft.height)) : null
    if (
      hasAllDimensions &&
      (length == null || width == null || height == null || length < 1 || width < 1 || height < 1)
    ) {
      setDimensionError('Габариты должны быть больше нуля.')
      return
    }
    const weight = dimensionDraft.weight.trim() === '' ? null : Math.floor(Number(dimensionDraft.weight))
    if (weight != null && (!Number.isFinite(weight) || weight < 1)) {
      setDimensionError('Вес должен быть больше нуля.')
      return
    }
    const payload: Record<string, number | null> = {}
    if (hasAllDimensions) {
      payload.length_mm = length
      payload.width_mm = width
      payload.height_mm = height
    }
    if (dimensionDraft.weight.trim() !== '') {
      payload.weight_g = weight
    }
    if (Object.keys(payload).length === 0) {
      setDimensionsLine(null)
      return
    }
    setBusy(true)
    setDimensionError(null)
    try {
      const res = await fetch(apiUrl(`/products/${dimensionsLine.product_id}/dimensions`), {
        method: 'PATCH',
        headers: { ...authHeaders, 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      })
      if (!res.ok) {
        setDimensionError(await readApiErrorMessage(res))
        return
      }
      setDimensionsLine(null)
      await loadDetail()
      await loadCatalog()
    } catch (e) {
      setDimensionError(e instanceof Error ? e.message : 'Не удалось сохранить габариты.')
    } finally {
      setBusy(false)
    }
  }

  const patchPlannedDate = async (isoDate: string) => {
    setBusy(true)
    setError(null)
    try {
      const res = await fetch(apiUrl(`/operations/inbound-intake-requests/${requestId}`), {
        method: 'PATCH',
        headers: { ...authHeaders, 'Content-Type': 'application/json' },
        body: JSON.stringify({ planned_delivery_date: isoDate }),
      })
      if (!res.ok) {
        setError(await readApiErrorMessage(res))
        return
      }
      setDetail((await res.json()) as InboundDetail)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Не удалось сохранить дату.')
    } finally {
      setBusy(false)
    }
  }

  const openPicker = async (initialSearch = '') => {
    setError(null)
    setPickerInitialSearch(initialSearch)
    try {
      if (catalog == null) {
        await loadCatalog()
      }
      setPickerOpen(true)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Не удалось загрузить каталог.')
    }
  }

  const addLineByBarcode = async (rawInput?: string) => {
    if (!detail) return
    const code = (rawInput ?? '').trim()
    if (!code) return
    setBusy(true)
    setError(null)
    try {
      let cat = catalog
      if (cat == null) {
        cat = await fetchCatalogRows()
        setCatalog(cat)
      }
      const productId = resolveProductIdByBarcode(cat, code)
      if (!productId) {
        setPickerInitialSearch(code)
        setError('Товар не найден в каталоге селлера. Добавление нового товара будет отдельной задачей.')
        return
      }
      const existing = detail.lines.find((ln) => ln.product_id === productId)
      if (existing) {
        const res = await fetch(
          apiUrl(
            `/operations/inbound-intake-requests/${requestId}/lines/${existing.id}/expected`,
          ),
          {
            method: 'PATCH',
            headers: { ...authHeaders, 'Content-Type': 'application/json' },
            body: JSON.stringify({ expected_qty: existing.expected_qty + 1 }),
          },
        )
        if (!res.ok) {
          setError(await readApiErrorMessage(res))
          return
        }
      } else {
        const res = await fetch(apiUrl(`/operations/inbound-intake-requests/${requestId}/lines`), {
          method: 'POST',
          headers: { ...authHeaders, 'Content-Type': 'application/json' },
          body: JSON.stringify({ product_id: productId, expected_qty: 1 }),
        })
        if (!res.ok) {
          setError(await readApiErrorMessage(res))
          return
        }
      }
      await loadDetail()
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Не удалось добавить строку по штрихкоду.')
    } finally {
      setBusy(false)
    }
  }

  const applyPicker = async (pickerQtyByProduct: Record<string, number>) => {
    if (!detail) return
    setBusy(true)
    setError(null)
    try {
      const lineByProduct = new Map(detail.lines.map((ln) => [ln.product_id, ln]))
      const receivingMode = detail.status !== 'draft' && receivingActive
      for (const [productId, rawQty] of Object.entries(pickerQtyByProduct)) {
        const addQty = Number.isFinite(rawQty) ? Math.floor(rawQty) : 0
        if (addQty <= 0) continue
        if (receivingMode) {
          const added = await addReceivedProductFact(productId, addQty)
          if (!added) {
            return
          }
          continue
        }
        const existing = lineByProduct.get(productId)
        if (existing) {
          const next = existing.expected_qty + addQty
          const res = await fetch(
            apiUrl(
              `/operations/inbound-intake-requests/${requestId}/lines/${existing.id}/expected`,
            ),
            {
              method: 'PATCH',
              headers: { ...authHeaders, 'Content-Type': 'application/json' },
              body: JSON.stringify({ expected_qty: next }),
            },
          )
          if (!res.ok) {
            setError(await readApiErrorMessage(res))
            return
          }
        } else {
          const res = await fetch(
            apiUrl(`/operations/inbound-intake-requests/${requestId}/lines`),
            {
              method: 'POST',
              headers: { ...authHeaders, 'Content-Type': 'application/json' },
              body: JSON.stringify({ product_id: productId, expected_qty: addQty }),
            },
          )
          if (!res.ok) {
            setError(await readApiErrorMessage(res))
            return
          }
        }
      }
      setPickerOpen(false)
      await loadDetail()
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Не удалось добавить товары.')
    } finally {
      setBusy(false)
    }
  }

  const submitToWarehouse = async () => {
    setBusy(true)
    setError(null)
    try {
      const res = await fetch(
        apiUrl(`/operations/inbound-intake-requests/${requestId}/submit`),
        { method: 'POST', headers: authHeaders },
      )
      if (!res.ok) {
        setError(await readApiErrorMessage(res))
        return
      }
      await loadDetail()
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Не удалось передать на склад.')
    } finally {
      setBusy(false)
    }
  }

  const beginReceiving = async () => {
    setBusy(true)
    setError(null)
    try {
      const res = await fetch(
        apiUrl(`/operations/inbound-intake-requests/${requestId}/begin-receiving`),
        { method: 'POST', headers: authHeaders },
      )
      if (!res.ok) {
        setError(await readApiErrorMessage(res))
        return
      }
      await loadDetail()
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Не удалось начать приёмку.')
    } finally {
      setBusy(false)
    }
  }

  const printDistributionLocationLabel = (locationId: string) => {
    const loc = locations.find((l) => l.id === locationId)
    if (!loc) return
    const dataUrl = renderBarcodeDataUrl(loc.barcode)
    printBarcodeLabel({
      title: `Ячейка № ${loc.code}`,
      barcode: loc.barcode,
      barcodeDataUrl: dataUrl,
    })
  }

  const printInboundBoxLabel = async (box: InboundBox) => {
    setBusy(true)
    setError(null)
    try {
      const dataUrl = renderBarcodeDataUrl(box.internal_barcode)
      printBarcodeLabel({
        title: `Короб № ${box.box_number}`,
        barcode: box.internal_barcode,
        barcodeDataUrl: dataUrl,
      })
      const res = await fetch(
        apiUrl(
          `/operations/inbound-intake-requests/${requestId}/boxes/${box.id}/mark-label-printed`,
        ),
        { method: 'POST', headers: authHeaders },
      )
      if (!res.ok) {
        setError(await readApiErrorMessage(res))
        return
      }
      await loadDetail()
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Не удалось напечатать этикетку короба.')
    } finally {
      setBusy(false)
    }
  }

  const printAllInboundBoxLabels = async () => {
    if (!detail?.boxes?.length) return
    for (const box of detail.boxes) {
      await printInboundBoxLabel(box)
    }
  }

  const printInboundCargoPlaceLabel = async (place: InboundCargoPlace) => {
    setBusy(true)
    setError(null)
    try {
      const dataUrl = renderBarcodeDataUrl(place.internal_barcode)
      printBarcodeLabel({
        title: `Грузоместо № ${place.place_number}`,
        barcode: place.internal_barcode,
        barcodeDataUrl: dataUrl,
      })
      const res = await fetch(
        apiUrl(
          `/operations/inbound-intake-requests/${requestId}/cargo-places/${place.id}/mark-label-printed`,
        ),
        { method: 'POST', headers: authHeaders },
      )
      if (!res.ok) {
        setError(await readApiErrorMessage(res))
        return
      }
      await loadDetail()
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Не удалось напечатать этикетку грузоместа.')
    } finally {
      setBusy(false)
    }
  }

  const printAllInboundCargoPlaceLabels = async () => {
    if (!detail?.cargo_places?.length) return
    for (const place of detail.cargo_places) {
      await printInboundCargoPlaceLabel(place)
    }
  }

  const scanToReceiving = async (raw?: string) => {
    const code = (raw ?? '').trim()
    if (!code) return
    setBusy(true)
    setError(null)
    try {
      const res = await fetch(
        apiUrl(`/operations/inbound-intake-requests/${requestId}/receiving/scan`),
        {
          method: 'POST',
          headers: { ...authHeaders, 'Content-Type': 'application/json' },
          body: JSON.stringify({ barcode: code }),
        },
      )
      if (!res.ok) {
        const errorCode = await readApiErrorMessage(res)
        setScanToastError(scanErrorMessageRu(errorCode))
        setScanAddBarcode(
          errorCode === 'product_not_on_request' || errorCode === 'barcode_unknown'
            ? code
            : null,
        )
        return
      }
      setScanAddBarcode(null)
      const scannedLine = (await res.json()) as InboundLine
      if (isReturnOperation && returnAutoPrint) {
        printReturnBarcodeForLine(scannedLine)
      }
      await loadDetail()
    } catch (e) {
      setScanToastError(e instanceof Error ? e.message : 'Не удалось выполнить скан.')
    } finally {
      setBusy(false)
    }
  }

  const createInboundBox = async (): Promise<string | null> => {
    setBusy(true)
    setError(null)
    try {
      const res = await fetch(apiUrl(`/operations/inbound-intake-requests/${requestId}/boxes`), {
        method: 'POST',
        headers: authHeaders,
      })
      if (!res.ok) {
        setError(scanErrorMessageRu(await readApiErrorMessage(res)))
        return null
      }
      const box = (await res.json()) as { id: string }
      await loadDetail()
      setPackagesExpanded(true)
      return box.id
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Не удалось создать короб.')
      return null
    } finally {
      setBusy(false)
    }
  }

  const resolveDiscrepancyAct = async (actId: string, action: 'approve' | 'reject') => {
    setDiscrepancyActsBusy(true)
    setDiscrepancyActsError(null)
    try {
      const res = await fetch(apiUrl(`/operations/discrepancy-acts/${actId}/${action}`), {
        method: 'POST',
        headers: authHeaders,
      })
      if (!res.ok) {
        setDiscrepancyActsError(await readApiErrorMessage(res))
        return
      }
      await loadLinkedDiscrepancyActs()
      await loadDetail()
    } catch (e) {
      setDiscrepancyActsError(e instanceof Error ? e.message : 'Не удалось обработать акт.')
    } finally {
      setDiscrepancyActsBusy(false)
    }
  }

  const openBoxAddDialog = (boxId: string) => {
    setBoxAddDialogBoxId(boxId)
  }

  const handleCreateBox = async () => {
    await createInboundBox()
  }

  const createCargoPlaces = async () => {
    const count = Math.floor(Number(cargoCount))
    if (!Number.isFinite(count) || count < 1 || count > 1000) {
      setCargoError('Укажите количество грузомест от 1 до 1000.')
      return
    }
    setBusy(true)
    setCargoError(null)
    setError(null)
    try {
      const res = await fetch(apiUrl(`/operations/inbound-intake-requests/${requestId}/cargo-places`), {
        method: 'POST',
        headers: { ...authHeaders, 'Content-Type': 'application/json' },
        body: JSON.stringify({ quantity: count }),
      })
      if (!res.ok) {
        setCargoError(await readApiErrorMessage(res))
        return
      }
      setCargoDialogOpen(false)
      setCargoCount('1')
      setPackagesExpanded(true)
      await loadDetail()
    } catch (e) {
      setCargoError(e instanceof Error ? e.message : 'Не удалось создать грузоместа.')
    } finally {
      setBusy(false)
    }
  }

  const deleteInboundBox = async (boxId: string) => {
    setBusy(true)
    setError(null)
    try {
      const res = await fetch(
        apiUrl(`/operations/inbound-intake-requests/${requestId}/boxes/${boxId}`),
        { method: 'DELETE', headers: authHeaders },
      )
      if (!res.ok) {
        setError(scanErrorMessageRu(await readApiErrorMessage(res)))
        return
      }
      if (boxAddDialogBoxId === boxId) {
        setBoxAddDialogBoxId(null)
      }
      await loadDetail()
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Не удалось удалить короб.')
    } finally {
      setBusy(false)
    }
  }

  const completeReceiving = async () => {
    setBusy(true)
    setError(null)
    setFinishConfirmOpen(false)
    try {
      const res = await fetch(
        apiUrl(`/operations/inbound-intake-requests/${requestId}/complete-receiving`),
        { method: 'POST', headers: authHeaders },
      )
      if (!res.ok) {
        setError(scanErrorMessageRu(await readApiErrorMessage(res)))
        return
      }
      await loadDetail()
      setDistOpen(true)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Не удалось завершить приёмку.')
    } finally {
      setBusy(false)
    }
  }

  const reopenReceiving = async () => {
    setBusy(true)
    setError(null)
    try {
      const res = await fetch(
        apiUrl(`/operations/inbound-intake-requests/${requestId}/reopen-receiving`),
        { method: 'POST', headers: authHeaders },
      )
      if (!res.ok) {
        setError(await readApiErrorMessage(res))
        return
      }
      setDistOpen(false)
      await loadDetail()
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Не удалось открыть приёмку для редактирования.')
    } finally {
      setBusy(false)
    }
  }

  const requestCompleteReceiving = () => {
    if (receivingTotals.hasAnyDiscrepancy) {
      setFinishConfirmOpen(true)
      return
    }
    void completeReceiving()
  }

  const setLineActual = async (lineId: string, actualQty: number) => {
    setBusy(true)
    setError(null)
    try {
      const res = await fetch(
        apiUrl(`/operations/inbound-intake-requests/${requestId}/lines/${lineId}/actual`),
        {
          method: 'PATCH',
          headers: { ...authHeaders, 'Content-Type': 'application/json' },
          body: JSON.stringify({ actual_qty: actualQty }),
        },
      )
      if (!res.ok) {
        const msg = await readApiErrorMessage(res)
        setError(msg === 'actual_missing' ? 'Укажите факт по всем строкам.' : msg)
        return
      }
      await loadDetail()
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Не удалось сохранить факт.')
    } finally {
      setBusy(false)
    }
  }

  const saveManualLineActual = async (lineId: string, rawOverride?: string) => {
    const raw =
      rawOverride ??
      actualDraftRef.current[lineId] ??
      actualDraftByLineId[lineId]
    const validationError = integerQtyError(raw)
    if (validationError) {
      setActualDraftErrorByLineId((prev) => ({ ...prev, [lineId]: validationError }))
      setManualEditLineId(lineId)
      focusActualInput(lineId)
      return
    }
    const displayed = parseIntegerQty(raw)
    if (displayed == null) {
      return
    }
    const line = detail?.lines.find((ln) => ln.id === lineId)
    if (!line) {
      return
    }
    const boxes = detail?.boxes ?? []
    const currentEffective = effectiveActualQty(line, boxes, detail?.status)
    if (displayed === currentEffective) {
      setActualDraftErrorByLineId((prev) => ({ ...prev, [lineId]: '' }))
      setManualEditLineId(null)
      return
    }
    const loose = looseQtyFromDisplayedTotal(displayed, line, boxes)
    await setLineActual(lineId, loose)
    setActualDraftErrorByLineId((prev) => ({ ...prev, [lineId]: '' }))
    setManualEditLineId(null)
  }

  const hasUnsavedActualChange = useMemo(() => {
    if (!manualEditLineId || !detail) return false
    const line = detail.lines.find((ln) => ln.id === manualEditLineId)
    if (!line) return false
    const raw = actualDraftByLineId[manualEditLineId]
    if (raw == null) return false
    const current = String(effectiveActualQty(line, detail.boxes ?? [], detail.status))
    return raw.trim() !== current
  }, [actualDraftByLineId, detail, manualEditLineId])

  const handleSaveDocument = async () => {
    if (manualEditLineId) {
      const raw = actualDraftRef.current[manualEditLineId] ?? actualDraftByLineId[manualEditLineId] ?? ''
      const validationError = integerQtyError(raw)
      if (validationError) {
        setActualDraftErrorByLineId((prev) => ({ ...prev, [manualEditLineId]: validationError }))
        focusActualInput(manualEditLineId)
        return
      }
      await saveManualLineActual(manualEditLineId, raw)
    }
    setSaveSuccessMsg('Документ сохранён.')
  }

  const handleClose = () => {
    if (hasUnsavedActualChange) {
      setCloseConfirmOpen(true)
      return
    }
    onClose()
  }

  const boxes = useMemo(
    () => [...(detail?.boxes ?? [])].sort((a, b) => a.box_number - b.box_number),
    [detail?.boxes],
  )

  const cargoPlaces = useMemo(
    () => [...(detail?.cargo_places ?? [])].sort((a, b) => a.place_number - b.place_number),
    [detail?.cargo_places],
  )

  const boxAddDialogBox = useMemo(
    () => boxes.find((b) => b.id === boxAddDialogBoxId) ?? null,
    [boxAddDialogBoxId, boxes],
  )

  const actualEditable =
    isFulfillmentAdmin &&
    receivingActive

  const hasPostedPartial = useMemo(
    () => (detail?.lines ?? []).some((ln) => (ln.posted_qty ?? 0) > 0),
    [detail?.lines],
  )

  const canReopenReceiving =
    isFulfillmentAdmin &&
    !sortingView &&
    detail != null &&
    isSortingStatus(detail.status) &&
    !hasPostedPartial

  if (busy && !detail) {
    return (
      <Stack sx={{ py: 6, alignItems: 'center' }} data-testid="ff-inbound-doc-loading">
        <CircularProgress />
        <Typography variant="body2" color="text.secondary" sx={{ mt: 1 }}>
          Загрузка…
        </Typography>
      </Stack>
    )
  }

  return (
    <FfProductMarkingPrintProvider token={token}>
    <GlobalStyles
      styles={{
        'body > [aria-hidden="true"]': {
          width: '100vw',
          maxWidth: '100vw',
          overflowX: 'hidden',
        },
      }}
    />
    <Box
      data-testid="ff-inbound-doc-root"
      sx={{ width: '100%', minWidth: 0, maxWidth: '100%', boxSizing: 'border-box' }}
    >
      {error ? (
        <Alert severity="error" sx={{ mb: 2 }} data-testid="ff-inbound-doc-error">
          {error}
        </Alert>
      ) : null}

      {!detail ? (
        <Alert severity="warning">Заявка не найдена или недоступна.</Alert>
      ) : (
        <Paper
          variant="outlined"
          sx={{
            p: 2,
            minHeight: '38vh',
            width: '100%',
            minWidth: 0,
            maxWidth: '100%',
            boxSizing: 'border-box',
            overflowX: 'hidden',
          }}
        >
          <Stack spacing={2} sx={{ mb: 2 }}>
            <Stack
              direction={{ xs: 'column', sm: 'row' }}
              spacing={2}
              useFlexGap
              sx={{ alignItems: { xs: 'flex-start', sm: 'flex-end' }, justifyContent: 'space-between' }}
            >
              <Stack spacing={0.25} sx={{ minWidth: 0 }}>
                <Typography variant="subtitle2" color="text.secondary" sx={{ fontWeight: 700 }}>
                  {processTitle}
                </Typography>
                {displayDocumentNumber ? (
                  <Typography
                    variant="h5"
                    sx={{ fontWeight: 800, lineHeight: 1.1 }}
                    data-testid="ff-inbound-document-number"
                  >
                    {displayDocumentNumber}
                  </Typography>
                ) : null}
              </Stack>

              <Stack
                direction="row"
                spacing={1.5}
                useFlexGap
                sx={{
                  alignItems: 'center',
                  flexWrap: 'wrap',
                  justifyContent: { xs: 'flex-start', sm: 'flex-end' },
                }}
                data-testid="ff-inbound-compact-summary"
              >
                <Typography variant="body2" color="text.secondary" data-testid="ff-inbound-operation-type">
                  Тип: <strong>{operationTypeLabel}</strong>
                </Typography>
                <Typography variant="body2" color="text.secondary" data-testid="ff-inbound-seller-name">
                  Селлер: <strong>{detail.seller_name ?? '—'}</strong>
                </Typography>
                <Typography variant="body2" color="text.secondary" data-testid="ff-inbound-received-summary">
                  Принято: <strong>{receivingTotals.acceptedQty} из {receivingTotals.expectedQty}</strong>
                </Typography>
                <Typography variant="body2" color="text.secondary" data-testid="ff-inbound-boxes-summary">
                  Короба:{' '}
                  <strong data-testid="ff-inbound-planned-boxes">
                    {receivingTotals.actualBoxes}
                    {receivingTotals.plannedBoxes != null ? ` из ${receivingTotals.plannedBoxes}` : ''}
                  </strong>
                </Typography>
                <Typography variant="body2" color="text.secondary" data-testid="ff-inbound-volume-summary">
                  Литраж: <strong>{receivingTotals.totalVolumeLiters.toFixed(2)} л</strong>
                </Typography>
                <Typography variant="body2" color="text.secondary" data-testid="ff-inbound-weight-summary">
                  Вес: <strong>{receivingTotals.totalWeightKg.toFixed(2)} кг</strong>
                </Typography>
              </Stack>
            </Stack>

            <Stack
              direction="row"
              spacing={2}
              useFlexGap
              sx={{ alignItems: 'center', flexWrap: 'wrap' }}
            >
              {plannedDateFieldEnabled ? (
                <WmsDateField
                  label="Дата приёмки (план)"
                  value={plannedDateDraft || null}
                  onChange={(iso) => {
                    const next = iso ?? ''
                    setPlannedDateDraft(next)
                    if ((next || '') !== (detail.planned_delivery_date ?? '')) {
                      void patchPlannedDate(next)
                    }
                  }}
                  disabled={draftLocked || busy}
                  required
                  testId="ff-inbound-planned-date"
                  slotProps={{ textField: { fullWidth: false, sx: { minWidth: 220 } } }}
                />
              ) : null}
              <Chip
                label={inboundStatusRu(detail.status)}
                color={inboundStatusChipColor(detail.status)}
                data-testid="ff-inbound-status-chip"
              />
            </Stack>

            <Stack
              direction="row"
              spacing={1}
              useFlexGap
              sx={{
                justifyContent: { xs: 'stretch', sm: 'flex-end' },
                alignItems: 'center',
                flexWrap: 'wrap',
              }}
            >
              {isFulfillmentAdmin &&
              workspace !== 'sorting' &&
              receivingActive ? (
                <>
                  <Button
                    variant="contained"
                    disabled={busy}
                    onClick={() => void openPicker()}
                    data-testid="ff-inbound-receiving-add-products"
                  >
                    Добавить товар
                  </Button>
                  {isReturnOperation ? (
                    <FormControlLabel
                      control={
                        <Switch
                          size="small"
                          checked={returnAutoPrint}
                          onChange={(e) => setReturnAutoPrint(e.target.checked)}
                          data-testid="ff-inbound-return-autoprint"
                        />
                      }
                      label="Печатать ШК при скане"
                    />
                  ) : null}
                </>
              ) : null}

              {isFulfillmentAdmin &&
              workspace !== 'sorting' &&
              receivingActive ? (
                <Button
                  variant="contained"
                  disabled={busy}
                  onClick={() => void requestCompleteReceiving()}
                  data-testid="ff-inbound-verify-complete"
                >
                  Завершить приёмку
                </Button>
              ) : null}

              {documentDistributionEnabled &&
              isFulfillmentAdmin &&
              addressStorageEnabled &&
              isSortingStatus(detail.status) &&
              workspace === 'full' ? (
                <Button
                  variant="contained"
                  disabled={distBusy || distributionCompleted}
                  onClick={() => setDistOpen(true)}
                  data-testid="ff-inbound-distribute-open"
                >
                  Распределить по ячейкам
                </Button>
              ) : null}

              {detail.status === 'draft' ? (
                <>
                  <Button
                    variant="contained"
                    disabled={draftLocked || busy}
                    onClick={() => void openPicker()}
                    data-testid="ff-inbound-add-products"
                  >
                    Добавить товар
                  </Button>
                  <Button
                    variant="contained"
                    color="secondary"
                    disabled={busy || detail.lines.length === 0}
                    onClick={() =>
                      isFulfillmentAdmin
                        ? void beginReceiving()
                        : void submitToWarehouse()
                    }
                    data-testid="ff-inbound-submit-warehouse"
                  >
                    {isFulfillmentAdmin ? 'Начать приёмку' : 'Передать на склад'}
                  </Button>
                </>
              ) : null}

              {canReopenReceiving ? (
                <Button
                  variant="outlined"
                  startIcon={<EditOutlined />}
                  disabled={busy}
                  onClick={() => void reopenReceiving()}
                  data-testid="ff-inbound-reopen-receiving"
                >
                  Редактировать
                </Button>
              ) : null}

              {waybillPrintEnabled && detail.lines.length > 0 ? (
                <Button
                  variant="outlined"
                  startIcon={<PrintOutlined />}
                  disabled={busy}
                  data-testid="ff-inbound-print-waybill"
                  onClick={() => {
                    const wh = requestWarehouse
                    const boxes = detail.boxes ?? []
                    printInboundSupplyWaybill({
                      documentId: detail.id,
                      documentNumber: displayDocumentNumber,
                      documentTypeLabel: operationTypeLabel,
                      statusLabel: inboundStatusRu(detail.status),
                      warehouseName: wh ? `${wh.name} (${wh.code})` : '—',
                      sellerName: detail.seller_name ?? null,
                      plannedDate: detail.planned_delivery_date,
                      createdAt: detail.created_at ?? null,
                      plannedBoxCount: detail.planned_box_count,
                      actualBoxCount: detail.actual_box_count ?? boxes.length,
                      lines: detail.lines.map((ln) => ({
                        sku_code: ln.sku_code,
                        product_name: ln.product_name,
                        quantity: ln.expected_qty,
                        received_qty: effectiveActualQty(ln, boxes, detail.status),
                      })),
                    })
                  }}
                >
                  Печать накладной
                </Button>
              ) : null}

              <Button
                variant="outlined"
                disabled={busy}
                onClick={() => void handleSaveDocument()}
                data-testid="ff-inbound-save"
              >
                Сохранить
              </Button>

              <Button variant="outlined" disabled={busy} onClick={handleClose} data-testid="ff-inbound-close">
                Закрыть
              </Button>
            </Stack>
          </Stack>

          {sortingView && receptionClosed ? (
            <>
              {isDoneStatus(detail.status) ? (
                <Alert severity="success" sx={{ mb: 2 }} data-testid="ff-sorting-posted-done">
                  Оприходовано — весь товар разложен по ячейкам хранения.
                </Alert>
              ) : null}
              <FfInboundSortingPanel
                token={token}
                requestId={requestId}
                warehouseId={detail.warehouse_id}
                completed={isDoneStatus(detail.status)}
                lines={(detail.lines ?? []).map((ln) => ({
                  product_id: ln.product_id,
                  sku_code: ln.sku_code,
                  product_name: ln.product_name,
                  actual_qty: ln.actual_qty,
                  posted_qty: ln.posted_qty ?? 0,
                }))}
                boxes={(detail.boxes ?? []).map((b) => ({
                  ...b,
                  remaining_qty: b.remaining_qty ?? 0,
                  lines: (b.lines ?? []).map((ln) => ({
                    ...ln,
                    posted_qty: ln.posted_qty ?? 0,
                    remaining_qty:
                      ln.remaining_qty ?? Math.max(0, ln.quantity - (ln.posted_qty ?? 0)),
                  })),
                }))}
                sortingRemainingQty={sortingRemainingTotal}
                onReload={async () => {
                  await loadDetail()
                }}
              />
            </>
          ) : null}

          {showInboundLinesTable ? (
            <TableContainer
              sx={{
                width: '100%',
                maxWidth: '100%',
                minWidth: 0,
                overflowX: 'auto',
                WebkitOverflowScrolling: 'touch',
              }}
            >
              {sortingView && receptionClosed ? (
                <Typography variant="subtitle2" sx={{ fontWeight: 700, mb: 1 }}>
                  Состав приёмки
                </Typography>
              ) : null}
              <Table
                size="small"
                data-testid="ff-inbound-lines-table"
                sx={{
                  tableLayout: 'fixed',
                  width: '100%',
                  minWidth: 760,
                  '& th': { py: 1.25 },
                  '& td': { py: 1.25 },
                  '& th, & td': { verticalAlign: 'middle' },
                }}
              >
                <TableHead>
                  <TableRow>
                    <TableCell sx={{ minWidth: 0, overflow: 'hidden' }}>
                      Товар
                    </TableCell>
                    <TableCell sx={{ width: 188 }}>
                      Габариты
                    </TableCell>
                    <TableCell align="right" sx={{ width: 112 }}>
                      План
                    </TableCell>
                    <TableCell align="right" sx={{ width: 200 }}>
                      Принято
                    </TableCell>
                  </TableRow>
                </TableHead>
                <TableBody>
                  {detail.lines.map((ln) => {
                  const displayMeta = productDisplayMetaFromCatalog(ln.product_id, ln, catalogById)
                  const boxes = detail.boxes ?? []
                  const effective = effectiveActualQty(ln, boxes, detail.status)
                  const hasDiscrepancy = effective !== ln.expected_qty
                  const matchesExpected = effective === ln.expected_qty && effective > 0
                  const discrepancyLabel = formatLineDiscrepancy(ln.expected_qty, effective)
                  const rowTestId = matchesExpected
                    ? 'ff-inbound-line-row-match'
                    : hasDiscrepancy
                      ? 'ff-inbound-line-row-discrepancy'
                      : 'ff-inbound-line-row'
                  const manualOpen = manualEditLineId === ln.id
                  return (
                    <TableRow
                      key={ln.id}
                      hover
                      data-testid={rowTestId}
                      sx={{
                        '& td': { px: 1.25 },
                        '& td:first-of-type': { pl: 1 },
                        '& td:last-of-type': { pr: 1 },
                        ...(matchesExpected
                          ? {
                              backgroundColor: (theme) =>
                                alpha(theme.palette.success.main, 0.12),
                            }
                          : null),
                        ...(hasDiscrepancy
                          ? {
                              backgroundColor: (theme) =>
                                alpha(theme.palette.error.main, 0.08),
                            }
                          : null),
                      }}
                    >
                      <InboundProductLineCell
                        meta={displayMeta}
                        productId={ln.product_id}
                        printTestId={`ff-inbound-line-print-${ln.id}`}
                      />
                      <TableCell sx={{ width: 188, minWidth: 0 }}>
                        <Stack direction="row" spacing={0.5} sx={{ alignItems: 'center', minWidth: 0 }}>
                          <Typography
                            variant="caption"
                            color="text.secondary"
                            sx={{
                              flex: '1 1 auto',
                              minWidth: 0,
                              overflow: 'hidden',
                              textOverflow: 'ellipsis',
                              whiteSpace: 'nowrap',
                            }}
                            title={formatLineDimensions(ln)}
                            data-testid="ff-inbound-line-dimensions"
                          >
                            {formatLineDimensions(ln)}
                          </Typography>
                          {isFulfillmentAdmin ? (
                            <Tooltip title="Габариты">
                              <Box component="span" sx={{ flex: '0 0 40px', display: 'inline-flex' }}>
                                <IconButton
                                  size="small"
                                  disabled={busy}
                                  onClick={() => openDimensionsEditor(ln)}
                                  data-testid="ff-inbound-line-dimensions-edit"
                                  aria-label="Габариты"
                                  sx={{ width: 40, height: 40 }}
                                >
                                  <StraightenOutlined fontSize="small" />
                                </IconButton>
                              </Box>
                            </Tooltip>
                          ) : null}
                        </Stack>
                      </TableCell>
                      <TableCell align="right" sx={{ width: 112, minWidth: 0 }}>
                        <Stack spacing={0.25} sx={{ alignItems: 'flex-end' }}>
                          <Typography
                            variant="body2"
                            sx={{ fontWeight: 600 }}
                            data-testid="ff-inbound-line-expected"
                          >
                            {ln.expected_qty}
                          </Typography>
                          {ln.added_by_fulfillment ? (
                            <Typography
                              variant="caption"
                              color="error.dark"
                              sx={{ whiteSpace: 'nowrap' }}
                              data-testid="ff-inbound-line-added-by-ff"
                            >
                              Добавлено ФФ
                            </Typography>
                          ) : null}
                        </Stack>
                      </TableCell>
                      <TableCell align="right" sx={{ width: 200, minWidth: 0 }}>
                        <Stack
                          direction="row"
                          spacing={0.75}
                          sx={{ justifyContent: 'flex-end', alignItems: 'center', minWidth: 0 }}
                        >
                          {manualOpen && actualEditable ? (
                            <TextField
                              type="text"
                              size="small"
                              value={
                                actualDraftByLineId[ln.id] ??
                                String(effectiveActualQty(ln, boxes, detail.status))
                              }
                              disabled={busy}
                              error={Boolean(actualDraftErrorByLineId[ln.id])}
                              helperText={actualDraftErrorByLineId[ln.id] || ' '}
                              inputRef={(node) => {
                                actualInputRefs.current[ln.id] = node
                              }}
                              onChange={(e) => {
                                const nextVal = e.target.value
                                actualDraftRef.current = {
                                  ...actualDraftRef.current,
                                  [ln.id]: nextVal,
                                }
                                setActualDraftErrorByLineId((prev) => ({
                                  ...prev,
                                  [ln.id]: '',
                                }))
                                setActualDraftByLineId((prev) => ({
                                  ...prev,
                                  [ln.id]: nextVal,
                                }))
                              }}
                              slotProps={{
                                htmlInput: {
                                  inputMode: 'numeric',
                                  pattern: '[0-9]*',
                                  'data-testid': 'ff-inbound-line-actual',
                                  onBlur: (e: FocusEvent<HTMLInputElement>) => {
                                    if (manualEditLineId !== ln.id) {
                                      return
                                    }
                                    void saveManualLineActual(ln.id, e.currentTarget.value)
                                  },
                                  onKeyDown: (e: KeyboardEvent<HTMLInputElement>) => {
                                    if (e.key === 'Enter') {
                                      e.preventDefault()
                                      void saveManualLineActual(ln.id, e.currentTarget.value)
                                    }
                                  },
                                },
                              }}
                              sx={{
                                flex: '0 0 116px',
                                width: 116,
                                '& .MuiFormHelperText-root': { mx: 0 },
                              }}
                            />
                          ) : (
                            <Stack spacing={0.1} sx={{ alignItems: 'flex-end', minWidth: 0, flex: '1 1 auto' }}>
                              <Typography
                                variant="body2"
                                sx={{ fontWeight: 700, minWidth: 24, textAlign: 'right' }}
                                data-testid="ff-inbound-line-actual-display"
                              >
                                {effective}
                              </Typography>
                              {discrepancyLabel ? (
                                <Typography
                                  variant="caption"
                                  color="error.dark"
                                  sx={{ lineHeight: 1.15, whiteSpace: 'nowrap' }}
                                  data-testid="ff-inbound-line-discrepancy"
                                >
                                  {discrepancyLabel}
                                </Typography>
                              ) : null}
                            </Stack>
                          )}
                          {actualEditable ? (
                            <IconButton
                              size="small"
                              aria-label="Править количество"
                              disabled={busy}
                              sx={{ flex: '0 0 40px', width: 40, height: 40 }}
                              onMouseDown={(e) => {
                                if (manualOpen) {
                                  e.preventDefault()
                                }
                              }}
                              onClick={() => {
                                if (manualOpen) {
                                  void saveManualLineActual(ln.id)
                                  return
                                }
                                setManualEditLineId(ln.id)
                                setActualDraftByLineId((prev) => ({
                                  ...prev,
                                  [ln.id]: String(effectiveActualQty(ln, boxes, detail.status)),
                                }))
                              }}
                              data-testid="ff-inbound-line-manual-edit"
                            >
                              <EditOutlined fontSize="small" />
                            </IconButton>
                          ) : null}
                        </Stack>
                      </TableCell>
                    </TableRow>
                  )
                })}
                {detail.lines.length === 0 ? (
                  <TableRow>
                    <TableCell colSpan={4}>
                      <Typography variant="body2" color="text.secondary">
                        Товаров пока нет. Нажмите «Добавить товар» или отсканируйте ШК товара из каталога селлера.
                      </Typography>
                    </TableCell>
                  </TableRow>
                ) : null}
              </TableBody>
            </Table>
          </TableContainer>
          ) : null}

          {sortingView && !receptionClosed ? (
            <Alert severity="info" sx={{ mt: 2 }} data-testid="ff-inbound-sorting-wait-reception">
              Сначала завершите приёмку в разделе <strong>Приёмка</strong>.
            </Alert>
          ) : null}

          {isFulfillmentAdmin && !sortingView && receivingActive && hasLineDiscrepancy ? (
            <Alert severity="warning" sx={{ mt: 2 }} data-testid="ff-inbound-discrepancy-hint">
              Есть расхождения с планом — при завершении потребуется подтверждение.
            </Alert>
          ) : null}

          {isFulfillmentAdmin &&
          !sortingView &&
          (linkedDiscrepancyActs.length > 0 || discrepancyActsError) ? (
            <Paper
              variant="outlined"
              sx={{ mt: 2, p: 1.5 }}
              data-testid="ff-inbound-discrepancy-acts"
            >
              <Stack spacing={1.25}>
                <Stack
                  direction={{ xs: 'column', sm: 'row' }}
                  spacing={1}
                  sx={{ alignItems: { sm: 'center' }, justifyContent: 'space-between' }}
                >
                  <Typography variant="subtitle2" sx={{ fontWeight: 800 }}>
                    Акты расхождения
                  </Typography>
                  {discrepancyActsBusy ? (
                    <CircularProgress size={18} data-testid="ff-inbound-discrepancy-acts-loading" />
                  ) : null}
                </Stack>
                {discrepancyActsError ? (
                  <Alert severity="error" data-testid="ff-inbound-discrepancy-acts-error">
                    {discrepancyActsError}
                  </Alert>
                ) : null}
                {linkedDiscrepancyActs.map((act) => (
                  <Box
                    key={act.id}
                    sx={{ borderTop: 1, borderColor: 'divider', pt: 1 }}
                    data-testid="ff-inbound-discrepancy-act"
                  >
                    <Stack
                      direction={{ xs: 'column', sm: 'row' }}
                      spacing={1}
                      sx={{ alignItems: { sm: 'center' }, justifyContent: 'space-between', mb: 1 }}
                    >
                      <Stack direction="row" spacing={1} sx={{ alignItems: 'center', flexWrap: 'wrap' }}>
                        <Typography variant="body2" sx={{ fontWeight: 700 }}>
                          {discrepancyActTitle(act.created_at)}
                        </Typography>
                        <Chip
                          size="small"
                          label={discrepancyActStatusRu(act.status)}
                          color={
                            act.status === 'approved'
                              ? 'success'
                              : act.status === 'rejected'
                                ? 'error'
                                : 'default'
                          }
                          data-testid="ff-inbound-discrepancy-act-status"
                        />
                      </Stack>
                      {act.status === 'confirmed' ? (
                        <Stack direction="row" spacing={1}>
                          <Button
                            size="small"
                            variant="contained"
                            disabled={discrepancyActsBusy}
                            onClick={() => void resolveDiscrepancyAct(act.id, 'approve')}
                            data-testid="ff-inbound-discrepancy-act-approve"
                          >
                            Утвердить
                          </Button>
                          <Button
                            size="small"
                            variant="outlined"
                            color="error"
                            disabled={discrepancyActsBusy}
                            onClick={() => void resolveDiscrepancyAct(act.id, 'reject')}
                            data-testid="ff-inbound-discrepancy-act-reject"
                          >
                            Отклонить
                          </Button>
                        </Stack>
                      ) : null}
                    </Stack>
                    <Table size="small" data-testid="ff-inbound-discrepancy-act-lines">
                      <TableHead>
                        <TableRow>
                          <TableCell>Товар</TableCell>
                          <TableCell align="right">Расхождение</TableCell>
                        </TableRow>
                      </TableHead>
                      <TableBody>
                        {act.lines.map((line) => (
                          <TableRow key={line.id} data-testid="ff-inbound-discrepancy-act-line">
                            <TableCell>
                              <Typography variant="body2" sx={{ fontWeight: 700 }}>
                                {line.sku_code}
                              </Typography>
                              <Typography variant="caption" color="text.secondary">
                                {line.product_name}
                              </Typography>
                            </TableCell>
                            <TableCell align="right">{signedQty(line.quantity)}</TableCell>
                          </TableRow>
                        ))}
                      </TableBody>
                    </Table>
                  </Box>
                ))}
              </Stack>
            </Paper>
          ) : null}

          {isFulfillmentAdmin && !sortingView ? (
            <Accordion
              expanded={packagesExpanded}
              onChange={(_, expanded) => setPackagesExpanded(expanded)}
              sx={{ mt: 2, border: 1, borderColor: 'divider', boxShadow: 'none', '&:before': { display: 'none' } }}
              data-testid="ff-inbound-packages-accordion"
            >
              <AccordionSummary
                expandIcon={<ExpandMoreOutlined />}
                data-testid="ff-inbound-packages-toggle"
              >
                <Stack direction="row" spacing={1.5} sx={{ alignItems: 'center', flexWrap: 'wrap' }}>
                  <Typography variant="subtitle2" sx={{ fontWeight: 800 }}>
                    Короба и грузоместа
                  </Typography>
                  <Chip size="small" label={`Короба: ${boxes.length}`} />
                  <Chip size="small" label={`Грузоместа: ${cargoPlaces.length}`} />
                </Stack>
              </AccordionSummary>
              <AccordionDetails data-testid="ff-inbound-boxes-panel">
                <Stack spacing={1.5}>
                  <Stack
                    direction={{ xs: 'column', sm: 'row' }}
                    spacing={1}
                    sx={{ alignItems: { sm: 'center' }, flexWrap: 'wrap' }}
                  >
                    <Button
                      variant="contained"
                      disabled={busy || !receivingActive}
                      onClick={() => void handleCreateBox()}
                      data-testid="ff-inbound-add-to-box"
                    >
                      Создать короба
                    </Button>
                    <Button
                      variant="contained"
                      disabled={busy || !receivingActive}
                      onClick={() => {
                        setCargoError(null)
                        setCargoDialogOpen(true)
                      }}
                      data-testid="ff-inbound-create-cargo-places"
                    >
                      Создать грузоместа
                    </Button>
                    {boxImportEnabled ? (
                      <Button
                        variant="outlined"
                        disabled={busy || !receivingActive}
                        onClick={() => setBoxImportOpen(true)}
                        data-testid="ff-inbound-import-boxes"
                      >
                        Загрузить по накладной
                      </Button>
                    ) : null}
                    <Button
                      variant="outlined"
                      disabled={busy || boxes.length === 0}
                      onClick={() => void printAllInboundBoxLabels()}
                      data-testid="ff-inbound-boxes-print-all"
                    >
                      Печать коробов
                    </Button>
                    <Button
                      variant="outlined"
                      disabled={busy || cargoPlaces.length === 0}
                      onClick={() => void printAllInboundCargoPlaceLabels()}
                      data-testid="ff-inbound-cargo-places-print-all"
                    >
                      Печать грузомест
                    </Button>
                  </Stack>

                  <Stack spacing={1}>
                    <Typography variant="body2" sx={{ fontWeight: 700 }}>
                      Короба
                    </Typography>
                    {boxes.map((box) => {
                      const visibleLines = box.lines.filter((ln) => ln.quantity > 0)
                      return (
                        <Paper
                          key={box.id}
                          variant="outlined"
                          sx={{ overflow: 'hidden', bgcolor: 'background.paper' }}
                          data-testid="ff-inbound-box-row"
                        >
                          <Stack
                            direction={{ xs: 'column', sm: 'row' }}
                            spacing={1}
                            sx={{
                              alignItems: { sm: 'center' },
                              px: 1.25,
                              py: 1,
                              bgcolor: 'action.hover',
                              borderBottom: 1,
                              borderColor: 'divider',
                            }}
                            data-testid={`ff-inbound-box-header-${box.id}`}
                          >
                            <Typography variant="body2" sx={{ fontWeight: 700 }}>
                              Короб № {box.box_number}{' '}
                              <Typography component="code" variant="body2">
                                {box.internal_barcode}
                              </Typography>
                            </Typography>
                            <Box sx={{ flexGrow: 1 }} />
                            <Stack direction="row" spacing={0.5} sx={{ flexWrap: 'wrap' }}>
                              <Button
                                size="small"
                                variant="contained"
                                disabled={busy || !receivingActive}
                                onClick={() => openBoxAddDialog(box.id)}
                                data-testid={`ff-inbound-box-fill-${box.id}`}
                              >
                                Наполнить
                              </Button>
                              <Button
                                size="small"
                                variant="outlined"
                                disabled={busy || !receivingActive || visibleLines.length > 0}
                                onClick={() => void deleteInboundBox(box.id)}
                                data-testid={`ff-inbound-box-delete-${box.id}`}
                              >
                                Удалить
                              </Button>
                              <Button
                                size="small"
                                variant="outlined"
                                disabled={busy}
                                onClick={() => void printInboundBoxLabel(box)}
                                data-testid={`ff-inbound-box-print-${box.id}`}
                              >
                                Печать
                              </Button>
                            </Stack>
                          </Stack>
                          {visibleLines.length > 0 ? (
                            <Stack spacing={0.25} sx={{ px: 1.25, py: 1, bgcolor: 'background.paper' }}>
                              {visibleLines.map((ln) => (
                                <Typography key={ln.id} variant="body2" color="text.secondary">
                                  {ln.sku_code} · {ln.product_name}: {ln.quantity}
                                </Typography>
                              ))}
                            </Stack>
                          ) : (
                            <Typography
                              variant="body2"
                              color="text.secondary"
                              sx={{ px: 1.25, py: 1, bgcolor: 'background.paper' }}
                            >
                              Пока нет товаров
                            </Typography>
                          )}
                        </Paper>
                      )
                    })}
                  </Stack>

                  <Stack spacing={1}>
                    <Typography variant="body2" sx={{ fontWeight: 700 }}>
                      Грузоместа
                    </Typography>
                    {cargoPlaces.map((place) => (
                      <Paper
                        key={place.id}
                        variant="outlined"
                        sx={{ px: 1.25, py: 1 }}
                        data-testid="ff-inbound-cargo-place-row"
                      >
                        <Stack direction={{ xs: 'column', sm: 'row' }} spacing={1} sx={{ alignItems: { sm: 'center' } }}>
                          <Typography variant="body2" sx={{ fontWeight: 700 }}>
                            Грузоместо № {place.place_number}{' '}
                            <Typography component="code" variant="body2">
                              {place.internal_barcode}
                            </Typography>
                          </Typography>
                          <Box sx={{ flexGrow: 1 }} />
                          {place.label_printed_at ? (
                            <Chip size="small" color="success" label="Этикетка напечатана" />
                          ) : null}
                          <Button
                            size="small"
                            variant="outlined"
                            disabled={busy}
                            onClick={() => void printInboundCargoPlaceLabel(place)}
                            data-testid={`ff-inbound-cargo-place-print-${place.id}`}
                          >
                            Печать
                          </Button>
                        </Stack>
                      </Paper>
                    ))}
                  </Stack>
                </Stack>
              </AccordionDetails>
            </Accordion>
          ) : null}

          {isFulfillmentAdmin && !sortingView ? (
            <Box sx={{ mt: 2 }}>
              {workspace === 'reception' && isSortingStatus(detail.status) ? (
                <Alert severity="success" sx={{ mt: 2 }} data-testid="ff-inbound-moved-to-sorting">
                  {addressStorageEnabled
                    ? 'Приёмка завершена. Остаток принят на склад ФФ (зона «Сортировка»). Разложение по ячейкам — в разделе Сортировка.'
                    : 'Приёмка завершена. Остаток принят на склад ФФ (зона «Сортировка»).'}
                </Alert>
              ) : null}

              {documentDistributionEnabled &&
              addressStorageEnabled &&
              isSortingStatus(detail.status) &&
              workspace === 'full' ? (
                <Paper variant="outlined" sx={{ p: 2 }} data-testid="ff-inbound-admin-distribution">
                  <Stack direction={{ xs: 'column', sm: 'row' }} spacing={1} sx={{ alignItems: { sm: 'center' } }}>
                    <Box sx={{ flexGrow: 1 }}>
                      <Typography variant="subtitle2" sx={{ fontWeight: 800 }}>
                        Распределение по ячейкам
                      </Typography>
                      <Typography variant="body2" color="text.secondary">
                        {distributionCompleted
                          ? hasNoCellPending
                            ? 'Распределение зафиксировано без ячеек — товар остаётся в зоне сортировки. Откройте заново и разложите принятое.'
                            : 'Всё принятое разложено по ячейкам хранения.'
                          : 'Разложите принятое по ячейкам хранения. Можно частями: разложенное сразу доступно к резерву, пока не разложено всё — приёмка остаётся в этом разделе.'}
                      </Typography>
                      {requestWarehouse ? (
                        <Typography
                          variant="body2"
                          color="text.secondary"
                          sx={{ mt: 0.5 }}
                          data-testid="ff-inbound-distribution-warehouse"
                        >
                          Склад этой заявки:{' '}
                          <strong>
                            {requestWarehouse.name} ({requestWarehouse.code})
                          </strong>
                          . В списке «Ячейка» — только ячейки этого склада (
                          {locations.length === 0
                            ? 'пока нет'
                            : locations.map((l) => l.code).join(', ')}
                          ).
                        </Typography>
                      ) : null}
                    </Box>
                  </Stack>

                  {distError ? (
                    <Alert severity="error" sx={{ mt: 2 }} data-testid="ff-inbound-distribution-error">
                      {distError}
                    </Alert>
                  ) : null}

                  {distributionCompleted && hasNoCellPending ? (
                    <Alert severity="warning" sx={{ mt: 2 }} data-testid="ff-inbound-distribution-stuck-empty">
                      Распределение зафиксировано, но принятый товар не разложен по ячейкам — в разделе{' '}
                      <strong>Каталог</strong> остатков не будет. Откройте распределение заново и укажите ячейки
                      для всего принятого количества.
                    </Alert>
                  ) : null}

                  {locations.length === 0 &&
                  !distributionCompleted &&
                  (distOpen || isSortingStatus(detail.status)) ? (
                    <Alert severity="warning" sx={{ mt: 2 }} data-testid="ff-inbound-distribution-no-locations">
                      <Typography variant="body2" sx={{ mb: 1 }}>
                        На складе этой заявки <strong>нет ячеек</strong> — поэтому список «Ячейка» пустой и
                        не открывается. Создайте ячейку здесь или в разделе{' '}
                        <strong>Ячейки</strong> (тот же склад).
                      </Typography>
                      <Stack direction={{ xs: 'column', sm: 'row' }} spacing={1}>
                        <TextField
                          size="small"
                          label="Код новой ячейки"
                          value={newLocationCode}
                          onChange={(e) => setNewLocationCode(e.target.value)}
                          disabled={distBusy}
                          placeholder="A-01"
                          slotProps={{
                            htmlInput: { 'data-testid': 'ff-inbound-distribution-new-location-code' },
                          }}
                        />
                        <Button
                          variant="contained"
                          disabled={distBusy || !newLocationCode.trim()}
                          onClick={() => void createWarehouseLocation()}
                          data-testid="ff-inbound-distribution-create-location"
                        >
                          Создать ячейку
                        </Button>
                      </Stack>
                    </Alert>
                  ) : null}

                  {distOpen || distributionCompleted ? (
                    <Box sx={{ mt: 2 }}>
                      <Stack direction={{ xs: 'column', sm: 'row' }} spacing={1} sx={{ mb: 1.5, alignItems: { sm: 'center' } }}>
                        <Typography variant="body2" sx={{ fontWeight: 700 }}>
                          Таблица распределения {distributionCompleted ? ' (зафиксировано)' : ''}
                        </Typography>
                        <Box sx={{ flexGrow: 1 }} />
                        {distributionEditable ? (
                          <>
                            <Button
                              variant="outlined"
                              disabled={distBusy}
                              onClick={() =>
                                setDistLines((prev) => [
                                  ...prev,
                                  {
                                    box_id: defaultPutawayBoxId,
                                    product_id: '',
                                    storage_location_id: '',
                                    quantity: '',
                                  },
                                ])
                              }
                              data-testid="ff-inbound-distribution-add-row"
                            >
                              Добавить строку
                            </Button>
                            <Button
                              variant="outlined"
                              disabled={distBusy}
                              onClick={() => void saveDistribution()}
                              data-testid="ff-inbound-distribution-save"
                            >
                              Сохранить
                            </Button>
                            <Button
                              variant="contained"
                              disabled={distBusy}
                              onClick={() => void completeDistribution()}
                              data-testid="ff-inbound-distribution-complete"
                            >
                              {hasNoCellPending ? 'Применить раскладку' : 'Завершить распределение'}
                            </Button>
                          </>
                        ) : canReopenDistribution ? (
                          <Button
                            variant="outlined"
                            color="warning"
                            disabled={distBusy}
                            onClick={() => void reopenDistribution()}
                            data-testid="ff-inbound-distribution-reopen"
                          >
                            Открыть распределение заново
                          </Button>
                        ) : null}
                      </Stack>

                      <TableContainer component={Paper} variant="outlined" sx={{ mb: 2 }}>
                        <Table size="small" data-testid="ff-inbound-distribution-table">
                          <TableHead>
                            <TableRow>
                              <TableCell sx={{ width: 420 }}>Товар</TableCell>
                              <TableCell align="right" sx={{ width: 140 }}>Кол-во</TableCell>
                              <TableCell sx={{ width: 260 }}>Ячейка</TableCell>
                              {distributionEditable ? <TableCell align="right" sx={{ width: 84 }} /> : null}
                            </TableRow>
                          </TableHead>
                          <TableBody>
                            {distLines.map((row, idx) => {
                              const accepted = acceptedQtyByProductId.get(row.product_id) ?? 0
                              const usedOther = (distSumByProductId.get(row.product_id) ?? 0) - (Math.floor(Number(row.quantity)) || 0)
                              const maxForRow = Math.max(accepted - usedOther, 0)
                              return (
                                <TableRow key={idx} data-testid="ff-inbound-distribution-row">
                                  <TableCell>
                                    <FormControl size="small" fullWidth>
                                      <InputLabel id={`ff-dist-prod-${idx}`}>Товар</InputLabel>
                                      <Select
                                        labelId={`ff-dist-prod-${idx}`}
                                        label="Товар"
                                        value={row.product_id}
                                        disabled={distBusy || !distributionEditable}
                                        onChange={(e) => {
                                          const v = String(e.target.value)
                                          setDistLines((prev) =>
                                            prev.map((r, i) => (i === idx ? { ...r, product_id: v } : r)),
                                          )
                                          if (v) void loadCellHints(v)
                                        }}
                                        data-testid="ff-inbound-distribution-product"
                                      >
                                        <MenuItem value="">
                                          <em>Выберите товар</em>
                                        </MenuItem>
                                        {distributableProducts.map((p) => (
                                          <MenuItem key={p.product_id} value={p.product_id}>
                                            {p.sku_code} · {p.product_name} (принято {p.accepted_qty})
                                          </MenuItem>
                                        ))}
                                      </Select>
                                    </FormControl>
                                  </TableCell>
                                  <TableCell align="right">
                                    <TextField
                                      type="number"
                                      size="small"
                                      value={row.quantity}
                                      disabled={distBusy || !distributionEditable}
                                      onChange={(e) =>
                                        setDistLines((prev) =>
                                          prev.map((r, i) => (i === idx ? { ...r, quantity: e.target.value } : r)),
                                        )
                                      }
                                      slotProps={{ htmlInput: { min: 1, max: maxForRow, 'data-testid': 'ff-inbound-distribution-qty' } }}
                                    />
                                  </TableCell>
                                  <TableCell>
                                    <Stack direction="row" spacing={0.5} sx={{ alignItems: 'center' }}>
                                      <FormControl size="small" sx={{ flexGrow: 1 }}>
                                        <InputLabel id={`ff-dist-loc-${idx}`}>Ячейка</InputLabel>
                                        <Select
                                          labelId={`ff-dist-loc-${idx}`}
                                          label="Ячейка"
                                          value={row.storage_location_id}
                                          disabled={distBusy || !distributionEditable || locations.length === 0}
                                          onChange={(e) => {
                                            const v = String(e.target.value)
                                            setDistLines((prev) =>
                                              prev.map((r, i) =>
                                                i === idx ? { ...r, storage_location_id: v } : r,
                                              ),
                                            )
                                          }}
                                          data-testid="ff-inbound-distribution-location"
                                        >
                                          <MenuItem value="">
                                            <em>Выберите ячейку</em>
                                          </MenuItem>
                                          {locations.map((loc) => (
                                            <MenuItem key={loc.id} value={loc.id}>
                                              <Box>
                                                <Typography variant="body2" component="span">
                                                  {loc.code}
                                                </Typography>
                                                <Typography
                                                  variant="caption"
                                                  color="text.secondary"
                                                  component="div"
                                                >
                                                  {loc.barcode}
                                                </Typography>
                                              </Box>
                                            </MenuItem>
                                          ))}
                                        </Select>
                                      </FormControl>
                                      {row.storage_location_id ? (
                                        <Tooltip title="Печать ШК ячейки">
                                          <span>
                                            <IconButton
                                              size="small"
                                              aria-label="Печать ШК ячейки"
                                              disabled={distBusy || !distributionEditable}
                                              onClick={() =>
                                                printDistributionLocationLabel(row.storage_location_id)
                                              }
                                              data-testid="ff-inbound-distribution-location-print"
                                            >
                                              <PrintOutlined fontSize="small" />
                                            </IconButton>
                                          </span>
                                        </Tooltip>
                                      ) : null}
                                    </Stack>
                                    {row.product_id && (cellHintsByProductId[row.product_id]?.length ?? 0) > 0 ? (
                                      <Stack
                                        direction="row"
                                        spacing={0.5}
                                        sx={{ mt: 0.75, flexWrap: 'wrap' }}
                                        data-testid="ff-inbound-cell-hints"
                                      >
                                        <Typography
                                          variant="caption"
                                          color="text.secondary"
                                          sx={{ alignSelf: 'center', mr: 0.5 }}
                                        >
                                          Уже лежит:
                                        </Typography>
                                        {cellHintsByProductId[row.product_id]!.map((h) => (
                                          <Chip
                                            key={h.storage_location_id}
                                            size="small"
                                            variant="outlined"
                                            label={`${h.storage_location_code} (${h.available})`}
                                            disabled={distBusy || !distributionEditable}
                                            onClick={() => {
                                              setDistLines((prev) =>
                                                prev.map((r, i) =>
                                                  i === idx
                                                    ? { ...r, storage_location_id: h.storage_location_id }
                                                    : r,
                                                ),
                                              )
                                            }}
                                            data-testid="ff-inbound-cell-hint"
                                          />
                                        ))}
                                      </Stack>
                                    ) : null}
                                  </TableCell>
                                  {distributionEditable ? (
                                    <TableCell align="right">
                                      <Button
                                        variant="text"
                                        color="error"
                                        disabled={distBusy}
                                        onClick={() => setDistLines((prev) => prev.filter((_, i) => i !== idx))}
                                        data-testid="ff-inbound-distribution-remove-row"
                                      >
                                        Удалить
                                      </Button>
                                    </TableCell>
                                  ) : null}
                                </TableRow>
                              )
                            })}
                            {distLines.length === 0 ? (
                              <TableRow>
                                <TableCell colSpan={distributionEditable ? 4 : 3}>
                                  <Typography variant="body2" color="text.secondary">
                                    Пока нет строк распределения.
                                  </Typography>
                                </TableCell>
                              </TableRow>
                            ) : null}
                          </TableBody>
                        </Table>
                      </TableContainer>

                      <Paper
                        variant="outlined"
                        sx={{
                          p: 2,
                          ...(hasNoCellPending
                            ? {
                                bgcolor: (theme) => alpha(theme.palette.warning.main, 0.14),
                                borderColor: (theme) => alpha(theme.palette.warning.main, 0.45),
                              }
                            : null),
                        }}
                        data-testid="ff-inbound-distribution-no-cell"
                        data-pending={hasNoCellPending ? '1' : '0'}
                      >
                        <Typography
                          variant="body2"
                          sx={{ fontWeight: 700, mb: 1 }}
                          color={hasNoCellPending ? 'warning.dark' : 'text.primary'}
                        >
                          Остаток «Без ячейки»
                        </Typography>
                        <Stack spacing={0.5}>
                          {noCellRemainingLines.map((p) => (
                            <Typography
                              key={p.product_id}
                              variant="body2"
                              color="warning.dark"
                              data-testid="ff-inbound-distribution-no-cell-line"
                            >
                              {p.sku_code} · {p.product_name}: {p.remaining}
                            </Typography>
                          ))}
                          {!hasNoCellPending ? (
                            <Typography variant="body2" color="text.secondary">
                              Остатков нет.
                            </Typography>
                          ) : null}
                        </Stack>
                      </Paper>
                    </Box>
                  ) : null}
                </Paper>
              ) : null}
            </Box>
          ) : null}
        </Paper>
      )}

      <WbProductPickerDialog
        open={pickerOpen}
        busy={busy}
        catalog={catalog}
        disabledProductIds={pickerDisabledProductIds}
        testIdPrefix="ff-inbound-picker"
        variant="ff"
        qtyColumnLabel={detail?.status === 'draft' ? 'Кол-во в заявку' : 'Факт'}
        initialSearch={pickerInitialSearch}
        applyLabel={detail?.status === 'draft' ? 'Добавить в заявку' : 'Добавить товар'}
        emptyMessage="В каталоге селлера нет товаров по этому поиску."
        onClose={() => setPickerOpen(false)}
        onApply={applyPicker}
      />

      <Dialog
        open={dimensionsLine != null}
        onClose={() => {
          if (!busy) setDimensionsLine(null)
        }}
        fullWidth
        maxWidth="xs"
        data-testid="ff-inbound-dimensions-dialog"
      >
        <DialogTitle>Габариты товара</DialogTitle>
        <DialogContent>
          <Stack spacing={2} sx={{ mt: 1 }}>
            {dimensionError ? (
              <Alert severity="error" data-testid="ff-inbound-dimensions-error">
                {dimensionError}
              </Alert>
            ) : null}
            <Typography variant="body2" color="text.secondary">
              {dimensionsLine?.product_name ?? ''}
            </Typography>
            <Stack direction={{ xs: 'column', sm: 'row' }} spacing={1}>
              <TextField
                size="small"
                label="Длина, мм"
                type="number"
                value={dimensionDraft.length}
                onChange={(e) => setDimensionDraft((prev) => ({ ...prev, length: e.target.value }))}
                slotProps={{ htmlInput: { min: 1, 'data-testid': 'ff-inbound-dimensions-length' } }}
              />
              <TextField
                size="small"
                label="Ширина, мм"
                type="number"
                value={dimensionDraft.width}
                onChange={(e) => setDimensionDraft((prev) => ({ ...prev, width: e.target.value }))}
                slotProps={{ htmlInput: { min: 1, 'data-testid': 'ff-inbound-dimensions-width' } }}
              />
              <TextField
                size="small"
                label="Высота, мм"
                type="number"
                value={dimensionDraft.height}
                onChange={(e) => setDimensionDraft((prev) => ({ ...prev, height: e.target.value }))}
                slotProps={{ htmlInput: { min: 1, 'data-testid': 'ff-inbound-dimensions-height' } }}
              />
            </Stack>
            <TextField
              size="small"
              label="Вес, г"
              type="number"
              value={dimensionDraft.weight}
              onChange={(e) => setDimensionDraft((prev) => ({ ...prev, weight: e.target.value }))}
              slotProps={{ htmlInput: { min: 1, 'data-testid': 'ff-inbound-dimensions-weight' } }}
            />
          </Stack>
        </DialogContent>
        <DialogActions>
          <Button disabled={busy} onClick={() => setDimensionsLine(null)}>
            Отмена
          </Button>
          <Button
            variant="contained"
            disabled={busy}
            onClick={() => void saveDimensions()}
            data-testid="ff-inbound-dimensions-save"
          >
            Сохранить
          </Button>
        </DialogActions>
      </Dialog>

      {boxAddDialogBox && boxAddDialogBoxId ? (
        <FfInboundBoxAddDialog
          open
          onClose={() => setBoxAddDialogBoxId(null)}
          requestId={requestId}
          boxId={boxAddDialogBoxId}
          boxLabel={`Короб № ${boxAddDialogBox.box_number} · ${boxAddDialogBox.internal_barcode}`}
          readOnly={!receivingActive}
          token={token}
          requestLines={detail?.lines ?? []}
          boxLines={boxAddDialogBox.lines}
          catalogById={catalogById}
          onUpdated={async () => {
            await loadDetail()
          }}
        />
      ) : null}

      <Snackbar
        open={importSuccessMsg !== null}
        autoHideDuration={3500}
        onClose={() => setImportSuccessMsg(null)}
        anchorOrigin={{ vertical: 'bottom', horizontal: 'center' }}
      >
        <Alert
          severity="success"
          variant="filled"
          onClose={() => setImportSuccessMsg(null)}
          data-testid="ff-inbound-import-success-snackbar"
          sx={{ width: '100%' }}
        >
          {importSuccessMsg}
        </Alert>
      </Snackbar>

      {boxImportEnabled && boxImportOpen ? (
        <BoxImportDialog
          open={boxImportOpen}
          token={token}
          requestId={requestId}
          importBasePath={`/operations/inbound-intake-requests/${requestId}/import-boxes`}
          testIdPrefix="ff-inbound-box-import"
          onClose={() => setBoxImportOpen(false)}
          onApplied={async (message) => {
            setImportSuccessMsg(message)
            await loadDetail()
          }}
        />
      ) : null}

      <Dialog
        open={cargoDialogOpen}
        onClose={() => {
          if (!busy) setCargoDialogOpen(false)
        }}
        maxWidth="xs"
        fullWidth
        data-testid="ff-inbound-cargo-places-dialog"
      >
        <DialogTitle>Создать грузоместа</DialogTitle>
        <DialogContent>
          <Stack spacing={2} sx={{ mt: 1 }}>
            {cargoError ? (
              <Alert severity="error" data-testid="ff-inbound-cargo-places-error">
                {cargoError}
              </Alert>
            ) : null}
            <TextField
              size="small"
              label="Количество грузомест"
              type="number"
              value={cargoCount}
              disabled={busy}
              onChange={(e) => setCargoCount(e.target.value)}
              slotProps={{ htmlInput: { min: 1, max: 1000, 'data-testid': 'ff-inbound-cargo-places-count' } }}
            />
          </Stack>
        </DialogContent>
        <DialogActions>
          <Button disabled={busy} onClick={() => setCargoDialogOpen(false)}>
            Отмена
          </Button>
          <Button
            variant="contained"
            disabled={busy}
            onClick={() => void createCargoPlaces()}
            data-testid="ff-inbound-cargo-places-create"
          >
            Создать
          </Button>
        </DialogActions>
      </Dialog>

      <Snackbar
        open={scanToastError !== null}
        autoHideDuration={3500}
        onClose={() => {
          setScanToastError(null)
          setScanAddBarcode(null)
        }}
        anchorOrigin={{ vertical: 'bottom', horizontal: 'center' }}
      >
        <Alert
          severity="error"
          variant="filled"
          onClose={() => {
            setScanToastError(null)
            setScanAddBarcode(null)
          }}
          action={
            scanAddBarcode ? (
              <Button
                color="inherit"
                size="small"
                onClick={() => {
                  const barcode = scanAddBarcode
                  setScanToastError(null)
                  setScanAddBarcode(null)
                  void openPicker(barcode)
                }}
                data-testid="ff-inbound-scan-add-product"
              >
                Добавить товар
              </Button>
            ) : undefined
          }
          data-testid="ff-inbound-scan-error-snackbar"
          sx={{ width: '100%' }}
        >
          {scanToastError}
        </Alert>
      </Snackbar>

      <Snackbar
        open={saveSuccessMsg !== null}
        autoHideDuration={2500}
        onClose={() => setSaveSuccessMsg(null)}
        anchorOrigin={{ vertical: 'bottom', horizontal: 'center' }}
      >
        <Alert
          severity="success"
          variant="filled"
          onClose={() => setSaveSuccessMsg(null)}
          data-testid="ff-inbound-save-success-snackbar"
          sx={{ width: '100%' }}
        >
          {saveSuccessMsg}
        </Alert>
      </Snackbar>

      <Dialog
        open={closeConfirmOpen}
        onClose={() => setCloseConfirmOpen(false)}
        maxWidth="xs"
        fullWidth
        data-testid="ff-inbound-close-confirm-dialog"
      >
        <DialogTitle>Закрыть без сохранения?</DialogTitle>
        <DialogContent>
          <Typography variant="body2" color="text.secondary">
            В строке факта осталось несохранённое количество.
          </Typography>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setCloseConfirmOpen(false)}>Остаться</Button>
          <Button
            color="warning"
            variant="contained"
            onClick={() => {
              setCloseConfirmOpen(false)
              onClose()
            }}
            data-testid="ff-inbound-close-confirm"
          >
            Закрыть
          </Button>
        </DialogActions>
      </Dialog>

      <Dialog
        open={finishConfirmOpen}
        onClose={() => setFinishConfirmOpen(false)}
        data-testid="ff-inbound-discrepancy-dialog"
        maxWidth="sm"
        fullWidth
      >
        <DialogTitle>Есть расхождения, провести приёмку?</DialogTitle>
        <DialogContent>
          <Stack spacing={2}>
            {discrepancyLines.length > 0 ? (
              <TableContainer component={Paper} variant="outlined">
                <Table size="small" data-testid="ff-inbound-discrepancy-lines">
                  <TableHead>
                    <TableRow>
                      <TableCell>SKU</TableCell>
                      <TableCell align="right">Ожидалось</TableCell>
                      <TableCell align="right">Принято</TableCell>
                      <TableCell align="right">Отклонение</TableCell>
                    </TableRow>
                  </TableHead>
                  <TableBody>
                    {discrepancyLines.map((line) => (
                      <TableRow key={line.productId} data-testid="ff-inbound-discrepancy-line">
                        <TableCell>
                          <Typography variant="body2" sx={{ fontWeight: 700 }}>
                            {line.skuCode}
                          </Typography>
                          {line.productName ? (
                            <Typography variant="caption" color="text.secondary">
                              {line.productName}
                            </Typography>
                          ) : null}
                        </TableCell>
                        <TableCell align="right">{line.expectedQty}</TableCell>
                        <TableCell align="right">{line.acceptedQty}</TableCell>
                        <TableCell align="right">
                          {line.shortage > 0 ? `Недостача ${line.shortage}` : `Излишек ${line.surplus}`}
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </TableContainer>
            ) : (
              <Typography variant="body2" color="text.secondary">
                По SKU расхождений нет.
              </Typography>
            )}

            <Paper
              variant="outlined"
              sx={{
                p: 1.5,
                bgcolor: receivingTotals.hasBoxDiscrepancy
                  ? (theme) => alpha(theme.palette.warning.main, 0.12)
                  : 'background.paper',
              }}
              data-testid="ff-inbound-discrepancy-box-summary"
            >
              <Typography variant="body2" sx={{ fontWeight: 700 }}>
                Короба: {receivingTotals.actualBoxes}
                {receivingTotals.plannedBoxes != null ? ` из ${receivingTotals.plannedBoxes}` : ''}
              </Typography>
              {receivingTotals.hasBoxDiscrepancy ? (
                <Typography variant="body2" color="warning.dark">
                  Количество коробов отличается от плана.
                </Typography>
              ) : null}
            </Paper>
          </Stack>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setFinishConfirmOpen(false)} disabled={busy}>
            Отмена
          </Button>
          <Button
            variant="contained"
            color="warning"
            disabled={busy}
            onClick={() => void completeReceiving()}
            data-testid="ff-inbound-discrepancy-confirm"
          >
            Завершить приёмку
          </Button>
        </DialogActions>
      </Dialog>
    </Box>
    </FfProductMarkingPrintProvider>
  )
}
