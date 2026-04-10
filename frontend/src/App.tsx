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
      setCatalogError(null)
      return
    }
    setCatalogError(null)
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
  }, [token, me, refreshWarehouses, refreshProducts])

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
