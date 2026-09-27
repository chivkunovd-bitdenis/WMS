// WMS-491 (кусок D1): фильтр «Селлер» каталога ФФ и «Расчётов» из адреса
// (?seller_id=<id>) — из карточки селлера ведут ссылки «Товары» и «Выставить
// счёт». Применяется только к уже загруженному списку селлеров, иначе
// оставляет «Все селлеры» (пустая строка): чужой, несуществующий или мусорный
// id фильтр не ломает.
export function resolveInitialSellerFilter(
  sellerIdParam: string | null,
  sellers: { id: string }[],
): string {
  if (!sellerIdParam) return ''
  return sellers.some((seller) => seller.id === sellerIdParam) ? sellerIdParam : ''
}
