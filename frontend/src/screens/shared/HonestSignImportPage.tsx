import { Alert, Stack, Typography } from '@mui/material'

type Props = {
  testIdPrefix?: string
}

/** T0.8 — диалог загрузки; отдельный маршрут-заглушка до реализации. */
export function HonestSignImportPage({ testIdPrefix = 'honest-sign-import' }: Props) {
  return (
    <Stack spacing={2} data-testid={`${testIdPrefix}-page`}>
      <Typography variant="h6">Загрузить КМ</Typography>
      <Alert severity="info">Диалог импорта — задача T0.8 (в работе).</Alert>
    </Stack>
  )
}
