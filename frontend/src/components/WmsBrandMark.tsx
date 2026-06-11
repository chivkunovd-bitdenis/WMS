import { Box } from '@mui/material'

type Props = {
  size?: number
}

/** Shared WMS mark (same asset as /favicon.svg). */
export function WmsBrandMark({ size = 28 }: Props) {
  return (
    <Box
      component="img"
      src="/favicon.svg"
      alt=""
      aria-hidden
      data-testid="wms-brand-mark"
      sx={{ width: size, height: size, flexShrink: 0, display: 'block' }}
    />
  )
}
