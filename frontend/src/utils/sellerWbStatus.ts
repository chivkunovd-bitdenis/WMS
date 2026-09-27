export type SellerWbStatusFields = {
  wb_has_key?: boolean
  wb_marketplace_scope_ok?: boolean | null
}

/**
 * Текст статуса WB Marketplace селлера — один источник для списка «Селлеры»
 * (колонка «WB Marketplace») и карточки селлера (WMS-491), чтобы текст не
 * разошёлся при правке одного из мест.
 */
export function sellerWbStatusLabel(seller: SellerWbStatusFields): string {
  if (seller.wb_has_key === false) {
    return 'Ключа нет'
  }
  if (seller.wb_marketplace_scope_ok === true) {
    return 'Проверка пройдена'
  }
  if (seller.wb_marketplace_scope_ok === false) {
    return 'Нет доступа к Marketplace'
  }
  return 'Не проверяли'
}
