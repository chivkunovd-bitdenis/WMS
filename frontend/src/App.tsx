import { useCallback, useEffect, useState } from 'react'
import './App.css'
import { apiUrl, getStoredToken, setStoredToken } from './api'

type Me = {
  email: string
  organization_name: string
  role: string
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
}

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
}

type InboundDetailRow = {
  id: string
  warehouse_id: string
  status: string
  lines: InboundLineRow[]
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
  const [postingLocations, setPostingLocations] = useState<LocationRow[]>([])
  const [postedInventoryRows, setPostedInventoryRows] = useState<
    {
      product_id: string
      sku_code: string
      product_name: string
      quantity: number
    }[]
  >([])

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
      const res = await fetch(
        apiUrl(`/operations/inbound-intake-requests/${requestId}`),
        { headers: authHeaders(t) },
      )
      if (!res.ok) {
        throw new Error(await readApiErrorMessage(res))
      }
      setInboundDetail((await res.json()) as InboundDetailRow)
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
      setSelectedWarehouseId(null)
      setInboundSummaries([])
      setSelectedInboundId(null)
      setInboundDetail(null)
      setPostingLocations([])
      setPostedInventoryRows([])
      setCatalogError(null)
      setOpsError(null)
      return
    }
    setCatalogError(null)
    setOpsError(null)
    void (async () => {
      try {
        await refreshWarehouses(token)
        await refreshProducts(token)
      } catch (e) {
        setCatalogError(
          e instanceof Error ? e.message : 'Не удалось загрузить каталог.',
        )
      }
    })()
    void (async () => {
      try {
        await refreshInboundList(token)
      } catch (e) {
        setOpsError(
          e instanceof Error ? e.message : 'Не удалось загрузить заявки.',
        )
      }
    })()
  }, [token, me, refreshWarehouses, refreshProducts, refreshInboundList])

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
    setPostedInventoryRows([])
  }, [selectedInboundId])

  useEffect(() => {
    if (!token || !inboundDetail || inboundDetail.status !== 'submitted') {
      setPostingLocations([])
      return
    }
    void (async () => {
      try {
        const res = await fetch(
          apiUrl(`/warehouses/${inboundDetail.warehouse_id}/locations`),
          { headers: authHeaders(token) },
        )
        if (!res.ok) {
          setPostingLocations([])
          return
        }
        setPostingLocations((await res.json()) as LocationRow[])
      } catch {
        setPostingLocations([])
      }
    })()
  }, [
    token,
    inboundDetail?.id,
    inboundDetail?.status,
    inboundDetail?.warehouse_id,
    authHeaders,
  ])

  useEffect(() => {
    if (!token || !selectedWarehouseId) {
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
  }, [token, selectedWarehouseId, refreshLocations])

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
    setPostingLocations([])
    setPostedInventoryRows([])
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
      const res = await fetch(apiUrl('/products'), {
        method: 'POST',
        headers: {
          ...authHeaders(token),
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          name,
          sku_code,
          length_mm,
          width_mm,
          height_mm,
        }),
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
    if (!token) {
      return
    }
    setOpsError(null)
    setOpsBusy(true)
    try {
      const warehouseId =
        selectedWarehouseId ??
        (warehouses.length === 1 ? warehouses[0]!.id : null)
      if (!warehouseId) {
        setOpsError('Выберите склад в списке выше.')
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
          body: JSON.stringify({ product_id, expected_qty }),
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

  async function onPostInboundRequest(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault()
    const form = e.currentTarget
    if (!token || !selectedInboundId) {
      return
    }
    setOpsError(null)
    setOpsBusy(true)
    try {
      const fd = new FormData(form)
      const storage_location_id = String(
        fd.get('inbound_post_location_id') ?? '',
      )
      const res = await fetch(
        apiUrl(
          `/operations/inbound-intake-requests/${selectedInboundId}/post`,
        ),
        {
          method: 'POST',
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
      await refreshInboundList(token)
      await refreshInboundDetail(token, selectedInboundId)
      const br = await fetch(
        apiUrl(
          `/operations/inventory-balances?storage_location_id=${encodeURIComponent(storage_location_id)}`,
        ),
        { headers: authHeaders(token) },
      )
      if (br.ok) {
        setPostedInventoryRows(
          (await br.json()) as {
            product_id: string
            sku_code: string
            product_name: string
            quantity: number
          }[],
        )
      }
    } catch (e) {
      setOpsError(
        e instanceof Error ? e.message : 'Не удалось провести приёмку.',
      )
    } finally {
      setOpsBusy(false)
    }
  }

  if (token && me) {
    return (
      <main data-testid="app-root" className="shell">
        <header className="top">
          <h1>WMS</h1>
          <button type="button" data-testid="logout" onClick={onLogout}>
            Выйти
          </button>
        </header>
        <section className="card" data-testid="dashboard">
          <p data-testid="user-email">{me.email}</p>
          <p data-testid="org-name">{me.organization_name}</p>
          <p data-testid="user-role">{me.role}</p>
        </section>
        <div className="stack" data-testid="catalog-section">
          {catalogError ? (
            <p className="error" data-testid="catalog-error">
              {catalogError}
            </p>
          ) : null}
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
          <section className="card">
            <h2>Товары (SKU)</h2>
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
              <button
                type="submit"
                data-testid="product-submit"
                disabled={catalogBusy}
              >
                {catalogBusy ? '…' : 'Добавить товар'}
              </button>
            </form>
            <ul className="list-plain" data-testid="product-list">
              {products.map((p) => (
                <li key={p.id} data-testid="product-item">
                  <strong>{p.name}</strong> — {p.sku_code},{' '}
                  <span data-testid="product-volume">
                    {p.volume_liters.toFixed(1)} л
                  </span>
                </li>
              ))}
            </ul>
          </section>
        </div>
        <div className="stack" data-testid="operations-section">
          {opsError ? (
            <p className="error" data-testid="operations-error">
              {opsError}
            </p>
          ) : null}
          <section className="card">
            <h2>Приёмка</h2>
            <p className="subtle">
              Заявка создаётся для выбранного склада. Остатки в ячейке
              появляются после проведения (все строки заявки в одну выбранную
              ячейку).
            </p>
            <form
              data-testid="inbound-create-form"
              noValidate
              onSubmit={(e) => void onCreateInboundRequest(e)}
            >
              <button
                type="submit"
                data-testid="inbound-create-submit"
                disabled={
                  opsBusy ||
                  (!selectedWarehouseId && warehouses.length !== 1)
                }
              >
                {opsBusy ? '…' : 'Новая заявка на приёмку'}
              </button>
            </form>
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
                      {ln.product_name} ({ln.sku_code}) — {ln.expected_qty} шт
                    </li>
                  ))}
                </ul>
                {inboundDetail.status === 'draft' ? (
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
                inboundDetail.lines.length > 0 ? (
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
                  <form
                    data-testid="inbound-post-form"
                    noValidate
                    onSubmit={(e) => void onPostInboundRequest(e)}
                  >
                    <label>
                      Ячейка для оприходования
                      <select
                        name="inbound_post_location_id"
                        data-testid="inbound-post-location"
                        required
                        defaultValue=""
                      >
                        <option value="" disabled>
                          Выберите ячейку
                        </option>
                        {postingLocations.map((loc) => (
                          <option key={loc.id} value={loc.id}>
                            {loc.code}
                          </option>
                        ))}
                      </select>
                    </label>
                    <button
                      type="submit"
                      data-testid="inbound-post-submit"
                      disabled={opsBusy || postingLocations.length === 0}
                    >
                      {opsBusy ? '…' : 'Провести приёмку'}
                    </button>
                  </form>
                ) : null}
                {postedInventoryRows.length > 0 ? (
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
                      </li>
                    ))}
                  </ul>
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
      {token && loading ? (
        <p data-testid="loading">Загрузка профиля…</p>
      ) : null}
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
