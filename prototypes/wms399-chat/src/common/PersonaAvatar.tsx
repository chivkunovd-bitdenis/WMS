import { Avatar } from '@mui/material'
import type { SxProps, Theme } from '@mui/material'
import type { Actor } from '../types'

type Props = {
  actor: Actor
  size?: number
  sx?: SxProps<Theme>
}

export function PersonaAvatar({ actor, size = 32, sx }: Props) {
  return (
    <Avatar
      variant="rounded"
      sx={{
        width: size,
        height: size,
        bgcolor: actor.color,
        fontSize: size * 0.44,
        fontWeight: 700,
        borderRadius: 2,
        ...sx,
      }}
    >
      {actor.short}
    </Avatar>
  )
}
