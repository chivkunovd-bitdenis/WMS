/**
 * Число остатка с разрядами, как в колонке «В Wildberries». Отрицательное
 * (резерв больше остатка, WMS-530 D3) — с настоящим знаком минус: дефис рядом
 * с цифрами читается как тире.
 */
export function formatStockQty(value: number): string {
  const digits = Math.abs(value).toLocaleString('ru-RU')
  return value < 0 ? `\u2212${digits}` : digits
}
