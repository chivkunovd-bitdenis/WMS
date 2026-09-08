import { useState } from 'react'
import { Alert, Box, Button, Container, Paper, Typography } from '@mui/material'
import { WmsBrandMark } from '../components/WmsBrandMark'
import type { Subscription } from '../hooks/useSubscription'

type Props = {
  subscription: Subscription
  onLogout: () => void
  onRetry: () => void
  onPay?: () => Promise<string | null>
  onCheckPayment?: () => Promise<boolean>
}

/** WMS-381/382. Подписка закончилась — работа закрыта, показываем сумму и оплату. */
export function SubscriptionBlockedScreen({
  subscription,
  onLogout,
  onRetry,
  onPay,
  onCheckPayment,
}: Props) {
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [checked, setChecked] = useState<string | null>(null)

  const paidUntil = subscription.paid_until
    ? new Date(subscription.paid_until).toLocaleDateString('ru-RU')
    : null

  const pay = async () => {
    if (!onPay) {
      return
    }
    setBusy(true)
    setError(null)
    setChecked(null)
    // При успехе браузер уходит на страницу ЮKassa и сюда уже не возвращается.
    const message = await onPay()
    if (message) {
      setError(message)
    }
    setBusy(false)
  }

  const check = async () => {
    setBusy(true)
    setError(null)
    setChecked(null)
    if (onCheckPayment) {
      const activated = await onCheckPayment()
      setChecked(
        activated
          ? 'Оплата найдена, подписка продлена.'
          : 'Оплата пока не подтверждена. Если платили только что — подождите минуту и проверьте ещё раз.',
      )
    }
    onRetry()
    setBusy(false)
  }

  return (
    <Box
      component="main"
      data-testid="subscription-blocked"
      sx={{
        minHeight: '100vh',
        bgcolor: 'background.default',
        py: { xs: 3, sm: 5 },
        px: 2,
      }}
    >
      <Container maxWidth="sm">
        <Box sx={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
          <Box sx={{ display: 'flex', alignItems: 'center', gap: 1.5 }}>
            <WmsBrandMark size={48} portal="fulfillment" />
            <Typography variant="h5" component="h1" sx={{ fontWeight: 900 }}>
              Короб ВМС
            </Typography>
          </Box>
          <Alert severity="warning">Подписка закончилась — работа приостановлена.</Alert>
          {error ? <Alert severity="error">{error}</Alert> : null}
          {checked ? <Alert severity="info">{checked}</Alert> : null}
          <Paper sx={{ p: 3 }}>
            <Typography variant="h6" gutterBottom>
              К оплате {subscription.price_rub.toLocaleString('ru-RU')} ₽
            </Typography>
            <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
              {paidUntil
                ? `Подписка была оплачена по ${paidUntil}. Чтобы продолжить работу, продлите её на месяц.`
                : 'Чтобы продолжить работу, продлите подписку на месяц.'}
            </Typography>
            <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
              Данные склада на месте и никуда не денутся — как только оплата
              пройдёт, работа продолжится с того же места.
            </Typography>
            <Box sx={{ display: 'flex', gap: 1.5, flexWrap: 'wrap' }}>
              {subscription.payment_available && onPay ? (
                <Button
                  variant="contained"
                  onClick={() => void pay()}
                  disabled={busy}
                  data-testid="subscription-pay"
                >
                  {busy ? 'Готовим оплату…' : 'Оплатить картой'}
                </Button>
              ) : null}
              <Button
                variant={subscription.payment_available ? 'outlined' : 'contained'}
                onClick={() => void check()}
                disabled={busy}
                data-testid="subscription-retry"
              >
                Проверить оплату
              </Button>
              <Button variant="text" onClick={onLogout} disabled={busy}>
                Выйти
              </Button>
            </Box>
          </Paper>
        </Box>
      </Container>
    </Box>
  )
}
