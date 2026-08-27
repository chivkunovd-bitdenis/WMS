import { Dialog, DialogActions, DialogContent, DialogTitle } from '@mui/material'
import type { ReactNode } from 'react'
import { useId } from 'react'

const DIALOG_ACCESSIBILITY = {
  disableAutoFocus: false,
  disableEnforceFocus: false,
  disableRestoreFocus: false,
  disableEscapeKeyDown: false,
} as const

// Единый диалог: MUI берёт фокус внутрь и возвращает его триггеру, Escape
// всегда вызывает onClose. Экрану остаётся передать содержимое и штатные Actions.
export function AppDialog({
  open,
  title,
  children,
  actions,
  onClose,
  maxWidth = 'sm',
  testId,
}: {
  open: boolean
  title: ReactNode
  children: ReactNode
  actions?: ReactNode
  onClose: () => void
  maxWidth?: 'xs' | 'sm' | 'md' | 'lg' | 'xl'
  testId?: string
}) {
  const titleId = useId().replace(/[^A-Za-z0-9_-]/g, '')
  return (
    <Dialog
      open={open}
      onClose={() => onClose()}
      maxWidth={maxWidth}
      fullWidth
      aria-labelledby={titleId}
      data-testid={testId}
      {...DIALOG_ACCESSIBILITY}
    >
      <DialogTitle id={titleId}>{title}</DialogTitle>
      <DialogContent dividers>{children}</DialogContent>
      {actions ? <DialogActions>{actions}</DialogActions> : null}
    </Dialog>
  )
}

// Test-only seam; this policy is intentionally not exported by ui-kit/index.
export const __appDialogTest = { accessibility: DIALOG_ACCESSIBILITY }
