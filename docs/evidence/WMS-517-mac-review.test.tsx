// Independent review reproducer only. Frozen SC17 tests remain unchanged.
import { createRequire } from 'node:module'
import { createRoot } from 'react-dom/client'
import { MemoryRouter } from 'react-router-dom'
import { expect, test, vi } from 'vitest'
import { SellerKizWithdrawalScreen } from '../../frontend/src/screens/v2/SellerKizWithdrawalScreen'

// Icons are decoration; preserve actual React, MUI controls, screen state and API.
vi.mock('@mui/icons-material', () => ({
  CloseOutlined: () => null, KeyOutlined: () => null, OpenInNewOutlined: () => null,
  RefreshOutlined: () => null, SearchOutlined: () => null,
}))

const require = createRequire(import.meta.url)
const { createHelper } = require('../../scripts/ops/avpack-sold-kiz-filter.js')
const delay = (ms: number) => new Promise(resolve => setTimeout(resolve, ms))
const seller = '0b8da5d8-f43a-42f5-a2ec-43173ea844bd'
const row = { row_id:'review-row', product_id:null, delivered_at:'2026-10-01T10:00:00Z', wb_order_id:'1',
  sku:'review', product_name:'Synthetic review', cis:'synthetic-cis', status:'not_withdrawn', error:null, operation_id:null }

for (const networkDelay of [0, 700]) test(`real React screen preparation with ${networkDelay}ms registry latency`, async () => {
  const host = document.createElement('div'); document.body.append(host)
  const root = createRoot(host)
  const originalFetch = window.fetch
  const calls: string[] = []
  let slow = false, certificateLists = 0
  window.localStorage.setItem('wms_token_seller', 'synthetic-review-token')
  window.fetch = async (input, init = {}) => {
    const url = new URL(String(input), window.location.origin)
    expect(init.method ?? 'GET').toBe('GET')
    calls.push(url.pathname)
    if (url.pathname === '/api/auth/me') return new Response(JSON.stringify({ tenant_id:'d6e1ad21-8afa-4acf-8d0b-907b9f2adcfe',
      seller_id:seller, active_seller_id:seller, role:'fulfillment_seller', withdrawal_enabled:true }))
    if (url.pathname.endsWith('/products')) return new Response('[]')
    expect(url.pathname).toBe('/api/operations/marking-codes/self/withdrawals')
    if (slow) await delay(networkDelay)
    return new Response(JSON.stringify({ rows:[row], total:1 }))
  }
  try {
    root.render(<MemoryRouter><SellerKizWithdrawalScreen token="synthetic-review-token" sellerId={seller}
      signingAdapter={{ checkReadiness:async () => ({}) as never, listCertificates:async () => { certificateLists++; return [] },
        signAttachedAuthChallenge:async () => { throw new Error('forbidden signing') },
        signDetachedDocument:async () => { throw new Error('forbidden signing') } }} /></MemoryRouter>)
    await delay(500)
    const refresh = () => [...document.querySelectorAll('button')].find(button => button.textContent?.trim() === 'Обновить')!
    expect(refresh().disabled).toBe(false)
    slow = true
    const outcome = await createHelper({ root:window }).run({ mode:'execute' }).catch((error:Error) => ({ error:error.message }))
    console.log(JSON.stringify({ networkDelay, outcome, refreshDisabled:refresh().disabled, certificateLists, registryGets:calls.filter(p=>p.endsWith('/withdrawals')).length }))
    expect(outcome.status).toBe('certificate_dialog_open')
    expect(certificateLists).toBe(1)
  } finally {
    root.unmount(); host.remove(); window.fetch=originalFetch; window.localStorage.clear()
    await delay(networkDelay)
  }
})
