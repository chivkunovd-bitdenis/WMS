// @vitest-environment jsdom
import { act } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from 'vitest'
import { UnloadPickScreen } from './UnloadPickScreen'
import { pickKey, type PickedMap } from './pickRows'
import { cellRef, type Cell, type GoodsLine, type PickProduct, type PlanLine } from './pickStub'

// WMS-709 · этап 2 (вид по ячейкам): зелёные собранные строки, скрытие лишних
// мест, возврат при уменьшении, «Уже подобрано», прокрутка к строке.
// Настоящий экран подбора в настоящем рендере; сохранение ответа не приходит
// (или приходит ровно тогда, когда тест этого хочет). Колонки ищутся по заголовку.

type Stock = GoodsLine & { pickCapacity?: number }
type View = { plan: PlanLine[]; stock: Stock[]; picked?: PickedMap }

beforeAll(() => {
  ;(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true
})

const product = (id: string): PickProduct => ({
  id, name: `Товар ${id.toUpperCase()}`, sku: `SKU-${id.toUpperCase()}`, sellerArticle: `ART-${id}`,
  barcode: `BC-${id.toUpperCase()}-0001`, photo: '', size: null,
})
const PRODUCTS = ['x', 'y', 'z', 'p', 'q', 'v', 'w', 'r'].map(product)

const CELLS: Cell[] = [
  { id: 'c7', code: 'Ж-1-7', barcode: 'LOC-7' },
  { id: 'c14', code: 'Ж-1-14', barcode: 'LOC-14' },
  { id: 'c20', code: 'Ж-1-20', barcode: 'LOC-20' },
  { id: 'c22', code: 'Ж-2-2', barcode: 'LOC-22' },
  { id: 'sort', code: 'Без ячеек', barcode: 'Без ячеек' },
]

const line = (id: string, productId: string, cellId: string, qty: number, extra: { pickCapacity?: number } = {}): Stock =>
  ({ id, productId, qty, holder: cellRef(cellId), ...extra })
const taken = (productId: string, cellId: string, qty: number): PickedMap => ({ [pickKey(productId, cellRef(cellId))]: qty })

// Товар p: план 2, снято по штуке с Ж-1-7 и Ж-1-14 — собран полностью. Ж-1-20 и
// сортировка без снятий. Товар q не собран: зелёных строк у него быть не должно.
const completeView = (): View => ({
  plan: [{ id: 'plan-p', productId: 'p', plan: 2 }, { id: 'plan-q', productId: 'q', plan: 2 }],
  stock: [
    line('p1', 'p', 'c7', 1), line('p2', 'p', 'c14', 1), line('p3', 'p', 'c20', 1), line('p4', 'p', 'sort', 1),
    line('q1', 'q', 'c7', 1), line('q2', 'q', 'c14', 2),
  ],
  picked: { ...taken('p', 'c7', 1), ...taken('p', 'c14', 1), ...taken('q', 'c7', 1) },
})

const norm = (text: string | null | undefined) => (text ?? '').replace(/\s+/g, '')

let host: HTMLDivElement
let root: Root
let scrolled: Element[]

beforeEach(() => {
  scrolled = []
  Element.prototype.scrollIntoView = function scrollIntoView(this: Element) { scrolled.push(this) }
  host = document.createElement('div')
  document.body.appendChild(host)
  root = createRoot(host)
})

afterEach(() => {
  act(() => root.unmount())
  host.remove()
})

async function mount(view: View, save = vi.fn()) {
  await act(async () => {
    root.render(<UnloadPickScreen
      onNote={() => undefined} groupByCell hideHeader hideFooterActions
      products={PRODUCTS} plan={view.plan} stock={view.stock} objects={[]} cells={CELLS}
      initialPicked={view.picked ?? {}} onSetPicked={save}
    />)
  })
  return save
}

const rowEl = (key: string) => host.querySelector<HTMLTableRowElement>(`tr[data-row-key="${key}"]`)
const itemEl = (key: string) => host.querySelector<HTMLElement>(`[data-testid="fbs-pick-item-${key}"]`)
const fieldOf = (productId: string, placeKey: string) =>
  host.querySelector<HTMLInputElement>(`input[data-testid="pick-place-qty-${productId}-${placeKey}"]`)
const headerNames = () => [...host.querySelectorAll('thead th')].map((th) => norm(th.textContent))

function columnOf(name: string): number {
  const index = headerNames().indexOf(norm(name))
  if (index < 0) throw new Error(`нет колонки «${name}»; есть: ${headerNames().join(' | ')}`)
  return index
}
const valueIn = (key: string, name: string) => rowEl(key)?.children[columnOf(name)]?.textContent?.trim()

function isGreen(key: string): boolean {
  const row = rowEl(key)
  if (!row) throw new Error(`нет строки ${key}`)
  const background = getComputedStyle(row).backgroundColor
  return background !== '' && background !== 'transparent' && background !== 'rgba(0, 0, 0, 0)'
}

async function type(field: HTMLInputElement | null, value: string) {
  if (!field) throw new Error('нет поля «Собрано»')
  await act(async () => {
    Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value')!.set!.call(field, value)
    field.dispatchEvent(new Event('input', { bubbles: true }))
  })
}

/** Клавиатурный сканер: символы и Enter туда, где сейчас фокус. */
async function scanCode(code: string) {
  await act(async () => {
    const target = document.activeElement ?? document.body
    for (const key of code) target.dispatchEvent(new KeyboardEvent('keydown', { key, bubbles: true, cancelable: true }))
    target.dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter', code: 'Enter', bubbles: true, cancelable: true }))
    await new Promise((resolve) => setTimeout(resolve, 30))
  })
}

describe('WMS-709 этап 2 · вид подбора по ячейкам', () => {
  it('C1: шапка вида по ячейкам', async () => {
    await mount(completeView())
    expect(headerNames()).toEqual([
      'Ячейка / тара / товар', 'ШК', 'Размер', 'План', 'Осталось подобрать', 'Остаток в коробе', 'Собрано',
    ].map(norm))
  })

  it('C2: план и «Осталось подобрать» по товару', async () => {
    await mount({
      plan: [{ id: 'plan-x', productId: 'x', plan: 6 }],
      stock: [line('a', 'x', 'c7', 1), line('b', 'x', 'c14', 1), line('c', 'x', 'c20', 1), line('d', 'x', 'c22', 5)],
      picked: { ...taken('x', 'c7', 1), ...taken('x', 'c14', 1), ...taken('x', 'c20', 1) },
    })
    const keys = ['plan-x|cell:c7', 'plan-x|cell:c14', 'plan-x|cell:c20', 'plan-x|cell:c22']
    expect(fieldOf('x', 'cell:c22')?.max).toBe('3')
    expect(keys.map((key) => valueIn(key, 'План'))).toEqual(['6', '6', '6', '6'])
    expect(keys.map((key) => valueIn(key, 'Осталось подобрать'))).toEqual(['3', '3', '3', '3'])
    expect(valueIn('plan-x|cell:c22', 'Остаток в коробе')).toBe('5')
    await type(fieldOf('x', 'cell:c22'), '1')
    expect(keys.map((key) => valueIn(key, 'Осталось подобрать'))).toEqual(['2', '2', '2', '2'])
    expect(valueIn('plan-x|cell:c22', 'Остаток в коробе')).toBe('5')
  })

  it('C3: сортировка без снятия — «Уже подобрано»', async () => {
    await mount({
      plan: [{ id: 'plan-x', productId: 'x', plan: 1 }, { id: 'plan-y', productId: 'y', plan: 1 }, { id: 'plan-z', productId: 'z', plan: 1 }],
      stock: [line('x1', 'x', 'c7', 1), line('x2', 'x', 'sort', 1), line('y1', 'y', 'sort', 1), line('z1', 'z', 'sort', 1, { pickCapacity: 0 })],
      picked: taken('x', 'c7', 1),
    })
    const toggle = () => host.querySelector<HTMLButtonElement>('[data-testid="fbs-pick-already-picked-toggle"]')
    expect(fieldOf('y', 'cell:sort')).not.toBeNull()
    expect(rowEl('plan-x|cell:sort')).toBeNull()
    expect(rowEl('plan-z|cell:sort')).toBeNull()
    expect(toggle()?.textContent).toContain('2 шт')
    expect(toggle()?.getAttribute('aria-expanded')).toBe('false')
    await act(async () => toggle()!.click())
    expect(fieldOf('x', 'cell:sort')).toBeNull()
    expect(fieldOf('z', 'cell:sort')).toBeNull()
    expect(rowEl('plan-x|cell:sort')).not.toBeNull()
    expect(rowEl('plan-z|cell:sort')).not.toBeNull()
    await act(async () => toggle()!.click())
    expect(rowEl('plan-x|cell:sort')).toBeNull()
  })

  it('C4: зелёные строки собранного товара', async () => {
    await mount(completeView())
    expect(isGreen('plan-p|cell:c7')).toBe(true)
    expect(isGreen('plan-p|cell:c14')).toBe(true)
    expect(isGreen('cell:c7')).toBe(false)
    expect(isGreen('cell:c14')).toBe(false)
    expect(isGreen('plan-q|cell:c7')).toBe(false)
    expect(isGreen('plan-q|cell:c14')).toBe(false)
    expect(fieldOf('p', 'cell:c14')?.max).toBe('1')
  })

  it('C5: скрытие мест и N шт по показанным строкам', async () => {
    await mount({
      plan: [{ id: 'plan-p', productId: 'p', plan: 1 }, { id: 'plan-q', productId: 'q', plan: 3 }],
      stock: [line('p1', 'p', 'c7', 1), line('p2', 'p', 'c14', 1), line('p3', 'p', 'c20', 1), line('q1', 'q', 'c14', 3)],
      picked: taken('p', 'c7', 1),
    })
    expect(isGreen('plan-p|cell:c7')).toBe(true)
    expect(rowEl('plan-p|cell:c14')).toBeNull()
    expect(rowEl('plan-p|cell:c20')).toBeNull()
    expect(itemEl('cell:c20')).toBeNull()
    expect(itemEl('cell:c7')?.textContent).toContain('1 шт')
    expect(itemEl('cell:c14')?.textContent).toContain('3 шт')
    expect(itemEl('cell:c14')?.textContent).not.toContain('4 шт')
    expect(rowEl('plan-q|cell:c14')).not.toBeNull()
  })

  it('C6: уменьшение «Собрано» возвращает строки', async () => {
    // Сервер не отвечает: экран должен сам показать новое состояние.
    const save = vi.fn(() => new Promise<void>(() => undefined))
    await mount(completeView(), save)
    expect(isGreen('plan-p|cell:c7')).toBe(true)
    await type(fieldOf('p', 'cell:c7'), '0')
    expect(isGreen('plan-p|cell:c7')).toBe(false)
    expect(rowEl('plan-p|cell:c20')).not.toBeNull()
    expect(rowEl('plan-p|cell:sort')).not.toBeNull()
    expect(valueIn('plan-p|cell:c14', 'Осталось подобрать')).toBe('1')
    await type(fieldOf('p', 'cell:c7'), '1')
    expect(isGreen('plan-p|cell:c7')).toBe(true)
    expect(rowEl('plan-p|cell:c20')).toBeNull()
    await act(async () => host.querySelector<HTMLButtonElement>('[data-testid="pick-undo-p-cell:c7"]')!.click())
    expect(isGreen('plan-p|cell:c7')).toBe(false)
    expect(rowEl('plan-p|cell:c20')).not.toBeNull()
    expect(valueIn('plan-p|cell:c20', 'Осталось подобрать')).toBe('1')
  })

  it('C7: незавершённый товар — все места видны', async () => {
    await mount({
      plan: [{ id: 'plan-p', productId: 'p', plan: 2 }],
      stock: [line('p1', 'p', 'c7', 5), line('p2', 'p', 'c14', 1)],
      picked: taken('p', 'c7', 1),
    })
    expect(isGreen('plan-p|cell:c7')).toBe(false)
    expect(isGreen('plan-p|cell:c14')).toBe(false)
    expect(fieldOf('p', 'cell:c14')?.max).toBe('1')
    expect(valueIn('plan-p|cell:c7', 'Осталось подобрать')).toBe('1')
    expect(valueIn('plan-p|cell:c14', 'Осталось подобрать')).toBe('1')
  })

  it('C17: план 0 и товар без мест — белые строки', async () => {
    await mount({
      plan: [{ id: 'plan-w', productId: 'w', plan: 0 }, { id: 'plan-v', productId: 'v', plan: 2 }],
      stock: [line('w1', 'w', 'c7', 2), line('w2', 'w', 'c14', 1)],
    })
    expect(isGreen('plan-w|cell:c7')).toBe(false)
    expect(rowEl('plan-w|cell:c14')).not.toBeNull()
    expect(isGreen('plan-v|no-stock')).toBe(false)
    expect(rowEl('plan-v|no-stock')?.textContent).toContain('Нет на складе')
  })

  it('C10: вид по товарам (FBO) не меняется', async () => {
    await act(async () => {
      root.render(<UnloadPickScreen
        onNote={() => undefined} hideHeader products={PRODUCTS}
        plan={[{ id: 'plan-p', productId: 'p', plan: 2 }, { id: 'plan-q', productId: 'q', plan: 2 }]}
        stock={[line('p1', 'p', 'c7', 2), line('q1', 'q', 'c14', 2)]}
        objects={[]} cells={CELLS} initialPicked={taken('p', 'c7', 2)} onSetPicked={vi.fn()}
      />)
    })
    expect(isGreen('plan-p')).toBe(true)
    expect(isGreen('plan-q')).toBe(false)
    await act(async () => host.querySelector<HTMLButtonElement>('[data-testid="pick-table-expand-plan-p"]')!.click())
    expect(fieldOf('p', 'cell:c7')).not.toBeNull()
  })

  it('C14: перезагрузка сохраняет зелёное и скрытое', async () => {
    await mount(completeView())
    await act(async () => root.unmount())
    root = createRoot(host)
    await mount(completeView())
    expect(isGreen('plan-p|cell:c14')).toBe(true)
    expect(rowEl('plan-p|cell:c20')).toBeNull()
    expect(host.querySelector('[data-testid="fbs-pick-already-picked-toggle"]')?.getAttribute('aria-expanded')).toBe('false')
    expect(valueIn('plan-p|cell:c14', 'Осталось подобрать')).toBe('0')
  })

  it('C16: скан собранного товара — «уже всё снято»', async () => {
    const save = await mount(completeView())
    await scanCode('LOC-14')
    await scanCode('BC-P-0001')
    expect(host.textContent).toContain('по плану уже всё снято')
    expect(save).not.toHaveBeenCalled()
  })

  it('C18: скан ячейки прокручивает один раз', async () => {
    await mount({
      plan: [{ id: 'plan-r', productId: 'r', plan: 2 }],
      stock: [line('r1', 'r', 'c7', 2), line('r2', 'r', 'c14', 2)],
    })
    await scanCode('LOC-14')
    expect(scrolled).toHaveLength(1)
    expect(scrolled[0]!.closest('tr')).toBe(rowEl('cell:c14'))
    await scanCode('BC-R-0001')
    expect(fieldOf('r', 'cell:c14')?.value).toBe('1')
    await type(fieldOf('r', 'cell:c14'), '2')
    expect(scrolled).toHaveLength(1)
  })
})
