import { Box, Stack, Typography } from '@mui/material'
import type { ReactNode } from 'react'

export function EmptyState({
  title,
  description,
  icon,
  action,
}: {
  title: string
  description?: string
  icon?: ReactNode
  action?: ReactNode
}) {
  return (
    <Box
      sx={{
        p: 4,
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'center',
        justifyContent: 'center',
        textAlign: 'center',
        gap: 1.5,
        color: 'text.secondary',
      }}
    >
      {icon ? <Box sx={{ color: 'primary.main', mb: 0.5 }}>{icon}</Box> : null}
      <Typography variant="subtitle1" sx={{ color: 'text.primary' }}>
        {title}
      </Typography>
      {description ? (
        <Typography variant="body2" sx={{ maxWidth: 320 }}>
          {description}
        </Typography>
      ) : null}
      {action ? <Stack sx={{ mt: 1 }}>{action}</Stack> : null}
    </Box>
  )
}
