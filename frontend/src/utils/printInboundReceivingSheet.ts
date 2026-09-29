import { escapeLabelHtml } from './productLabelText'

export type InboundReceivingSheetItem = {
  product_name: string
  /** Артикул продавца (vendor code); при отсутствии — SKU. */
  vendor_code: string
  sku_code: string
  /** ШК товара (штрихкод WB). */
  barcode: string | null
  /** Артикул WB (nmID). */
  wb_nm_id: number | null
  photo_url: string | null
  /** Сколько заявил селлер. */
  expected_qty: number
}

export type InboundReceivingSheetData = {
  documentNumber: string | null
  sellerName: string | null
  warehouseName: string
  plannedDate: string | null
  items: InboundReceivingSheetItem[]
}

function itemRow(item: InboundReceivingSheetItem, index: number): string {
  const photo = item.photo_url?.trim()
  const photoBlock = photo
    ? `<img class="rs-photo" src="${escapeLabelHtml(photo)}" alt="фото" onerror="this.style.display='none';this.nextElementSibling.style.display='flex'" />
       <div class="rs-photo rs-photo-empty" style="display:none">фото</div>`
    : `<div class="rs-photo rs-photo-empty">фото</div>`

  const article = item.vendor_code.trim() || item.sku_code.trim()
  const productMeta = [
    article ? `Арт.: ${article}` : '',
    item.sku_code.trim() ? `SKU: ${item.sku_code.trim()}` : '',
    item.wb_nm_id != null ? `Артикул WB: ${item.wb_nm_id}` : '',
  ]
    .filter(Boolean)
    .map((part) => `<span>${escapeLabelHtml(part)}</span>`)
    .join(' · ')
  const barcode = item.barcode?.trim() || '—'

  return `<tr data-testid="rs-sheet-card" data-row-index="${index}">
  <td class="rs-photo-cell">${photoBlock}</td>
  <td class="rs-product-cell">
    <p class="rs-name">${escapeLabelHtml(item.product_name)}</p>
    ${productMeta ? `<p class="rs-meta">${productMeta}</p>` : ''}
  </td>
  <td class="rs-barcode-cell" data-testid="receiving-sheet-barcode">${escapeLabelHtml(barcode)}</td>
  <td class="rs-expected-cell" data-testid="receiving-sheet-expected">${item.expected_qty}</td>
  <td class="rs-fact-cell" data-testid="receiving-sheet-fact"></td>
</tr>`
}

