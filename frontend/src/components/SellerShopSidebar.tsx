import {
  Box,
  Checkbox,
  Divider,
  FormControlLabel,
  List,
  ListItemButton,
  ListItemText,
  Typography,
} from '@mui/material'

export type SellerShopRow = {
  id: string
  name: string
  enabled?: boolean
  is_home?: boolean
}

type Props = {
  canManage: boolean
  homeSellerId: string | null
  activeSellerId: string | null
  delegatableShops: SellerShopRow[]
  switchableShops: SellerShopRow[]
  busy?: boolean
  allowAllShops?: boolean
  onToggleShop: (sellerId: string, enabled: boolean) => void
  onSwitchShop: (sellerId: string | null) => void
}

export function SellerShopSidebar({
  canManage,
  homeSellerId,
  activeSellerId,
  delegatableShops,
  switchableShops,
  busy = false,
  allowAllShops = false,
  onToggleShop,
  onSwitchShop,
}: Props) {
  if (!canManage && switchableShops.length <= 1) {
    return null
  }

  const showSwitcher = allowAllShops || switchableShops.length > 1

  return (
    <Box sx={{ mt: 2 }} data-testid="seller-shops-panel">
      {canManage ? (
        <>
          <Typography
            variant="caption"
            sx={{
              px: 2,
              py: 0.5,
              display: 'block',
              color: 'text.secondary',
              textTransform: 'uppercase',
              letterSpacing: '0.04em',
            }}
          >
            Магазины
          </Typography>
          <List dense disablePadding data-testid="seller-shops-checklist">
            {delegatableShops.length === 0 ? (
              <Typography variant="body2" sx={{ px: 2, py: 1, color: 'text.secondary' }}>
                Нет других магазинов
              </Typography>
            ) : (
              delegatableShops.map((shop) => (
                <FormControlLabel
                  key={shop.id}
                  sx={{ mx: 1, display: 'flex', alignItems: 'flex-start' }}
                  control={
                    <Checkbox
                      size="small"
                      checked={Boolean(shop.enabled)}
                      disabled={busy}
                      data-testid={`seller-shop-check-${shop.id}`}
                      onChange={(e) => onToggleShop(shop.id, e.target.checked)}
                    />
                  }
                  label={
                    <Typography variant="body2" sx={{ pt: 0.75 }}>
                      {shop.name}
                    </Typography>
                  }
                />
              ))
            )}
          </List>
          {showSwitcher ? <Divider sx={{ my: 1 }} /> : null}
        </>
      ) : null}

      {showSwitcher ? (
        <>
          <Typography
            variant="caption"
            sx={{
              px: 2,
              py: 0.5,
              display: 'block',
              color: 'text.secondary',
              textTransform: 'uppercase',
              letterSpacing: '0.04em',
            }}
          >
            Активный магазин
          </Typography>
          <List dense disablePadding data-testid="seller-shop-switcher">
            {allowAllShops ? (
              <ListItemButton
                selected={activeSellerId == null}
                disabled={busy}
                data-testid="seller-shop-switch-all"
                onClick={() => onSwitchShop(null)}
              >
                <ListItemText primary="Все магазины" />
              </ListItemButton>
            ) : null}
            {switchableShops.map((shop) => {
              const selected =
                activeSellerId === shop.id ||
                (activeSellerId == null && shop.id === homeSellerId)
              return (
                <ListItemButton
                  key={shop.id}
                  selected={selected}
                  disabled={busy}
                  data-testid={`seller-shop-switch-${shop.id}`}
                  onClick={() =>
                    onSwitchShop(shop.is_home ? null : shop.id)
                  }
                >
                  <ListItemText
                    primary={shop.name}
                    secondary={shop.is_home ? 'Мой' : undefined}
                  />
                </ListItemButton>
              )
            })}
          </List>
        </>
      ) : null}
    </Box>
  )
}
