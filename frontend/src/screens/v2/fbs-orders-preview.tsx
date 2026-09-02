import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { MemoryRouter } from 'react-router-dom'
import { CssBaseline, ThemeProvider } from '@mui/material'

import { muiTheme } from '../../mui/theme'
import { AuthedAppLayout } from '../../layouts/AuthedAppLayout'
import { FfFbsOrdersScreen } from './FfFbsOrdersScreen'
import type { FbsWorklistOrder, FbsWorklistWarehouseOption } from './fbsApi'
import '../../index.css'

// Полный макет экрана «Заказы FBS» на подставных данных.
//
// Как и в макете «Расчёты» (billing-sections-preview.tsx): рендерится настоящий
// экран внутри настоящего шелла портала, подменён только сервер — `fetch`
// отвечает выдуманным, но правдоподобным списком заказов. Товары и продавцы
// те же, что в макетах «Каталог» и «Карта склада» (ИП Чжоу, ИП Горячкина, ООО
// Ситипак, ИП Ларин) — это один и тот же выдуманный склад на всех вкладках
// лендинга, а не разрозненные картинки.

const SELLERS = [
  { id: 's-zhou', name: 'ИП Чжоу' },
  { id: 's-gor', name: 'ИП Горячкина' },
  { id: 's-city', name: 'ООО Ситипак' },
  { id: 's-larin', name: 'ИП Ларин' },
]

const WAREHOUSE_OPTIONS: FbsWorklistWarehouseOption[] = [
  { id: 'wb-koledino', name: 'Коледино', wb_warehouse: { id: 1, name: 'Коледино' } },
  { id: 'wb-elektrostal', name: 'Электросталь', wb_warehouse: { id: 2, name: 'Электросталь' } },
]

// Точка отсчёта дедлайнов — момент открытия страницы. Плашки «Отгрузить до»
// красятся по разнице с server_now, поэтому даты считаем от него, а не от
// фиксированной календарной даты: иначе через день макет показывал бы одни
// просрочки.
const NOW = Date.now()
const hoursFromNow = (hours: number) => new Date(NOW + hours * 3_600_000).toISOString()

function emptyMetadata(): FbsWorklistOrder['metadata'] {
  return { required: [], optional: [], states: [], delivery_allowed: true, last_checked_at: NOW ? new Date(NOW).toISOString() : null }
}

function markingMissingMetadata(kind: string): FbsWorklistOrder['metadata'] {
  return {
    required: [kind],
    optional: [],
    states: [{ kind, status: 'missing', reason: null }],
    delivery_allowed: false,
    last_checked_at: new Date(NOW).toISOString(),
  }
}

type OrderSeed = {
  id: string
  wbOrderId: number
  seller: (typeof SELLERS)[number]
  productName: string
  sellerArticle: string
  barcode: string
  sku: string
  size?: string | null
  color?: string | null
  canPvz: boolean
  buyerType?: 'individual' | 'legal'
  deadlineHours: number
  status?: string
  blockers?: Array<{ code: string; message: string }>
  metadata?: FbsWorklistOrder['metadata']
}

