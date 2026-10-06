import { compactPrintWidth, printColgroup } from './printTableColumns'

export type WaybillLine = {
  sku_code: string
  product_name: string
  size?: string | null
  color?: string | null
  quantity: number
  shipped_qty?: number
  received_qty?: number | null
  storage_location_code?: string | null
}

export type ShipmentWaybillDocKind =
  | 'marketplace_unload'
  | 'operational_outbound'
  | 'inbound_intake'

export type ShipmentWaybillData = {
  docKind: ShipmentWaybillDocKind
  documentId: string
  documentNumber?: string | null
  waybillNumber?: string | null
  documentTypeLabel?: string | null
  statusLabel: string
  warehouseName: string
  sellerName: string | null
  wbWarehouseLabel?: string | null
  plannedDate: string | null
  createdAt: string | null
  plannedBoxCount?: number | null
  actualBoxCount?: number | null
  lines: WaybillLine[]
  pickAllocations?: { location_code: string; sku_code: string; quantity: number }[]
}

/** @deprecated Use ShipmentWaybillData + printShipmentWaybill */
export type MarketplaceUnloadWaybillData = Omit<ShipmentWaybillData, 'docKind'> & {
  wbWarehouseLabel: string | null
}

declare global {
  interface Window {
    __WMS_CAPTURE_PRINT_HTML__?: boolean
    __WMS_LAST_PRINT_HTML__?: string
  }
}

function escapeHtml(text: string): string {
  return text
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;')
}

function docTitle(kind: ShipmentWaybillDocKind): string {
  if (kind === 'marketplace_unload') {
    return 'Накладная — отгрузка на маркетплейс'
  }
  if (kind === 'inbound_intake') {
    return 'Накладная — приёмка на склад ФФ'
  }
  return 'Накладная — отгрузка со склада'
}

function footerText(kind: ShipmentWaybillDocKind): string {
  if (kind === 'inbound_intake') {
    return ''
  }
  return 'Печать для сверки перед вывозом. Факт отгрузки — в системе WMS.'
}

function inboundDocumentNumber(data: ShipmentWaybillData): string {
  const n = data.documentNumber?.trim()
  if (!n) {
    return '№ —'
  }
  return n.startsWith('№') ? n : `№ ${n}`
}

function discrepancyText(expectedQty: number, acceptedQty: number): string {
  if (acceptedQty < expectedQty) {
    return `Недостача ${expectedQty - acceptedQty}`
  }
  if (acceptedQty > expectedQty) {
    return `Излишек ${acceptedQty - expectedQty}`
  }
  return 'Нет'
}

