import { useCallback, useEffect, useMemo, useState } from 'react'
import PrintOutlined from '@mui/icons-material/PrintOutlined'
import {
  Alert,
  Avatar,
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
import { printBarcodeLabel } from '../../utils/printBarcodeLabel'
import { printInboundSupplyWaybill } from '../../utils/printShipmentWaybill'
import { readApiErrorMessage } from '../../utils/readApiErrorMessage'
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
}

type InboundBox = {
  id: string
  box_number: number
  internal_barcode: string
  label_printed_at: string | null
  intake_opened_at: string | null
  intake_closed_at: string | null
  is_open: boolean
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

export type WbCatalogRow = {
  id: string
  name: string
  sku_code: string
  wb_nm_id: number | null
  wb_vendor_code: string | null
  wb_subject_name: string | null
  wb_primary_image_url: string | null
  wb_barcodes: string[]
  wb_primary_barcode: string | null
}

type Props = {
  token: string
  requestId: string
  isFulfillmentAdmin: boolean
  onClose: () => void
}

function statusRu(status: string): string {
  if (status === 'draft') return 'Черновик'
  if (status === 'submitted') return 'Передано на склад'
  if (status === 'primary_accepted') return 'Принято на складе'
  if (status === 'verifying') return 'Проверка на складе'
  if (status === 'verified') return 'Проверено на складе'
  if (status === 'posted') return 'Оприходовано'
  return status
}

export function FfInboundRequestView({ token, requestId, isFulfillmentAdmin, onClose }: Props) {
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
  const [pickerSearch, setPickerSearch] = useState('')
  const [pickerCategory, setPickerCategory] = useState<string>('__all__')
  const [pickerQtyByProduct, setPickerQtyByProduct] = useState<Record<string, number>>({})

  const [plannedDateDraft, setPlannedDateDraft] = useState<string>('')
  const [actualBoxCountDraft, setActualBoxCountDraft] = useState<string>('')
  const [boxOpenScan, setBoxOpenScan] = useState('')
  const [boxQtyDraftByProductId, setBoxQtyDraftByProductId] = useState<Record<string, string>>({})
  const [lineBarcodeScan, setLineBarcodeScan] = useState('')
  const [newLocationCode, setNewLocationCode] = useState('')
  const [requestWarehouse, setRequestWarehouse] = useState<WarehouseRow | null>(null)

  const boxIntakeMode = (detail?.boxes?.length ?? 0) > 0
  const verifyingWithBoxes =
    boxIntakeMode &&
    (detail?.status === 'primary_accepted' || detail?.status === 'verifying')

  const loadDetail = useCallback(async () => {
    const res = await fetch(apiUrl(`/operations/inbound-intake-requests/${requestId}`), {
      headers: authHeaders,
    })
    if (!res.ok) {
      throw new Error(await readApiErrorMessage(res))
    }
    setDetail((await res.json()) as InboundDetail)
  }, [authHeaders, requestId])

  const fetchCatalogRows = useCallback(async (): Promise<WbCatalogRow[]> => {
    const [productsRes, ffRes] = await Promise.all([
      fetch(apiUrl('/products'), { headers: authHeaders }),
      fetch(apiUrl('/products/ff-catalog'), { headers: authHeaders }),
    ])
    if (!productsRes.ok) {
      throw new Error(await readApiErrorMessage(productsRes))
    }
    const products = (await productsRes.json()) as {
      id: string
      name: string
      sku_code: string
      wb_nm_id?: number | null
      wb_vendor_code?: string | null
    }[]
    const ffRows = ffRes.ok ? ((await ffRes.json()) as WbCatalogRow[]) : []
    const ffById = new Map(ffRows.map((r) => [r.id, r]))
    return products.map((p) => {
      const ff = ffById.get(p.id)
      if (ff) {
        return ff
      }
      return {
        id: p.id,
        name: p.name,
        sku_code: p.sku_code,
        wb_nm_id: p.wb_nm_id ?? null,
        wb_vendor_code: p.wb_vendor_code ?? null,
        wb_subject_name: null,
        wb_primary_image_url: null,
        wb_barcodes: [],
        wb_primary_barcode: null,
      }
    })
  }, [authHeaders])

  const loadCatalog = useCallback(async () => {
    setCatalog(await fetchCatalogRows())
  }, [fetchCatalogRows])

  const loadLocations = useCallback(
    async (warehouseId: string) => {
      const res = await fetch(apiUrl(`/warehouses/${warehouseId}/locations`), {
        headers: authHeaders,
      })
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
          product_id: r.product_id,
          storage_location_id: r.storage_location_id,
          quantity: String(r.quantity),
        })),
      )
    } catch (e) {
      setDistLines([])
      setDistError(e instanceof Error ? e.message : 'Не удалось загрузить распределение.')
    }
  }, [authHeaders, detail, requestId])

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
    setPlannedDateDraft(detail?.planned_delivery_date ?? '')
  }, [detail?.planned_delivery_date])

  useEffect(() => {
    if (detail?.actual_box_count != null) {
      setActualBoxCountDraft(String(detail.actual_box_count))
    } else if (detail?.planned_box_count != null) {
      setActualBoxCountDraft(String(detail.planned_box_count))
    } else {
      setActualBoxCountDraft('1')
    }
  }, [detail?.planned_box_count, detail?.actual_box_count, detail?.status])

  useEffect(() => {
    if (!detail) {
      setActualDraftByLineId({})
      return
    }
    // Manual verify: default draft to expected only when not using box intake.
    // Box intake: «Принято» comes from короба — do not pretend undeclared lines are accepted.
    setActualDraftByLineId((prev) => {
      const viaBoxes = (detail.boxes?.length ?? 0) > 0
      const next: Record<string, string> = {}
      for (const ln of detail.lines) {
        const existing = prev[ln.id]
        if (existing !== undefined && !viaBoxes) {
          next[ln.id] = existing
          continue
        }
        if (viaBoxes) {
          next[ln.id] = ln.actual_qty != null ? String(ln.actual_qty) : ''
        } else {
          next[ln.id] = String(ln.actual_qty ?? ln.expected_qty)
        }
      }
      return next
    })
  }, [detail])

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
    if (!['verified'].includes(detail.status)) {
      setDistOpen(false)
      setDistLines([])
      return
    }
    void loadDistribution()
  }, [detail, isFulfillmentAdmin, loadDistribution])

  useEffect(() => {
    if (!distOpen || detail?.status !== 'verified') return
    for (const row of distLines) {
      if (row.product_id) void loadCellHints(row.product_id)
    }
  }, [distOpen, detail?.status, distLines, loadCellHints])

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

  const categories = useMemo(() => {
    if (!catalog) return []
    const s = new Set<string>()
    for (const r of catalog) {
      const c = r.wb_subject_name?.trim()
      if (c) s.add(c)
    }
    return Array.from(s).sort((a, b) => a.localeCompare(b))
  }, [catalog])

  const filteredPickerRows = useMemo(() => {
    if (!catalog) return []
    const q = pickerSearch.trim().toLowerCase()
    return catalog.filter((r) => {
      if (pickerCategory !== '__all__') {
        const sub = (r.wb_subject_name ?? '').trim()
        if (sub !== pickerCategory) return false
      }
      if (!q) return true
      const nm = r.wb_nm_id != null ? String(r.wb_nm_id) : ''
      const barcodes = r.wb_barcodes.join(' ').toLowerCase()
      const hay = `${r.sku_code} ${r.wb_vendor_code ?? ''} ${r.name} ${nm} ${barcodes}`.toLowerCase()
      return hay.includes(q)
    })
  }, [catalog, pickerCategory, pickerSearch])

  const draftLocked = detail != null && detail.status !== 'draft'

  const acceptedQtyByProductId = useMemo(() => {
    const m = new Map<string, number>()
    if (!detail) return m
    const viaBoxes = (detail.boxes?.length ?? 0) > 0
    for (const ln of detail.lines) {
      const accepted = viaBoxes ? (ln.actual_qty ?? 0) : (ln.actual_qty ?? ln.expected_qty)
      m.set(ln.product_id, accepted)
    }
    return m
  }, [detail])

  const distributableProducts = useMemo(() => {
    if (!detail) return []
    const rows = detail.lines
      .map((ln) => ({
        product_id: ln.product_id,
        sku_code: ln.sku_code,
        product_name: ln.product_name,
        accepted_qty:
          (detail.boxes?.length ?? 0) > 0
            ? (ln.actual_qty ?? 0)
            : (ln.actual_qty ?? ln.expected_qty),
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

  const validateDistributionDraft = (): string | null => {
    if (!detail) return 'Заявка не загружена.'
    // allow empty draft: everything goes to "Без ячейки"
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
        .map((r) => ({
          product_id: r.product_id,
          storage_location_id: r.storage_location_id,
          quantity: Math.floor(Number(r.quantity)),
        }))
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

  const completeDistribution = async () => {
    if (!detail) return
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
        .map((r) => ({
          product_id: r.product_id,
          storage_location_id: r.storage_location_id,
          quantity: Math.floor(Number(r.quantity)),
        }))
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

  const applyPicker = async () => {
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
      setPickerQtyByProduct({})
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

  const primaryAccept = async () => {
    const actualBoxes = Math.floor(Number(actualBoxCountDraft))
    if (!Number.isFinite(actualBoxes) || actualBoxes < 0) {
      setError('Укажите фактическое количество коробов (целое число ≥ 0).')
      return
    }
    setBusy(true)
    setError(null)
    try {
      const res = await fetch(
        apiUrl(`/operations/inbound-intake-requests/${requestId}/primary-accept`),
        {
          method: 'POST',
          headers: { ...authHeaders, 'Content-Type': 'application/json' },
          body: JSON.stringify({ actual_box_count: actualBoxes }),
        },
      )
      if (!res.ok) {
        setError(await readApiErrorMessage(res))
        return
      }
      await loadDetail()
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Не удалось выполнить первичную приёмку.')
    } finally {
      setBusy(false)
    }
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
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Не удалось сохранить факт.')
    } finally {
      setBusy(false)
    }
  }

  const ensureActualsSaved = async () => {
    if (!detail) {
      return
    }
    if ((detail.boxes?.length ?? 0) > 0) {
      // Факт по строкам уже синхронизируется из поштучной приёмки по коробам.
      return
    }
    // Save actuals for all lines (required by backend before verify).
    // Important: do not rely on onBlur — user can click "Завершить" while focus is in the field.
    for (const ln of detail.lines) {
      const raw = actualDraftByLineId[ln.id]
      const v = Number(raw)
      if (!Number.isFinite(v) || v < 0) {
        throw new Error('Укажите факт по всем строкам (целое число ≥ 0).')
      }
      // Avoid redundant patches when already saved and unchanged.
      if (ln.actual_qty != null && v === ln.actual_qty) {
        continue
      }
      // Backend accepts patch only for verifying stage; still, patching here matches the UX intent.
      await setLineActual(ln.id, Math.floor(v))
    }
    await loadDetail()
  }

  const completeVerify = async () => {
    setBusy(true)
    setError(null)
    try {
      if (boxIntakeMode && activeIntakeBox) {
        setError(
          `Закройте короб № ${activeIntakeBox.box_number} (${activeIntakeBox.internal_barcode}) перед завершением пересчёта.`,
        )
        return
      }
      if (boxIntakeMode && detail) {
        const missing = detail.lines.filter((ln) => ln.actual_qty == null)
        if (missing.length > 0) {
          const names = missing
            .slice(0, 4)
            .map((ln) => ln.sku_code)
            .join(', ')
          const more = missing.length > 4 ? ` и ещё ${missing.length - 4}` : ''
          setError(
            `Укажите количество в поштучной приёмке по коробам для всех позиций (в коробе можно поставить 0). Не заполнено: ${names}${more}.`,
          )
          return
        }
      }
      await ensureActualsSaved()
      const res = await fetch(
        apiUrl(`/operations/inbound-intake-requests/${requestId}/verify`),
        { method: 'POST', headers: authHeaders },
      )
      if (!res.ok) {
        const msg = await readApiErrorMessage(res)
        setError(
          msg === 'actual_missing'
            ? boxIntakeMode
              ? 'Укажите количество по каждой позиции в поштучной приёмке по коробам (0 — если товар не принимали).'
              : 'Укажите факт по всем строкам.'
            : msg === 'open_box_exists'
              ? 'Сначала закройте открытый короб в блоке поштучной приёмки.'
              : msg,
        )
        return
      }
      await loadDetail()
      setDistOpen(true)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Не удалось завершить пересчёт.')
    } finally {
      setBusy(false)
    }
  }

  const activeIntakeBox = detail?.boxes?.find((b) => b.is_open) ?? null

  const qtyInOtherBoxesByProductId = useMemo(() => {
    const m = new Map<string, number>()
    if (!detail?.boxes || !activeIntakeBox) {
      return m
    }
    for (const box of detail.boxes) {
      if (box.id === activeIntakeBox.id) {
        continue
      }
      for (const ln of box.lines) {
        m.set(ln.product_id, (m.get(ln.product_id) ?? 0) + ln.quantity)
      }
    }
    return m
  }, [activeIntakeBox, detail?.boxes])

  useEffect(() => {
    if (!activeIntakeBox || !detail) {
      setBoxQtyDraftByProductId({})
      return
    }
    const draft: Record<string, string> = {}
    for (const ln of detail.lines) {
      const inBox = activeIntakeBox.lines.find((bl) => bl.product_id === ln.product_id)
      draft[ln.product_id] = String(inBox?.quantity ?? 0)
    }
    setBoxQtyDraftByProductId(draft)
  }, [activeIntakeBox, detail])

  const actualEditable =
    isFulfillmentAdmin &&
    (detail?.status === 'primary_accepted' || detail?.status === 'verifying') &&
    !boxIntakeMode

  const openInboundBox = async (barcode: string) => {
    const code = barcode.trim()
    if (!code) return
    setBusy(true)
    setError(null)
    try {
      const res = await fetch(
        apiUrl(`/operations/inbound-intake-requests/${requestId}/boxes/open`),
        {
          method: 'POST',
          headers: { ...authHeaders, 'Content-Type': 'application/json' },
          body: JSON.stringify({ barcode: code }),
        },
      )
      if (!res.ok) {
        setError(await readApiErrorMessage(res))
        return
      }
      setBoxOpenScan('')
      await loadDetail()
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Не удалось открыть короб.')
    } finally {
      setBusy(false)
    }
  }

  const openInboundBoxByScan = async () => {
    await openInboundBox(boxOpenScan)
  }

  const saveBoxLineQty = async (productId: string) => {
    if (!activeIntakeBox) return
    const raw = boxQtyDraftByProductId[productId] ?? '0'
    const qty = Math.floor(Number(raw))
    if (!Number.isFinite(qty) || qty < 0) {
      setError('Укажите целое количество ≥ 0.')
      return
    }
    const inBox = activeIntakeBox.lines.find((ln) => ln.product_id === productId)
    if (inBox && inBox.quantity === qty) {
      return
    }
    setBusy(true)
    setError(null)
    try {
      const res = await fetch(
        apiUrl(
          `/operations/inbound-intake-requests/${requestId}/boxes/${activeIntakeBox.id}/lines/${productId}`,
        ),
        {
          method: 'PUT',
          headers: { ...authHeaders, 'Content-Type': 'application/json' },
          body: JSON.stringify({ quantity: qty }),
        },
      )
      if (!res.ok) {
        const msg = await readApiErrorMessage(res)
        setError(msg)
        return
      }
      await loadDetail()
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Не удалось сохранить количество.')
    } finally {
      setBusy(false)
    }
  }

  const closeActiveInboundBox = async () => {
    if (!activeIntakeBox) return
    setBusy(true)
    setError(null)
    try {
      const res = await fetch(
        apiUrl(
          `/operations/inbound-intake-requests/${requestId}/boxes/${activeIntakeBox.id}/close`,
        ),
        { method: 'POST', headers: authHeaders },
      )
      if (!res.ok) {
        setError(await readApiErrorMessage(res))
        return
      }
      await loadDetail()
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Не удалось закрыть короб.')
    } finally {
      setBusy(false)
    }
  }

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
          <Stack
            direction={{ xs: 'column', md: 'row' }}
            spacing={2}
            sx={{ mb: 2, alignItems: { md: 'center' } }}
          >
            <TextField
              label="Дата поставки (план)"
              type="date"
              size="small"
              disabled={draftLocked || busy}
              value={plannedDateDraft}
              onChange={(e) => setPlannedDateDraft(e.target.value)}
              onBlur={() => {
                if ((plannedDateDraft || '') !== (detail.planned_delivery_date ?? '')) {
                  void patchPlannedDate(plannedDateDraft)
                }
              }}
              slotProps={{
                inputLabel: { shrink: true },
                htmlInput: { 'data-testid': 'ff-inbound-planned-date' },
              }}
            />
            <Chip
              label={statusRu(detail.status)}
              color={detail.status === 'draft' ? 'default' : 'primary'}
              data-testid="ff-inbound-status-chip"
            />
            {detail.planned_box_count != null ? (
              <Typography variant="body2" color="text.secondary" data-testid="ff-inbound-planned-boxes">
                План коробов: <strong>{detail.planned_box_count}</strong>
                {detail.actual_box_count != null ? (
                  <>
                    {' '}
                    · факт: <strong>{detail.actual_box_count}</strong>
                  </>
                ) : null}
              </Typography>
            ) : null}
            <Box sx={{ flexGrow: 1 }} />

            {isFulfillmentAdmin && (detail.status === 'primary_accepted' || detail.status === 'verifying') ? (
              <Button
                variant="contained"
                disabled={busy}
                onClick={() => void completeVerify()}
                data-testid="ff-inbound-verify-complete"
              >
                Завершить пересчёт
              </Button>
            ) : null}

            {isFulfillmentAdmin && detail.status === 'verified' ? (
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
                  sx={{ width: '100%', flexBasis: '100%' }}
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
                    statusLabel: statusRu(detail.status),
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

          <TableContainer sx={{ width: '100%', overflowX: 'hidden' }}>
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
                  <TableCell sx={{ width: 56 }}>Фото</TableCell>
                  <TableCell sx={{ width: 190, pl: 2 }}>Артикул</TableCell>
                  <TableCell sx={{ width: 220 }}>ШК</TableCell>
                  <TableCell sx={{ width: 140 }}>Артикул продавца</TableCell>
                  <TableCell sx={{ width: 120, pr: 2 }}>Артикул WB</TableCell>
                  <TableCell sx={{ pl: 2 }}>Наименование</TableCell>
                  <TableCell align="right" sx={{ width: 120 }}>
                    Заявлено
                  </TableCell>
                  <TableCell align="right" sx={{ width: 150 }}>
                    {verifyingWithBoxes ? 'Принято (из коробов)' : 'Принято'}
                  </TableCell>
                </TableRow>
              </TableHead>
              <TableBody>
                {detail.lines.map((ln) => {
                  const cat = catalogById.get(ln.product_id)
                  const img = cat?.wb_primary_image_url ?? undefined
                  const barcode =
                    cat?.wb_primary_barcode ??
                    (cat?.wb_barcodes.length ? cat.wb_barcodes.join(', ') : '—')
                  const actualIsSet = ln.actual_qty != null
                  const pendingBoxAcceptance = verifyingWithBoxes && !actualIsSet
                  const hasDiscrepancy = actualIsSet && ln.actual_qty !== ln.expected_qty
                  const matchesExpected = actualIsSet && ln.actual_qty === ln.expected_qty
                  const rowTestId = matchesExpected
                    ? 'ff-inbound-line-row-match'
                    : hasDiscrepancy
                      ? 'ff-inbound-line-row-discrepancy'
                      : pendingBoxAcceptance
                        ? 'ff-inbound-line-row-pending'
                        : 'ff-inbound-line-row'
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
                        ...(pendingBoxAcceptance
                          ? {
                              backgroundColor: (theme) =>
                                alpha(theme.palette.action.hover, 0.04),
                            }
                          : null),
                      }}
                    >
                      <TableCell>
                        <Avatar
                          variant="rounded"
                          src={img}
                          alt=""
                          sx={{ width: 44, height: 44 }}
                          slotProps={{ img: { loading: 'lazy' } }}
                        />
                      </TableCell>
                      <TableCell sx={{ whiteSpace: 'nowrap', pl: 2 }} title={ln.sku_code}>
                        {ln.sku_code}
                      </TableCell>
                      <TableCell sx={{ whiteSpace: 'nowrap' }} title={barcode}>
                        {barcode}
                      </TableCell>
                      <TableCell
                        sx={{ whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}
                        title={cat?.wb_vendor_code ?? '—'}
                      >
                        {cat?.wb_vendor_code ?? '—'}
                      </TableCell>
                      <TableCell sx={{ pr: 2 }}>{cat?.wb_nm_id ?? '—'}</TableCell>
                      <TableCell sx={{ pl: 2, whiteSpace: 'normal', wordBreak: 'break-word' }}>
                        <Typography variant="body2" sx={{ lineHeight: 1.25 }}>
                          {ln.product_name}
                        </Typography>
                      </TableCell>
                      <TableCell align="right" sx={{ minWidth: 120 }}>
                        {ln.expected_qty}
                      </TableCell>
                      <TableCell align="right" sx={{ minWidth: 150 }}>
                        <TextField
                          type="number"
                          size="small"
                          placeholder={verifyingWithBoxes ? '—' : undefined}
                          value={
                            verifyingWithBoxes
                              ? ln.actual_qty != null
                                ? String(ln.actual_qty)
                                : ''
                              : (actualDraftByLineId[ln.id] ??
                                (ln.actual_qty != null ? String(ln.actual_qty) : ''))
                          }
                          disabled={busy || !actualEditable}
                          onChange={(e) =>
                            setActualDraftByLineId((prev) => ({
                              ...prev,
                              [ln.id]: e.target.value,
                            }))
                          }
                          onBlur={() => {
                            if (verifyingWithBoxes) return
                            const raw = actualDraftByLineId[ln.id]
                            const v = Number(raw)
                            if (!Number.isFinite(v) || v < 0) return
                            if (ln.actual_qty != null && v === ln.actual_qty) return
                            void setLineActual(ln.id, Math.floor(v))
                          }}
                          slotProps={{
                            htmlInput: {
                              min: 0,
                              'data-testid': 'ff-inbound-line-actual',
                            },
                          }}
                        />
                      </TableCell>
                    </TableRow>
                  )
                })}
                {detail.lines.length === 0 ? (
                  <TableRow>
                    <TableCell colSpan={8}>
                      <Typography variant="body2" color="text.secondary">
                        Пока нет строк. Добавьте товары.
                      </Typography>
                    </TableCell>
                  </TableRow>
                ) : null}
              </TableBody>
            </Table>
          </TableContainer>

          {isFulfillmentAdmin ? (
            <Box sx={{ mt: 2 }}>
              {detail.status === 'submitted' ? (
                <Paper variant="outlined" sx={{ p: 2 }} data-testid="ff-inbound-admin-submitted">
                  <Typography variant="subtitle2" sx={{ fontWeight: 800, mb: 1 }}>
                    Приёмка по коробам
                  </Typography>
                  <Typography variant="body2" color="text.secondary" sx={{ mb: 1.5 }}>
                    Сверьте количество коробов с планом селлера. Поштучный пересчёт — на следующем
                    этапе.
                  </Typography>
                  {detail.planned_box_count != null ? (
                    <Typography variant="body2" sx={{ mb: 1 }}>
                      План селлера: <strong>{detail.planned_box_count}</strong> кор.
                    </Typography>
                  ) : null}
                  <Stack direction={{ xs: 'column', sm: 'row' }} spacing={1.5} sx={{ mb: 1.5 }}>
                    <TextField
                      label="Факт коробов"
                      type="number"
                      size="small"
                      value={actualBoxCountDraft}
                      onChange={(e) => setActualBoxCountDraft(e.target.value)}
                      slotProps={{
                        htmlInput: {
                          min: 0,
                          'data-testid': 'ff-inbound-actual-box-count',
                        },
                      }}
                    />
                  </Stack>
                  {detail.planned_box_count != null &&
                  Number(actualBoxCountDraft) !== detail.planned_box_count ? (
                    <Alert severity="warning" sx={{ mb: 1.5 }} data-testid="ff-inbound-boxes-discrepancy">
                      Расхождение по коробам: план {detail.planned_box_count}, факт{' '}
                      {actualBoxCountDraft || '—'}.
                    </Alert>
                  ) : null}
                  <Button
                    variant="contained"
                    disabled={busy}
                    onClick={() => void primaryAccept()}
                    data-testid="ff-inbound-primary-accept"
                  >
                    Принято по коробам
                  </Button>
                </Paper>
              ) : null}
              {detail.boxes_discrepancy && detail.status !== 'submitted' ? (
                <Alert severity="warning" sx={{ mt: 2 }} data-testid="ff-inbound-boxes-discrepancy-badge">
                  Зафиксировано расхождение по коробам (план {detail.planned_box_count ?? '—'} ≠ факт{' '}
                  {detail.actual_box_count ?? '—'}).
                </Alert>
              ) : null}

              {(detail.boxes?.length ?? 0) > 0 ? (
                <Paper variant="outlined" sx={{ p: 2, mt: 2 }} data-testid="ff-inbound-boxes-panel">
                  <Stack
                    direction={{ xs: 'column', sm: 'row' }}
                    spacing={1}
                    sx={{ alignItems: { sm: 'center' }, mb: 1.5 }}
                  >
                    <Box sx={{ flexGrow: 1 }}>
                      <Typography variant="subtitle2" sx={{ fontWeight: 800 }}>
                        Короба и внутренние ШК
                      </Typography>
                      <Typography variant="body2" color="text.secondary">
                        После приёмки по коробам — печать этикеток 58×40 (CODE128) для поштучной приёмки.
                      </Typography>
                    </Box>
                    {isFulfillmentAdmin ? (
                      <Button
                        variant="outlined"
                        disabled={busy}
                        onClick={() => void printAllInboundBoxLabels()}
                        data-testid="ff-inbound-boxes-print-all"
                      >
                        Печать всех
                      </Button>
                    ) : null}
                  </Stack>
                  <TableContainer component={Paper} variant="outlined">
                    <Table size="small" data-testid="ff-inbound-boxes-table">
                      <TableHead>
                        <TableRow>
                          <TableCell sx={{ width: 80 }}>№</TableCell>
                          <TableCell>Штрихкод</TableCell>
                          <TableCell sx={{ width: 140 }}>Этикетка</TableCell>
                          {isFulfillmentAdmin ? <TableCell sx={{ width: 120 }} /> : null}
                        </TableRow>
                      </TableHead>
                      <TableBody>
                        {(detail.boxes ?? []).map((box) => (
                          <TableRow key={box.id} data-testid="ff-inbound-box-row">
                            <TableCell>{box.box_number}</TableCell>
                            <TableCell>
                              <Typography
                                variant="body2"
                                component="code"
                                data-testid="ff-inbound-box-barcode"
                              >
                                {box.internal_barcode}
                              </Typography>
                            </TableCell>
                            <TableCell>
                              {box.label_printed_at ? (
                                <Chip size="small" label="Напечатано" color="success" variant="outlined" />
                              ) : (
                                <Chip size="small" label="Не печатали" variant="outlined" />
                              )}
                            </TableCell>
                            {isFulfillmentAdmin ? (
                              <TableCell>
                                <Stack direction="row" spacing={0.5}>
                                  {!box.is_open && box.intake_closed_at == null ? (
                                    <Button
                                      size="small"
                                      variant="contained"
                                      disabled={busy || activeIntakeBox != null}
                                      onClick={() => void openInboundBox(box.internal_barcode)}
                                      data-testid="ff-inbound-box-open-btn"
                                    >
                                      Открыть
                                    </Button>
                                  ) : null}
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
                              </TableCell>
                            ) : null}
                          </TableRow>
                        ))}
                      </TableBody>
                    </Table>
                  </TableContainer>
                </Paper>
              ) : null}

              {boxIntakeMode &&
              isFulfillmentAdmin &&
              (detail.status === 'primary_accepted' || detail.status === 'verifying') ? (
                <Paper
                  variant="outlined"
                  sx={{ p: 2, mt: 2 }}
                  data-testid="ff-inbound-box-intake-panel"
                >
                  <Typography variant="subtitle2" sx={{ fontWeight: 800, mb: 1 }}>
                    Поштучная приёмка по коробу
                  </Typography>
                  <Typography variant="body2" color="text.secondary" sx={{ mb: 1.5 }}>
                    Откройте короб (скан INB-… или кнопка в таблице коробов), вручную укажите
                    количество по каждой позиции в этом коробе и закройте короб. Можно указать
                    больше, чем в заявке — расхождение зафиксируется при пересчёте. Сканирование
                    штрихкодов товара не требуется.
                  </Typography>
                  {!activeIntakeBox ? (
                    <Stack direction={{ xs: 'column', sm: 'row' }} spacing={1} sx={{ mb: 1.5 }}>
                      <TextField
                        size="small"
                        label="ШК короба (INB)"
                        value={boxOpenScan}
                        onChange={(e) => setBoxOpenScan(e.target.value)}
                        disabled={busy}
                        fullWidth
                        onKeyDown={(e) => {
                          if (e.key === 'Enter') void openInboundBoxByScan()
                        }}
                        slotProps={{
                          htmlInput: { 'data-testid': 'ff-inbound-box-open-scan' },
                        }}
                      />
                      <Button
                        variant="contained"
                        disabled={busy || !boxOpenScan.trim()}
                        onClick={() => void openInboundBoxByScan()}
                        data-testid="ff-inbound-box-open-submit"
                      >
                        Открыть короб
                      </Button>
                    </Stack>
                  ) : (
                    <Stack spacing={1.5}>
                      <Alert severity="info" data-testid="ff-inbound-active-box">
                        Активный короб № <strong>{activeIntakeBox.box_number}</strong> (
                        <code>{activeIntakeBox.internal_barcode}</code>)
                      </Alert>
                      <Stack direction="row" spacing={1} sx={{ mb: 1 }}>
                        <Button
                          variant="outlined"
                          disabled={busy}
                          onClick={() => void closeActiveInboundBox()}
                          data-testid="ff-inbound-box-close"
                        >
                          Закрыть короб
                        </Button>
                      </Stack>
                      <Table size="small" data-testid="ff-inbound-active-box-lines">
                        <TableHead>
                          <TableRow>
                            <TableCell>Артикул</TableCell>
                            <TableCell>Товар</TableCell>
                            <TableCell align="right" sx={{ width: 90 }}>
                              Заявлено
                            </TableCell>
                            <TableCell align="right" sx={{ width: 120 }}>
                              В коробе
                            </TableCell>
                          </TableRow>
                        </TableHead>
                        <TableBody>
                          {detail.lines.map((ln) => {
                            const inOther = qtyInOtherBoxesByProductId.get(ln.product_id) ?? 0
                            const totalAfter =
                              inOther +
                              Math.floor(
                                Number(boxQtyDraftByProductId[ln.product_id] ?? '0') || 0,
                              )
                            return (
                              <TableRow key={ln.id} data-testid="ff-inbound-box-line-row">
                                <TableCell>{ln.sku_code}</TableCell>
                                <TableCell>{ln.product_name}</TableCell>
                                <TableCell align="right">{ln.expected_qty}</TableCell>
                                <TableCell align="right">
                                  <TextField
                                    type="number"
                                    size="small"
                                    value={boxQtyDraftByProductId[ln.product_id] ?? '0'}
                                    disabled={busy}
                                    onChange={(e) =>
                                      setBoxQtyDraftByProductId((prev) => ({
                                        ...prev,
                                        [ln.product_id]: e.target.value,
                                      }))
                                    }
                                    onBlur={() => void saveBoxLineQty(ln.product_id)}
                                    helperText={
                                      totalAfter > ln.expected_qty
                                        ? `всего ${totalAfter} (заявлено ${ln.expected_qty})`
                                        : inOther > 0
                                          ? `в др. коробах ${inOther}`
                                          : undefined
                                    }
                                    slotProps={{
                                      htmlInput: {
                                        min: 0,
                                        'data-testid': 'ff-inbound-box-line-qty',
                                      },
                                    }}
                                    sx={{ maxWidth: 120 }}
                                  />
                                </TableCell>
                              </TableRow>
                            )
                          })}
                        </TableBody>
                      </Table>
                    </Stack>
                  )}
                </Paper>
              ) : null}

              {detail.status === 'verified' ? (
                <Paper variant="outlined" sx={{ p: 2 }} data-testid="ff-inbound-admin-distribution">
                  <Stack direction={{ xs: 'column', sm: 'row' }} spacing={1} sx={{ alignItems: { sm: 'center' } }}>
                    <Box sx={{ flexGrow: 1 }}>
                      <Typography variant="subtitle2" sx={{ fontWeight: 800 }}>
                        Распределение по ячейкам
                      </Typography>
                      <Typography variant="body2" color="text.secondary">
                        {distributionCompleted
                          ? 'Распределение зафиксировано, правки недоступны.'
                          : detail.status === 'verified'
                            ? 'Добавьте строки (товар + ячейка + кол-во) или нажмите «Завершить распределение» без строк — остаток уйдёт в «Без ячейки».'
                            : 'Станет доступно после «Завершить пересчёт» (статус «Проверено на складе»).'}
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

                  {locations.length === 0 &&
                  !distributionCompleted &&
                  (distOpen || detail.status === 'verified') ? (
                    <Alert severity="warning" sx={{ mt: 2 }} data-testid="ff-inbound-distribution-no-locations">
                      <Typography variant="body2" sx={{ mb: 1 }}>
                        На складе этой заявки <strong>нет ячеек</strong> — поэтому список «Ячейка» пустой и
                        не открывается. Создайте ячейку здесь или в разделе{' '}
                        <strong>Каталог → Ячейки</strong> (тот же склад).
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
                                setDistLines((prev) => [...prev, { product_id: '', storage_location_id: '', quantity: '' }])
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
                              Завершить распределение
                            </Button>
                          </>
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

      <Dialog
        open={pickerOpen}
        onClose={() => (busy ? undefined : setPickerOpen(false))}
        maxWidth={false}
        fullWidth
        slotProps={{ paper: { sx: { width: 'min(1200px, 96vw)', maxHeight: '92vh' } } }}
        data-testid="ff-inbound-picker"
      >
        <DialogTitle>Выбор товаров</DialogTitle>
        <DialogContent dividers>
          <Stack spacing={2} sx={{ mb: 2 }}>
            <TextField
              label="Поиск (артикул, ШК, nm, название, артикул продавца)"
              value={pickerSearch}
              onChange={(e) => setPickerSearch(e.target.value)}
              onKeyDown={(e) => {
                if (e.key !== 'Enter' || !catalog) return
                e.preventDefault()
                const productId = resolveProductIdByBarcode(catalog, pickerSearch)
                const targetId =
                  productId ?? (filteredPickerRows.length === 1 ? filteredPickerRows[0]!.id : null)
                if (!targetId) return
                setPickerQtyByProduct((prev) => ({
                  ...prev,
                  [targetId]: (prev[targetId] ?? 0) + 1,
                }))
                setPickerSearch('')
              }}
              size="small"
              fullWidth
              slotProps={{ htmlInput: { 'data-testid': 'ff-inbound-picker-search' } }}
            />
            <FormControl size="small" sx={{ minWidth: 260 }}>
              <InputLabel id="ff-picker-cat-label">Категория (WB)</InputLabel>
              <Select
                labelId="ff-picker-cat-label"
                label="Категория (WB)"
                value={pickerCategory}
                onChange={(e) => setPickerCategory(String(e.target.value))}
                data-testid="ff-inbound-picker-category"
              >
                <MenuItem value="__all__">Все</MenuItem>
                {categories.map((c) => (
                  <MenuItem key={c} value={c}>
                    {c}
                  </MenuItem>
                ))}
              </Select>
            </FormControl>
          </Stack>
          <TableContainer sx={{ width: '100%', overflowX: 'hidden' }}>
            <Table
              size="small"
              data-testid="ff-inbound-picker-table"
              sx={{ tableLayout: 'fixed', width: '100%' }}
            >
              <TableHead>
                <TableRow>
                  <TableCell sx={{ width: 56 }}>Фото</TableCell>
                  <TableCell sx={{ width: 160, pl: 2 }}>Артикул</TableCell>
                  <TableCell sx={{ width: 190 }}>ШК</TableCell>
                  <TableCell sx={{ width: 150 }}>Артикул продавца</TableCell>
                  <TableCell sx={{ width: 120, pr: 2 }}>Артикул WB</TableCell>
                  <TableCell sx={{ pl: 2 }}>Наименование</TableCell>
                  <TableCell align="right" sx={{ width: 140 }}>
                    Кол-во в заявку
                  </TableCell>
                </TableRow>
              </TableHead>
              <TableBody>
                {filteredPickerRows.map((r) => {
                  const inDraft = lineProductIds.has(r.id)
                  const qty = pickerQtyByProduct[r.id] ?? 0
                  return (
                    <TableRow
                      key={r.id}
                      hover
                      sx={{ opacity: inDraft ? 0.45 : 1 }}
                      data-testid="ff-inbound-picker-row"
                      data-in-draft={inDraft ? '1' : '0'}
                    >
                      <TableCell>
                        <Avatar variant="rounded" src={r.wb_primary_image_url ?? undefined} sx={{ width: 44, height: 44 }} />
                      </TableCell>
                      <TableCell sx={{ pl: 2 }} title={r.sku_code}>
                        {r.sku_code}
                      </TableCell>
                      <TableCell title={r.wb_primary_barcode ?? (r.wb_barcodes[0] ?? '—')}>
                        {r.wb_primary_barcode ?? (r.wb_barcodes[0] ?? '—')}
                      </TableCell>
                      <TableCell title={r.wb_vendor_code ?? '—'}>{r.wb_vendor_code ?? '—'}</TableCell>
                      <TableCell sx={{ pr: 2 }}>{r.wb_nm_id ?? '—'}</TableCell>
                      <TableCell sx={{ pl: 2 }} title={r.name}>
                        <Typography variant="body2" noWrap>
                          {r.name}
                        </Typography>
                        {inDraft ? (
                          <Typography variant="caption" color="text.secondary" sx={{ display: 'block' }} noWrap>
                            Товар уже добавлен в заявку
                          </Typography>
                        ) : null}
                      </TableCell>
                      <TableCell align="right">
                        <TextField
                          type="number"
                          size="small"
                          disabled={inDraft || busy}
                          value={qty || ''}
                          onChange={(e) =>
                            setPickerQtyByProduct((prev) => ({
                              ...prev,
                              [r.id]: Number(e.target.value),
                            }))
                          }
                          slotProps={{ htmlInput: { min: 0, 'data-testid': 'ff-inbound-picker-qty' } }}
                        />
                      </TableCell>
                    </TableRow>
                  )
                })}
              </TableBody>
            </Table>
          </TableContainer>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setPickerOpen(false)} disabled={busy} data-testid="ff-inbound-picker-cancel">
            Отмена
          </Button>
          <Button variant="contained" onClick={() => void applyPicker()} disabled={busy} data-testid="ff-inbound-picker-apply">
            Добавить в заявку
          </Button>
        </DialogActions>
      </Dialog>
    </Box>
  )
}

