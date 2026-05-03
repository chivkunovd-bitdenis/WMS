import { Box, Typography } from '@mui/material'

type Props = {
  title: string
  description?: string
}

/**
 * Canonical page header for the FF portal.
 * Keep typography consistent across screens.
 */
export function PageHeader({ title, description }: Props) {
  return (
    <Box sx={{ mb: 2 }}>
      <Typography variant="h5" gutterBottom>
        {title}
      </Typography>
      {description ? (
        <Typography variant="body2" color="text.secondary">
          {description}
        </Typography>
      ) : null}
    </Box>
  )
}

