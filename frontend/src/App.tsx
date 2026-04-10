import { useCallback, useEffect, useState } from 'react'
import './App.css'
import { apiUrl, getStoredToken, setStoredToken } from './api'

type Me = {
  email: string
  organization_name: string
  role: string
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

  useEffect(() => {
    if (token) {
      void loadMe(token)
    } else {
      setMe(null)
    }
  }, [token, loadMe])

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
