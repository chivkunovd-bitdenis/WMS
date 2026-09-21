import { useCallback, useEffect, useRef, useState } from 'react'
import {
  apiUrl,
  getStoredToken,
  isAuthTokenStorageKey,
  setStoredToken,
} from '../api'
import { readApiErrorMessage } from '../utils/readApiErrorMessage'
import { buildAutoTenantSlug } from '../utils/tenantSlug'

import {
  isFfPortalRole,
  type FfPermissions,
} from '../utils/ffPermissions'
import type { SellerPermissions } from '../utils/sellerPermissions'

export type Me = {
  id: string
  email: string | null
  full_name?: string | null
  job_title?: string | null
  display_name: string
  organization_name: string
  organization_slug?: string
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
  seller_permissions?: SellerPermissions | null
  address_storage_enabled?: boolean
  separate_marking_print_enabled?: boolean
  fbs_shipment_cutoff_time?: string | null
}

export type AuthPortal = 'fulfillment' | 'seller'

type RegisterFormEvent = React.FormEvent<HTMLFormElement>

export function nameLoginPayload(fullName: string, password: string, organization: string) {
  return { full_name: fullName, password, organization: organization.trim() || undefined }
}

export type SessionProfileResult =
  | { outcome: 'stale' }
  | { outcome: 'loaded'; me: Me }
  | { outcome: 'unauthorized'; message: string }
  | { outcome: 'failed'; message: string }

/**
 * Профиль применяется, только если к моменту ответа сессия осталась прежней.
 *
 * WMS-488: вкладку могли переключить на другого селлера или закрыть сессию,
 * пока ответ шёл. Такой ответ описывает прежнего пользователя — ни профиль,
 * ни его 401 к новой сессии отношения не имеют.
 */
export async function loadSessionProfile(
  token: string,
  isSessionToken: (candidate: string) => boolean,
): Promise<SessionProfileResult> {
  try {
    const res = await fetch(apiUrl('/auth/me'), {
      headers: { Authorization: `Bearer ${token}` },
    })
    if (!isSessionToken(token)) {
      return { outcome: 'stale' }
    }
    if (!res.ok) {
      const msg = await readApiErrorMessage(res)
      if (!isSessionToken(token)) {
        return { outcome: 'stale' }
      }
      if (res.status === 401) {
        return {
          outcome: 'unauthorized',
          message: `Не удалось загрузить профиль (401). ${msg}. Попробуйте войти снова.`,
        }
      }
      return {
        outcome: 'failed',
        message: `Не удалось загрузить профиль (${res.status}). ${msg}`,
      }
    }
    const me = (await res.json()) as Me
    if (!isSessionToken(token)) {
      return { outcome: 'stale' }
    }
    return { outcome: 'loaded', me }
  } catch (e) {
    if (!isSessionToken(token)) {
      return { outcome: 'stale' }
    }
    return {
      outcome: 'failed',
      message:
        e instanceof Error
          ? e.message
          : 'Не удалось связаться с сервером. Проверьте, что API запущен.',
    }
  }
}

/**
 * Ответ принадлежит текущей сессии портала, только если с ним согласны и сама
 * вкладка, и общее хранилище.
 *
 * WMS-488: соседняя вкладка пишет новый токен в localStorage сразу, а событие
 * storage до нас доходит позже. В этом промежутке вкладка ещё помнит прежнего
 * пользователя, и ответ на его запрос выглядит «своим». Если сверяться только
 * с памятью вкладки, чужой 401 сотрёт уже записанную чужую сессию.
 */
export function isCurrentSessionToken(params: {
  candidate: string
  sessionToken: string | null
  storedToken: string | null
}): boolean {
  return params.sessionToken === params.candidate && params.storedToken === params.candidate
}

/** Сообщение о том, что роль пользователя не подходит порталу; null — подходит. */
export function portalRoleMismatchMessage(portal: AuthPortal, role: string): string | null {
  if (portal === 'seller' && role !== 'fulfillment_seller') {
    return 'Этот адрес только для селлера. Войдите email селлера (не админа ФФ). Портал фулфилмента: главная страница без /seller/.'
  }
  if (portal === 'fulfillment' && role === 'fulfillment_seller') {
    return 'Этот портал для сотрудников фулфилмента. Селлеру: откройте /seller/ и войдите там (отдельный вход).'
  }
  if (portal === 'fulfillment' && !isFfPortalRole(role)) {
    return 'Этот портал только для сотрудников фулфилмента.'
  }
  return null
}

export type StorageSessionChange =
  | { changed: false }
  | { changed: true; token: string | null }

/**
 * Решение вкладки по событию storage из соседней вкладки (WMS-488).
 *
 * Токен портала лежит в общем для вкладок localStorage, поэтому вход, смена
 * магазина и выход в одной вкладке меняют сессию всех остальных.
 */
