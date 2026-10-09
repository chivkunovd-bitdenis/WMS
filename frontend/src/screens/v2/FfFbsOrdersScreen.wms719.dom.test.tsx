// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from 'vitest'
import {
  click, headers, installNetwork, json, mount, order, page, refresh, row, search, tab,
} from './test-support/fbsOrdersDom'
import type { FbsWorklistOrder } from './fbsApi'

let dispose: (() => Promise<void>) | undefined
afterEach(async () => { await dispose?.(); dispose = undefined; vi.unstubAllGlobals(); vi.restoreAllMocks() })

async function open(items: FbsWorklistOrder[]) {
  const network = installNetwork((url) => {
    if (url.pathname.endsWith('/fbs-orders/worklist')) return json(page(items))
    if (url.pathname.endsWith('/fbs-supplies/worklist')) return json({ items: [], total: 0, server_now: page([]).server_now })
    throw new Error(`Unexpected request: ${url}`)
  })
  dispose = await mount(network)
  return network
}

function sizeCell(id = 'order-a') { return row(id).cells[headers().indexOf('Размер')] }
function position(id: string, size?: string | null) {
  return { id, product_id: id, name: `Товар ${id}`, seller_article: `ART-${id}`, sku: `SKU-${id}`, barcode: `BAR-${id}`, size, quantity: 3, reserved_quantity: 3, picked_quantity: 0 }
}

describe('WMS-719 size replaces SKU in the real FBS screen', () => {
  it.each(['Новые', 'Отменённые'])('C1 replaces SKU with one size column on %s', async (label) => {
    await open([order()])
    if (label !== 'Новые') await tab(label)
    const names = headers()
    expect(names.filter((name) => name === 'Размер')).toHaveLength(1)
    expect(names).not.toContain('SKU')
    expect(names.slice(names.indexOf('Артикул продавца'), names.indexOf('Артикул продавца') + 3)).toEqual(['Артикул продавца', 'Размер', 'ШК'])
    expect(sizeCell().textContent).toBe('M')
    expect(row().textContent).not.toContain('DISTINCT-SKU-719')
  })

  it.each(['Новые', 'Отменённые'])('C2 preserves each Ozon position size and order after refresh on %s', async (label) => {
    const item = order()
    item.marketplace = 'ozon'
    item.product.size = 'WRONG-COMMON-SIZE'
    item.positions = [position('one', 'S'), position('two', 'XL'), position('three')]
    await open([item])
    if (label !== 'Новые') await tab(label)
    for (let read = 0; read < 2; read += 1) {
      expect(Array.from(sizeCell().children, (node) => node.textContent)).toEqual(['S', 'XL', '—'])
      expect(row().cells[1].textContent).toMatch(/Товар one.*Товар two.*Товар three/)
      expect(sizeCell().textContent).not.toContain('WRONG-COMMON-SIZE')
      if (read === 0) await refresh()
    }
  })

  it.each([['wb', 'Новые'], ['ozon', 'Новые'], ['wb', 'Отменённые'], ['ozon', 'Отменённые']] as const)('C3 uses product size or dash without positions for %s on %s', async (marketplace, label) => {
    const sizes = [undefined, null, '', '   ', 'Универсальный']
    const items = sizes.map((size, index) => {
      const item = order(`size-${index}`)
      item.marketplace = marketplace
      if (size === undefined) delete (item.product as Partial<typeof item.product>).size
      else item.product.size = size
      return item
    })
    await open(items)
    if (label !== 'Новые') await tab(label)
    for (let read = 0; read < 2; read += 1) {
      sizes.forEach((size, index) => expect(sizeCell(`size-${index}`).textContent).toBe(size?.trim() || '—'))
      if (read === 0) await refresh()
    }
  })

  it.each(['Новые', 'Отменённые'])('C3 keeps equal sizes as separate Ozon position values on %s', async (label) => {
    const item = order()
    item.marketplace = 'ozon'
    item.positions = [position('one', 'L'), position('two', 'L')]
    await open([item])
    if (label !== 'Новые') await tab(label)
    expect(Array.from(sizeCell().children, (node) => node.textContent)).toEqual(['L', 'L'])
  })

  it.each(['Новые', 'Отменённые'])('C3 normalizes unknown sizes independently for Ozon positions on %s', async (label) => {
    const item = order(); item.marketplace = 'ozon'
    item.product.size = 'WRONG-FALLBACK'
    item.positions = [position('absent'), position('null', null), position('empty', ''), position('spaces', '   '), position('known', 'S')]
    await open([item])
    if (label !== 'Новые') await tab(label)
    expect(Array.from(sizeCell().children, (node) => node.textContent)).toEqual(['—', '—', '—', '—', 'S'])
  })

  it('C4 preserves SKU search, selection and real Excel export after refresh', async () => {
    const item = order()
    const before = structuredClone(item)
    const network = await open([item])
    const blobs: Blob[] = []
    Object.defineProperty(URL, 'createObjectURL', { configurable: true, value: (blob: Blob) => { blobs.push(blob); return 'blob:test-export' } })
    Object.defineProperty(URL, 'revokeObjectURL', { configurable: true, value: vi.fn() })
    vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => undefined)
    await search('DISTINCT-SKU-719')
    expect(network.mock.calls.some(([input]) => new URL(String(input), 'http://localhost').searchParams.get('search') === 'DISTINCT-SKU-719')).toBe(true)
    await click(row().querySelector('input[type="checkbox"]'))
    expect((row().querySelector('input[type="checkbox"]') as HTMLInputElement).checked).toBe(true)
    await click(document.querySelector('[data-testid="fbs-orders-download-excel"]'))
    expect(blobs).toHaveLength(1)
    const exported = await new Promise<string>((resolve) => {
      const reader = new FileReader(); reader.onload = () => resolve(String(reader.result)); reader.readAsText(blobs[0])
    })
    expect(exported).toContain('DISTINCT-SKU-719')
    expect(exported).toContain('BAR-719 / DISTINCT-SKU-719')
    await refresh()
    expect(sizeCell().textContent).toBe('M')
    expect(item).toEqual(before)
  })

  it('C5 keeps core order columns, status outside New and the supply table', async () => {
    await open([order()])
    for (const label of ['Новые', 'Отменённые']) {
      if (label !== 'Новые') await tab(label)
      expect(headers()).toEqual(expect.arrayContaining(['Товар', 'Селлер', 'Маршрут сдачи', 'Отгрузить до']))
      expect(headers().includes('Статус')).toBe(label !== 'Новые')
    }
    for (const label of ['В работе', 'В доставке', 'Завершённые']) {
      await tab(label)
      expect(headers()).toEqual(['Номер / название поставки', 'Селлер', 'Склад', 'Заказы / единицы', 'Короба', 'Статус', 'Печать'])
    }
    // Do not assert an overdue tab: its removal belongs to WMS-692.
  })
})
