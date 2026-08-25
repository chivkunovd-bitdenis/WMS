import { Chip } from '@mui/material'

export type MarketplaceKind = 'wb' | 'ozon'

const MARKETPLACE_PALETTE: Record<MarketplaceKind, string> = {
  ozon: '#005BFF',
  wb: '#B01887',
}

export function MarketplaceChip({
  marketplace,
  testId,
}: {
  marketplace: MarketplaceKind
  testId?: string
}) {
  const color = MARKETPLACE_PALETTE[marketplace]
  return (
    <Chip
      size="small"
      variant="outlined"
      label={marketplace === 'ozon' ? 'Ozon' : 'Wildberries'}
      data-testid={testId}
      sx={{
        flexShrink: 0,
        color,
        borderColor: color,
        backgroundColor: 'transparent',
        pointerEvents: 'none',
      }}
    />
  )
}
