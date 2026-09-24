import { Box, Chip } from '@mui/material'

export type MarketplaceKind = 'wb' | 'ozon'

/** Brand colors shared by marketplace chips and compact headers. */
export const MARKETPLACE_PALETTE: Record<MarketplaceKind, string> = {
  ozon: '#005BFF',
  wb: '#B01887',
}

export const MARKETPLACE_LABELS: Record<MarketplaceKind, string> = {
  ozon: 'Ozon',
  wb: 'Wildberries',
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
      label={MARKETPLACE_LABELS[marketplace]}
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

/** Compact non-interactive marketplace mark for a block heading. */
export function MarketplaceIcon({
  marketplace,
  testId,
}: {
  marketplace: MarketplaceKind
  testId?: string
}) {
  return (
    <Box
      component="span"
      role="img"
      aria-label={MARKETPLACE_LABELS[marketplace]}
      data-testid={testId}
      sx={{
        width: 22,
        height: 22,
        borderRadius: '6px',
        flex: 'none',
        display: 'inline-grid',
        placeItems: 'center',
        color: 'common.white',
        fontSize: 10,
        fontWeight: 800,
        letterSpacing: '-0.02em',
        lineHeight: 1,
        backgroundColor: MARKETPLACE_PALETTE[marketplace],
      }}
    >
      {marketplace === 'ozon' ? 'OZ' : 'WB'}
    </Box>
  )
}
