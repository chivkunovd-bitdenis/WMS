// Read-only browser DOM contract. Run on the visible mixed packing view in CUA.
// A jsdom or hidden view is explicitly invalid evidence.
function wms666MixedPackingGeometryContract() {
  const host = document.querySelector('[data-testid="fbs-unified-packing-rows"]')
  if (!host) throw new Error('Open the unified mixed packing view first')
  const rows = [...host.querySelectorAll('[data-order-id]')]
    .filter(row => row.getBoundingClientRect().width > 0)
  if (!rows.some(row => row.querySelector('[data-task-id="FBS-09"]'))
      || !rows.some(row => !row.querySelector('[data-task-id="FBS-09"]'))) {
    throw new Error('The fixture must show both WB and Ozon packing rows')
  }
  const measurements = rows.map(row => {
    const size = row.querySelector('[data-testid="fbs-packing-size"]')
    const sticker = row.querySelector('[data-testid="fbs-sticker-code"]')?.parentElement
    const marking = [...row.querySelectorAll('*')]
      .find(node => node.children.length === 0 && node.textContent?.trim() === 'ЧЗ')?.parentElement
    if (!size || !sticker || !marking) throw new Error('Visible row lacks a required column')
    return { order: row.getAttribute('data-order-id'),
      marketplace: row.querySelector('[data-task-id="FBS-09"]') ? 'wb' : 'ozon',
      size: size.getBoundingClientRect().right,
      sticker: sticker.getBoundingClientRect().right,
      marking: marking.getBoundingClientRect().right }
  })
  const deltas = Object.fromEntries(['size', 'sticker', 'marking'].map(column => [column,
    Math.max(...measurements.map(row => row[column])) - Math.min(...measurements.map(row => row[column]))]))
  return { passed: Object.values(deltas).every(delta => delta <= 1), tolerancePx: 1,
    viewport: { width: innerWidth, height: innerHeight }, deltas, measurements }
}
