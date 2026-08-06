export function ordersWord(count: number) {
  const lastTwo = Math.abs(count) % 100
  if (lastTwo >= 11 && lastTwo <= 14) return 'заказов'
  const last = lastTwo % 10
  if (last === 1) return 'заказ'
  if (last >= 2 && last <= 4) return 'заказа'
  return 'заказов'
}

export function normalizeMetadataKind(kind: string | undefined) {
  const normalized = kind?.toLowerCase() ?? 'sgtin'
  return normalized === 'kiz' ? 'sgtin' : normalized
}

export function metadataKindLabel(kind: string) {
  const normalized = normalizeMetadataKind(kind)
  return ({ sgtin: 'КИЗ', uin: 'УИН', imei: 'IMEI', gtin: 'GTIN' } as Record<string, string>)[normalized]
    ?? 'Идентификатор'
}

export type LatestRequestGuard = {
  begin: () => number
  isCurrent: (generation: number) => boolean
  invalidate: () => void
}

/**
 * Generation guard for polling and async effects. Only the newest request may
 * commit its result; closing/changing the screen invalidates in-flight work.
 */
export function createLatestRequestGuard(): LatestRequestGuard {
  let generation = 0
  return {
    begin: () => {
      generation += 1
      return generation
    },
    isCurrent: (candidate) => candidate === generation,
    invalidate: () => {
      generation += 1
    },
  }
}

export function supportsFbsCommonSupplyQr(
  supply: { delivery_type: 'warehouse_sc' | 'pvz' } | null | undefined,
): boolean {
  return supply?.delivery_type === 'warehouse_sc'
}

/**
 * Binds one idempotency key to every retry of the same logical mutation.
 * A timeout may happen after the server committed, so generating a fresh key
 * inside the retry callback could duplicate the operation.
 */
export function bindFbsIdempotencyKey<T>(
  idempotencyKey: string,
  operation: (idempotencyKey: string) => Promise<T>,
): () => Promise<T> {
  return () => operation(idempotencyKey)
}

export type FbsPickingListPrintRow = {
  name: string
  imageUrl: string | null
  identifiers: string[]
  locations: string[]
  required: number
  picked: number
  wbOrders: number[]
  marking: string
}

export type FbsPickingListPrintInput = {
  supplyName: string
  wbSupplyId: string
  sellerName: string
  wmsWarehouseName: string
  routeLabel: string
  deadlineLabel: string
  printedAtLabel: string
  rows: FbsPickingListPrintRow[]
}

function escapePrintHtml(value: string | number) {
  return String(value)
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;')
    .replaceAll("'", '&#039;')
}

function printableImageUrl(value: string | null) {
  if (!value || !/^(https?:|data:image\/)/i.test(value)) return ''
  return escapePrintHtml(value)
}

export function buildFbsPickingListPrintHtml(input: FbsPickingListPrintInput) {
  const rows = input.rows.map((row, index) => {
    const imageUrl = printableImageUrl(row.imageUrl)
    return `
      <tr>
        <td class="number">${index + 1}</td>
        <td class="image">${imageUrl ? `<img src="${imageUrl}" alt="" />` : '<span>—</span>'}</td>
        <td>
          <strong>${escapePrintHtml(row.name)}</strong>
          <div class="muted">${row.identifiers.length ? row.identifiers.map(escapePrintHtml).join(' · ') : 'Идентификаторы не указаны'}</div>
        </td>
        <td>${row.locations.length ? row.locations.map(escapePrintHtml).join('<br />') : 'Ячейка не назначена'}</td>
        <td>${row.wbOrders.map((id) => `№${escapePrintHtml(id)}`).join('<br />')}</td>
        <td class="quantity">${escapePrintHtml(row.required)}</td>
        <td class="quantity">${escapePrintHtml(row.picked)} / ${escapePrintHtml(row.required)}</td>
        <td>${escapePrintHtml(row.marking)}</td>
      </tr>`
  }).join('')

  return `<!doctype html>
<html lang="ru">
  <head>
    <meta charset="utf-8" />
    <title>Лист подбора — ${escapePrintHtml(input.supplyName)}</title>
    <style>
      @page { size: A4 landscape; margin: 10mm; }
      * { box-sizing: border-box; }
      body { margin: 0; color: #172033; font: 12px/1.35 Arial, sans-serif; }
      h1 { margin: 0 0 4px; font-size: 22px; }
      .subtitle { margin-bottom: 14px; color: #5c6475; }
      .meta { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 8px; margin-bottom: 14px; }
      .meta div { border: 1px solid #d9dce5; border-radius: 6px; padding: 7px 9px; }
      .meta span { display: block; color: #687083; font-size: 10px; }
      .meta strong { display: block; margin-top: 2px; }
      table { width: 100%; border-collapse: collapse; table-layout: fixed; }
      th, td { border: 1px solid #cfd3df; padding: 6px; text-align: left; vertical-align: middle; overflow-wrap: anywhere; }
      th { background: #f1eefb; font-size: 10px; text-transform: uppercase; }
      tr { break-inside: avoid; }
      .number { width: 28px; text-align: center; }
      .image { width: 54px; text-align: center; }
      .image img { display: block; width: 42px; height: 42px; margin: auto; object-fit: contain; }
      .quantity { width: 62px; text-align: center; font-weight: 700; }
      .muted { margin-top: 3px; color: #687083; font-size: 10px; }
      .footer { margin-top: 8px; color: #687083; font-size: 10px; }
    </style>
  </head>
  <body>
    <h1>Лист подбора FBS</h1>
    <div class="subtitle">${escapePrintHtml(input.supplyName)} · № WB ${escapePrintHtml(input.wbSupplyId)}</div>
    <div class="meta">
      <div><span>Селлер</span><strong>${escapePrintHtml(input.sellerName)}</strong></div>
      <div><span>Склад WMS</span><strong>${escapePrintHtml(input.wmsWarehouseName)}</strong></div>
      <div><span>Маршрут</span><strong>${escapePrintHtml(input.routeLabel)}</strong></div>
      <div><span>Сдать до</span><strong>${escapePrintHtml(input.deadlineLabel)}</strong></div>
    </div>
    <table>
      <thead><tr><th class="number">№</th><th class="image">Фото</th><th>Товар и идентификаторы</th><th>Ячейка</th><th>Заказы WB</th><th class="quantity">Взять</th><th class="quantity">Подобрано</th><th>Маркировка</th></tr></thead>
      <tbody>${rows || '<tr><td colspan="8">В поставке нет товаров для подбора.</td></tr>'}</tbody>
    </table>
    <div class="footer">Сформировано WMS: ${escapePrintHtml(input.printedAtLabel)} · Актуальное серверное состояние на момент печати.</div>
    <script>
      const images = Array.from(document.images);
      const ready = images.map((image) => image.complete ? Promise.resolve() : new Promise((resolve) => {
        image.addEventListener('load', resolve, { once: true });
        image.addEventListener('error', resolve, { once: true });
      }));
      Promise.all(ready).then(() => { window.focus(); window.print(); });
    </script>
  </body>
</html>`
}
