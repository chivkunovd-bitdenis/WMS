import { Box, Typography } from '@mui/material'

type Props = {
  title: string
  hint: string
  testId: string
}

export function FfPlaceholderPage({ title, hint, testId }: Props) {
  return (
    <Box data-testid={testId}>
      <Typography variant="h5" gutterBottom>
        {title}
      </Typography>
      <Typography variant="body2" color="text.secondary">
        {hint}
      </Typography>
    </Box>
  )
}
