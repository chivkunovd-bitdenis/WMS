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
  wb_size: string | null
  wb_composition: string | null
  photo_url: string | null
  /** Текст ТЗ на упаковку из карточки товара. */
  instructions: string | null
}

export type ShipmentPackagingSheetData = {
  documentNumber: string
  warehouseName: string
  sellerName: string | null
  createdAt: string | null
  items: PackagingSheetItem[]
}

function metaLine(label: string, value: string | null | undefined): string {
  const v = value?.toString().trim()
  if (!v) {
    return ''
  }
  return `<p class="pk-meta"><span class="pk-meta-label">${escapeLabelHtml(label)}</span> ${escapeLabelHtml(v)}</p>`
}

function itemCard(item: PackagingSheetItem, index: number): string {
  const photo = item.photo_url?.trim()
  const photoBlock = photo
    ? `<img class="pk-photo" src="${escapeLabelHtml(photo)}" alt="фото" onerror="this.style.display='none';this.nextElementSibling.style.display='flex'" />
       <div class="pk-photo pk-photo-empty" style="display:none">фото</div>`
    : `<div class="pk-photo pk-photo-empty">фото</div>`

  const article = item.vendor_code.trim() || item.sku_code.trim()
  const instructions = item.instructions?.trim()
  const instructionsBlock = instructions
    ? `<div class="pk-tz-text">${escapeLabelHtml(instructions)}</div>`
    : `<div class="pk-tz-text pk-tz-empty">ТЗ не заполнено</div>`

  return `<section class="pk-card" data-testid="tz-sheet-card" data-tz-index="${index}">
  <div class="pk-left">
    ${photoBlock}
    <div class="pk-fields">
      <p class="pk-name">${escapeLabelHtml(item.product_name)}</p>
      ${metaLine('Артикул продавца:', article)}
      ${metaLine('ШК:', item.barcode)}
      ${metaLine('Артикул WB:', item.wb_nm_id != null ? String(item.wb_nm_id) : null)}
      ${metaLine('Размер:', item.wb_size)}
      ${metaLine('Состав:', item.wb_composition)}
    </div>
  </div>
  <div class="pk-right">
    <h2 class="pk-tz-title">ТЗ на упаковку</h2>
    ${instructionsBlock}
  </div>
</section>`
}

/** HTML сводной печатной формы «ТЗ на упаковку» для всей отгрузки (A4, книжная). */
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
      @page { size: A4 portrait; margin: 12mm; }
      * { box-sizing: border-box; }
      body { font-family: system-ui, -apple-system, Segoe UI, Roboto, Arial, sans-serif; font-size: 12px; color: #111; margin: 0; }
      h1 { font-size: 18px; margin: 0 0 8px; }
      .pk-head { display: grid; grid-template-columns: 1fr 1fr; gap: 4px 24px; margin: 0 0 16px; }
      .pk-head dt { font-weight: 600; margin: 0; }
      .pk-head dd { margin: 0 0 4px; }
      .pk-card {
        display: flex;
        gap: 12px;
        border: 1px solid #ccc;
        border-radius: 4px;
        padding: 10px 12px;
        margin: 0 0 12px;
        page-break-inside: avoid;
        break-inside: avoid;
      }
      .pk-left { flex: 0 0 33%; max-width: 33%; }
      .pk-right { flex: 1 1 auto; min-width: 0; }
      .pk-photo {
        width: 100%;
        max-width: 45mm;
        height: 45mm;
        object-fit: contain;
        border: 1px solid #eee;
        display: block;
        margin: 0 0 6px;
      }
      .pk-photo-empty {
        display: flex;
        align-items: center;
        justify-content: center;
        color: #999;
        font-size: 11px;
        background: #f5f5f5;
      }
      .pk-name { font-weight: 600; margin: 0 0 4px; word-break: break-word; }
      .pk-meta { margin: 0 0 2px; word-break: break-word; }
      .pk-meta-label { font-weight: 600; }
      .pk-tz-title { font-size: 14px; margin: 0 0 6px; }
      .pk-tz-text {
        white-space: pre-wrap;
        word-break: break-word;
        line-height: 1.4;
      }
      .pk-tz-empty { color: #999; font-style: italic; }
      .pk-empty { color: #555; }
      .pk-foot { margin-top: 8px; font-size: 11px; color: #555; }
    </style>
  </head>
  <body>
    <h1>ТЗ на упаковку — Отгрузка ${escapeLabelHtml(data.documentNumber)}</h1>
    <dl class="pk-head">
      <dt>Склад ФФ</dt><dd>${escapeLabelHtml(data.warehouseName)}</dd>
      <dt>Селлер</dt><dd>${escapeLabelHtml(data.sellerName ?? '—')}</dd>
      <dt>Создано</dt><dd>${escapeLabelHtml(data.createdAt ?? '—')}</dd>
      <dt>Товаров</dt><dd>${data.items.length}</dd>
    </dl>
    ${body}
    <p class="pk-foot">Инструкции по упаковке для склада. Актуальная версия — в системе WMS.</p>
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
