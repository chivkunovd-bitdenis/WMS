import { useCallback, useEffect, useState } from 'react'
import './App.css'
import { apiUrl } from './api'
import { Navigate, Route, Routes, useLocation, useNavigate } from 'react-router-dom'
import { ProfileLoadingScreen } from './screens/ProfileLoadingScreen'
import { PublicAuthScreen } from './screens/PublicAuthScreen'
import { AuthedAppLayout } from './layouts/AuthedAppLayout'
import { CatalogSection } from './sections/CatalogSection'
import { readApiErrorMessage } from './utils/readApiErrorMessage'
import { useAuth } from './hooks/useAuth'
import { Screen } from './screens/AppV2Screens'
import { ProductsScreen } from './screens/v2/ProductsScreen'
import { SellersScreen } from './screens/v2/SellersScreen'
import { InboundScreen } from './screens/v2/InboundScreen'
import { OutboundScreen } from './screens/v2/OutboundScreen'
import { WildberriesScreen } from './screens/v2/WildberriesScreen'
import { MovementsScreen } from './screens/v2/MovementsScreen'
import { TransfersScreen } from './screens/v2/TransfersScreen'
import {
  AppBar as MuiAppBar,
  Box as MuiBox,
  Dialog,
  IconButton,
  Toolbar as MuiToolbar,
  Typography as MuiTypography,
} from '@mui/material'
import CloseIcon from '@mui/icons-material/Close'
import { FfPackagingPage } from './screens/ff/FfPackagingPage'
import { FfPendingMarkingPage } from './screens/ff/FfPendingMarkingPage'
import { FfDashboard } from './screens/ff/FfDashboard'
import {
  FfSuppliesShipmentsPage,
  type FfDiscrepancyActSummary,
  type FfMarketplaceUnloadSummary,
} from './screens/ff/FfSuppliesShipmentsPage'
import { FfHonestSignPage } from './screens/ff/FfHonestSignPage'
import { HonestSignImportPage } from './screens/shared/HonestSignImportPage'
import { FfHonestSignLedgerPage } from './screens/ff/FfHonestSignLedgerPage'
import { FfReportsPage } from './screens/ff/FfReportsPage'
import { FfHonestSignReprintsPage } from './screens/ff/FfHonestSignReprintsPage'
import { NotificationsPage } from './screens/shared/NotificationsPage'
import { HonestSignPoolPage } from './screens/shared/HonestSignPoolPage'
import { HonestSignProductPage } from './screens/shared/HonestSignProductPage'
import { FfPlaceholderPage } from './screens/ff/FfPlaceholderPage'
import { FfStoragePage } from './screens/ff/FfStoragePage'
import { FfInventoryPage } from './screens/ff/inventory/FfInventoryPage'
import { FfProductsFbsPage } from './screens/ff/products-fbs/FfProductsFbsPage'
import { FfSortingObjectsPage } from './screens/ff/sorting-objects/FfSortingObjectsPage'
import { FfWarehouseMapPage } from './screens/ff/warehouse-map/FfWarehouseMapPage'
import { FfInboundRequestView, type InboundRequestWorkspace } from './screens/ff/FfInboundRequestView'
import { FfInboundQueuePage } from './screens/ff/FfInboundQueuePage'
import { FfProductsCatalogScreen } from './screens/v2/FfProductsCatalogScreen'
import { FfFbsOrdersScreen } from './screens/v2/FfFbsOrdersScreen'
import { FfFbsStockSyncScreen } from './screens/v2/FfFbsStockSyncScreen'
import { FfSettingsScreen } from './screens/ff/FfSettingsScreen'
import { FfBillingScreen } from './screens/ff/FfBillingScreen'
import {
  canAccessFfBlock,
  ffRoleLabel,
  resolveFfPermissions,
} from './utils/ffPermissions'
import { setSeparateMarkingPrintEnabled } from './utils/separateMarkingPrint'
import type { InboundOperationType } from './utils/inboundOperationType'

type WarehouseRow = { id: string; name: string; code: string; is_operational: boolean }
const reportWarehouseOptions = (warehouses: WarehouseRow[]) =>
  warehouses
    .filter((warehouse) => warehouse.is_operational)
    .map((warehouse) => ({ id: warehouse.id, name: warehouse.name }))
type LocationRow = { id: string; code: string; warehouse_id: string; barcode: string }
type ProductRow = {
  id: string
  name: string
  sku_code: string
  length_mm: number | null
  width_mm: number | null
  height_mm: number | null
  volume_liters: number | null
  seller_id: string | null
  seller_name: string | null
  wb_nm_id?: number | null
  wb_vendor_code?: string | null
  ozon_sku?: string | null
  ozon_offer_id?: string | null
  wb_barcodes?: string[]
  wb_primary_barcode?: string | null
}

type SellerRow = { id: string; name: string; ozon_connected?: boolean | null }

type InboundSummaryRow = {
  id: string
  warehouse_id: string
  status: string
  operation_type?: string | null
  document_number?: string | null
  display_number?: string | null
  waybill_number?: string | null
  line_count: number
  goods_qty_total?: number | null
  planned_box_count?: number | null
  actual_box_count?: number | null
  boxes_discrepancy?: boolean
  has_discrepancy?: boolean
  planned_delivery_date: string | null
  seller_id?: string | null
  seller_name?: string | null
  product_names?: string[]
  created_by_seller_id?: string | null
  created_at?: string
  sorting_remaining_qty?: number
}

