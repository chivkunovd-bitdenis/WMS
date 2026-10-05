// @vitest-environment jsdom
import { act } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { afterEach, beforeAll, describe, expect, it, vi } from 'vitest'
import { FbsStockDialog } from './FbsStockDialog'
import { FbsStockDialogContainer } from './FbsStockDialogContainer'
import type { FbsStockDialogData } from './fbsStockDialogLoader'
import type { BindingOutcome, SaveOutcome, StockDialogSession } from './fbsStockDialogSession'
import { toProductBindingState, type StockBinding, type StockDialogProduct } from './fbsStockBlocks'

// Окно «Остаток для FBS» (WMS-469) в настоящем React-рендере: исполняются
// эффекты, обработчики и модалка MUI. Сеть подменена сессией с управляемыми
// исходами — проверяется, что окно делает после ответов, а не сами запросы
// (те — в fbsStockDialogSession.test.ts).

beforeAll(() => {
  ;(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true
})

const A = 'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa'
const B = 'bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb'
const WMS = [{ id: A, name: 'Склад A' }, { id: B, name: 'Склад B' }]

const wb: StockBinding = {
  id: 'b-wb', marketplace: 'wb', externalId: '501001', name: 'E2E Seller Warehouse',
  wmsWarehouseId: A, wmsWarehouseName: 'Склад A', served: true, editable: true,
}
const ozon: StockBinding = {
  id: 'b-ozon', marketplace: 'ozon', externalId: '777001', name: 'Хоругвино',
  wmsWarehouseId: A, wmsWarehouseName: 'Склад A', served: true, editable: true,
}

type RuleSpec = { free: number; value?: number; mode?: 'percent' | 'units'; publish?: boolean; applicable?: boolean; unitsConfigured?: boolean }
function product(rules: Record<string, RuleSpec>, id = 'p'): StockDialogProduct {
  return {
    id, name: `Товар ${id}`, sku: id.toUpperCase(), size: null,
    byBinding: Object.fromEntries(Object.entries(rules).map(([bindingId, one]) => [bindingId, toProductBindingState({
      publish: one.publish ?? true, mode: one.mode ?? 'units', value: one.value ?? 0,
      units_configured: one.unitsConfigured ?? true, marketplace: 'wb',
      external_warehouse_id: '501001', wms_warehouse_id: A, served: true, applicable: one.applicable ?? true,
      on_hand: one.free, reserved: 0, free_stock: one.free, published_now: 0,
    })])),
  }
}
function data(bindings: StockBinding[], products: StockDialogProduct[], extraCabinet = false): FbsStockDialogData {
  return {
    products, bindings,
    cabinets: {
      wb: { received: true, rows: [
        { wb_warehouse_id: 501001, name: 'E2E Seller Warehouse', wms_warehouse_id: A, served: true, marketplace: 'wb' },
        ...(extraCabinet ? [{ wb_warehouse_id: 501002, name: 'Второй склад', wms_warehouse_id: null, served: false, marketplace: 'wb' as const }] : []),
      ] },
      ozon: { received: false },
    },
    wbWarehousesError: null, ozonWarehousesError: null,
  }
}

/** Перечитанное состояние — всегда новый объект, как и настоящий ответ сервера. */
const fresh = (d: FbsStockDialogData): FbsStockDialogData => ({
  ...d, bindings: d.bindings.map((one) => ({ ...one })), products: d.products.map((one) => ({ ...one })),
})

/** Отложенный ответ: тест сам решает, когда он придёт. */
function deferred<T>() {
  let resolve!: (value: T) => void
  const promise = new Promise<T>((r) => { resolve = r })
  return { promise, resolve }
}

/** Подменная сессия: загрузка отдаёт заданные данные, действия — то, что скажет тест. */
function fakeSession(initial: FbsStockDialogData) {
  const putCalls: Array<{ marketplace: string; externalId: string; body: unknown }> = []
  const saveCalls: Array<Record<string, unknown>> = []
  const saveProductIds: string[][] = []
  let nextPut: (call: { marketplace: string; externalId: string; body: { wms_warehouse_id?: string; served?: boolean } }) => Promise<BindingOutcome> | BindingOutcome =
    () => ({ ok: true, data: fresh(initial) })
  let nextSave: (body: Record<string, unknown>) => Promise<SaveOutcome> | SaveOutcome = () => ({ kind: 'saved' })
  let rereadAnswer: () => FbsStockDialogData | null = () => fresh(initial)
  const session: StockDialogSession = {
    load: async () => initial,
    reread: async () => rereadAnswer(),
    putBinding: async (marketplace, externalId, body) => {
      putCalls.push({ marketplace, externalId, body })
      return nextPut({ marketplace, externalId, body })
    },
    saveRule: async (ids, byBinding) => {
      saveProductIds.push(ids)
      saveCalls.push(byBinding)
      return nextSave(byBinding)
    },
  }
  return {
    session, putCalls, saveCalls, saveProductIds,
    onPut: (fn: typeof nextPut) => { nextPut = fn },
    onSave: (fn: typeof nextSave) => { nextSave = fn },
    onReread: (fn: typeof rereadAnswer) => { rereadAnswer = fn },
  }
}

let root: Root | null = null
let host: HTMLDivElement | null = null
async function mount(element: React.ReactElement) {
  host = document.createElement('div')
  document.body.appendChild(host)
  root = createRoot(host)
  await act(async () => { root!.render(element) })
}
afterEach(async () => {
  if (root) await act(async () => { root!.unmount() })
  root = null
  host?.remove()
  host = null
  document.body.innerHTML = ''
})

const $ = <T extends HTMLElement = HTMLElement>(testId: string): T => {
  const el = document.querySelector<T>(`[data-testid="${testId}"]`)
  if (!el) throw new Error(`no element ${testId}`)
  return el
}
const maybe = (testId: string) => document.querySelector(`[data-testid="${testId}"]`)
const input = (testId: string) => $<HTMLInputElement>(testId)
async function type(testId: string, value: string) {
  const el = input(testId)
  const setter = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value')!.set!
  await act(async () => {
    setter.call(el, value)
    el.dispatchEvent(new Event('input', { bubbles: true }))
  })
}
async function click(testId: string) {
  await act(async () => { $(testId).click() })
}
async function select(testId: string, value: string) {
  const el = $<HTMLSelectElement>(testId)
  await act(async () => {
    el.value = value
    el.dispatchEvent(new Event('change', { bubbles: true }))
  })
}
async function pressEscape() {
  await act(async () => {
    $('fbs-stock-dialog').dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true }))
  })
}
const tick = () => act(async () => { await Promise.resolve() })

