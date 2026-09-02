import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { CssBaseline, ThemeProvider } from '@mui/material'

import { muiTheme } from '../../mui/theme'
import { AuthedAppLayout } from '../../layouts/AuthedAppLayout'
import { FfPackagingPage, type PackagingTask } from './FfPackagingPage'
import '../../index.css'

// Макет экрана «Упаковка»: очередь заданий — обычный React-компонент,
// получающий данные пропсами (как FfInboundQueuePage), а вот сама
// FfPackagingPage внутри уже сама стучится на сервер за списком и за карточкой
// задания. Поэтому здесь, как и в «Заказы FBS», подменяем `fetch`, а не пропсы,
// и заворачиваем экран в те же два маршрута, что и в App.tsx (`ff/packaging` и
// `ff/packaging/:taskId`) — иначе клик по строке открывает карточку и тут же
// её теряет: экран сверяет открытый task с параметром маршрута.

function line(overrides: Partial<PackagingTask['lines'][number]> & { id: string }): PackagingTask['lines'][number] {
  return {
    product_id: overrides.id,
    seller_id: null,
    seller_name: null,
    sku_code: 'SKU',
    product_name: 'Товар',
    storage_location_id: 'loc-1',
    storage_location_code: 'A-01-02',
    packaging_instructions: null,
    requires_honest_sign: false,
    qty_total: 1,
    qty_suggested_packed: 0,
    qty_confirmed_packed: 0,
    qty_need_pack: 1,
    qty_packed_in_task: 0,
    qty_done: 0,
    qty_marking_printed: 0,
    qty_marking_external: 0,
    qty_product_label_printed: 0,
    marking_available_count: 0,
    is_complete: false,
    ...overrides,
  }
}

const TASKS: PackagingTask[] = [
  {
    id: 'pack-1', document_number: 'Упаковка № 000045', display_number: '№000045',
    warehouse_id: 'w-yartsevo', warehouse_name: 'Ярцево', warehouse_code: 'Ярцево',
    seller_id: 's-gor', seller_name: 'ИП Горячкина', status: 'in_progress',
    marketplace_unload_request_id: 'mpu-1', inbound_intake_request_id: null, is_complete: false,
    created_at: '2026-09-02T07:10:00Z', updated_at: '2026-09-02T09:40:00Z',
    lines: [
      line({
        id: 'p-ts-wht-m', sku_code: 'TS-WHT-M', product_name: 'Футболка хлопок белая',
        storage_location_code: 'A-01-02', requires_honest_sign: true,
        qty_total: 20, qty_need_pack: 20, qty_packed_in_task: 12, qty_done: 12,
        qty_marking_printed: 12, marking_available_count: 8,
      }),
      line({
        id: 'p-hd-gry-l', sku_code: 'HD-GRY-L', product_name: 'Худи оверсайз серое',
        storage_location_code: 'A-02-01', requires_honest_sign: true,
        qty_total: 8, qty_need_pack: 8, qty_packed_in_task: 8, qty_done: 8,
        qty_marking_printed: 8, marking_available_count: 0, is_complete: true,
      }),
    ],
    events: [
      { id: 'ev-1', event_sequence: 1, action: 'scan_pack', line_id: 'p-ts-wht-m', product_id: 'p-ts-wht-m', product_name: 'Футболка хлопок белая', storage_location_id: 'loc-1', storage_location_code: 'A-01-02', quantity: 1, note: null, created_by_user_id: 'u1', created_by_user_email: 'operator@example.com', created_at: '2026-09-02T09:12:00Z', reversed_at: null },
      { id: 'ev-2', event_sequence: 2, action: 'manual_pack', line_id: 'p-hd-gry-l', product_id: 'p-hd-gry-l', product_name: 'Худи оверсайз серое', storage_location_id: 'loc-2', storage_location_code: 'A-02-01', quantity: 8, note: null, created_by_user_id: 'u1', created_by_user_email: 'operator@example.com', created_at: '2026-09-02T09:30:00Z', reversed_at: null },
    ],
  },
  {
    id: 'pack-2', document_number: 'Упаковка № 000046', display_number: '№000046',
    warehouse_id: 'w-yartsevo', warehouse_name: 'Ярцево', warehouse_code: 'Ярцево',
    seller_id: 's-city', seller_name: 'ООО Ситипак', status: 'in_progress',
    marketplace_unload_request_id: null, inbound_intake_request_id: null, is_complete: false,
    created_at: '2026-09-02T08:05:00Z', updated_at: '2026-09-02T08:05:00Z',
    lines: [
      line({
        id: 'p-sn-run-42', sku_code: 'SN-RUN-42', product_name: 'Кроссовки беговые',
        storage_location_code: 'B-01-04', qty_total: 6, qty_need_pack: 6,
      }),
      line({
        id: 'p-sk-spt-3', sku_code: 'SK-SPT-3', product_name: 'Носки спортивные, 3 пары',
        storage_location_code: 'B-01-05', qty_total: 30, qty_need_pack: 30,
      }),
    ],
    events: [],
  },
  {
    id: 'pack-3', document_number: 'Упаковка № 000044', display_number: '№000044',
    warehouse_id: 'w-yartsevo', warehouse_name: 'Ярцево', warehouse_code: 'Ярцево',
    seller_id: 's-larin', seller_name: 'ИП Ларин', status: 'done',
    marketplace_unload_request_id: 'mpu-9', inbound_intake_request_id: null, is_complete: true,
    created_at: '2026-09-01T11:00:00Z', updated_at: '2026-09-01T15:20:00Z', completed_at: '2026-09-01T15:20:00Z',
    lines: [
      line({
        id: 'p-mg-450', sku_code: 'MG-450', product_name: 'Термокружка 450 мл',
        storage_location_code: 'C-03-01', qty_total: 10, qty_need_pack: 10,
        qty_packed_in_task: 10, qty_done: 10, is_complete: true,
      }),
    ],
    events: [],
  },
]

