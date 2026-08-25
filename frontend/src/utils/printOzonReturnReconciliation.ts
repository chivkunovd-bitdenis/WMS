import { escapeLabelHtml } from './productLabelText'

export type OzonReturnReconciliationItem = {
  offer_id: string | null
  ozon_sku: number | null
  product_name: string
  return_reason_name: string | null
  quantity: number
  return_barcode: string | null
}

export type OzonReturnReconciliationGroup = {
  giveout_id: number
  giveout_status: string
  warehouse_name: string
  warehouse_address: string
  items: OzonReturnReconciliationItem[]
}

export type OzonReturnReconciliationData = {
  documentNumber: string | null
  sellerName: string | null
  groups: OzonReturnReconciliationGroup[]
}

function itemRow(item: OzonReturnReconciliationItem): string {
  return `<tr>
    <td>${escapeLabelHtml(item.offer_id ?? '—')}</td>
    <td>${escapeLabelHtml(item.ozon_sku != null ? String(item.ozon_sku) : '—')}</td>
    <td>${escapeLabelHtml(item.product_name)}</td>
    <td>${escapeLabelHtml(item.return_reason_name ?? '—')}</td>
    <td class="qty">${item.quantity}</td>
    <td>${escapeLabelHtml(item.return_barcode ?? '—')}</td>
  </tr>`
}

export function buildOzonReturnReconciliationHtml(data: OzonReturnReconciliationData): string {
  const sections = data.groups
    .map(
      (group, index) => `<section data-testid="ozon-return-reconciliation-group">
        <h2>${index + 1}. ${escapeLabelHtml(group.warehouse_name)}</h2>
        <p class="group-meta">${escapeLabelHtml(group.warehouse_address)} · выдача ${group.giveout_id} · ${escapeLabelHtml(group.giveout_status)}</p>
        <table>
          <thead><tr>
            <th>Артикул продавца</th><th>Артикул Ozon</th><th>Наименование</th>
            <th>Причина возврата</th><th class="qty">Количество</th><th>ШК возврата</th>
          </tr></thead>
          <tbody>${group.items.map(itemRow).join('')}</tbody>
        </table>
      </section>`,
    )
    .join('')
  return `<!doctype html>
<html><head><meta charset="utf-8" />
  <title>Лист сверки возвратов Ozon</title>
  <style>
    @page { size: A4 landscape; margin: 8mm; }
    * { box-sizing: border-box; }
    body { margin: 0; color: #111; font: 10px system-ui, sans-serif; }
    h1 { margin: 0 0 4px; font-size: 16px; }
    .document-meta { margin: 0 0 10px; color: #444; }
    section { break-inside: avoid-page; margin: 0 0 12px; }
    h2 { margin: 0 0 2px; font-size: 13px; }
    .group-meta { margin: 0 0 5px; color: #555; }
    table { width: 100%; table-layout: fixed; border-collapse: collapse; }
    th, td { border: 1px solid #bbb; padding: 4px; text-align: left; word-break: break-word; }
    th { background: #eee; font-size: 9px; }
    tr { break-inside: avoid-page; }
    .qty { width: 18mm; text-align: right; }
    .empty { color: #555; }
  </style>
</head><body>
  <h1>Лист сверки возвратов Ozon</h1>
  <p class="document-meta">Документ: ${escapeLabelHtml(data.documentNumber ?? '—')} · Селлер: ${escapeLabelHtml(data.sellerName ?? '—')}</p>
  ${sections || '<p class="empty">Нет добавленных пунктов выдачи.</p>'}
</body></html>`
}

declare global {
  interface Window {
    __WMS_CAPTURE_PRINT_HTML__?: boolean
    __WMS_LAST_PRINT_HTML__?: string
  }
}

export function printOzonReturnReconciliation(data: OzonReturnReconciliationData): void {
  const html = buildOzonReturnReconciliationHtml(data)
  if (typeof window !== 'undefined' && window.__WMS_CAPTURE_PRINT_HTML__) {
    window.__WMS_LAST_PRINT_HTML__ = html
  }
  const iframe = document.createElement('iframe')
  iframe.setAttribute('aria-hidden', 'true')
  iframe.style.cssText = 'position:fixed;right:0;bottom:0;width:0;height:0;border:0'
  document.body.appendChild(iframe)
  iframe.onload = () => {
    const printWindow = iframe.contentWindow
    if (!printWindow) {
      iframe.remove()
      return
    }
    printWindow.focus()
    printWindow.print()
    window.setTimeout(() => iframe.remove(), 500)
  }
  iframe.srcdoc = html
}
