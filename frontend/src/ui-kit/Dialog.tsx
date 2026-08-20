import {
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  Stack,
  Typography,
} from '@mui/material'
import type { ReactNode } from 'react'
import { DangerAction, PrimaryAction, SecondaryAction } from './Actions'

export type DialogAction = {
  label: string
  onClick: () => void
  kind?: 'primary' | 'secondary' | 'danger'
  disabledReason?: string
}

export function ModalDialog({
  open,
  title,
  description,
  children,
  actions,
  onClose,
  testId,
}: {
  open: boolean
  title: string
  description?: string
  children?: ReactNode
  actions?: DialogAction[]
  onClose: () => void
  testId?: string
}) {
  return (
    <Dialog open={open} onClose={onClose} fullWidth maxWidth="sm" data-testid={testId}>
      <DialogTitle sx={{ pb: 1 }}>{title}</DialogTitle>
      <DialogContent>
        <Stack spacing={2}>
          {description ? (
            <Typography variant="body2" color="text.secondary">
              {description}
            </Typography>
          ) : null}
          {children}
        </Stack>
      </DialogContent>
      {actions?.length ? (
        <DialogActions sx={{ px: 3, pb: 2 }}>
          {actions.map((action) => {
            const props = {
              key: action.label,
              onClick: action.onClick,
              disabledReason: action.disabledReason,
              children: action.label,
            }
            if (action.kind === 'danger') return <DangerAction {...props} />
            if (action.kind === 'primary') return <PrimaryAction {...props} />
            return <SecondaryAction {...props} />
          })}
        </DialogActions>
      ) : null}
    </Dialog>
  )
}
