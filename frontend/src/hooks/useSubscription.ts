import { useCallback, useEffect, useState } from 'react'
import { apiUrl } from '../api'

export type Subscription = {
  enabled: boolean
  paid_until: string | null
  days_left: number | null
  blocked: boolean
  price_rub: number
  payment_available: boolean
}

/** WMS-381: состояние подписки организации. */
export function useSubscription(token: string | null) {
  const [subscription, setSubscription] = useState<Subscription | null>(null)
  const [loaded, setLoaded] = useState(false)

  const reload = useCallback(async () => {
    if (!token) {
      setSubscription(null)
      setLoaded(false)
      return
    }
    try {
      const res = await fetch(apiUrl('/subscription'), {
        headers: { Authorization: `Bearer ${token}` },
      })
      if (!res.ok) {
        // Недоступная ручка не должна запирать работающий склад: считаем, что
        // ограничений нет, и пускаем человека работать.
        setSubscription(null)
        return
      }
      setSubscription((await res.json()) as Subscription)
    } catch {
      setSubscription(null)
    } finally {
      setLoaded(true)
    }
  }, [token])

  useEffect(() => {
    void reload()
  }, [reload])

  /** Создать платёж и увести человека на страницу оплаты ЮKassa. */
  const startPayment = useCallback(async (): Promise<string | null> => {
    if (!token) {
      return 'Нужно войти заново.'
    }
    try {
      const res = await fetch(apiUrl('/subscription/pay'), {
        method: 'POST',
        headers: { Authorization: `Bearer ${token}` },
      })
      if (!res.ok) {
        if (res.status === 403) {
          return 'Оплатить подписку может только администратор организации.'
        }
        if (res.status === 409) {
          return 'Оплата картой пока не подключена. Свяжитесь с фулфилментом.'
        }
        return 'ЮKassa не ответила. Попробуйте ещё раз через минуту.'
      }
      const data = (await res.json()) as { confirmation_url: string }
      window.location.href = data.confirmation_url
      return null
    } catch {
      return 'Сеть: не удалось создать платёж. Попробуйте ещё раз.'
    }
  }, [token])

  /** Спросить у ЮKassa, прошла ли оплата. */
  const syncPayment = useCallback(async (): Promise<boolean> => {
    if (!token) {
      return false
    }
    try {
      const res = await fetch(apiUrl('/subscription/sync'), {
        method: 'POST',
        headers: { Authorization: `Bearer ${token}` },
      })
      if (!res.ok) {
        return false
      }
      const data = (await res.json()) as { activated: boolean }
      await reload()
      return data.activated
    } catch {
      return false
    }
  }, [token, reload])

  return {
    subscription,
    subscriptionLoaded: loaded,
    reloadSubscription: reload,
    startPayment,
    syncPayment,
  }
}

/** Склонение слова «день» для остатка подписки. */
export function daysWord(days: number): string {
  const mod100 = days % 100
  if (mod100 >= 11 && mod100 <= 14) {
    return 'дней'
  }
  switch (days % 10) {
    case 1:
      return 'день'
    case 2:
    case 3:
    case 4:
      return 'дня'
    default:
      return 'дней'
  }
}
