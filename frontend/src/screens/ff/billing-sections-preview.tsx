import { StrictMode, useState } from 'react'
import { createRoot } from 'react-dom/client'
import { MemoryRouter } from 'react-router-dom'
import { Box, CssBaseline, ThemeProvider, Typography } from '@mui/material'

import { muiTheme } from '../../mui/theme'
import { FfBillingSellerDetails } from './FfBillingSellerDetails'
import type { SellerReportDetails, SellerReportEntry } from './FfBillingSellerDetails'
import '../../index.css'

// Превью раскрывашки селлера на выдуманных данных: сервер и вход не нужны.
// Экран расчётов целиком без токена не открыть, а смотреть на разделы глазами
// надо — иначе правка вёрстки проверяется только на стенде после выкатки.

function entry(
  id: string,
  serviceCode: string,
  documentNumber: string,
  quantity: number,
  rate: number,
  day: number,
): SellerReportEntry {
  return {
    id,
    kind: 'operation_fact',
    occurred_at: `2026-08-${String(day).padStart(2, '0')}T09:30:00Z`,
    service_code: serviceCode,
    item_quantity: quantity,
    source_type: serviceCode === 'inbound' ? 'inbound_intake' : 'marketplace_unload',
    source_id: id,
    source_target: { kind: 'route', to: '#' },
    document_number: documentNumber,
    product_name: null,
    sku: null,
    result: 'completed',
    unit: 'item',
    rate_kopecks: rate,
    amount_kopecks: rate * quantity,
    billing_ledger_entry_id: `ledger-${id}`,
    invoice_history: { state: 'known', count: id.endsWith('1') ? 1 : 0 },
  }
}

const details: SellerReportDetails = {
  seller_id: 'seller-1',
  seller_name: 'Ромашка',
  entries: [
    entry('in-1', 'inbound', 'Приёмка № 000045', 120, 300, 12),
    entry('in-2', 'inbound', 'Приёмка № 000046', 80, 300, 14),
    entry('out-1', 'marketplace_outbound', 'Отгрузка № 000012', 200, 300, 18),
    entry('pack-1', 'packing', 'Упаковка № 000031', 200, 500, 18),
    entry('pack-2', 'packing', 'Упаковка № 000032', 45, 700, 19),
  ],
  storage_row: {
    kind: 'storage',
    date_from: '2026-08-01',
    date_to: '2026-08-31',
    liter_days: 1240,
    status: 'calculated',
    amount_kopecks: 62000,
    calculation_token: 'token',
  },
  next_cursor: null,
}

export function BillingSectionsPreview() {
  const [picked, setPicked] = useState<string[]>([])
  const [storagePicked, setStoragePicked] = useState(false)
  return (
    <ThemeProvider theme={muiTheme}>
      <CssBaseline />
      <MemoryRouter>
        <Box sx={{ p: 3 }}>
          <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mb: 2 }}>
            Превью раскрывашки селлера на выдуманных данных. В портале она живёт под строкой
            селлера в таблице «Расчёты». Выбрано начислений: {picked.length}
            {storagePicked ? ' + хранение' : ''}.
          </Typography>
          <FfBillingSellerDetails
            details={details}
            loading={false}
            error={false}
            includeFinance
            selectedRootIds={picked}
            onToggleRoot={(id, checked) =>
              setPicked((ids) => (checked ? [...new Set([...ids, id])] : ids.filter((x) => x !== id)))
            }
            storageSelected={storagePicked}
            onToggleStorage={setStoragePicked}
            onLoadMore={() => undefined}
            onOpenInbound={() => undefined}
          />
        </Box>
      </MemoryRouter>
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
      <BillingSectionsPreview />
    </StrictMode>,
  )
}
