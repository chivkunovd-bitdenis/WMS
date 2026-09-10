// Local-only review fixture. Every fetch terminates here; no real account/API access.
import { useState } from 'react'
import { createRoot } from 'react-dom/client'
import { Box, Button, CssBaseline, ThemeProvider, Typography } from '@mui/material'
import { muiTheme } from '../src/mui/theme'
import { FfProductsFbsPage, toProduct, toRule, type ApiRule } from '../src/screens/ff/products-fbs/FfProductsFbsPage'
import { FbsStockDialog } from '../src/screens/ff/products-fbs/FbsStockDialog'
import type { Seller } from '../src/screens/ff/products-fbs/stub'
import '../src/index.css'

const sellerId = 'synthetic-seller'
const catalogRow = { id: 'synthetic-product', seller_id: sellerId, name: 'WB/Ozon склад 123',
  sku_code: 'SYNTHETIC-123', wb_primary_barcode: null, marketplaces: ['wb', 'ozon'] }
let current: ApiRule = {
  publish: true, publish_ozon: true, same_everywhere: true, percent: 50,
  by_warehouse: {}, units_mode: true,
  units_by_warehouse: { 'wb:123': 5, 'ozon:123': 3 },
  units_remaining_by_warehouse: { 'wb:123': 5, 'ozon:123': 3 },
  on_hand: 10, reserved: 0, free_stock: 10, published_now: 8,
}
const bindings = [{ wb_warehouse_id: 123, marketplace: 'wb' as const, is_active: true },
  { wb_warehouse_id: 123, marketplace: 'ozon' as const, is_active: true }]
let recordSave = (_value: string) => {}
window.fetch = async (input, init) => {
  const path = new URL(String(input), location.origin).pathname
  const answer = (data: unknown) => new Response(JSON.stringify(data), {
    headers: { 'Content-Type': 'application/json' },
  })
  if (init?.method === 'PUT') {
    const payload = JSON.parse(String(init.body))
    const rule = payload.rule ?? payload
    recordSave(JSON.stringify(rule.units_by_warehouse))
    current = { ...current, ...rule, units_remaining_by_warehouse: rule.units_by_warehouse }
    return answer(current)
  }
  if (path.endsWith('/ff-catalog-page')) return answer({ items: [catalogRow] })
  if (path.endsWith('/fbs-rule/bulk')) return answer({ items: [{ ...current, product_id: catalogRow.id }] })
  if (path.endsWith('/warehouse-bindings')) return answer(bindings)
  if (path.endsWith('/warehouses')) return answer([
    { wb_warehouse_id: 123, served: true, wms_warehouse_id: 'physical-1', name: 'WB 123' },
  ])
  throw new Error(`Unexpected synthetic request: ${path}`)
}
const twoWarehouseRule: ApiRule = { ...current, units_mode: false,
  on_hand: 6, free_stock: 6, published_now: 2 }
const twoWarehouseSeller: Seller = { id: sellerId, name: 'Синтетические два склада',
  wbWarehouses: [{ id: 'physical-1', name: 'Склад A' }, { id: 'physical-2', name: 'Склад B' }],
  warehouses: bindings.map((binding, i) => ({ id: `${binding.marketplace}:123`,
    marketplace: binding.marketplace, name: `${binding.marketplace} 123`,
    boundTo: `physical-${i + 1}`, fbsEnabled: true })),
}
function Review() {
  const [saved, setSaved] = useState('Ещё не сохраняли')
  const [open, setOpen] = useState(false)
  recordSave = setSaved
  return <ThemeProvider theme={muiTheme}><CssBaseline />
    <Box sx={{ p: 2 }}>
      <Typography>Синтетическая проверка WMS-417. Сеть заменена локальными ответами.</Typography>
      <Typography data-testid="captured-save">Последний JSON: {saved}</Typography>
      <Button onClick={() => setOpen(true)}>Проверить два физических склада</Button>
      <FfProductsFbsPage token="synthetic-only" sellers={[{ id: sellerId, name: 'Synthetic WB/Ozon' }]} />
      <FbsStockDialog open={open} products={[toProduct(catalogRow, twoWarehouseRule, sellerId)]}
        seller={twoWarehouseSeller} rule={toRule(catalogRow.id, twoWarehouseRule, bindings)}
        onClose={() => setOpen(false)} onSave={() => setOpen(false)} onBind={() => {}} />
    </Box>
  </ThemeProvider>
}
createRoot(document.getElementById('root')!).render(<Review />)
