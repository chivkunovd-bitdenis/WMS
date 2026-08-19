import { HonestSignScreen } from '../shared/HonestSignScreen'

type Props = {
  token: string
  sellerId: string
  /** Префикс переходов. Пустой в отдельном портале селлера — там префикс `/seller`
   *  добавляет сам роутер через `basename`. Непустой, когда портал смонтирован внутрь
   *  приложения фулфилмента: тогда `basename` не работает и путь строится руками,
   *  ровно как в `sellerPath()` из `SellerApp`. */
  navigationBasePath?: string
}

export function SellerHonestSignScreen({
  token,
  sellerId,
  navigationBasePath = '',
}: Props) {
  return (
    <HonestSignScreen
      token={token}
      sellerId={sellerId}
      testIdPrefix="seller-honest-sign"
      routeBase={navigationBasePath}
    />
  )
}
