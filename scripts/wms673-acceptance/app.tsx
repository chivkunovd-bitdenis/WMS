import React from 'react'
import { createRoot } from 'react-dom/client'
import { FfFbsSupplyWorkspace } from '../../frontend/src/screens/v2/FfFbsSupplyWorkspace'
import { FfFbsSupplyAssembly } from '../../frontend/src/screens/v2/FfFbsSupplyAssembly'
import { wms673Auth, wms673Workspace, wms673OzonOrder } from '../../frontend/src/screens/v2/wms673PrintFixtures'

// Real product components and existing API fixtures. Only transport is synthetic.
const kind = new URLSearchParams(location.search).get('kind') ?? 'single'
const first = wms673Workspace()
first.orders[0].product.size = 'Универсальный'
first.orders[0].product.color = 'Красный & синий насыщенный длинный цвет'
const fixtures = [first, wms673Workspace('supply-oz', [wms673OzonOrder()], 'ozon')]
const before = JSON.stringify(fixtures)
const requests: unknown[] = []
Object.assign(window, { acceptance: { fixtures, requests, before } })
window.fetch = async (input, init) => {
  const url = new URL(typeof input === 'string' ? input : input instanceof URL ? input.href : input.url, location.href)
  const path = url.pathname.replace(/^\/api/, '')
  const method = init?.method ?? 'GET'
  requests.push({ path, method })
  if (method !== 'GET') throw new Error(`Unexpected mutation: ${method} ${path}`)
  const one = fixtures.find(f => path.startsWith(`/operations/fbs-supplies/${f.supply.id}/`))
  const body = one && path.endsWith('/workspace') ? one
    : one && path.endsWith('/pick-options') ? []
    : path === '/warehouses' ? []
    : /marketplace-products|wb-products|product-catalog/.test(path) ? { items: [], total: 0 } : null
  return new Response(JSON.stringify(body), { headers: { 'Content-Type': 'application/json' } })
}
createRoot(document.getElementById('root')!).render(kind === 'single'
  ? <FfFbsSupplyWorkspace token="synthetic-wms673" authHeaders={wms673Auth} supplyId={first.supply.id} open onClose={() => undefined} />
  : <FfFbsSupplyAssembly token="synthetic-wms673" authHeaders={wms673Auth} supplyIds={fixtures.map(f => f.supply.id)} open onClose={() => undefined} />)
