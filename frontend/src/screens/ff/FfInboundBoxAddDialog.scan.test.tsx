// @vitest-environment jsdom
import { act } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from 'vitest'
import type { WbProductCatalogRow } from '../../types/wbProductCatalog'
import { PRODUCT_SCAN_AMBIGUOUS_MESSAGE } from '../../utils/productScanResolver'
import { FfInboundBoxAddDialog } from './FfInboundBoxAddDialog'

// F/S-INB-06 «Наполнение короба / грузоместа» в настоящем React-рендере: оба входа
// (клавиатурный сканер и ручной Enter), классификатор ЧЗ раньше товара, запрос к
// серверу. Фикстуры — раздел 9 docs/requirements/WMS-536.md.

beforeAll(() => {
  ;(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true
  // jsdom не умеет прокрутку; диалог прокручивает к отсканированной строке.
  Element.prototype.scrollIntoView = () => undefined
})

const WB_P = '4601234567893'
const WB_A = '4601234567886'
const OZN = 'OZN-987654'
const CYR = 'ФА_МОД8-4а/083/42'
const DUP = 'DUP-536'
const BOX_PROD = 'BOX-PROD-536'
const GS = '\x1d'
const KIZ_GS = `010460123456789321SERIAL536${GS}91ABCD${GS}92SIGNATURE536`
const KIZ_NO_GS = '010460123456789321SERIAL53691ABCD92SIGNATURE536'

function row(id: string, fields: Partial<WbProductCatalogRow> = {}): WbProductCatalogRow {
  return {
    id,
    name: `Товар ${id}`,
    sku_code: `SKU-${id}`,
    wb_nm_id: null,
    wb_vendor_code: null,
    wb_subject_name: null,
    wb_primary_image_url: null,
    wb_barcodes: [],
    wb_primary_barcode: null,
    wb_size: null,
    wb_color: null,
    ...fields,
  }
}

const P = row('P', {
  sku_code: 'AbC-42',
  wb_primary_barcode: WB_P,
  wb_barcodes: [WB_P, WB_A, BOX_PROD],
  marketplace_bindings: [
    { marketplace: 'ozon', external_sku: '987654', external_offer_id: 'offer-536', external_barcodes: [OZN] },
  ],
})
const Q = row('Q', { marketplace_bindings: [{ marketplace: 'ozon', external_barcodes: [DUP] }] })
const D = row('D', { sku_code: DUP })
const LAT = row('LAT', { sku_code: 'Chin-56005' })
const CYRP = row('CYRP', { sku_code: CYR })
const N13 = row('N13', { wb_primary_barcode: '4601234567899' })
const N14 = row('N14', { wb_barcodes: ['04601234567899'] })
/** Есть в каталоге селлера, но не в документе (пустая приёмка ФФ, WMS-473). */
const OUTSIDE = row('OUT', { sku_code: 'ЖК-ЛЁН/7' })

const DOCUMENT = [P, Q, D, LAT, CYRP, N13, N14]
const CATALOG = new Map([...DOCUMENT, OUTSIDE].map((r) => [r.id, r]))
const LINES = DOCUMENT.map((r) => ({
  id: `line-${r.id}`,
  product_id: r.id,
  sku_code: r.sku_code,
  product_name: r.name,
  expected_qty: 5,
}))

type ScanBody = { barcode: string; product_id?: string }

let root: Root | null = null
let host: HTMLDivElement | null = null
let requests: ScanBody[] = []
type MarkingScan = (code: string, lineId: string | null) => Promise<void>
let onMarkingScan = vi.fn<MarkingScan>(async () => undefined)
let onUpdated = vi.fn(async () => undefined)

beforeEach(() => {
  requests = []
  onMarkingScan = vi.fn<MarkingScan>(async () => undefined)
  onUpdated = vi.fn(async () => undefined)
  // Сервер отвечает строкой короба того товара, который пришёл подсказкой, а без
  // подсказки — товаром каталога, как это делает серверная ветка (WMS-473).
  vi.stubGlobal('fetch', vi.fn(async (_url: string, init?: RequestInit) => {
    const body = JSON.parse(String(init?.body)) as ScanBody
    requests.push(body)
    const productId = body.product_id ?? 'OUT'
    return new Response(
      JSON.stringify({ id: `box-line-${productId}`, product_id: productId, sku_code: productId, product_name: productId, quantity: 1 }),
      { status: 200 },
    )
  }))
})

afterEach(() => {
  act(() => root?.unmount())
  host?.remove()
  root = null
  host = null
  document.body.innerHTML = ''
  vi.unstubAllGlobals()
})

function mount() {
  host = document.createElement('div')
  document.body.appendChild(host)
  root = createRoot(host)
  act(() => {
    root!.render(
      <FfInboundBoxAddDialog
        open
        onClose={() => undefined}
        requestId="r1"
        boxId="box-1"
        boxLabel="Короб № 1"
        readOnly={false}
        token="t"
        requestLines={LINES}
        boxLines={[]}
        catalogById={CATALOG}
        onUpdated={onUpdated}
        onMarkingScan={onMarkingScan}
      />,
    )
  })
}

async function flush() {
  for (let i = 0; i < 6; i += 1) {
    await act(async () => {
      await new Promise((resolve) => setTimeout(resolve, 0))
    })
  }
}

// Физическая клавиша для символа в русской раскладке (ЙЦУКЕН).
const RU_KEYS: Record<string, string> = {
  й: 'KeyQ', ц: 'KeyW', у: 'KeyE', к: 'KeyR', е: 'KeyT', н: 'KeyY', г: 'KeyU', ш: 'KeyI', щ: 'KeyO',
  з: 'KeyP', х: 'BracketLeft', ъ: 'BracketRight', ф: 'KeyA', ы: 'KeyS', в: 'KeyD', а: 'KeyF', п: 'KeyG',
  р: 'KeyH', о: 'KeyJ', л: 'KeyK', д: 'KeyL', ж: 'Semicolon', э: 'Quote', я: 'KeyZ', ч: 'KeyX', с: 'KeyC',
  м: 'KeyV', и: 'KeyB', т: 'KeyN', ь: 'KeyM', б: 'Comma', ю: 'Period', ё: 'Backquote',
}

function keyEvent(ch: string): KeyboardEventInit {
  if (ch === GS) return { key: ']', code: 'BracketRight', ctrlKey: true }
  const lower = ch.toLowerCase()
  const shiftKey = ch !== lower
  if (RU_KEYS[lower]) return { key: ch, code: RU_KEYS[lower], shiftKey }
  if (/[a-z]/.test(lower)) return { key: ch, code: `Key${lower.toUpperCase()}`, shiftKey }
  if (/[0-9]/.test(ch)) return { key: ch, code: `Digit${ch}` }
  const symbols: Record<string, KeyboardEventInit> = {
    '-': { key: '-', code: 'Minus' },
    _: { key: '_', code: 'Minus', shiftKey: true },
    '/': { key: '/', code: 'Slash' },
  }
  return symbols[ch] ?? { key: ch, code: '' }
}

/** Быстрая пачка клавиатурного сканера с Enter на конце — как её видит документ. */
async function wedge(text: string) {
  const target = document.activeElement ?? document.body
  act(() => {
    for (const ch of text) {
      target.dispatchEvent(new KeyboardEvent('keydown', { ...keyEvent(ch), bubbles: true, cancelable: true }))
    }
    target.dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter', code: 'Enter', bubbles: true, cancelable: true }))
  })
  await flush()
}

function scanInput(): HTMLInputElement {
  return document.querySelector<HTMLInputElement>('[data-testid="ff-inbound-box-add-scan-input"]')!
}

/** Ручной ввод в поле и Enter: раскладка не исправляется. */
async function manual(text: string) {
  const input = scanInput()
  const setter = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value')!.set!
  act(() => {
    setter.call(input, text)
    input.dispatchEvent(new Event('input', { bubbles: true }))
  })
  // Медленный ввод человека: сканер пропускает Enter полю.
  await new Promise((resolve) => setTimeout(resolve, 1100))
  act(() => {
    input.dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter', code: 'Enter', bubbles: true, cancelable: true }))
  })
  await flush()
}

function errorText(): string | null {
  return document.querySelector('[data-testid="ff-inbound-box-add-error"]')?.textContent ?? null
}

describe('F/S-INB-06: товар в короб через единый поиск', () => {
  it.each([
    ['основной WB', WB_P, WB_P, 'P'],
    ['дополнительный WB', WB_A, WB_A, 'P'],
    ['Ozon-штрихкод', OZN, OZN, 'P'],
    ['SKU в другом регистре', 'aBc-42', 'aBc-42', 'P'],
    ['кириллический SKU — исходными символами', CYR, CYR, 'CYRP'],
    ['SKU в русской раскладке — исправленным после промаха исходного', 'Сршт-56005', 'Chin-56005', 'LAT'],
    ['код, совпавший с коробом: короб уже выбран, это товар', BOX_PROD, BOX_PROD, 'P'],
    ['13 знаков', '4601234567899', '4601234567899', 'N13'],
    ['14 знаков с ведущим нулём', '04601234567899', '04601234567899', 'N14'],
  ])('сканер: %s', async (_label, typed, barcode, productId) => {
    mount()
    await wedge(typed)
    expect(requests).toEqual([{ barcode, product_id: productId }])
    expect(errorText()).toBeNull()
  })

  it('код двух карточек документа: серверу не уходит ничего, понятная ошибка', async () => {
    mount()
    await wedge(DUP)
    expect(requests).toEqual([])
    expect(errorText()).toBe(PRODUCT_SCAN_AMBIGUOUS_MESSAGE)
    // Следующий скан работает как обычно.
    await wedge(WB_A)
    expect(requests).toEqual([{ barcode: WB_A, product_id: 'P' }])
  })

  it('ручной Enter в русской раскладке не исправляется: уходит как набран, без подсказки', async () => {
    mount()
    await manual('Сршт-56005')
    expect(requests).toEqual([{ barcode: 'Сршт-56005' }])
  })

  it('ручной Enter с Ozon-штрихкодом находит товар документа', async () => {
    mount()
    await manual(OZN)
    expect(requests).toEqual([{ barcode: OZN, product_id: 'P' }])
  })

  it('товар каталога вне документа: подсказки нет, кириллический артикул уходит исходными символами', async () => {
    mount()
    await wedge(OUTSIDE.sku_code)
    expect(requests).toEqual([{ barcode: OUTSIDE.sku_code }])
    expect(onUpdated).toHaveBeenCalled()
  })

  it.each([
    ['external_sku', '987654'],
    ['external_offer_id', 'offer-536'],
  ])('%s не становится штрихкодом: уходит серверу без подсказки', async (_label, code) => {
    mount()
    await wedge(code)
    expect(requests).toEqual([{ barcode: code }])
  })
})

describe('F/S-INB-06: ЧЗ классифицируется раньше товара (R8, R9, R-27)', () => {
  it('КИЗ с GS и без GS уходит в ЧЗ, товарный запрос не отправляется', async () => {
    mount()
    await wedge(KIZ_GS)
    await wedge(KIZ_NO_GS)
    expect(requests).toEqual([])
    expect(onMarkingScan.mock.calls).toEqual([
      [KIZ_GS, null],
      [KIZ_NO_GS, null],
    ])
  })

  it('товар → КИЗ: КИЗ привязывается к строке только что отсканированного товара', async () => {
    mount()
    await wedge(WB_A)
    await wedge(KIZ_GS)
    expect(requests).toEqual([{ barcode: WB_A, product_id: 'P' }])
    expect(onMarkingScan).toHaveBeenCalledWith(KIZ_GS, 'line-P')
  })

  it('неоднозначный товар сбрасывает товар для КИЗ, как любой неуспешный скан товара', async () => {
    mount()
    await wedge(WB_A)
    await wedge(DUP)
    await wedge(KIZ_GS)
    expect(onMarkingScan).toHaveBeenCalledWith(KIZ_GS, null)
  })
})
