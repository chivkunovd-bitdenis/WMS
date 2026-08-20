import { Box, Paper, Stack } from '@mui/material'
import type { ReactNode } from 'react'

export function ScreenShell({ children, testId }: { children: ReactNode; testId?: string }) {
  return (
    <Box data-testid={testId} sx={{ px: { xs: 2, md: 3 }, py: 2, maxWidth: 1440, mx: 'auto' }}>
      {children}
    </Box>
  )
}

export function ScreenSection({
  children,
  testId,
}: {
  children: ReactNode
  testId?: string
}) {
  return (
    <Paper variant="outlined" data-testid={testId} sx={{ p: 2, mb: 2 }}>
      {children}
    </Paper>
  )
}

export function ToolbarLine({ children, testId }: { children: ReactNode; testId?: string }) {
  return (
    <Stack
      direction={{ xs: 'column', sm: 'row' }}
      spacing={1}
      data-testid={testId}
      sx={{ alignItems: { sm: 'center' }, justifyContent: 'space-between', mb: 2 }}
    >
      {children}
    </Stack>
  )
}