function renderContainer(fake: ReturnType<typeof fakeSession>, extra: Partial<Parameters<typeof FbsStockDialogContainer>[0]> = {}) {
  const onClose = vi.fn()
  const element = (
    <FbsStockDialogContainer token="t" sellerId="s" sellerName="ИП Тест" chosen={[{ id: 'p', name: 'Товар p', sku_code: 'P' }]}
      warehouses={WMS} canEditBindings onClose={onClose} onLoadError={() => {}} session={fake.session} {...extra} />
  )
  return { element, onClose }
}

describe('WMS-469 F2: открытие окна не меняет сохранённый лимит', () => {
  it('лимит 50 при свободных 30 остаётся 50 после эффектов; «Сохранить» без правок шлёт пустое тело', async () => {
    const onSave = vi.fn()
    await mount(<FbsStockDialog open sellerName="ИП Тест" products={[product({ 'b-wb': { free: 30, value: 50 } })]}
      bindings={[wb]} cabinets={data([wb], []).cabinets} wmsWarehouses={WMS} canEditBindings onClose={() => {}} onSave={onSave} />)
    expect(input('fbs-stock-units-b-wb').value).toBe('50')
    expect(maybe('fbs-stock-cap-note-b-wb')).toBeNull()
    await click('fbs-stock-save')
    expect(onSave).toHaveBeenCalledWith({})
  })

  it('включение передачи без ввода числа уносит прежние 50, а не обрезанные 30', async () => {
    const onSave = vi.fn()
    await mount(<FbsStockDialog open sellerName="ИП Тест" products={[product({ 'b-wb': { free: 30, value: 50, publish: false } })]}
      bindings={[wb]} cabinets={data([wb], []).cabinets} wmsWarehouses={WMS} canEditBindings onClose={() => {}} onSave={onSave} />)
    await click('fbs-stock-publish-b-wb')
    expect(input('fbs-stock-units-b-wb').value).toBe('50')
    await click('fbs-stock-save')
    expect(onSave).toHaveBeenCalledWith({ 'b-wb': { publish: true, mode: 'units', value: 50, units_configured: true } })
  })

  it('R12: новый ввод выше остатка режется с подписью — это и есть единственная обрезка при вводе', async () => {
    await mount(<FbsStockDialog open sellerName="ИП Тест" products={[product({ 'b-wb': { free: 30, value: 10 } })]}
      bindings={[wb]} cabinets={data([wb], []).cabinets} wmsWarehouses={WMS} canEditBindings onClose={() => {}} onSave={() => {}} />)
    await type('fbs-stock-units-b-wb', '80')
    expect(input('fbs-stock-units-b-wb').value).toBe('30')
    expect($('fbs-stock-cap-note-b-wb').textContent).toBe('товара «Товар p» всего 30 штук')
  })
})

