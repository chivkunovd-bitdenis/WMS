// @vitest-environment jsdom
import { act } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from 'vitest'
import type { UnloadPickScanResult } from '../ff/unload-pick/UnloadPickScreen'

// WMS-574 · общий подбор окна сборки: настоящий контейнер FfFbsAssemblyPick,
// экран подбора заменён захватом его props — тест зовёт тот же обработчик
// скана, что и экран. Сервер подменён через fetch.

type ScanHandler = (payload: { barcode: string; sourceKey: string | null }) => Promise<UnloadPickScanResult>
type SetPickedHandler = (payload: { productId: string; place: { key: string }; quantity: number }) => Promise<void>
const captured = vi.hoisted(() => ({ onScan: null as ScanHandler | null, onSetPicked: null as SetPickedHandler | null }))

vi.mock('../ff/unload-pick/UnloadPickScreen', () => ({
  UnloadPickScreen: (props: { onScan?: ScanHandler; onSetPicked?: SetPickedHandler }) => {
    captured.onScan = props.onScan ?? null
    captured.onSetPicked = props.onSetPicked ?? null
    return null
  },
}))

import { FfFbsAssemblyPick } from './FfFbsAssemblyPick'

beforeAll(() => {
  ;(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true
})

const SAME_BARCODE = '4600000000999'
// Две поставки разных селлеров, у каждого свой товар с одним и тем же ШК.
const SUPPLIES = [
  { id: 's1', sellerId: 'seller-a', productId: 'p-a' },
  { id: 's2', sellerId: 'seller-b', productId: 'p-b' },
]

let picked: Record<string, number>
let scanCalls: Array<{ supply: string; productId: unknown }>
let setCalls: Array<{ supply: string; body: Record<string, unknown>; key: string | null }>
let emptySourceSupply: string | null
let failFirstSet: boolean
let commitFirstSetBeforeReply: boolean
let conflictSet: boolean
const originalFetch = globalThis.fetch

function json(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } })
}

function pickOptions(supply: (typeof SUPPLIES)[number]) {
  const taken = picked[supply.id] ?? 0
  const available = emptySourceSupply === supply.id ? 0 : 5 - taken
  return [{
    product_id: supply.productId,
    sku_code: `SKU-${supply.productId}`,
    product_name: `Товар ${supply.productId}`,
    seller_article: null,
    barcode: null,
    planned_qty: 1,
    picked_qty: taken,
    locations: [{
      storage_location_id: `loc-${supply.id}`,
      location_code: `А-${supply.id}`,
      quantity: 5,
      reserved: 0,
      available,
      picked: taken,
      sources: [{ quantity: 5, available, is_loose: true, source_label: 'Россыпью', container_path: [], picked: taken }],
    }],
  }]
}

