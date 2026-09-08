import { Avatar } from '@mui/material'
import type { Seller } from '../types'

export function SellerAvatar({ seller, size = 36 }: { seller: Seller; size?: number }) {
  return (
    <Avatar
      variant="rounded"
      sx={{
        width: size,
        height: size,
        bgcolor: seller.color,
        fontSize: size * 0.4,
        fontWeight: 700,
        borderRadius: 2,
      }}
    >
      {seller.short}
    </Avatar>
  )
}
