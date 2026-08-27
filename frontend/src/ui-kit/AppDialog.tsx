import { Dialog, DialogActions, DialogContent, DialogTitle } from '@mui/material'
import type { ReactNode } from 'react'
import { useId } from 'react'

// Единый диалог: MUI сам берёт фокус внутрь модалки, возвращает его триггеру и
// закрывает окно по Escape — это его поведение по умолчанию. Явные флаги
// disableAutoFocus/disableEnforceFocus/disableRestoreFocus/disableEscapeKeyDown
// в MUI 9 до Modal уже не доходят: они утекают на DOM-узел, и React их
// отбрасывает с ошибкой в консоли. Поэтому здесь их нет, а само поведение
// доказано браузером в tests-e2e/ui-kit-form-primitives.spec.ts.
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
    >
      <DialogTitle id={titleId}>{title}</DialogTitle>
      <DialogContent dividers>{children}</DialogContent>
      {actions ? <DialogActions>{actions}</DialogActions> : null}
    </Dialog>
  )
}
