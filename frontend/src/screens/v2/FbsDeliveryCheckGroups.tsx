import { useState } from 'react'
import { Box, Collapse, List, ListItemButton, ListItemText, Stack, Typography } from '@mui/material'
import ExpandMoreIcon from '@mui/icons-material/ExpandMore'
import { ordersWord, type FbsDeliveryCheckGroup } from './fbsUx'

export function DeliveryCheckGroupList({ groups, orderLabel }: {
  groups: FbsDeliveryCheckGroup[]
  /** Подпись строки заказа; без неё — «Заказ WB №…». Ozon передаёт номер отправления. */
  orderLabel?: (orderId: number) => string
}) {
  const [expandedKeys, setExpandedKeys] = useState<Set<string>>(() => new Set())

  return (
    <List disablePadding sx={{ mt: 0.5 }}>
      {groups.map((group) => {
        const expanded = expandedKeys.has(group.key)
        const hasOrders = group.orderIds.length > 0
        return (
          <Box
            component="li"
            key={group.key}
            sx={{ listStyle: 'none', borderTop: 1, borderColor: 'divider' }}
          >
            <ListItemButton
              disabled={!hasOrders}
              onClick={() => {
                setExpandedKeys((current) => {
                  const next = new Set(current)
                  if (expanded) next.delete(group.key)
                  else next.add(group.key)
                  return next
                })
              }}
              sx={{ px: 0, py: 0.75, '&.Mui-disabled': { opacity: 1 } }}
              data-testid={`fbs-delivery-check-${group.key}`}
            >
              <ListItemText
                primary={group.title}
                secondary={group.description}
                slotProps={{
                  primary: { variant: 'body2', sx: { fontWeight: 600 } },
                  secondary: { variant: 'caption' },
                }}
                sx={{ my: 0 }}
              />
              {hasOrders ? (
                <Stack direction="row" spacing={0.5} sx={{ ml: 1, alignItems: 'center' }}>
                  <Typography variant="caption" color="text.secondary" sx={{ whiteSpace: 'nowrap' }}>
                    {group.orderIds.length} {ordersWord(group.orderIds.length)}
                  </Typography>
                  <ExpandMoreIcon
                    fontSize="small"
                    sx={{ transform: expanded ? 'rotate(180deg)' : 'none', transition: 'transform 150ms' }}
                  />
                </Stack>
              ) : null}
            </ListItemButton>
            <Collapse in={expanded} unmountOnExit>
              <Stack
                spacing={0}
                sx={{
                  maxHeight: 220,
                  overflowY: 'auto',
                  mb: 0.75,
                  pl: 1.5,
                  pr: 0.5,
                  '& > :not(:last-child)': { borderBottom: 1, borderColor: 'divider' },
                }}
                data-testid={`fbs-delivery-check-orders-${group.key}`}
              >
                {group.orderIds.map((orderId) => (
                  <Box key={orderId} sx={{ py: 0.35, overflowWrap: 'anywhere' }}>
                    <Typography variant="body2">{orderLabel ? orderLabel(orderId) : `Заказ WB №${orderId}`}</Typography>
                    {group.orderDetails?.[orderId]?.map((detail) => (
                      <Typography key={detail} variant="body2" color="text.secondary">{detail}</Typography>
                    ))}
                  </Box>
                ))}
              </Stack>
            </Collapse>
          </Box>
        )
      })}
    </List>
  )
}

