import { escapeLabelHtml } from './productLabelText'

const LABEL_CSS = `
  @page { size: 58mm 40mm; margin: 0; }
  * { box-sizing: border-box; }
  html, body { margin: 0; padding: 0; }
  body { font-family: Arial, Helvetica, sans-serif; color: #111; background: #fff; }
  .label {
    width: 58mm;
    height: 40mm;
    padding: 1.5mm;
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    overflow: hidden;
    page-break-after: always;
    break-after: page;
  }
  .label:last-child { page-break-after: auto; break-after: auto; }
  .matrix img {
    width: 28mm;
    height: 28mm;
    object-fit: contain;
    display: block;
  }
  .tail {
    margin: 0.5mm 0 0;
    font-size: 5.5pt;
    text-align: center;
    word-break: break-all;
    line-height: 1.1;
    max-width: 54mm;
  }
`

export function maskCisCode(cis: string): string {
  const t = cis.trim()
  if (t.length <= 12) {
    return t
  }
  return `…${t.slice(-12)}`
}

export async function renderDataMatrixDataUrl(cis: string): Promise<string> {
  const bwipjs = await import('bwip-js')
  const canvas = document.createElement('canvas')
  bwipjs.toCanvas(canvas, {
    bcid: 'datamatrix',
    text: cis,
    scale: 2,
    height: 12,
    includetext: false,
  })
  return canvas.toDataURL('image/png')
}

function buildMarkingLabelHtml(cis: string, matrixDataUrl: string): string {
  return `<section class="label" data-testid="marking-thermal-label">
  <div class="matrix"><img src="${matrixDataUrl}" alt="ЧЗ" /></div>
  <p class="tail">${escapeLabelHtml(maskCisCode(cis))}</p>
</section>`
}

export function buildMarkingLabelsDocument(
  labels: { cis: string; matrixDataUrl: string }[],
): string {
  const body = labels.map((l) => buildMarkingLabelHtml(l.cis, l.matrixDataUrl)).join('')
  return `<!doctype html>
<html>
  <head>
    <meta charset="utf-8" />
    <title>Честный знак</title>
    <style>${LABEL_CSS}</style>
  </head>
  <body>${body}</body>
</html>`
}

export function expandCodesWithDuplicates(codes: string[], duplicateCopies: number): string[] {
  const copies = duplicateCopies === 2 ? 2 : 1
  const out: string[] = []
  for (const code of codes) {
    for (let i = 0; i < copies; i += 1) {
      out.push(code)
    }
  }
  return out
}

export async function printMarkingCodeLabels(
  codes: string[],
  duplicateCopies: number,
): Promise<void> {
  if (codes.length === 0) {
    throw new Error('Нет кодов для печати.')
  }
  const expanded = expandCodesWithDuplicates(codes, duplicateCopies)
  const unique = [...new Set(expanded)]
  const urlByCis = new Map<string, string>()
  await Promise.all(
    unique.map(async (cis) => {
      urlByCis.set(cis, await renderDataMatrixDataUrl(cis))
    }),
  )
  const labels = expanded.map((cis) => ({
    cis,
    matrixDataUrl: urlByCis.get(cis) ?? '',
  }))
  const html = buildMarkingLabelsDocument(labels)

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
    const imgs = doc?.querySelectorAll('img') ?? []
    if (imgs.length === 0) {
      printNow()
      return
    }
    let pending = imgs.length
    const done = () => {
      pending -= 1
      if (pending <= 0) {
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
