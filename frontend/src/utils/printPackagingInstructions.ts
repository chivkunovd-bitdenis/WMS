export type PackagingInstructionsPrintData = {
  sku_code: string
  product_name: string
  seller_name?: string | null
  instructions: string
  requires_honest_sign?: boolean
}

function escapeHtml(text: string): string {
  return text
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;')
}

/** HTML для печати ТЗ на упаковку (A4). */
export function buildPackagingInstructionsPrintHtml(data: PackagingInstructionsPrintData): string {
  const instructions = data.instructions.trim()
  const honestSignNote = data.requires_honest_sign
    ? '<p class="flag">Нужен Честный знак при упаковке</p>'
    : ''

  return `<!doctype html>
<html>
  <head>
    <meta charset="utf-8" />
    <title>ТЗ на упаковку — ${escapeHtml(data.sku_code)}</title>
    <style>
      @page { size: A4; margin: 12mm; }
      body {
        font-family: system-ui, -apple-system, Segoe UI, Roboto, Arial, sans-serif;
        font-size: 13px;
        color: #111;
        line-height: 1.45;
      }
      h1 { font-size: 20px; margin: 0 0 12px; }
      .meta { display: grid; grid-template-columns: 140px 1fr; gap: 4px 16px; margin-bottom: 20px; }
      .meta dt { font-weight: 600; margin: 0; }
      .meta dd { margin: 0; }
      h2 { font-size: 15px; margin: 0 0 8px; }
      .instructions {
        border: 1px solid #ccc;
        border-radius: 4px;
        padding: 12px 14px;
        min-height: 120mm;
        white-space: pre-wrap;
        word-break: break-word;
      }
      .instructions.empty { color: #777; font-style: italic; }
      .flag {
        margin: 0 0 12px;
        padding: 8px 10px;
        border: 1px solid #f0ad4e;
        background: #fff8e6;
        border-radius: 4px;
        font-weight: 600;
      }
      .foot { margin-top: 20px; font-size: 11px; color: #555; }
    </style>
  </head>
  <body>
    <h1>ТЗ на упаковку</h1>
    <dl class="meta">
      <dt>SKU</dt><dd>${escapeHtml(data.sku_code)}</dd>
      <dt>Товар</dt><dd>${escapeHtml(data.product_name)}</dd>
      <dt>Селлер</dt><dd>${escapeHtml(data.seller_name?.trim() || '—')}</dd>
    </dl>
    ${honestSignNote}
    <h2>Инструкция для склада</h2>
    <div class="instructions${instructions ? '' : ' empty'}">${
      instructions ? escapeHtml(instructions) : 'Инструкция не заполнена'
    }</div>
    <p class="foot">Печать для склада. Актуальная версия — в системе WMS.</p>
  </body>
</html>`
}

/** Печать ТЗ на упаковку (A4, браузер). */
export function printPackagingInstructions(data: PackagingInstructionsPrintData): void {
  const html = buildPackagingInstructionsPrintHtml(data)
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
