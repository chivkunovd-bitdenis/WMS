export function movementTypeLabel(type: string): string {
  if (type === 'inbound_intake') return 'Приемка'
  if (type === 'stock_transfer_out') return 'Перемещение: списано'
  if (type === 'stock_transfer_in') return 'Перемещение: принято'
  if (type === 'outbound_shipment') return 'Отгрузка'
  if (type === 'marketplace_unload') return 'Отгрузка на МП'
  if (type === 'fbs_shipment') return 'FBS'
  if (type === 'product_tz_import') return 'Импорт ТЗ'
  return type
}
