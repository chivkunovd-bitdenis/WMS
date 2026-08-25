export type ManualProductSeller = {
  id: string
  name: string
  ozon_connected?: boolean | null
}

export function sellerHasOzonConnection(
  sellers: ManualProductSeller[],
  sellerId: string,
): boolean {
  return sellers.some((seller) => seller.id === sellerId && seller.ozon_connected === true)
}