/** Печать накладной (A4, браузер). */
export function printShipmentWaybill(data: ShipmentWaybillData): void {
  const isOperational = data.docKind === 'operational_outbound'
  const isInbound = data.docKind === 'inbound_intake'

  const columns = printColgroup(186, [
    ...(!isInbound ? [{ width: 7 }] : []),
    { width: compactPrintWidth('SKU', data.lines.map((line) => line.sku_code), 16, 12, 4.5, 12) },
    { grow: 1 },
    { width: compactPrintWidth('Артикул', data.lines.map((line) => line.sku_code), 20, 12, 4.5, 12) },
    { width: compactPrintWidth('Цвет', data.lines.map((line) => line.color), 17, 12, 4.5, 12) },
    { width: compactPrintWidth('Размер', data.lines.map((line) => line.size), 18, 12, 4.5, 12) },
    ...(isOperational ? [{ width: compactPrintWidth('Ячейка', data.lines.map((line) => line.storage_location_code), 16, 12, 4.5, 12) }] : []),
    { width: compactPrintWidth(isInbound ? 'Заявлено' : 'Кол-во', data.lines.map((line) => line.quantity), 18, 12, 4.5, 12) },
    ...(isOperational ? [{ width: compactPrintWidth('Отгружено', data.lines.map((line) => line.shipped_qty), 20, 12, 4.5, 12) }] : []),
    ...(isInbound ? [
      { width: compactPrintWidth('Факт', data.lines.map((line) => line.received_qty ?? 0), 15, 12, 4.5, 12) },
      { width: compactPrintWidth('Расхождение', data.lines.map((line) => discrepancyText(line.quantity, line.received_qty ?? 0)), 28, 12, 4.5, 12) },
    ] : []),
  ])
  const lineRows = data.lines.map((line, index) => `<tr>
    ${!isInbound ? `<td>${index + 1}</td>` : ''}
    <td>${escapeHtml(line.sku_code)}</td>
    <td class="product">${escapeHtml(line.product_name)}</td>
    <td>${escapeHtml(line.sku_code.trim() || '—')}</td>
    <td>${escapeHtml(line.color?.trim() || '—')}</td>
    <td>${escapeHtml(line.size?.trim() || '—')}</td>
    ${isOperational ? `<td>${escapeHtml(line.storage_location_code ?? '—')}</td>` : ''}
    <td align="right">${line.quantity}</td>
    ${isOperational ? `<td align="right">${line.shipped_qty ?? '—'}</td>` : ''}
    ${isInbound ? `<td align="right">${line.received_qty ?? 0}</td><td>${escapeHtml(discrepancyText(line.quantity, line.received_qty ?? 0))}</td>` : ''}
  </tr>`).join('')

  const boxMeta =
    isInbound && (data.plannedBoxCount != null || data.actualBoxCount != null)
      ? `<dt>Короба (план / факт)</dt><dd>${data.plannedBoxCount ?? '—'} / ${data.actualBoxCount ?? '—'}</dd>`
      : ''

  const pickBlock =
    data.pickAllocations && data.pickAllocations.length > 0
      ? `<h2>Подбор по ячейкам</h2>
        <table>
          <thead><tr><th>Ячейка</th><th>SKU</th><th align="right">Кол-во</th></tr></thead>
          <tbody>
            ${data.pickAllocations
              .map(
                (p) =>
                  `<tr><td>${escapeHtml(p.location_code)}</td><td>${escapeHtml(p.sku_code)}</td><td align="right">${p.quantity}</td></tr>`,
              )
              .join('')}
          </tbody>
        </table>`
      : ''

  const wbMeta =
    data.docKind === 'marketplace_unload'
      ? `<dt>Склад МП (WB)</dt><dd>${escapeHtml(data.wbWarehouseLabel ?? '—')}</dd>`
      : ''

  const colSpan = isInbound ? 8 : 7 + (isOperational ? 2 : 0)
  const inboundTypeLabel = data.documentTypeLabel?.trim() || 'Поставка'
  const inboundTitle = `${inboundTypeLabel} ${inboundDocumentNumber(data)}`
  const printTitle = isInbound ? inboundTitle : `Накладная ${data.documentId.slice(0, 8)}`
  const headingTitle = isInbound
    ? `Накладная — ${inboundTypeLabel.toLowerCase()} на склад ФФ · ${inboundDocumentNumber(data)}`
    : docTitle(data.docKind)
  const inboundMeta = isInbound
    ? `<dt>Документ</dt><dd>${escapeHtml(inboundTitle)}</dd>
      <dt>Накладная селлера</dt><dd>${escapeHtml(data.waybillNumber?.trim() || '—')}</dd>
      <dt>Селлер</dt><dd>${escapeHtml(data.sellerName ?? '—')}</dd>
      <dt>Дата</dt><dd>${escapeHtml(data.plannedDate ?? '—')}</dd>
      <dt>Склад ФФ</dt><dd>${escapeHtml(data.warehouseName || '—')}</dd>
      ${boxMeta}`
    : ''
  const defaultMeta = !isInbound
    ? `<dt>Документ</dt><dd>${escapeHtml(data.documentId)}</dd>
      <dt>Статус</dt><dd>${escapeHtml(data.statusLabel)}</dd>
      <dt>Склад ФФ</dt><dd>${escapeHtml(data.warehouseName)}</dd>
      <dt>Селлер</dt><dd>${escapeHtml(data.sellerName ?? '—')}</dd>
      ${wbMeta}
      ${boxMeta}
      <dt>Плановая дата</dt><dd>${escapeHtml(data.plannedDate ?? '—')}</dd>
      <dt>Создано</dt><dd>${escapeHtml(data.createdAt ?? '—')}</dd>`
    : ''
  const tableHead = `<tr>${!isInbound ? '<th>#</th>' : ''}<th>SKU</th><th>${isInbound ? 'Товар' : 'Наименование'}</th><th>Артикул</th><th>Цвет</th><th>Размер</th>${isOperational ? '<th>Ячейка</th>' : ''}<th align="right">${isInbound ? 'Заявлено' : 'Кол-во'}</th>${isOperational ? '<th align="right">Отгружено</th>' : ''}${isInbound ? '<th align="right">Факт</th><th>Расхождение</th>' : ''}</tr>`

  const foot = footerText(data.docKind)

  const html = `<!doctype html>
<html>
  <head>
    <meta charset="utf-8" />
    <title>${escapeHtml(printTitle)}</title>
    <style>
      @page { margin: 12mm; }
      body { font-family: system-ui, -apple-system, Segoe UI, Roboto, Arial, sans-serif; font-size: 12px; color: #111; }
      h1 { font-size: 18px; margin: 0 0 8px; }
      h2 { font-size: 14px; margin: 16px 0 8px; }
      .meta { display: grid; grid-template-columns: 1fr 1fr; gap: 6px 24px; margin-bottom: 16px; }
      .meta dt { font-weight: 600; margin: 0; }
      .meta dd { margin: 0 0 6px; }
      table { width: 100%; border-collapse: collapse; table-layout: fixed; }
      * { box-sizing: border-box; }
      th, td { border: 1px solid #ccc; padding: 6px 8px; text-align: left; vertical-align: top; overflow-wrap: anywhere; }
      th { background: #f5f5f5; }
      tr { break-inside: avoid; }
      .foot { margin-top: 24px; font-size: 11px; color: #555; }
    </style>
  </head>
  <body>
    <h1>${escapeHtml(headingTitle)}</h1>
    <dl class="meta">
      ${inboundMeta || defaultMeta}
    </dl>
    <h2>Состав</h2>
    <table>
      ${columns}
      <thead>
        ${tableHead}
      </thead>
      <tbody>${lineRows || `<tr><td colspan="${colSpan}">Нет строк</td></tr>`}</tbody>
    </table>
    ${pickBlock}
    ${foot ? `<p class="foot">${foot}</p>` : ''}
  </body>
</html>`

  if (typeof window !== 'undefined' && window.__WMS_CAPTURE_PRINT_HTML__) {
    window.__WMS_LAST_PRINT_HTML__ = html
  }

  const iframe = document.createElement('iframe')
  iframe.setAttribute('aria-hidden', 'true')
  iframe.style.cssText = 'position:fixed;right:0;bottom:0;width:0;height:0;border:0'
  document.body.appendChild(iframe)

  const cleanup = () => {
    try {
      document.body.removeChild(iframe)
    } catch {
      // ignore
    }
  }

  const printNow = () => {
    const w = iframe.contentWindow
    if (!w) {
      cleanup()
      return
    }
    try {
      w.focus()
    } catch {
      // ignore
    }
    setTimeout(() => {
      try {
        w.print()
      } finally {
        setTimeout(cleanup, 500)
      }
    }, 150)
  }

  iframe.srcdoc = html
  iframe.onload = printNow
}

export function printMarketplaceUnloadWaybill(
  data: MarketplaceUnloadWaybillData,
): void {
  printShipmentWaybill({
    docKind: 'marketplace_unload',
    ...data,
    wbWarehouseLabel: data.wbWarehouseLabel,
  })
}

export function printOperationalOutboundWaybill(
  data: Omit<ShipmentWaybillData, 'docKind' | 'wbWarehouseLabel'>,
): void {
  printShipmentWaybill({
    docKind: 'operational_outbound',
    ...data,
  })
}

export function printInboundSupplyWaybill(
  data: Omit<
    ShipmentWaybillData,
    'docKind' | 'wbWarehouseLabel' | 'pickAllocations'
  >,
): void {
  printShipmentWaybill({
    docKind: 'inbound_intake',
    ...data,
  })
}
