import { useEffect, useState } from 'react'
import { Alert, Box, Button, Chip, Paper, Typography } from '@mui/material'
import { daysWord, useSubscription } from '../../hooks/useSubscription'

type Props = {
  token: string
  isFulfillmentAdmin: boolean
}

/** WMS-381/382. Раздел «Подписка» в настройках кабинета фулфилмента. */
export function FfSubscriptionPanel({ token, isFulfillmentAdmin }: Props) {
  const { subscription, startPayment, syncPayment } = useSubscription(token)
  const [busy, setBusy] = useState(false)
  const [message, setMessage] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)

  // Человек вернулся со страницы оплаты — сразу спрашиваем ЮKassa о результате,
  // чтобы он увидел продлённый срок, а не прежние цифры.
  useEffect(() => {
    if (typeof window === 'undefined') {
      return
    }
    if (new URLSearchParams(window.location.search).get('tab') !== 'subscription') {
      return
    }
    void (async () => {
      const activated = await syncPayment()
      if (activated) {
        setMessage('Оплата прошла, подписка продлена на месяц.')
      }
    })()
  }, [syncPayment])

  if (!subscription || !subscription.enabled) {
    return null
  }

  const days = subscription.days_left ?? 0
  const paidUntil = subscription.paid_until
    ? new Date(subscription.paid_until).toLocaleDateString('ru-RU')
    : '—'
  const soon = days <= 5

  const pay = async () => {
    setBusy(true)
    setError(null)
    setMessage(null)
    const failure = await startPayment()
    if (failure) {
      setError(failure)
    }
    setBusy(false)
  }

  const check = async () => {
    setBusy(true)
    setError(null)
    const activated = await syncPayment()
    setMessage(
      activated
        ? 'Оплата найдена, подписка продлена.'
        : 'Новых оплат не найдено.',
    )
    setBusy(false)
  }

  return (
    <Paper sx={{ p: 3, mt: 3 }} data-testid="ff-subscription-panel">
      <Typography variant="h6" gutterBottom>
        Подписка
      </Typography>
      {subscription.blocked ? (
        <Alert severity="error" sx={{ mb: 2 }}>
          Подписка закончилась {paidUntil}. Работа в системе приостановлена.
        </Alert>
      ) : (
        <Alert severity={soon ? 'warning' : 'info'} sx={{ mb: 2 }}>
          {soon
            ? 'Подписка скоро закончится — продлите, чтобы склад не встал.'
            : 'Подписка активна.'}
        </Alert>
      )}
      {message ? (
        <Alert severity="success" sx={{ mb: 2 }}>
          {message}
        </Alert>
      ) : null}
      {error ? (
        <Alert severity="error" sx={{ mb: 2 }}>
          {error}
        </Alert>
      ) : null}
      <Box sx={{ display: 'flex', gap: 1.5, flexWrap: 'wrap', alignItems: 'center' }}>
        <Chip
          data-testid="ff-subscription-days"
          color={subscription.blocked ? 'error' : soon ? 'warning' : 'success'}
          label={
            subscription.blocked
              ? 'Осталось 0 дней'
              : `Осталось ${days} ${daysWord(days)}`
          }
        />
        <Typography variant="body2" color="text.secondary">
          Оплачено по {paidUntil}
        </Typography>
        <Typography variant="body2" color="text.secondary">
          Месяц подписки: {subscription.price_rub.toLocaleString('ru-RU')} ₽
        </Typography>
      </Box>
      {subscription.payment_available && isFulfillmentAdmin ? (
        <Box sx={{ display: 'flex', gap: 1.5, flexWrap: 'wrap', mt: 2 }}>
          <Button
            variant="contained"
            onClick={() => void pay()}
            disabled={busy}
            data-testid="ff-subscription-pay"
          >
            {busy ? 'Готовим оплату…' : 'Продлить на месяц'}
          </Button>
          <Button variant="outlined" onClick={() => void check()} disabled={busy}>
            Проверить оплату
          </Button>
        </Box>
      ) : null}
    </Paper>
  )
}
