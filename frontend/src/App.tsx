import { useCallback, useEffect, useState } from 'react'
import './App.css'
import { apiUrl } from './api'
import { Navigate, Route, Routes } from 'react-router-dom'
import { ProfileLoadingScreen } from './screens/ProfileLoadingScreen'
import { PublicAuthScreen } from './screens/PublicAuthScreen'
import { AuthedAppLayout } from './layouts/AuthedAppLayout'
import { CatalogSection } from './sections/CatalogSection'
import { OperationsSection } from './sections/OperationsSection'
import { DashboardCard } from './components/DashboardCard'
import { readApiErrorMessage } from './utils/readApiErrorMessage'
import { useAuth } from './hooks/useAuth'
import { PlaceholderCard, Screen } from './screens/AppV2Screens'
import { ProductsScreen } from './screens/v2/ProductsScreen'
import { InboundScreen } from './screens/v2/InboundScreen'
import { OutboundScreen } from './screens/v2/OutboundScreen'
import { WildberriesScreen } from './screens/v2/WildberriesScreen'
import { MovementsScreen } from './screens/v2/MovementsScreen'
import { TransfersScreen } from './screens/v2/TransfersScreen'
import { StatCard } from './components/StatCard'

type WarehouseRow = { id: string; name: string; code: string }
type LocationRow = { id: string; code: string; warehouse_id: string }
type ProductRow = {
  id: string
  name: string
  sku_code: string
  length_mm: number
  width_mm: number
  height_mm: number
  volume_liters: number
  seller_id: string | null
  seller_name: string | null
  wb_nm_id?: number | null
  wb_vendor_code?: string | null
}

type SellerRow = { id: string; name: string }

type InboundSummaryRow = {
  id: string
  warehouse_id: string
  status: string
  line_count: number
}

type InboundLineRow = {
  id: string
  product_id: string
  sku_code: string
  product_name: string
  expected_qty: number
  posted_qty: number
  storage_location_id: string | null
  storage_location_code: string | null
}

