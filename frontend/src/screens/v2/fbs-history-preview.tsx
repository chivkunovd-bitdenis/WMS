import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { Box, CssBaseline, ThemeProvider, Typography } from '@mui/material'

import { muiTheme } from '../../mui/theme'
import { FbsOrderHistoryTimeline, type FbsOrderHistory } from './FbsOrderHistoryDialog'
import '../../index.css'

// Превью истории заказа на выдуманных событиях: сервер и вход не нужны.

const HISTORY: FbsOrderHistory = {
  order_id: 'preview',
  wb_order_id: 271834606,
  status: 'sorted',
  wb_status: 'sorted',
  supply_id: 'supply',
  events: [
    { at: '2026-08-21T06:12:00Z', kind: 'created', title: 'Заказ появился в системе', actor: null, details: null },
    { at: '2026-08-21T07:41:00Z', kind: 'pick', title: 'Товар подобран', actor: 'kladovshik@example.com', details: 'из тары (короб), штрихкод 2000000000011' },
    { at: '2026-08-21T08:03:00Z', kind: 'marking', title: 'Внесён код: Честный знак', actor: null, details: '0104630123456789215fS8k… · статус applied' },
    { at: '2026-08-21T08:05:00Z', kind: 'print_requested', title: 'Стикер заказа: запрошен', actor: null, details: null },
    { at: '2026-08-21T08:05:30Z', kind: 'print_ready', title: 'Стикер заказа: получен от WB', actor: null, details: null },
    { at: '2026-08-21T08:11:00Z', kind: 'packed', title: 'Заказ упакован', actor: 'upakovshik@example.com', details: null },
    { at: '2026-08-21T09:30:00Z', kind: 'supply', title: 'Поставка: status_changed', actor: 'staging-admin@example.com', details: 'status_before: assembling, status_after: delivered' },
    { at: '2026-08-22T04:10:00Z', kind: 'supply', title: 'Поставка: line_added', actor: null, details: 'qty_before: 0, qty_after: 1' },
  ],
}

export function FbsHistoryPreview() {
  return (
    <ThemeProvider theme={muiTheme}>
      <CssBaseline />
      <Box sx={{ p: 3, maxWidth: 900 }}>
        <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mb: 2 }}>
          Превью истории заказа FBS на выдуманных событиях. В портале она открывается окном по заказу.
        </Typography>
        <FbsOrderHistoryTimeline history={HISTORY} />
      </Box>
    </ThemeProvider>
  )
}

type RootHost = HTMLElement & { __previewRoot?: ReturnType<typeof createRoot> }

const container = document.getElementById('root') as RootHost | null
if (container) {
  const root = container.__previewRoot ?? createRoot(container)
  container.__previewRoot = root
  root.render(
    <StrictMode>
      <FbsHistoryPreview />
    </StrictMode>,
  )
}
