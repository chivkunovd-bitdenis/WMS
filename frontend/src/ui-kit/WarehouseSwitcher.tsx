import { useState } from 'react'
import { Button, Menu, MenuItem, CircularProgress, Box } from '@mui/material'
import ExpandMoreIcon from '@mui/icons-material/ExpandMore'
import { realWarehouses } from '../utils/fbsWarehouse'

export interface WarehouseSwitcherProps {
  currentWarehouseId: string | null
  currentWarehouseName: string | null
  warehouses: Array<{ id: string; name: string; code: string; is_auto_fbs?: boolean }>
  onSelectWarehouse: (warehouseId: string) => void
  isLoading?: boolean
}

export function WarehouseSwitcher({
  currentWarehouseId,
  currentWarehouseName,
  warehouses,
  onSelectWarehouse,
  isLoading = false,
}: WarehouseSwitcherProps) {
  const [anchorEl, setAnchorEl] = useState<null | HTMLElement>(null)

  // Показываем компонент только если есть больше одного настоящего склада
  const realWareHouses = realWarehouses(warehouses)
  if (realWareHouses.length <= 1) {
    return null
  }

  const handleOpen = (event: React.MouseEvent<HTMLElement>) => {
    setAnchorEl(event.currentTarget)
  }

  const handleClose = () => {
    setAnchorEl(null)
  }

  const handleSelectWarehouse = (warehouseId: string) => {
    onSelectWarehouse(warehouseId)
    handleClose()
  }

  return (
    <Box data-testid="warehouse-switcher">
      <Button
        onClick={handleOpen}
        variant="text"
        endIcon={isLoading ? <CircularProgress size={20} /> : <ExpandMoreIcon />}
        data-testid="warehouse-switcher-button"
        disabled={isLoading}
        sx={{ textTransform: 'none', fontWeight: 500 }}
      >
        {currentWarehouseName || 'Выбрать склад'}
      </Button>

      <Menu
        anchorEl={anchorEl}
        open={Boolean(anchorEl)}
        onClose={handleClose}
        data-testid="warehouse-switcher-menu"
      >
        {realWareHouses.map((warehouse) => (
          <MenuItem
            key={warehouse.id}
            onClick={() => handleSelectWarehouse(warehouse.id)}
            selected={warehouse.id === currentWarehouseId}
            data-testid={`warehouse-option-${warehouse.id}`}
          >
            {warehouse.name}
          </MenuItem>
        ))}
      </Menu>
    </Box>
  )
}
