import { HonestSignScreen } from '../shared/HonestSignScreen'

type Props = {
  token: string
  sellerId: string
}

export function SellerHonestSignScreen({ token, sellerId }: Props) {
  return (
    <HonestSignScreen
      token={token}
      sellerId={sellerId}
      testIdPrefix="seller-honest-sign"
      routeBase="/seller"
      showSellerDashboard
    />
  )
}
