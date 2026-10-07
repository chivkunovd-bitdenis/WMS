// @vitest-environment jsdom
import { act } from 'react'
import { createRoot } from 'react-dom/client'
import { beforeAll, describe, expect, it, vi } from 'vitest'
import { UnloadPickScreen } from './UnloadPickScreen'
import { pickKey, type PickedMap } from './pickRows'
import { cellRef } from './pickStub'

beforeAll(() => { (globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true })
const key = pickKey('p', cellRef('c'))
const props = {
  onNote: () => undefined, groupByCell: true, hideHeader: true, hideFooterActions: true,
  products: [{ id: 'p', name: 'Товар', sku: 'SKU', barcode: '123456', sellerArticle: 'ART', photo: '', size: null }],
  plan: [{ id: 'plan', productId: 'p', plan: 20 }],
  stock: [{ id: 'stock', productId: 'p', qty: 30, holder: cellRef('c') }],
  objects: [], cells: [{ id: 'c', code: 'C', barcode: 'CELL-C' }],
}

async function edit(input: HTMLInputElement, value: string) {
  await act(async () => {
    Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value')!.set!.call(input, value)
    input.dispatchEvent(new Event('input', { bubbles: true }))
  })
}

async function fixture(onSetPicked: () => void | Promise<void>) {
  const host = document.createElement('div'); document.body.appendChild(host)
  const root = createRoot(host)
  const render = async (initialPicked: PickedMap) => act(async () => root.render(
    <UnloadPickScreen {...props} initialPicked={initialPicked} onSetPicked={onSetPicked} />,
  ))
  await render({ [key]: 0 })
  const input = () => host.querySelector<HTMLInputElement>('input[data-testid="pick-place-qty-p-cell:c"]')!
  const close = async () => { await act(async () => root.unmount()); host.remove() }
  return { render, input, close }
}

describe('WMS-693/697 manual save lifecycle', () => {
  it('flushes the final number once on unmount before debounce', async () => {
    const save = vi.fn()
    const f = await fixture(save)
    await edit(f.input(), '1'); await edit(f.input(), '12')
    expect(save).not.toHaveBeenCalled()
    await f.close()
    expect(save).toHaveBeenCalledOnce()
    expect(save.mock.calls[0][0]).toMatchObject({ productId: 'p', quantity: 12 })
    await new Promise((resolve) => setTimeout(resolve, 450))
    expect(save).toHaveBeenCalledOnce()
  })

  it('cancels a pending manual target when Undo happens before debounce and close', async () => {
    const save = vi.fn()
    const f = await fixture(save)
    await edit(f.input(), '12')
    const undo = document.querySelector<HTMLButtonElement>('button[data-testid="pick-undo-p-cell:c"]')!
    expect(undo).toBeTruthy()
    await act(async () => undo.click())
    expect(f.input().value).toBe('0')
    await f.close()
    await new Promise((resolve) => setTimeout(resolve, 450))
    expect(save).toHaveBeenCalledOnce()
    expect(save.mock.calls[0][0]).toMatchObject({ productId: 'p', quantity: 0 })
  })

  it('applies a server refresh received while a conflicting save is still pending', async () => {
    let finish!: () => void
    const save = vi.fn(() => new Promise<void>((resolve) => { finish = resolve }))
    const f = await fixture(save)
    try {
      await edit(f.input(), '1')
      await act(async () => new Promise((resolve) => setTimeout(resolve, 450)))
      expect(save).toHaveBeenCalledOnce()
      await f.render({ [key]: 2 })
      expect(f.input().value).toBe('1')
      await act(async () => finish())
      expect(f.input().value).toBe('2')
    } finally { await f.close() }
  })

  it('keeps a newer number being typed when a prior request finishes', async () => {
    let finish!: () => void
    const save = vi.fn(() => new Promise<void>((resolve) => { finish = resolve }))
    const f = await fixture(save)
    try {
      await edit(f.input(), '1')
      await act(async () => new Promise((resolve) => setTimeout(resolve, 450)))
      await edit(f.input(), '3')
      await f.render({ [key]: 2 })
      await act(async () => finish())
      expect(f.input().value).toBe('3')
    } finally { await f.close(); finish() }
  })
})
