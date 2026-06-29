import { useCallback, useEffect, useMemo, useState } from 'react'
import EditOutlined from '@mui/icons-material/EditOutlined'
import PrintOutlined from '@mui/icons-material/PrintOutlined'
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
  FormControl,
  IconButton,
  InputLabel,
  MenuItem,
  Paper,
  Select,
  Snackbar,
  Stack,
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
import { FfProductLineCells, FfProductTableHeadCells } from '../../components/FfProductLineCells'
import { WbProductPickerDialog } from '../../components/WbProductPickerDialog'
import { WmsDateField } from '../../components/WmsDateField'
import {
  productDisplayMetaFromCatalog,
  type WbProductCatalogRow,
} from '../../types/wbProductCatalog'
import { printBarcodeLabel } from '../../utils/printBarcodeLabel'
import { printInboundSupplyWaybill } from '../../utils/printShipmentWaybill'
import { readApiErrorMessage } from '../../utils/readApiErrorMessage'
import { FfInboundBoxAddDialog } from './FfInboundBoxAddDialog'
import { FfInboundSortingPanel } from './FfInboundSortingPanel'
import {
  effectiveActualQty,
  inboundStatusRu,
  isDoneStatus,
  isReceivingStatus,
  isSortingStatus,
  scanErrorMessageRu,
} from './inboundReceivingHelpers'
import { suggestNextLocationCode } from '../../utils/suggestNextLocationCode'
import { renderBarcodeDataUrl } from '../../utils/renderBarcodeDataUrl'
import { resolveProductIdByBarcode } from '../../utils/resolveProductByBarcode'

type LocationRow = { id: string; code: string; warehouse_id: string; barcode: string }
type WarehouseRow = { id: string; name: string; code: string }

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

type InboundLine = {
  id: string
  product_id: string
  sku_code: string
  product_name: string
  expected_qty: number
  actual_qty: number | null
  posted_qty: number
  storage_location_id: string | null
  storage_location_code: string | null
}

