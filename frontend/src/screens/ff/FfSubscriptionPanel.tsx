import { Alert, Box, Chip, Paper, Typography } from '@mui/material'
import { daysWord, useSubscription } from '../../hooks/useSubscription'

type Props = {
  token: string
}

/** WMS-381. Раздел «Подписка» в настройках кабинета фулфилмента. */
export function FfSubscriptionPanel({ token }: Props) {
  const { subscription } = useSubscription(token)

  if (!subscription || !subscription.enabled) {
    return null
  }

  const days = subscription.days_left ?? 0
  const paidUntil = subscription.paid_until
    ? new Date(subscription.paid_until).toLocaleDateString('ru-RU')
    : '—'
  const soon = days <= 5

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
          К оплате за месяц: {subscription.price_rub.toLocaleString('ru-RU')} ₽
        </Typography>
      </Box>
    </Paper>
  )
}
