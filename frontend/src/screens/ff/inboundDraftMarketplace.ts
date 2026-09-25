export function inboundMarketplaceLabel(row: { marketplaces?: string[] } | undefined): string {
  const labels = (row?.marketplaces ?? []).map((marketplace) => marketplace === 'ozon' ? 'Ozon' : marketplace === 'wb' ? 'WB' : marketplace).filter(Boolean)
  return labels.length ? labels.join(' / ') : '—'
}