type InboundDetail = {
  id: string
  document_number: string | null
  warehouse_id: string
  status: string
  planned_delivery_date: string | null
  planned_box_count: number | null
  actual_box_count: number | null
  boxes_discrepancy: boolean
  has_discrepancy: boolean
  seller_name?: string | null
  created_at?: string | null
  distribution_completed_at: string | null
  boxes: InboundBox[]
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

type Props = {
  token: string
  requestId: string
  isFulfillmentAdmin: boolean
  workspace?: InboundRequestWorkspace
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

  const [distOpen, setDistOpen] = useState(false)
  const [distBusy, setDistBusy] = useState(false)
  const [distError, setDistError] = useState<string | null>(null)
  const [distLines, setDistLines] = useState<DistributionLineDraft[]>([])
  const [cellHintsByProductId, setCellHintsByProductId] = useState<Record<string, CellLocationHint[]>>({})

  const [pickerOpen, setPickerOpen] = useState(false)

  const [plannedDateDraft, setPlannedDateDraft] = useState<string>('')
  const [lineBarcodeScan, setLineBarcodeScan] = useState('')
  const [receivingScan, setReceivingScan] = useState('')
  const [manualEditLineId, setManualEditLineId] = useState<string | null>(null)
  const [boxAddDialogBoxId, setBoxAddDialogBoxId] = useState<string | null>(null)
  const [finishConfirmOpen, setFinishConfirmOpen] = useState(false)
  const [scanToastError, setScanToastError] = useState<string | null>(null)
  const [newLocationCode, setNewLocationCode] = useState('')
  const [requestWarehouse, setRequestWarehouse] = useState<WarehouseRow | null>(null)

  const sortingView = workspace === 'sorting'
  const receptionClosed =
    detail != null && (isSortingStatus(detail.status) || isDoneStatus(detail.status))
  const receivingActive =
    detail != null &&
    (detail.status === 'submitted' || isReceivingStatus(detail.status))
  const showInboundLinesTable = !sortingView || receptionClosed
  const defaultPutawayBoxId = useMemo(() => {
    const closed = (detail?.boxes ?? []).filter((b) => b.intake_closed_at != null)
    if (closed.length === 1) {
      return closed[0]!.id
    }
    return ''
  }, [detail?.boxes])

  const sortingRemainingTotal = useMemo(() => {
    if (!detail) return 0
    const boxes = detail.boxes ?? []
    return detail.lines.reduce((sum, ln) => {
      const accepted = effectiveActualQty(ln, boxes)
      return sum + Math.max(0, accepted - ln.posted_qty)
    }, 0)
  }, [detail])

  const loadDetail = useCallback(async (): Promise<InboundDetail> => {
    const res = await fetch(apiUrl(`/operations/inbound-intake-requests/${requestId}`), {
      headers: authHeaders,
    })
    if (!res.ok) {
      throw new Error(await readApiErrorMessage(res))
    }
    const data = (await res.json()) as InboundDetail
    setDetail(data)
    return data
  }, [authHeaders, requestId])

  const fetchCatalogRows = useCallback(async (): Promise<WbCatalogRow[]> => {
    const res = await fetch(apiUrl('/products/linked-wb-catalog'), { headers: authHeaders })
    if (!res.ok) {
      throw new Error(await readApiErrorMessage(res))
    }
    return (await res.json()) as WbCatalogRow[]
  }, [authHeaders])

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
    setActualDraftByLineId((prev) => {
      const next: Record<string, string> = {}
      for (const ln of detail.lines) {
        const existing = prev[ln.id]
        if (existing !== undefined && manualEditLineId === ln.id) {
          next[ln.id] = existing
          continue
        }
        next[ln.id] = String(ln.actual_qty ?? 0)
      }
      return next
    })
  }, [detail, manualEditLineId])

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

  const draftLocked = detail != null && detail.status !== 'draft'

  const acceptedQtyByProductId = useMemo(() => {
    const m = new Map<string, number>()
    if (!detail) return m
    const boxes = detail.boxes ?? []
    for (const ln of detail.lines) {
      m.set(ln.product_id, effectiveActualQty(ln, boxes))
    }
    return m
  }, [detail])

  const hasLineDiscrepancy = useMemo(() => {
    if (!detail) return false
    const boxes = detail.boxes ?? []
    return detail.lines.some((ln) => effectiveActualQty(ln, boxes) !== ln.expected_qty)
  }, [detail])

  const distributableProducts = useMemo(() => {
    if (!detail) return []
    const boxes = detail.boxes ?? []
    const rows = detail.lines
      .map((ln) => ({
        product_id: ln.product_id,
        sku_code: ln.sku_code,
        product_name: ln.product_name,
        accepted_qty: effectiveActualQty(ln, boxes),
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

  const openPicker = async () => {
    setError(null)
    try {
      if (catalog == null) {
        await loadCatalog()
      }
      setPickerOpen(true)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Не удалось загрузить каталог.')
    }
  }

  const addLineByBarcode = async () => {
    if (!detail) return
    const code = lineBarcodeScan.trim()
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
        setError('Товар не найден по штрихкоду или артикулу.')
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
      setLineBarcodeScan('')
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
      for (const [productId, rawQty] of Object.entries(pickerQtyByProduct)) {
        const addQty = Number.isFinite(rawQty) ? Math.floor(rawQty) : 0
        if (addQty <= 0) continue
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

  const scanToReceiving = async () => {
    const code = receivingScan.trim()
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
        setScanToastError(scanErrorMessageRu(await readApiErrorMessage(res)))
        return
      }
      setReceivingScan('')
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
      return box.id
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Не удалось создать короб.')
      return null
    } finally {
      setBusy(false)
    }
  }

  const openBoxAddDialog = async () => {
    const openBox = detail?.boxes?.find((b) => b.is_open) ?? null
    if (openBox) {
      setBoxAddDialogBoxId(openBox.id)
      return
    }
    const boxId = await createInboundBox()
    if (boxId) {
      setBoxAddDialogBoxId(boxId)
    }
  }

  const completeReceiving = async () => {
    setBusy(true)
    setError(null)
    try {
      const res = await fetch(
        apiUrl(`/operations/inbound-intake-requests/${requestId}/complete-receiving`),
        { method: 'POST', headers: authHeaders },
      )
      if (!res.ok) {
        const msg = await readApiErrorMessage(res)
        setError(
          msg === 'open_box_exists'
            ? 'Сначала закройте открытый короб.'
            : scanErrorMessageRu(msg),
        )
        return
      }
      setFinishConfirmOpen(false)
      await loadDetail()
      setDistOpen(true)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Не удалось завершить приёмку.')
    } finally {
      setBusy(false)
    }
  }

  const requestCompleteReceiving = () => {
    if (hasLineDiscrepancy) {
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

  const saveManualLineActual = async (lineId: string) => {
    const raw = actualDraftByLineId[lineId]
    const v = Number(raw)
    if (!Number.isFinite(v) || v < 0) {
      setError('Укажите целое количество ≥ 0.')
      return
    }
    await setLineActual(lineId, Math.floor(v))
    setManualEditLineId(null)
  }

  const boxAddDialogBox = useMemo(
    () => detail?.boxes?.find((b) => b.id === boxAddDialogBoxId) ?? null,
    [boxAddDialogBoxId, detail?.boxes],
  )

  const closedBoxes = useMemo(
    () => (detail?.boxes ?? []).filter((b) => b.intake_closed_at != null),
    [detail?.boxes],
  )

  const openBoxes = useMemo(
    () => (detail?.boxes ?? []).filter((b) => b.is_open),
    [detail?.boxes],
  )

  const actualEditable =
    isFulfillmentAdmin &&
    receivingActive

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
    <Box data-testid="ff-inbound-doc-root">
      {error ? (
        <Alert severity="error" sx={{ mb: 2 }} data-testid="ff-inbound-doc-error">
          {error}
        </Alert>
      ) : null}

      {!detail ? (
        <Alert severity="warning">Заявка не найдена или недоступна.</Alert>
      ) : (
        <Paper variant="outlined" sx={{ p: 2, minHeight: '38vh' }}>
          <Stack spacing={2} sx={{ mb: 2 }}>
            <Stack
              direction="row"
              spacing={2}
              useFlexGap
              sx={{ alignItems: 'center', flexWrap: 'wrap' }}
            >
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
              <Chip
                label={inboundStatusRu(detail.status)}
                color={detail.status === 'draft' ? 'default' : 'primary'}
                data-testid="ff-inbound-status-chip"
              />
              {detail.document_number ? (
                <Typography
                  variant="subtitle2"
                  sx={{ fontWeight: 600 }}
                  data-testid="ff-inbound-document-number"
                >
                  {detail.document_number}
                </Typography>
              ) : null}
              {detail.planned_box_count != null ? (
                <Typography variant="body2" color="text.secondary" data-testid="ff-inbound-planned-boxes">
                  План коробов: <strong>{detail.planned_box_count}</strong>
                </Typography>
              ) : null}
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
                <Button
                  variant="contained"
                  disabled={busy || openBoxes.length > 0}
                  onClick={() => void requestCompleteReceiving()}
                  data-testid="ff-inbound-verify-complete"
                >
                  Завершить
                </Button>
              ) : null}

              {isFulfillmentAdmin &&
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
                  <Stack
                    direction={{ xs: 'column', sm: 'row' }}
                    spacing={1}
                    sx={{ width: { xs: '100%', sm: 'auto' }, flexBasis: { xs: '100%', sm: 'auto' } }}
                    data-testid="ff-inbound-line-barcode-row"
                  >
                    <TextField
                      size="small"
                      label="Штрихкод / артикул"
                      value={lineBarcodeScan}
                      disabled={draftLocked || busy}
                      onChange={(e) => setLineBarcodeScan(e.target.value)}
                      onKeyDown={(e) => {
                        if (e.key === 'Enter') {
                          e.preventDefault()
                          void addLineByBarcode()
                        }
                      }}
                      slotProps={{ htmlInput: { 'data-testid': 'ff-inbound-line-barcode-scan' } }}
                      sx={{ minWidth: 220, flexGrow: 1 }}
                    />
                    <Button
                      variant="outlined"
                      disabled={draftLocked || busy || !lineBarcodeScan.trim()}
                      onClick={() => void addLineByBarcode()}
                      data-testid="ff-inbound-line-barcode-add"
                    >
                      Добавить по ШК
                    </Button>
                  </Stack>
                  <Button
                    variant="outlined"
                    disabled={draftLocked || busy}
                    onClick={() => void openPicker()}
                    data-testid="ff-inbound-add-products"
                  >
                    Добавить товары
                  </Button>
                  <Button
                    variant="contained"
                    color="secondary"
                    disabled={busy || detail.lines.length === 0}
                    onClick={() => void submitToWarehouse()}
                    data-testid="ff-inbound-submit-warehouse"
                  >
                    Передать на склад
                  </Button>
                </>
              ) : null}

              {detail.lines.length > 0 ? (
                <Button
                  variant="outlined"
                  startIcon={<PrintOutlined />}
                  disabled={busy}
                  data-testid="ff-inbound-print-waybill"
                  onClick={() => {
                    const wh = requestWarehouse
                    printInboundSupplyWaybill({
                      documentId: detail.id,
                      statusLabel: inboundStatusRu(detail.status),
                      warehouseName: wh ? `${wh.name} (${wh.code})` : detail.warehouse_id,
                      sellerName: detail.seller_name ?? null,
                      plannedDate: detail.planned_delivery_date,
                      createdAt: detail.created_at ?? null,
                      plannedBoxCount: detail.planned_box_count,
                      actualBoxCount: detail.actual_box_count,
                      lines: detail.lines.map((ln) => ({
                        sku_code: ln.sku_code,
                        product_name: ln.product_name,
                        quantity: ln.expected_qty,
                        received_qty: ln.actual_qty,
                      })),
                    })
                  }}
                >
                  Печать накладной
                </Button>
              ) : null}

              <Button variant="outlined" disabled={busy} onClick={onClose} data-testid="ff-inbound-close">
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
          <TableContainer sx={{ width: '100%', overflowX: 'hidden' }}>
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
                '& th': { py: 1.25 },
                '& td': { py: 1.25 },
              }}
            >
              <TableHead>
                <TableRow>
                  <FfProductTableHeadCells />
                  <TableCell align="right" sx={{ width: 120 }}>
                    Заявлено
                  </TableCell>
                  <TableCell align="right" sx={{ width: 150 }}>
                    Принято
                  </TableCell>
                </TableRow>
              </TableHead>
              <TableBody>
                {detail.lines.map((ln) => {
                  const displayMeta = productDisplayMetaFromCatalog(ln.product_id, ln, catalogById)
                  const boxes = detail.boxes ?? []
                  const effective = effectiveActualQty(ln, boxes)
                  const hasDiscrepancy = effective !== ln.expected_qty
                  const matchesExpected = effective === ln.expected_qty && effective > 0
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
                      <FfProductLineCells
                        meta={displayMeta}
                        printTestId={`ff-inbound-line-print-${ln.id}`}
                      />
                      <TableCell align="right" sx={{ minWidth: 120 }}>
                        {ln.expected_qty}
                      </TableCell>
                      <TableCell align="right" sx={{ minWidth: 150 }}>
                        <Stack
                          direction="row"
                          spacing={0.5}
                          sx={{ justifyContent: 'flex-end', alignItems: 'center' }}
                        >
                          {manualOpen && actualEditable ? (
                            <TextField
                              type="number"
                              size="small"
                              value={actualDraftByLineId[ln.id] ?? String(ln.actual_qty ?? 0)}
                              disabled={busy}
                              onChange={(e) =>
                                setActualDraftByLineId((prev) => ({
                                  ...prev,
                                  [ln.id]: e.target.value,
                                }))
                              }
                              onKeyDown={(e) => {
                                if (e.key === 'Enter') {
                                  e.preventDefault()
                                  void saveManualLineActual(ln.id)
                                }
                              }}
                              slotProps={{
                                htmlInput: {
                                  min: 0,
                                  'data-testid': 'ff-inbound-line-actual',
                                },
                              }}
                              sx={{ width: 88 }}
                            />
                          ) : (
                            <Typography
                              variant="body2"
                              sx={{ fontWeight: 600, minWidth: 24, textAlign: 'right' }}
                              data-testid="ff-inbound-line-actual-display"
                            >
                              {effective}
                            </Typography>
                          )}
                          {actualEditable ? (
                            <IconButton
                              size="small"
                              aria-label="Править количество"
                              disabled={busy}
                              onClick={() => {
                                if (manualOpen) {
                                  void saveManualLineActual(ln.id)
                                  return
                                }
                                setManualEditLineId(ln.id)
                                setActualDraftByLineId((prev) => ({
                                  ...prev,
                                  [ln.id]: String(ln.actual_qty ?? 0),
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
                    <TableCell colSpan={9}>
                      <Typography variant="body2" color="text.secondary">
                        Пока нет строк. Добавьте товары.
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

          {isFulfillmentAdmin && !sortingView && receivingActive ? (
            <Paper variant="outlined" sx={{ p: 2, mt: 2 }} data-testid="ff-inbound-receiving-scan-panel">
              <Typography variant="subtitle2" sx={{ fontWeight: 800, mb: 1 }}>
                Скан приёмки
              </Typography>
              <Typography variant="body2" color="text.secondary" sx={{ mb: 1.5 }}>
                Скан штрихкода товара добавляет +1 к принятому количеству. Скан в короб — только в
                модалке «Добавить в короб».
              </Typography>
              <Stack direction={{ xs: 'column', sm: 'row' }} spacing={1}>
                <TextField
                  size="small"
                  label="Штрихкод товара"
                  value={receivingScan}
                  disabled={busy || boxAddDialogBoxId != null}
                  onChange={(e) => setReceivingScan(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter') {
                      e.preventDefault()
                      void scanToReceiving()
                    }
                  }}
                  slotProps={{ htmlInput: { 'data-testid': 'ff-inbound-receiving-scan-input' } }}
                  sx={{ minWidth: 220, flexGrow: 1 }}
                />
                <Button
                  variant="contained"
                  disabled={busy || !receivingScan.trim() || boxAddDialogBoxId != null}
                  onClick={() => void scanToReceiving()}
                  data-testid="ff-inbound-receiving-scan-submit"
                >
                  Скан
                </Button>
                <Button
                  variant="outlined"
                  disabled={busy || openBoxes.length > 0}
                  onClick={() => void openBoxAddDialog()}
                  data-testid="ff-inbound-add-to-box"
                >
                  Добавить в короб
                </Button>
              </Stack>
              {hasLineDiscrepancy ? (
                <Alert severity="warning" sx={{ mt: 1.5 }} data-testid="ff-inbound-discrepancy-hint">
                  Есть расхождения с планом — при завершении потребуется подтверждение.
                </Alert>
              ) : null}
            </Paper>
          ) : null}

          {isFulfillmentAdmin && !sortingView && (detail.boxes?.length ?? 0) > 0 ? (
            <Paper variant="outlined" sx={{ p: 2, mt: 2 }} data-testid="ff-inbound-boxes-panel">
              <Stack
                direction={{ xs: 'column', sm: 'row' }}
                spacing={1}
                sx={{ alignItems: { sm: 'center' }, mb: 1.5 }}
              >
                <Box sx={{ flexGrow: 1 }}>
                  <Typography variant="subtitle2" sx={{ fontWeight: 800 }}>
                    Короба приёмки
                  </Typography>
                  <Typography variant="body2" color="text.secondary">
                    Закрытые короба с составом. Этикетки 58×40 (CODE128).
                  </Typography>
                </Box>
                <Button
                  variant="outlined"
                  disabled={busy}
                  onClick={() => void printAllInboundBoxLabels()}
                  data-testid="ff-inbound-boxes-print-all"
                >
                  Печать всех
                </Button>
              </Stack>
              {closedBoxes.length > 0 ? (
                <Stack spacing={1.5} sx={{ mb: 1.5 }}>
                  {closedBoxes.map((box) => (
                    <Paper key={box.id} variant="outlined" sx={{ p: 1.5 }} data-testid="ff-inbound-box-closed">
                      <Stack
                        direction={{ xs: 'column', sm: 'row' }}
                        spacing={1}
                        sx={{ alignItems: { sm: 'center' }, mb: 1 }}
                      >
                        <Typography variant="body2" sx={{ fontWeight: 700 }}>
                          Короб № {box.box_number}{' '}
                          <Typography component="code" variant="body2">
                            {box.internal_barcode}
                          </Typography>
                        </Typography>
                        <Box sx={{ flexGrow: 1 }} />
                        <Button
                          size="small"
                          variant="outlined"
                          disabled={busy}
                          onClick={() => void printInboundBoxLabel(box)}
                          data-testid="ff-inbound-box-print"
                        >
                          Печать
                        </Button>
                      </Stack>
                      {box.lines.length > 0 ? (
                        <Stack spacing={0.25}>
                          {box.lines.map((ln) => (
                            <Typography key={ln.id} variant="body2" color="text.secondary">
                              {ln.sku_code} · {ln.product_name}: {ln.quantity}
                            </Typography>
                          ))}
                        </Stack>
                      ) : (
                        <Typography variant="body2" color="text.secondary">
                          Пустой короб
                        </Typography>
                      )}
                    </Paper>
                  ))}
                </Stack>
              ) : (
                <Typography variant="body2" color="text.secondary" sx={{ mb: 1.5 }}>
                  Закрытых коробов пока нет.
                </Typography>
              )}
              {openBoxes.length > 0 ? (
                <Alert severity="info" data-testid="ff-inbound-open-box-hint">
                  Открыт короб № {openBoxes[0]!.box_number}. Закройте его в модалке «Добавить в
                  короб» перед завершением приёмки.
                </Alert>
              ) : null}
            </Paper>
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

              {addressStorageEnabled && isSortingStatus(detail.status) && workspace === 'full' ? (
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
                              {hasNoCellPending ? 'Применить разкладку' : 'Завершить распределение'}
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
        disabledProductIds={lineProductIds}
        testIdPrefix="ff-inbound-picker"
        variant="ff"
        qtyColumnLabel="Кол-во в заявку"
        onClose={() => setPickerOpen(false)}
        onApply={applyPicker}
      />

      {boxAddDialogBox && boxAddDialogBoxId ? (
        <FfInboundBoxAddDialog
          open
          onClose={() => setBoxAddDialogBoxId(null)}
          requestId={requestId}
          boxId={boxAddDialogBoxId}
          boxLabel={`Короб № ${boxAddDialogBox.box_number} · ${boxAddDialogBox.internal_barcode}`}
          boxClosed={boxAddDialogBox.intake_closed_at != null}
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
        open={scanToastError !== null}
        autoHideDuration={3500}
        onClose={() => setScanToastError(null)}
        anchorOrigin={{ vertical: 'bottom', horizontal: 'center' }}
      >
        <Alert
          severity="error"
          variant="filled"
          onClose={() => setScanToastError(null)}
          data-testid="ff-inbound-scan-error-snackbar"
          sx={{ width: '100%' }}
        >
          {scanToastError}
        </Alert>
      </Snackbar>

      <Dialog
        open={finishConfirmOpen}
        onClose={() => setFinishConfirmOpen(false)}
        data-testid="ff-inbound-discrepancy-dialog"
      >
        <DialogTitle>Есть расхождения, точно провести?</DialogTitle>
        <DialogContent>
          <Typography variant="body2">
            Факт по одной или нескольким позициям не совпадает с планом. Приёмка будет проведена с
            расхождением.
          </Typography>
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
            Завершить
          </Button>
        </DialogActions>
      </Dialog>
    </Box>
  )
}

