export type FbsMarketplace = 'wb' | 'ozon'

export function buildFbsSyncTargets(
  sellerIds: string[],
  selectedSellerId: string,
): Array<{ sellerId: string; marketplace: FbsMarketplace }> {
  const targets = selectedSellerId === '__all__' ? sellerIds : [selectedSellerId]
  return targets.flatMap((sellerId) => ([
    { sellerId, marketplace: 'wb' as const },
    { sellerId, marketplace: 'ozon' as const },
  ]))
}

export function mixedMarketplaceSelectionMessage(marketplaces: FbsMarketplace[]): string | null {
  return new Set(marketplaces).size > 1
    ? 'Нельзя объединить заказы Wildberries и Ozon в одну поставку.'
    : null
}

export function fbsBoxOperationsDisabled(marketplace: FbsMarketplace): boolean {
  return marketplace === 'ozon'
}

export function orderStatusForChip(order: {
  marketplace: FbsMarketplace
  status: string
  wb_status: string | null
}): string {
  return order.marketplace === 'ozon' && order.status === 'external_processing'
    ? order.wb_status || order.status
    : order.status
}

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

export type FbsPickingListPrintRow = {
  name: string
  size: string | null
  imageUrl: string | null
  identifiers: string[]
  locations: string[]
  required: number
  picked: number
  wbOrders: number[]
  stickerCodes: Array<string | null>
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

function renderStickerCode(value: string | null) {
  if (!value) return '—'
  const compact = value.replace(/\s+/g, '')
  if (compact.length <= 4) return `<strong>${escapePrintHtml(compact)}</strong>`
  const prefix = compact.slice(0, -4)
  const suffix = compact.slice(-4)
  return `${escapePrintHtml(prefix)} <strong>${escapePrintHtml(suffix)}</strong>`
}

export function buildFbsPickingListPrintHtml(input: FbsPickingListPrintInput) {
  let position = 1
  const rows = input.rows.map((row) => {
    const positionFrom = position
    const positionTo = positionFrom + row.required - 1
    position = positionTo + 1
    const positionLabel = positionFrom === positionTo ? `${positionFrom}` : `${positionFrom}–${positionTo}`
    const imageUrl = printableImageUrl(row.imageUrl)
    const nonEmptyStickerCodes = row.stickerCodes.filter((code): code is string => Boolean(code))
    const stickerCodes = nonEmptyStickerCodes.length
      ? nonEmptyStickerCodes.map(renderStickerCode).join('<br />')
      : '—'
    return `
      <tr>
        <td class="number">${positionLabel}</td>
        <td class="image">${imageUrl ? `<img src="${imageUrl}" alt="" />` : '<span>—</span>'}</td>
        <td>
          <strong>${escapePrintHtml(row.name)}</strong>
          <div class="muted">${row.identifiers.length ? row.identifiers.map(escapePrintHtml).join(' · ') : 'Идентификаторы не указаны'}</div>
        </td>
        <td class="size">${row.size ? escapePrintHtml(row.size) : '—'}</td>
        <td>${row.locations.length ? row.locations.map(escapePrintHtml).join('<br />') : 'Ячейка не назначена'}</td>
        <td>${row.wbOrders.map((id) => `№${escapePrintHtml(id)}`).join('<br />')}</td>
        <td class="sticker">${stickerCodes}</td>
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
      .size { width: 78px; text-align: center; white-space: nowrap; }
      td.size { font-size: 20px; font-weight: 700; }
      .quantity { width: 62px; text-align: center; font-weight: 700; }
      .sticker { width: 96px; font-size: 14px; white-space: nowrap; }
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
      <thead><tr><th class="number">№</th><th class="image">Фото</th><th>Товар и идентификаторы</th><th class="size">Размер</th><th>Ячейка</th><th>Заказы WB</th><th class="sticker">Стикер</th><th class="quantity">Взять</th><th class="quantity">Подобрано</th><th>Маркировка</th></tr></thead>
      <tbody>${rows || '<tr><td colspan="10">В поставке нет товаров для подбора.</td></tr>'}</tbody>
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
