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
import { printMarketplaceUnloadWaybill } from '../../utils/printShipmentWaybill'

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
  planned_qty: number
  picked_qty: number
  locations: MarketplaceUnloadPickOptionLocation[]
}

type MarketplaceUnloadDetail = {
  id: string
  warehouse_id: string
  warehouse_name: string
  status: string
  ff_modified: boolean
  seller_name: string | null
  wb_mp_warehouse_id: number | null
  planned_shipment_date: string | null
  created_at: string | null
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
  pageVariant = 'supplies',
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
  const isMpShipmentsPage = pageVariant === 'mp-shipments'
  const [kind, setKind] = useState<QuickFilterKind>(isMpShipmentsPage ? 'marketplace_unload' : 'all')
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
  const [collectQty, setCollectQty] = useState<string>('1')
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
  const [activePickLocationId, setActivePickLocationId] = useState<string | null>(null)
  const [activePickLocationCode, setActivePickLocationCode] = useState<string | null>(null)
  const [attachBoxBarcode, setAttachBoxBarcode] = useState('')

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
          seller_name?: string | null
          wb_mp_warehouse_id?: number | null
          planned_shipment_date?: string | null
          created_at?: string
          lines: {
            id: string
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
        }
        setUnloadDetail({
          id: j.id,
          warehouse_id: j.warehouse_id,
          warehouse_name: j.warehouse_name,
          status: j.status,
          ff_modified: Boolean(j.ff_modified),
          seller_name: j.seller_name ?? null,
          wb_mp_warehouse_id: j.wb_mp_warehouse_id ?? null,
          planned_shipment_date: j.planned_shipment_date ?? null,
          created_at: j.created_at ?? null,
          lines: j.lines.map((ln) => ({
            id: ln.id,
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
    setActivePickLocationId(null)
    setActivePickLocationCode(null)
    setCollectQty('1')
    setAttachBoxBarcode('')
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

  const doCollectScan = async (openBoxId: string | null) => {
    if (!token || !authHeaders || docModal !== 'marketplace_unload' || !docModalId) {
      return
    }
    const raw = scanBarcode.trim()
    if (!raw) {
      setModalError('Введите штрихкод.')
      return
    }
    const qty = Number(collectQty)
    if (!Number.isInteger(qty) || qty < 1) {
      setModalError('Укажите количество ≥ 1.')
      return
    }
    setModalBusy(true)
    setModalError(null)
    try {
      const locRes = await fetch(
        apiUrl(`/operations/marketplace-unload-requests/${docModalId}/pick/scan`),
        {
          method: 'POST',
          headers: { ...authHeaders, 'Content-Type': 'application/json' },
          body: JSON.stringify({ barcode: raw }),
        },
      )
      if (locRes.ok) {
        const j = (await locRes.json()) as {
          kind: string
          storage_location_id?: string | null
          location_code?: string | null
        }
        if (j.kind === 'location' && j.storage_location_id) {
          setActivePickLocationId(j.storage_location_id)
          setActivePickLocationCode(j.location_code ?? j.storage_location_id)
          setScanBarcode('')
          return
        }
      }

      if (!openBoxId) {
        setModalError('Сначала откройте или добавьте короб для сборки.')
        return
      }
      if (!activePickLocationId) {
        setModalError('Сначала отсканируйте ячейку.')
        return
      }

      const prodRes = await fetch(
        apiUrl(
          `/operations/marketplace-unload-requests/${docModalId}/boxes/${openBoxId}/scan`,
        ),
        {
          method: 'POST',
          headers: { ...authHeaders, 'Content-Type': 'application/json' },
          body: JSON.stringify({
            barcode: raw,
            storage_location_id: activePickLocationId,
            quantity: qty,
          }),
        },
      )
      if (!prodRes.ok) {
        setModalError(await readApiErrorMessage(prodRes))
        return
      }
      setScanBarcode('')
      await loadDocDetail()
      await onRefreshFfSupplyExtras()
    } catch (e) {
      setModalError(e instanceof Error ? e.message : 'Не удалось выполнить скан.')
    } finally {
      setModalBusy(false)
    }
  }

  const doScan = async (boxId: string) => {
    await doCollectScan(boxId)
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


  const attachExistingBox = async () => {
    if (!token || !authHeaders || !docModalId) {
      return
    }
    const raw = attachBoxBarcode.trim()
    if (!raw) {
      setModalError('Введите штрихкод короба.')
      return
    }
    setModalBusy(true)
    setModalError(null)
    try {
      const res = await fetch(
        apiUrl(`/operations/marketplace-unload-requests/${docModalId}/boxes/attach`),
        {
          method: 'POST',
          headers: { ...authHeaders, 'Content-Type': 'application/json' },
          body: JSON.stringify({ barcode: raw, box_preset: boxPreset }),
        },
      )
      if (!res.ok) {
        setModalError(await readApiErrorMessage(res))
        return
      }
      setAttachBoxBarcode('')
      await loadDocDetail()
      await onRefreshFfSupplyExtras()
    } catch (e) {
      setModalError(e instanceof Error ? e.message : 'Не удалось добавить короб.')
    } finally {
      setModalBusy(false)
    }
  }

  const openPickDialog = async () => {
    if (!token || !authHeaders || !docModalId) {
      return
    }
    if (!openMpBox) {
      setModalError('Сначала откройте короб — ручной подбор идёт в текущую тару.')
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
      setPickQtyByProductLoc({})
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
    const hasDiscrepancy = unloadDetail?.lines.some((ln) => ln.has_discrepancy) ?? false
    if (
      hasDiscrepancy &&
      !window.confirm(
        'Фактический набор не совпадает с планом по одной или нескольким строкам. Отгрузить с расхождением?',
      )
    ) {
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
          body: JSON.stringify({ acknowledge_discrepancy: hasDiscrepancy }),
        },
      )
      if (!res.ok) {
        const msg = await readApiErrorMessage(res)
        if (msg.includes('discrepancy_requires_ack')) {
          setModalError('Подтвердите отгрузку с расхождением (факт ≠ план).')
        } else {
          setModalError(msg)
        }
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
          ...discrepancyActSummaries.map((r) => ({
            kind: 'discrepancy_act' as const,
            id: r.id,
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

  const mpDraft = docModal === 'marketplace_unload' && unloadDetail?.status === 'draft'
  const mpSubmitted =
    docModal === 'marketplace_unload' && unloadDetail?.status === 'submitted'
  const mpConfirmed = docModal === 'marketplace_unload' && unloadDetail?.status === 'confirmed'
  const mpPickEditable =
    mpConfirmed && docModal === 'marketplace_unload' && unloadDetail?.status !== 'shipped'

  const mpCollectSummary = useMemo(() => {
    if (!unloadDetail || docModal !== 'marketplace_unload') {
      return null
    }
    const planned = unloadDetail.lines.reduce((sum, ln) => sum + ln.quantity, 0)
    const picked = unloadDetail.lines.reduce((sum, ln) => sum + (ln.picked_qty ?? 0), 0)
    return { planned, picked, remaining: planned - picked }
  }, [unloadDetail, docModal])

  const openMpBox = useMemo(
    () => unloadDetail?.boxes.find((b) => !b.closed_at) ?? null,
    [unloadDetail?.boxes],
  )

  const draftDoc =
    mpDraft ||
    mpSubmitted ||
    (docModal === 'discrepancy_act' && divergeDetail?.status === 'draft')
  const mpLineDraft = mpDraft || mpSubmitted

  const pageTestId = isMpShipmentsPage ? 'ff-mp-shipments-page' : 'ff-supplies-shipments-page'

  return (
    <Box data-testid={pageTestId}>
      <PageHeader
        title={isMpShipmentsPage ? 'Отгрузки на МП' : 'Поставки'}
        description={
          isMpShipmentsPage
            ? 'Документы отгрузки фулфилмента на маркетплейс: состав, короба, подбор по ячейкам и проведение отгрузки.'
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
        <Stack direction={{ xs: 'column', sm: 'row' }} spacing={1.5}>
          {isMpShipmentsPage ? (
            <Button
              variant="contained"
              color="primary"
              disabled={busy}
              data-testid="ff-create-mp-shipment"
              onClick={() => void createAndOpenMpShipment()}
            >
              Создать отгрузку на МП
            </Button>
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
              <TableCell colSpan={isMpShipmentsPage ? 6 : 7}>
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
          {docModal === 'marketplace_unload' && mpConfirmed && mpCollectSummary ? (
            <Paper
              variant="outlined"
              sx={{ p: 1.5, mb: 2, bgcolor: 'action.hover' }}
              data-testid="ff-mp-collect-summary"
            >
              <Typography variant="subtitle2" sx={{ mb: 0.5 }}>
                Сборка отгрузки
              </Typography>
              <Typography variant="body2">
                Нужно: <strong>{mpCollectSummary.planned}</strong>
                {' · '}
                Собрано: <strong>{mpCollectSummary.picked}</strong>
                {' · '}
                Осталось:{' '}
                <strong
                  style={{
                    color: mpCollectSummary.remaining !== 0 ? '#ed6c02' : undefined,
                  }}
                >
                  {mpCollectSummary.remaining}
                </strong>
              </Typography>
            </Paper>
          ) : null}
          <Table size="small" data-testid="ff-supplies-doc-lines">
            <TableHead>
              <TableRow>
                <TableCell>Артикул</TableCell>
                <TableCell>Товар</TableCell>
                {docModal !== 'marketplace_unload' ? (
                  <TableCell>Строка приёмки</TableCell>
                ) : null}
                <TableCell align="right">План</TableCell>
                {docModal === 'marketplace_unload' && mpConfirmed ? (
                  <>
                    <TableCell align="right">Собрано</TableCell>
                    <TableCell align="right">Осталось</TableCell>
                  </>
                ) : null}
                {draftDoc ? <TableCell align="right" width={56} /> : null}
              </TableRow>
            </TableHead>
            <TableBody>
              {(() => {
                const lines = unloadDetail?.lines ?? divergeDetail?.lines ?? []
                const mpCols =
                  docModal === 'marketplace_unload' && mpConfirmed ? 2 : 0
                const emptySpan =
                  3 + (docModal === 'marketplace_unload' ? 0 : 1) + mpCols + (draftDoc ? 1 : 0)
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
                  return (
                  <TableRow
                    key={ln.id}
                    sx={
                      ln.has_discrepancy
                        ? { '& .MuiTableCell-root': { color: 'error.main' } }
                        : undefined
                    }
                    data-testid={
                      ln.has_discrepancy ? `ff-mp-line-discrepancy-${ln.id}` : undefined
                    }
                  >
                    <TableCell>{ln.sku_code}</TableCell>
                    <TableCell>{ln.product_name}</TableCell>
                    {docModal !== 'marketplace_unload' ? (
                      <TableCell sx={{ color: 'text.secondary', fontSize: 13 }}>
                        {ln.inbound_intake_line_id
                          ? `${ln.inbound_intake_line_id.slice(0, 8)}…`
                          : '—'}
                      </TableCell>
                    ) : null}
                    <TableCell align="right">{ln.quantity}</TableCell>
                    {docModal === 'marketplace_unload' && mpConfirmed ? (
                      <>
                        <TableCell align="right">{picked}</TableCell>
                        <TableCell align="right">{remaining}</TableCell>
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
                )})
              })()}
            </TableBody>
          </Table>
          {docModal === 'marketplace_unload' && unloadDetail && mpConfirmed ? (
            <Box sx={{ mt: 2 }} data-testid="ff-mp-boxes">
              {(() => {
                const openBox = openMpBox
                const closed = unloadDetail.boxes.filter((b) => Boolean(b.closed_at))
                return (
                  <Stack spacing={1.5}>
                    <Typography variant="subtitle2">Сборка в короба</Typography>
                    <Typography variant="body2" color="text.secondary">
                      Откройте короб, отсканируйте ячейку, затем товар (или укажите количество).
                      Снятие с полки всегда попадает в открытую тару.
                    </Typography>
                    <Stack direction={{ xs: 'column', sm: 'row' }} spacing={1} sx={{ mb: 1 }}>
                      <TextField
                        size="small"
                        label="Штрихкод существующего короба"
                        value={attachBoxBarcode}
                        onChange={(e) => setAttachBoxBarcode(e.target.value)}
                        disabled={modalBusy}
                        fullWidth
                        data-testid="ff-mp-box-attach-input"
                      />
                      <Button
                        variant="outlined"
                        onClick={() => void attachExistingBox()}
                        disabled={modalBusy}
                        data-testid="ff-mp-box-attach"
                      >
                        Добавить короб
                      </Button>
                    </Stack>

                    {mpConfirmed ? (
                      <Paper variant="outlined" sx={{ p: 1.5 }}>
                        <Stack spacing={1.25}>
                              <Typography variant="body2" color="text.secondary">
                            Открытый короб:{' '}
                            {openBox
                              ? openBox.internal_barcode ?? `${openBox.id.slice(0, 8)}…`
                              : 'нет'}
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
                              <Stack
                                direction="row"
                                spacing={1}
                                sx={{ flexWrap: 'wrap', gap: 1 }}
                              >
                                {openBox.internal_barcode ? (
                                  <Chip
                                    size="small"
                                    label={`Короб: ${openBox.internal_barcode}`}
                                    data-testid="ff-mp-active-box"
                                  />
                                ) : null}
                                {activePickLocationCode ? (
                                  <Chip
                                    size="small"
                                    label={`Ячейка: ${activePickLocationCode}`}
                                    data-testid="ff-mp-active-location"
                                  />
                                ) : (
                                  <Typography variant="caption" color="warning.main">
                                    Сначала отсканируйте ячейку
                                  </Typography>
                                )}
                              </Stack>
                              <Stack direction={{ xs: 'column', sm: 'row' }} spacing={1}>
                                <TextField
                                  size="small"
                                  label="Штрихкод ячейки / товара"
                                  value={scanBarcode}
                                  onChange={(e) => setScanBarcode(e.target.value)}
                                  onKeyDown={(e) => {
                                    if (e.key === 'Enter') {
                                      e.preventDefault()
                                      void doScan(openBox.id)
                                    }
                                  }}
                                  disabled={modalBusy}
                                  fullWidth
                                  data-testid="ff-mp-pick-scan-input"
                                />
                                <TextField
                                  size="small"
                                  label="Кол-во"
                                  type="number"
                                  value={collectQty}
                                  onChange={(e) => setCollectQty(e.target.value)}
                                  slotProps={{ htmlInput: { min: 1 } }}
                                  sx={{ width: { xs: '100%', sm: 96 } }}
                                  disabled={modalBusy}
                                  data-testid="ff-mp-collect-qty"
                                />
                                <Button
                                  variant="contained"
                                  onClick={() => void doScan(openBox.id)}
                                  disabled={modalBusy}
                                  data-testid="ff-mp-pick-scan"
                                >
                                  Добавить
                                </Button>
                                <Button
                                  variant="outlined"
                                  onClick={() => void closeBox(openBox.id)}
                                  disabled={modalBusy}
                                  data-testid="ff-mp-box-close"
                                >
                                  Закрыть короб
                                </Button>
                              </Stack>
                              <Table size="small" sx={{ mt: 1 }} data-testid="ff-mp-open-box-lines">
                                <TableHead>
                                  <TableRow>
                                    <TableCell>Артикул</TableCell>
                                    <TableCell>Товар</TableCell>
                                    <TableCell align="right">В коробе</TableCell>
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
                                {b.internal_barcode ?? b.id.slice(0, 8)} · {b.box_preset} ·{' '}
                                {b.closed_at ? b.closed_at.slice(0, 19).replace('T', ' ') : '—'}
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

                    {unloadDetail.pick_allocations.length > 0 ? (
                      <Paper variant="outlined" sx={{ p: 1.5 }} data-testid="ff-mp-pick-saved">
                        <Typography variant="subtitle2" sx={{ mb: 1 }}>
                          Откуда сняли (по ячейкам)
                        </Typography>
                        <Table size="small">
                          <TableHead>
                            <TableRow>
                              <TableCell>Товар</TableCell>
                              <TableCell>Ячейка</TableCell>
                              <TableCell align="right">Кол-во</TableCell>
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
          {docModal === 'marketplace_unload' && unloadDetail && unloadDetail.lines.length > 0 ? (
            <Button
              variant="outlined"
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
          ) : null}
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
                (mpCollectSummary?.picked ?? 0) < 1
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
        <DialogTitle>Подбор в текущий короб</DialogTitle>
        <DialogContent dividers>
          <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
            Укажите, сколько снять с каждой ячейки в открытый короб. Можно больше или меньше плана —
            при отгрузке потребуется подтверждение расхождения.
          </Typography>
          <Stack spacing={2}>
            {pickOptions.map((prod) => (
              <Paper key={prod.product_id} variant="outlined" sx={{ p: 1.5 }}>
                <Typography variant="subtitle2">
                  {prod.sku_code} — {prod.product_name}{' '}
                  <Typography component="span" variant="body2" color="text.secondary">
                    (план: {prod.planned_qty}, собрано: {prod.picked_qty})
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