async function server(input: RequestInfo | URL, init?: RequestInit): Promise<Response> {
  const url = new URL(typeof input === 'string' ? input : input instanceof URL ? input.href : input.url, 'http://wms.test')
  const path = url.pathname.replace(/^\/api/, '')
  if (path === '/products/linked-wb-catalog') {
    const sellerId = url.searchParams.get('seller_id')
    const supply = SUPPLIES.find((one) => one.sellerId === sellerId)!
    return json([{
      id: supply.productId, name: `Товар ${supply.productId}`, sku_code: `SKU-${supply.productId}`,
      wb_nm_id: null, wb_vendor_code: null, wb_subject_name: null, wb_primary_image_url: null,
      wb_barcodes: [SAME_BARCODE], wb_primary_barcode: SAME_BARCODE, wb_size: null, wb_color: null,
    }])
  }
  const options = path.match(/^\/operations\/fbs-supplies\/([^/]+)\/pick-options$/)
  if (options) return json(pickOptions(SUPPLIES.find((one) => one.id === options[1])!))
  const scan = path.match(/^\/operations\/fbs-supplies\/([^/]+)\/pick\/scan$/)
  if (scan) {
    const supply = SUPPLIES.find((one) => one.id === scan[1])!
    const body = JSON.parse(String(init?.body ?? '{}')) as { product_id?: string }
    scanCalls.push({ supply: supply.id, productId: body.product_id })
    // Сервер поставки знает только свой товар и снимает его, пока он нужен.
    if (body.product_id !== supply.productId || (picked[supply.id] ?? 0) >= 1) {
      return json({ detail: 'Товар не входит в состав поставки или уже подобран.' }, 409)
    }
    picked[supply.id] = (picked[supply.id] ?? 0) + 1
    return json({
      kind: 'product', storage_location_id: null, location_code: null, product_id: supply.productId,
      sku_code: `SKU-${supply.productId}`, product_name: `Товар ${supply.productId}`, picked_qty: 1,
      allocation_quantity: 1, container_kind: null, container_id: null, container_code: null,
    })
  }
  const set = path.match(/^\/operations\/fbs-supplies\/([^/]+)\/pick\/set$/)
  if (set) {
    const body = JSON.parse(String(init?.body ?? '{}')) as Record<string, unknown>
    setCalls.push({ supply: set[1], body, key: new Headers(init?.headers).get('Idempotency-Key') })
    if (failFirstSet) {
      failFirstSet = false
      if (commitFirstSetBeforeReply) picked[set[1]] = Number(body.quantity)
      throw new TypeError('lost set reply')
    }
    if (conflictSet) return json({ detail: { code: 'pick_quantity_changed', message: 'Количество изменилось.' } }, 409)
    return json({ quantity: body.quantity })
  }
  return json(null)
}

let host: HTMLDivElement
let root: Root

beforeEach(() => {
  picked = {}
  scanCalls = []
  captured.onScan = null
  captured.onSetPicked = null
  setCalls = []
  emptySourceSupply = null
  failFirstSet = false
  commitFirstSetBeforeReply = false
  conflictSet = false
  globalThis.fetch = server as typeof fetch
  host = document.createElement('div')
  document.body.appendChild(host)
  root = createRoot(host)
})

afterEach(() => {
  act(() => root.unmount())
  host.remove()
  globalThis.fetch = originalFetch
})

async function settle(ms = 30) {
  await act(async () => {
    await new Promise((resolve) => setTimeout(resolve, ms))
  })
}

