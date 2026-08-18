import { escapeLabelHtml } from './productLabelText'

export type PackagingSheetItem = {
  product_name: string
  /** Артикул продавца (vendor code); при отсутствии — SKU. */
  vendor_code: string
  sku_code: string
  /** ШК товара (штрихкод WB). */
  barcode: string | null
  /** Артикул WB (nmID). */
  wb_nm_id: number | null
  photo_url: string | null
  /** Текст ТЗ на упаковку из карточки товара. */
  instructions: string | null
  /** Количество по строке отгрузки. */
  quantity: number
}

export type ShipmentPackagingSheetData = {
  documentNumber: string
  documentType: string
  sellerName: string | null
  shipmentDate: string | null
  warehouseName: string
  marketplaceWarehouseName?: string | null
  createdAt?: string | null
  items: PackagingSheetItem[]
}

function itemRow(item: PackagingSheetItem, index: number): string {
  const photo = item.photo_url?.trim()
  const photoBlock = photo
    ? `<img class="pk-photo" src="${escapeLabelHtml(photo)}" alt="фото" onerror="this.style.display='none';this.nextElementSibling.style.display='flex'" />
       <div class="pk-photo pk-photo-empty" style="display:none">фото</div>`
    : `<div class="pk-photo pk-photo-empty">фото</div>`

  const article = item.vendor_code.trim() || item.sku_code.trim()
  const productMeta = [
    article ? `Арт.: ${article}` : '',
    item.sku_code.trim() ? `SKU: ${item.sku_code.trim()}` : '',
    item.wb_nm_id != null ? `Артикул WB: ${item.wb_nm_id}` : '',
  ]
    .filter(Boolean)
    .map((part) => `<span>${escapeLabelHtml(part)}</span>`)
    .join(' · ')
  const instructions = item.instructions?.trim()
  const instructionsBlock = instructions
    ? `<div class="pk-instructions-text">${escapeLabelHtml(instructions)}</div>`
    : `<div class="pk-instructions-text pk-empty-text">Инструкция не заполнена</div>`
  const barcode = item.barcode?.trim() || '—'

  return `<tr data-testid="tz-sheet-card" data-row-index="${index}">
  <td class="pk-photo-cell">${photoBlock}</td>
  <td class="pk-product-cell">
    <p class="pk-name">${escapeLabelHtml(item.product_name)}</p>
    ${productMeta ? `<p class="pk-meta">${productMeta}</p>` : ''}
  </td>
  <td class="pk-barcode-cell" data-testid="shipment-sheet-barcode">${escapeLabelHtml(barcode)}</td>
  <td class="pk-qty-cell" data-testid="tz-sheet-qty">${item.quantity}</td>
  <td class="pk-instructions-cell" data-testid="shipment-sheet-instructions">${instructionsBlock}</td>
  <td class="pk-fact-cell" data-testid="shipment-sheet-fact"></td>
</tr>`
}

/** HTML компактного листа отгрузки с упаковочными инструкциями (A4). */
export function buildShipmentPackagingSheetHtml(data: ShipmentPackagingSheetData): string {
  const rows = data.items.map((item, i) => itemRow(item, i)).join('')
  const body =
    data.items.length > 0
      ? rows
      : '<p class="pk-empty" data-testid="tz-sheet-empty">Нет товаров для печати.</p>'
  const marketplaceWarehouse = data.marketplaceWarehouseName?.trim()
  const createdAt = data.createdAt?.trim()
  return `<!doctype html>
<html>
  <head>
    <meta charset="utf-8" />
    <title>Лист отгрузки — ${escapeLabelHtml(data.documentNumber)}</title>
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
      .pk-head {
        display: grid;
        grid-template-columns: repeat(3, minmax(0, 1fr));
        gap: 3px 12px;
        margin: 0 0 8px;
        padding: 6px 8px;
        border: 1px solid #cfcfcf;
        background: #f6f6f6;
      }
      .pk-head dt { margin: 0; color: #555; font-size: 9px; text-transform: uppercase; }
      .pk-head dd { margin: 0; font-weight: 700; word-break: break-word; }
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
      .pk-photo-cell { width: 24mm; }
      .pk-product-cell { width: 35%; }
      .pk-barcode-cell { width: 24mm; word-break: break-word; font-weight: 700; }
      .pk-qty-cell { width: 14mm; text-align: right; font-weight: 700; font-size: 13px; }
      .pk-instructions-cell { width: auto; }
      .pk-fact-cell { width: 18mm; min-height: 24mm; }
      .pk-photo {
        width: 21mm;
        height: 21mm;
        object-fit: contain;
        border: 1px solid #eee;
        display: block;
        margin: 0;
      }
      .pk-photo-empty {
        display: flex;
        align-items: center;
        justify-content: center;
        color: #999;
        font-size: 11px;
        background: #f5f5f5;
      }
      .pk-name { font-weight: 700; margin: 0 0 2px; word-break: break-word; }
      .pk-meta { margin: 0; color: #555; word-break: break-word; }
      .pk-instructions-text {
        white-space: pre-wrap;
        word-break: break-word;
        line-height: 1.35;
      }
      .pk-empty-text { color: #999; font-style: italic; }
      .pk-empty { color: #555; }
    </style>
  </head>
  <body>
    <h1>Лист отгрузки</h1>
    <dl class="pk-head">
      <div><dt>Селлер</dt><dd>${escapeLabelHtml(data.sellerName ?? '—')}</dd></div>
      <div><dt>Дата</dt><dd>${escapeLabelHtml(data.shipmentDate ?? createdAt ?? '—')}</dd></div>
      <div><dt>Тип</dt><dd>${escapeLabelHtml(data.documentType)}</dd></div>
      <div><dt>Номер</dt><dd>${escapeLabelHtml(data.documentNumber)}</dd></div>
      <div><dt>Склад ФФ</dt><dd>${escapeLabelHtml(data.warehouseName)}</dd></div>
      <div><dt>Склад МП</dt><dd>${escapeLabelHtml(marketplaceWarehouse || '—')}</dd></div>
    </dl>
    ${
      data.items.length > 0
        ? `<table data-testid="shipment-sheet-table">
      <thead>
        <tr>
          <th>Фото</th>
          <th>Товар</th>
          <th>ШК</th>
          <th>Кол-во</th>
          <th>Инструкции</th>
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

/** Печать компактного листа отгрузки (A4, браузер). Ждёт загрузки фото (с таймаутом). */
export function printShipmentPackagingSheet(data: ShipmentPackagingSheetData): void {
  const html = buildShipmentPackagingSheetHtml(data)
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
