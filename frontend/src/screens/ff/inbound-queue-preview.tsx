import { StrictMode, useState } from 'react'
import { createRoot } from 'react-dom/client'
import { MemoryRouter } from 'react-router-dom'
import {
  AppBar as MuiAppBar,
  Box as MuiBox,
  CssBaseline,
  Dialog,
  IconButton,
  ThemeProvider,
  Toolbar as MuiToolbar,
  Typography as MuiTypography,
} from '@mui/material'
import CloseIcon from '@mui/icons-material/Close'

import { muiTheme } from '../../mui/theme'
import { AuthedAppLayout } from '../../layouts/AuthedAppLayout'
import { FfInboundQueuePage } from './FfInboundQueuePage'
import { FfInboundRequestView } from './FfInboundRequestView'
import type { InboundQueueRow } from '../../utils/inboundQueues'
import '../../index.css'

// Макет экрана «Приёмка». Очередь заявок (FfInboundQueuePage) — обычный
// компонент на пропсах, как в боевом приложении: строки приходят готовым
// массивом, сервер тут ни при чём. А вот открытая заявка (FfInboundRequestView)
// сама стучится на сервер по своему requestId, поэтому под неё, как и для
// «Заказы FBS» и «Упаковка», подменяем `fetch`. Диалог — точная копия того,
// как карточка приёмки открывается в App.tsx (полноэкранная модалка с крестиком).

const SELLERS = [
  { id: 's-zhou', name: 'ИП Чжоу' },
  { id: 's-gor', name: 'ИП Горячкина' },
  { id: 's-city', name: 'ООО Ситипак' },
  { id: 's-larin', name: 'ИП Ларин' },
]

const QUEUE_ROWS: InboundQueueRow[] = [
  {
    id: 'inb-1', status: 'draft', operation_type: 'inbound', line_count: 2,
    planned_delivery_date: '2026-09-04', created_by_seller_id: 'seller-user-4', seller_name: 'ИП Ларин', seller_id: 's-larin',
    document_number: 'Приёмка № 000214', display_number: '№000214',
    product_names: ['Термокружка 450 мл', 'Ремень кожаный'], goods_qty_total: 80,
    planned_box_count: null, actual_box_count: null, boxes_discrepancy: false, has_discrepancy: false,
    created_at: '2026-09-02T06:40:00Z',
  },
  {
    id: 'inb-2', status: 'submitted', operation_type: 'inbound', line_count: 3,
    planned_delivery_date: '2026-09-03', created_by_seller_id: 'seller-user-3', seller_name: 'ООО Ситипак', seller_id: 's-city',
    document_number: 'Приёмка № 000213', display_number: '№000213',
    product_names: ['Кроссовки беговые', 'Носки спортивные, 3 пары'], goods_qty_total: 240,
    planned_box_count: 4, actual_box_count: null, boxes_discrepancy: false, has_discrepancy: false,
    created_at: '2026-09-01T14:20:00Z',
  },
  {
    id: 'inb-3', status: 'receiving', operation_type: 'inbound', line_count: 2,
    planned_delivery_date: '2026-09-02', created_by_seller_id: 'seller-user-2', seller_name: 'ИП Горячкина', seller_id: 's-gor',
    document_number: 'Приёмка № 000212', display_number: '№000212',
    product_names: ['Футболка хлопок белая', 'Худи оверсайз серое'], goods_qty_total: 160,
    planned_box_count: 3, actual_box_count: 2, boxes_discrepancy: true, has_discrepancy: true,
    created_at: '2026-09-02T07:00:00Z',
  },
  {
    id: 'inb-4', status: 'done', operation_type: 'inbound', line_count: 1,
    planned_delivery_date: '2026-08-29', created_by_seller_id: 'seller-user-1', seller_name: 'ИП Чжоу', seller_id: 's-zhou',
    document_number: 'Приёмка № 000208', display_number: '№000208',
    product_names: ['Футболка хлопок белая'], goods_qty_total: 300,
    planned_box_count: 5, actual_box_count: 5, boxes_discrepancy: false, has_discrepancy: false,
    created_at: '2026-08-29T09:00:00Z',
  },
]

