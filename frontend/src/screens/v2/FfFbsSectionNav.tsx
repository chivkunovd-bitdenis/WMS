import { Tab, Tabs } from '@mui/material'
import { useLocation, useNavigate } from 'react-router-dom'

/** Поднавигация модуля FBS: заказы и остатки WB. */
export function FfFbsSectionNav() {
  const loc = useLocation()
  const nav = useNavigate()
  const value = loc.pathname.includes('/stock-sync') ? 'stock-sync' : 'orders'

  return (
    <Tabs
      value={value}
      onChange={(_, v) => {
        nav(v === 'orders' ? '/app/ff/fbs' : '/app/ff/fbs/stock-sync')
      }}
      sx={{ mb: 2, borderBottom: 1, borderColor: 'divider' }}
      data-testid="fbs-section-nav"
    >
      <Tab value="orders" label="Заказы" data-testid="fbs-nav-orders" />
      <Tab value="stock-sync" label="Остатки WB" data-testid="fbs-nav-stock-sync" />
    </Tabs>
  )
}