type InboundDetailRow = {
  id: string
  warehouse_id: string
  status: string
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

type OutboundSummaryRow = {
  id: string
  warehouse_id: string
  status: string
  line_count: number
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
  const { token, me, error, loading, authBusy, onRegister, onLogin, logout } =
    useAuth()
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
        apiUrl(`/warehouses/${warehouseId}/locations`),
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
      const res = await fetch(apiUrl('/products'), {
        headers: authHeaders(t),
      })
      if (!res.ok) {
        throw new Error(await readApiErrorMessage(res))
      }
      setProducts((await res.json()) as ProductRow[])
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
      const res = await fetch(apiUrl('/operations/inbound-intake-requests'), {
        headers: authHeaders(t),
      })
      if (!res.ok) {
        throw new Error(await readApiErrorMessage(res))
      }
      setInboundSummaries((await res.json()) as InboundSummaryRow[])
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
        await refreshWarehouses(token)
        if (me.role !== 'fulfillment_admin') {
          setLocations([])
          setSelectedWarehouseId(null)
        }
        await refreshProducts(token)
        await refreshSellers(token)
      } catch (e) {
        setCatalogError(
          e instanceof Error ? e.message : 'Не удалось загрузить каталог.',
        )
      }
    })()
    void (async () => {
      try {
        await refreshInboundList(token)
        await refreshOutboundList(token)
        await refreshGlobalMovements(token)
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
    refreshGlobalMovements,
  ])

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
    if (!token || !selectedWarehouseId || me?.role !== 'fulfillment_admin') {
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
        }
        if (cancelled) {
          return
        }
        setWbHasContentToken(Boolean(j.has_content_token))
        setWbHasSuppliesToken(Boolean(j.has_supplies_token))
      } catch {
        if (!cancelled) {
          setWbHasContentToken(false)
          setWbHasSuppliesToken(false)
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

  async function onCreateSeller(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault()
    const form = e.currentTarget
    if (!token) {
      return
    }
    setCatalogError(null)
    setCatalogBusy(true)
    try {
      const fd = new FormData(form)
      const name = String(fd.get('seller_name') ?? '').trim()
      const res = await fetch(apiUrl('/sellers'), {
        method: 'POST',
        headers: {
          ...authHeaders(token),
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ name }),
      })
      if (!res.ok) {
        setCatalogError(await readApiErrorMessage(res))
        return
      }
      form.reset()
      await refreshSellers(token)
    } catch (err) {
      setCatalogError(
        err instanceof Error ? err.message : 'Не удалось создать селлера.',
      )
    } finally {
      setCatalogBusy(false)
    }
  }

  async function onCreateSellerAccount(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault()
    const form = e.currentTarget
    if (!token) {
      return
    }
    setCatalogError(null)
    setCatalogBusy(true)
    try {
      const fd = new FormData(form)
      const seller_id = String(fd.get('acc_seller_id') ?? '')
      const email = String(fd.get('acc_email') ?? '').trim()
      const password = String(fd.get('acc_password') ?? '')
      const res = await fetch(apiUrl('/auth/seller-accounts'), {
        method: 'POST',
        headers: {
          ...authHeaders(token),
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ seller_id, email, password }),
      })
      if (!res.ok) {
        setCatalogError(await readApiErrorMessage(res))
        return
      }
      form.reset()
    } catch (err) {
      setCatalogError(
        err instanceof Error
          ? err.message
          : 'Не удалось создать аккаунт селлера.',
      )
    } finally {
      setCatalogBusy(false)
    }
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

  async function onCreateLocation(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault()
    const form = e.currentTarget
    if (!token || !selectedWarehouseId) {
      return
    }
    setCatalogError(null)
    setCatalogBusy(true)
    try {
      const fd = new FormData(form)
      const code = String(fd.get('location_code') ?? '').trim()
      const res = await fetch(
        apiUrl(`/warehouses/${selectedWarehouseId}/locations`),
        {
          method: 'POST',
          headers: {
            ...authHeaders(token),
            'Content-Type': 'application/json',
          },
          body: JSON.stringify({ code }),
        },
      )
      if (!res.ok) {
        setCatalogError(await readApiErrorMessage(res))
        return
      }
      form.reset()
      await refreshLocations(token, selectedWarehouseId)
    } catch (e) {
      setCatalogError(
        e instanceof Error
          ? e.message
          : 'Сеть: не удалось создать ячейку.',
      )
    } finally {
      setCatalogBusy(false)
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
        body: JSON.stringify({ warehouse_id: warehouseId }),
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
      const body: Record<string, string> = {}
      if (content) {
        body.content_api_token = content
      }
      if (supplies) {
        body.supplies_api_token = supplies
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
      }
      setWbHasContentToken(Boolean(j.has_content_token))
      setWbHasSuppliesToken(Boolean(j.has_supplies_token))
      form.reset()
    } catch (err) {
      setOpsError(
        err instanceof Error ? err.message : 'Не удалось сохранить токены WB.',
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

  const rootElement = (() => {
    if (!token) {
      return (
        <PublicAuthScreen
          error={error}
          authBusy={authBusy}
          onRegister={(e) => void onRegister(e)}
          onLogin={(e) => void onLogin(e)}
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
    const canEditInboundDraft = isFulfillmentAdmin || isFulfillmentSeller
    const canEditOutboundDraft = isFulfillmentAdmin || isFulfillmentSeller

    const v2 = (
      <AuthedAppLayout
        onLogout={onLogout}
        title="WMS"
        userLabel={me.email}
        userRoleLabel={me.role}
      >
        <Routes>
          <Route
            path="dashboard"
            element={
              <Screen title="Дашборд" subtitle="Ключевые статусы и быстрые действия">
                <div className="kpi-grid" data-testid="kpi-grid">
                  <StatCard
                    label="Склады"
                    value={warehouses.length}
                    hint="Количество складов"
                    tone="accent"
                    data-testid="kpi-warehouses"
                  />
                  <StatCard
                    label="Ячейки"
                    value={locations.length}
                    hint="По выбранному складу"
                    data-testid="kpi-locations"
                  />
                  <StatCard
                    label="SKU"
                    value={products.length}
                    hint="Товары в каталоге"
                    data-testid="kpi-products"
                  />
                  <StatCard
                    label="Селлеры"
                    value={sellers.length}
                    hint="Клиенты фулфилмента"
                    data-testid="kpi-sellers"
                  />
                </div>

                <div className="screen-grid">
                  <div className="stack">
                    <DashboardCard
                      me={me}
                      isFulfillmentAdmin={isFulfillmentAdmin}
                      sellers={sellers}
                      catalogBusy={catalogBusy}
                      onCreateSellerAccount={(e) => void onCreateSellerAccount(e)}
                    />
                    <PlaceholderCard
                      title="Сводка по операциям"
                      hint={`Inbound: ${inboundSummaries.length} · Outbound: ${outboundSummaries.length} · Movements: ${globalMovements.length}`}
                    />
                  </div>
                  <div className="stack">
                    <PlaceholderCard
                      title="Быстрый старт"
                      hint="Слева выбери экран: Products / Inbound / Outbound / WB. Это новый структурный UI (v2)."
                    />
                    <PlaceholderCard
                      title="Интеграции"
                      hint="Wildberries — отдельный экран в разделе Integrations."
                    />
                  </div>
                </div>
              </Screen>
            }
          />

          <Route
            path="catalog"
            element={
              <Screen title="Каталог" subtitle="Склады, ячейки, товары, селлеры и интеграции">
                <CatalogSection
                  isFulfillmentAdmin={isFulfillmentAdmin}
                  catalogBusy={catalogBusy}
                  catalogError={catalogError}
                  sellers={sellers}
                  warehouses={warehouses}
                  locations={locations}
                  selectedWarehouseId={selectedWarehouseId}
                  setSelectedWarehouseId={setSelectedWarehouseId}
                  products={products}
                  onCreateWarehouse={(e) => void onCreateWarehouse(e)}
                  onCreateLocation={(e) => void onCreateLocation(e)}
                  onCreateSeller={(e) => void onCreateSeller(e)}
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
            }
          />

          <Route
            path="catalog/products"
            element={
              <ProductsScreen
                isFulfillmentAdmin={isFulfillmentAdmin}
                catalogBusy={catalogBusy}
                catalogError={catalogError}
                sellers={sellers}
                products={products}
                onCreateProduct={(e) => void onCreateProduct(e)}
              />
            }
          />

          <Route
            path="ops"
            element={
              <Screen title="Операции склада" subtitle="Приёмка, отгрузка, движения и перемещения">
                <OperationsSection
                  opsError={opsError}
                  opsBusy={opsBusy}
                  isFulfillmentAdmin={isFulfillmentAdmin}
                  isFulfillmentSeller={isFulfillmentSeller}
                  canEditInboundDraft={canEditInboundDraft}
                  canEditOutboundDraft={canEditOutboundDraft}
                  warehouses={warehouses}
                  selectedWarehouseId={selectedWarehouseId}
                  locations={locations}
                  products={products}
                  inboundSummaries={inboundSummaries}
                  selectedInboundId={selectedInboundId}
                  setSelectedInboundId={setSelectedInboundId}
                  inboundDetail={inboundDetail}
                  inboundRequestLocations={inboundRequestLocations}
                  inboundMovements={inboundMovements}
                  postedInventoryRows={postedInventoryRows}
                  globalMovements={globalMovements}
                  outboundSummaries={outboundSummaries}
                  selectedOutboundId={selectedOutboundId}
                  setSelectedOutboundId={setSelectedOutboundId}
                  outboundDetail={outboundDetail}
                  outboundRequestLocations={outboundRequestLocations}
                  outboundMovements={outboundMovements}
                  backgroundJobStatus={backgroundJobStatus}
                  backgroundJobResult={backgroundJobResult}
                  onStartMovementsDigestJob={() => void onStartMovementsDigestJob()}
                  onCreateInboundRequest={(e) => void onCreateInboundRequest(e)}
                  onAddInboundLine={(e) => void onAddInboundLine(e)}
                  onSubmitInboundRequest={() => void onSubmitInboundRequest()}
                  onSaveInboundLineStorage={(e) => void onSaveInboundLineStorage(e)}
                  onReceiveInboundLine={(e) => void onReceiveInboundLine(e)}
                  onPostInboundRequest={() => void onPostInboundRequest()}
                  onRefreshGlobalMovementsClick={() => void onRefreshGlobalMovementsClick()}
                  onStockTransfer={(e) => void onStockTransfer(e)}
                  onCreateOutboundRequest={(e) => void onCreateOutboundRequest(e)}
                  onAddOutboundLine={(e) => void onAddOutboundLine(e)}
                  onDeleteOutboundLine={(lineId) => void onDeleteOutboundLine(lineId)}
                  onSubmitOutboundRequest={() => void onSubmitOutboundRequest()}
                  onSaveOutboundLineStorage={(e) => void onSaveOutboundLineStorage(e)}
                  onShipOutboundLine={(e) => void onShipOutboundLine(e)}
                  onPostOutboundRequest={() => void onPostOutboundRequest()}
                />
              </Screen>
            }
          />

          <Route
            path="ops/inbound"
            element={
              <InboundScreen
                opsError={opsError}
                opsBusy={opsBusy}
                isFulfillmentAdmin={isFulfillmentAdmin}
                isFulfillmentSeller={isFulfillmentSeller}
                canEditInboundDraft={canEditInboundDraft}
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
                onSaveInboundLineStorage={(e) => void onSaveInboundLineStorage(e)}
                onReceiveInboundLine={(e) => void onReceiveInboundLine(e)}
                onPostInboundRequest={() => void onPostInboundRequest()}
              />
            }
          />

          <Route
            path="ops/outbound"
            element={
              <OutboundScreen
                opsError={opsError}
                opsBusy={opsBusy}
                isFulfillmentAdmin={isFulfillmentAdmin}
                isFulfillmentSeller={isFulfillmentSeller}
                canEditOutboundDraft={canEditOutboundDraft}
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
            }
          />

          <Route
            path="ops/movements"
            element={
              <MovementsScreen
                globalMovements={globalMovements}
                onRefreshGlobalMovementsClick={() => void onRefreshGlobalMovementsClick()}
              />
            }
          />

          <Route
            path="ops/transfers"
            element={
              <TransfersScreen
                opsError={opsError}
                opsBusy={opsBusy}
                isFulfillmentAdmin={isFulfillmentAdmin}
                locations={locations}
                products={products}
                onStockTransfer={(e) => void onStockTransfer(e)}
              />
            }
          />

          <Route
            path="integrations/wb"
            element={
              <WildberriesScreen
                sellers={sellers}
                products={products}
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
            }
          />

          <Route path="*" element={<Navigate to="/app/dashboard" replace />} />
        </Routes>
      </AuthedAppLayout>
    )

    return (
      <Routes>
        <Route path="/" element={<Navigate to="/app/dashboard" replace />} />
        <Route path="/app/*" element={v2} />
        <Route path="*" element={<Navigate to="/app/dashboard" replace />} />
      </Routes>
    )
  })()

  return (
    <Routes>
      <Route path="*" element={rootElement} />
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  )
}