describe('WMS-577 review P2-2: отрицательное «Доступно» (free=-3) не ломает сохранение', () => {
  it('ввод 5 при free=-3 даёт в поле 0, а не -3, и сохраняет 0', async () => {
    const onSave = vi.fn()
    await mount(<FbsStockDialog open sellerName="ИП Тест" products={[product({ 'b-wb': { free: -3, value: 0 } })]}
      bindings={[wb]} cabinets={data([wb], []).cabinets} wmsWarehouses={WMS} canEditBindings onClose={() => {}} onSave={onSave} />)
    await type('fbs-stock-units-b-wb', '5')
    expect(input('fbs-stock-units-b-wb').value).toBe('0')
    expect($('fbs-stock-cap-note-b-wb').textContent).toBe('товара «Товар p» всего 0 штук')
    await click('fbs-stock-save')
    expect(onSave).toHaveBeenCalledWith({ 'b-wb': { publish: true, mode: 'units', value: 0, units_configured: true } })
  })

  it('явный ноль при free=-3 тоже даёт 0, а не -3 (раньше падал и явный ноль)', async () => {
    const onSave = vi.fn()
    await mount(<FbsStockDialog open sellerName="ИП Тест" products={[product({ 'b-wb': { free: -3, value: 5 } })]}
      bindings={[wb]} cabinets={data([wb], []).cabinets} wmsWarehouses={WMS} canEditBindings onClose={() => {}} onSave={onSave} />)
    await type('fbs-stock-units-b-wb', '0')
    expect(input('fbs-stock-units-b-wb').value).toBe('0')
    await click('fbs-stock-save')
    expect(onSave).toHaveBeenCalledWith({ 'b-wb': { publish: true, mode: 'units', value: 0, units_configured: true } })
  })
})

describe('WMS-469 F6: время записи', () => {
  it('открытая форма добавления заперта, Escape не закрывает, второй PUT не начинается; ответ закрывает окно', async () => {
    const fake = fakeSession(data([wb], [product({ 'b-wb': { free: 100, value: 10 } })], true))
    const save = deferred<SaveOutcome>()
    fake.onSave(() => save.promise)
    const { element, onClose } = renderContainer(fake)
    await mount(element)
    await click('fbs-stock-add')
    expect(maybe('fbs-stock-picker')).not.toBeNull()
    await type('fbs-stock-units-b-wb', '12')
    await click('fbs-stock-save')
    // Запись идёт: всё заперто, включая форму добавления.
    expect(input('fbs-stock-units-b-wb').disabled).toBe(true)
    expect(input('fbs-stock-picker-seller').disabled).toBe(true)
    expect($<HTMLSelectElement>('fbs-stock-picker-ff').disabled).toBe(true)
    expect($<HTMLButtonElement>('fbs-stock-picker-cancel').disabled).toBe(true)
    await pressEscape()
    expect(onClose).not.toHaveBeenCalled()
    expect(maybe('fbs-stock-dialog')).not.toBeNull()
    // Выбор склада ФФ в форме во время записи не запускает добавление.
    await select('fbs-stock-picker-ff', B)
    expect(fake.putCalls).toHaveLength(0)
    // Ответ первого сохранения — окно закрывается с тем, что было отправлено.
    await act(async () => { save.resolve({ kind: 'saved' }) })
    expect(fake.saveCalls).toEqual([{ 'b-wb': { publish: true, mode: 'units', value: 12, units_configured: true } }])
    expect(onClose).toHaveBeenCalledTimes(1)
  })

  it('без записи Escape закрывает окно', async () => {
    const fake = fakeSession(data([wb], [product({ 'b-wb': { free: 100, value: 10 } })]))
    const { element, onClose } = renderContainer(fake)
    await mount(element)
    await pressEscape()
    expect(onClose).toHaveBeenCalledTimes(1)
  })
})

