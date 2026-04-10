import { useCallback, useEffect, useState } from 'react'
import './App.css'
import { apiUrl, getStoredToken, setStoredToken } from './api'

type Me = {
  email: string
  organization_name: string
  role: string
}

export default function App() {
  const [token, setToken] = useState<string | null>(() => getStoredToken())
  const [me, setMe] = useState<Me | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)

  const loadMe = useCallback(async (t: string) => {
    setLoading(true)
    setError(null)
    try {
      const res = await fetch(apiUrl('/auth/me'), {
        headers: { Authorization: `Bearer ${t}` },
      })
      if (!res.ok) {
        throw new Error(await res.text())
      }
      setMe((await res.json()) as Me)
    } catch {
      setStoredToken(null)
      setToken(null)
      setMe(null)
      setError('Сессия недействительна. Войдите снова.')
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
    const fd = new FormData(e.currentTarget)
    const body = {
      organization_name: String(fd.get('organization_name') ?? ''),
      slug: String(fd.get('slug') ?? ''),
      admin_email: String(fd.get('admin_email') ?? ''),
      password: String(fd.get('password') ?? ''),
    }
    const res = await fetch(apiUrl('/auth/register'), {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    })
    if (!res.ok) {
      setError('Регистрация не удалась (slug или email заняты).')
      return
    }
    const data = (await res.json()) as { access_token: string }
    setStoredToken(data.access_token)
    setToken(data.access_token)
  }

  async function onLogin(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault()
    setError(null)
    const fd = new FormData(e.currentTarget)
    const body = {
      email: String(fd.get('email') ?? ''),
      password: String(fd.get('password') ?? ''),
    }
    const res = await fetch(apiUrl('/auth/login'), {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    })
    if (!res.ok) {
      setError('Неверный email или пароль.')
      return
    }
    const data = (await res.json()) as { access_token: string }
    setStoredToken(data.access_token)
    setToken(data.access_token)
  }

  function onLogout() {
    setStoredToken(null)
    setToken(null)
    setMe(null)
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
      {loading ? <p data-testid="loading">Загрузка…</p> : null}
      {error ? (
        <p className="error" data-testid="auth-error">
          {error}
        </p>
      ) : null}
      <div className="grid2">
        <section className="card">
          <h2>Регистрация фулфилмента</h2>
          <form data-testid="register-form" onSubmit={(e) => void onRegister(e)}>
            <label>
              Организация
              <input name="organization_name" required />
            </label>
            <label>
              Slug (латиница)
              <input name="slug" data-testid="register-slug" required pattern="[a-z0-9-]+" />
            </label>
            <label>
              Email админа
              <input name="admin_email" type="email" required />
            </label>
            <label>
              Пароль
              <input name="password" type="password" minLength={8} required />
            </label>
            <button type="submit">Создать аккаунт</button>
          </form>
        </section>
        <section className="card">
          <h2>Вход</h2>
          <form data-testid="login-form" onSubmit={(e) => void onLogin(e)}>
            <label>
              Email
              <input name="email" type="email" required />
            </label>
            <label>
              Пароль
              <input name="password" type="password" required />
            </label>
            <button type="submit">Войти</button>
          </form>
        </section>
      </div>
    </main>
  )
}
