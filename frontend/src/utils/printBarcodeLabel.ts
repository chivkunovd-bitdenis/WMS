/** Print a CODE128 label (58×40 workflow — same iframe pattern as catalog cell labels). */
export function printBarcodeLabel(options: {
  title: string
  barcode: string
  barcodeDataUrl: string
}): void {
  const { title, barcode, barcodeDataUrl } = options
  const html = `<!doctype html>
<html>
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>Print barcode</title>
    <style>
      @page { margin: 10mm; }
      body { font-family: system-ui, -apple-system, Segoe UI, Roboto, Arial, sans-serif; padding: 0; margin: 0; }
      .wrap { display: grid; gap: 8px; justify-items: center; }
      .title { font-size: 14px; font-weight: 700; }
      .code { font-size: 12px; font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace; }
      img { width: 320px; height: auto; }
    </style>
  </head>
  <body>
    <div class="wrap">
      <div class="title">${title}</div>
      <img id="barcode" src="${barcodeDataUrl}" alt="barcode" />
      <div class="code">${barcode}</div>
    </div>
  </body>
</html>`

  const iframe = document.createElement('iframe')
  iframe.setAttribute('aria-hidden', 'true')
  iframe.style.position = 'fixed'
  iframe.style.right = '0'
  iframe.style.bottom = '0'
  iframe.style.width = '0'
  iframe.style.height = '0'
  iframe.style.border = '0'
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
    }, 100)
  }

  iframe.srcdoc = html
  iframe.onload = () => {
    const doc = iframe.contentDocument
    const img = doc?.getElementById('barcode') as HTMLImageElement | null
    if (!img) {
      printNow()
      return
    }
    if (img.complete) {
      printNow()
      return
    }
    img.addEventListener('load', printNow, { once: true })
    img.addEventListener('error', printNow, { once: true })
  }
}