export function sessionChangeFromStorage(params: {
  eventKey: string | null
  portal: AuthPortal
  sessionToken: string | null
  storedToken: string | null
}): StorageSessionChange {
  if (!isAuthTokenStorageKey(params.eventKey, params.portal)) {
    return { changed: false }
  }
  if (params.storedToken === params.sessionToken) {
    return { changed: false }
  }
  return { changed: true, token: params.storedToken }
}

export function useAuth(portal: AuthPortal = 'fulfillment') {
  const [token, setToken] = useState<string | null>(() => getStoredToken(portal))
  const [portalMismatch, setPortalMismatch] = useState<string | null>(null)
  // Профиль хранится вместе с токеном, которому он принадлежит: проверка роли
  // выполняется позже ответа, и к этому моменту сессия портала может быть уже
  // другой — закрывать её из-за роли прежнего пользователя нельзя (WMS-488).
  const [profile, setProfile] = useState<{ token: string; me: Me } | null>(null)
  const me = profile?.me ?? null
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)
  const [authBusy, setAuthBusy] = useState(false)
  const [notice, setNotice] = useState<string | null>(null)

  // Токен текущей сессии вкладки, доступный синхронно: по нему отличаем свой
  // ответ от ответа прежней сессии, не дожидаясь перерисовки.
  const sessionTokenRef = useRef<string | null>(token)

  const isSessionToken = useCallback(
    (candidate: string) => isCurrentSessionToken({
      candidate,
      sessionToken: sessionTokenRef.current,
      storedToken: getStoredToken(portal),
    }),
    [portal],
  )

  const startSession = useCallback((next: string | null) => {
    sessionTokenRef.current = next
    setToken(next)
  }, [])

  // Переход на сессию, которая уже лежит в хранилище портала. Нужен и при
  // событии storage, и когда устаревший ответ первым обнаружил подмену: просто
  // промолчать нельзя — вкладка осталась бы с профилем прежнего пользователя.
  const adoptStoredSession = useCallback(() => {
    const stored = getStoredToken(portal)
    if (stored === sessionTokenRef.current) {
      return false
    }
    setProfile(null)
    setError(null)
    setNotice(null)
    setPortalMismatch(null)
    startSession(stored)
    return true
  }, [portal, startSession])

  // Сессию закрывает только тот ответ, чей токен всё ещё принадлежит порталу.
  // Чужую сессию, записанную соседней вкладкой, вместо удаления принимаем.
  const endSessionForToken = useCallback(
    (requestToken: string, message: string) => {
      if (!isSessionToken(requestToken)) {
        adoptStoredSession()
        return false
      }
      setStoredToken(null, portal)
      startSession(null)
      setProfile(null)
      setError(message)
      return true
    },
    [adoptStoredSession, isSessionToken, portal, startSession],
  )

  const loadMe = useCallback(
    async (t: string) => {
      setLoading(true)
      setError(null)
      const result = await loadSessionProfile(t, isSessionToken)
      if (result.outcome === 'stale') {
        // Сессия уже другая: и профиль, и флаг загрузки принадлежат её запросу.
        adoptStoredSession()
        return
      }
      setLoading(false)
      if (result.outcome === 'loaded') {
        setProfile({ token: t, me: result.me })
        return
      }
      if (result.outcome === 'unauthorized') {
        endSessionForToken(t, result.message)
        return
      }
      setProfile(null)
      setError(result.message)
    },
    [adoptStoredSession, endSessionForToken, isSessionToken],
  )

  useEffect(() => {
    if (token) {
      void loadMe(token)
    } else {
      setProfile(null)
      setLoading(false)
    }
  }, [token, loadMe])

  useEffect(() => {
    const onStorage = (event: StorageEvent) => {
      if (event.storageArea && event.storageArea !== window.localStorage) {
        return
      }
      const change = sessionChangeFromStorage({
        eventKey: event.key,
        portal,
        sessionToken: sessionTokenRef.current,
        storedToken: getStoredToken(portal),
      })
      if (!change.changed) {
        return
      }
      // WMS-488: в соседней вкладке сменили пользователя или вышли. Профиль и
      // всё, что построено на нём (каталог, документы, остатки), снимаем сразу
      // — до того, как сервер подтвердит новую личность.
      adoptStoredSession()
    }
    window.addEventListener('storage', onStorage)
    return () => window.removeEventListener('storage', onStorage)
  }, [portal, adoptStoredSession])

  useEffect(() => {
    if (!profile) {
      return
    }
    const mismatch = portalRoleMismatchMessage(portal, profile.me.role)
    if (!mismatch) {
      setPortalMismatch(null)
      return
    }
    // Роль проверяется у того пользователя, чьему токену принадлежит профиль:
    // сессию соседней вкладки неподходящая роль прежнего входа не закрывает.
    if (endSessionForToken(profile.token, mismatch)) {
      setPortalMismatch(mismatch)
    }
  }, [profile, portal, endSessionForToken])

  const clearNotice = useCallback(() => {
    setNotice(null)
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
          startSession(data.access_token)
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
  }, [portal, startSession])

  const onLogin = useCallback(
    async (e: RegisterFormEvent) => {
      e.preventDefault()
      setError(null)
      setNotice(null)
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
              setError(
                'Пароль ещё не задан. Мы отправили ссылку на эту почту — откройте письмо и задайте пароль. Письма нет — нажмите «Забыли пароль».',
              )
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
            setError('Неверные данные для входа.')
          } else {
            setError(await readApiErrorMessage(res))
          }
          return
        }
        const data = (await res.json()) as { access_token: string }
        setStoredToken(data.access_token, portal)
        setPortalMismatch(null)
        startSession(data.access_token)
      } catch {
        setError(
          'Сеть: не удалось достучаться до API. Проверьте, что контейнер api запущен.',
        )
      } finally {
        setAuthBusy(false)
      }
    },
    [portal, startSession],
  )

  const onSetPasswordByLink = useCallback(
    async (e: RegisterFormEvent, linkToken: string) => {
      e.preventDefault()
      setError(null)
      setNotice(null)
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
        const res = await fetch(apiUrl('/auth/set-password'), {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ token: linkToken, password }),
        })
        if (!res.ok) {
          if (res.status === 410) {
            setError('Ссылка устарела. Запросите новую через «Забыли пароль».')
            return
          }
          if (res.status === 409) {
            setError('По этой ссылке пароль уже задан. Войдите обычным способом.')
            return
          }
          if (res.status === 400) {
            setError('Ссылка не подходит. Запросите новую через «Забыли пароль».')
            return
          }
          setError(await readApiErrorMessage(res))
          return
        }
        const data = (await res.json()) as { access_token: string }
        setStoredToken(data.access_token, portal)
        setPortalMismatch(null)
        startSession(data.access_token)
        // Человек пришёл на /set-password из письма. Оставить его на этом
        // адресе нельзя: в приложении такого экрана нет, и он упрётся в «Нет
        // доступа». Перекладываем на корень своего портала.
        if (typeof window !== 'undefined') {
          window.location.replace(portal === 'seller' ? '/seller/' : '/')
        }
      } catch {
        setError(
          'Сеть: не удалось достучаться до API. Проверьте, что контейнер api запущен.',
        )
      } finally {
        setAuthBusy(false)
      }
    },
    [portal, startSession],
  )

  const onRequestPasswordReset = useCallback(async (e: RegisterFormEvent) => {
    e.preventDefault()
    setError(null)
    setNotice(null)
    setAuthBusy(true)
    try {
      const fd = new FormData(e.currentTarget)
      const email = String(fd.get('reset_email') ?? '').trim()
      if (!email) {
        setError('Укажите email.')
        return
      }
      const res = await fetch(apiUrl('/auth/request-password-reset'), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email }),
      })
      if (!res.ok && res.status !== 204) {
        setError(await readApiErrorMessage(res))
        return
      }
      // Ответ одинаковый для любой почты — намеренно, чтобы форма не работала
      // как проверялка чужих адресов.
      setNotice(
        'Если такая почта есть в системе, письмо со ссылкой уже отправлено. Проверьте входящие и «Спам».',
      )
    } catch {
      setError(
        'Сеть: не удалось достучаться до API. Проверьте, что контейнер api запущен.',
      )
    } finally {
      setAuthBusy(false)
    }
  }, [])

  const logout = useCallback(() => {
    setStoredToken(null, portal)
    startSession(null)
    setProfile(null)
    setError(null)
    setPortalMismatch(null)
    setNotice(null)
  }, [portal, startSession])

  const applyToken = useCallback(
    (nextToken: string) => {
      setStoredToken(nextToken, portal)
      setPortalMismatch(null)
      startSession(nextToken)
    },
    [portal, startSession],
  )

  const updateProfile = useCallback(
    async (fields: { full_name: string; job_title: string }) => {
      if (!token) {
        throw new Error('Сессия не найдена. Войдите снова.')
      }
      const res = await fetch(apiUrl('/auth/me'), {
        method: 'PATCH',
        headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' },
        body: JSON.stringify(fields),
      })
      if (!res.ok) {
        throw new Error(await readApiErrorMessage(res))
      }
      const next = (await res.json()) as Me
      if (isSessionToken(token)) {
        setProfile({ token, me: next })
      }
      return next
    },
    [isSessionToken, token],
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
    notice,
    onRegister,
    onLogin,
    onSetPasswordByLink,
    onRequestPasswordReset,
    clearNotice,
    logout,
    applyToken,
    updateProfile,
    reloadMe,
  }
}
