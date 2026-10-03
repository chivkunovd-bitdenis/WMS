import { useState } from 'react'
import { Box, Collapse, ListItemButton, ListItemText, Stack, Typography } from '@mui/material'
import ExpandMoreIcon from '@mui/icons-material/ExpandMore'
import type { FbsDeliveryPreflight } from './fbsApi'
import { ordersWord } from './fbsUx'

export function FbsCancelledDeliveryOrders({ orders }: {
  orders: NonNullable<FbsDeliveryPreflight['cancelled_orders']>
}) {
  const [expanded, setExpanded] = useState(false)
  return (
    <Box>
      <ListItemButton
        onClick={() => setExpanded((current) => !current)}
        aria-expanded={expanded}
        aria-controls="fbs-cancelled-delivery-orders"
        sx={{ px: 0, py: 0.75 }}
        data-testid="fbs-cancelled-delivery-toggle"
      >
        <ListItemText
          primary="Отменённые заказы"
          secondary="Выньте эти товары из коробов перед передачей. Они будут исключены из поставки."
          slotProps={{ primary: { variant: 'subtitle2' }, secondary: { variant: 'body2' } }}
        />
        <Typography variant="caption" sx={{ ml: 1, whiteSpace: 'nowrap' }}>
          {orders.length} {ordersWord(orders.length)}
        </Typography>
        <ExpandMoreIcon fontSize="small" sx={{ transform: expanded ? 'rotate(180deg)' : 'none' }} />
      </ListItemButton>
      <Collapse in={expanded} unmountOnExit>
        <Stack
          id="fbs-cancelled-delivery-orders"
          sx={{ maxHeight: 220, overflowY: 'auto', '& > :not(:last-child)': { borderBottom: 1, borderColor: 'divider' } }}
        >
          {orders.map((order) => (
            <Typography key={order.order_id} variant="body2" sx={{ py: 0.5, overflowWrap: 'anywhere' }}>
              WB {order.wb_order_id} · {order.article ?? 'Артикул не указан'}
              {order.product_name ? ` · ${order.product_name}` : ''}
              {' · '}{order.boxes.length > 0
                ? order.boxes.map((box) => `Короб ${box.box_number} (${box.box_barcode})`).join(', ')
                : 'Короб не назначен'}
            </Typography>
          ))}
        </Stack>
      </Collapse>
    </Box>
  )
}
