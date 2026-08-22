import { Alert } from '@mui/material'
import type { ReactNode } from 'react'

export type WarningNoticeProps = {
  children: ReactNode
  testId?: string
}

export function WarningNotice({ children, testId }: WarningNoticeProps) {
  return <Alert severity="warning" sx={{ mb: 2 }} data-testid={testId}>{children}</Alert>
}
