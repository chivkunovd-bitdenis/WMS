// @vitest-environment jsdom
import { act } from 'react'
import { createRoot } from 'react-dom/client'
import { renderToStaticMarkup } from 'react-dom/server'
import { beforeAll, describe, expect, it, vi } from 'vitest'
import { FbsCellPickTable } from './FbsCellPickTable'
import { UnloadPickScreen } from './UnloadPickScreen'
import { cellPickRowsOf, rowsOf } from './pickRows'
import { cellRef, objRef, type Cell, type GoodsLine, type PickProduct, type WarehouseObject } from './pickStub'

const cells: Cell[] = [
  { id: 'c-10', code: 'А 10', barcode: 'CELL-10' },
  { id: 'c-2', code: 'А 2', barcode: 'CELL-2' },
  { id: 'c-1', code: 'А 1', barcode: 'CELL-1' },
]
const objects: WarehouseObject[] = [
  { id: 'pallet', kind: 'pallet', code: 'П-10', barcode: 'PALLET-10', holder: cellRef('c-10') },
  { id: 'box', kind: 'box', code: 'КР-2', barcode: 'BOX-2', holder: objRef('pallet') },
  { id: 'loose-box', kind: 'box', code: 'КР-БЕЗ', barcode: 'BOX-NO-CELL', holder: null },
]
const products: PickProduct[] = [
  { id: 'sku-a', name: 'Товар A', sku: 'SKU-A', sellerArticle: 'ART-A', barcode: 'PRIMARY-A', photo: '', size: 'M' },
  { id: 'sku-b', name: 'Товар B', sku: 'SKU-B', sellerArticle: 'ART-B', barcode: 'PRIMARY-B', photo: '', size: null },
  { id: 'sku-c', name: 'Нет на складе', sku: 'SKU-C', sellerArticle: 'ART-C', barcode: 'PRIMARY-C', photo: '', size: null },
]
const stock: GoodsLine[] = [
  { id: 'a-1', productId: 'sku-a', qty: 3, holder: cellRef('c-1') },
  { id: 'a-2', productId: 'sku-a', qty: 4, holder: cellRef('c-2') },
  { id: 'a-3', productId: 'sku-a', qty: 5, holder: objRef('box') },
  { id: 'b-1', productId: 'sku-b', qty: 6, holder: objRef('box') },
  { id: 'b-2', productId: 'sku-b', qty: 7, holder: objRef('loose-box') },
]
const rows = rowsOf(
  products.map((product, index) => ({ id: `plan-${index}`, productId: product.id, plan: 20 })),
  stock, objects, cells, {}, products,
)

