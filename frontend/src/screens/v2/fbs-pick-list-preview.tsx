import { StrictMode, useState } from 'react'
import { createRoot } from 'react-dom/client'
import { MemoryRouter } from 'react-router-dom'
import { Box, CssBaseline, Stack, ThemeProvider, Typography } from '@mui/material'

import { muiTheme } from '../../mui/theme'
import { AuthedAppLayout } from '../../layouts/AuthedAppLayout'
import { FfFbsPickList } from './FfFbsPickList'
import type { FbsPickingItem } from './fbsApi'
import '../../index.css'

// Макет листа подбора FBS (диалог, открывающийся из поставки на вкладке
// «Заказы FBS» → «В работе»). В боевом экране это модалка поверх списка
// поставок — здесь она открыта поверх той же карточки заказов, что и на
// вкладке «Заказы FBS», чтобы вкладка не выглядела вырванной из контекста.

const PICKING_ITEMS: FbsPickingItem[] = [
  { article: 'TS-WHT-M', sku_code: 'TS-WHT-M', size: 'M', product_name: 'Футболка хлопок белая', quantity: 4 },
  { article: 'TS-WHT-L', sku_code: 'TS-WHT-L', size: 'L', product_name: 'Футболка хлопок белая', quantity: 2 },
  { article: 'HD-GRY-L', sku_code: 'HD-GRY-L', size: 'L', product_name: 'Худи оверсайз серое', quantity: 3 },
  { article: 'SN-RUN-42', sku_code: 'SN-RUN-42', size: '42', product_name: 'Кроссовки беговые', quantity: 1 },
  { article: 'SK-SPT-3', sku_code: 'SK-SPT-3', size: null, product_name: 'Носки спортивные, 3 пары', quantity: 6 },
  { article: 'MG-450', sku_code: 'MG-450', size: null, product_name: 'Термокружка 450 мл', quantity: 2 },
]

function stubResponse(url: string): unknown {
  if (url.includes('/picking-list')) {
    return { items: PICKING_ITEMS }
  }
  if (url.includes('/stickers')) {
    return { stickers: [] }
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

function PickListPreview() {
  const [open, setOpen] = useState(true)
  return (
    <Box sx={{ minHeight: '100vh' }}>
      <Box sx={{ p: 3, maxWidth: 720 }}>
        <Typography variant="h5" sx={{ mb: 1 }}>Поставка № 000214 · Коледино</Typography>
        <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
          ИП Горячкина · 6 позиций, 18 единиц. Лист подбора открывается по кнопке «Подбор» из
          карточки поставки на вкладке «Заказы FBS».
        </Typography>
        <Stack direction="row" spacing={1}>
          <Box
            component="button"
            onClick={() => setOpen(true)}
            sx={{
              px: 2, py: 1, borderRadius: 1, border: '1px solid', borderColor: 'primary.main',
              color: 'primary.main', bgcolor: 'transparent', cursor: 'pointer', fontSize: 14,
            }}
          >
            Открыть лист подбора
          </Box>
        </Stack>
      </Box>
      <FfFbsPickList
        token="preview"
        authHeaders={() => ({})}
        supplyId="supply-preview-214"
        open={open}
        onClose={() => setOpen(false)}
      />
    </Box>
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
        <MemoryRouter initialEntries={['/app/ff/fbs']}>
          <AuthedAppLayout
            onLogout={() => undefined}
            portal="ff"
            meRole="fulfillment_admin"
            userLabel="staging-admin@example.com"
            userRoleLabel="администратор"
          >
            <PickListPreview />
          </AuthedAppLayout>
        </MemoryRouter>
      </ThemeProvider>
    </StrictMode>,
  )
}
