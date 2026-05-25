export type WaybillLine = {
  sku_code: string
  product_name: string
  quantity: number
  shipped_qty?: number
  storage_location_code?: string | null
}

export type ShipmentWaybillDocKind = 'marketplace_unload' | 'operational_outbound'

export type ShipmentWaybillData = {
  docKind: ShipmentWaybillDocKind
  documentId: string
  statusLabel: string
  warehouseName: string
  sellerName: string | null
  wbWarehouseLabel?: string | null
  plannedDate: string | null
  createdAt: string | null
  lines: WaybillLine[]
  pickAllocations?: { location_code: string; sku_code: string; quantity: number }[]
}

/** @deprecated Use ShipmentWaybillData + printShipmentWaybill */
export type MarketplaceUnloadWaybillData = Omit<ShipmentWaybillData, 'docKind'> & {
  wbWarehouseLabel: string | null
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
  return 'Накладная — отгрузка со склада'
}

/** Печать накладной отгрузки (A4, браузер). */
export function printShipmentWaybill(data: ShipmentWaybillData): void {
  const isOperational = data.docKind === 'operational_outbound'
  const lineRows = data.lines
    .map((ln, i) => {
      const shipped =
        isOperational && ln.shipped_qty != null
          ? `<td align="right">${ln.shipped_qty}</td>`
          : ''
      const cell =
        isOperational
          ? `<td>${escapeHtml(ln.storage_location_code ?? '—')}</td>`
          : ''
      return `<tr>
          <td>${i + 1}</td>
          <td>${escapeHtml(ln.sku_code)}</td>
          <td>${escapeHtml(ln.product_name)}</td>
          ${cell}
          <td align="right">${ln.quantity}</td>
          ${shipped}
        </tr>`
    })
    .join('')

  const headShipped = isOperational ? '<th align="right">Отгружено</th>' : ''
  const headCell = isOperational ? '<th>Ячейка</th>' : ''

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

  const html = `<!doctype html>
<html>
  <head>
    <meta charset="utf-8" />
    <title>Накладная ${escapeHtml(data.documentId.slice(0, 8))}</title>
    <style>
      @page { margin: 12mm; }
      body { font-family: system-ui, -apple-system, Segoe UI, Roboto, Arial, sans-serif; font-size: 12px; color: #111; }
      h1 { font-size: 18px; margin: 0 0 8px; }
      h2 { font-size: 14px; margin: 16px 0 8px; }
      .meta { display: grid; grid-template-columns: 1fr 1fr; gap: 6px 24px; margin-bottom: 16px; }
      .meta dt { font-weight: 600; margin: 0; }
      .meta dd { margin: 0 0 6px; }
      table { width: 100%; border-collapse: collapse; }
      th, td { border: 1px solid #ccc; padding: 6px 8px; text-align: left; }
      th { background: #f5f5f5; }
      .foot { margin-top: 24px; font-size: 11px; color: #555; }
    </style>
  </head>
  <body>
    <h1>${docTitle(data.docKind)}</h1>
    <dl class="meta">
      <dt>Документ</dt><dd>${escapeHtml(data.documentId)}</dd>
      <dt>Статус</dt><dd>${escapeHtml(data.statusLabel)}</dd>
      <dt>Склад ФФ</dt><dd>${escapeHtml(data.warehouseName)}</dd>
      <dt>Селлер</dt><dd>${escapeHtml(data.sellerName ?? '—')}</dd>
      ${wbMeta}
      <dt>Плановая дата</dt><dd>${escapeHtml(data.plannedDate ?? '—')}</dd>
      <dt>Создано</dt><dd>${escapeHtml(data.createdAt ?? '—')}</dd>
    </dl>
    <h2>Состав</h2>
    <table>
      <thead>
        <tr><th>#</th><th>SKU</th><th>Наименование</th>${headCell}<th align="right">Кол-во</th>${headShipped}</tr>
      </thead>
      <tbody>${lineRows || '<tr><td colspan="6">Нет строк</td></tr>'}</tbody>
    </table>
    ${pickBlock}
    <p class="foot">Печать для сверки перед вывозом. Факт отгрузки — в системе WMS.</p>
  </body>
</html>`

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
