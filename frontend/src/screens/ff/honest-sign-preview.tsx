import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { MemoryRouter } from 'react-router-dom'
import { CssBaseline, ThemeProvider } from '@mui/material'

import { muiTheme } from '../../mui/theme'
import { AuthedAppLayout } from '../../layouts/AuthedAppLayout'
import { FfHonestSignPage } from './FfHonestSignPage'
import '../../index.css'

// Макет экрана «Честный знак»: остатки кодов маркировки по товарам. Тот же
// каталог, что и в остальных вкладках лендинга — здесь смотрим на него не «где
// лежит» и не «что заказано», а «сколько кодов маркировки осталось напечатать».

const SELLERS = [
  { id: 's-zhou', name: 'ИП Чжоу' },
  { id: 's-gor', name: 'ИП Горячкина' },
  { id: 's-city', name: 'ООО Ситипак' },
  { id: 's-larin', name: 'ИП Ларин' },
]

type InventoryRow = {
  product_id: string
  sku_code: string
  product_name: string
  requires_honest_sign: boolean
  available_count: number
  printed_count: number
  personal_available: number
  shared_baskets: Array<{ pool_id: string; gtin: string; title: string; available: number; products_count: number }>
}

const ROWS: InventoryRow[] = [
  {
    product_id: 'p-ts-wht-m', sku_code: 'TS-WHT-M', product_name: 'Футболка хлопок белая',
    requires_honest_sign: true, available_count: 42, printed_count: 12, personal_available: 42,
    shared_baskets: [],
  },
  {
    product_id: 'p-hd-gry-l', sku_code: 'HD-GRY-L', product_name: 'Худи оверсайз серое',
    requires_honest_sign: true, available_count: 6, printed_count: 8, personal_available: 6,
    shared_baskets: [],
  },
  {
    product_id: 'p-sn-run-42', sku_code: 'SN-RUN-42', product_name: 'Кроссовки беговые',
    requires_honest_sign: true, available_count: 0, printed_count: 0, personal_available: 0,
    shared_baskets: [
      { pool_id: 'pool-shoes-42', gtin: '04680987654321', title: 'Общая корзина · обувь р.42', available: 340, products_count: 3 },
    ],
  },
  {
    product_id: 'p-sk-spt-3', sku_code: 'SK-SPT-3', product_name: 'Носки спортивные, 3 пары',
    requires_honest_sign: true, available_count: 128, printed_count: 40, personal_available: 128,
    shared_baskets: [],
  },
]

function stubResponse(url: string): unknown {
  if (url.includes('/operations/marking-codes/inventory')) {
    return { rows: ROWS, unlinked_available_count: 15, defective_count: 3 }
  }
  if (url.includes('/operations/marking-codes/pools')) {
    return [
      { id: 'pool-shoes-42', title: 'Общая корзина · обувь р.42', gtin: '04680987654321', products: [{ id: 'p-sn-run-42', sku_code: 'SN-RUN-42', name: 'Кроссовки беговые' }], available: 340, linked_products_count: 1 },
      { id: 'pool-unlinked', title: 'Без привязки', gtin: '04600000000000', products: [], available: 15, linked_products_count: 0 },
    ]
  }
  if (url.includes('/products/linked-wb-catalog')) {
    return []
  }
  if (url.includes('/notifications')) {
    return { items: [], unread_count: 0 }
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

type RootHost = HTMLElement & { __previewRoot?: ReturnType<typeof createRoot> }

const container = document.getElementById('root') as RootHost | null
if (container) {
  const root = container.__previewRoot ?? createRoot(container)
  container.__previewRoot = root
  root.render(
    <StrictMode>
      <ThemeProvider theme={muiTheme}>
        <CssBaseline />
        <MemoryRouter initialEntries={['/app/ff/honest-sign']}>
          <AuthedAppLayout
            onLogout={() => undefined}
            portal="ff"
            meRole="fulfillment_admin"
            userLabel="staging-admin@example.com"
            userRoleLabel="администратор"
          >
            <FfHonestSignPage token="preview" sellers={SELLERS} />
          </AuthedAppLayout>
        </MemoryRouter>
      </ThemeProvider>
    </StrictMode>,
  )
}
