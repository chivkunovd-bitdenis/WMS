import { useCallback, useEffect, useState } from 'react'
import './App.css'
import { apiUrl, getStoredToken, setStoredToken } from './api'

type Me = {
  email: string
  organization_name: string
  role: string
  seller_id?: string | null
  seller_name?: string | null
}

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

async function readApiErrorMessage(res: Response): Promise<string> {
  try {
    const text = await res.text()
    if (!text) {
      return `Ошибка ${res.status}`
    }
    const data = JSON.parse(text) as { detail?: unknown }
    const d = data.detail
    if (typeof d === 'string') {
      return d
    }
    if (Array.isArray(d)) {
      const parts = d.map((x: { msg?: string; loc?: unknown }) =>
        typeof x?.msg === 'string' ? x.msg : JSON.stringify(x),
      )
      return parts.join('; ')
    }
    return text.slice(0, 200)
  } catch {
    return `Ошибка ${res.status}`
  }
}

export default function App() {
  const [token, setToken] = useState<string | null>(() => getStoredToken())
  const [me, setMe] = useState<Me | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)
  const [authBusy, setAuthBusy] = useState(false)
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

  const loadMe = useCallback(async (t: string) => {
    setLoading(true)
    setError(null)
    try {
      const res = await fetch(apiUrl('/auth/me'), {
        headers: { Authorization: `Bearer ${t}` },
      })
      if (!res.ok) {
        const msg = await readApiErrorMessage(res)
        if (res.status === 401) {
          throw new Error(
            `Не удалось загрузить профиль (401). ${msg}. Попробуйте войти снова.`,
          )
        }
        throw new Error(
          `Не удалось загрузить профиль (${res.status}). ${msg}`,
        )
      }
      setMe((await res.json()) as Me)
    } catch (e) {
      setStoredToken(null)
      setToken(null)
      setMe(null)
      setError(
        e instanceof Error
          ? e.message
          : 'Не удалось связаться с сервером. Проверьте, что API запущен.',
      )
    } finally {
      setLoading(false)
    }
  }, [])

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
    if (token) {
      void loadMe(token)
    } else {
      setMe(null)
    }
  }, [token, loadMe])

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

  async function onRegister(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault()
    setError(null)
    setAuthBusy(true)
    try {
      const fd = new FormData(e.currentTarget)
      const rawSlug = String(fd.get('slug') ?? '').trim()
      const slug = rawSlug.toLowerCase().replace(/\s+/g, '-')
      if (slug.length < 2) {
        setError('Slug слишком короткий (минимум 2 символа, латиница и дефис).')
        return
      }
      if (!/^[a-z0-9-]+$/.test(slug)) {
        setError(
          'Slug: только строчные латинские буквы, цифры и дефис (например my-fulfillment).',
        )
        return
      }
      const body = {
        organization_name: String(fd.get('organization_name') ?? '').trim(),
        slug,
        admin_email: String(fd.get('admin_email') ?? '').trim(),
        password: String(fd.get('password') ?? ''),
      }
      const res = await fetch(apiUrl('/auth/register'), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      })
      if (!res.ok) {
        if (res.status === 409) {
          setError('Такой slug или email уже заняты. Выберите другие.')
        } else if (res.status === 422) {
          setError(await readApiErrorMessage(res))
        } else {
          setError(await readApiErrorMessage(res))
        }
        return
      }
      const data = (await res.json()) as { access_token: string }
      if (!data.access_token) {
        setError('Сервер не вернул токен. Обратитесь к разработчику.')
        return
      }
      setStoredToken(data.access_token)
      setToken(data.access_token)
    } catch {
      setError(
        'Сеть: не удалось достучаться до API. Проверьте адрес и что контейнер api запущен.',
      )
    } finally {
      setAuthBusy(false)
    }
  }

  async function onLogin(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault()
    setError(null)
    setAuthBusy(true)
    try {
      const fd = new FormData(e.currentTarget)
      const body = {
        email: String(fd.get('email') ?? '').trim(),
        password: String(fd.get('password') ?? ''),
      }
      const res = await fetch(apiUrl('/auth/login'), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      })
      if (!res.ok) {
        if (res.status === 401) {
          setError('Неверный email или пароль.')
        } else {
          setError(await readApiErrorMessage(res))
        }
        return
      }
      const data = (await res.json()) as { access_token: string }
      setStoredToken(data.access_token)
      setToken(data.access_token)
    } catch {
      setError(
        'Сеть: не удалось достучаться до API. Проверьте, что контейнер api запущен.',
      )
    } finally {
      setAuthBusy(false)
    }
  }

  function onLogout() {
    setStoredToken(null)
    setToken(null)
    setMe(null)
    setError(null)
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

  if (token && !me) {
    return (
      <main data-testid="app-root" className="shell">
        <header className="top">
          <h1>WMS</h1>
          <button type="button" data-testid="logout" onClick={onLogout}>
            Выйти
          </button>
        </header>
        <p className="hint" data-testid="loading">
          {loading
            ? 'Загрузка профиля…'
            : 'Получаем данные аккаунта…'}{' '}
          Если экран не меняется, проверьте, что API доступен (прокси Vite /
          контейнер api в docker).
        </p>
      </main>
    )
  }

  if (token && me) {
    const isFulfillmentAdmin = me.role === 'fulfillment_admin'
    const isFulfillmentSeller = me.role === 'fulfillment_seller'
    const canEditInboundDraft = isFulfillmentAdmin || isFulfillmentSeller
    const canEditOutboundDraft = isFulfillmentAdmin || isFulfillmentSeller
    return (
      <main data-testid="app-root" className="shell">
        <header className="top">
          <h1>WMS</h1>
          <button type="button" data-testid="logout" onClick={onLogout}>
            Выйти
          </button>
        </header>
        <nav
          className="app-nav"
          aria-label="Основные разделы"
          data-testid="app-section-nav"
        >
          <a href="#catalog-section">Каталог и товары</a>
          <span aria-hidden="true">
            {' '}
            ·{' '}
          </span>
          <a href="#operations-section">Операции склада</a>
        </nav>
        <section className="card" data-testid="dashboard">
          <p data-testid="user-email">{me.email}</p>
          <p data-testid="org-name">{me.organization_name}</p>
          <p data-testid="user-role">{me.role}</p>
          {me.seller_name ? (
            <p data-testid="seller-cabinet-label">Селлер: {me.seller_name}</p>
          ) : null}
          {isFulfillmentAdmin && sellers.length > 0 ? (
            <form
              data-testid="seller-account-form"
              style={{ marginTop: 12 }}
              noValidate
              onSubmit={(e) => void onCreateSellerAccount(e)}
            >
              <h3 className="subtle" style={{ marginTop: 0 }}>
                Аккаунт селлера (вход по email)
              </h3>
              <label>
                Селлер
                <select
                  name="acc_seller_id"
                  data-testid="seller-account-seller"
                  required
                  defaultValue=""
                >
                  <option value="" disabled>
                    Выберите
                  </option>
                  {sellers.map((s) => (
                    <option key={s.id} value={s.id}>
                      {s.name}
                    </option>
                  ))}
                </select>
              </label>
              <label>
                Email
                <input
                  name="acc_email"
                  data-testid="seller-account-email"
                  type="email"
                  required
                  autoComplete="off"
                />
              </label>
              <label>
                Пароль
                <input
                  name="acc_password"
                  data-testid="seller-account-password"
                  type="password"
                  minLength={8}
                  required
                  autoComplete="new-password"
                />
              </label>
              <button
                type="submit"
                data-testid="seller-account-submit"
                disabled={catalogBusy}
              >
                {catalogBusy ? '…' : 'Создать аккаунт селлера'}
              </button>
            </form>
          ) : null}
        </section>
        <div
          id="catalog-section"
          className="stack"
          data-testid="catalog-section"
        >
          {catalogError ? (
            <p className="error" data-testid="catalog-error">
              {catalogError}
            </p>
          ) : null}
          {!isFulfillmentAdmin ? (
            <p className="subtle" data-testid="seller-cabinet-notice">
              Режим селлера: доступны ваши SKU, заявки с вашими товарами и
              журнал движений. Управление складом — у фулфилмента.
            </p>
          ) : null}
          {isFulfillmentAdmin ? (
          <section className="card">
            <h2>Склады</h2>
            <p className="subtle">
              Код склада — латиница, цифры, символы _ и -.
            </p>
            <form
              data-testid="warehouse-form"
              noValidate
              onSubmit={(e) => void onCreateWarehouse(e)}
            >
              <label>
                Название
                <input
                  name="warehouse_name"
                  data-testid="warehouse-name"
                  required
                />
              </label>
              <label>
                Код
                <input
                  name="warehouse_code"
                  data-testid="warehouse-code"
                  required
                  autoComplete="off"
                />
              </label>
              <button
                type="submit"
                data-testid="warehouse-submit"
                disabled={catalogBusy}
              >
                {catalogBusy ? '…' : 'Добавить склад'}
              </button>
            </form>
            <ul className="list-plain" data-testid="warehouse-list">
              {warehouses.map((w) => (
                <li key={w.id}>
                  <button
                    type="button"
                    data-testid="warehouse-item"
                    data-selected={w.id === selectedWarehouseId ? 'true' : 'false'}
                    onClick={() => setSelectedWarehouseId(w.id)}
                    style={{
                      width: '100%',
                      textAlign: 'left',
                      background:
                        w.id === selectedWarehouseId
                          ? 'rgba(91, 79, 212, 0.12)'
                          : 'transparent',
                      border: '1px solid rgba(0,0,0,0.08)',
                      borderRadius: 8,
                      padding: '8px 10px',
                      cursor: 'pointer',
                    }}
                  >
                    <strong>{w.name}</strong>{' '}
                    <span className="subtle" style={{ margin: 0 }}>
                      ({w.code})
                    </span>
                  </button>
                </li>
              ))}
            </ul>
          </section>
          ) : null}
          {isFulfillmentAdmin ? (
          <section className="card">
            <h2>Ячейки</h2>
            {!selectedWarehouseId ? (
              <p className="subtle">Сначала создайте склад.</p>
            ) : (
              <form
                data-testid="location-form"
                noValidate
                onSubmit={(e) => void onCreateLocation(e)}
              >
                <label>
                  Код ячейки
                  <input
                    name="location_code"
                    data-testid="location-code"
                    required
                    autoComplete="off"
                  />
                </label>
                <button
                  type="submit"
                  data-testid="location-submit"
                  disabled={catalogBusy}
                >
                  {catalogBusy ? '…' : 'Добавить ячейку'}
                </button>
              </form>
            )}
            <ul className="list-plain" data-testid="location-list">
              {locations.map((loc) => (
                <li key={loc.id} data-testid="location-item">
                  {loc.code}
                </li>
              ))}
            </ul>
          </section>
          ) : null}
          <section className="card" data-testid="sellers-section">
            <h2>Селлеры</h2>
            <p className="subtle">
              Клиенты фулфилмента; можно привязать к SKU при создании товара.
            </p>
            {isFulfillmentAdmin ? (
            <form
              data-testid="seller-form"
              noValidate
              onSubmit={(e) => void onCreateSeller(e)}
            >
              <label>
                Название селлера
                <input
                  name="seller_name"
                  data-testid="seller-name"
                  required
                  autoComplete="off"
                />
              </label>
              <button
                type="submit"
                data-testid="seller-submit"
                disabled={catalogBusy}
              >
                {catalogBusy ? '…' : 'Добавить селлера'}
              </button>
            </form>
            ) : null}
            <ul className="list-plain" data-testid="seller-list">
              {sellers.map((s) => (
                <li key={s.id} data-testid="seller-item">
                  {s.name}
                </li>
              ))}
            </ul>
          </section>
          {isFulfillmentAdmin && sellers.length > 0 && wbSellerId ? (
            <section className="card" data-testid="wildberries-integration-section">
              <h2>Wildberries (импорт)</h2>
              <p className="subtle">
                Токены хранятся зашифрованно. Синхронизация — только чтение: карточки
                (первая страница) и список поставок FBW (первая страница), без записи в
                WB.
              </p>
              <label>
                Селлер для интеграции
                <select
                  data-testid="wb-seller-select"
                  value={wbSellerId}
                  onChange={(ev) => setWbSellerId(ev.target.value)}
                >
                  {sellers.map((s) => (
                    <option key={s.id} value={s.id}>
                      {s.name}
                    </option>
                  ))}
                </select>
              </label>
              <p className="subtle" data-testid="wb-token-flags">
                Контент API: {wbHasContentToken ? 'токен есть' : 'нет токена'} ·
                Поставки API: {wbHasSuppliesToken ? 'токен есть' : 'нет токена'}
              </p>
              <form
                data-testid="wb-tokens-form"
                noValidate
                onSubmit={(e) => void onSaveWbTokens(e)}
              >
                <label>
                  Токен контента WB
                  <input
                    name="wb_content_token"
                    data-testid="wb-content-token"
                    type="password"
                    autoComplete="off"
                    placeholder="вставьте токен категории «Контент»"
                  />
                </label>
                <label>
                  Токен поставок WB (необязательно)
                  <input
                    name="wb_supplies_token"
                    data-testid="wb-supplies-token"
                    type="password"
                    autoComplete="off"
                    placeholder="для импорта поставок FBW (первая страница)"
                  />
                </label>
                <button
                  type="submit"
                  data-testid="wb-save-tokens"
                  disabled={wbTokensBusy}
                >
                  {wbTokensBusy ? '…' : 'Сохранить токены'}
                </button>
              </form>
              <button
                type="button"
                data-testid="wb-sync-cards"
                disabled={wbSyncBusy || !wbHasContentToken}
                onClick={() => void onStartWbCardsSyncJob()}
              >
                {wbSyncBusy ? '…' : 'Обновить карточки из WB'}
              </button>
              <p className="subtle" data-testid="wb-sync-status">
                Синхронизация: {wbJobStatus ?? '—'}
              </p>
              {wbJobResult ? (
                <p data-testid="wb-sync-result">{wbJobResult}</p>
              ) : null}
              <button
                type="button"
                data-testid="wb-sync-supplies"
                disabled={wbSuppliesSyncBusy || !wbHasSuppliesToken}
                onClick={() => void onStartWbSuppliesSyncJob()}
                style={{ marginTop: 12 }}
              >
                {wbSuppliesSyncBusy ? '…' : 'Обновить поставки из WB'}
              </button>
              <p className="subtle" data-testid="wb-supplies-sync-status">
                Синхронизация поставок: {wbSuppliesJobStatus ?? '—'}
              </p>
              {wbSuppliesJobResult ? (
                <p data-testid="wb-supplies-sync-result">{wbSuppliesJobResult}</p>
              ) : null}
              <h3 className="subtle" style={{ marginTop: 16 }}>
                Импортированные карточки
              </h3>
              {wbImportedCards.length === 0 ? (
                <p className="subtle" data-testid="wb-imported-cards-empty">
                  Пока нет — выполните синхронизацию.
                </p>
              ) : (
                <ul className="list-plain" data-testid="wb-imported-cards-list">
                  {wbImportedCards.map((c) => (
                    <li key={String(c.nm_id)} data-testid="wb-imported-card-item">
                      nmID {c.nm_id}
                      {c.vendor_code ? ` · ${c.vendor_code}` : ''}
                    </li>
                  ))}
                </ul>
              )}
              <h3 className="subtle" style={{ marginTop: 16 }}>
                Импортированные поставки
              </h3>
              {wbImportedSupplies.length === 0 ? (
                <p className="subtle" data-testid="wb-imported-supplies-empty">
                  Пока нет — сохраните токен поставок и выполните синхронизацию.
                </p>
              ) : (
                <ul className="list-plain" data-testid="wb-imported-supplies-list">
                  {wbImportedSupplies.map((s) => (
                    <li
                      key={s.external_key}
                      data-testid="wb-imported-supply-item"
                    >
                      {s.wb_supply_id != null ? `supply ${s.wb_supply_id}` : ''}
                      {s.wb_supply_id != null && s.wb_preorder_id != null ? ' · ' : ''}
                      {s.wb_preorder_id != null ? `preorder ${s.wb_preorder_id}` : ''}
                      {s.status_id != null ? ` · статус ${s.status_id}` : ''}
                    </li>
                  ))}
                </ul>
              )}
              <h3 className="subtle" style={{ marginTop: 16 }}>
                Привязка SKU к карточке WB
              </h3>
              <p className="subtle">
                Товар должен быть привязан к тому же селлеру, что выбран выше; nm_id —
                из списка импортированных карточек.
              </p>
              <form
                data-testid="wb-link-product-form"
                noValidate
                onSubmit={(e) => void onLinkProductToWb(e)}
              >
                <label>
                  Товар
                  <select
                    name="wb_link_product_id"
                    data-testid="wb-link-product-id"
                    required
                    defaultValue=""
                  >
                    <option value="" disabled>
                      — выберите —
                    </option>
                    {products
                      .filter((p) => p.seller_id === wbSellerId)
                      .map((p) => (
                        <option key={p.id} value={p.id}>
                          {p.sku_code} — {p.name}
                        </option>
                      ))}
                  </select>
                </label>
                <label>
                  nm_id (WB)
                  <input
                    name="wb_link_nm_id"
                    data-testid="wb-link-nm-id"
                    type="number"
                    min={1}
                    required
                    autoComplete="off"
                  />
                </label>
                <button
                  type="submit"
                  data-testid="wb-link-submit"
                  disabled={wbLinkBusy}
                >
                  {wbLinkBusy ? '…' : 'Привязать'}
                </button>
              </form>
            </section>
          ) : null}
          <section className="card">
            <h2>Товары (SKU)</h2>
            {isFulfillmentAdmin ? (
            <form
              data-testid="product-form"
              noValidate
              onSubmit={(e) => void onCreateProduct(e)}
            >
              <label>
                Название
                <input
                  name="product_name"
                  data-testid="product-name"
                  required
                />
              </label>
              <label>
                SKU
                <input
                  name="product_sku"
                  data-testid="product-sku"
                  required
                  autoComplete="off"
                />
              </label>
              <label>
                Длина, мм
                <input
                  name="product_length_mm"
                  data-testid="product-length-mm"
                  type="number"
                  min={1}
                  required
                />
              </label>
              <label>
                Ширина, мм
                <input
                  name="product_width_mm"
                  data-testid="product-width-mm"
                  type="number"
                  min={1}
                  required
                />
              </label>
              <label>
                Высота, мм
                <input
                  name="product_height_mm"
                  data-testid="product-height-mm"
                  type="number"
                  min={1}
                  required
                />
              </label>
              {sellers.length > 0 ? (
                <label>
                  Селлер (необязательно)
                  <select
                    name="product_seller_id"
                    data-testid="product-seller"
                    defaultValue=""
                  >
                    <option value="">— нет —</option>
                    {sellers.map((s) => (
                      <option key={s.id} value={s.id}>
                        {s.name}
                      </option>
                    ))}
                  </select>
                </label>
              ) : null}
              <button
                type="submit"
                data-testid="product-submit"
                disabled={catalogBusy}
              >
                {catalogBusy ? '…' : 'Добавить товар'}
              </button>
            </form>
            ) : null}
            <ul className="list-plain" data-testid="product-list">
              {products.map((p) => (
                <li
                  key={p.id}
                  data-testid="product-item"
                  data-product-id={p.id}
                >
                  <strong>{p.name}</strong> — {p.sku_code},{' '}
                  <span data-testid="product-volume">
                    {p.volume_liters.toFixed(1)} л
                  </span>
                  {p.seller_name ? (
                    <span data-testid="product-seller-name">
                      {' '}
                      · селлер: {p.seller_name}
                    </span>
                  ) : null}
                  {p.wb_nm_id != null ? (
                    <span data-testid="product-wb-nm">
                      {' '}
                      · WB nmID {p.wb_nm_id}
                      {p.wb_vendor_code ? ` (${p.wb_vendor_code})` : ''}
                    </span>
                  ) : null}
                </li>
              ))}
            </ul>
          </section>
        </div>
        <div
          id="operations-section"
          className="stack"
          data-testid="operations-section"
        >
          {opsError ? (
            <p className="error" data-testid="operations-error">
              {opsError}
            </p>
          ) : null}
          {isFulfillmentAdmin ? (
          <section className="card" data-testid="background-job-section">
            <h2>Фоновая задача</h2>
            <p className="subtle">
              Сервер считает сводку по журналу движений в фоне; статус
              обновляется после запуска (как отчёт / тяжёлая операция).
            </p>
            <button
              type="button"
              data-testid="background-job-start"
              disabled={opsBusy}
              onClick={() => void onStartMovementsDigestJob()}
            >
              {opsBusy ? '…' : 'Сводка по движениям'}
            </button>
            <p className="subtle" data-testid="background-job-status">
              Статус: {backgroundJobStatus ?? '—'}
            </p>
            {backgroundJobResult ? (
              <p data-testid="background-job-result">{backgroundJobResult}</p>
            ) : null}
          </section>
          ) : null}
          <section className="card">
            <h2>Приёмка</h2>
            <p className="subtle">
              Ячейку можно указать при добавлении строки или позже. Частичный
              приём — по строке; «Провести весь остаток» оприходует всё
              непринятое по строкам с назначенной ячейкой. Движения пишутся в
              журнал.
            </p>
            {canEditInboundDraft ? (
            <form
              data-testid="inbound-create-form"
              noValidate
              onSubmit={(e) => void onCreateInboundRequest(e)}
            >
              {isFulfillmentSeller && warehouses.length > 1 ? (
                <label style={{ display: 'block', marginBottom: 8 }}>
                  Склад для заявки
                  <select
                    name="inbound_warehouse_id"
                    data-testid="inbound-create-warehouse"
                    required
                    defaultValue=""
                  >
                    <option value="" disabled>
                      Выберите склад
                    </option>
                    {warehouses.map((w) => (
                      <option key={w.id} value={w.id}>
                        {w.code} — {w.name}
                      </option>
                    ))}
                  </select>
                </label>
              ) : null}
              <button
                type="submit"
                data-testid="inbound-create-submit"
                disabled={
                  opsBusy ||
                  warehouses.length === 0 ||
                  (!isFulfillmentSeller &&
                    !selectedWarehouseId &&
                    warehouses.length !== 1)
                }
              >
                {opsBusy ? '…' : 'Новая заявка на приёмку'}
              </button>
            </form>
            ) : null}
            <ul className="list-plain" data-testid="inbound-requests-list">
              {inboundSummaries.map((row) => (
                <li key={row.id}>
                  <button
                    type="button"
                    data-testid="inbound-request-item"
                    data-status={row.status}
                    onClick={() => setSelectedInboundId(row.id)}
                    style={{
                      width: '100%',
                      textAlign: 'left',
                      background:
                        row.id === selectedInboundId
                          ? 'rgba(91, 79, 212, 0.12)'
                          : 'transparent',
                      border: '1px solid rgba(0,0,0,0.08)',
                      borderRadius: 8,
                      padding: '8px 10px',
                      cursor: 'pointer',
                    }}
                  >
                    <span data-testid="inbound-request-status">{row.status}</span>
                    {' · '}
                    строк: {row.line_count}
                  </button>
                </li>
              ))}
            </ul>
            {inboundDetail ? (
              <div data-testid="inbound-detail">
                <p className="subtle" data-testid="inbound-detail-status">
                  Статус: {inboundDetail.status}
                </p>
                <ul
                  className="list-plain"
                  data-testid="inbound-detail-lines"
                >
                  {inboundDetail.lines.map((ln) => (
                    <li
                      key={ln.id}
                      data-testid="inbound-detail-line"
                    >
                      {ln.product_name} ({ln.sku_code}) — принято{' '}
                      {ln.posted_qty} из {ln.expected_qty}
                      {ln.storage_location_code
                        ? ` · ячейка: ${ln.storage_location_code}`
                        : ''}
                    </li>
                  ))}
                </ul>
                {inboundDetail.status === 'draft' && canEditInboundDraft ? (
                  <form
                    data-testid="inbound-line-form"
                    noValidate
                    onSubmit={(e) => void onAddInboundLine(e)}
                  >
                    <label>
                      Товар
                      <select
                        name="inbound_product_id"
                        data-testid="inbound-line-product"
                        required
                        defaultValue=""
                      >
                        <option value="" disabled>
                          Выберите SKU
                        </option>
                        {products.map((p) => (
                          <option key={p.id} value={p.id}>
                            {p.sku_code} — {p.name}
                          </option>
                        ))}
                      </select>
                    </label>
                    <label>
                      Количество, шт
                      <input
                        name="inbound_qty"
                        data-testid="inbound-line-qty"
                        type="number"
                        min={1}
                        required
                      />
                    </label>
                    {inboundRequestLocations.length > 0 ? (
                      <label>
                        Ячейка (необязательно)
                        <select
                          name="inbound_line_storage_id"
                          data-testid="inbound-line-location"
                          defaultValue=""
                        >
                          <option value="">— позже —</option>
                          {inboundRequestLocations.map((loc) => (
                            <option key={loc.id} value={loc.id}>
                              {loc.code}
                            </option>
                          ))}
                        </select>
                      </label>
                    ) : null}
                    <button
                      type="submit"
                      data-testid="inbound-line-submit"
                      disabled={opsBusy || products.length === 0}
                    >
                      {opsBusy ? '…' : 'Добавить строку'}
                    </button>
                  </form>
                ) : null}
                {inboundDetail.status === 'draft' &&
                inboundDetail.lines.length > 0 &&
                isFulfillmentAdmin ? (
                  <button
                    type="button"
                    data-testid="inbound-submit-request"
                    disabled={opsBusy}
                    onClick={() => void onSubmitInboundRequest()}
                  >
                    {opsBusy ? '…' : 'Отправить заявку'}
                  </button>
                ) : null}
                {inboundDetail.status === 'submitted' ? (
                  <div data-testid="inbound-receiving-panel">
                    <p className="subtle">Строки в работе</p>
                    {isFulfillmentAdmin ? (
                    <>
                    {inboundDetail.lines.map((ln) =>
                      ln.posted_qty < ln.expected_qty ? (
                        <div
                          key={ln.id}
                          style={{
                            border: '1px solid rgba(0,0,0,0.08)',
                            borderRadius: 8,
                            padding: '10px 12px',
                            marginBottom: 10,
                          }}
                        >
                          <p className="subtle" style={{ marginTop: 0 }}>
                            {ln.sku_code} — осталось{' '}
                            {ln.expected_qty - ln.posted_qty} из{' '}
                            {ln.expected_qty}
                          </p>
                          <form
                            data-testid="inbound-line-storage-form"
                            data-line-id={ln.id}
                            noValidate
                            onSubmit={(e) =>
                              void onSaveInboundLineStorage(e)
                            }
                          >
                            <label>
                              Ячейка
                              <select
                                name="line_storage_id"
                                data-testid="inbound-line-storage-select"
                                defaultValue={ln.storage_location_id ?? ''}
                                required
                              >
                                <option value="" disabled>
                                  Выберите ячейку
                                </option>
                                {inboundRequestLocations.map((loc) => (
                                  <option key={loc.id} value={loc.id}>
                                    {loc.code}
                                  </option>
                                ))}
                              </select>
                            </label>
                            <button
                              type="submit"
                              data-testid="inbound-line-storage-save"
                              disabled={
                                opsBusy || inboundRequestLocations.length === 0
                              }
                            >
                              Сохранить ячейку
                            </button>
                          </form>
                          <form
                            data-testid="inbound-line-receive-form"
                            data-line-id={ln.id}
                            noValidate
                            onSubmit={(e) => void onReceiveInboundLine(e)}
                          >
                            <label>
                              Принять, шт
                              <input
                                name="receive_qty"
                                data-testid="inbound-line-receive-qty"
                                type="number"
                                min={1}
                                max={ln.expected_qty - ln.posted_qty}
                                required
                              />
                            </label>
                            <button
                              type="submit"
                              data-testid="inbound-line-receive-submit"
                              disabled={opsBusy}
                            >
                              Принять
                            </button>
                          </form>
                        </div>
                      ) : null,
                    )}
                    <button
                      type="button"
                      data-testid="inbound-post-submit"
                      disabled={opsBusy}
                      onClick={() => void onPostInboundRequest()}
                    >
                      {opsBusy ? '…' : 'Провести весь остаток'}
                    </button>
                    </>
                    ) : (
                    <p className="subtle" data-testid="inbound-seller-read-only">
                      Приёмку ведёт фулфилмент; доступен просмотр строк и
                      статуса.
                    </p>
                    )}
                  </div>
                ) : null}
                {inboundMovements.length > 0 ? (
                  <div data-testid="inbound-movements-block">
                    <p className="subtle">Журнал движений по заявке</p>
                    <ul
                      className="list-plain"
                      data-testid="inbound-movements-list"
                    >
                      {inboundMovements.map((m) => (
                        <li
                          key={m.id}
                          data-testid="inbound-movement-row"
                        >
                          {m.quantity_delta > 0 ? '+' : ''}
                          {m.quantity_delta} · {m.movement_type}
                        </li>
                      ))}
                    </ul>
                  </div>
                ) : null}
                {isFulfillmentAdmin && postedInventoryRows.length > 0 ? (
                  <ul
                    className="list-plain"
                    data-testid="inventory-balance-list"
                  >
                    {postedInventoryRows.map((row) => (
                      <li
                        key={row.product_id}
                        data-testid="inventory-balance-row"
                      >
                        {row.sku_code} — {row.quantity} шт
                        {row.reserved > 0 ? (
                          <span data-testid="inventory-balance-available-hint">
                            {' '}
                            (доступно {row.available})
                          </span>
                        ) : null}
                      </li>
                    ))}
                  </ul>
                ) : null}
              </div>
            ) : null}
          </section>
          <section className="card" data-testid="global-movements-section">
            <h2>Журнал движений</h2>
            <p className="subtle">
              Последние операции по складу (приёмка, перемещение, отгрузка).
            </p>
            <button
              type="button"
              data-testid="global-movements-refresh"
              onClick={() => void onRefreshGlobalMovementsClick()}
            >
              Обновить
            </button>
            <ul
              className="list-plain"
              data-testid="global-movements-list"
              style={{ marginTop: 12 }}
            >
              {globalMovements.map((m) => (
                <li key={m.id} data-testid="global-movement-row">
                  {m.sku_code}: {m.quantity_delta > 0 ? '+' : ''}
                  {m.quantity_delta} · {m.movement_type}
                </li>
              ))}
            </ul>
          </section>
          {isFulfillmentAdmin ? (
          <section className="card" data-testid="stock-transfer-section">
            <h2>Перемещение между ячейками</h2>
            <p className="subtle">
              Списание с ячейки «откуда» и оприходование в «куда» на одном складе.
            </p>
            <form
              data-testid="stock-transfer-form"
              noValidate
              onSubmit={(e) => void onStockTransfer(e)}
            >
              <label>
                Откуда (ячейка)
                <select
                  name="transfer_from_loc"
                  data-testid="transfer-from-loc"
                  required
                  defaultValue=""
                >
                  <option value="" disabled>
                    Выберите
                  </option>
                  {locations.map((loc) => (
                    <option key={loc.id} value={loc.id}>
                      {loc.code}
                    </option>
                  ))}
                </select>
              </label>
              <label>
                Куда (ячейка)
                <select
                  name="transfer_to_loc"
                  data-testid="transfer-to-loc"
                  required
                  defaultValue=""
                >
                  <option value="" disabled>
                    Выберите
                  </option>
                  {locations.map((loc) => (
                    <option key={loc.id} value={loc.id}>
                      {loc.code}
                    </option>
                  ))}
                </select>
              </label>
              <label>
                Товар
                <select
                  name="transfer_product_id"
                  data-testid="transfer-product"
                  required
                  defaultValue=""
                >
                  <option value="" disabled>
                    SKU
                  </option>
                  {products.map((p) => (
                    <option key={p.id} value={p.id}>
                      {p.sku_code} — {p.name}
                    </option>
                  ))}
                </select>
              </label>
              <label>
                Количество
                <input
                  name="transfer_qty"
                  data-testid="transfer-qty"
                  type="number"
                  min={1}
                  required
                />
              </label>
              <button
                type="submit"
                data-testid="transfer-submit"
                disabled={opsBusy || locations.length < 2}
              >
                {opsBusy ? '…' : 'Переместить'}
              </button>
            </form>
          </section>
          ) : null}
          <section className="card" data-testid="outbound-section">
            <h2>Отгрузка</h2>
            <p className="subtle">
              Заявка на списание остатков из выбранных ячеек. Назначьте ячейку
              на строке; отгрузка по строке частями; «Провести весь остаток»
              списывает всё неотгруженное.
            </p>
            {canEditOutboundDraft ? (
            <form
              data-testid="outbound-create-form"
              noValidate
              onSubmit={(e) => void onCreateOutboundRequest(e)}
            >
              {isFulfillmentSeller && warehouses.length > 1 ? (
                <label style={{ display: 'block', marginBottom: 8 }}>
                  Склад для отгрузки
                  <select
                    name="outbound_warehouse_id"
                    data-testid="outbound-create-warehouse"
                    required
                    defaultValue=""
                  >
                    <option value="" disabled>
                      Выберите склад
                    </option>
                    {warehouses.map((w) => (
                      <option key={w.id} value={w.id}>
                        {w.code} — {w.name}
                      </option>
                    ))}
                  </select>
                </label>
              ) : null}
              <button
                type="submit"
                data-testid="outbound-create-submit"
                disabled={
                  opsBusy ||
                  warehouses.length === 0 ||
                  (!isFulfillmentSeller &&
                    !selectedWarehouseId &&
                    warehouses.length !== 1)
                }
              >
                {opsBusy ? '…' : 'Новая заявка на отгрузку'}
              </button>
            </form>
            ) : null}
            <ul className="list-plain" data-testid="outbound-requests-list">
              {outboundSummaries.map((row) => (
                <li key={row.id}>
                  <button
                    type="button"
                    data-testid="outbound-request-item"
                    data-status={row.status}
                    onClick={() => setSelectedOutboundId(row.id)}
                    style={{
                      width: '100%',
                      textAlign: 'left',
                      background:
                        row.id === selectedOutboundId
                          ? 'rgba(91, 79, 212, 0.12)'
                          : 'transparent',
                      border: '1px solid rgba(0,0,0,0.08)',
                      borderRadius: 8,
                      padding: '8px 10px',
                      cursor: 'pointer',
                    }}
                  >
                    <span data-testid="outbound-request-status">{row.status}</span>
                    {' · '}
                    строк: {row.line_count}
                  </button>
                </li>
              ))}
            </ul>
            {outboundDetail ? (
              <div data-testid="outbound-detail">
                <p className="subtle" data-testid="outbound-detail-status">
                  Статус: {outboundDetail.status}
                </p>
                <ul
                  className="list-plain"
                  data-testid="outbound-detail-lines"
                >
                  {outboundDetail.lines.map((ln) => (
                    <li
                      key={ln.id}
                      data-testid="outbound-detail-line"
                      data-line-id={ln.id}
                    >
                      {ln.product_name} ({ln.sku_code}) — отгружено{' '}
                      {ln.shipped_qty} из {ln.quantity}
                      {ln.storage_location_code
                        ? ` · ячейка: ${ln.storage_location_code}`
                        : ''}
                      {outboundDetail.status === 'draft' && isFulfillmentAdmin ? (
                        <button
                          type="button"
                          data-testid="outbound-line-delete"
                          disabled={opsBusy}
                          onClick={() => void onDeleteOutboundLine(ln.id)}
                        >
                          Удалить строку
                        </button>
                      ) : null}
                    </li>
                  ))}
                </ul>
                {outboundDetail.status === 'draft' && canEditOutboundDraft ? (
                  <form
                    data-testid="outbound-line-form"
                    noValidate
                    onSubmit={(e) => void onAddOutboundLine(e)}
                  >
                    <label>
                      Товар
                      <select
                        name="outbound_product_id"
                        data-testid="outbound-line-product"
                        required
                        defaultValue=""
                      >
                        <option value="" disabled>
                          Выберите SKU
                        </option>
                        {products.map((p) => (
                          <option key={p.id} value={p.id}>
                            {p.sku_code} — {p.name}
                          </option>
                        ))}
                      </select>
                    </label>
                    <label>
                      Количество, шт
                      <input
                        name="outbound_qty"
                        data-testid="outbound-line-qty"
                        type="number"
                        min={1}
                        required
                      />
                    </label>
                    {outboundRequestLocations.length > 0 ? (
                      <label>
                        Ячейка (необязательно)
                        <select
                          name="outbound_line_storage_id"
                          data-testid="outbound-line-location"
                          defaultValue=""
                        >
                          <option value="">— позже —</option>
                          {outboundRequestLocations.map((loc) => (
                            <option key={loc.id} value={loc.id}>
                              {loc.code}
                            </option>
                          ))}
                        </select>
                      </label>
                    ) : null}
                    <button
                      type="submit"
                      data-testid="outbound-line-submit"
                      disabled={opsBusy || products.length === 0}
                    >
                      {opsBusy ? '…' : 'Добавить строку'}
                    </button>
                  </form>
                ) : null}
                {outboundDetail.status === 'draft' &&
                outboundDetail.lines.length > 0 &&
                isFulfillmentAdmin ? (
                  <button
                    type="button"
                    data-testid="outbound-submit-request"
                    disabled={opsBusy}
                    onClick={() => void onSubmitOutboundRequest()}
                  >
                    {opsBusy ? '…' : 'Отправить заявку'}
                  </button>
                ) : null}
                {outboundDetail.status === 'submitted' ? (
                  <div data-testid="outbound-ship-panel">
                    <p className="subtle">Строки в работе</p>
                    {isFulfillmentAdmin ? (
                    <>
                    {outboundDetail.lines.map((ln) =>
                      ln.shipped_qty < ln.quantity ? (
                        <div
                          key={ln.id}
                          style={{
                            border: '1px solid rgba(0,0,0,0.08)',
                            borderRadius: 8,
                            padding: '10px 12px',
                            marginBottom: 10,
                          }}
                        >
                          <p className="subtle" style={{ marginTop: 0 }}>
                            {ln.sku_code} — осталось отгрузить{' '}
                            {ln.quantity - ln.shipped_qty} из {ln.quantity}
                          </p>
                          <form
                            data-testid="outbound-line-storage-form"
                            data-line-id={ln.id}
                            noValidate
                            onSubmit={(e) => void onSaveOutboundLineStorage(e)}
                          >
                            <label>
                              Ячейка отбора
                              <select
                                name="out_line_storage_id"
                                data-testid="outbound-line-storage-select"
                                defaultValue={ln.storage_location_id ?? ''}
                                required
                              >
                                <option value="" disabled>
                                  Выберите ячейку
                                </option>
                                {outboundRequestLocations.map((loc) => (
                                  <option key={loc.id} value={loc.id}>
                                    {loc.code}
                                  </option>
                                ))}
                              </select>
                            </label>
                            <button
                              type="submit"
                              data-testid="outbound-line-storage-save"
                              disabled={
                                opsBusy || outboundRequestLocations.length === 0
                              }
                            >
                              Сохранить ячейку
                            </button>
                          </form>
                          <form
                            data-testid="outbound-line-ship-form"
                            data-line-id={ln.id}
                            noValidate
                            onSubmit={(e) => void onShipOutboundLine(e)}
                          >
                            <label>
                              Отгрузить, шт
                              <input
                                name="ship_qty"
                                data-testid="outbound-line-ship-qty"
                                type="number"
                                min={1}
                                max={ln.quantity - ln.shipped_qty}
                                required
                              />
                            </label>
                            <button
                              type="submit"
                              data-testid="outbound-line-ship-submit"
                              disabled={opsBusy}
                            >
                              Отгрузить
                            </button>
                          </form>
                        </div>
                      ) : null,
                    )}
                    <button
                      type="button"
                      data-testid="outbound-post-submit"
                      disabled={opsBusy}
                      onClick={() => void onPostOutboundRequest()}
                    >
                      {opsBusy ? '…' : 'Провести весь остаток'}
                    </button>
                    </>
                    ) : (
                    <p className="subtle" data-testid="outbound-seller-read-only">
                      Отгрузку ведёт фулфилмент; доступен просмотр строк и
                      статуса.
                    </p>
                    )}
                  </div>
                ) : null}
                {outboundMovements.length > 0 ? (
                  <div data-testid="outbound-movements-block">
                    <p className="subtle">Движения по отгрузке</p>
                    <ul
                      className="list-plain"
                      data-testid="outbound-movements-list"
                    >
                      {outboundMovements.map((m) => (
                        <li
                          key={m.id}
                          data-testid="outbound-movement-row"
                        >
                          {m.quantity_delta} · {m.movement_type}
                        </li>
                      ))}
                    </ul>
                  </div>
                ) : null}
              </div>
            ) : null}
          </section>
        </div>
      </main>
    )
  }

  return (
    <main data-testid="app-root" className="shell">
      <header className="top">
        <h1>WMS</h1>
      </header>
      {error ? (
        <p className="error" data-testid="auth-error">
          {error}
        </p>
      ) : null}
      <div className="grid2">
        <section className="card">
          <h2>Регистрация фулфилмента</h2>
          <p className="hint">
            Slug — короткое имя на латинице (например <code>acme-ff</code>), без
            пробелов.
          </p>
          <form
            data-testid="register-form"
            noValidate
            onSubmit={(e) => void onRegister(e)}
          >
            <label>
              Организация
              <input name="organization_name" required />
            </label>
            <label>
              Slug (латиница)
              <input
                name="slug"
                data-testid="register-slug"
                required
                placeholder="acme-ff"
                autoComplete="off"
              />
            </label>
            <label>
              Email админа
              <input name="admin_email" type="email" required />
            </label>
            <label>
              Пароль
              <input name="password" type="password" minLength={8} required />
            </label>
            <button type="submit" disabled={authBusy}>
              {authBusy ? 'Отправка…' : 'Создать аккаунт'}
            </button>
          </form>
        </section>
        <section className="card">
          <h2>Вход</h2>
          <form
            data-testid="login-form"
            noValidate
            onSubmit={(e) => void onLogin(e)}
          >
            <label>
              Email
              <input name="email" type="email" required />
            </label>
            <label>
              Пароль
              <input name="password" type="password" required />
            </label>
            <button type="submit" disabled={authBusy}>
              {authBusy ? 'Вход…' : 'Войти'}
            </button>
          </form>
        </section>
      </div>
    </main>
  )
}
