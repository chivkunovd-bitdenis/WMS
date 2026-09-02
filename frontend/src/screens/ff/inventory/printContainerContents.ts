import type { ContainerContents, ContentsRow } from './containerContents'

/**
 * Печать описи содержимого тары — лист А4, который клеят на короб.
 *
 * Кегль крупный намеренно: лист читают с расстояния, стоя у стеллажа, а не с
 * рабочего стола. Опознание тары идёт по коду с её физического ярлыка, поэтому
 * он и стоит крупно в чёрной плашке; номер из дерева документа печатается мелко,
 * рядом с остальной служебной строкой.
 *
 * Печатаем через скрытый iframe тем же способом, что и этикетки штрихкода
 * (`utils/printBarcodeLabel`): открытая вкладка мешает оператору, а браузер
 * умеет закрыть её сам далеко не всегда.
 */

function escapeHtml(text: string): string {
  return text
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;')
}

export type ContainerContentsPrintOptions = {
  contents: ContainerContents
  /** Номер документа пересчёта: «ИНВ-1F69E69A». */
  documentNumber: string
  /** Дата пересчёта, уже в человеческом виде. */
  documentDate: string
}

function rowHtml(row: ContentsRow, index: number): string {
  const photo = row.photoUrl
    ? `<img class="photo" src="${escapeHtml(row.photoUrl)}" alt="" />`
    : '<span class="photo photo--empty"></span>'
  const ledgerMark = row.fromLedger ? '<span class="ledger">по учёту</span>' : ''
  return `<tr>
      <td class="num">${index + 1}</td>
      <td class="pic">${photo}</td>
      <td class="name">${escapeHtml(row.name)}</td>
      <td class="size">${escapeHtml(row.size ?? '—')}</td>
      <td class="code">${escapeHtml(row.barcode ?? '—')}</td>
      <td class="art">${escapeHtml(row.vendorCode ?? '—')}</td>
      <td class="qty">${row.quantity}${ledgerMark}</td>
    </tr>`
}