describe('WMS-469 F9: смена склада ФФ', () => {
  it('отказ смены (перечитано — прежний склад): лимит 50 и черновик не тронуты, сохранение — пустое', async () => {
    const initial = data([wb], [product({ 'b-wb': { free: 30, value: 50 } })])
    const fake = fakeSession(initial)
    fake.onPut(() => ({ ok: false, message: 'Ошибка 500', data: fresh(initial) }))
    const { element } = renderContainer(fake)
    await mount(element)
    await select('fbs-stock-bind-b-wb', B)
    await tick()
    expect($('fbs-stock-error').textContent).toBe('Ошибка 500')
    expect(input('fbs-stock-units-b-wb').value).toBe('50')
    expect(maybe('fbs-stock-cap-note-b-wb')).toBeNull()
    await click('fbs-stock-save')
    expect(fake.saveCalls).toEqual([{}])
  })

  it('ошибка уже в окне, затем успешная смена на склад с большим остатком: число и подпись не обрезаны', async () => {
    const initial = data([wb], [product({ 'b-wb': { free: 30, value: 50 } })])
    const fake = fakeSession(initial)
    // Первое действие падает и оставляет ошибку в окне.
    fake.onPut(() => ({ ok: false, message: 'Ошибка 500', data: fresh(initial) }))
    const { element } = renderContainer(fake)
    await mount(element)
    await select('fbs-stock-bind-b-wb', B)
    await tick()
    expect($('fbs-stock-error').textContent).toBe('Ошибка 500')
    // Второе — смена склада на B со свободными 100, ответ отложен: очистка
    // ошибки в начале запроса не должна ничего пересчитывать по складу A.
    const put = deferred<BindingOutcome>()
    fake.onPut(() => put.promise)
    await select('fbs-stock-bind-b-wb', B)
    expect(input('fbs-stock-units-b-wb').value).toBe('50')
    expect(maybe('fbs-stock-cap-note-b-wb')).toBeNull()
    const moved = data([{ ...wb, wmsWarehouseId: B, wmsWarehouseName: 'Склад B' }], [product({ 'b-wb': { free: 100, value: 50 } })])
    await act(async () => { put.resolve({ ok: true, data: moved }) })
    expect(input('fbs-stock-units-b-wb').value).toBe('50')
    expect(maybe('fbs-stock-cap-note-b-wb')).toBeNull()
    expect($<HTMLSelectElement>('fbs-stock-bind-b-wb').value).toBe(B)
  })

  it('успешная смена на склад с меньшим остатком: число встаёт на максимум с подписью и уходит при сохранении', async () => {
    const initial = data([wb], [product({ 'b-wb': { free: 30, value: 50 } })])
    const fake = fakeSession(initial)
    const moved = data([{ ...wb, wmsWarehouseId: B, wmsWarehouseName: 'Склад B' }], [product({ 'b-wb': { free: 20, value: 50 } })])
    fake.onPut(() => ({ ok: true, data: moved }))
    const { element } = renderContainer(fake)
    await mount(element)
    await select('fbs-stock-bind-b-wb', B)
    await tick()
    expect(fake.putCalls[0]).toMatchObject({ externalId: '501001', body: { wms_warehouse_id: B } })
    expect(input('fbs-stock-units-b-wb').value).toBe('20')
    expect($('fbs-stock-cap-note-b-wb').textContent).toBe('товара «Товар p» всего 20 штук')
    await click('fbs-stock-save')
    expect(fake.saveCalls).toEqual([{ 'b-wb': { publish: true, mode: 'units', value: 20, units_configured: true } }])
  })
})

