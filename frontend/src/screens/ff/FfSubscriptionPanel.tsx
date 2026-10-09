import { useCallback, useEffect, useRef, useState } from 'react'
import { Box, Button, Divider, Paper, Stack, Typography } from '@mui/material'
import { daysWord, useSubscription } from '../../hooks/useSubscription'

type Props = {
  token: string
  isFulfillmentAdmin: boolean
}

function formatDate(value: string | null): string {
  if (!value) {
    return '—'
  }
  return new Date(value).toLocaleDateString('ru-RU', {
    day: 'numeric',
    month: 'long',
    year: 'numeric',
  })
}

/** WMS-381/382. Раздел «Подписка» в настройках кабинета фулфилмента.
 *
 * Кнопки «Проверить оплату» здесь намеренно нет: клиент не должен тыкать в неё,
 * чтобы получить оплаченное. Статус подтягивается сам — при открытии раздела и
 * несколько раз подряд после возврата со страницы оплаты, пока ЮKassa думает.
 */
export function FfSubscriptionPanel({ token, isFulfillmentAdmin }: Props) {
  const { subscription, startPayment, syncPayment } = useSubscription(token)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const polled = useRef(false)

  const pollForPayment = useCallback(async () => {
    // Один тихий опрос при открытии раздела покрывает обычный случай: человек
    // вернулся с оплаты, и подписка продлевается сама. После возврата ЮKassa
    // иногда подтверждает не сразу — тогда переспрашиваем ещё несколько раз.
    const returnedFromPayment =
      typeof window !== 'undefined' &&
      new URLSearchParams(window.location.search).get('tab') === 'subscription'
    const attempts = returnedFromPayment ? 6 : 1
    for (let attempt = 0; attempt < attempts; attempt += 1) {
      if (await syncPayment()) {
        return
      }
      if (attempt + 1 < attempts) {
        await new Promise((resolve) => setTimeout(resolve, 5000))
      }
    }
  }, [syncPayment])

  useEffect(() => {
    if (polled.current) {
      return
    }
    polled.current = true
    void pollForPayment()
  }, [pollForPayment])

  if (!subscription || !subscription.enabled) {
    return null
  }

  const days = subscription.days_left ?? 0
  const blocked = subscription.blocked
  const soon = !blocked && days <= 5
  const statusLabel = blocked ? 'Истекла' : soon ? 'Заканчивается' : 'Активна'
  const statusColor = blocked ? '#b3261e' : soon ? '#8a5a00' : '#1b5e20'
  const statusBg = blocked ? '#fdeceb' : soon ? '#fff4e0' : '#e9f5ec'

  const pay = async () => {
    setBusy(true)
    setError(null)
    const failure = await startPayment()
    if (failure) {
      setError(failure)
    }
    setBusy(false)
  }

  return (
    <Paper sx={{ p: 3, mt: 3, maxWidth: 520 }} data-testid="ff-subscription-panel">
      <Stack direction="row" sx={{ alignItems: 'center', justifyContent: 'space-between', mb: 2.5 }}>
        <Typography variant="subtitle2" color="text.secondary">
          Подписка
        </Typography>
        <Box
          data-testid="ff-subscription-status"
          sx={{
            fontSize: 11,
            fontWeight: 600,
            px: 1.25,
            py: 0.4,
            borderRadius: 5,
            color: statusColor,
            bgcolor: statusBg,
            letterSpacing: '0.03em',
          }}
        >
          {statusLabel}
        </Box>
      </Stack>

      <Stack direction="row" sx={{ alignItems: 'baseline', gap: 0.75, mb: 2 }}>
        <Typography
          data-testid="ff-subscription-days"
          sx={{ fontSize: 40, fontWeight: 600, letterSpacing: '-0.03em', lineHeight: 1 }}
        >
          {blocked ? 0 : days}
        </Typography>
        <Typography variant="body2" color="text.secondary">
          {daysWord(blocked ? 0 : days)} осталось
        </Typography>
      </Stack>

      <Divider sx={{ mb: 2 }} />

      <Stack spacing={1.25} sx={{ mb: isFulfillmentAdmin ? 2.5 : 0 }}>
        <Stack direction="row" sx={{ justifyContent: 'space-between' }}>
          <Typography variant="body2" color="text.secondary">
            {blocked ? 'Была оплачена по' : 'Оплачена по'}
          </Typography>
          <Typography variant="body2">{formatDate(subscription.paid_until)}</Typography>
        </Stack>
        <Stack direction="row" sx={{ justifyContent: 'space-between' }}>
          <Typography variant="body2" color="text.secondary">
            Месяц подписки
          </Typography>
          <Typography variant="body2">
            {subscription.price_rub.toLocaleString('ru-RU')} ₽
          </Typography>
        </Stack>
      </Stack>

      {error ? (
        <Typography variant="body2" sx={{ color: 'error.main', mb: 2 }}>
          {error}
        </Typography>
      ) : null}

      {isFulfillmentAdmin && subscription.payment_available ? (
        <Button
          variant="contained"
          onClick={() => void pay()}
          disabled={busy}
          data-testid="ff-subscription-pay"
          fullWidth
        >
          {busy ? 'Переход к ЮKassa…' : blocked ? 'Оплатить в ЮKassa' : 'Продлить в ЮKassa'}
        </Button>
      ) : null}
    </Paper>
  )
}
