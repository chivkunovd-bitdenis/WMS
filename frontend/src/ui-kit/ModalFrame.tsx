import { Dialog, DialogActions, DialogContent, DialogTitle, Typography } from '@mui/material'
import type { ReactNode } from 'react'

export type ModalFrameProps = {
  open: boolean
  title: string
  purpose?: string
  maxWidth?: 'sm' | 'md' | 'lg'
  busy?: boolean
  onClose: () => void
  actions: ReactNode
  children: ReactNode
  testId?: string
}

export function ModalFrame({
  open,
  title,
  purpose,
  maxWidth = 'md',
  busy = false,
  onClose,
  actions,
  children,
  testId,
}: ModalFrameProps) {
  return (
    <Dialog
      open={open}
      fullWidth
      maxWidth={maxWidth}
      onClose={(_, reason) => {
        if (!busy) onClose()
      }}
      aria-busy={busy}
      data-testid={testId}
    >
      <DialogTitle>
        {title}
        {purpose ? (
          <Typography component="div" variant="body2" color="text.secondary">
            {purpose}
          </Typography>
        ) : null}
      </DialogTitle>
      <DialogContent dividers sx={{ overflowY: 'auto' }}>
        {children}
      </DialogContent>
      <DialogActions>{actions}</DialogActions>
    </Dialog>
  )
}