/** HTML листа приёмки с фото товаров и пустой колонкой «Факт» под ручной пересчёт (A4). */
export function buildInboundReceivingSheetHtml(data: InboundReceivingSheetData): string {
  const rows = data.items.map((item, i) => itemRow(item, i)).join('')
  const body =
    data.items.length > 0
      ? rows
      : '<p class="rs-empty" data-testid="rs-sheet-empty">Нет товаров для печати.</p>'
  const documentNumberLabel = data.documentNumber?.trim() || '—'
  return `<!doctype html>
<html>
  <head>
    <meta charset="utf-8" />
    <title>Лист приёмки — ${escapeLabelHtml(documentNumberLabel)}</title>
    <style>
      /* Ориентацию выбирает оператор в диалоге печати — не форсируем landscape в @page
         (иначе при Portrait в диалоге карточки уезжают за область печати). */
      @page { size: A4; margin: 7mm 8mm 8mm; }
      * { box-sizing: border-box; }
      body {
        font-family: system-ui, -apple-system, Segoe UI, Roboto, Arial, sans-serif;
        font-size: 10.5px;
        color: #111;
        margin: 0;
        width: 100%;
        -webkit-print-color-adjust: exact;
        print-color-adjust: exact;
      }
      h1 { font-size: 15px; margin: 0 0 5px; }
      .rs-head {
        display: grid;
        grid-template-columns: repeat(4, minmax(0, 1fr));
        gap: 3px 12px;
        margin: 0 0 8px;
        padding: 6px 8px;
        border: 1px solid #cfcfcf;
        background: #f6f6f6;
      }
      .rs-head dt { margin: 0; color: #555; font-size: 9px; text-transform: uppercase; }
      .rs-head dd { margin: 0; font-weight: 700; word-break: break-word; }
      table {
        width: 100%;
        border-collapse: collapse;
        table-layout: fixed;
      }
      th,
      td {
        border: 1px solid #cfcfcf;
        padding: 4px 5px;
        vertical-align: top;
      }
      th {
        background: #ececec;
        font-size: 9px;
        text-align: left;
        text-transform: uppercase;
        color: #444;
      }
      tr {
        page-break-inside: avoid;
        break-inside: avoid-page;
      }
      .rs-photo-cell { width: 24mm; }
      .rs-product-cell { width: auto; }
      .rs-barcode-cell { width: 30mm; word-break: break-word; font-weight: 700; }
      .rs-expected-cell { width: 20mm; text-align: right; font-weight: 700; font-size: 13px; }
      .rs-fact-cell { width: 20mm; min-height: 24mm; }
      .rs-photo {
        width: 21mm;
        height: 21mm;
        object-fit: contain;
        border: 1px solid #eee;
        display: block;
        margin: 0;
      }
      .rs-photo-empty {
        display: flex;
        align-items: center;
        justify-content: center;
        color: #999;
        font-size: 11px;
        background: #f5f5f5;
      }
      .rs-name { font-weight: 700; margin: 0 0 2px; word-break: break-word; }
      .rs-meta { margin: 0; color: #555; word-break: break-word; }
      .rs-empty { color: #555; }
    </style>
  </head>
  <body>
    <h1>Лист приёмки</h1>
    <dl class="rs-head">
      <div><dt>Номер</dt><dd>${escapeLabelHtml(documentNumberLabel)}</dd></div>
      <div><dt>Селлер</dt><dd>${escapeLabelHtml(data.sellerName ?? '—')}</dd></div>
      <div><dt>Склад</dt><dd>${escapeLabelHtml(data.warehouseName)}</dd></div>
      <div><dt>Дата</dt><dd>${escapeLabelHtml(data.plannedDate ?? '—')}</dd></div>
    </dl>
    ${
      data.items.length > 0
        ? `<table data-testid="receiving-sheet-table">
      <thead>
        <tr>
          <th>Фото</th>
          <th>Товар</th>
          <th>ШК</th>
          <th>Заявлено</th>
          <th>Факт</th>
        </tr>
      </thead>
      <tbody>${body}</tbody>
    </table>`
        : body
    }
  </body>
</html>`
}

declare global {
  interface Window {
    __WMS_CAPTURE_PRINT_HTML__?: boolean
    __WMS_LAST_PRINT_HTML__?: string
  }
}

/** Печать листа приёмки (A4, браузер). Ждёт загрузки фото (с таймаутом). */
export function printInboundReceivingSheet(data: InboundReceivingSheetData): void {
  const html = buildInboundReceivingSheetHtml(data)
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

  let printed = false
  const printNow = () => {
    if (printed) {
      return
    }
    printed = true
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
    }, 100)
  }

  iframe.srcdoc = html
  iframe.onload = () => {
    const doc = iframe.contentDocument
    const imgs = doc?.querySelectorAll('img') ?? []
    if (imgs.length === 0) {
      printNow()
      return
    }
    // Не блокируем печать надолго из-за внешних фото WB.
    const safety = setTimeout(printNow, 3000)
    let pending = imgs.length
    const done = () => {
      pending -= 1
      if (pending <= 0) {
        clearTimeout(safety)
        printNow()
      }
    }
    imgs.forEach((img) => {
      const el = img as HTMLImageElement
      if (el.complete) {
        done()
        return
      }
      el.addEventListener('load', done, { once: true })
      el.addEventListener('error', done, { once: true })
    })
  }
}