describe('WMS-469 F5: перечитывание после сбоя не удалось', () => {
  it('следующее действие сначала перечитывает и берёт склад из свежего состояния', async () => {
    const initial = data([wb], [product({ 'b-wb': { free: 30, value: 50 } })])
    const fake = fakeSession(initial)
    // Сервер принял A→B, ответ потерян, перечитать не удалось.
    fake.onPut(() => ({ ok: false, message: 'Failed to fetch', data: null }))
    const { element } = renderContainer(fake)
    await mount(element)
    await select('fbs-stock-bind-b-wb', B)
    await tick()
    expect($<HTMLSelectElement>('fbs-stock-bind-b-wb').value).toBe(A)
    // Связь восстановилась: перечитывание показывает B.
    const moved = data([{ ...wb, wmsWarehouseId: B, wmsWarehouseName: 'Склад B' }], [product({ 'b-wb': { free: 100, value: 50 } })])
    fake.onReread(() => moved)
    fake.onPut(() => ({ ok: true, data: moved }))
    await select('fbs-stock-bind-b-wb', B)
    await tick()
    // Окно сначала перечитало фактический B и уже его отправило в повторном действии.
    expect(fake.putCalls[1]).toMatchObject({ body: { wms_warehouse_id: B } })
    expect(fake.putCalls[1]!.body).not.toHaveProperty('served')
    expect($<HTMLSelectElement>('fbs-stock-bind-b-wb').value).toBe(B)
  })

  it('если перечитать снова не удалось — действие не выполняется, причина в окне', async () => {
    const initial = data([wb], [product({ 'b-wb': { free: 30, value: 50 } })])
    const fake = fakeSession(initial)
    fake.onPut(() => ({ ok: false, message: 'Failed to fetch', data: null }))
    const { element } = renderContainer(fake)
    await mount(element)
    await select('fbs-stock-bind-b-wb', B)
    await tick()
    fake.onReread(() => null)
    await select('fbs-stock-bind-b-wb', B)
    await tick()
    expect(fake.putCalls).toHaveLength(1)
    expect($('fbs-stock-error').textContent).toContain('не удалось перечитать')
  })
})

describe('WMS-670: точная область товар × склад', () => {
  it('C1/C2: served=false не скрывает строку, а сохранение WB не трогает binding, Ozon и другие товары', async () => {
    const initial = data(
      [{ ...wb, served: false }, ozon],
      [product({ 'b-wb': { free: 100, value: 50 }, 'b-ozon': { free: 100, value: 40 } })],
    )
    const fake = fakeSession(initial)
    const { element } = renderContainer(fake)
    await mount(element)

    expect(maybe('fbs-stock-served-b-wb')).toBeNull()
    expect(maybe('fbs-stock-row-b-wb')).not.toBeNull()
    expect(input('fbs-stock-units-b-ozon').value).toBe('40')

    await type('fbs-stock-units-b-wb', '30')
    await click('fbs-stock-save')

    expect(fake.saveProductIds).toEqual([['p']])
    expect(fake.saveCalls).toEqual([{
      'b-wb': { publish: true, mode: 'units', value: 30, units_configured: true },
    }])
    expect(fake.putCalls).toHaveLength(0)
  })
})

