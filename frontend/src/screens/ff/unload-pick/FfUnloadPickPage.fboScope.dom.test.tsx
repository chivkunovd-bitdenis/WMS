// @vitest-environment jsdom
import { act } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, beforeAll, beforeEach, describe, expect, it } from 'vitest'
import { FfUnloadPickPage } from './FfUnloadPickPage'
import { UnloadPickScreen } from './UnloadPickScreen'
import { cellRef } from './pickStub'

// WMS-686 · границы: всё новое включается только для FBO. Поставка FBS и экран без fboMode —
// без переключателя, без столбца «КИЗ», без стрелок сворачивания и без «Забрать короб целиком»,
// и FBS не ходит в ручки КИЗ.

beforeAll(() => {
  ;(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true
})

const originalFetch = globalThis.fetch
let host: HTMLDivElement
let root: Root
let requested: string[]

const json = (body: unknown, status = 200) =>
  new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } })

const PICK_OPTIONS = [{
  product_id: 'p-1', sku_code: 'SKU-1', product_name: 'Куртка демо', seller_article: null, barcode: null,
  planned_qty: 3, picked_qty: 0,
  locations: [{
    storage_location_id: 'loc-b', location_code: 'Б-02', quantity: 4, reserved: 0, available: 4, picked: 0,
    sources: [{
      quantity: 4, available: 4, is_loose: false, source_label: 'Короб КР-1', picked: 0,
      container_path: [{ kind: 'box', id: 'box-1', code: 'КР-1', label: 'Короб КР-1' }],
    }],
  }],
}]

beforeEach(() => {
  requested = []
  globalThis.fetch = (async (input: RequestInfo | URL) => {
    const url = new URL(typeof input === 'string' ? input : input instanceof URL ? input.href : input.url, 'http://wms.test')
    const path = url.pathname.replace(/^\/api/, '')
    requested.push(path)
    if (path === '/products/linked-wb-catalog') return json([])
    if (path === '/operations/fbs-supplies/doc-1') {
      return json({ id: 'doc-1', marketplace: 'wb', document_number: 'D-1', display_number: 'D-1', status: 'picking', seller_id: 's', seller_name: 'С', planned_shipment_date: null })
    }
    if (path === '/operations/fbs-supplies/doc-1/pick-options') return json(PICK_OPTIONS)
    return json({ detail: `unexpected ${path}` }, 404)
  }) as typeof fetch
  host = document.createElement('div')
  document.body.appendChild(host)
  root = createRoot(host)
})

afterEach(() => {
  act(() => root.unmount())
  host.remove()
  globalThis.fetch = originalFetch
})

const byTestId = (testId: string) => host.querySelector(`[data-testid="${testId}"]`)

async function settle() {
  for (let step = 0; step < 5; step += 1) {
    await act(async () => {
      await new Promise((resolve) => setTimeout(resolve, 0))
    })
  }
}

describe('WMS-686 · FBS и экран без fboMode остаются прежними', () => {
  it('поставка FBS: таблица по ячейкам без переключателя, «КИЗ», стрелок и «Забрать короб целиком»; ручки КИЗ не вызываются', async () => {
    await act(async () => {
      root.render(
        <MemoryRouter>
          <FfUnloadPickPage token="t" requestId="doc-1" source="fbs" hideHeader />
        </MemoryRouter>,
      )
    })
    await settle()

    expect(byTestId('fbs-cell-pick-table')).not.toBeNull()
    expect(byTestId('pick-view-switch')).toBeNull()
    expect([...host.querySelectorAll('th')].map((one) => one.textContent)).not.toContain('КИЗ')
    expect(host.querySelector('[data-testid^="fbs-pick-collapse-"]')).toBeNull()
    expect(host.querySelector('[data-testid^="pick-kiz-"]')).toBeNull()
    expect(byTestId('pick-take-whole-box')).toBeNull()
    expect(requested.some((path) => path.includes('marking-codes'))).toBe(false)
    expect(window.sessionStorage.length).toBe(0)
  })

  it('UnloadPickScreen без fboMode: прежняя таблица от товара с зелёной заливкой готовых строк и без новых элементов', async () => {
    await act(async () => {
      root.render(
        <UnloadPickScreen
          onNote={() => undefined}
          hideHeader
          products={[{ id: 'p', name: 'Товар', sku: 'SKU', barcode: '123456', sellerArticle: 'ART', photo: '', size: null }]}
          plan={[{ id: 'plan', productId: 'p', plan: 2 }]}
          stock={[{ id: 'stock', productId: 'p', qty: 5, holder: cellRef('c') }]}
          objects={[]}
          cells={[{ id: 'c', code: 'C', barcode: 'CELL-C' }]}
          initialPicked={{ 'p|cell:c': 2 }}
        />,
      )
    })
    await settle()

    expect(byTestId('pick-table')).not.toBeNull()
    expect(byTestId('pick-view-switch')).toBeNull()
    expect([...host.querySelectorAll('th')].map((one) => one.textContent)).not.toContain('КИЗ')
    // Готовая строка по-прежнему красится заливкой DataTable, а не приглушается.
    const row = host.querySelector('[data-testid="pick-table"] tbody tr')!
    expect(getComputedStyle(row).backgroundColor).not.toBe('')
    expect(host.querySelector('[style*="opacity: 0.55"]')).toBeNull()
  })
})
