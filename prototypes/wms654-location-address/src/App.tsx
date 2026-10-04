import { Box } from '@mui/material'
import { useState, type MouseEvent } from 'react'
import { FfWarehouseMapScreen } from '../../../frontend/src/screens/ff/warehouse-map/FfWarehouseMapScreen'
import { stubData } from '../../../frontend/src/screens/ff/warehouse-map/stub'
import { Wms654CreateCellDialog } from './Wms654CreateCellDialog'

export default function App() {
  const [warehouseId, setWarehouseId] = useState('wh-yartsevo')
  const [dialogOpen, setDialogOpen] = useState(false)
  const data = stubData(warehouseId)

  function openPrototypeDialog(event: MouseEvent<HTMLDivElement>) {
    const target = event.target as HTMLElement
    if (!target.closest('[data-testid="warehouse-map-create-cell"]')) return
    event.preventDefault()
    event.stopPropagation()
    setDialogOpen(true)
  }

  return (
    <Box sx={{ minHeight: '100vh', bgcolor: 'background.default' }}>
      <Box sx={{ display: 'flex', minHeight: '100vh' }}>
        <Box
          aria-hidden
          sx={{
            width: 260,
            flexShrink: 0,
            borderRight: '1px solid',
            borderColor: 'divider',
            bgcolor: 'background.paper',
          }}
        />
        <Box sx={{ flexGrow: 1, minWidth: 0, p: 3 }} onClickCapture={openPrototypeDialog}>
          <FfWarehouseMapScreen
            data={data}
            loading={false}
            error={null}
            warehouseId={warehouseId}
            onWarehouseChange={setWarehouseId}
            onMove={() => undefined}
            onCreateCell={() => undefined}
            onCreateWarehouse={() => undefined}
            onPrinter={() => undefined}
            onPrintCell={() => undefined}
            onInventory={() => undefined}
            historyFor={(row) => data.journal.filter((entry) => entry.subject === row.title)}
          />
        </Box>
      </Box>

      <Wms654CreateCellDialog
        open={dialogOpen}
        warehouseName={data.warehouses.find((warehouse) => warehouse.id === warehouseId)?.name ?? ''}
        onClose={() => setDialogOpen(false)}
      />
    </Box>
  )
}