type InboundLineRow = {
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

type InboundBoxLineRow = {
  id: string
  product_id: string
  sku_code: string
  product_name: string
  quantity: number
}

type InboundBoxRow = {
  id: string
  box_number: number
  internal_barcode: string
  is_open: boolean
  lines: InboundBoxLineRow[]
}

type InboundDetailRow = {
  id: string
  warehouse_id: string
  status: string
  planned_delivery_date: string | null
  planned_box_count?: number | null
  actual_box_count?: number | null
  boxes_discrepancy?: boolean
  has_discrepancy?: boolean
  seller_id?: string | null
  seller_name?: string | null
  created_by_seller_id?: string | null
  boxes?: InboundBoxRow[]
  lines: InboundLineRow[]
}

type InboundMovementRow = {
  id: string
  product_id: string
  storage_location_id: string
  quantity_delta: number
  movement_type: string
  inbound_intake_line_id: string | null
  created_at: string
}

type GlobalMovementRow = {
  id: string
  product_id: string
  sku_code: string
  storage_location_id: string
  quantity_delta: number
  movement_type: string
  created_at: string
}

function FfAccessDeniedPage() {
  return (
    <FfPlaceholderPage
      title="Нет доступа"
      hint="Нет доступа к этому разделу."
      testId="ff-access-denied"
    />
  )
}

function SellerPortalDocumentRedirect() {
  const location = useLocation()

  useEffect(() => {
    window.location.replace(`${location.pathname}${location.search}${location.hash}`)
  }, [location.hash, location.pathname, location.search])

  return <ProfileLoadingScreen loading onLogout={() => window.location.replace('/')} />
}

type OutboundSummaryRow = {
  id: string
  warehouse_id: string
  status: string
  line_count: number
  warehouse_name?: string
  goods_qty_total?: number
  planned_shipment_date?: string | null
  created_at?: string
  marketplace_label?: string
  seller_id?: string | null
  seller_name?: string | null
}

type OutboundLineRow = {
  id: string
  product_id: string
  sku_code: string
  product_name: string
  quantity: number
  shipped_qty: number
  storage_location_id: string | null
  storage_location_code: string | null
}

type OutboundDetailRow = {
  id: string
  warehouse_id: string
  status: string
  planned_shipment_date?: string | null
  lines: OutboundLineRow[]
}

type OutboundMovementRow = {
  id: string
  product_id: string
  storage_location_id: string
  quantity_delta: number
  movement_type: string
  outbound_shipment_line_id: string
  created_at: string
}

type PostedInventoryBalanceRow = {
  product_id: string
  sku_code: string
  product_name: string
  quantity: number
  reserved: number
  available: number
}

// (StockSummaryRow moved into SellerProductsStockScreen)

type WbImportedCardRow = {
  nm_id: number
  vendor_code: string | null
  title: string | null
  updated_at: string
}

type WbImportedSupplyRow = {
  external_key: string
  wb_supply_id: number | null
  wb_preorder_id: number | null
  status_id: number | null
  updated_at: string
}

export default function App() {
  const {
    token,
    me,
    error,
    portalMismatch,
    loading,
    authBusy,
    pendingPasswordSetupEmail,
    onRegister,
    onLogin,
    onSetInitialPassword,
    onCancelPasswordSetup,
    logout,
    reloadMe,
  } = useAuth('fulfillment')
  const navigate = useNavigate()
  const [pendingMpUnloadId, setPendingMpUnloadId] = useState<string | null>(null)
  const [warehouses, setWarehouses] = useState<WarehouseRow[]>([])
  const [selectedWarehouseId, setSelectedWarehouseId] = useState<string | null>(
    null,
  )
  const [locations, setLocations] = useState<LocationRow[]>([])
  const [products, setProducts] = useState<ProductRow[]>([])
  const [sellers, setSellers] = useState<SellerRow[]>([])
  const [catalogError, setCatalogError] = useState<string | null>(null)
  const [catalogBusy, setCatalogBusy] = useState(false)
  const [inboundSummaries, setInboundSummaries] = useState<InboundSummaryRow[]>(
    [],
  )
  const [inboundListLoading, setInboundListLoading] = useState(false)
  const [inboundListError, setInboundListError] = useState<string | null>(null)
  const [selectedInboundId, setSelectedInboundId] = useState<string | null>(
    null,
  )
  const [inboundDetail, setInboundDetail] = useState<InboundDetailRow | null>(
    null,
  )
  const [opsError, setOpsError] = useState<string | null>(null)
  const [opsBusy, setOpsBusy] = useState(false)
  const [inboundRequestLocations, setInboundRequestLocations] = useState<
    LocationRow[]
  >([])
  const [inboundMovements, setInboundMovements] = useState<
    InboundMovementRow[]
  >([])
  const [postedInventoryRows, setPostedInventoryRows] = useState<
    PostedInventoryBalanceRow[]
  >([])
  // Seller stock is loaded by SellerProductsStockScreen directly (WB catalog + summary).
  const [globalMovements, setGlobalMovements] = useState<GlobalMovementRow[]>(
    [],
  )
  const [outboundSummaries, setOutboundSummaries] = useState<
    OutboundSummaryRow[]
  >([])
  const [selectedOutboundId, setSelectedOutboundId] = useState<string | null>(
    null,
  )
  const [outboundDetail, setOutboundDetail] = useState<OutboundDetailRow | null>(
    null,
  )
  const [ffDocModal, setFfDocModal] = useState<null | 'inbound' | 'outbound'>(null)
  const [ffDocDirty, setFfDocDirty] = useState(false)
  const [ffInboundWorkspace, setFfInboundWorkspace] =
    useState<InboundRequestWorkspace>('full')
  const [marketplaceUnloadSummaries, setMarketplaceUnloadSummaries] = useState<
    FfMarketplaceUnloadSummary[]
  >([])
  const [discrepancyActSummaries, setDiscrepancyActSummaries] = useState<
    FfDiscrepancyActSummary[]
  >([])
  const [ffSuppliesNotice, setFfSuppliesNotice] = useState<string | null>(null)
  const [outboundRequestLocations, setOutboundRequestLocations] = useState<
    LocationRow[]
  >([])
  const [outboundMovements, setOutboundMovements] = useState<
    OutboundMovementRow[]
  >([])
  const [backgroundJobStatus, setBackgroundJobStatus] = useState<string | null>(
    null,
  )
  const [backgroundJobResult, setBackgroundJobResult] = useState<string | null>(
    null,
  )
  const [wbSellerId, setWbSellerId] = useState<string | null>(null)
  const [wbHasContentToken, setWbHasContentToken] = useState(false)
  const [wbHasSuppliesToken, setWbHasSuppliesToken] = useState(false)
  const [wbHasMarketplaceToken, setWbHasMarketplaceToken] = useState(false)
  const [wbMarketplaceScopeOk, setWbMarketplaceScopeOk] = useState<boolean | null>(null)
  const [wbTokenUpdatedAt, setWbTokenUpdatedAt] = useState<string | null>(null)
  const [wbTokensBusy, setWbTokensBusy] = useState(false)
  const [wbSyncBusy, setWbSyncBusy] = useState(false)
  const [wbJobStatus, setWbJobStatus] = useState<string | null>(null)
  const [wbJobResult, setWbJobResult] = useState<string | null>(null)
  const [wbImportedCards, setWbImportedCards] = useState<WbImportedCardRow[]>([])
  const [wbImportedSupplies, setWbImportedSupplies] = useState<WbImportedSupplyRow[]>([])
  const [wbSuppliesSyncBusy, setWbSuppliesSyncBusy] = useState(false)
  const [wbSuppliesJobStatus, setWbSuppliesJobStatus] = useState<string | null>(null)
  const [wbSuppliesJobResult, setWbSuppliesJobResult] = useState<string | null>(null)
  const [wbLinkBusy, setWbLinkBusy] = useState(false)

  const authHeaders = useCallback(
    (t: string) => ({ Authorization: `Bearer ${t}` }),
    [],
  )

  const refreshWbImportedCards = useCallback(
    async (t: string, sellerId: string) => {
      try {
        const res = await fetch(
          apiUrl(`/integrations/wildberries/sellers/${sellerId}/imported-cards`),
          { headers: authHeaders(t) },
        )
        if (!res.ok) {
          setWbImportedCards([])
          return
        }
        setWbImportedCards((await res.json()) as WbImportedCardRow[])
      } catch {
        setWbImportedCards([])
      }
    },
    [authHeaders],
  )

  const refreshWbImportedSupplies = useCallback(
    async (t: string, sellerId: string) => {
      try {
        const res = await fetch(
          apiUrl(`/integrations/wildberries/sellers/${sellerId}/imported-supplies`),
          { headers: authHeaders(t) },
        )
        if (!res.ok) {
          setWbImportedSupplies([])
          return
        }
        setWbImportedSupplies((await res.json()) as WbImportedSupplyRow[])
      } catch {
        setWbImportedSupplies([])
      }
    },
    [authHeaders],
  )

  const refreshWarehouses = useCallback(
    async (t: string) => {
      const res = await fetch(apiUrl('/warehouses'), {
        headers: authHeaders(t),
      })
      if (!res.ok) {
        throw new Error(await readApiErrorMessage(res))
      }
      const data = (await res.json()) as WarehouseRow[]
      setWarehouses(data)
      setSelectedWarehouseId((prev) => {
        if (data.length === 0) {
          return null
        }
        if (prev && data.some((w) => w.id === prev)) {
          return prev
        }
        return data[0]!.id
      })
    },
    [authHeaders],
  )

  const refreshLocations = useCallback(
    async (t: string, warehouseId: string) => {
      const res = await fetch(
        apiUrl(`/warehouses/${warehouseId}/locations?exclude_sorting_zone=true`),
        { headers: authHeaders(t) },
      )
      if (!res.ok) {
        throw new Error(await readApiErrorMessage(res))
      }
      setLocations((await res.json()) as LocationRow[])
    },
    [authHeaders],
  )

  const refreshProducts = useCallback(
    async (t: string) => {
      const headers = authHeaders(t)
      const [productsRes, catalogRes] = await Promise.all([
        fetch(apiUrl('/products'), { headers }),
        fetch(apiUrl('/products/ff-catalog'), { headers }),
      ])
      if (!productsRes.ok) {
        throw new Error(await readApiErrorMessage(productsRes))
      }
      const base = (await productsRes.json()) as ProductRow[]
      if (!catalogRes.ok) {
        setProducts(base)
        return
      }
      const catalog = (await catalogRes.json()) as {
        id: string
        wb_barcodes?: string[]
        wb_primary_barcode?: string | null
      }[]
      const barcodesById = new Map(
        catalog.map((r) => [r.id, { wb_barcodes: r.wb_barcodes ?? [], wb_primary_barcode: r.wb_primary_barcode }]),
      )
      setProducts(
        base.map((p) => {
          const wb = barcodesById.get(p.id)
          return wb ? { ...p, ...wb } : p
        }),
      )
    },
    [authHeaders],
  )

  const refreshSellers = useCallback(
    async (t: string) => {
      const res = await fetch(apiUrl('/sellers'), {
        headers: authHeaders(t),
      })
      if (!res.ok) {
        throw new Error(await readApiErrorMessage(res))
      }
      setSellers((await res.json()) as SellerRow[])
    },
    [authHeaders],
  )

  const refreshInboundList = useCallback(
    async (t: string) => {
      setInboundListLoading(true)
      setInboundListError(null)
      try {
        const res = await fetch(apiUrl('/operations/inbound-intake-requests'), {
          headers: authHeaders(t),
        })
        if (!res.ok) {
          throw new Error(await readApiErrorMessage(res))
        }
        setInboundSummaries((await res.json()) as InboundSummaryRow[])
      } catch (e) {
        const message = e instanceof Error ? e.message : 'Не удалось загрузить приёмки.'
        setInboundListError(message)
        throw e
      } finally {
        setInboundListLoading(false)
      }
    },
    [authHeaders],
  )

  const refreshInboundDetail = useCallback(
    async (t: string, requestId: string) => {
      const [dRes, mRes] = await Promise.all([
        fetch(apiUrl(`/operations/inbound-intake-requests/${requestId}`), {
          headers: authHeaders(t),
        }),
        fetch(
          apiUrl(`/operations/inbound-intake-requests/${requestId}/movements`),
          { headers: authHeaders(t) },
        ),
      ])
      if (!dRes.ok) {
        throw new Error(await readApiErrorMessage(dRes))
      }
      setInboundDetail((await dRes.json()) as InboundDetailRow)
      if (mRes.ok) {
        setInboundMovements((await mRes.json()) as InboundMovementRow[])
      } else {
        setInboundMovements([])
      }
    },
    [authHeaders],
  )

  const refreshGlobalMovements = useCallback(
    async (t: string) => {
      const res = await fetch(
        apiUrl('/operations/inventory-movements?limit=80'),
        { headers: authHeaders(t) },
      )
      if (!res.ok) {
        throw new Error(await readApiErrorMessage(res))
      }
      setGlobalMovements((await res.json()) as GlobalMovementRow[])
    },
    [authHeaders],
  )

  const refreshOutboundList = useCallback(
    async (t: string) => {
      const res = await fetch(
        apiUrl('/operations/outbound-shipment-requests'),
        { headers: authHeaders(t) },
      )
      if (!res.ok) {
        throw new Error(await readApiErrorMessage(res))
      }
      setOutboundSummaries((await res.json()) as OutboundSummaryRow[])
    },
    [authHeaders],
  )

  const refreshMarketplaceUnloadList = useCallback(
    async (t: string) => {
      const res = await fetch(apiUrl('/operations/marketplace-unload-requests'), {
        headers: authHeaders(t),
      })
      if (!res.ok) {
        throw new Error(await readApiErrorMessage(res))
      }
      setMarketplaceUnloadSummaries(
        (await res.json()) as FfMarketplaceUnloadSummary[],
      )
    },
    [authHeaders],
  )

  const refreshDiscrepancyActList = useCallback(
    async (t: string) => {
      const res = await fetch(apiUrl('/operations/discrepancy-acts'), {
        headers: authHeaders(t),
      })
      if (!res.ok) {
        throw new Error(await readApiErrorMessage(res))
      }
      setDiscrepancyActSummaries((await res.json()) as FfDiscrepancyActSummary[])
    },
    [authHeaders],
  )

  const refreshOutboundDetail = useCallback(
    async (t: string, requestId: string) => {
      const [dRes, mRes] = await Promise.all([
        fetch(
          apiUrl(`/operations/outbound-shipment-requests/${requestId}`),
          { headers: authHeaders(t) },
        ),
        fetch(
          apiUrl(
            `/operations/outbound-shipment-requests/${requestId}/movements`,
          ),
          { headers: authHeaders(t) },
        ),
      ])
      if (!dRes.ok) {
        throw new Error(await readApiErrorMessage(dRes))
      }
      setOutboundDetail((await dRes.json()) as OutboundDetailRow)
      if (mRes.ok) {
        setOutboundMovements((await mRes.json()) as OutboundMovementRow[])
      } else {
        setOutboundMovements([])
      }
    },
    [authHeaders],
  )

  useEffect(() => {
    if (!token || !me) {
      setWarehouses([])
      setLocations([])
      setProducts([])
      setSellers([])
      setSelectedWarehouseId(null)
      setInboundSummaries([])
      setSelectedInboundId(null)
      setInboundDetail(null)
      setInboundRequestLocations([])
      setInboundMovements([])
      setPostedInventoryRows([])
      setGlobalMovements([])
      setOutboundSummaries([])
      setMarketplaceUnloadSummaries([])
      setDiscrepancyActSummaries([])
      setFfSuppliesNotice(null)
      setSelectedOutboundId(null)
      setOutboundDetail(null)
      setOutboundRequestLocations([])
      setOutboundMovements([])
      setBackgroundJobStatus(null)
      setBackgroundJobResult(null)
      setWbSellerId(null)
      setWbHasContentToken(false)
      setWbHasSuppliesToken(false)
      setWbTokensBusy(false)
      setWbSyncBusy(false)
      setWbJobStatus(null)
      setWbJobResult(null)
      setWbImportedCards([])
      setWbImportedSupplies([])
      setWbSuppliesSyncBusy(false)
      setWbSuppliesJobStatus(null)
      setWbSuppliesJobResult(null)
      setWbLinkBusy(false)
      setCatalogError(null)
      setOpsError(null)
      return
    }
    setCatalogError(null)
    setOpsError(null)
    void (async () => {
      try {
        const canLoadReception = canAccessFfBlock(me.role, me.permissions, 'reception')
        const canLoadMpShipments = canAccessFfBlock(me.role, me.permissions, 'mp_shipments')
        const canLoadPackaging = canAccessFfBlock(me.role, me.permissions, 'packaging')
        const canLoadCells =
          canAccessFfBlock(me.role, me.permissions, 'cells') ||
          canAccessFfBlock(me.role, me.permissions, 'inventory')
        const canLoadWarehouseCatalog =
          me.role === 'fulfillment_admin' ||
          canLoadReception ||
          canLoadMpShipments ||
          canLoadPackaging ||
          canLoadCells
        const canLoadProductCatalog = canLoadWarehouseCatalog
        if (canLoadWarehouseCatalog) {
          await refreshWarehouses(token)
        } else {
          setWarehouses([])
          setSelectedWarehouseId(null)
        }
        if (me.role !== 'fulfillment_admin' && !canLoadCells) {
          setLocations([])
          setSelectedWarehouseId(null)
        }
        if (canLoadProductCatalog) {
          await refreshProducts(token)
          await refreshSellers(token)
        } else {
          setProducts([])
          setSellers([])
        }
      } catch (e) {
        setCatalogError(
          e instanceof Error ? e.message : 'Не удалось загрузить каталог.',
        )
      }
    })()
    void (async () => {
      try {
        const canLoadReception = canAccessFfBlock(me.role, me.permissions, 'reception')
        const canLoadMpShipments = canAccessFfBlock(me.role, me.permissions, 'mp_shipments')
        if (me.role === 'fulfillment_admin' || canLoadReception) {
          await refreshInboundList(token)
        } else {
          setInboundSummaries([])
        }
        if (me.role === 'fulfillment_admin') {
          await refreshOutboundList(token)
          await refreshDiscrepancyActList(token)
          await refreshGlobalMovements(token)
        } else {
          setOutboundSummaries([])
          setDiscrepancyActSummaries([])
          setGlobalMovements([])
        }
        if (me.role === 'fulfillment_admin' || canLoadMpShipments) {
          await refreshMarketplaceUnloadList(token)
        } else {
          setMarketplaceUnloadSummaries([])
        }
      } catch (e) {
        setOpsError(
          e instanceof Error ? e.message : 'Не удалось загрузить заявки.',
        )
      }
    })()
  }, [
    token,
    me,
    refreshWarehouses,
    refreshProducts,
    refreshSellers,
    refreshInboundList,
    refreshOutboundList,
    refreshMarketplaceUnloadList,
    refreshDiscrepancyActList,
    refreshGlobalMovements,
  ])

  useEffect(() => {
    setSeparateMarkingPrintEnabled(me?.separate_marking_print_enabled === true)
  }, [me])

  useEffect(() => {
    if (!token || !selectedInboundId) {
      setInboundDetail(null)
      return
    }
    void (async () => {
      try {
        setOpsError(null)
        await refreshInboundDetail(token, selectedInboundId)
      } catch (e) {
        setOpsError(
          e instanceof Error ? e.message : 'Не удалось загрузить заявку.',
        )
      }
    })()
  }, [token, selectedInboundId, refreshInboundDetail])

  useEffect(() => {
    if (!token || !selectedOutboundId) {
      setOutboundDetail(null)
      return
    }
    void (async () => {
      try {
        setOpsError(null)
        await refreshOutboundDetail(token, selectedOutboundId)
      } catch (e) {
        setOpsError(
          e instanceof Error ? e.message : 'Не удалось загрузить отгрузку.',
        )
      }
    })()
  }, [token, selectedOutboundId, refreshOutboundDetail])

  useEffect(() => {
    if (!token || !outboundDetail?.warehouse_id) {
      setOutboundRequestLocations([])
      return
    }
    void (async () => {
      try {
        const res = await fetch(
          apiUrl(`/warehouses/${outboundDetail.warehouse_id}/locations`),
          { headers: authHeaders(token) },
        )
        if (!res.ok) {
          setOutboundRequestLocations([])
          return
        }
        setOutboundRequestLocations((await res.json()) as LocationRow[])
      } catch {
        setOutboundRequestLocations([])
      }
    })()
  }, [token, outboundDetail?.warehouse_id, authHeaders])

  useEffect(() => {
    setPostedInventoryRows([])
  }, [selectedInboundId])

  useEffect(() => {
    if (ffDocModal !== 'inbound' || !inboundDetail?.warehouse_id) {
      return
    }
    setSelectedWarehouseId(inboundDetail.warehouse_id)
  }, [ffDocModal, inboundDetail?.warehouse_id])

  useEffect(() => {
    if (ffDocModal !== 'outbound' || !outboundDetail?.warehouse_id) {
      return
    }
    setSelectedWarehouseId(outboundDetail.warehouse_id)
  }, [ffDocModal, outboundDetail?.warehouse_id])

  useEffect(() => {
    if (!token || !inboundDetail?.warehouse_id) {
      setInboundRequestLocations([])
      return
    }
    void (async () => {
      try {
        const res = await fetch(
          apiUrl(`/warehouses/${inboundDetail.warehouse_id}/locations`),
          { headers: authHeaders(token) },
        )
        if (!res.ok) {
          setInboundRequestLocations([])
          return
        }
        setInboundRequestLocations((await res.json()) as LocationRow[])
      } catch {
        setInboundRequestLocations([])
      }
    })()
  }, [token, inboundDetail?.warehouse_id, authHeaders])

  useEffect(() => {
    if (
      !token ||
      !selectedWarehouseId ||
      (me?.role !== 'fulfillment_admin' &&
        !canAccessFfBlock(me?.role ?? '', me?.permissions, 'cells'))
    ) {
      setLocations([])
      return
    }
    void (async () => {
      try {
        await refreshLocations(token, selectedWarehouseId)
      } catch (e) {
        setCatalogError(
          e instanceof Error ? e.message : 'Не удалось загрузить ячейки.',
        )
      }
    })()
  }, [token, me?.role, selectedWarehouseId, refreshLocations])

  useEffect(() => {
    if (!me || me.role !== 'fulfillment_admin') {
      setWbSellerId(null)
      return
    }
    if (sellers.length === 0) {
      setWbSellerId(null)
      return
    }
    setWbSellerId((prev) => {
      if (prev && sellers.some((s) => s.id === prev)) {
        return prev
      }
      return sellers[0].id
    })
  }, [me, sellers])

  useEffect(() => {
    if (!token || me?.role !== 'fulfillment_admin' || !wbSellerId) {
      setWbHasContentToken(false)
      setWbHasSuppliesToken(false)
      setWbMarketplaceScopeOk(null)
      setWbTokenUpdatedAt(null)
      return
    }
    let cancelled = false
    void (async () => {
      try {
        const res = await fetch(
          apiUrl(`/integrations/wildberries/sellers/${wbSellerId}/tokens`),
          { headers: authHeaders(token) },
        )
        if (!res.ok || cancelled) {
          return
        }
        const j = (await res.json()) as {
          has_content_token: boolean
          has_supplies_token: boolean
          has_marketplace_token?: boolean
          marketplace_scope_ok?: boolean | null
          updated_at?: string | null
        }
        if (cancelled) {
          return
        }
        setWbHasContentToken(Boolean(j.has_content_token))
        setWbHasSuppliesToken(Boolean(j.has_supplies_token))
        setWbHasMarketplaceToken(Boolean(j.has_marketplace_token))
        setWbMarketplaceScopeOk(j.marketplace_scope_ok ?? null)
        setWbTokenUpdatedAt(j.updated_at ?? null)
      } catch {
        if (!cancelled) {
          setWbHasContentToken(false)
          setWbHasSuppliesToken(false)
          setWbHasMarketplaceToken(false)
          setWbMarketplaceScopeOk(null)
        }
      }
    })()
    return () => {
      cancelled = true
    }
  }, [token, me?.role, wbSellerId, authHeaders])

  useEffect(() => {
    if (!token || me?.role !== 'fulfillment_admin' || !wbSellerId) {
      setWbImportedCards([])
      return
    }
    void refreshWbImportedCards(token, wbSellerId)
  }, [token, me?.role, wbSellerId, refreshWbImportedCards])

  useEffect(() => {
    if (!token || me?.role !== 'fulfillment_admin' || !wbSellerId) {
      setWbImportedSupplies([])
      return
    }
    void refreshWbImportedSupplies(token, wbSellerId)
  }, [token, me?.role, wbSellerId, refreshWbImportedSupplies])

  // Seller stock is loaded by SellerProductsStockScreen directly.

  function onLogout() {
    logout()
    setInboundSummaries([])
    setSelectedInboundId(null)
    setInboundDetail(null)
    setOpsError(null)
    setInboundRequestLocations([])
    setInboundMovements([])
    setPostedInventoryRows([])
    setGlobalMovements([])
    setOutboundSummaries([])
    setSelectedOutboundId(null)
    setOutboundDetail(null)
    setOutboundRequestLocations([])
    setOutboundMovements([])
    setSellers([])
    setBackgroundJobStatus(null)
    setBackgroundJobResult(null)
  }

  async function onCreateWarehouse(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault()
    const form = e.currentTarget
    if (!token) {
      return
    }
    setCatalogError(null)
    setCatalogBusy(true)
    try {
      const fd = new FormData(form)
      const name = String(fd.get('warehouse_name') ?? '').trim()
      const rawCode = String(fd.get('warehouse_code') ?? '').trim()
      const code = rawCode.toLowerCase()
      if (!/^[a-z0-9_-]+$/.test(code)) {
        setCatalogError(
          'Код склада: латиница, цифры, _ и - (например main-wh).',
        )
        return
      }
      const res = await fetch(apiUrl('/warehouses'), {
        method: 'POST',
        headers: {
          ...authHeaders(token),
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ name, code }),
      })
      if (!res.ok) {
        setCatalogError(await readApiErrorMessage(res))
        return
      }
      const created = (await res.json()) as WarehouseRow
      form.reset()
      await refreshWarehouses(token)
      setSelectedWarehouseId(created.id)
    } catch (e) {
      setCatalogError(
        e instanceof Error
          ? e.message
          : 'Сеть: не удалось создать склад.',
      )
    } finally {
      setCatalogBusy(false)
    }
  }

  async function onCreateLocation(body: {
    code?: string
    rack_name?: string
    side?: 1 | 2
    position?: number
  }): Promise<boolean> {
    if (!token || !selectedWarehouseId) {
      return false
    }
    const trimmedCode = body.code?.trim() ?? ''
    const trimmedRack = body.rack_name?.trim() ?? ''
    const hasRack = trimmedRack.length > 0
    if (!hasRack && !trimmedCode) {
      setCatalogError('Укажите стеллаж или код ячейки.')
      return false
    }
    if (hasRack && !body.side) {
      setCatalogError('Укажите сторону (1 или 2).')
      return false
    }
    if (hasRack && !trimmedCode) {
      setCatalogError('Не удалось сформировать название ячейки — проверьте стеллаж и сторону.')
      return false
    }
    setCatalogError(null)
    setCatalogBusy(true)
    try {
      const res = await fetch(
        apiUrl(`/warehouses/${selectedWarehouseId}/locations`),
        {
          method: 'POST',
          headers: {
            ...authHeaders(token),
            'Content-Type': 'application/json',
          },
          body: JSON.stringify(
            hasRack
              ? {
                  rack_name: trimmedRack,
                  side: body.side,
                  position: body.position,
                  code: trimmedCode,
                }
              : { code: trimmedCode },
          ),
        },
      )
      if (!res.ok) {
        const msg = await readApiErrorMessage(res)
        setCatalogError(
          msg.includes('location_code_taken') || msg.includes('already exists')
            ? 'Такой код ячейки уже есть на этом складе.'
            : msg,
        )
        return false
      }
      await refreshLocations(token, selectedWarehouseId)
      return true
    } catch (e) {
      setCatalogError(
        e instanceof Error
          ? e.message
          : 'Сеть: не удалось создать ячейку.',
      )
      return false
    } finally {
      setCatalogBusy(false)
    }
  }

  async function onRenameWarehouse(warehouseId: string, name: string): Promise<boolean> {
    if (!token) {
      return false
    }
    const trimmed = name.trim()
    if (!trimmed) {
      setCatalogError('Укажите название склада.')
      return false
    }
    setCatalogError(null)
    setCatalogBusy(true)
    try {
      const res = await fetch(apiUrl(`/warehouses/${warehouseId}`), {
        method: 'PATCH',
        headers: {
          ...authHeaders(token),
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ name: trimmed }),
      })
      if (!res.ok) {
        setCatalogError(await readApiErrorMessage(res))
        return false
      }
      await refreshWarehouses(token)
      return true
    } catch (e) {
      setCatalogError(e instanceof Error ? e.message : 'Сеть: не удалось переименовать склад.')
      return false
    } finally {
      setCatalogBusy(false)
    }
  }

  async function onDeleteWarehouse(warehouseId: string): Promise<boolean> {
    if (!token) {
      return false
    }
    setCatalogError(null)
    setCatalogBusy(true)
    try {
      const res = await fetch(apiUrl(`/warehouses/${warehouseId}`), {
        method: 'DELETE',
        headers: authHeaders(token),
      })
      if (!res.ok) {
        const msg = await readApiErrorMessage(res)
        setCatalogError(
          msg === 'warehouse_has_documents'
            ? 'Нельзя удалить склад: к нему привязаны документы.'
            : msg === 'warehouse_has_stock'
              ? 'Нельзя удалить склад: на нём есть остатки.'
              : msg === 'warehouse_has_locations'
                ? 'Нельзя удалить склад: сначала удалите обычные ячейки.'
                : msg,
        )
        return false
      }
      await refreshWarehouses(token)
      return true
    } catch (e) {
      setCatalogError(e instanceof Error ? e.message : 'Сеть: не удалось удалить склад.')
      return false
    } finally {
      setCatalogBusy(false)
    }
  }

  async function onRenameLocation(
    warehouseId: string,
    locationId: string,
    code: string,
  ): Promise<boolean> {
    if (!token) {
      return false
    }
    const trimmed = code.trim()
    if (!trimmed) {
      setCatalogError('Укажите код ячейки.')
      return false
    }
    setCatalogError(null)
    setCatalogBusy(true)
    try {
      const res = await fetch(apiUrl(`/warehouses/${warehouseId}/locations/${locationId}`), {
        method: 'PATCH',
        headers: {
          ...authHeaders(token),
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ code: trimmed }),
      })
      if (!res.ok) {
        const msg = await readApiErrorMessage(res)
        setCatalogError(
          msg === 'location_code_taken'
            ? 'Такой код ячейки уже есть на этом складе.'
            : msg === 'system_location_locked'
              ? 'Служебную зону сортировки нельзя переименовать.'
              : msg,
        )
        return false
      }
      await refreshLocations(token, warehouseId)
      return true
    } catch (e) {
      setCatalogError(e instanceof Error ? e.message : 'Сеть: не удалось переименовать ячейку.')
      return false
    } finally {
      setCatalogBusy(false)
    }
  }

  async function onDeleteLocation(
    warehouseId: string,
    locationId: string,
    moveStockTo?: 'sorting' | 'unallocated',
  ): Promise<boolean> {
    if (!token) {
      return false
    }
    setCatalogError(null)
    setCatalogBusy(true)
    try {
      const params = moveStockTo ? `?move_stock_to=${moveStockTo}` : ''
      const res = await fetch(apiUrl(`/warehouses/${warehouseId}/locations/${locationId}${params}`), {
        method: 'DELETE',
        headers: authHeaders(token),
      })
      if (!res.ok) {
        const msg = await readApiErrorMessage(res)
        setCatalogError(
          msg === 'location_has_stock'
            ? 'В ячейке есть товар. Выберите перенос в сортировку или без ячейки.'
            : msg === 'system_location_locked'
              ? 'Служебную зону сортировки нельзя удалить.'
              : msg,
        )
        return false
      }
      await refreshLocations(token, warehouseId)
      return true
    } catch (e) {
      setCatalogError(e instanceof Error ? e.message : 'Сеть: не удалось удалить ячейку.')
      return false
    } finally {
      setCatalogBusy(false)
    }
  }

  async function onLoadLocationBalances(locationId: string): Promise<
    {
      product_id: string
      sku_code: string
      product_name: string
      quantity: number
      reserved: number
      available: number
    }[]
  > {
    if (!token) {
      return []
    }
    try {
      const res = await fetch(
        apiUrl(`/operations/inventory-balances?storage_location_id=${locationId}`),
        { headers: authHeaders(token) },
      )
      if (!res.ok) {
        return []
      }
      return (await res.json()) as {
        product_id: string
        sku_code: string
        product_name: string
        quantity: number
        reserved: number
        available: number
      }[]
    } catch {
      return []
    }
  }

  async function onListWarehouseRacks(warehouseId: string): Promise<string[]> {
    if (!token) {
      return []
    }
    try {
      const res = await fetch(apiUrl(`/warehouses/${warehouseId}/racks`), {
        headers: authHeaders(token),
      })
      if (!res.ok) {
        return []
      }
      const rows = (await res.json()) as { name: string }[]
      return rows.map((r) => r.name)
    } catch {
      return []
    }
  }

  async function onSuggestLocation(
    warehouseId: string,
    rackName: string,
    side: 1 | 2,
  ): Promise<{ position: number; code: string } | null> {
    if (!token) {
      return null
    }
    try {
      const params = new URLSearchParams({ rack_name: rackName, side: String(side) })
      const res = await fetch(apiUrl(`/warehouses/${warehouseId}/locations/suggest?${params}`), {
        headers: authHeaders(token),
      })
      if (!res.ok) {
        return null
      }
      return (await res.json()) as { position: number; code: string }
    } catch {
      return null
    }
  }

  async function onCreateProduct(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault()
    const form = e.currentTarget
    if (!token) {
      return
    }
    setCatalogError(null)
    setCatalogBusy(true)
    try {
      const fd = new FormData(form)
      const name = String(fd.get('product_name') ?? '').trim()
      const sku_code = String(fd.get('product_sku') ?? '').trim()
      const length_mm = Number(fd.get('product_length_mm'))
      const width_mm = Number(fd.get('product_width_mm'))
      const height_mm = Number(fd.get('product_height_mm'))
      const seller_raw = String(fd.get('product_seller_id') ?? '').trim()
      const body: Record<string, unknown> = {
        name,
        sku_code,
        length_mm,
        width_mm,
        height_mm,
      }
      if (seller_raw) {
        body.seller_id = seller_raw
      }
      const res = await fetch(apiUrl('/products'), {
        method: 'POST',
        headers: {
          ...authHeaders(token),
          'Content-Type': 'application/json',
        },
        body: JSON.stringify(body),
      })
      if (!res.ok) {
        setCatalogError(await readApiErrorMessage(res))
        return
      }
      form.reset()
      await refreshProducts(token)
    } catch (e) {
      setCatalogError(
        e instanceof Error
          ? e.message
          : 'Сеть: не удалось создать товар.',
      )
    } finally {
      setCatalogBusy(false)
    }
  }

  async function onCreateInboundRequest(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault()
    const form = e.currentTarget
    if (!token || !me) {
      return
    }
    setOpsError(null)
    setOpsBusy(true)
    try {
      const fd = new FormData(form)
      const whFromForm = String(fd.get('inbound_warehouse_id') ?? '').trim()
      const planned_delivery_date_raw = String(
        fd.get('inbound_planned_delivery_date') ?? '',
      ).trim()
      const planned_delivery_date = planned_delivery_date_raw || null
      const operation_type =
        String(fd.get('inbound_operation_type') ?? 'inbound').trim() || 'inbound'
      const warehouseId =
        whFromForm ||
        selectedWarehouseId ||
        (warehouses.length === 1 ? warehouses[0]!.id : null)
      if (!warehouseId) {
        setOpsError(
          me.role === 'fulfillment_seller' && warehouses.length > 1
            ? 'Выберите склад для новой заявки.'
            : 'Выберите склад в списке выше.',
        )
        return
      }
      const res = await fetch(apiUrl('/operations/inbound-intake-requests'), {
        method: 'POST',
        headers: {
          ...authHeaders(token),
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ warehouse_id: warehouseId, planned_delivery_date, operation_type }),
      })
      if (!res.ok) {
        setOpsError(await readApiErrorMessage(res))
        return
      }
      const created = (await res.json()) as InboundDetailRow
      form.reset()
      await refreshInboundList(token)
      setSelectedInboundId(created.id)
    } catch (e) {
      setOpsError(
        e instanceof Error ? e.message : 'Не удалось создать заявку.',
      )
    } finally {
      setOpsBusy(false)
    }
  }

  async function onAddInboundLine(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault()
    const form = e.currentTarget
    if (!token || !selectedInboundId) {
      return
    }
    setOpsError(null)
    setOpsBusy(true)
    try {
      const fd = new FormData(form)
      const product_id = String(fd.get('inbound_product_id') ?? '')
      const expected_qty = Number(fd.get('inbound_qty'))
      const storage_raw = String(
        fd.get('inbound_line_storage_id') ?? '',
      ).trim()
      const body: Record<string, unknown> = { product_id, expected_qty }
      if (storage_raw) {
        body.storage_location_id = storage_raw
      }
      const res = await fetch(
        apiUrl(
          `/operations/inbound-intake-requests/${selectedInboundId}/lines`,
        ),
        {
          method: 'POST',
          headers: {
            ...authHeaders(token),
            'Content-Type': 'application/json',
          },
          body: JSON.stringify(body),
        },
      )
      if (!res.ok) {
        setOpsError(await readApiErrorMessage(res))
        return
      }
      form.reset()
      await refreshInboundList(token)
      await refreshInboundDetail(token, selectedInboundId)
    } catch (e) {
      setOpsError(
        e instanceof Error ? e.message : 'Не удалось добавить строку.',
      )
    } finally {
      setOpsBusy(false)
    }
  }

  async function onSubmitInboundRequest() {
    if (!token || !selectedInboundId) {
      return
    }
    setOpsError(null)
    setOpsBusy(true)
    try {
      const res = await fetch(
        apiUrl(
          `/operations/inbound-intake-requests/${selectedInboundId}/submit`,
        ),
        {
          method: 'POST',
          headers: authHeaders(token),
        },
      )
      if (!res.ok) {
        setOpsError(await readApiErrorMessage(res))
        return
      }
      await refreshInboundList(token)
      await refreshInboundDetail(token, selectedInboundId)
    } catch (e) {
      setOpsError(
        e instanceof Error ? e.message : 'Не удалось отправить заявку.',
      )
    } finally {
      setOpsBusy(false)
    }
  }

  async function onPrimaryAcceptInboundRequest() {
    if (!token || !selectedInboundId || !inboundDetail) {
      return
    }
    setOpsError(null)
    setOpsBusy(true)
    try {
      const firstLine = inboundDetail.lines[0]
      if (firstLine != null && inboundDetail.status === 'submitted') {
        const patchRes = await fetch(
          apiUrl(
            `/operations/inbound-intake-requests/${selectedInboundId}/lines/${firstLine.id}/actual`,
          ),
          {
            method: 'PATCH',
            headers: {
              ...authHeaders(token),
              'Content-Type': 'application/json',
            },
            body: JSON.stringify({ actual_qty: 0 }),
          },
        )
        if (!patchRes.ok) {
          setOpsError(await readApiErrorMessage(patchRes))
          return
        }
      }
      const boxRes = await fetch(
          apiUrl(`/operations/inbound-intake-requests/${selectedInboundId}/boxes`),
          { method: 'POST', headers: authHeaders(token) },
        )
        if (!boxRes.ok) {
          setOpsError(await readApiErrorMessage(boxRes))
          return
        }
      await refreshInboundList(token)
      await refreshInboundDetail(token, selectedInboundId)
    } catch (e) {
      setOpsError(e instanceof Error ? e.message : 'Не удалось выполнить первичную приёмку.')
    } finally {
      setOpsBusy(false)
    }
  }

  async function onOpenInboundBoxByBarcode(barcode: string) {
    if (!token || !selectedInboundId) {
      return
    }
    setOpsError(null)
    setOpsBusy(true)
    try {
      const res = await fetch(
        apiUrl(`/operations/inbound-intake-requests/${selectedInboundId}/boxes/open`),
        {
          method: 'POST',
          headers: { ...authHeaders(token), 'Content-Type': 'application/json' },
          body: JSON.stringify({ barcode }),
        },
      )
      if (!res.ok) {
        setOpsError(await readApiErrorMessage(res))
        return
      }
      await refreshInboundDetail(token, selectedInboundId)
    } catch (e) {
      setOpsError(e instanceof Error ? e.message : 'Не удалось открыть короб.')
    } finally {
      setOpsBusy(false)
    }
  }

  async function onScanInboundProductBarcode(barcode: string) {
    if (!token || !selectedInboundId) {
      return
    }
    const openBox = inboundDetail?.boxes?.find((b) => b.is_open)
    if (!openBox) {
      setOpsError('Сначала отсканируйте короб (INB-…).')
      return
    }
    setOpsError(null)
    setOpsBusy(true)
    try {
      const res = await fetch(
        apiUrl(
          `/operations/inbound-intake-requests/${selectedInboundId}/boxes/${openBox.id}/scan`,
        ),
        {
          method: 'POST',
          headers: { ...authHeaders(token), 'Content-Type': 'application/json' },
          body: JSON.stringify({ barcode }),
        },
      )
      if (!res.ok) {
        setOpsError(await readApiErrorMessage(res))
        return
      }
      await refreshInboundDetail(token, selectedInboundId)
    } catch (e) {
      setOpsError(e instanceof Error ? e.message : 'Не удалось отсканировать товар.')
    } finally {
      setOpsBusy(false)
    }
  }

  async function onCloseInboundBoxIntake() {
    if (!token || !selectedInboundId) {
      return
    }
    const openBox = inboundDetail?.boxes?.find((b) => b.is_open)
    if (!openBox) {
      return
    }
    setOpsError(null)
    setOpsBusy(true)
    try {
      const res = await fetch(
        apiUrl(
          `/operations/inbound-intake-requests/${selectedInboundId}/boxes/${openBox.id}/close`,
        ),
        { method: 'POST', headers: authHeaders(token) },
      )
      if (!res.ok) {
        setOpsError(await readApiErrorMessage(res))
        return
      }
      await refreshInboundDetail(token, selectedInboundId)
    } catch (e) {
      setOpsError(e instanceof Error ? e.message : 'Не удалось закрыть короб.')
    } finally {
      setOpsBusy(false)
    }
  }

  async function onSetInboundLineActualQty(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault()
    const form = e.currentTarget
    if (!token || !selectedInboundId) {
      return
    }
    const lineId = form.getAttribute('data-line-id')
    if (!lineId) {
      return
    }
    setOpsError(null)
    setOpsBusy(true)
    try {
      const fd = new FormData(form)
      const actual_qty = Number(fd.get('actual_qty'))
      const res = await fetch(
        apiUrl(
          `/operations/inbound-intake-requests/${selectedInboundId}/lines/${lineId}/actual`,
        ),
        {
          method: 'PATCH',
          headers: {
            ...authHeaders(token),
            'Content-Type': 'application/json',
          },
          body: JSON.stringify({ actual_qty }),
        },
      )
      if (!res.ok) {
        setOpsError(await readApiErrorMessage(res))
        return
      }
      await refreshInboundList(token)
      await refreshInboundDetail(token, selectedInboundId)
      form.reset()
    } catch (e) {
      setOpsError(e instanceof Error ? e.message : 'Не удалось сохранить факт.')
    } finally {
      setOpsBusy(false)
    }
  }

  async function onCompleteInboundVerification() {
    if (!token || !selectedInboundId) {
      return
    }
    setOpsError(null)
    setOpsBusy(true)
    try {
      const res = await fetch(
        apiUrl(`/operations/inbound-intake-requests/${selectedInboundId}/verify`),
        { method: 'POST', headers: authHeaders(token) },
      )
      if (!res.ok) {
        setOpsError(await readApiErrorMessage(res))
        return
      }
      await refreshInboundList(token)
      await refreshInboundDetail(token, selectedInboundId)
    } catch (e) {
      setOpsError(e instanceof Error ? e.message : 'Не удалось завершить пересчёт.')
    } finally {
      setOpsBusy(false)
    }
  }

  async function onPostInboundRequest() {
    if (!token || !selectedInboundId) {
      return
    }
    setOpsError(null)
    setOpsBusy(true)
    try {
      const res = await fetch(
        apiUrl(
          `/operations/inbound-intake-requests/${selectedInboundId}/post`,
        ),
        {
          method: 'POST',
          headers: authHeaders(token),
        },
      )
      if (!res.ok) {
        setOpsError(await readApiErrorMessage(res))
        return
      }
      const data = (await res.json()) as InboundDetailRow
      await refreshInboundList(token)
      await refreshInboundDetail(token, selectedInboundId)
      const storageIds = [
        ...new Set(
          data.lines
            .map((l) => l.storage_location_id)
            .filter((x): x is string => Boolean(x)),
        ),
      ]
      const merged: PostedInventoryBalanceRow[] = []
      for (const sid of storageIds) {
        const br = await fetch(
          apiUrl(
            `/operations/inventory-balances?storage_location_id=${encodeURIComponent(sid)}`,
          ),
          { headers: authHeaders(token) },
        )
        if (br.ok) {
          merged.push(...((await br.json()) as PostedInventoryBalanceRow[]))
        }
      }
      setPostedInventoryRows(merged)
      await refreshGlobalMovements(token)
    } catch (e) {
      setOpsError(
        e instanceof Error ? e.message : 'Не удалось провести приёмку.',
      )
    } finally {
      setOpsBusy(false)
    }
  }

  async function onSaveInboundLineStorage(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault()
    const form = e.currentTarget
    if (!token || !selectedInboundId) {
      return
    }
    const lineId = form.getAttribute('data-line-id')
    if (!lineId) {
      return
    }
    setOpsError(null)
    setOpsBusy(true)
    try {
      const fd = new FormData(form)
      const storage_location_id = String(fd.get('line_storage_id') ?? '')
      const res = await fetch(
        apiUrl(
          `/operations/inbound-intake-requests/${selectedInboundId}/lines/${lineId}`,
        ),
        {
          method: 'PATCH',
          headers: {
            ...authHeaders(token),
            'Content-Type': 'application/json',
          },
          body: JSON.stringify({ storage_location_id }),
        },
      )
      if (!res.ok) {
        setOpsError(await readApiErrorMessage(res))
        return
      }
      await refreshInboundDetail(token, selectedInboundId)
      await refreshInboundList(token)
      form.reset()
    } catch (err) {
      setOpsError(
        err instanceof Error ? err.message : 'Не удалось сохранить ячейку.',
      )
    } finally {
      setOpsBusy(false)
    }
  }

  async function onReceiveInboundLine(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault()
    const form = e.currentTarget
    if (!token || !selectedInboundId) {
      return
    }
    const lineId = form.getAttribute('data-line-id')
    if (!lineId) {
      return
    }
    setOpsError(null)
    setOpsBusy(true)
    try {
      const fd = new FormData(form)
      const quantity = Number(fd.get('receive_qty'))
      const res = await fetch(
        apiUrl(
          `/operations/inbound-intake-requests/${selectedInboundId}/lines/${lineId}/receive`,
        ),
        {
          method: 'POST',
          headers: {
            ...authHeaders(token),
            'Content-Type': 'application/json',
          },
          body: JSON.stringify({ quantity }),
        },
      )
      if (!res.ok) {
        setOpsError(await readApiErrorMessage(res))
        return
      }
      const data = (await res.json()) as InboundDetailRow
      await refreshInboundList(token)
      await refreshInboundDetail(token, selectedInboundId)
      const storageIds = [
        ...new Set(
          data.lines
            .map((l) => l.storage_location_id)
            .filter((x): x is string => Boolean(x)),
        ),
      ]
      const merged: PostedInventoryBalanceRow[] = []
      for (const sid of storageIds) {
        const br = await fetch(
          apiUrl(
            `/operations/inventory-balances?storage_location_id=${encodeURIComponent(sid)}`,
          ),
          { headers: authHeaders(token) },
        )
        if (br.ok) {
          merged.push(...((await br.json()) as PostedInventoryBalanceRow[]))
        }
      }
      setPostedInventoryRows(merged)
      await refreshGlobalMovements(token)
      form.reset()
    } catch (err) {
      setOpsError(
        err instanceof Error ? err.message : 'Не удалось принять количество.',
      )
    } finally {
      setOpsBusy(false)
    }
  }

  async function onStockTransfer(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault()
    const form = e.currentTarget
    if (!token) {
      return
    }
    setOpsError(null)
    setOpsBusy(true)
    try {
      const fd = new FormData(form)
      const from_storage_location_id = String(
        fd.get('transfer_from_loc') ?? '',
      )
      const to_storage_location_id = String(fd.get('transfer_to_loc') ?? '')
      const product_id = String(fd.get('transfer_product_id') ?? '')
      const quantity = Number(fd.get('transfer_qty'))
      const res = await fetch(apiUrl('/operations/stock-transfers'), {
        method: 'POST',
        headers: {
          ...authHeaders(token),
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          from_storage_location_id,
          to_storage_location_id,
          product_id,
          quantity,
        }),
      })
      if (!res.ok) {
        setOpsError(await readApiErrorMessage(res))
        return
      }
      form.reset()
      await refreshGlobalMovements(token)
    } catch (err) {
      setOpsError(
        err instanceof Error ? err.message : 'Не удалось переместить остаток.',
      )
    } finally {
      setOpsBusy(false)
    }
  }

  async function onCreateOutboundRequest(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault()
    const form = e.currentTarget
    if (!token || !me) {
      return
    }
    const fd = new FormData(form)
    const whFromForm = String(fd.get('outbound_warehouse_id') ?? '').trim()
    const warehouseId =
      whFromForm ||
      selectedWarehouseId ||
      (warehouses.length === 1 ? warehouses[0]!.id : null)
    if (!warehouseId) {
      setOpsError(
        me.role === 'fulfillment_seller' && warehouses.length > 1
          ? 'Выберите склад для новой заявки на отгрузку.'
          : 'Выберите склад в каталоге.',
      )
      return
    }
    setOpsError(null)
    setOpsBusy(true)
    try {
      const res = await fetch(
        apiUrl('/operations/outbound-shipment-requests'),
        {
          method: 'POST',
          headers: {
            ...authHeaders(token),
            'Content-Type': 'application/json',
          },
          body: JSON.stringify({ warehouse_id: warehouseId }),
        },
      )
      if (!res.ok) {
        setOpsError(await readApiErrorMessage(res))
        return
      }
      const created = (await res.json()) as OutboundDetailRow
      await refreshOutboundList(token)
      setSelectedOutboundId(created.id)
    } catch (err) {
      setOpsError(
        err instanceof Error ? err.message : 'Не удалось создать отгрузку.',
      )
    } finally {
      setOpsBusy(false)
    }
  }

  async function onAddOutboundLine(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault()
    const form = e.currentTarget
    if (!token || !selectedOutboundId) {
      return
    }
    setOpsError(null)
    setOpsBusy(true)
    try {
      const fd = new FormData(form)
      const product_id = String(fd.get('outbound_product_id') ?? '')
      const quantity = Number(fd.get('outbound_qty'))
      const storage_raw = String(
        fd.get('outbound_line_storage_id') ?? '',
      ).trim()
      const body: Record<string, unknown> = { product_id, quantity }
      if (storage_raw) {
        body.storage_location_id = storage_raw
      }
      const res = await fetch(
        apiUrl(
          `/operations/outbound-shipment-requests/${selectedOutboundId}/lines`,
        ),
        {
          method: 'POST',
          headers: {
            ...authHeaders(token),
            'Content-Type': 'application/json',
          },
          body: JSON.stringify(body),
        },
      )
      if (!res.ok) {
        setOpsError(await readApiErrorMessage(res))
        return
      }
      form.reset()
      await refreshOutboundList(token)
      await refreshOutboundDetail(token, selectedOutboundId)
    } catch (err) {
      setOpsError(
        err instanceof Error ? err.message : 'Не удалось добавить строку.',
      )
    } finally {
      setOpsBusy(false)
    }
  }

  async function onDeleteOutboundLine(lineId: string) {
    if (!token || !selectedOutboundId) {
      return
    }
    setOpsError(null)
    setOpsBusy(true)
    try {
      const res = await fetch(
        apiUrl(
          `/operations/outbound-shipment-requests/${selectedOutboundId}/lines/${lineId}`,
        ),
        { method: 'DELETE', headers: authHeaders(token) },
      )
      if (!res.ok) {
        setOpsError(await readApiErrorMessage(res))
        return
      }
      await refreshOutboundList(token)
      await refreshOutboundDetail(token, selectedOutboundId)
    } catch (err) {
      setOpsError(
        err instanceof Error ? err.message : 'Не удалось удалить строку.',
      )
    } finally {
      setOpsBusy(false)
    }
  }

  async function onSubmitOutboundRequest() {
    if (!token || !selectedOutboundId) {
      return
    }
    setOpsError(null)
    setOpsBusy(true)
    try {
      const res = await fetch(
        apiUrl(
          `/operations/outbound-shipment-requests/${selectedOutboundId}/submit`,
        ),
        { method: 'POST', headers: authHeaders(token) },
      )
      if (!res.ok) {
        setOpsError(await readApiErrorMessage(res))
        return
      }
      await refreshOutboundList(token)
      await refreshOutboundDetail(token, selectedOutboundId)
    } catch (err) {
      setOpsError(
        err instanceof Error ? err.message : 'Не удалось отправить отгрузку.',
      )
    } finally {
      setOpsBusy(false)
    }
  }

  async function onSaveOutboundLineStorage(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault()
    const form = e.currentTarget
    if (!token || !selectedOutboundId) {
      return
    }
    const lineId = form.getAttribute('data-line-id')
    if (!lineId) {
      return
    }
    setOpsError(null)
    setOpsBusy(true)
    try {
      const fd = new FormData(form)
      const storage_location_id = String(fd.get('out_line_storage_id') ?? '')
      const res = await fetch(
        apiUrl(
          `/operations/outbound-shipment-requests/${selectedOutboundId}/lines/${lineId}`,
        ),
        {
          method: 'PATCH',
          headers: {
            ...authHeaders(token),
            'Content-Type': 'application/json',
          },
          body: JSON.stringify({ storage_location_id }),
        },
      )
      if (!res.ok) {
        setOpsError(await readApiErrorMessage(res))
        return
      }
      await refreshOutboundDetail(token, selectedOutboundId)
      await refreshOutboundList(token)
      form.reset()
    } catch (err) {
      setOpsError(
        err instanceof Error ? err.message : 'Не удалось сохранить ячейку.',
      )
    } finally {
      setOpsBusy(false)
    }
  }

  async function onShipOutboundLine(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault()
    const form = e.currentTarget
    if (!token || !selectedOutboundId) {
      return
    }
    const lineId = form.getAttribute('data-line-id')
    if (!lineId) {
      return
    }
    setOpsError(null)
    setOpsBusy(true)
    try {
      const fd = new FormData(form)
      const quantity = Number(fd.get('ship_qty'))
      const res = await fetch(
        apiUrl(
          `/operations/outbound-shipment-requests/${selectedOutboundId}/lines/${lineId}/ship`,
        ),
        {
          method: 'POST',
          headers: {
            ...authHeaders(token),
            'Content-Type': 'application/json',
          },
          body: JSON.stringify({ quantity }),
        },
      )
      if (!res.ok) {
        setOpsError(await readApiErrorMessage(res))
        return
      }
      await refreshOutboundList(token)
      await refreshOutboundDetail(token, selectedOutboundId)
      await refreshGlobalMovements(token)
      form.reset()
    } catch (err) {
      setOpsError(
        err instanceof Error ? err.message : 'Не удалось отгрузить количество.',
      )
    } finally {
      setOpsBusy(false)
    }
  }

  async function onPostOutboundRequest() {
    if (!token || !selectedOutboundId) {
      return
    }
    setOpsError(null)
    setOpsBusy(true)
    try {
      const res = await fetch(
        apiUrl(
          `/operations/outbound-shipment-requests/${selectedOutboundId}/post`,
        ),
        { method: 'POST', headers: authHeaders(token) },
      )
      if (!res.ok) {
        setOpsError(await readApiErrorMessage(res))
        return
      }
      await refreshOutboundList(token)
      await refreshOutboundDetail(token, selectedOutboundId)
      await refreshGlobalMovements(token)
    } catch (err) {
      setOpsError(
        err instanceof Error ? err.message : 'Не удалось провести отгрузку.',
      )
    } finally {
      setOpsBusy(false)
    }
  }

  async function onRefreshGlobalMovementsClick() {
    if (!token) {
      return
    }
    setOpsError(null)
    try {
      await refreshGlobalMovements(token)
    } catch (err) {
      setOpsError(
        err instanceof Error
          ? err.message
          : 'Не удалось обновить журнал движений.',
      )
    }
  }

  async function onStartMovementsDigestJob() {
    if (!token) {
      return
    }
    setOpsError(null)
    setOpsBusy(true)
    setBackgroundJobStatus('pending')
    setBackgroundJobResult(null)
    try {
      const res = await fetch(apiUrl('/operations/background-jobs'), {
        method: 'POST',
        headers: {
          ...authHeaders(token),
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ job_type: 'movements_digest' }),
      })
      if (!res.ok) {
        setOpsError(await readApiErrorMessage(res))
        setBackgroundJobStatus(null)
        return
      }
      const started = (await res.json()) as { id: string; status: string }
      const jobId = started.id
      setBackgroundJobStatus(started.status)
      for (let i = 0; i < 60; i++) {
        await new Promise((r) => setTimeout(r, 200))
        const st = await fetch(
          apiUrl(`/operations/background-jobs/${jobId}`),
          { headers: authHeaders(token) },
        )
        if (!st.ok) {
          continue
        }
        const j = (await st.json()) as {
          status: string
          result_json: { total_movements?: number } | null
          error_message: string | null
        }
        setBackgroundJobStatus(j.status)
        if (j.status === 'done') {
          const n = j.result_json?.total_movements ?? 0
          setBackgroundJobResult(`Всего движений: ${n}`)
          await refreshGlobalMovements(token)
          break
        }
        if (j.status === 'failed') {
          setBackgroundJobResult(j.error_message ?? 'failed')
          break
        }
      }
    } catch (err) {
      setOpsError(
        err instanceof Error ? err.message : 'Не удалось выполнить задачу.',
      )
      setBackgroundJobStatus(null)
    } finally {
      setOpsBusy(false)
    }
  }

  async function onSaveWbTokens(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault()
    if (!token || !wbSellerId) {
      return
    }
    const form = e.currentTarget
    setWbTokensBusy(true)
    setOpsError(null)
    try {
      const fd = new FormData(form)
      const content = String(fd.get('wb_content_token') ?? '').trim()
      const supplies = String(fd.get('wb_supplies_token') ?? '').trim()
      const marketplace = String(fd.get('wb_marketplace_token') ?? '').trim()
      const body: Record<string, string> = {}
      if (content) {
        body.content_api_token = content
      }
      if (supplies) {
        body.supplies_api_token = supplies
      }
      if (marketplace) {
        body.marketplace_api_token = marketplace
      }
      if (Object.keys(body).length === 0) {
        setOpsError('Укажите хотя бы один токен для сохранения.')
        return
      }
      const res = await fetch(
        apiUrl(`/integrations/wildberries/sellers/${wbSellerId}/tokens`),
        {
          method: 'PATCH',
          headers: {
            ...authHeaders(token),
            'Content-Type': 'application/json',
          },
          body: JSON.stringify(body),
        },
      )
      if (!res.ok) {
        setOpsError(await readApiErrorMessage(res))
        return
      }
      const j = (await res.json()) as {
        has_content_token: boolean
        has_supplies_token: boolean
        has_marketplace_token?: boolean
        marketplace_scope_ok?: boolean | null
        updated_at?: string | null
      }
      setWbHasContentToken(Boolean(j.has_content_token))
      setWbHasSuppliesToken(Boolean(j.has_supplies_token))
      setWbHasMarketplaceToken(Boolean(j.has_marketplace_token))
      setWbMarketplaceScopeOk(j.marketplace_scope_ok ?? null)
      setWbTokenUpdatedAt(j.updated_at ?? null)
      form.reset()
    } catch (err) {
      setOpsError(
        err instanceof Error ? err.message : 'Не удалось сохранить токены WB.',
      )
    } finally {
      setWbTokensBusy(false)
    }
  }

  // Аварийная кнопка: стереть отдельный маркетплейс-токен, чтобы бэкенд снова
  // взял единый ключ (`token = marketplace or content`). Понадобилась после того,
  // как в этом слоте на стенде обнаружился мусор, который иначе нечем перебить.
  async function onClearWbMarketplaceToken() {
    if (!token || !wbSellerId) {
      return
    }
    setWbTokensBusy(true)
    setOpsError(null)
    try {
      const res = await fetch(
        apiUrl(`/integrations/wildberries/sellers/${wbSellerId}/tokens`),
        {
          method: 'PATCH',
          headers: {
            ...authHeaders(token),
            'Content-Type': 'application/json',
          },
          body: JSON.stringify({ marketplace_api_token: null }),
        },
      )
      if (!res.ok) {
        setOpsError(await readApiErrorMessage(res))
        return
      }
      const j = (await res.json()) as {
        has_marketplace_token?: boolean
        marketplace_scope_ok?: boolean | null
        updated_at?: string | null
      }
      setWbHasMarketplaceToken(Boolean(j.has_marketplace_token))
      setWbMarketplaceScopeOk(j.marketplace_scope_ok ?? null)
      setWbTokenUpdatedAt(j.updated_at ?? null)
    } catch (err) {
      setOpsError(
        err instanceof Error ? err.message : 'Не удалось стереть маркетплейс-токен WB.',
      )
    } finally {
      setWbTokensBusy(false)
    }
  }

  async function onStartWbCardsSyncJob() {
    if (!token || !wbSellerId) {
      return
    }
    setOpsError(null)
    setWbSyncBusy(true)
    setWbJobStatus('pending')
    setWbJobResult(null)
    try {
      const res = await fetch(apiUrl('/operations/background-jobs'), {
        method: 'POST',
        headers: {
          ...authHeaders(token),
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          job_type: 'wildberries_cards_sync',
          seller_id: wbSellerId,
        }),
      })
      if (!res.ok) {
        setOpsError(await readApiErrorMessage(res))
        setWbJobStatus(null)
        return
      }
      const started = (await res.json()) as { id: string; status: string }
      const jobId = started.id
      setWbJobStatus(started.status)
      for (let i = 0; i < 60; i++) {
        await new Promise((r) => setTimeout(r, 200))
        const st = await fetch(apiUrl(`/operations/background-jobs/${jobId}`), {
          headers: authHeaders(token),
        })
        if (!st.ok) {
          continue
        }
        const j = (await st.json()) as {
          status: string
          result_json: { cards_received?: number } | null
          error_message: string | null
        }
        setWbJobStatus(j.status)
        if (j.status === 'done') {
          const n = j.result_json?.cards_received ?? 0
          setWbJobResult(`Карточек получено: ${n}`)
          await refreshWbImportedCards(token, wbSellerId)
          break
        }
        if (j.status === 'failed') {
          setWbJobResult(j.error_message ?? 'failed')
          break
        }
      }
    } catch (err) {
      setOpsError(
        err instanceof Error ? err.message : 'Не удалось запустить синхронизацию WB.',
      )
      setWbJobStatus(null)
    } finally {
      setWbSyncBusy(false)
    }
  }

  async function onStartWbSuppliesSyncJob() {
    if (!token || !wbSellerId) {
      return
    }
    setOpsError(null)
    setWbSuppliesSyncBusy(true)
    setWbSuppliesJobStatus('pending')
    setWbSuppliesJobResult(null)
    try {
      const res = await fetch(apiUrl('/operations/background-jobs'), {
        method: 'POST',
        headers: {
          ...authHeaders(token),
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          job_type: 'wildberries_supplies_sync',
          seller_id: wbSellerId,
        }),
      })
      if (!res.ok) {
        setOpsError(await readApiErrorMessage(res))
        setWbSuppliesJobStatus(null)
        return
      }
      const started = (await res.json()) as { id: string; status: string }
      const jobId = started.id
      setWbSuppliesJobStatus(started.status)
      for (let i = 0; i < 60; i++) {
        await new Promise((r) => setTimeout(r, 200))
        const st = await fetch(apiUrl(`/operations/background-jobs/${jobId}`), {
          headers: authHeaders(token),
        })
        if (!st.ok) {
          continue
        }
        const j = (await st.json()) as {
          status: string
          result_json: {
            supplies_received?: number
            supplies_saved?: number
          } | null
          error_message: string | null
        }
        setWbSuppliesJobStatus(j.status)
        if (j.status === 'done') {
          const got = j.result_json?.supplies_received ?? 0
          const saved = j.result_json?.supplies_saved ?? 0
          setWbSuppliesJobResult(`Поставок получено: ${got}, сохранено: ${saved}`)
          await refreshWbImportedSupplies(token, wbSellerId)
          break
        }
        if (j.status === 'failed') {
          setWbSuppliesJobResult(j.error_message ?? 'failed')
          break
        }
      }
    } catch (err) {
      setOpsError(
        err instanceof Error
          ? err.message
          : 'Не удалось запустить синхронизацию поставок WB.',
      )
      setWbSuppliesJobStatus(null)
    } finally {
      setWbSuppliesSyncBusy(false)
    }
  }

  async function onLinkProductToWb(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault()
    if (!token || !wbSellerId) {
      return
    }
    const form = e.currentTarget
    const fd = new FormData(form)
    const productId = String(fd.get('wb_link_product_id') ?? '').trim()
    const nmRaw = String(fd.get('wb_link_nm_id') ?? '').trim()
    setOpsError(null)
    setCatalogError(null)
    if (!productId) {
      setOpsError('Выберите товар для привязки.')
      return
    }
    const nm = Number(nmRaw)
    if (!Number.isInteger(nm) || nm < 1) {
      setOpsError('Укажите целый nm_id ≥ 1.')
      return
    }
    setWbLinkBusy(true)
    try {
      const res = await fetch(
        apiUrl(`/integrations/wildberries/sellers/${wbSellerId}/link-product`),
        {
          method: 'POST',
          headers: {
            ...authHeaders(token),
            'Content-Type': 'application/json',
          },
          body: JSON.stringify({ product_id: productId, nm_id: nm }),
        },
      )
      if (!res.ok) {
        setOpsError(await readApiErrorMessage(res))
        return
      }
      await refreshProducts(token)
      form.reset()
    } catch (err) {
      setOpsError(
        err instanceof Error ? err.message : 'Не удалось привязать товар к WB.',
      )
    } finally {
      setWbLinkBusy(false)
    }
  }

  const onCreateFfMpShipment = useCallback(async (
    sellerId: string,
    marketplace: 'wb' | 'ozon',
  ): Promise<{ id: string } | null> => {
    if (!token) {
      return null
    }
    if (!sellerId) {
      setOpsError('Выберите селлера (ИП) для отгрузки.')
      return null
    }
    let wid: string | null = selectedWarehouseId ?? warehouses[0]?.id ?? null
    if (!wid) {
      try {
        const res = await fetch(apiUrl('/warehouses'), {
          headers: authHeaders(token),
        })
        if (res.ok) {
          const list = (await res.json()) as WarehouseRow[]
          wid = list[0]?.id ?? null
        }
      } catch {
        wid = null
      }
    }
    if (!wid) {
      setOpsError('Сначала создайте склад в каталоге.')
      return null
    }
    setFfSuppliesNotice(null)
    setOpsError(null)
    setOpsBusy(true)
    try {
      if (marketplace === 'wb') {
        const tokRes = await fetch(
          apiUrl(`/integrations/wildberries/sellers/${sellerId}/tokens`),
          {
            method: 'PATCH',
            headers: {
              ...authHeaders(token),
              'Content-Type': 'application/json',
            },
            body: JSON.stringify({ supplies_api_token: 'ff-mp-shipment-token' }),
          },
        )
        if (!tokRes.ok) {
          setOpsError(await readApiErrorMessage(tokRes))
          return null
        }
      }

      // WB MP warehouse may be unavailable (no supplies token / not imported yet).
      // We still allow creating a draft and selecting WB warehouse later.
      type WbMpRow = { wb_warehouse_id: number }
      let wbMpId: number | null = null
      if (marketplace === 'wb') {
        try {
          const whRes = await fetch(apiUrl('/operations/wb-mp-warehouses'), {
            headers: authHeaders(token),
          })
          if (whRes.ok) {
            const rows = (await whRes.json()) as WbMpRow[]
            wbMpId = rows[0]?.wb_warehouse_id ?? null
          }
        } catch {
          wbMpId = null
        }
      }

      const res = await fetch(apiUrl('/operations/marketplace-unload-requests'), {
        method: 'POST',
        headers: {
          ...authHeaders(token),
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          warehouse_id: wid,
          seller_id: sellerId,
          marketplace,
          ...(wbMpId != null ? { wb_mp_warehouse_id: wbMpId } : { wb_mp_warehouse_id: null }),
        }),
      })
      if (!res.ok) {
        setOpsError(await readApiErrorMessage(res))
        return null
      }
      const created = (await res.json()) as { id: string }
      await refreshMarketplaceUnloadList(token)
      setFfSuppliesNotice(
        marketplace === 'ozon'
          ? 'Отгрузка Ozon создана (черновик). Состав по строкам — на следующем этапе.'
          : wbMpId == null
            ? 'Отгрузка на маркетплейс создана (черновик). Выберите склад WB в документе, когда они подгрузятся.'
            : 'Отгрузка на маркетплейс создана (черновик). Состав по строкам — на следующем этапе.',
      )
      return created
    } catch (e) {
      setOpsError(
        e instanceof Error ? e.message : 'Не удалось создать отгрузку на МП.',
      )
      return null
    } finally {
      setOpsBusy(false)
    }
  }, [
    token,
    selectedWarehouseId,
    warehouses,
    authHeaders,
    refreshMarketplaceUnloadList,
  ])

  const onCreateFfInboundDraft = useCallback(async (
    operationType: InboundOperationType, sellerId: string, marketplace?: 'wildberries' | 'ozon',
  ): Promise<{ id: string } | null> => {
    if (!token) {
      return null
    }
    const wid = selectedWarehouseId ?? warehouses[0]?.id ?? null
    if (!wid) {
      setOpsError('Склад ФФ не найден.')
      return null
    }
    if (!sellerId) {
      setOpsError('Выберите селлера для документа.')
      return null
    }
    setFfSuppliesNotice(null)
    setOpsError(null)
    setOpsBusy(true)
    try {
      const res = await fetch(apiUrl('/operations/inbound-intake-requests'), {
        method: 'POST',
        headers: {
          ...authHeaders(token),
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          warehouse_id: wid,
          operation_type: operationType,
          seller_id: sellerId,
          ...(operationType === 'return' && marketplace ? { marketplace } : {}),
        }),
      })
      if (!res.ok) {
        setOpsError(await readApiErrorMessage(res))
        return null
      }
      const created = (await res.json()) as { id: string }
      await refreshInboundList(token)
      return created
    } catch (e) {
      setOpsError(
        e instanceof Error
          ? e.message
          : operationType === 'return'
            ? 'Не удалось создать возврат.'
            : 'Не удалось создать приёмку.',
      )
      return null
    } finally {
      setOpsBusy(false)
    }
  }, [authHeaders, refreshInboundList, selectedWarehouseId, token, warehouses])

  const onCreateFfDiscrepancyAct = useCallback(async (): Promise<{ id: string } | null> => {
    if (!token) {
      return null
    }
    setFfSuppliesNotice(null)
    setOpsError(null)
    setOpsBusy(true)
    try {
      const res = await fetch(apiUrl('/operations/discrepancy-acts'), {
        method: 'POST',
        headers: {
          ...authHeaders(token),
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({}),
      })
      if (!res.ok) {
        setOpsError(await readApiErrorMessage(res))
        return null
      }
      const created = (await res.json()) as { id: string }
      await refreshDiscrepancyActList(token)
      setFfSuppliesNotice('Акт расхождения создан (черновик). Добавьте строки и передайте на FF.')
      return created
    } catch (e) {
      setOpsError(
        e instanceof Error ? e.message : 'Не удалось создать акт расхождения.',
      )
      return null
    } finally {
      setOpsBusy(false)
    }
  }, [token, authHeaders, refreshDiscrepancyActList])

  const closeFfDocument = useCallback(() => {
    if (ffDocDirty && !window.confirm('Закрыть без сохранения?')) {
      return
    }
    setFfDocDirty(false)
    setFfDocModal(null)
    setSelectedInboundId(null)
    setSelectedOutboundId(null)
    setFfInboundWorkspace('full')
    if (token) {
      void refreshInboundList(token)
    }
  }, [ffDocDirty, refreshInboundList, token])

  const rootElement = (() => {
    if (!token) {
      return (
        <PublicAuthScreen
          variant="fulfillment"
          error={portalMismatch ?? error}
          authBusy={authBusy}
          pendingPasswordSetupEmail={pendingPasswordSetupEmail}
          onRegister={(e) => void onRegister(e)}
          onLogin={(e) => void onLogin(e)}
          onSetInitialPassword={(e) => void onSetInitialPassword(e)}
          onCancelPasswordSetup={onCancelPasswordSetup}
        />
      )
    }
    if (token && !me) {
      return <ProfileLoadingScreen loading={loading} onLogout={onLogout} />
    }
    if (!me) {
      return null
    }

    const isFulfillmentAdmin = me.role === 'fulfillment_admin'
    const isFulfillmentSeller = me.role === 'fulfillment_seller'
    const ffPermissions = resolveFfPermissions(me.role, me.permissions)
    const canMpShipmentOps =
      isFulfillmentAdmin || canAccessFfBlock(me.role, me.permissions, 'mp_shipments')
    const canPackagingOps =
      isFulfillmentAdmin || canAccessFfBlock(me.role, me.permissions, 'packaging')
    const canShiftLeadOps = canAccessFfBlock(me.role, me.permissions, 'shift_lead')
    const canReceptionOps = canAccessFfBlock(me.role, me.permissions, 'reception')
    const canInventoryOps = canAccessFfBlock(me.role, me.permissions, 'inventory')
    const canCellsOps = canAccessFfBlock(me.role, me.permissions, 'cells') || canInventoryOps
    const canSettingsOps = isFulfillmentAdmin || canAccessFfBlock(me.role, me.permissions, 'settings')
    const portal: 'seller' | 'ff' = 'ff'
    const base = '/app/ff'
    const ffAccessDenied = <FfAccessDeniedPage />

    // seller stock should always be available on products tab
    // (refreshed lazily by screens via this helper)

    const v2 = (
      <AuthedAppLayout
        onLogout={onLogout}
        title="Портал ФФ"
        userLabel={me.email}
        userRoleLabel={ffRoleLabel(me.role)}
        meRole={me.role}
        ffPermissions={ffPermissions}
        portal={portal} addressStorageEnabled={me.address_storage_enabled !== false}
      >
        <>
        <Routes>
          <Route index element={<Navigate to={`${base}/dashboard`} replace />} />
          <Route
            path="dashboard"
            element={<Navigate to={`${base}/dashboard`} replace />}
          />

          <Route
            path="ff/dashboard"
            element={
              <FfDashboard
                me={me}
                token={token}
                authHeaders={authHeaders}
                isFulfillmentAdmin={isFulfillmentAdmin}
                inboundSummaries={inboundSummaries}
                outboundSummaries={outboundSummaries}
                mpUnloadSummaries={marketplaceUnloadSummaries
                  .filter((r) => r.status === 'submitted')
                  .map((r) => ({
                    id: r.id,
                    status: r.status,
                    line_count: r.line_count,
                    planned_shipment_date: r.planned_shipment_date ?? null,
                    created_at: r.created_at,
                    warehouse_name: r.warehouse_name,
                    seller_name: r.seller_name,
                    marketplace_label:
                      r.marketplace === 'ozon' ? 'Ozon' : 'Wildberries',
                    goods_qty_total: r.line_count,
                  }))}
                onOpenInbound={(id) => {
                  setSelectedOutboundId(null)
                  setSelectedInboundId(id)
                  setFfInboundWorkspace('full')
                  setFfDocModal('inbound')
                }}
                onOpenOutbound={(id) => {
                  setPendingMpUnloadId(null)
                  setSelectedInboundId(null)
                  setSelectedOutboundId(id)
                  setFfDocModal('outbound')
                }}
                onOpenMarketplaceUnload={(id) => {
                  setPendingMpUnloadId(id)
                  navigate(`${base}/ff/mp-shipments`)
                }}
                onOpenFbsSupply={(id) => {
                  navigate(`${base}/fbs?supply_id=${id}`)
                }}
              />
            }
          />

          <Route
            path="ff/supplies-shipments"
            element={<Navigate to={`${base}/reception`} replace />}
          />

          <Route
            path="ff/mp-shipments"
            element={
              token && canMpShipmentOps ? (
                <FfSuppliesShipmentsPage
                  pageVariant="mp-shipments"
                  busy={opsBusy}
                  error={opsError}
                  infoNotice={ffSuppliesNotice}
                  onDismissInfoNotice={() => setFfSuppliesNotice(null)}
                  token={token}
                  addressStorageEnabled={me?.address_storage_enabled !== false}
                  sellers={sellers.map((s) => ({ id: s.id, name: s.name }))}
                  productPicklist={products.map((p) => ({
                    id: p.id,
                    sku_code: p.sku_code,
                    name: p.name,
                  }))}
                  onRefreshFfSupplyExtras={async () => {
                    if (!token) {
                      return
                    }
                    await refreshMarketplaceUnloadList(token)
                    await refreshDiscrepancyActList(token)
                  }}
                  inboundSummaries={inboundSummaries}
                  outboundSummaries={outboundSummaries}
                  marketplaceUnloadSummaries={marketplaceUnloadSummaries}
                  discrepancyActSummaries={discrepancyActSummaries}
                  initialMarketplaceUnloadId={pendingMpUnloadId}
                  onInitialMarketplaceUnloadOpened={() => setPendingMpUnloadId(null)}
                  onOpenInbound={(id) => {
                    setSelectedOutboundId(null)
                    setSelectedInboundId(id)
                    setFfInboundWorkspace('full')
                    setFfDocModal('inbound')
                  }}
                  onOpenOutbound={(id) => {
                    setSelectedInboundId(null)
                    setSelectedOutboundId(id)
                    setFfDocModal('outbound')
                  }}
                  onCreateMpShipment={onCreateFfMpShipment}
                  onCreateDiverge={onCreateFfDiscrepancyAct}
                />
              ) : (
                ffAccessDenied
              )
            }
          />

          <Route
            path="ff/reception"
            element={
              token && canReceptionOps ? (
                <FfInboundQueuePage
                  addressStorageEnabled={me.address_storage_enabled !== false} workspace="reception"
                  rows={inboundSummaries}
                  creatingDraft={opsBusy}
                  sellers={sellers.map((s) => ({ id: s.id, name: s.name }))}
                  loading={inboundListLoading}
                  error={inboundListError}
                  onRetry={async () => {
                    if (token) {
                      await refreshInboundList(token)
                    }
                  }}
                  onCreateDraft={async (operationType, sellerId, marketplace) => {
                    const created = await onCreateFfInboundDraft(operationType, sellerId, marketplace)
                    if (!created?.id) {
                      return
                    }
                    setSelectedOutboundId(null)
                    setSelectedInboundId(created.id)
                    setFfInboundWorkspace('reception')
                    setFfDocModal('inbound')
                  }}
                  onOpen={(id) => {
                    setSelectedOutboundId(null)
                    setSelectedInboundId(id)
                    setFfInboundWorkspace('reception')
                    setFfDocModal('inbound')
                  }}
                />
              ) : (
                ffAccessDenied
              )
            }
          />

          <Route
            path="ff/sorting"
            element={
              token && canReceptionOps ? (
                <FfInboundQueuePage
                  addressStorageEnabled={me.address_storage_enabled !== false} workspace="sorting"
                  rows={inboundSummaries}
                  onOpen={(id) => {
                    setSelectedOutboundId(null)
                    setSelectedInboundId(id)
                    setFfInboundWorkspace('sorting')
                    setFfDocModal('inbound')
                  }}
                />
              ) : (
                ffAccessDenied
              )
            }
          />

          <Route
            path="ff/products"
            element={
              token && canCellsOps ? (
                <FfProductsCatalogScreen
                  token={token}
                  authHeaders={authHeaders}
                  sellers={sellers}
                  canManageCatalog={isFulfillmentAdmin} addressStorageEnabled={me.address_storage_enabled !== false}
                />
              ) : (
                ffAccessDenied
              )
            }
          />

          <Route
            path="ff/fbs"
            element={
              token && canPackagingOps ? (
                <FfFbsOrdersScreen
                  token={token}
                  authHeaders={authHeaders}
                  sellers={sellers}
                  isAdmin={isFulfillmentAdmin} addressStorageEnabled={me.address_storage_enabled !== false}
                />
              ) : (
                ffAccessDenied
              )
            }
          />

          <Route
            path="ff/fbs/stock-sync"
            element={
              token && isFulfillmentAdmin ? (
                <FfFbsStockSyncScreen token={token} authHeaders={authHeaders} sellers={sellers} />
              ) : (
                ffAccessDenied
              )
            }
          />

          <Route
            path="ff/packaging"
            element={
              token && canPackagingOps ? (
                <FfPackagingPage token={token} addressStorageEnabled={me.address_storage_enabled !== false} />
              ) : (
                ffAccessDenied
              )
            }
          />
          <Route
            path="ff/packaging/:taskId"
            element={
              token && canPackagingOps ? (
                <FfPackagingPage token={token} addressStorageEnabled={me.address_storage_enabled !== false} />
              ) : (
                ffAccessDenied
              )
            }
          />
          <Route
            path="ff/packaging/pending-marking"
            element={
              token && canPackagingOps ? (
                <FfPendingMarkingPage token={token} addressStorageEnabled={me.address_storage_enabled !== false} />
              ) : (
                ffAccessDenied
              )
            }
          />

          <Route
            path="ff/honest-sign"
            element={
              token && isFulfillmentAdmin ? (
                <FfHonestSignPage
                  token={token}
                  sellers={sellers.map((s) => ({ id: s.id, name: s.name }))}
                />
              ) : (
                ffAccessDenied
              )
            }
          />

          <Route
            path="ff/honest-sign/pool/:poolId"
            element={
              token && isFulfillmentAdmin ? (
                <HonestSignPoolPage token={token} testIdPrefix="ff-honest-sign-pool" />
              ) : (
                ffAccessDenied
              )
            }
          />
          <Route
            path="ff/honest-sign/product/:productId"
            element={
              token && isFulfillmentAdmin ? (
                <HonestSignProductPage token={token} testIdPrefix="ff-honest-sign-product" />
              ) : (
                ffAccessDenied
              )
            }
          />
          <Route
            path="ff/honest-sign/ledger"
            element={
              token && isFulfillmentAdmin ? (
                <FfHonestSignLedgerPage
                  token={token}
                  sellers={sellers.map((s) => ({ id: s.id, name: s.name }))}
                />
              ) : (
                ffAccessDenied
              )
            }
          />
          <Route
            path="ff/reports"
            element={
              token && (isFulfillmentAdmin || canAccessFfBlock(me.role, me.permissions, 'inventory')) ? (
                <FfReportsPage
                  token={token}
                  sellers={sellers.map((s) => ({ id: s.id, name: s.name }))}
                  warehouses={reportWarehouseOptions(warehouses)}
                />
              ) : (
                ffAccessDenied
              )
            }
          />
          <Route
            path="seller/reports"
            element={
              token && me.seller_permissions?.products ? (
                <FfReportsPage
                  token={token}
                  sellers={[]}
                  warehouses={reportWarehouseOptions(warehouses)}
                />
              ) : (
                ffAccessDenied
              )
            }
          />
          <Route
            path="ff/billing"
            element={
              token && isFulfillmentAdmin ? (
                <FfBillingScreen
                  token={token}
                  sellers={sellers.map((seller) => ({ id: seller.id, name: seller.name }))}
                  onOpenInbound={(id) => {
                    setSelectedOutboundId(null)
                    setSelectedInboundId(id)
                    setFfInboundWorkspace('reception')
                    setFfDocModal('inbound')
                  }}
                />
              ) : (
                ffAccessDenied
              )
            }
          />
          <Route
            path="ff/honest-sign/reprints"
            element={
              token && canShiftLeadOps ? (
                <FfHonestSignReprintsPage token={token} />
              ) : (
                ffAccessDenied
              )
            }
          />
          <Route
            path="ff/honest-sign/import"
            element={
              token && isFulfillmentAdmin ? (
                <HonestSignImportPage />
              ) : (
                ffAccessDenied
              )
            }
          />

          <Route
            path="ff/notifications"
            element={
              token ? (
                <NotificationsPage token={token} portal="ff" testId="ff-notifications-page" />
              ) : (
                <FfPlaceholderPage
                  title="Уведомления"
                  hint="Нет токена."
                  testId="ff-notifications-placeholder"
                />
              )
            }
          />

          <Route
            path="ff/inventory"
            element={token && canInventoryOps ? <FfStoragePage isFulfillmentAdmin={isFulfillmentAdmin} token={token} /> : ffAccessDenied}
          />

          {/* Раскладка объектами: товар в коробе, короб на палете, палета в ячейке.
              Место товара не хранится, а вычисляется по цепочке держателей. */}
          <Route
            path="ff/sorting-objects"
            element={
              token && canCellsOps ? (
                <FfSortingObjectsPage
                  token={token}
                  warehouses={warehouses.map((w) => ({ id: w.id, name: w.name }))}
                />
              ) : (
                ffAccessDenied
              )
            }
          />

          <Route
            path="ff/warehouse-map"
            element={
              token && canCellsOps ? (
                <FfWarehouseMapPage
                  token={token}
                  warehouses={warehouses.map((w) => ({ id: w.id, name: w.name }))}
                />
              ) : (
                ffAccessDenied
              )
            }
          />

          {/* Управление остатком FBS: доля свободного остатка вместо числа штук.
              Отдельный адрес, потому что «ff/products» — существующий каталог,
              а этот экран про правила публикации, а не про карточки товара. */}
          <Route
            path="ff/fbs-stock"
            element={
              token && isFulfillmentAdmin ? (
                <FfProductsFbsPage
                  token={token}
                  sellers={sellers.map((seller) => ({ id: seller.id, name: seller.name }))}
                />
              ) : (
                ffAccessDenied
              )
            }
          />

          {/* Пересчёт живёт отдельным адресом: «ff/inventory» занят экраном
              расчёта хранения, и отбирать у него адрес — ломать работающее. */}
          <Route
            path="ff/stocktaking"
            element={
              token && canInventoryOps ? (
                <FfInventoryPage
                  token={token}
                  sellers={sellers.map((seller) => ({ id: seller.id, name: seller.name }))}
                  warehouses={warehouses.map((w) => ({ id: w.id, name: w.name }))}
                />
              ) : (
                ffAccessDenied
              )
            }
          />

          <Route
            path="ff/settings"
            element={
              token && canSettingsOps ? (
                <FfSettingsScreen
                  token={token}
                  authHeaders={authHeaders}
                  isFulfillmentAdmin={isFulfillmentAdmin}
                  canManageStaff={canSettingsOps}
                  addressStorageEnabled={me.address_storage_enabled !== false}
                  onAddressStorageChange={() => {
                    void reloadMe()
                  }}
                  separateMarkingPrintEnabled={me.separate_marking_print_enabled === true}
                  fbsShipmentCutoffTime={me.fbs_shipment_cutoff_time ?? null}
                />
              ) : (
                ffAccessDenied
              )
            }
          />

          <Route
            path="ff/inbound"
            element={token && canReceptionOps ? <Navigate to={`${base}/reception`} replace /> : ffAccessDenied}
          />
          <Route
            path="ff/outbound"
            element={token && isFulfillmentAdmin ? <Navigate to="/app/ops/outbound" replace /> : ffAccessDenied}
          />
          <Route
            path="ff/warehouses"
            element={token && canCellsOps ? (me.address_storage_enabled !== false ? <Navigate to="/app/catalog" replace /> : <Navigate to={`${base}/products`} replace />) : ffAccessDenied}
          />
          <Route
            path="ff/integrations/wb"
            element={token && isFulfillmentAdmin ? <Navigate to="/app/integrations/wb" replace /> : ffAccessDenied}
          />

          <Route
            path="catalog"
            element={
              token && canCellsOps && isFulfillmentAdmin && me.address_storage_enabled !== false ? (
                <Screen title="Ячейки" subtitle="Склады и ячейки">
                  <CatalogSection
                    isFulfillmentAdmin={isFulfillmentAdmin || canCellsOps}
                    catalogBusy={catalogBusy}
                    catalogError={catalogError}
                    sellers={sellers}
                    warehouses={warehouses}
                    locations={locations}
                    selectedWarehouseId={selectedWarehouseId}
                    setSelectedWarehouseId={setSelectedWarehouseId}
                    products={products}
                    onCreateWarehouse={(e) => void onCreateWarehouse(e)}
                    onCreateLocation={onCreateLocation}
                    onRenameWarehouse={onRenameWarehouse}
                    onDeleteWarehouse={onDeleteWarehouse}
                    onRenameLocation={onRenameLocation}
                    onDeleteLocation={onDeleteLocation}
                    onLoadLocationBalances={onLoadLocationBalances}
                    onListWarehouseRacks={onListWarehouseRacks}
                    onSuggestLocation={onSuggestLocation}
                    onCreateProduct={(e) => void onCreateProduct(e)}
                    wbSellerId={wbSellerId}
                    setWbSellerId={setWbSellerId}
                    wbHasContentToken={wbHasContentToken}
                    wbHasSuppliesToken={wbHasSuppliesToken}
                    wbTokensBusy={wbTokensBusy}
                    wbSyncBusy={wbSyncBusy}
                    wbSuppliesSyncBusy={wbSuppliesSyncBusy}
                    wbLinkBusy={wbLinkBusy}
                    wbJobStatus={wbJobStatus}
                    wbJobResult={wbJobResult}
                    wbSuppliesJobStatus={wbSuppliesJobStatus}
                    wbSuppliesJobResult={wbSuppliesJobResult}
                    wbImportedCards={wbImportedCards}
                    wbImportedSupplies={wbImportedSupplies}
                    onSaveWbTokens={(e) => void onSaveWbTokens(e)}
                    onStartWbCardsSyncJob={() => void onStartWbCardsSyncJob()}
                    onStartWbSuppliesSyncJob={() => void onStartWbSuppliesSyncJob()}
                    onLinkProductToWb={(e) => void onLinkProductToWb(e)}
                  />
                </Screen>
              ) : token && canCellsOps ? (
                <Navigate to={`${base}/products`} replace />
              ) : (
                ffAccessDenied
              )
            }
          />

          <Route
            path="ff/sellers"
            element={
              token && isFulfillmentAdmin ? (
                <SellersScreen
                  token={token}
                  authHeaders={authHeaders}
                  isFulfillmentAdmin={isFulfillmentAdmin}
                  sellers={sellers}
                  onRefresh={() => void refreshSellers(token)}
                />
              ) : (
                ffAccessDenied
              )
            }
          />

          <Route
            path="catalog/products"
            element={
              token && isFulfillmentAdmin ? (
                <ProductsScreen
                  isFulfillmentAdmin={isFulfillmentAdmin}
                  catalogBusy={catalogBusy}
                  catalogError={catalogError}
                  sellers={sellers}
                  products={products}
                  onCreateProduct={(e) => void onCreateProduct(e)}
                />
              ) : (
                ffAccessDenied
              )
            }
          />

          <Route
            path="ops"
            element={token && canReceptionOps ? <Navigate to={`${base}/reception`} replace /> : ffAccessDenied}
          />

          <Route
            path="ops/inbound"
            element={
              token && canReceptionOps ? (
                <InboundScreen
                  opsError={opsError}
                  opsBusy={opsBusy}
                  isFulfillmentAdmin={isFulfillmentAdmin}
                  isFulfillmentSeller={isFulfillmentSeller}
                  canEditInboundDraft={canReceptionOps} addressStorageEnabled={me.address_storage_enabled !== false}
                  warehouses={warehouses}
                  selectedWarehouseId={selectedWarehouseId}
                  products={products}
                  inboundSummaries={inboundSummaries}
                  selectedInboundId={selectedInboundId}
                  setSelectedInboundId={setSelectedInboundId}
                  inboundDetail={inboundDetail}
                  inboundRequestLocations={inboundRequestLocations}
                  inboundMovements={inboundMovements}
                  postedInventoryRows={postedInventoryRows}
                  onCreateInboundRequest={(e) => void onCreateInboundRequest(e)}
                  onAddInboundLine={(e) => void onAddInboundLine(e)}
                  onSubmitInboundRequest={() => void onSubmitInboundRequest()}
                  onPrimaryAcceptInboundRequest={() => void onPrimaryAcceptInboundRequest()}
                  onOpenInboundBoxByBarcode={(code) => void onOpenInboundBoxByBarcode(code)}
                  onScanInboundProductBarcode={(code) => void onScanInboundProductBarcode(code)}
                  onCloseInboundBoxIntake={() => void onCloseInboundBoxIntake()}
                  onSetInboundLineActualQty={(e) => void onSetInboundLineActualQty(e)}
                  onCompleteInboundVerification={() => void onCompleteInboundVerification()}
                  onSaveInboundLineStorage={(e) => void onSaveInboundLineStorage(e)}
                  onReceiveInboundLine={(e) => void onReceiveInboundLine(e)}
                  onPostInboundRequest={() => void onPostInboundRequest()}
                />
              ) : (
                ffAccessDenied
              )
            }
          />

          <Route
            path="ops/outbound"
            element={
              token && isFulfillmentAdmin ? (
                <OutboundScreen
                  opsError={opsError}
                  opsBusy={opsBusy}
                  isFulfillmentAdmin={isFulfillmentAdmin}
                  isFulfillmentSeller={isFulfillmentSeller}
                  canEditOutboundDraft={isFulfillmentAdmin} addressStorageEnabled={me.address_storage_enabled !== false}
                  warehouses={warehouses}
                  selectedWarehouseId={selectedWarehouseId}
                  products={products}
                  outboundSummaries={outboundSummaries}
                  selectedOutboundId={selectedOutboundId}
                  setSelectedOutboundId={setSelectedOutboundId}
                  outboundDetail={outboundDetail}
                  outboundRequestLocations={outboundRequestLocations}
                  outboundMovements={outboundMovements}
                  onCreateOutboundRequest={(e) => void onCreateOutboundRequest(e)}
                  onAddOutboundLine={(e) => void onAddOutboundLine(e)}
                  onDeleteOutboundLine={(lineId) => void onDeleteOutboundLine(lineId)}
                  onSubmitOutboundRequest={() => void onSubmitOutboundRequest()}
                  onSaveOutboundLineStorage={(e) => void onSaveOutboundLineStorage(e)}
                  onShipOutboundLine={(e) => void onShipOutboundLine(e)}
                  onPostOutboundRequest={() => void onPostOutboundRequest()}
                />
              ) : (
                ffAccessDenied
              )
            }
          />

          <Route
            path="ops/movements"
            element={
              token && isFulfillmentAdmin ? (
                <MovementsScreen
                  globalMovements={globalMovements}
                  onRefreshGlobalMovementsClick={() => void onRefreshGlobalMovementsClick()}
                  isFulfillmentAdmin={isFulfillmentAdmin}
                  opsBusy={opsBusy}
                  backgroundJobStatus={backgroundJobStatus}
                  backgroundJobResult={backgroundJobResult}
                  onStartMovementsDigestJob={() => void onStartMovementsDigestJob()}
                />
              ) : (
                ffAccessDenied
              )
            }
          />

          <Route
            path="ops/transfers"
            element={
              token && isFulfillmentAdmin && me.address_storage_enabled !== false ? (
                <TransfersScreen
                  opsError={opsError}
                  opsBusy={opsBusy}
                  isFulfillmentAdmin={isFulfillmentAdmin} addressStorageEnabled={me.address_storage_enabled !== false}
                  locations={locations}
                  products={products}
                  onStockTransfer={(e) => void onStockTransfer(e)}
                />
              ) : (
                ffAccessDenied
              )
            }
          />

          <Route
            path="integrations/wb"
            element={
              token && isFulfillmentAdmin ? (
                <WildberriesScreen
                  sellers={sellers}
                  products={products}
                  wbSellerId={wbSellerId}
                  setWbSellerId={setWbSellerId}
                  wbHasContentToken={wbHasContentToken}
                  wbHasSuppliesToken={wbHasSuppliesToken}
                  wbHasMarketplaceToken={wbHasMarketplaceToken}
                  wbMarketplaceScopeOk={wbMarketplaceScopeOk}
                  wbTokenUpdatedAt={wbTokenUpdatedAt}
                  wbTokensBusy={wbTokensBusy}
                  wbSyncBusy={wbSyncBusy}
                  wbSuppliesSyncBusy={wbSuppliesSyncBusy}
                  wbLinkBusy={wbLinkBusy}
                  wbJobStatus={wbJobStatus}
                  wbJobResult={wbJobResult}
                  wbSuppliesJobStatus={wbSuppliesJobStatus}
                  wbSuppliesJobResult={wbSuppliesJobResult}
                  wbImportedCards={wbImportedCards}
                  wbImportedSupplies={wbImportedSupplies}
                  onSaveWbTokens={(e) => void onSaveWbTokens(e)}
                  onClearWbMarketplaceToken={() => void onClearWbMarketplaceToken()}
                  onStartWbCardsSyncJob={() => void onStartWbCardsSyncJob()}
                  onStartWbSuppliesSyncJob={() => void onStartWbSuppliesSyncJob()}
                  onLinkProductToWb={(e) => void onLinkProductToWb(e)}
                />
              ) : (
                ffAccessDenied
              )
            }
          />

          <Route path="*" element={ffAccessDenied} />
        </Routes>

        <Dialog
          open={ffDocModal !== null}
          onClose={closeFfDocument}
          fullScreen
          data-testid="ff-doc-dialog"
        >
          <MuiAppBar position="sticky" color="inherit" elevation={1}>
            <MuiToolbar>
              <IconButton
                edge="start"
                color="inherit"
                aria-label="Закрыть"
                onClick={closeFfDocument}
                data-testid="ff-doc-dialog-close"
              >
                <CloseIcon />
              </IconButton>
              <MuiTypography variant="h6" sx={{ flex: 1 }}>
                Документ
              </MuiTypography>
            </MuiToolbar>
          </MuiAppBar>
          <MuiBox sx={{ p: 2, overflow: 'auto', height: 'calc(100vh - 64px)' }}>
            {ffDocModal === 'inbound' ? (
              token && selectedInboundId ? (
                <FfInboundRequestView
                  token={token}
                  requestId={selectedInboundId}
                  isFulfillmentAdmin={canReceptionOps}
                  workspace={ffInboundWorkspace}
                  sellers={sellers}
                  addressStorageEnabled={me?.address_storage_enabled !== false}
                  onDirtyChange={setFfDocDirty}
                  onClose={closeFfDocument}
                />
              ) : (
                <MuiTypography variant="body2" color="text.secondary">
                  Нет выбранной заявки.
                </MuiTypography>
              )
            ) : ffDocModal === 'outbound' ? (
              <OutboundScreen
                opsError={opsError}
                opsBusy={opsBusy}
                isFulfillmentAdmin={isFulfillmentAdmin}
                isFulfillmentSeller={isFulfillmentSeller}
                canEditOutboundDraft={isFulfillmentAdmin} addressStorageEnabled={me.address_storage_enabled !== false}
                warehouses={warehouses}
                selectedWarehouseId={selectedWarehouseId}
                products={products}
                outboundSummaries={outboundSummaries}
                selectedOutboundId={selectedOutboundId}
                setSelectedOutboundId={setSelectedOutboundId}
                outboundDetail={outboundDetail}
                outboundRequestLocations={outboundRequestLocations}
                outboundMovements={outboundMovements}
                onCreateOutboundRequest={(e) => void onCreateOutboundRequest(e)}
                onAddOutboundLine={(e) => void onAddOutboundLine(e)}
                onDeleteOutboundLine={(lineId) => void onDeleteOutboundLine(lineId)}
                onSubmitOutboundRequest={() => void onSubmitOutboundRequest()}
                onSaveOutboundLineStorage={(e) => void onSaveOutboundLineStorage(e)}
                onShipOutboundLine={(e) => void onShipOutboundLine(e)}
                onPostOutboundRequest={() => void onPostOutboundRequest()}
              />
            ) : null}
          </MuiBox>
        </Dialog>
        </>
      </AuthedAppLayout>
    )

    return (
      <Routes>
        <Route path="/" element={<Navigate to={`${base}/dashboard`} replace />} />
        <Route path="/app/*" element={v2} />
        <Route path="*" element={v2} />
      </Routes>
    )
  })()

  return (
    <Routes>
      <Route path="/seller" element={<SellerPortalDocumentRedirect />} />
      <Route path="/seller/*" element={<SellerPortalDocumentRedirect />} />
      <Route path="*" element={rootElement} />
    </Routes>
  )
}
