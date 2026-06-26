import { Box, Paper, Typography } from '@mui/material'

type Props = {
  testId?: string
}

export function FfHonestSignReprintsPage({ testId = 'ff-honest-sign-reprints-page' }: Props) {
  return (
    <Box data-testid={testId}>
      <Typography variant="h5" gutterBottom>
        Перепечатки ЧЗ
      </Typography>
      <Paper variant="outlined" sx={{ p: 3 }}>
        <Typography variant="body2" color="text.secondary" data-testid={`${testId}-empty`}>
          Нет ожидающих запросов на перепечатку.
        </Typography>
      </Paper>
    </Box>
  )
}
