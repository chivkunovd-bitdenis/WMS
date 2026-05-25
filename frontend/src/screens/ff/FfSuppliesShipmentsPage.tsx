import { useCallback, useEffect, useMemo, useState } from 'react'
import { DeleteOutlineOutlined } from '@mui/icons-material'
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
  MenuItem,
  Paper,
  Select,
  Stack,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableRow,
  TextField,
  Tooltip,
  Typography,
} from '@mui/material'
import { apiUrl } from '../../api'
import { readApiErrorMessage } from '../../utils/readApiErrorMessage'
import type { FfInboundSummary, FfOutboundSummary } from './FfDashboard'
import { PageHeader } from '../../ui/PageHeader'
import { formatDateTimeLocal } from '../../utils/formatDateTimeLocal'

export type FfMarketplaceUnloadSummary = {
  id: string
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
  sku_code: string
  product_name: string
  quantity: number
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

type MarketplaceUnloadPickOptionLocation = {
  storage_location_id: string
  location_code: string
  quantity: number
  reserved: number
  available: number
}

type MarketplaceUnloadPickOptionProduct = {
  product_id: string
  sku_code: string
  product_name: string
  scanned_qty: number
  locations: MarketplaceUnloadPickOptionLocation[]
}

type MarketplaceUnloadDetail = {
  id: string
  warehouse_id: string
  warehouse_name: string
  status: string
  ff_modified: boolean
  wb_mp_warehouse_id: number | null
  lines: DocLineRow[]
  boxes: MarketplaceUnloadBox[]
  pick_allocations: MarketplaceUnloadPickAllocation[]
}

type DiscrepancyActDetail = {
  id: string
  status: string
  inbound_intake_request_id: string | null
  lines: DocLineRow[]
}

type DocKind = 'inbound' | 'outbound' | 'marketplace_unload' | 'discrepancy_act'

/** Быстрые фильтры без операционной «Отгрузки» — только «Отгрузки на МП». */
type QuickFilterKind = 'all' | 'inbound' | 'marketplace_unload' | 'discrepancy_act'

type UnifiedRow = {
  kind: DocKind
  id: string
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
  if (status === 'shipped') return 'Отгружено'
  if (status === 'submitted') return 'Запланировано'
  if (status === 'primary_accepted') return 'Принято на складе'
  if (status === 'verifying') return 'Проверка'
  if (status === 'verified') return 'Проверено'
  if (status === 'posted') return 'Проведено'
  return status
}

function kindRu(kind: DocKind): string {
  if (kind === 'inbound') return 'Поставка'
  if (kind === 'outbound') return 'Отгрузка'
  if (kind === 'marketplace_unload') return 'Отгрузка на МП'
  return 'Расхождение'
}

type ProductPick = { id: string; sku_code: string; name: string }
type AvailableProductPick = ProductPick & { available: number }

type Props = {
  busy: boolean
  error: string | null
  infoNotice: string | null
  onDismissInfoNotice: () => void
  token: string | null
  productPicklist: ProductPick[]
  onRefreshFfSupplyExtras: () => Promise<void>
  inboundSummaries: FfInboundSummary[]
  outboundSummaries: FfOutboundSummary[]
  marketplaceUnloadSummaries: FfMarketplaceUnloadSummary[]
  discrepancyActSummaries: FfDiscrepancyActSummary[]
  onOpenInbound: (id: string) => void
  onOpenOutbound: (id: string) => void
  onCreateMpShipment: () => Promise<{ id: string } | null>
  onCreateDiverge: () => Promise<{ id: string } | null>
  initialMarketplaceUnloadId?: string | null
  onInitialMarketplaceUnloadOpened?: () => void
}

export function FfSuppliesShipmentsPage({
  busy,
  error,
  infoNotice,
  onDismissInfoNotice,
  token,
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
}: Props) {
  const [kind, setKind] = useState<QuickFilterKind>('all')
  const [sellerFilter, setSellerFilter] = useState<string>('all')
  const [sortKey, setSortKey] = useState<'planned_desc' | 'planned_asc' | 'created_desc' | 'created_asc'>(
    'created_desc',
  )

  const [docModal, setDocModal] = useState<null | 'marketplace_unload' | 'discrepancy_act'>(null)
  const [docModalId, setDocModalId] = useState<string | null>(null)
  const [modalBusy, setModalBusy] = useState(false)
  const [modalError, setModalError] = useState<string | null>(null)
  const [unloadDetail, setUnloadDetail] = useState<MarketplaceUnloadDetail | null>(null)
  const [divergeDetail, setDivergeDetail] = useState<DiscrepancyActDetail | null>(null)
  const [lineProductId, setLineProductId] = useState<string>('')
  const [lineQty, setLineQty] = useState<string>('1')
  const [boxPreset, setBoxPreset] = useState<'60_40_40' | '30_20_30'>('60_40_40')
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
  const [pickDialogOpen, setPickDialogOpen] = useState(false)
  const [pickOptions, setPickOptions] = useState<MarketplaceUnloadPickOptionProduct[]>([])
  const [confirmDate, setConfirmDate] = useState<string>('')
  const [pickQtyByProductLoc, setPickQtyByProductLoc] = useState<
    Record<string, Record<string, string>>
  >({})

  const authHeaders = useMemo(
    () => (token ? { Authorization: `Bearer ${token}` } : null),
    [token],
  )

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
          warehouse_id: string
          warehouse_name: string
          status: string
          ff_modified?: boolean
          wb_mp_warehouse_id?: number | null
          lines: { id: string; sku_code: string; product_name: string; quantity: number }[]
          boxes?: {
            id: string
            box_preset: string
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
        }
        setUnloadDetail({
          id: j.id,
          warehouse_id: j.warehouse_id,
          warehouse_name: j.warehouse_name,
          status: j.status,
          ff_modified: Boolean(j.ff_modified),
          wb_mp_warehouse_id: j.wb_mp_warehouse_id ?? null,
          lines: j.lines.map((ln) => ({
            id: ln.id,
            sku_code: ln.sku_code,
            product_name: ln.product_name,
            quantity: ln.quantity,
            inbound_intake_line_id: null,
          })),
          boxes: (j.boxes ?? []).map((b) => ({
            id: b.id,
            box_preset: b.box_preset,
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
        })
        const stockRes = await fetch(
          apiUrl(
            `/operations/inventory-balances/summary?warehouse_id=${encodeURIComponent(j.warehouse_id)}`,
          ),
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

  const createAndOpenMpShipment = async () => {
    const created = await onCreateMpShipment()
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
    setModalBusy(true)
    setModalError(null)
    try {
      const res = await fetch(apiUrl(`/operations/marketplace-unload-requests/${docModalId}/boxes`), {
        method: 'POST',
        headers: {
          ...authHeaders,
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ box_preset: boxPreset }),
      })
      if (!res.ok) {
        setModalError(await readApiErrorMessage(res))
        return
      }
      setScanBarcode('')
      await loadDocDetail()
      await onRefreshFfSupplyExtras()
    } catch (e) {
      setModalError(e instanceof Error ? e.message : 'Не удалось открыть короб.')
    } finally {
      setModalBusy(false)
    }
  }

  const doScan = async (boxId: string) => {
    if (!token || !authHeaders || docModal !== 'marketplace_unload' || !docModalId) {
      return
    }
    const raw = scanBarcode.trim()
    if (!raw) {
      setModalError('Введите штрихкод.')
      return
    }
    setModalBusy(true)
    setModalError(null)
    try {
      const res = await fetch(
        apiUrl(`/operations/marketplace-unload-requests/${docModalId}/boxes/${boxId}/scan`),
        {
          method: 'POST',
          headers: {
            ...authHeaders,
            'Content-Type': 'application/json',
          },
          body: JSON.stringify({ barcode: raw }),
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
      setModalError(e instanceof Error ? e.message : 'Не удалось отсканировать.')
    } finally {
      setModalBusy(false)
    }
  }

  const closeBox = async (boxId: string) => {
    if (!token || !authHeaders || docModal !== 'marketplace_unload' || !docModalId) {
      return
    }
    setModalBusy(true)
    setModalError(null)
    try {
      const res = await fetch(
        apiUrl(`/operations/marketplace-unload-requests/${docModalId}/boxes/${boxId}/close`),
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
      setModalError(e instanceof Error ? e.message : 'Не удалось закрыть короб.')
    } finally {
      setModalBusy(false)
    }
  }

  const openPickDialog = async () => {
    if (!token || !authHeaders || !docModalId) {
      return
    }
    setModalBusy(true)
    setModalError(null)
    try {
      const res = await fetch(
        apiUrl(`/operations/marketplace-unload-requests/${docModalId}/pick-options`),
        { headers: authHeaders },
      )
      if (!res.ok) {
        setModalError(await readApiErrorMessage(res))
        return
      }
      const opts = (await res.json()) as MarketplaceUnloadPickOptionProduct[]
      setPickOptions(opts)
      const seed: Record<string, Record<string, string>> = {}
      for (const a of unloadDetail?.pick_allocations ?? []) {
        if (!seed[a.product_id]) {
          seed[a.product_id] = {}
        }
        seed[a.product_id][a.storage_location_id] = String(a.quantity)
      }
      setPickQtyByProductLoc(seed)
      setPickDialogOpen(true)
    } catch (e) {
      setModalError(e instanceof Error ? e.message : 'Не удалось загрузить подбор.')
    } finally {
      setModalBusy(false)
    }
  }

  const savePickAllocations = async () => {
    if (!token || !authHeaders || !docModalId) {
      return
    }
    const allocations: { product_id: string; storage_location_id: string; quantity: number }[] = []
    for (const [productId, byLoc] of Object.entries(pickQtyByProductLoc)) {
      for (const [locId, raw] of Object.entries(byLoc)) {
        const q = Number(raw)
        if (Number.isInteger(q) && q > 0) {
          allocations.push({
            product_id: productId,
            storage_location_id: locId,
            quantity: q,
          })
        }
      }
    }
    setModalBusy(true)
    setModalError(null)
    try {
      const res = await fetch(
        apiUrl(`/operations/marketplace-unload-requests/${docModalId}/pick-allocations`),
        {
          method: 'PUT',
          headers: { ...authHeaders, 'Content-Type': 'application/json' },
          body: JSON.stringify({ allocations }),
        },
      )
      if (!res.ok) {
        setModalError(await readApiErrorMessage(res))
        return
      }
      setPickDialogOpen(false)
      await loadDocDetail()
      await onRefreshFfSupplyExtras()
    } catch (e) {
      setModalError(e instanceof Error ? e.message : 'Не удалось сохранить подбор.')
    } finally {
      setModalBusy(false)
    }
  }

  const shipMpUnload = async () => {
    if (!token || !authHeaders || !docModalId) {
      return
    }
    setModalBusy(true)
    setModalError(null)
    try {
      const res = await fetch(
        apiUrl(`/operations/marketplace-unload-requests/${docModalId}/ship`),
        { method: 'POST', headers: authHeaders },
      )
      if (!res.ok) {
        setModalError(await readApiErrorMessage(res))
        return
      }
      await loadDocDetail()
      await onRefreshFfSupplyExtras()
    } catch (e) {
      setModalError(e instanceof Error ? e.message : 'Не удалось отгрузить.')
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
        const body =
          confirmDate.trim().length > 0
            ? { planned_shipment_date: confirmDate.trim() }
            : {}
        const res = await fetch(
          apiUrl(`/operations/marketplace-unload-requests/${docModalId}/confirm`),
          {
            method: 'POST',
            headers: { ...authHeaders, 'Content-Type': 'application/json' },
            body: JSON.stringify(body),
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
    for (const r of inboundSummaries) {
      if (r.seller_name) {
        s.add(r.seller_name)
      }
    }
    for (const r of outboundSummaries) {
      if (r.seller_name) {
        s.add(r.seller_name)
      }
    }
    for (const r of marketplaceUnloadSummaries) {
      if (r.seller_name) {
        s.add(r.seller_name)
      }
    }
    for (const r of discrepancyActSummaries) {
      if (r.seller_name) {
        s.add(r.seller_name)
      }
    }
    return Array.from(s).sort((a, b) => a.localeCompare(b))
  }, [
    inboundSummaries,
    outboundSummaries,
    marketplaceUnloadSummaries,
    discrepancyActSummaries,
  ])

  const rows = useMemo(() => {
    const all: UnifiedRow[] = [
      ...inboundSummaries.map((r) => ({
        kind: 'inbound' as const,
        id: r.id,
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
        plannedDate: r.planned_shipment_date ?? r.created_at?.slice(0, 10) ?? null,
        createdAt: r.created_at ?? null,
        status: r.status,
        lineCount: r.line_count,
        sellerName: r.seller_name ?? null,
        extraLabel: null,
        ffModified: false,
      })),
      ...marketplaceUnloadSummaries.map((r) => ({
        kind: 'marketplace_unload' as const,
        id: r.id,
        plannedDate: r.planned_shipment_date ?? null,
        createdAt: r.created_at,
        status: r.status,
        lineCount: r.line_count,
        sellerName: r.seller_name ?? null,
        extraLabel: r.warehouse_name,
        ffModified: Boolean(r.ff_modified),
      })),
      ...discrepancyActSummaries.map((r) => ({
        kind: 'discrepancy_act' as const,
        id: r.id,
        plannedDate: null,
        createdAt: r.created_at,
        status: r.status,
        lineCount: r.line_count,
        sellerName: r.seller_name ?? null,
        extraLabel: r.inbound_intake_request_id ? `приёмка ${r.inbound_intake_request_id.slice(0, 8)}…` : null,
        ffModified: false,
      })),
    ]
    let filtered = kind === 'all' ? all : all.filter((x) => x.kind === kind)
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

  const mpDraft = docModal === 'marketplace_unload' && unloadDetail?.status === 'draft'
  const mpSubmitted =
    docModal === 'marketplace_unload' && unloadDetail?.status === 'submitted'
  const mpConfirmed = docModal === 'marketplace_unload' && unloadDetail?.status === 'confirmed'
  const mpPickEditable =
    mpConfirmed && docModal === 'marketplace_unload' && unloadDetail?.status !== 'shipped'

  const draftDoc =
    mpDraft ||
    mpSubmitted ||
    (docModal === 'discrepancy_act' && divergeDetail?.status === 'draft')
  const mpLineDraft = mpDraft || mpSubmitted

  return (
    <Box data-testid="ff-supplies-shipments-page">
      <PageHeader
        title="Поставки и отгрузки"
        description="Единый список: поставки (селлер → ФФ), операционные отгрузки, документы отгрузки ФФ на маркетплейс и акты расхождения. По строкам отгрузки на МП и расхождения — клик для состава; поставку и отгрузку из операций открываем в разделе операций."
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
        <Stack direction={{ xs: 'column', sm: 'row' }} spacing={1.5}>
          <Button
            variant="contained"
            color="primary"
            disabled={busy}
            data-testid="ff-create-mp-shipment"
            onClick={() => void createAndOpenMpShipment()}
          >
            Создать отгрузку на МП
          </Button>
          <Button
            variant="outlined"
            color="secondary"
            disabled={busy}
            data-testid="ff-create-diverge"
            onClick={() => void createAndOpenDiverge()}
          >
            Создать расхождение
          </Button>
        </Stack>
      </Paper>

      <Paper variant="outlined" sx={{ p: 2, mb: 2 }}>
        <Stack
          direction={{ xs: 'column', md: 'row' }}
          spacing={1.5}
          sx={{ flexWrap: 'wrap', alignItems: { xs: 'stretch', md: 'center' } }}
        >
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
              variant={kind === 'marketplace_unload' ? 'contained' : 'outlined'}
              onClick={() => setKind('marketplace_unload')}
              data-testid="ff-docs-filter-mp-shipment"
            >
              Отгрузки на МП
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
            <TableCell>Тип</TableCell>
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
              <TableCell colSpan={7}>
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
                <TableCell>{kindRu(row.kind)}</TableCell>
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
            <Alert severity="error" sx={{ mb: 2 }}>
              {modalError}
            </Alert>
          ) : null}
          {modalBusy && !unloadDetail && !divergeDetail ? (
            <Typography variant="body2" color="text.secondary">
              Загрузка…
            </Typography>
          ) : null}
          {unloadDetail ? (
            <Typography variant="body2" color="text.secondary" sx={{ mb: 1 }}>
              Склад: {unloadDetail.warehouse_name} · {statusRu(unloadDetail.status)}
            </Typography>
          ) : null}
          {unloadDetail?.ff_modified ? (
            <Alert severity="warning" sx={{ mb: 1 }} data-testid="ff-mp-ff-modified-notice">
              Состав изменён на складе после планирования селлером.
            </Alert>
          ) : null}
          {docModal === 'marketplace_unload' && unloadDetail && mpLineDraft ? (
            <Stack direction={{ xs: 'column', sm: 'row' }} spacing={1.25} sx={{ mb: 2, mt: 1 }}>
              <FormControl
                size="small"
                sx={{ minWidth: 280, width: { xs: '100%', sm: 'auto' } }}
                disabled={modalBusy || wbMpWarehousesBusy}
              >
                <InputLabel id="ff-mp-wb-warehouse">Склад WB (маркетплейс)</InputLabel>
                <Select
                  labelId="ff-mp-wb-warehouse"
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
                <Typography
                  variant="caption"
                  color="text.secondary"
                  sx={{ alignSelf: { xs: 'flex-start', sm: 'center' }, lineHeight: 1.25 }}
                >
                  Можно создать черновик без склада WB. Для «Утвердить» нужно выбрать склад, когда он появится.
                </Typography>
              ) : null}
            </Stack>
          ) : null}
          {divergeDetail ? (
            <Typography variant="body2" color="text.secondary" sx={{ mb: 1 }}>
              {statusRu(divergeDetail.status)}
              {divergeDetail.inbound_intake_request_id
                ? ` · приёмка ${divergeDetail.inbound_intake_request_id.slice(0, 8)}…`
                : ''}
            </Typography>
          ) : null}
          <Table size="small" data-testid="ff-supplies-doc-lines">
            <TableHead>
              <TableRow>
                <TableCell>Артикул</TableCell>
                <TableCell>Товар</TableCell>
                <TableCell>Строка приёмки</TableCell>
                <TableCell align="right">Кол-во</TableCell>
                {draftDoc ? <TableCell align="right" width={56} /> : null}
              </TableRow>
            </TableHead>
            <TableBody>
              {(() => {
                const lines = unloadDetail?.lines ?? divergeDetail?.lines ?? []
                const emptySpan = draftDoc ? 5 : 4
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
                return lines.map((ln) => (
                  <TableRow key={ln.id}>
                    <TableCell>{ln.sku_code}</TableCell>
                    <TableCell>{ln.product_name}</TableCell>
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
                ))
              })()}
            </TableBody>
          </Table>
          {docModal === 'marketplace_unload' && unloadDetail && unloadDetail.pick_allocations.length > 0 ? (
            <Paper variant="outlined" sx={{ p: 1.5, mt: 2 }} data-testid="ff-mp-pick-saved">
              <Typography variant="subtitle2" sx={{ mb: 1 }}>
                Подбор по ячейкам
              </Typography>
              <Table size="small">
                <TableHead>
                  <TableRow>
                    <TableCell>Товар</TableCell>
                    <TableCell>Ячейка</TableCell>
                    <TableCell align="right">Снять</TableCell>
                  </TableRow>
                </TableHead>
                <TableBody>
                  {unloadDetail.pick_allocations.map((a) => (
                    <TableRow key={a.id}>
                      <TableCell>
                        {a.sku_code} — {a.product_name}
                      </TableCell>
                      <TableCell>{a.location_code}</TableCell>
                      <TableCell align="right">{a.quantity}</TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </Paper>
          ) : null}
          {docModal === 'marketplace_unload' && unloadDetail && mpConfirmed ? (
            <Box sx={{ mt: 2 }} data-testid="ff-mp-boxes">
              {(() => {
                const openBox = unloadDetail.boxes.find((b) => !b.closed_at) ?? null
                const closed = unloadDetail.boxes.filter((b) => Boolean(b.closed_at))
                return (
                  <Stack spacing={1.5}>
                    <Typography variant="subtitle2">Короба</Typography>

                    {mpConfirmed ? (
                      <Paper variant="outlined" sx={{ p: 1.5 }}>
                        <Stack spacing={1.25}>
                          <Typography variant="body2" color="text.secondary">
                            Открытый короб: {openBox ? `${openBox.id.slice(0, 8)}…` : 'нет'}
                          </Typography>
                          {!openBox ? (
                            <Stack direction="row" spacing={1} sx={{ alignItems: 'center' }}>
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
                                variant="contained"
                                onClick={() => void createBox()}
                                disabled={modalBusy}
                                data-testid="ff-mp-box-open"
                              >
                                Открыть короб
                              </Button>
                            </Stack>
                          ) : (
                            <Stack spacing={1}>
                              <Stack direction="row" spacing={1} sx={{ alignItems: 'center' }}>
                                <TextField
                                  size="small"
                                  label="Штрихкод WB"
                                  value={scanBarcode}
                                  onChange={(e) => setScanBarcode(e.target.value)}
                                  disabled={modalBusy}
                                  fullWidth
                                  data-testid="ff-mp-box-scan-input"
                                />
                                <Button
                                  variant="contained"
                                  onClick={() => void doScan(openBox.id)}
                                  disabled={modalBusy}
                                  data-testid="ff-mp-box-scan"
                                >
                                  Скан
                                </Button>
                                <Button
                                  variant="outlined"
                                  onClick={() => void closeBox(openBox.id)}
                                  disabled={modalBusy}
                                  data-testid="ff-mp-box-close"
                                >
                                  Закрыть
                                </Button>
                              </Stack>
                              <Table size="small" sx={{ mt: 1 }} data-testid="ff-mp-open-box-lines">
                                <TableHead>
                                  <TableRow>
                                    <TableCell>Артикул</TableCell>
                                    <TableCell>Товар</TableCell>
                                    <TableCell align="right">Сканов</TableCell>
                                  </TableRow>
                                </TableHead>
                                <TableBody>
                                  {openBox.lines.length === 0 ? (
                                    <TableRow>
                                      <TableCell colSpan={3}>
                                        <Typography variant="body2" color="text.secondary">
                                          Пока нет сканов
                                        </Typography>
                                      </TableCell>
                                    </TableRow>
                                  ) : (
                                    openBox.lines.map((ln) => (
                                      <TableRow key={ln.id}>
                                        <TableCell>{ln.sku_code}</TableCell>
                                        <TableCell>{ln.product_name}</TableCell>
                                        <TableCell align="right">{ln.quantity}</TableCell>
                                      </TableRow>
                                    ))
                                  )}
                                </TableBody>
                              </Table>
                            </Stack>
                          )}
                        </Stack>
                      </Paper>
                    ) : null}

                    {closed.length > 0 ? (
                      <Paper variant="outlined" sx={{ p: 1.5 }}>
                        <Typography variant="body2" sx={{ mb: 1 }}>
                          Закрытые короба: {closed.length}
                        </Typography>
                        <Stack spacing={1}>
                          {closed.map((b) => (
                            <Box key={b.id} sx={{ borderTop: '1px solid', borderColor: 'divider', pt: 1 }}>
                              <Typography variant="body2" color="text.secondary">
                                {b.box_preset} · {b.id.slice(0, 8)}… · {b.closed_at ? b.closed_at.slice(0, 19).replace('T', ' ') : '—'}
                              </Typography>
                              <Table size="small" sx={{ mt: 0.5 }}>
                                <TableHead>
                                  <TableRow>
                                    <TableCell>Артикул</TableCell>
                                    <TableCell>Товар</TableCell>
                                    <TableCell align="right">Кол-во</TableCell>
                                  </TableRow>
                                </TableHead>
                                <TableBody>
                                  {b.lines.length === 0 ? (
                                    <TableRow>
                                      <TableCell colSpan={3}>
                                        <Typography variant="body2" color="text.secondary">
                                          Нет строк
                                        </Typography>
                                      </TableCell>
                                    </TableRow>
                                  ) : (
                                    b.lines.map((ln) => (
                                      <TableRow key={ln.id}>
                                        <TableCell>{ln.sku_code}</TableCell>
                                        <TableCell>{ln.product_name}</TableCell>
                                        <TableCell align="right">{ln.quantity}</TableCell>
                                      </TableRow>
                                    ))
                                  )}
                                </TableBody>
                              </Table>
                            </Box>
                          ))}
                        </Stack>
                      </Paper>
                    ) : null}
                  </Stack>
                )
              })()}
            </Box>
          ) : null}
          {((draftDoc && docModal !== 'marketplace_unload') ||
            (mpDraft && docModal === 'marketplace_unload')) &&
          docProductPicklist.length > 0 ? (
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
          {draftDoc && docProductPicklist.length === 0 ? (
            <Typography variant="caption" color="text.secondary" sx={{ mt: 1, display: 'block' }}>
              {docModal === 'marketplace_unload'
                ? 'Нет товаров с доступным остатком на складе ФФ.'
                : 'Добавьте товары в каталоге, чтобы оформить строки.'}
            </Typography>
          ) : null}
        </DialogContent>
        <DialogActions>
          {mpPickEditable ? (
            <Button
              variant="outlined"
              disabled={modalBusy || (unloadDetail?.lines.length ?? 0) < 1}
              onClick={() => void openPickDialog()}
              data-testid="ff-mp-start-picking"
            >
              Начать подбор
            </Button>
          ) : null}
          {mpConfirmed ? (
            <Button
              variant="contained"
              color="primary"
              disabled={
                modalBusy ||
                (unloadDetail?.pick_allocations.length ?? 0) < 1
              }
              onClick={() => void shipMpUnload()}
              data-testid="ff-mp-ship"
            >
              Отгружено
            </Button>
          ) : null}
          {docModal === 'marketplace_unload' && (mpDraft || mpSubmitted) ? (
            <TextField
              size="small"
              label="Дата отвоза"
              type="date"
              value={confirmDate}
              onChange={(e) => setConfirmDate(e.target.value)}
              slotProps={{ inputLabel: { shrink: true } }}
              sx={{ mr: 1 }}
              data-testid="ff-mp-confirm-date"
            />
          ) : null}
          {docModal === 'marketplace_unload' && (mpDraft || mpSubmitted) ? (
            <Button
              variant="contained"
              color="secondary"
              disabled={
                modalBusy ||
                (docModal === 'marketplace_unload' && unloadDetail?.wb_mp_warehouse_id == null) ||
                (unloadDetail?.lines.length ?? 0) < 1
              }
              onClick={() => void submitDoc()}
              data-testid="ff-supplies-doc-submit"
            >
              Подтвердить
            </Button>
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
          <Button onClick={closeDocModal} data-testid="ff-supplies-doc-close">
            Закрыть
          </Button>
        </DialogActions>
      </Dialog>

      <Dialog
        open={pickDialogOpen}
        onClose={() => setPickDialogOpen(false)}
        maxWidth="md"
        fullWidth
        data-testid="ff-mp-picking-dialog"
      >
        <DialogTitle>Подбор товара по ячейкам</DialogTitle>
        <DialogContent dividers>
          <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
            Укажите, сколько снять с каждой ячейки. Сумма по товару должна совпасть с количеством
            отсканированным в коробах.
          </Typography>
          <Stack spacing={2}>
            {pickOptions.map((prod) => (
              <Paper key={prod.product_id} variant="outlined" sx={{ p: 1.5 }}>
                <Typography variant="subtitle2">
                  {prod.sku_code} — {prod.product_name}{' '}
                  <Typography component="span" variant="body2" color="text.secondary">
                    (скан: {prod.scanned_qty})
                  </Typography>
                </Typography>
                {prod.locations.length === 0 ? (
                  <Typography variant="body2" color="warning.main" sx={{ mt: 1 }}>
                    Нет остатка в ячейках на этом складе.
                  </Typography>
                ) : (
                  <Table size="small" sx={{ mt: 1 }}>
                    <TableHead>
                      <TableRow>
                        <TableCell>Ячейка</TableCell>
                        <TableCell align="right">Доступно</TableCell>
                        <TableCell align="right">Снять</TableCell>
                      </TableRow>
                    </TableHead>
                    <TableBody>
                      {prod.locations.map((loc) => (
                        <TableRow key={loc.storage_location_id}>
                          <TableCell>{loc.location_code}</TableCell>
                          <TableCell align="right">{loc.available}</TableCell>
                          <TableCell align="right">
                            <TextField
                              size="small"
                              type="number"
                              slotProps={{ htmlInput: { min: 0 } }}
                              value={
                                pickQtyByProductLoc[prod.product_id]?.[loc.storage_location_id] ??
                                ''
                              }
                              onChange={(e) => {
                                const v = e.target.value
                                setPickQtyByProductLoc((prev) => ({
                                  ...prev,
                                  [prod.product_id]: {
                                    ...(prev[prod.product_id] ?? {}),
                                    [loc.storage_location_id]: v,
                                  },
                                }))
                              }}
                              sx={{ width: 88 }}
                              data-testid={`ff-mp-pick-qty-${loc.location_code}`}
                            />
                          </TableCell>
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                )}
              </Paper>
            ))}
          </Stack>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setPickDialogOpen(false)}>Отмена</Button>
          <Button
            variant="contained"
            disabled={modalBusy || pickOptions.length < 1}
            onClick={() => void savePickAllocations()}
            data-testid="ff-mp-pick-save"
          >
            Сохранить подбор
          </Button>
        </DialogActions>
      </Dialog>
    </Box>
  )
}
