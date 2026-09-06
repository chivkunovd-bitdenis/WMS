import { useCallback, useEffect, useState } from 'react'
import { apiUrl } from '../api'

export type Subscription = {
  enabled: boolean
  paid_until: string | null
  days_left: number | null
  blocked: boolean
  price_rub: number
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

  return { subscription, subscriptionLoaded: loaded, reloadSubscription: reload }
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