describe('WMS-574 Д5 · общий подбор при одном ШК у товаров разных селлеров', () => {
  it('каждая штука уходит поставке, которой нужен именно её товар', async () => {
    await act(async () => {
      root.render(<FfFbsAssemblyPick token="t" supplies={SUPPLIES.map(({ id, sellerId }) => ({ id, sellerId }))} />)
    })
    await settle(80)
    expect(captured.onScan).not.toBeNull()

    let first: UnloadPickScanResult | null = null
    await act(async () => {
      first = await captured.onScan!({ barcode: SAME_BARCODE, sourceKey: null })
    })
    await settle()
    let second: UnloadPickScanResult | null = null
    await act(async () => {
      second = await captured.onScan!({ barcode: SAME_BARCODE, sourceKey: null })
    })
    await settle()

    expect(first).toMatchObject({ kind: 'product', productId: 'p-a' })
    expect(second).toMatchObject({ kind: 'product', productId: 'p-b' })
    expect(picked).toEqual({ s1: 1, s2: 1 })
    expect(scanCalls).toEqual([
      { supply: 's1', productId: 'p-a' },
      { supply: 's2', productId: 'p-b' },
    ])
  })

  it('skips only a no-stock candidate and sends one scan to the later seller with stock', async () => {
    emptySourceSupply = 's1'
    await act(async () => {
      root.render(<FfFbsAssemblyPick token="t" supplies={SUPPLIES.map(({ id, sellerId }) => ({ id, sellerId }))} />)
    })
    await settle(80)

    await act(async () => {
      await captured.onScan!({ barcode: SAME_BARCODE, sourceKey: null })
    })

    expect(scanCalls).toEqual([{ supply: 's2', productId: 'p-b' }])
    expect(picked).toEqual({ s2: 1 })
  })

  it('retries a manual group save with its original expected quantity and idempotency key', async () => {
    await act(async () => {
      root.render(<FfFbsAssemblyPick token="t" supplies={[{ id: 's1', sellerId: 'seller-a' }]} />)
    })
    await settle(80)
    failFirstSet = true

    await act(async () => {
      await captured.onSetPicked!({ productId: 'p-a', place: { key: 'cell:loc-s1' }, quantity: 1 })
    })
    await settle()
    await act(async () => {
      await captured.onSetPicked!({ productId: 'p-a', place: { key: 'cell:loc-s1' }, quantity: 1 })
    })

    expect(setCalls).toHaveLength(2)
    expect(setCalls.map((call) => call.body)).toEqual([
      { product_id: 'p-a', storage_location_id: 'loc-s1', quantity: 1, expected_quantity: 0, container_kind: null, container_id: null },
      { product_id: 'p-a', storage_location_id: 'loc-s1', quantity: 1, expected_quantity: 0, container_kind: null, container_id: null },
    ])
    expect(setCalls[0].key).toBeTruthy()
    expect(setCalls[1].key).toBe(setCalls[0].key)
  })

  it('reconciles a committed-but-lost target 2 before accepting a new target 3', async () => {
    await act(async () => {
      root.render(<FfFbsAssemblyPick token="t" supplies={[{ id: 's1', sellerId: 'seller-a' }]} />)
    })
    await settle(80)
    failFirstSet = true
    commitFirstSetBeforeReply = true

    await act(async () => {
      await captured.onSetPicked!({ productId: 'p-a', place: { key: 'cell:loc-s1' }, quantity: 2 })
    })
    await settle()
    await act(async () => {
      await captured.onSetPicked!({ productId: 'p-a', place: { key: 'cell:loc-s1' }, quantity: 3 })
    })
    await settle()

    // The second action settles the unknown target 2 and deliberately does
    // not pretend that its success saved the later target 3.
    expect(setCalls.map((call) => call.body.quantity)).toEqual([2, 2])
    expect(setCalls[1].key).toBe(setCalls[0].key)
    expect(picked.s1).toBe(2)

    await act(async () => {
      await captured.onSetPicked!({ productId: 'p-a', place: { key: 'cell:loc-s1' }, quantity: 3 })
    })
    expect(setCalls[2].body).toMatchObject({ quantity: 3, expected_quantity: 2 })
    expect(setCalls[2].key).not.toBe(setCalls[0].key)
  })

  it('settles a lost committed target 2 even when the operator submits the same current number', async () => {
    await act(async () => {
      root.render(<FfFbsAssemblyPick token="t" supplies={[{ id: 's1', sellerId: 'seller-a' }]} />)
    })
    await settle(80)
    failFirstSet = true
    commitFirstSetBeforeReply = true

    await act(async () => {
      await captured.onSetPicked!({ productId: 'p-a', place: { key: 'cell:loc-s1' }, quantity: 2 })
    })
    await settle()
    await act(async () => {
      await captured.onSetPicked!({ productId: 'p-a', place: { key: 'cell:loc-s1' }, quantity: 2 })
    })

    // A plan would be empty at 2; reconciliation still replays the old key.
    expect(setCalls.map((call) => call.body.quantity)).toEqual([2, 2])
    expect(setCalls[1].key).toBe(setCalls[0].key)
  })

  it('on pick_quantity_changed refreshes the source and does not overwrite it with the requested number', async () => {
    await act(async () => {
      root.render(<FfFbsAssemblyPick token="t" supplies={[{ id: 's1', sellerId: 'seller-a' }]} />)
    })
    await settle(80)
    conflictSet = true

    await act(async () => {
      await captured.onSetPicked!({ productId: 'p-a', place: { key: 'cell:loc-s1' }, quantity: 1 })
    })
    await settle()

    expect(setCalls).toHaveLength(1)
    expect(setCalls[0].body).toMatchObject({ quantity: 1, expected_quantity: 0 })
  })
})