beforeAll(() => {
  ;(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true
})

describe('FBS picking grouped by cell', () => {
  it('walks cells in natural order and keeps every loose, nested, unplaced and missing-stock item', () => {
    const grouped = cellPickRowsOf(rows, objects, cells)
    expect(grouped.flatMap((item) => item.kind === 'cell' ? [item.title] : [])).toEqual([
      'А 1', 'А 2', 'А 10', 'Без ячейки',
    ])
    expect(grouped.filter((item) => item.kind === 'goods')).toHaveLength(6)
    expect(grouped.filter((item) => item.kind === 'goods' && item.row.product.id === 'sku-a')).toHaveLength(3)
    expect(grouped.filter((item) => item.kind === 'goods' && item.row.product.id === 'sku-b')).toHaveLength(2)
    expect(grouped.find((item) => item.kind === 'cell' && item.title === 'А 10')).toMatchObject({ qty: 11 })
    expect(grouped.filter((item) => item.kind === 'goods').reduce((total, item) => total + (item.kind === 'goods' ? item.place?.qty ?? 0 : 0), 0)).toBe(25)
    expect(grouped.slice(4, 8).map((item) => item.kind === 'goods' ? item.row.product.sku : item.title)).toEqual([
      'А 10', 'Палета П-10', 'Короб КР-2', 'SKU-A',
    ])
    expect(grouped).toContainEqual(expect.objectContaining({ kind: 'goods', place: null }))
  })

  it('shows the same primary barcodes and one quantity input per physical place', () => {
    const html = renderToStaticMarkup(<FbsCellPickTable
      rows={rows} objects={objects} cells={cells} source={null}
      onQtyChange={() => undefined} canUndo={() => false} onUndo={() => undefined}
    />)
    expect(html).toContain('PRIMARY-A')
    expect(html).toContain('PRIMARY-B')
    expect(html).toContain('PRIMARY-C')
    expect(html).toContain('ART-A')
    expect(html).toContain('КР-БЕЗ')
    const rendered = document.createElement('div')
    rendered.innerHTML = html
    expect(rendered.querySelectorAll('input[data-testid^="pick-place-qty-"]')).toHaveLength(stock.length)
  })

  it('puts the API sorting zone named “Без ячеек” after physical cells', () => {
    const sortingCell: Cell = { id: 'sorting', code: 'Без ячеек', barcode: 'Без ячеек' }
    const withSorting = rowsOf(
      [{ id: 'plan-a', productId: 'sku-a', plan: 20 }],
      [...stock, { id: 'unassigned', productId: 'sku-a', qty: 2, holder: cellRef('sorting') }],
      objects, [...cells, sortingCell], {}, products,
    )
    expect(cellPickRowsOf(withSorting, objects, [...cells, sortingCell]).flatMap((item) => (
      item.kind === 'cell' ? [item.title] : []
    ))).toEqual(['А 1', 'А 2', 'А 10', 'Без ячеек'])
  })

  it('keeps the existing place-specific picking action in the cell view', async () => {
    const host = document.createElement('div')
    document.body.appendChild(host)
    const root = createRoot(host)
    const onSetPicked = vi.fn()
    try {
      await act(async () => root.render(<UnloadPickScreen
        onNote={() => undefined} groupByCell hideHeader hideFooterActions
        products={products} plan={[{ id: 'plan-a', productId: 'sku-a', plan: 20 }]}
        stock={stock} objects={objects} cells={cells} onSetPicked={onSetPicked}
      />))
      const input = host.querySelector<HTMLInputElement>('input[data-testid="pick-place-qty-sku-a-cell:c-2"]')!
      expect(input).toBeTruthy()
      act(() => input.focus())
      act(() => input.dispatchEvent(new KeyboardEvent('keydown', { key: '2', code: 'Digit2', bubbles: true })))
      const setter = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value')!.set!
      await act(async () => {
        setter.call(input, '2')
        input.dispatchEvent(new Event('input', { bubbles: true }))
      })
      await act(async () => new Promise((resolve) => setTimeout(resolve, 700)))
      expect(onSetPicked).toHaveBeenCalledOnce()
      expect(onSetPicked.mock.calls[0]![0]).toMatchObject({
        productId: 'sku-a', quantity: 2, place: { key: cellRef('c-2'), qty: 4 },
      })
      const otherInput = host.querySelector<HTMLInputElement>('input[data-testid="pick-place-qty-sku-a-cell:c-1"]')!
      act(() => otherInput.focus())
      act(() => otherInput.dispatchEvent(new KeyboardEvent('keydown', { key: '1', code: 'Digit1', bubbles: true })))
      await act(async () => {
        setter.call(otherInput, '1')
        otherInput.dispatchEvent(new Event('input', { bubbles: true }))
      })
      await act(async () => new Promise((resolve) => setTimeout(resolve, 700)))
      expect(onSetPicked).toHaveBeenCalledTimes(2)
      expect(host.querySelectorAll('button[data-testid^="pick-undo-"]')).toHaveLength(1)
      const undo = host.querySelector<HTMLButtonElement>('button[data-testid="pick-undo-sku-a-cell:c-1"]')!
      expect(undo).toBeTruthy()
      await act(async () => undo.click())
      expect(onSetPicked).toHaveBeenCalledTimes(3)
      expect(onSetPicked.mock.calls[2]![0]).toMatchObject({
        productId: 'sku-a', quantity: 0, place: { key: cellRef('c-1'), qty: 3 },
      })
      expect(host.querySelector<HTMLInputElement>('input[data-testid="pick-place-qty-sku-a-cell:c-2"]')?.value).toBe('2')
    } finally {
      act(() => root.unmount())
      host.remove()
    }
  })
})
