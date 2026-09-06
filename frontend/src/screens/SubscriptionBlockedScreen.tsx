import { Alert, Box, Button, Container, Paper, Typography } from '@mui/material'
import { WmsBrandMark } from '../components/WmsBrandMark'
import type { Subscription } from '../hooks/useSubscription'

type Props = {
  subscription: Subscription
  onLogout: () => void
  onRetry: () => void
}

/** WMS-381. Подписка закончилась — работа закрыта, показываем сумму к оплате. */
export function SubscriptionBlockedScreen({ subscription, onLogout, onRetry }: Props) {
  const paidUntil = subscription.paid_until
    ? new Date(subscription.paid_until).toLocaleDateString('ru-RU')
    : null

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
          <Paper sx={{ p: 3 }}>
            <Typography variant="h6" gutterBottom>
              К оплате {subscription.price_rub.toLocaleString('ru-RU')} ₽
            </Typography>
            <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
              {paidUntil
                ? `Подписка была оплачена по ${paidUntil}. Чтобы продолжить работу, продлите её на следующий месяц.`
                : 'Чтобы продолжить работу, продлите подписку на следующий месяц.'}
            </Typography>
            <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
              Данные склада на месте и никуда не денутся — как только оплата
              пройдёт, работа продолжится с того же места.
            </Typography>
            <Box sx={{ display: 'flex', gap: 1.5, flexWrap: 'wrap' }}>
              <Button variant="contained" onClick={onRetry} data-testid="subscription-retry">
                Проверить оплату
              </Button>
              <Button variant="text" onClick={onLogout}>
                Выйти
              </Button>
            </Box>
          </Paper>
        </Box>
      </Container>
    </Box>
  )
}
