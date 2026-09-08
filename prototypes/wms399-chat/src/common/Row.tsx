import { Box } from '@mui/material'
import type { BoxProps } from '@mui/material'
import type { CSSProperties, ReactNode } from 'react'

type Props = Omit<BoxProps, 'display'> & {
  align?: CSSProperties['alignItems']
  justify?: CSSProperties['justifyContent']
  spacing?: number
  wrap?: boolean
  direction?: 'row' | 'column' | 'row-reverse' | 'column-reverse'
  children?: ReactNode
}

export function Row({
  align,
  justify,
  spacing = 0,
  wrap = false,
  direction = 'row',
  sx,
  children,
  ...rest
}: Props) {
  return (
    <Box
      {...rest}
      sx={[
        {
          display: 'flex',
          flexDirection: direction,
          alignItems: align,
          justifyContent: justify,
          flexWrap: wrap ? 'wrap' : 'nowrap',
          gap: spacing,
          minWidth: 0,
        },
        ...(Array.isArray(sx) ? sx : sx ? [sx] : []),
      ]}
    >
      {children}
    </Box>
  )
}

export function Col({
  align,
  justify,
  spacing = 0,
  sx,
  children,
  ...rest
}: Omit<Props, 'direction' | 'wrap'>) {
  return (
    <Box
      {...rest}
      sx={[
        {
          display: 'flex',
          flexDirection: 'column',
          alignItems: align,
          justifyContent: justify,
          gap: spacing,
          minWidth: 0,
        },
        ...(Array.isArray(sx) ? sx : sx ? [sx] : []),
      ]}
    >
      {children}
    </Box>
  )
}