describe('WMS-490 D6: встроенный режим (вкладка «Задать остаток» карточки товара)', () => {
  it('то же тело и те же кнопки, без рамки диалога; кнопки порталятся в заданный узел', async () => {
    const fake = fakeSession(data([wb], [product({ 'b-wb': { free: 100, value: 10 } })]))
    const footerHost = document.createElement('div')
    document.body.appendChild(footerHost)
    const { element } = renderContainer(fake, { embedded: true, footerSlotEl: footerHost })
    await mount(element)
    // Тело — то же, что у окна: заголовок товара и блок склада есть, а рамки
    // диалога (AppDialog) нет вовсе.
    expect(maybe('fbs-stock-dialog')).toBeNull()
    expect($('fbs-stock-head').textContent).toBe('Товар p · P')
    expect(maybe('fbs-stock-block-b-wb')).not.toBeNull()
    // Кнопки — не в теле, а в заданном узле нижней панели карточки.
    expect(host!.querySelector('[data-testid="fbs-stock-save"]')).toBeNull()
    expect(footerHost.querySelector('[data-testid="fbs-stock-save"]')).not.toBeNull()
    expect(footerHost.querySelector('[data-testid="fbs-stock-cancel"]')).not.toBeNull()
    footerHost.remove()
  })

  it('«Сохранить» зовёт тот же saveRule и закрывает так же, как окно', async () => {
    const fake = fakeSession(data([wb], [product({ 'b-wb': { free: 100, value: 10 } })]))
    const footerHost = document.createElement('div')
    document.body.appendChild(footerHost)
    const { element, onClose } = renderContainer(fake, { embedded: true, footerSlotEl: footerHost })
    await mount(element)
    const saveButton = footerHost.querySelector<HTMLButtonElement>('[data-testid="fbs-stock-save"]')!
    await act(async () => { saveButton.click() })
    expect(fake.saveCalls).toEqual([{}])
    expect(onClose).toHaveBeenCalledTimes(1)
    footerHost.remove()
  })

  it('«Отмена» закрывает без сохранения, как в окне', async () => {
    const fake = fakeSession(data([wb], [product({ 'b-wb': { free: 100, value: 10 } })]))
    const footerHost = document.createElement('div')
    document.body.appendChild(footerHost)
    const { element, onClose } = renderContainer(fake, { embedded: true, footerSlotEl: footerHost })
    await mount(element)
    const cancelButton = footerHost.querySelector<HTMLButtonElement>('[data-testid="fbs-stock-cancel"]')!
    await act(async () => { cancelButton.click() })
    expect(fake.saveCalls).toHaveLength(0)
    expect(onClose).toHaveBeenCalledTimes(1)
    footerHost.remove()
  })

  it('провал загрузки не закрывает встроенный контейнер (R16) — в отличие от окна', async () => {
    const failingSession: StockDialogSession = {
      load: async () => { throw new Error('Сеть недоступна') },
      reread: async () => null,
      putBinding: async () => ({ ok: false, message: 'unused', data: null }),
      saveRule: async () => ({ kind: 'saved' }),
    }
    const onClose = vi.fn()
    const onLoadError = vi.fn()
    await mount(
      <FbsStockDialogContainer
        token="t" sellerId="s" sellerName="ИП Тест" chosen={[{ id: 'p', name: 'Товар p', sku_code: 'P' }]}
        warehouses={WMS} canEditBindings onClose={onClose} onLoadError={onLoadError}
        session={failingSession} embedded footerSlotEl={null}
      />,
    )
    await tick()
    expect(onLoadError).toHaveBeenCalledWith('Сеть недоступна')
    expect(onClose).not.toHaveBeenCalled()
  })

  it('окно (не embedded) на том же провале закрывается, как раньше', async () => {
    const failingSession: StockDialogSession = {
      load: async () => { throw new Error('Сеть недоступна') },
      reread: async () => null,
      putBinding: async () => ({ ok: false, message: 'unused', data: null }),
      saveRule: async () => ({ kind: 'saved' }),
    }
    const onClose = vi.fn()
    const onLoadError = vi.fn()
    await mount(
      <FbsStockDialogContainer
        token="t" sellerId="s" sellerName="ИП Тест" chosen={[{ id: 'p', name: 'Товар p', sku_code: 'P' }]}
        warehouses={WMS} canEditBindings onClose={onClose} onLoadError={onLoadError}
        session={failingSession}
      />,
    )
    await tick()
    expect(onLoadError).toHaveBeenCalledWith('Сеть недоступна')
    expect(onClose).toHaveBeenCalledTimes(1)
  })

  it('onBusyChange сообщает карточке о записи и её завершении', async () => {
    const fake = fakeSession(data([wb], [product({ 'b-wb': { free: 100, value: 10 } })]))
    const save = deferred<SaveOutcome>()
    fake.onSave(() => save.promise)
    const footerHost = document.createElement('div')
    document.body.appendChild(footerHost)
    const onBusyChange = vi.fn()
    const { element } = renderContainer(fake, { embedded: true, footerSlotEl: footerHost, onBusyChange })
    await mount(element)
    onBusyChange.mockClear()
    const saveButton = footerHost.querySelector<HTMLButtonElement>('[data-testid="fbs-stock-save"]')!
    await act(async () => { saveButton.click() })
    expect(onBusyChange).toHaveBeenCalledWith(true)
    await act(async () => { save.resolve({ kind: 'saved' }) })
    expect(onBusyChange).toHaveBeenLastCalledWith(false)
    footerHost.remove()
  })

})
