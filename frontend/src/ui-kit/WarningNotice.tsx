import { Alert } from '@mui/material'
import type { ReactNode } from 'react'

export function WarningNotice({ children, testId }: { children: ReactNode; testId?: string }) {
  return <Alert severity="warning" sx={{ mb: 2 }} data-testid={testId}>{children}</Alert>
}