export function printContainerContents(options: ContainerContentsPrintOptions): void {
  const { contents, documentNumber, documentDate } = options
  const hasLedgerRows = contents.rows.some((row) => row.fromLedger)

  const meta = [
    ['Документ', documentNumber],
    ['Пересчёт от', documentDate],
    ...(contents.cellLabel ? [['Место', contents.cellLabel]] : []),
    ['Номер в дереве', contents.treeCode],
  ]
    .map(
      ([key, value]) =>
        `<div><span class="k">${escapeHtml(key as string)}</span><span class="v">${escapeHtml(value as string)}</span></div>`,
    )
    .join('')

  const html = `<!doctype html>
<html lang="ru">
  <head>
    <meta charset="utf-8" />
    <title>Опись ${escapeHtml(contents.label)}</title>
    <style>
      @page { size: A4 portrait; margin: 12mm; }
      * { box-sizing: border-box; }
      body {
        margin: 0;
        color: #14110F;
        background: #FFFFFF;
        font-family: "Arial Narrow", Arial, Helvetica, system-ui, sans-serif;
        font-variant-numeric: tabular-nums;
      }
      .seller {
        margin: 0;
        font-size: 22mm;
        line-height: 0.95;
        font-weight: 800;
        letter-spacing: -0.01em;
        text-transform: uppercase;
      }
      .plate {
        margin-top: 4mm;
        padding: 3mm 5mm 4mm;
        background: #14110F;
        color: #FFFFFF;
      }
      .plate .kind {
        font-size: 5mm;
        letter-spacing: 0.28em;
        text-transform: uppercase;
        opacity: 0.75;
      }
      .plate .code {
        margin-top: 1mm;
        font-family: "Courier New", ui-monospace, monospace;
        font-size: 11mm;
        line-height: 1;
        font-weight: 700;
      }
      .meta {
        margin-top: 4mm;
        padding-top: 2.5mm;
        border-top: 0.6mm solid #14110F;
        display: flex;
        flex-wrap: wrap;
        gap: 2mm 8mm;
        font-size: 3.6mm;
      }
      .meta div { display: flex; gap: 2mm; align-items: baseline; }
      .meta .k { font-size: 2.8mm; letter-spacing: 0.1em; text-transform: uppercase; color: #6E6862; }
      .meta .v { font-weight: 700; font-family: "Courier New", monospace; }
      table { margin-top: 6mm; width: 100%; border-collapse: collapse; }
      thead th {
        font-size: 3.4mm;
        letter-spacing: 0.12em;
        text-transform: uppercase;
        text-align: left;
        font-weight: 700;
        padding: 0 2mm 2mm 0;
        border-bottom: 1.1mm solid #14110F;
        white-space: nowrap;
      }
      tbody td {
        padding: 2.4mm 2mm;
        border-bottom: 0.25mm solid #BDB7B1;
        vertical-align: middle;
        font-size: 4.4mm;
      }
      tbody tr { break-inside: avoid; page-break-inside: avoid; }
      /* Ширины — общие для шапки и тела, иначе колонки разъезжаются. Кегль и
         начертание задаются ТОЛЬКО телу: без этого крупный шрифт ячейки
         «Штук» вытягивал и заголовок, и шапка читалась криво. */
      .num { width: 7mm; padding-left: 0; }
      .pic { width: 22mm; }
      .size { width: 16mm; text-align: center; }
      .code { width: 40mm; }
      .art { width: 24mm; }
      .qty { width: 20mm; text-align: right; }
      tbody .num { color: #6E6862; font-size: 3.6mm; }
      .photo { display: block; width: 18mm; height: 18mm; object-fit: cover; border: 0.25mm solid #BDB7B1; }
      .photo--empty { background: #F1EEEB; }
      tbody .name { font-weight: 600; }
      tbody .size { font-size: 6mm; font-weight: 700; }
      tbody .code { font-family: "Courier New", monospace; font-size: 4.2mm; }
      tbody .art { font-family: "Courier New", monospace; font-size: 4.2mm; }
      tbody .qty { font-size: 8mm; font-weight: 800; line-height: 1; }
      .ledger {
        display: block;
        font-size: 2.6mm;
        font-weight: 400;
        letter-spacing: 0.06em;
        text-transform: uppercase;
        color: #6E6862;
      }
      .totals {
        margin-top: 4mm;
        padding-top: 4mm;
        border-top: 1.1mm solid #14110F;
        display: flex;
        align-items: baseline;
        gap: 8mm;
        flex-wrap: wrap;
      }
      .totals .label { font-size: 4mm; letter-spacing: 0.12em; text-transform: uppercase; font-weight: 700; }
      .totals .big { font-size: 11mm; font-weight: 800; line-height: 1; margin-left: 2mm; }
      .totals .sign { margin-left: auto; font-size: 3.4mm; color: #6E6862; }
      .totals .sign span { display: inline-block; border-bottom: 0.3mm solid #14110F; width: 34mm; }
      .footnote { margin-top: 3mm; font-size: 3mm; color: #6E6862; }
      .empty { margin-top: 8mm; font-size: 6mm; font-weight: 700; }
    </style>
  </head>
  <body>
    <p class="seller">${escapeHtml(contents.seller)}</p>
    <div class="plate">
      <div class="kind">${escapeHtml(contents.treeCode.split(' ')[0] ?? 'Тара')}</div>
      <div class="code">${escapeHtml(contents.label)}</div>
    </div>
    <div class="meta">${meta}</div>
    ${
      contents.rows.length === 0
        ? '<p class="empty">Внутри пусто — печатать нечего.</p>'
        : `<table>
      <thead>
        <tr>
          <th class="num">№</th>
          <th class="pic">Фото</th>
          <th>Товар</th>
          <th class="size">Размер</th>
          <th class="code">Штрихкод</th>
          <th class="art">Артикул</th>
          <th class="qty">Штук</th>
        </tr>
      </thead>
      <tbody>
        ${contents.rows.map(rowHtml).join('\n')}
      </tbody>
    </table>
    <div class="totals">
      <div><span class="label">Позиций</span><span class="big">${contents.rows.length}</span></div>
      <div><span class="label">Всего штук</span><span class="big">${contents.totalPieces}</span></div>
      <div class="sign">Считал <span></span> &nbsp; Дата <span></span></div>
    </div>
    ${
      hasLedgerRows
        ? '<p class="footnote">Строки с пометкой «по учёту» на пересчёте ещё не трогали: там стоит число из системы, а не посчитанное руками.</p>'
        : ''
    }`
    }
  </body>
</html>`

  if (window.__WMS_CAPTURE_PRINT_HTML__) {
    window.__WMS_LAST_PRINT_HTML__ = html
  }

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
      // уже убран
    }
  }

  const printNow = () => {
    const frameWindow = iframe.contentWindow
    if (!frameWindow) {
      cleanup()
      return
    }
    try {
      frameWindow.focus()
    } catch {
      // фокус не обязателен
    }
    setTimeout(() => {
      frameWindow.addEventListener('afterprint', cleanup, { once: true })
      try {
        if (window.__WMS_CAPTURE_PRINT_HTML__) {
          window.__WMS_PRINT_JOB_COUNT__ = (window.__WMS_PRINT_JOB_COUNT__ ?? 0) + 1
        }
        frameWindow.print()
      } catch {
        cleanup()
      }
    }, 100)
  }

  iframe.srcdoc = html
  iframe.onload = () => {
    const doc = iframe.contentDocument
    const images = Array.from(doc?.querySelectorAll<HTMLImageElement>('img.photo') ?? [])
    if (images.length === 0) {
      printNow()
      return
    }
    // Ждём картинки, но не заложником: снимок с маркетплейса может не открыться,
    // а опись без фото всё равно нужна — печатаем как есть.
    Promise.allSettled(images.map((image) => image.decode())).then(printNow)
  }
}
