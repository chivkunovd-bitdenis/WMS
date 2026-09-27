import { HonestSignScreen } from '../shared/HonestSignScreen'
import { Stack } from '@mui/material'

import { SellerHonestSignTabs } from './SellerKizWithdrawalScreen'

type Props = {
  token: string
  sellerId: string
  withdrawalEnabled?: boolean
}

export function SellerHonestSignScreen({ token, sellerId, withdrawalEnabled = false }: Props) {
  return (
    <Stack spacing={2}>
      {withdrawalEnabled && <SellerHonestSignTabs active="pools" />}
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