type InboundDetailStub = {
  id: string
  document_number: string
  display_number: string
  warehouse_id: string
  status: string
  operation_type: 'inbound' | 'return'
  marketplace: null
  planned_delivery_date: string
  planned_box_count: number
  actual_box_count: number
  boxes_discrepancy: boolean
  has_discrepancy: boolean
  seller_id: string
  seller_name: string
  created_by_seller_id: string
  created_at: string
  distribution_completed_at: null
  boxes: Array<{
    id: string; box_number: number; internal_barcode: string
    label_printed_at: string | null; intake_opened_at: string | null; intake_closed_at: string | null
    is_open: boolean
    lines: Array<{ id: string; product_id: string; sku_code: string; product_name: string; quantity: number }>
  }>
  cargo_places: []
  lines: Array<{
    id: string; product_id: string; sku_code: string; product_name: string; wb_barcode: string | null
    requires_honest_sign: boolean; length_mm: null; width_mm: null; height_mm: null; weight_g: null; volume_liters: null
    added_by_fulfillment: boolean; expected_qty: number; actual_qty: number | null; posted_qty: number
    storage_location_id: string | null; storage_location_code: string | null
  }>
}

const DETAIL: InboundDetailStub = {
  id: 'inb-3', document_number: 'Приёмка № 000212', display_number: '№000212',
  warehouse_id: 'w-yartsevo', status: 'receiving', operation_type: 'inbound', marketplace: null,
  planned_delivery_date: '2026-09-02', planned_box_count: 3, actual_box_count: 2,
  boxes_discrepancy: true, has_discrepancy: true,
  seller_id: 's-gor', seller_name: 'ИП Горячкина', created_by_seller_id: 'seller-user-2',
  created_at: '2026-09-02T07:00:00Z', distribution_completed_at: null,
  boxes: [
    {
      id: 'box-1', box_number: 1, internal_barcode: 'WHB-000212-01',
      label_printed_at: '2026-09-02T07:05:00Z', intake_opened_at: '2026-09-02T07:10:00Z', intake_closed_at: '2026-09-02T07:40:00Z',
      is_open: false,
      lines: [{ id: 'bl-1', product_id: 'p-ts-wht-m', sku_code: 'TS-WHT-M', product_name: 'Футболка хлопок белая', quantity: 100 }],
    },
    {
      id: 'box-2', box_number: 2, internal_barcode: 'WHB-000212-02',
      label_printed_at: '2026-09-02T07:41:00Z', intake_opened_at: '2026-09-02T07:42:00Z', intake_closed_at: null,
      is_open: true,
      lines: [{ id: 'bl-2', product_id: 'p-hd-gry-l', sku_code: 'HD-GRY-L', product_name: 'Худи оверсайз серое', quantity: 40 }],
    },
  ],
  cargo_places: [],
  lines: [
    {
      // Вся принятая партия ушла в короба — свободного (не в коробе) остатка нет,
      // поэтому actual_qty = 0, а фактическое количество даёт только короб-1 (100 шт).
      // При плане 120 это честная недостача 20 шт.
      id: 'line-1', product_id: 'p-ts-wht-m', sku_code: 'TS-WHT-M', product_name: 'Футболка хлопок белая',
      wb_barcode: '4680123456789', requires_honest_sign: true,
      length_mm: null, width_mm: null, height_mm: null, weight_g: null, volume_liters: null,
      added_by_fulfillment: false, expected_qty: 120, actual_qty: 0, posted_qty: 0,
      storage_location_id: null, storage_location_code: null,
    },
    {
      id: 'line-2', product_id: 'p-hd-gry-l', sku_code: 'HD-GRY-L', product_name: 'Худи оверсайз серое',
      wb_barcode: '4680123456796', requires_honest_sign: true,
      length_mm: null, width_mm: null, height_mm: null, weight_g: null, volume_liters: null,
      added_by_fulfillment: false, expected_qty: 40, actual_qty: 0, posted_qty: 0,
      storage_location_id: null, storage_location_code: null,
    },
  ],
}

