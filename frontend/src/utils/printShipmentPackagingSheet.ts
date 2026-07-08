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
  sellerName: string | null
  items: PackagingSheetItem[]
}

function itemCard(item: PackagingSheetItem, index: number): string {
  const photo = item.photo_url?.trim()
  const photoBlock = photo
    ? `<img class="pk-photo" src="${escapeLabelHtml(photo)}" alt="фото" onerror="this.style.display='none';this.nextElementSibling.style.display='flex'" />
       <div class="pk-photo pk-photo-empty" style="display:none">фото</div>`
    : `<div class="pk-photo pk-photo-empty">фото</div>`

  const article = item.vendor_code.trim() || item.sku_code.trim()
  const metaParts = [
    article ? `Артикул продавца: ${article}` : '',
    item.wb_nm_id != null ? `Артикул WB: ${item.wb_nm_id}` : '',
  ]
    .filter(Boolean)
    .map((part) => `<span class="pk-meta-part">${escapeLabelHtml(part)}</span>`)
    .join('')
  const barcodeLine = item.barcode?.trim()
    ? `<p class="pk-barcode">ШК: ${escapeLabelHtml(item.barcode.trim())}</p>`
    : ''
  const instructions = item.instructions?.trim()
  const instructionsBlock = instructions
    ? `<div class="pk-tz-text">${escapeLabelHtml(instructions)}</div>`
    : `<div class="pk-tz-text pk-tz-empty">ТЗ не заполнено</div>`

  return `<section class="pk-card" data-testid="tz-sheet-card" data-tz-index="${index}">
  <div class="pk-left">
    ${photoBlock}
  </div>
  <div class="pk-main">
    <div class="pk-product">
      <p class="pk-name">${escapeLabelHtml(item.product_name)}</p>
      ${metaParts ? `<p class="pk-meta">${metaParts}</p>` : ''}
      ${barcodeLine}
    </div>
    <div class="pk-tz">
      <p class="pk-tz-title">ТЗ на упаковку</p>
      ${instructionsBlock}
    </div>
  </div>
  <div class="pk-qty-col" data-testid="tz-sheet-qty">
    <span class="pk-qty-label">Кол-во</span>
    <span class="pk-qty-value">${item.quantity}</span>
  </div>
</section>`
}

/** HTML сводной печатной формы «ТЗ на упаковку» для всей отгрузки (A4). */
export function buildShipmentPackagingSheetHtml(data: ShipmentPackagingSheetData): string {
  const cards = data.items.map((item, i) => itemCard(item, i)).join('')
  const body =
    data.items.length > 0
      ? cards
      : '<p class="pk-empty" data-testid="tz-sheet-empty">Нет товаров для печати.</p>'
  return `<!doctype html>
<html>
  <head>
    <meta charset="utf-8" />
    <title>ТЗ на упаковку — ${escapeLabelHtml(data.documentNumber)}</title>
    <style>
      @page { size: A4 landscape; margin: 4mm 10mm 6mm; }
      * { box-sizing: border-box; }
      body {
        font-family: system-ui, -apple-system, Segoe UI, Roboto, Arial, sans-serif;
        font-size: 12px;
        color: #111;
        margin: 0;
        -webkit-print-color-adjust: exact;
        print-color-adjust: exact;
      }
      h1 { font-size: 14px; margin: 0 0 1px; }
      .pk-head { margin: 0 0 6px; font-size: 11px; color: #444; }
      /* Одинаковые прямоугольные строки на всю ширину, высотой с фото товара. */
      .pk-card {
        display: flex;
        gap: 8px;
        border: 1px solid #bbb;
        border-radius: 4px;
        padding: 6px;
        margin: 0 0 8px;
        page-break-inside: avoid;
        break-inside: avoid;
      }
      .pk-left { flex: 0 0 40mm; }
      .pk-main { flex: 1 1 auto; min-width: 0; display: flex; flex-direction: column; }
      .pk-photo {
        width: 40mm;
        height: 40mm;
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
      /* Серая плашка — данные товара; ниже — задание на упаковку. */
      .pk-product {
        background: #e8e8e8;
        border: 1px solid #ccc;
        border-radius: 3px;
        padding: 4px 8px;
      }
      .pk-name { font-weight: 700; margin: 0; word-break: break-word; }
      .pk-meta { margin: 2px 0 0; word-break: break-word; }
      .pk-meta-part { margin-right: 12px; }
      .pk-barcode { margin: 2px 0 0; font-weight: 700; word-break: break-word; }
      .pk-tz { margin-top: 5px; }
      .pk-tz-title {
        margin: 0 0 2px;
        font-size: 10px;
        font-weight: 600;
        color: #555;
        text-transform: uppercase;
        letter-spacing: 0.04em;
      }
      .pk-tz-text {
        white-space: pre-wrap;
        word-break: break-word;
        line-height: 1.4;
      }
      .pk-tz-empty { color: #999; font-style: italic; }
      .pk-qty-col {
        flex: 0 0 16mm;
        display: flex;
        flex-direction: column;
        align-items: center;
        justify-content: flex-start;
        border-left: 1px solid #ddd;
        padding-left: 6px;
        margin-left: 4px;
      }
      .pk-qty-label {
        font-size: 9px;
        font-weight: 600;
        color: #555;
        text-transform: uppercase;
        letter-spacing: 0.04em;
      }
      .pk-qty-value {
        margin-top: 4px;
        font-size: 16px;
        font-weight: 700;
        line-height: 1.2;
      }
      .pk-empty { color: #555; }
    </style>
  </head>
  <body>
    <h1>ТЗ на упаковку — Отгрузка ${escapeLabelHtml(data.documentNumber)}</h1>
    <p class="pk-head">Селлер: ${escapeLabelHtml(data.sellerName ?? '—')} · Товаров: ${data.items.length}</p>
    ${body}
  </body>
</html>`
}

declare global {
  interface Window {
    __WMS_CAPTURE_PRINT_HTML__?: boolean
    __WMS_LAST_PRINT_HTML__?: string
  }
}

/** Печать сводной формы ТЗ на упаковку (A4, браузер). Ждёт загрузки фото (с таймаутом). */
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
