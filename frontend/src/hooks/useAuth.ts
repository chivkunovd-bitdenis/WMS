import { useCallback, useEffect, useState } from 'react'
import {
  apiUrl,
  getStoredToken,
  setStoredToken,
} from '../api'
import { readApiErrorMessage } from '../utils/readApiErrorMessage'
import { buildAutoTenantSlug } from '../utils/tenantSlug'

import {
  isFfPortalRole,
  type FfPermissions,
} from '../utils/ffPermissions'

export type Me = {
  email: string
  organization_name: string
  role: string
  seller_id?: string | null
  seller_name?: string | null
  home_seller_id?: string | null
  home_seller_name?: string | null
  active_seller_id?: string | null
  active_seller_name?: string | null
  can_manage_seller_shops?: boolean
  switchable_shops?: {
    id: string
    name: string
    enabled?: boolean
    is_home?: boolean
  }[]
  delegatable_shops?: {
    id: string
    name: string
    enabled?: boolean
    is_home?: boolean
  }[]
  permissions?: FfPermissions | null
  address_storage_enabled?: boolean
  separate_marking_print_enabled?: boolean
}

export type AuthPortal = 'fulfillment' | 'seller'

type RegisterFormEvent = React.FormEvent<HTMLFormElement>

export function useAuth(portal: AuthPortal = 'fulfillment') {
  const [token, setToken] = useState<string | null>(() => getStoredToken(portal))
  const [portalMismatch, setPortalMismatch] = useState<string | null>(null)
  const [me, setMe] = useState<Me | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)
  const [authBusy, setAuthBusy] = useState(false)
  const [pendingPasswordSetupEmail, setPendingPasswordSetupEmail] = useState<
    string | null
  >(null)

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
      setStoredToken(null, portal)
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
  }, [portal])

  useEffect(() => {
    if (token) {
      void loadMe(token)
    } else {
      setMe(null)
    }
  }, [token, loadMe])

  useEffect(() => {
    if (!me) {
      return
    }
    if (portal === 'seller' && me.role !== 'fulfillment_seller') {
      const msg =
        'Этот адрес только для селлера. Войдите email селлера (не админа ФФ). Портал фулфилмента: главная страница без /seller/.'
      setPortalMismatch(msg)
      setError(msg)
      setStoredToken(null, 'seller')
      setToken(null)
      setMe(null)
      return
    }
    if (portal === 'fulfillment' && me.role === 'fulfillment_seller') {
      const msg =
        'Этот портал для сотрудников фулфилмента. Селлеру: откройте /seller/ и войдите там (отдельный вход).'
      setPortalMismatch(msg)
      setError(msg)
      setStoredToken(null, 'fulfillment')
      setToken(null)
      setMe(null)
      return
    }
    if (portal === 'fulfillment' && !isFfPortalRole(me.role)) {
      const msg = 'Этот портал только для сотрудников фулфилмента.'
      setPortalMismatch(msg)
      setError(msg)
      setStoredToken(null, 'fulfillment')
      setToken(null)
      setMe(null)
      return
    }
    setPortalMismatch(null)
  }, [me, portal])

  const onCancelPasswordSetup = useCallback(() => {
    setPendingPasswordSetupEmail(null)
    setError(null)
  }, [])

  const onRegister = useCallback(async (e: RegisterFormEvent) => {
    e.preventDefault()
    setError(null)
    setAuthBusy(true)
    const fd = new FormData(e.currentTarget)
    const organization_name = String(fd.get('organization_name') ?? '').trim()
    const admin_email = String(fd.get('admin_email') ?? '').trim()
    const password = String(fd.get('password') ?? '')
    try {
      if (!organization_name) {
        setError('Укажите название организации.')
        return
      }
      if (!admin_email) {
        setError('Укажите email администратора.')
        return
      }
      if (password.length < 8) {
        setError('Пароль: минимум 8 символов.')
        return
      }

      const maxSlugAttempts = 4
      for (let attempt = 0; attempt < maxSlugAttempts; attempt++) {
        const slug =
          attempt === 0
            ? buildAutoTenantSlug(organization_name)
            : buildAutoTenantSlug(`${organization_name} ${attempt}`)
        const body = {
          organization_name,
          slug,
          admin_email,
          password,
        }
        const res = await fetch(apiUrl('/auth/register'), {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(body),
        })
        if (res.ok) {
          const data = (await res.json()) as { access_token: string }
          if (!data.access_token) {
            setError('Сервер не вернул токен. Обратитесь к разработчику.')
            return
          }
          setStoredToken(data.access_token, portal)
          setToken(data.access_token)
          return
        }
        if (res.status === 409) {
          if (attempt + 1 < maxSlugAttempts) {
            continue
          }
          setError(
            'Такой email уже занят или не удалось выделить код организации. Попробуйте другой email.',
          )
          return
        }
        const msg = await readApiErrorMessage(res)
        setError(res.status === 422 ? `Проверьте поля: ${msg}` : msg)
        return
      }
    } catch {
      setError(
        'Сеть: не удалось достучаться до API. Проверьте адрес и что контейнер api запущен.',
      )
    } finally {
      setAuthBusy(false)
    }
  }, [portal])

  const onLogin = useCallback(
    async (e: RegisterFormEvent) => {
      e.preventDefault()
      setError(null)
      setPendingPasswordSetupEmail(null)
      setAuthBusy(true)
      try {
        const fd = new FormData(e.currentTarget)
        const email = String(fd.get('email') ?? '').trim()
        const password = String(fd.get('password') ?? '')
        if (!email) {
          setError('Укажите email.')
          return
        }
        const res = await fetch(apiUrl('/auth/login'), {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ email, password }),
        })
        if (res.status === 403) {
          const text = await res.text()
          try {
            const j = JSON.parse(text) as { detail?: string }
            if (j.detail === 'password_setup_required') {
              setPendingPasswordSetupEmail(email)
              return
            }
            setError(
              typeof j.detail === 'string' ? j.detail : 'Доступ запрещён.',
            )
          } catch {
            setError(text ? text.slice(0, 200) : 'Доступ запрещён.')
          }
          return
        }
        if (!res.ok) {
          if (res.status === 401) {
            setError('Неверный email или пароль.')
          } else {
            setError(await readApiErrorMessage(res))
          }
          return
        }
        const data = (await res.json()) as { access_token: string }
        setStoredToken(data.access_token, portal)
        setPortalMismatch(null)
        setToken(data.access_token)
      } catch {
        setError(
          'Сеть: не удалось достучаться до API. Проверьте, что контейнер api запущен.',
        )
      } finally {
        setAuthBusy(false)
      }
    },
    [portal],
  )

  const onSetInitialPassword = useCallback(
    async (e: RegisterFormEvent) => {
      e.preventDefault()
      if (!pendingPasswordSetupEmail) {
        return
      }
      setError(null)
      setAuthBusy(true)
      const fd = new FormData(e.currentTarget)
      const password = String(fd.get('new_password') ?? '')
      const password2 = String(fd.get('new_password_confirm') ?? '')
      try {
        if (password.length < 8) {
          setError('Пароль: минимум 8 символов.')
          return
        }
        if (password !== password2) {
          setError('Пароли не совпадают.')
          return
        }
        const res = await fetch(apiUrl('/auth/set-initial-password'), {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            email: pendingPasswordSetupEmail,
            password,
          }),
        })
        if (!res.ok) {
          setError(await readApiErrorMessage(res))
          return
        }
        const data = (await res.json()) as { access_token: string }
        setPendingPasswordSetupEmail(null)
        setStoredToken(data.access_token, portal)
        setPortalMismatch(null)
        setToken(data.access_token)
      } catch {
        setError(
          'Сеть: не удалось достучаться до API. Проверьте, что контейнер api запущен.',
        )
      } finally {
        setAuthBusy(false)
      }
    },
    [pendingPasswordSetupEmail, portal],
  )

  const logout = useCallback(() => {
    setStoredToken(null, portal)
    setToken(null)
    setMe(null)
    setError(null)
    setPortalMismatch(null)
    setPendingPasswordSetupEmail(null)
  }, [portal])

  const applyToken = useCallback(
    (nextToken: string) => {
      setStoredToken(nextToken, portal)
      setPortalMismatch(null)
      setToken(nextToken)
    },
    [portal],
  )

  const reloadMe = useCallback(
    async (overrideToken?: string | null) => {
      const t = overrideToken ?? token
      if (!t) {
        return null
      }
      await loadMe(t)
      return t
    },
    [loadMe, token],
  )

  return {
    token,
    me,
    portalMismatch,
    error,
    loading,
    authBusy,
    pendingPasswordSetupEmail,
    onRegister,
    onLogin,
    onSetInitialPassword,
    onCancelPasswordSetup,
    logout,
    applyToken,
    reloadMe,
  }
}
