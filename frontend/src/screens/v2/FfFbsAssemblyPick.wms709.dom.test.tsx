// @vitest-environment jsdom
import { act } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { afterEach, beforeAll, beforeEach, describe, expect, it } from 'vitest'
import { FfFbsAssemblyPick } from './FfFbsAssemblyPick'

// WMS-709 · C8: групповая сборка из двух поставок с общим товаром. Настоящие
// контейнер групповой сборки и экран подбора (без подмены); сервер — подставной
// fetch, который хранит снятое по каждой поставке и отдаёт его обратно.

beforeAll(() => {
  ;(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true
})

const SUPPLIES = [
  { id: 's1', sellerId: 'seller-a' },
  { id: 's2', sellerId: 'seller-b' },
]
// Товар g: в каждой поставке план 2, в группе 4. Места поставок разные, но
// у s2 два места: одно уже начато, второе пусто.
const LOCATIONS: Record<string, Array<{ id: string; code: string; qty: number }>> = {
  s1: [{ id: 'loc-a', code: 'А-1', qty: 3 }],
  s2: [{ id: 'loc-b', code: 'Б-1', qty: 4 }, { id: 'loc-c', code: 'В-1', qty: 1 }],
}

// Снятое по поставке и месту: ключ «поставка|место». В группе снято 2 + 1 = 3 из 4.
let picked: Record<string, number>
let originalFetch: typeof globalThis.fetch
let host: HTMLDivElement
let root: Root

function json(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } })
}

function optionsOf(supply: string) {
  const locations = LOCATIONS[supply]!.map((location) => {
    const taken = picked[`${supply}|${location.id}`] ?? 0
    const available = location.qty - taken
    return {
      storage_location_id: location.id, location_code: location.code, quantity: location.qty, reserved: 0,
      available, picked: taken,
      sources: [{ quantity: location.qty, available, is_loose: true, source_label: 'Россыпью', container_path: [], picked: taken }],
    }
  })
  const pickedTotal = locations.reduce((sum, location) => sum + location.picked, 0)
  return [{
    product_id: 'g', sku_code: 'SKU-G', product_name: 'Товар G', seller_article: null, barcode: null,
    planned_qty: 2, picked_qty: pickedTotal, locations,
  }]
}

async function server(input: RequestInfo | URL, init?: RequestInit): Promise<Response> {
  const url = new URL(typeof input === 'string' ? input : input instanceof URL ? input.href : input.url, 'http://wms.test')
  const path = url.pathname.replace(/^\/api/, '')
  if (path.startsWith('/products/linked-wb-catalog')) return json([])
  const options = path.match(/^\/operations\/fbs-supplies\/([^/]+)\/pick-options$/)
  if (options) return json(optionsOf(options[1]!))
  const set = path.match(/^\/operations\/fbs-supplies\/([^/]+)\/pick\/set$/)
  if (set) {
    const body = JSON.parse(String(init?.body ?? '{}')) as { storage_location_id: string; quantity: number }
    picked[`${set[1]}|${body.storage_location_id}`] = body.quantity
    return json({ quantity: body.quantity })
  }
  return json(null)
}

beforeEach(() => {
  picked = { 's1|loc-a': 2, 's2|loc-b': 1 }
  originalFetch = globalThis.fetch
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

async function waitMs(ms: number) {
  await act(async () => {
    await new Promise((resolve) => setTimeout(resolve, ms))
  })
}

const rowOf = (placeKey: string): HTMLTableRowElement | null =>
  host.querySelector<HTMLInputElement>(`input[data-testid="pick-place-qty-g-${placeKey}"]`)?.closest('tr') ?? null

function greenRow(row: Element | null): boolean {
  if (!row) throw new Error('нет строки места')
  const background = getComputedStyle(row).backgroundColor
  return background !== '' && background !== 'transparent' && background !== 'rgba(0, 0, 0, 0)'
}

function valueOf(row: Element | null, name: string): string | undefined {
  const names = [...host.querySelectorAll('thead th')].map((th) => (th.textContent ?? '').replace(/\s+/g, ''))
  const index = names.indexOf(name.replace(/\s+/g, ''))
  if (index < 0) throw new Error(`нет колонки «${name}»; есть: ${names.join(' | ')}`)
  return row?.children[index]?.textContent?.trim()
}

async function typeInto(placeKey: string, value: string) {
  const field = host.querySelector<HTMLInputElement>(`input[data-testid="pick-place-qty-g-${placeKey}"]`)
  if (!field) throw new Error(`нет поля ${placeKey}`)
  await act(async () => {
    Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value')!.set!.call(field, value)
    field.dispatchEvent(new Event('input', { bubbles: true }))
  })
}

describe('WMS-709 · C8: групповая сборка считает план, остаток и подсветку по сумме группы', () => {
  it('C8: групповая сборка — сумма по группе', async () => {
    await act(async () => {
      root.render(<FfFbsAssemblyPick token="t" supplies={SUPPLIES} />)
    })
    await waitMs(60)

    // Поставка s1 сама по себе собрана (2 из 2), но в группе не хватает одной штуки.
    expect(rowOf('cell:loc-a')).not.toBeNull()
    expect(greenRow(rowOf('cell:loc-a'))).toBe(false)
    expect(rowOf('cell:loc-c')).not.toBeNull()
    expect(valueOf(rowOf('cell:loc-a'), 'План')).toBe('4')

    // Дособираем в s2: группа 4 из 4, места без снятий скрываются.
    await typeInto('cell:loc-b', '2')
    await waitMs(700)
    expect(greenRow(rowOf('cell:loc-a'))).toBe(true)
    expect(greenRow(rowOf('cell:loc-b'))).toBe(true)
    expect(rowOf('cell:loc-c')).toBeNull()
    expect(valueOf(rowOf('cell:loc-a'), 'Осталось подобрать')).toBe('0')
    expect(valueOf(rowOf('cell:loc-b'), 'Осталось подобрать')).toBe('0')
  }, 20000)
})