const ORDER_SEEDS: OrderSeed[] = [
  {
    id: 'ord-1', wbOrderId: 271834606, seller: SELLERS[1]!, productName: 'Футболка хлопок белая',
    sellerArticle: 'TS-WHT-M', barcode: '4680123456789', sku: 'TS-WHT-M', size: 'M', canPvz: true,
    deadlineHours: 7,
  },
  {
    id: 'ord-2', wbOrderId: 271834712, seller: SELLERS[1]!, productName: 'Худи оверсайз серое',
    sellerArticle: 'HD-GRY-L', barcode: '4680123456796', sku: 'HD-GRY-L', size: 'L', canPvz: false,
    deadlineHours: 30,
  },
  {
    id: 'ord-3', wbOrderId: 271901188, seller: SELLERS[2]!, productName: 'Кроссовки беговые',
    sellerArticle: 'SN-RUN-42', barcode: '4600987654321', sku: 'SN-RUN-42', size: '42', canPvz: true,
    deadlineHours: 62,
  },
  {
    id: 'ord-4', wbOrderId: 271902240, seller: SELLERS[2]!, productName: 'Носки спортивные, 3 пары',
    sellerArticle: 'SK-SPT-3', barcode: '4600987654338', sku: 'SK-SPT-3', canPvz: true,
    deadlineHours: 18,
  },
  {
    id: 'ord-5', wbOrderId: 272014477, seller: SELLERS[3]!, productName: 'Термокружка 450 мл',
    sellerArticle: 'MG-450', barcode: '4601122334455', sku: 'MG-450', canPvz: true,
    deadlineHours: 4,
    blockers: [{ code: 'warehouse_unmapped', message: 'Склад WB не привязан' }],
  },
  {
    id: 'ord-6', wbOrderId: 272014588, seller: SELLERS[3]!, productName: 'Ремень кожаный',
    sellerArticle: 'BL-110', barcode: '4601122334462', sku: 'BL-110', size: '110', canPvz: false,
    deadlineHours: 46,
  },
  {
    id: 'ord-7', wbOrderId: 272077310, seller: SELLERS[1]!, productName: 'Футболка хлопок белая',
    sellerArticle: 'TS-WHT-L', barcode: '4680123456772', sku: 'TS-WHT-L', size: 'L', canPvz: true,
    buyerType: 'legal', deadlineHours: 21,
  },
  {
    id: 'ord-8', wbOrderId: 272090041, seller: SELLERS[0]!, productName: 'Футболка хлопок белая',
    sellerArticle: 'TS-WHT-M', barcode: '4680123456789', sku: 'TS-WHT-M', size: 'M', canPvz: true,
    deadlineHours: 90,
  },
]

const EXPIRED_SEEDS: OrderSeed[] = [
  {
    id: 'ord-e1', wbOrderId: 271700214, seller: SELLERS[1]!, productName: 'Худи оверсайз серое',
    sellerArticle: 'HD-GRY-L', barcode: '4680123456796', sku: 'HD-GRY-L', size: 'L', canPvz: false,
    deadlineHours: -6, status: 'new', metadata: markingMissingMetadata('chestny_znak'),
  },
  {
    id: 'ord-e2', wbOrderId: 271700390, seller: SELLERS[2]!, productName: 'Носки спортивные, 3 пары',
    sellerArticle: 'SK-SPT-3', barcode: '4600987654338', sku: 'SK-SPT-3', canPvz: true,
    deadlineHours: -22, status: 'new',
  },
]

const CANCELLED_SEEDS: OrderSeed[] = [
  {
    id: 'ord-c1', wbOrderId: 271500118, seller: SELLERS[3]!, productName: 'Ремень кожаный',
    sellerArticle: 'BL-110', barcode: '4601122334462', sku: 'BL-110', size: '110', canPvz: true,
    deadlineHours: -40, status: 'cancelled',
  },
]

function buildOrder(seed: OrderSeed): FbsWorklistOrder {
  return {
    id: seed.id,
    marketplace: 'wb',
    external_order_id: null,
    wb_order_id: seed.wbOrderId,
    status: seed.status ?? 'new',
    wb_status: null,
    supplier_status: null,
    seller: { id: seed.seller.id, name: seed.seller.name },
    wb_warehouse: { id: 1, name: 'Коледино' },
    wms_warehouse: { id: 'w-yartsevo', name: 'Ярцево' },
    product: {
      id: `p-${seed.sku}`,
      name: seed.productName,
      image_url: null,
      seller_article: seed.sellerArticle,
      wb_article: 100000 + seed.wbOrderId % 900000,
      barcode: seed.barcode,
      sku: seed.sku,
      chrt_id: null,
      category: null,
      color: seed.color ?? null,
      size: seed.size ?? null,
    },
    positions: [
      {
        product_id: `p-${seed.sku}`,
        name: seed.productName,
        seller_article: seed.sellerArticle,
        sku: seed.sku,
        quantity: 1,
        reserved_quantity: 1,
        picked_quantity: 0,
      },
    ],
    inventory: { available_unpacked: 12, locations: [{ id: 'loc-1', code: 'A-01-02', available_unpacked: 12 }] },
    buyer_type: seed.buyerType ?? 'individual',
    cargo_type: 'ordinary',
    can_pvz: seed.canPvz,
    metadata: seed.metadata ?? emptyMetadata(),
    sticker: { code: null, status: 'not_requested', asset_url: null, applied_at: null },
    pick: { status: 'pending', location_code: null, picked_at: null },
    pack: { status: 'pending', packed_at: null },
    created_at_wb: hoursFromNow(seed.deadlineHours - 120),
    deadline_at: hoursFromNow(seed.deadlineHours),
    supply_id: null,
    selection_blockers: seed.blockers ?? [],
  }
}

