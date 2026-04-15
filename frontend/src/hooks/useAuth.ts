import { useCallback, useEffect, useState } from 'react'
import { apiUrl, getStoredToken, setStoredToken } from '../api'
import { readApiErrorMessage } from '../utils/readApiErrorMessage'

export type Me = {
  email: string
  organization_name: string
  role: string
  seller_id?: string | null
  seller_name?: string | null
}

type RegisterFormEvent = React.FormEvent<HTMLFormElement>

export function useAuth() {
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
        throw new Error(`Не удалось загрузить профиль (${res.status}). ${msg}`)
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

  const onRegister = useCallback(async (e: RegisterFormEvent) => {
    e.preventDefault()
    setError(null)
    setAuthBusy(true)
    try {
      const fd = new FormData(e.currentTarget)
      const rawSlug = String(fd.get('slug') ?? '').trim()
      const slug = rawSlug.toLowerCase().replace(/\s+/g, '-')
      const password = String(fd.get('password') ?? '')
      // Локальная подсказка, но финальная валидация на сервере.
      if (slug.length < 2) {
        setError('Slug слишком короткий (минимум 2 символа, латиница и дефис).')
      } else if (!/^[a-z0-9-]+$/.test(slug)) {
        setError(
          'Slug: только строчные латинские буквы, цифры и дефис (например my-fulfillment).',
        )
      }
      if (password.length > 0 && password.length < 8) {
        setError('Пароль: минимум 8 символов.')
      }
      const body = {
        organization_name: String(fd.get('organization_name') ?? '').trim(),
        slug,
        admin_email: String(fd.get('admin_email') ?? '').trim(),
        password,
      }
      const res = await fetch(apiUrl('/auth/register'), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      })
      if (!res.ok) {
        if (res.status === 409) {
          setError('Такой slug или email уже заняты. Выберите другие.')
        } else {
          const msg = await readApiErrorMessage(res)
          setError(
            res.status === 422
              ? `Проверьте поля: ${msg}`
              : msg,
          )
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
  }, [])

  const onLogin = useCallback(async (e: RegisterFormEvent) => {
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
  }, [])

  const logout = useCallback(() => {
    setStoredToken(null)
    setToken(null)
    setMe(null)
    setError(null)
  }, [])

  return { token, me, error, loading, authBusy, onRegister, onLogin, logout }
}

