import { Box } from '@mui/material'

export type WmsPortal = 'fulfillment' | 'seller'

type Props = {
  size?: number
  portal?: WmsPortal
}

const MARK_SRC: Record<WmsPortal, string> = {
  fulfillment: '/favicon.svg',
  seller: '/favicon-seller.svg',
}

/** Portal mark — same asset as the matching favicon. */
export function WmsBrandMark({ size = 28, portal = 'fulfillment' }: Props) {
  return (
    <Box
      component="img"
      src={MARK_SRC[portal]}
      alt=""
      aria-hidden
      data-testid={portal === 'seller' ? 'wms-brand-mark-seller' : 'wms-brand-mark'}
      sx={{ width: size, height: size, flexShrink: 0, display: 'block' }}
    />
  )
}
