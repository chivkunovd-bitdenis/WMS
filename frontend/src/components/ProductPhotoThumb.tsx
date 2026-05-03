import { Avatar } from '@mui/material'

type Props = {
  src: string | null | undefined
  alt?: string
  size?: number
  testId?: string
}

export function ProductPhotoThumb({ src, alt = '', size = 44, testId }: Props) {
  return (
    <Avatar
      variant="rounded"
      src={src ?? undefined}
      alt={alt}
      sx={{ width: size, height: size }}
      slotProps={{ img: { loading: 'lazy' } }}
      data-testid={testId}
    />
  )
}