const NEW_ORDERS = ORDER_SEEDS.map(buildOrder)
const EXPIRED_ORDERS = EXPIRED_SEEDS.map(buildOrder)
const CANCELLED_ORDERS = CANCELLED_SEEDS.map(buildOrder)

function ordersForStatusGroup(statusGroup: string | null): FbsWorklistOrder[] {
  if (statusGroup === 'expired') return EXPIRED_ORDERS
  if (statusGroup === 'cancelled') return CANCELLED_ORDERS
  // «В работе» / «В доставке» / «Завершённые» показывают поставки (activeSupplies),
  // а не эту выдачу — она нужна там только для заказов WB без локальной карточки
  // поставки. Ни один заказ мокапа в поставку не собран, так что для этих трёх
  // групп список пуст: иначе «новые» заказы ошибочно всплывали бы там же.
  if (statusGroup === 'active' || statusGroup === 'delivery' || statusGroup === 'done') return []
  return NEW_ORDERS
}

function stubResponse(url: string, method: string): unknown {
  const parsed = new URL(url, window.location.origin)
  const path = parsed.pathname
  const statusGroup = parsed.searchParams.get('status_group')

  if (path.endsWith('/operations/fbs-orders/worklist')) {
    return {
      items: ordersForStatusGroup(statusGroup),
      next_cursor: null,
      server_now: new Date(NOW).toISOString(),
      warehouse_options: WAREHOUSE_OPTIONS,
    }
  }
  if (path.endsWith('/operations/fbs-supplies/worklist')) {
    // Витрина «поставок» в макете пуста намеренно: карточка поставки — отдельный
    // тяжёлый экран (FfFbsSupplyWorkspace), не входящий в эту витрину. Вкладки
    // «В работе»/«В доставке»/«Завершённые» переключаются по-настоящему и
    // честно показывают пустое состояние, а не рисуют то, что не открывается.
    return { items: [], server_now: new Date(NOW).toISOString() }
  }
  if (path.endsWith('/fbs/assembly-time')) {
    return { hours: 6.4, orders: 318, within_12_hours_percent: 92, within_24_hours_percent: 99 }
  }
  if (path.endsWith('/operations/fbs-orders/sync') && method === 'POST') {
    // «skipped» — синхронизация помечается как пропущенная и цикл сразу
    // переходит к следующему продавцу, не дожидаясь фоновой задачи.
    return { id: 'preview-sync-job', status: 'skipped' }
  }
  if (path.endsWith('/notifications')) {
    return { items: [], unread_count: 0 }
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
        <MemoryRouter initialEntries={['/app/ff/fbs']}>
          <AuthedAppLayout
            onLogout={() => undefined}
            portal="ff"
            meRole="fulfillment_admin"
            userLabel="staging-admin@example.com"
            userRoleLabel="администратор"
          >
            <FfFbsOrdersScreen
              token="preview"
              authHeaders={() => ({})}
              sellers={SELLERS}
              isAdmin
            />
          </AuthedAppLayout>
        </MemoryRouter>
      </ThemeProvider>
    </StrictMode>,
  )
}
