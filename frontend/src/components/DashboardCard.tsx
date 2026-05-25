import { Link as RouterLink } from 'react-router-dom'
import { Alert, Button, Typography } from '@mui/material'
import { Card } from '../ui/Card'

type Me = {
  email: string
  organization_name: string
  role: string
  seller_name?: string | null
}

type Props = {
  me: Me
  isFulfillmentAdmin: boolean
  /** Вложенный блок (без дублирующего data-testid на корне карточки) */
  embedded?: boolean
}

export function DashboardCard({ me, isFulfillmentAdmin, embedded = false }: Props) {
  return (
    <Card className="card" data-testid={embedded ? undefined : 'dashboard'}>
      {embedded ? null : (
        <>
          <p data-testid="user-email">{me.email}</p>
          <p data-testid="org-name">{me.organization_name}</p>
          <p data-testid="user-role">{me.role}</p>
          {me.seller_name ? (
            <p data-testid="seller-cabinet-label">Селлер: {me.seller_name}</p>
          ) : null}
        </>
      )}

      {isFulfillmentAdmin ? (
        <Alert severity="info" sx={{ mt: embedded ? 0 : 1.5 }} data-testid="dashboard-sellers-hint">
          <Typography variant="body2" component="span">
            Новых селлеров добавляйте в разделе «Селлеры»: название и email. Пароль селлер задаёт при
            первом входе (поле пароля оставить пустым).
          </Typography>
          <Button
            component={RouterLink}
            to="/app/ff/sellers"
            size="small"
            variant="outlined"
            sx={{ mt: 1 }}
            data-testid="dashboard-go-sellers"
          >
            Открыть «Селлеры»
          </Button>
        </Alert>
      ) : null}
    </Card>
  )
}
