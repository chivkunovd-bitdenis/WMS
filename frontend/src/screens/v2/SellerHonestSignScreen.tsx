import { HonestSignScreen } from '../shared/HonestSignScreen'

type Props = {
  token: string
}

export function SellerHonestSignScreen({ token }: Props) {
  return <HonestSignScreen token={token} testIdPrefix="seller-honest-sign" />
}
