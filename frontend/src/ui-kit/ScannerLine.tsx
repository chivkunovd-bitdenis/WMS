import { Stack, Typography } from '@mui/material'

// Канон R-25: экран, который слушает сканер, обязан об этом говорить.
// Работающий, но молчащий слушатель равен отсутствующей функции — так и вышло
// с приёмкой, где сканирование было, а заказчик спрашивал, где оно.
export function ScannerLine({
  active,
  expects,
  testId,
}: {
  active: boolean
  expects: string
  testId?: string
}) {
  return (
    <Stack
      direction="row"
      spacing={1}
      data-testid={testId}
      sx={{
        alignItems: 'center',
        alignSelf: 'flex-start',
        px: 1.5,
        py: 0.75,
        mb: 2,
        borderRadius: 2.5,
        backgroundColor: active ? 'rgba(27, 107, 69, 0.10)' : 'rgba(15, 23, 42, 0.06)',
        color: active ? '#14603D' : 'text.secondary',
      }}
    >
      <Typography variant="body2" sx={{ fontWeight: 600 }}>
        {active ? `Сканер активен — ${expects}` : 'Сканер не слушает этот экран'}
      </Typography>
    </Stack>
  )
}
