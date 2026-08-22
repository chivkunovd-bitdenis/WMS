export function productWarehouseQuantity(
  productId: string,
  quantities: Record<string, number>,
): number {
  return quantities[productId] ?? 0
}
