import { HonestSignScreen } from '../shared/HonestSignScreen'
import { Stack } from '@mui/material'

import { SellerHonestSignTabs } from './SellerKizWithdrawalScreen'

type Props = {
  token: string
  sellerId: string
}

export function SellerHonestSignScreen({ token, sellerId }: Props) {
  return (
    <Stack spacing={2}>
      <SellerHonestSignTabs active="pools" />
      <HonestSignScreen
        token={token}
        sellerId={sellerId}
        testIdPrefix="seller-honest-sign"
        routeBase="/seller"
        showSellerDashboard
      />
    </Stack>
  )
}
