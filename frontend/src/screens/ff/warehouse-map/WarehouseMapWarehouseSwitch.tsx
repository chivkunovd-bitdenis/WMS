import { ToggleButton, ToggleButtonGroup } from '@mui/material'
import type { WarehouseOption } from './WarehouseMapTypes'

// Переключатель складов «Карты склада», вынесенный из `WarehouseMapToolbar.tsx`
// (WMS-490 D5), чтобы вкладка «Расположение» карточки товара показывала тот же
// переключатель, только со складами, где лежит этот товар (R10) — без
// перерисовки и без изменения вида самого компонента.

export function WarehouseMapWarehouseSwitch({
  warehouses,
  warehouseId,
  onWarehouseChange,
}: {
  warehouses: WarehouseOption[]
  warehouseId: string | null
  onWarehouseChange: (id: string) => void
}) {
  return (
    <ToggleButtonGroup
      exclusive
      size="small"
      value={warehouseId}
      onChange={(_event, value: string | null) => {
        if (value) onWarehouseChange(value)
      }}
      aria-label="Склад"
      data-testid="warehouse-map-warehouses"
      sx={{ flexWrap: 'wrap' }}
    >
      {warehouses.map((warehouse) => (
        <ToggleButton
          key={warehouse.id}
          value={warehouse.id}
          data-testid={`warehouse-map-warehouse-${warehouse.id}`}
          sx={{ textTransform: 'none', fontWeight: 600, px: 1.75 }}
        >
          {warehouse.name}
        </ToggleButton>
      ))}
    </ToggleButtonGroup>
  )
}
