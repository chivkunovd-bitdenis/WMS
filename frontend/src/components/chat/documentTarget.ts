import type { AttachedDocument } from './chatApi'

// Existing working routes only. Seller has no operator FBS/outbound surface.
export function workingDocumentTarget(document: Pick<AttachedDocument, 'kind' | 'id' | 'seller_id'>, base: string): string | null {
  const id = encodeURIComponent(document.id)
  if (base === '/app/ff') {
    switch (document.kind) {
      case 'fbs_order': return `${base}/fbs?order_id=${id}&seller_id=${encodeURIComponent(document.seller_id)}`
      case 'fbs_supply': return `${base}/fbs?supply_id=${id}`
      // Получатель — общий обработчик WMS-177 в App.tsx: на маршруте
      // /app/ff/reception он читает `?open_inbound=<id>` и открывает документ
      // по идентификатору, не опираясь на строки очереди. Параметр менять
      // нельзя: другого потребителя у этой ссылки в выпуске нет.
      case 'inbound_intake': return `${base}/reception?open_inbound=${id}`
      case 'marketplace_unload': return `${base}/mp-shipments?open_mp=${id}`
      case 'outbound_shipment': return `${base}/mp-shipments?open_outbound=${id}`
    }
  }
  if (document.kind === 'inbound_intake') return `${base}/inbound/${id}`
  return null
}
