import { Tab, Tabs } from '@mui/material'
import { useNavigate } from 'react-router-dom'

/** Поднавигация модуля FBS. Настройка остатков теперь живёт в каталоге. */
export function FfFbsSectionNav() {
  const nav = useNavigate()

  return (
    <Tabs
      value="orders"
      onChange={() => nav('/app/ff/fbs')}
      sx={{ mb: 2, borderBottom: 1, borderColor: 'divider' }}
      data-testid="fbs-section-nav"
    >
      <Tab value="orders" label="Заказы" data-testid="fbs-nav-orders" />
    </Tabs>
  )
}
