// @vitest-environment jsdom
import { Dialog, DialogContent } from '@mui/material'
import { act } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from 'vitest'
import { UnloadPickScreen, type UnloadPickScanResult } from './UnloadPickScreen'
import { cellRef, objRef, type PickProduct } from './pickStub'

// WMS-575 · подбор: скан принимает вся вкладка, где бы ни стоял курсор.
// Настоящий экран подбора в настоящем рендере; «сервер» — подставной onScan,
// сканер — события keydown в тот элемент, где сейчас фокус.

beforeAll(() => {
  ;(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true
})

const BARCODE = '2000000000011'
const product: PickProduct = {
  id: 'product-1',
  name: 'Куртка демо',
  sellerArticle: 'KURTKA-01',
  sku: 'EMU-KURTKA',
  barcode: BARCODE,
  photo: '',
  size: '48',
}

let host: HTMLDivElement
let root: Root

beforeEach(() => {
  host = document.createElement('div')
  document.body.appendChild(host)
  root = createRoot(host)
})

afterEach(() => {
  act(() => root.unmount())
  host.remove()
  document.body.innerHTML = ''
})

async function settle(ms = 0) {
  const steps = Math.max(1, Math.ceil(ms / 10))
  for (let step = 0; step < steps; step += 1) {
    await act(async () => {
      await new Promise((resolve) => setTimeout(resolve, Math.min(ms, 10)))
    })
  }
}

function keydown(target: Element, key: string) {
  const event = new KeyboardEvent('keydown', { key, code: /\d/.test(key) ? `Digit${key}` : key, bubbles: true, cancelable: true })
  target.dispatchEvent(event)
  return event
}

/** «Клавиатурный» сканер: символы подряд и Enter — туда, где фокус. */
function scan(code: string) {
  const target = document.activeElement ?? document.body
  let enter: KeyboardEvent | null = null
  act(() => {
    for (const key of code) keydown(target, key)
    enter = keydown(target, 'Enter')
  })
  return enter! as KeyboardEvent
}

/** Подставной pick/scan: каждое снятие — плюс одна штука с ячейки cell-1. */
function fakeServer(delayMs = 0) {
  let allocated = 0
  const calls: string[] = []
  const onScan = vi.fn(async ({ barcode }: { barcode: string; sourceKey: string | null }): Promise<UnloadPickScanResult> => {
    calls.push(barcode)
    if (delayMs) await new Promise((resolve) => setTimeout(resolve, delayMs))
    allocated += 1
    return {
      kind: 'product',
      sourceKey: null,
      storageLocationId: 'cell-1',
      productId: product.id,
      sku: product.sku,
      productName: product.name,
      pickedQty: allocated,
      allocationQuantity: allocated,
    }
  })
  return { onScan, calls }
}

function Screen({
  onScan,
  onSetPicked,
  plan = 3,
  dialogOpen = false,
}: {
  onScan: (payload: { barcode: string; sourceKey: string | null }) => Promise<UnloadPickScanResult>
  onSetPicked?: (payload: { productId: string; quantity: number }) => void
  plan?: number
  dialogOpen?: boolean
}) {
  return (
    <>
      <UnloadPickScreen
        onNote={() => undefined}
        hideHeader
        hideFooterActions
        products={[product]}
        plan={[{ id: 'plan-1', productId: product.id, plan }]}
        stock={[{ id: 'stock-1', productId: product.id, qty: 20, holder: cellRef('cell-1') }]}
        cells={[{ id: 'cell-1', code: 'А-01-01', barcode: 'LOC-A-01-01' }]}
        objects={[]}
        onScan={onScan}
        onSetPicked={onSetPicked}
      />
      <Dialog open={dialogOpen}>
        <DialogContent>История поставки</DialogContent>
      </Dialog>
    </>
  )
}

const leftQty = () => document.querySelector('[data-testid="pick-left-qty"]')?.textContent
const scannerLine = () => document.querySelector<HTMLElement>('[data-testid="pick-scan-line"]')
const expandButton = () => document.querySelector<HTMLButtonElement>('[data-testid^="pick-table-expand-"]')!
const expanded = () => document.querySelector('[data-testid^="pick-table-expanded-"]') !== null

describe('WMS-575 · подбор принимает скан, где бы ни стоял курсор', () => {
  it('C1/R1: фокус на стрелке строки — штука снята, строка не свернулась от Enter, плашка «Сканер активен»', async () => {
    const server = fakeServer()
    await act(async () => root.render(<Screen onScan={server.onScan} />))
    // Оператор раскрыл строку — фокус остался на стрелке (как в воспроизведении 2.1).
    await act(async () => expandButton().click())
    act(() => expandButton().focus())
    expect(document.activeElement).toBe(expandButton())
    expect(expanded()).toBe(true)
    expect(leftQty()).toBe('3')

    const enter = scan(BARCODE)
    await settle(30)

    expect(server.calls).toEqual([BARCODE])
    expect(enter.defaultPrevented).toBe(true)
    expect(expanded()).toBe(true)
    expect(leftQty()).toBe('2')
    expect(scannerLine()?.dataset.scannerActive).toBe('true')
  })

  it('C1/R1: фокус на пустом месте (body) — скан обработан', async () => {
    const server = fakeServer()
    await act(async () => root.render(<Screen onScan={server.onScan} />))
    act(() => (document.activeElement as HTMLElement | null)?.blur())
    expect(document.activeElement).toBe(document.body)

    scan(BARCODE)
    await settle(30)

    expect(server.calls).toEqual([BARCODE])
    expect(leftQty()).toBe('2')
  })

  it('C1/R1: фокус в поле «Снять» — цифры штрихкода не меняют число и не уходят на сервер', async () => {
    const server = fakeServer()
    const setPicked = vi.fn()
    await act(async () => root.render(<Screen onScan={server.onScan} onSetPicked={setPicked} />))
    await act(async () => expandButton().click())
    const qty = document.querySelector<HTMLInputElement>('input[data-testid^="pick-place-qty-"]')!
    act(() => qty.focus())
    expect(qty.value).toBe('0')

    // Браузер успевает вписать первую цифру кода в поле: «2» проходит проверку
    // потолка (план 3) и меняет число — как у живого оператора.
    const setter = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value')!.set!
    act(() => { keydown(qty, BARCODE[0]!) })
    await act(async () => {
      setter.call(qty, BARCODE[0])
      qty.dispatchEvent(new Event('input', { bubbles: true }))
    })
    expect(qty.value).toBe('2')
    // Остальные символы и Enter.
    act(() => {
      for (const key of BARCODE.slice(1)) keydown(qty, key)
      keydown(qty, 'Enter')
    })
    await settle(700)

    expect(server.calls).toEqual([BARCODE])
    // Скан снял одну штуку; «2» из штрихкода откатилась и на сервер не ушла.
    expect(qty.value).toBe('1')
    expect(leftQty()).toBe('2')
    expect(setPicked).not.toHaveBeenCalled()
  })

  it('R4: ручной ввод числа в «Снять» по-прежнему сохраняется', async () => {
    const server = fakeServer()
    const setPicked = vi.fn()
    await act(async () => root.render(<Screen onScan={server.onScan} onSetPicked={setPicked} />))
    await act(async () => expandButton().click())
    const qty = document.querySelector<HTMLInputElement>('input[data-testid^="pick-place-qty-"]')!
    act(() => qty.focus())
    const setter = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value')!.set!
    act(() => { keydown(qty, '2') })
    await act(async () => {
      setter.call(qty, '2')
      qty.dispatchEvent(new Event('input', { bubbles: true }))
    })
    await settle(700)

    expect(server.calls).toEqual([])
    expect(setPicked).toHaveBeenCalledTimes(1)
    expect(setPicked.mock.calls[0]![0]).toMatchObject({ productId: product.id, quantity: 2 })
    expect(leftQty()).toBe('1')
  })

  it('C3/R3: пять кодов подряд быстрее ответа сервера — пять снятий по порядку', async () => {
    const server = fakeServer(60)
    await act(async () => root.render(<Screen onScan={server.onScan} plan={10} />))
    act(() => expandButton().focus())

    for (let index = 0; index < 5; index += 1) scan(BARCODE)
    await settle(800)

    expect(server.calls).toEqual([BARCODE, BARCODE, BARCODE, BARCODE, BARCODE])
    expect(leftQty()).toBe('5')
  })

  it('C4/R4: окно поверх вкладки — «Сканер не слушает» и скан не обработан; закрыли — слушает без кликов', async () => {
    const server = fakeServer()
    await act(async () => root.render(<Screen onScan={server.onScan} />))
    expect(scannerLine()?.dataset.scannerActive).toBe('true')

    await act(async () => root.render(<Screen onScan={server.onScan} dialogOpen />))
    await settle(20)
    expect(scannerLine()?.dataset.scannerActive).toBe('false')
    expect(scannerLine()?.textContent).toContain('Сканер не слушает')
    scan(BARCODE)
    await settle(30)
    expect(server.calls).toEqual([])

    await act(async () => root.render(<Screen onScan={server.onScan} />))
    await settle(400)
    expect(scannerLine()?.dataset.scannerActive).toBe('true')
    act(() => (document.activeElement as HTMLElement | null)?.blur())
    scan(BARCODE)
    await settle(30)
    expect(server.calls).toEqual([BARCODE])
    expect(leftQty()).toBe('2')
  })
})


describe('WMS-602 · ячейка → тара → товар в подборе ФБС', () => {
  it('передаёт ячейку в скан тары, затем выбранный короб в скан товара', async () => {
    const onScan = vi.fn(async ({ barcode }: { barcode: string; sourceKey: string | null }): Promise<UnloadPickScanResult> => {
      if (barcode === 'J-1-4') return {
        kind: 'location', storageLocationId: 'cell-1', locationCode: 'Ж-1-4',
      }
      if (barcode === 'INB-M5KSFV1J1XP9WW') return {
        kind: 'container', storageLocationId: 'cell-1', locationCode: 'Ж-1-4',
        containerKind: 'box', containerId: 'box-1', containerCode: barcode,
      }
      return {
        kind: 'product', sourceKey: objRef('box-1'), storageLocationId: 'cell-1',
        productId: product.id, sku: product.sku, productName: product.name,
        pickedQty: 1, allocationQuantity: 1,
      }
    })
    await act(async () => root.render(<Screen onScan={onScan} />))
    scan('J-1-4')
    await settle(30)
    expect(leftQty()).toBe('3')
    expect(document.querySelector('[data-testid="pick-source"]')?.textContent).toBe('Ж-1-4')
    scan('INB-M5KSFV1J1XP9WW')
    await settle(30)
    expect(leftQty()).toBe('3')
    expect(document.querySelector('[data-testid="pick-source"]')?.textContent).toBe('INB-M5KSFV1J1XP9WW')
    scan(BARCODE)
    await settle(30)
    expect(onScan.mock.calls.map(([payload]) => payload)).toEqual([
      { barcode: 'J-1-4', sourceKey: null },
      { barcode: 'INB-M5KSFV1J1XP9WW', sourceKey: cellRef('cell-1') },
      { barcode: BARCODE, sourceKey: objRef('box-1') },
    ])
  })
})
