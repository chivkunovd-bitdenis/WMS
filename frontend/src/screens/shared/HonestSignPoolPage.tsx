import { Alert, Stack, Typography } from '@mui/material'
import { useParams, useSearchParams } from 'react-router-dom'

type Props = {
  token: string
  testIdPrefix?: string
}

/** T0.9 заполнит вкладки; сейчас — заглушка навигации с Э1. */
export function HonestSignPoolPage({ token, testIdPrefix = 'honest-sign-pool' }: Props) {
  const { poolId } = useParams<{ poolId: string }>()
  const [searchParams] = useSearchParams()
  const tab = searchParams.get('tab')

  return (
    <Stack spacing={2} data-testid={`${testIdPrefix}-page`}>
      <Typography variant="h6">Карточка пула</Typography>
      <Alert severity="info">
        Пул {poolId}
        {tab ? ` · вкладка «${tab}»` : ''} — полный экран в задаче T0.9.
      </Alert>
      <Typography variant="body2" color="text.secondary">
        Токен сессии: {token ? 'есть' : 'нет'}
      </Typography>
    </Stack>
  )
}