function stubResponse(url: string, method: string): unknown {
  const idMatch = /\/operations\/packaging-tasks\/([^/?]+)$/.exec(url)
  if (idMatch && method === 'GET') {
    const task = TASKS.find((t) => t.id === idMatch[1])
    return task ?? { error: 'not_found' }
  }
  if (url.includes('/operations/packaging-tasks?')) {
    const status = new URL(url, window.location.origin).searchParams.get('status')
    const filtered = TASKS.filter((t) =>
      status === 'done' ? t.status === 'done' : status === 'cancelled' ? t.status === 'cancelled' : t.status !== 'done' && t.status !== 'cancelled',
    )
    return filtered
  }
  if (url.includes('/products/linked-wb-catalog')) {
    return []
  }
  if (url.includes('/utils/pendingMarkingApi') || url.includes('/operations/marking-codes/pending-marking')) {
    return { rows: [], total: 0 }
  }
  if (url.includes('/notifications')) {
    return { items: [], unread_count: 0 }
  }
  // Действия сканирования/печати/отмены — макет не пересчитывает задание по-настоящему,
  // а просто отдаёт его обратно, чтобы клик не падал с ошибкой.
  if (idMatch) {
    const task = TASKS.find((t) => t.id === idMatch[1])
    if (task) return task
  }
  return {}
}

function installStubServer() {
  window.fetch = (async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = typeof input === 'string' ? input : input instanceof URL ? input.href : input.url
    const method = (init?.method ?? 'GET').toUpperCase()
    return new Response(JSON.stringify(stubResponse(url, method)), {
      status: 200,
      headers: { 'Content-Type': 'application/json' },
    })
  }) as typeof window.fetch
}

installStubServer()

type RootHost = HTMLElement & { __previewRoot?: ReturnType<typeof createRoot> }

const container = document.getElementById('root') as RootHost | null
if (container) {
  const root = container.__previewRoot ?? createRoot(container)
  container.__previewRoot = root
  root.render(
    <StrictMode>
      <ThemeProvider theme={muiTheme}>
        <CssBaseline />
        <MemoryRouter initialEntries={['/app/ff/packaging']}>
          <AuthedAppLayout
            onLogout={() => undefined}
            portal="ff"
            meRole="fulfillment_admin"
            userLabel="staging-admin@example.com"
            userRoleLabel="администратор"
          >
            <Routes>
              <Route path="/app/ff/packaging" element={<FfPackagingPage token="preview" />} />
              <Route path="/app/ff/packaging/:taskId" element={<FfPackagingPage token="preview" />} />
            </Routes>
          </AuthedAppLayout>
        </MemoryRouter>
      </ThemeProvider>
    </StrictMode>,
  )
}