const WAREHOUSES = [{ id: 'w-yartsevo', name: 'Ярцево', code: 'YAR' }]
const LOCATIONS = [
  { id: 'loc-a01', code: 'A-01-01', warehouse_id: 'w-yartsevo', barcode: 'LOC-A0101' },
  { id: 'loc-a02', code: 'A-01-02', warehouse_id: 'w-yartsevo', barcode: 'LOC-A0102' },
  { id: 'loc-a03', code: 'A-02-01', warehouse_id: 'w-yartsevo', barcode: 'LOC-A0201' },
]

function stubResponse(url: string): unknown {
  if (url.endsWith(`/operations/inbound-intake-requests/${DETAIL.id}`)) {
    return DETAIL
  }
  if (url.includes('/operations/discrepancy-acts')) {
    return []
  }
  if (url.includes('/products/linked-wb-catalog')) {
    return []
  }
  if (url.includes(`/warehouses/${DETAIL.warehouse_id}/locations`)) {
    return LOCATIONS
  }
  if (url.endsWith('/warehouses')) {
    return WAREHOUSES
  }
  if (url.includes('/notifications')) {
    return { items: [], unread_count: 0 }
  }
  // Действия сканирования/распределения в макете не пересчитывают документ —
  // отдаём его как есть, чтобы клик не падал с ошибкой.
  if (url.includes('/operations/inbound-intake-requests/')) {
    return DETAIL
  }
  return {}
}

function installStubServer() {
  window.fetch = (async (input: RequestInfo | URL) => {
    const url = typeof input === 'string' ? input : input instanceof URL ? input.href : input.url
    return new Response(JSON.stringify(stubResponse(url)), {
      status: 200,
      headers: { 'Content-Type': 'application/json' },
    })
  }) as typeof window.fetch
}

installStubServer()

function InboundPreview() {
  const [openId, setOpenId] = useState<string | null>(null)
  return (
    <>
      <FfInboundQueuePage
        workspace="reception"
        rows={QUEUE_ROWS}
        sellers={SELLERS}
        onOpen={(id) => setOpenId(id)}
        onCreateDraft={() => undefined}
      />
      <Dialog open={openId !== null} onClose={() => setOpenId(null)} fullScreen data-testid="ff-doc-dialog">
        <MuiAppBar position="sticky" color="inherit" elevation={1}>
          <MuiToolbar>
            <IconButton edge="start" color="inherit" aria-label="Закрыть" onClick={() => setOpenId(null)}>
              <CloseIcon />
            </IconButton>
            <MuiTypography variant="h6" sx={{ flex: 1 }}>Документ</MuiTypography>
          </MuiToolbar>
        </MuiAppBar>
        <MuiBox sx={{ p: 2, overflow: 'auto', height: 'calc(100vh - 64px)' }}>
          {openId === DETAIL.id ? (
            <FfInboundRequestView
              token="preview"
              requestId={openId}
              isFulfillmentAdmin
              workspace="reception"
              sellers={SELLERS}
              onClose={() => setOpenId(null)}
            />
          ) : openId ? (
            <MuiTypography variant="body2" color="text.secondary" sx={{ p: 2 }}>
              В макете открывается полная карточка только для приёмки №000212 (ИП Горячкина) —
              остальные строки показывают, как выглядит очередь на разных стадиях.
            </MuiTypography>
          ) : null}
        </MuiBox>
      </Dialog>
    </>
  )
}

type RootHost = HTMLElement & { __previewRoot?: ReturnType<typeof createRoot> }

const container = document.getElementById('root') as RootHost | null
if (container) {
  const root = container.__previewRoot ?? createRoot(container)
  container.__previewRoot = root
  root.render(
    <StrictMode>
      <ThemeProvider theme={muiTheme}>
        <CssBaseline />
        <MemoryRouter initialEntries={['/app/ff/reception']}>
          <AuthedAppLayout
            onLogout={() => undefined}
            portal="ff"
            meRole="fulfillment_admin"
            userLabel="staging-admin@example.com"
            userRoleLabel="администратор"
          >
            <InboundPreview />
          </AuthedAppLayout>
        </MemoryRouter>
      </ThemeProvider>
    </StrictMode>,
  )
}
