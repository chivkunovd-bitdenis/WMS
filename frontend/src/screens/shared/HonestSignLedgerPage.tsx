import { Alert, Stack, Typography } from '@mui/material'
import { useSearchParams } from 'react-router-dom'

type Props = {
  testIdPrefix?: string
}

/** T0.10 — лента расхода; заглушка маршрута с Э1. */
export function HonestSignLedgerPage({ testIdPrefix = 'honest-sign-ledger' }: Props) {
  const [searchParams] = useSearchParams()
  const poolId = searchParams.get('pool_id')

  return (
    <Stack spacing={2} data-testid={`${testIdPrefix}-page`}>
      <Typography variant="h6">Лента расхода</Typography>
      <Alert severity="info">
        {poolId ? `Фильтр pool_id=${poolId}. ` : ''}
        Полный экран — задача T0.10.
      </Alert>
    </Stack>
  )
}
