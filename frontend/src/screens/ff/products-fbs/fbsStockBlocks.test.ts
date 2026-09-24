import { describe, expect, it } from 'vitest'
import {
  addableWarehouses,
  blockTotals,
  buildStockBindings,
  capNoteText,
  clampUnits,
  draftFromState,
  initialDrafts,
  rowCalc,
  ruleBodyFromDrafts,
  snapPercent,
  toggleByPercent,
  toProductBindingState,
  unitsCap,
  visibleStockBindings,
  type ApiBindingRule,
  type BlockDraft,
  type StockBinding,
  type StockDialogProduct,
} from './fbsStockBlocks'
import type { CabinetList, SavedWarehouseBinding } from './fbsSellerWarehouseRows'

// Арифметика окна «Остаток для FBS» (WMS-469) без React и сети: то, что
// оператор видит в поле «шт», на ползунке и в подписи под полем.

const YARTSEVO = '441c8654-b6c2-48fe-950f-65acbc921118'

const wb: StockBinding = {
  id: 'b-wb', marketplace: 'wb', externalId: '501001', name: 'E2E Seller Warehouse',
  wmsWarehouseId: YARTSEVO, wmsWarehouseName: 'Ярцево', served: true, editable: true,
}
const ozon: StockBinding = {
  id: 'b-ozon', marketplace: 'ozon', externalId: '1020005029603630', name: 'Хоругвино',
  wmsWarehouseId: YARTSEVO, wmsWarehouseName: 'Ярцево', served: true, editable: true,
}

function product(
  id: string,
  name: string,
  free: Record<string, number>,
  extra: Partial<ApiBindingRule> = {},
): StockDialogProduct {
  return {
    id, name, sku: id.toUpperCase(), size: null,
    byBinding: Object.fromEntries(Object.entries(free).map(([bindingId, freeStock]) => [
      bindingId,
      toProductBindingState({
        publish: false, mode: 'percent', value: 0, marketplace: 'wb', external_warehouse_id: '501001',
        wms_warehouse_id: YARTSEVO, served: true, applicable: true, on_hand: freeStock + 2, reserved: 2,
        free_stock: freeStock, published_now: 0, ...extra,
      }),
    ])),
  }
}

const fifty = product('p50', 'Платье 50-52', { 'b-wb': 50 })
const thirty = product('p30', 'Платье 54-56', { 'b-wb': 30 })
const thirtyLong = product('p30-long', 'Костюм с очень длинным названием товара для проверки переноса', { 'b-wb': 30 })

describe('WMS-469 R10 процент → число', () => {
  it('C10: 50 % от 50 и 30 — это 25 + 15 = 40, каждому товару отдельно с округлением вниз', () => {
    const draft: BlockDraft = { publish: true, byPercent: true, percent: 50, units: 0 }
    expect(rowCalc(wb, draft, [fifty, thirty])).toEqual({ free: 80, ship: 40, pct: 50, fieldValue: 40 })
  })

  it('округляет вниз каждый товар, а не сумму: 75 % от 50 и 30 = 37 + 22 = 59, не floor(60)', () => {
    const draft: BlockDraft = { publish: true, byPercent: true, percent: 75, units: 0 }
    expect(rowCalc(wb, draft, [fifty, thirty]).ship).toBe(59)
  })

  it('шаг ползунка — 5 процентных пунктов, границы 0 и 100', () => {
    expect(snapPercent(73)).toBe(75)
    expect(snapPercent(72)).toBe(70)
    expect(snapPercent(-5)).toBe(0)
    expect(snapPercent(140)).toBe(100)
  })
})

describe('WMS-469 R11 число → процент', () => {
  it('C11: 30 штук на товары с 50 и 30 — индикатор 75 % (60 из 80), в поле остаётся 30', () => {
    const draft: BlockDraft = { publish: true, byPercent: false, percent: 0, units: 30 }
    expect(rowCalc(wb, draft, [fifty, thirty])).toEqual({ free: 80, ship: 60, pct: 75, fieldValue: 30 })
  })

  it('число — одинаковый потолок каждому товару, а не сумма на выделение', () => {
    const draft: BlockDraft = { publish: true, byPercent: false, percent: 0, units: 20 }
    // 20 + 20 = 40 из 80.
    expect(rowCalc(wb, draft, [fifty, thirty]).ship).toBe(40)
  })

  it('без свободного остатка индикатор показывает 0 %, а не делит на ноль', () => {
    const empty = product('p0', 'Юбка', { 'b-wb': 0 })
    const draft: BlockDraft = { publish: true, byPercent: false, percent: 0, units: 5 }
    expect(rowCalc(wb, draft, [empty]).pct).toBe(0)
  })
})

describe('WMS-469 R12 обрезка ручного числа без блокировки', () => {
  it('C7: один товар со свободными 30 — ввод 50 даёт 30 и подпись с названием', () => {
    const { units, limitedBy } = clampUnits(wb, 50, [thirty])
    expect(units).toBe(30)
    expect(limitedBy).toEqual({ free: 30, product: thirty })
    expect(capNoteText(limitedBy!)).toBe('товара «Платье 54-56» всего 30 штук')
  })

  it('C8: несколько товаров — потолок по самому малому, подпись называет именно его', () => {
    const { units, limitedBy } = clampUnits(wb, 50, [fifty, thirty])
    expect(units).toBe(30)
    expect(limitedBy?.product.id).toBe('p30')
  })

  it('C9 / D3: при равных минимумах называется первый товар в порядке выбранных строк', () => {
    expect(unitsCap(wb, [thirtyLong, thirty]).product.id).toBe('p30-long')
    expect(unitsCap(wb, [thirty, thirtyLong]).product.id).toBe('p30')
  })

  it('число в пределах остатка принимается как есть, без подписи', () => {
    expect(clampUnits(wb, 25, [fifty, thirty])).toEqual({ units: 25, limitedBy: null })
  })

  it('склоняет «штук» по-русски', () => {
    expect(capNoteText({ free: 1, product: { name: 'А' } })).toBe('товара «А» всего 1 штука')
    expect(capNoteText({ free: 3, product: { name: 'А' } })).toBe('товара «А» всего 3 штуки')
    expect(capNoteText({ free: 11, product: { name: 'А' } })).toBe('товара «А» всего 11 штук')
    // Разделитель тысяч — как у toLocaleString('ru-RU') (узкий неразрывный пробел).
    expect(capNoteText({ free: 1250, product: { name: 'А' } })).toBe(`товара «А» всего ${(1250).toLocaleString('ru-RU')} штук`)
  })
})

describe('WMS-469 R9 галка «процентом» — одно значение в двух представлениях', () => {
  it('число → процент: берёт текущую долю и ставит на шаг ползунка', () => {
    const draft: BlockDraft = { publish: true, byPercent: false, percent: 0, units: 30 }
    expect(toggleByPercent(wb, draft, true, [fifty, thirty])).toMatchObject({ byPercent: true, percent: 75 })
  })

  it('WMS-483: процент → число оставляет незаданный поштучный лимит пустым', () => {
    const draft: BlockDraft = { publish: true, byPercent: true, percent: 50, units: null }
    expect(toggleByPercent(wb, draft, false, [fifty])).toMatchObject({ byPercent: false, units: null })
  })

  it('процент → число не создаёт новый лимит и для нескольких товаров', () => {
    const draft: BlockDraft = { publish: true, byPercent: true, percent: 100, units: null }
    expect(toggleByPercent(wb, draft, false, [fifty, thirty])).toMatchObject({ byPercent: false, units: null })
  })
})

describe('WMS-469 черновики и суммы блока', () => {
  it('черновик берётся из сохранённого правила: units → ручной режим, percent → процентный', () => {
    expect(draftFromState({ publish: true, mode: 'units', value: 30, unitsConfigured: true, applicable: true, onHand: 50, reserved: 0, freeStock: 50 }))
      .toEqual({ publish: true, byPercent: false, percent: 0, units: 30 })
    expect(draftFromState({ publish: false, mode: 'percent', value: 40, unitsConfigured: false, applicable: true, onHand: 50, reserved: 0, freeStock: 50 }))
      .toEqual({ publish: false, byPercent: true, percent: 40, units: null })
    expect(draftFromState({ publish: true, mode: 'units', value: 0, unitsConfigured: false, applicable: true, onHand: 50, reserved: 0, freeStock: 50 }))
      .toEqual({ publish: true, byPercent: false, percent: 0, units: null })
    expect(draftFromState(undefined)).toEqual({ publish: false, byPercent: true, percent: 0, units: null })
  })

  it('при нескольких товарах окно начинает с правила первого выбранного', () => {
    const first = product('a', 'А', { 'b-wb': 10 }, { publish: true, mode: 'units', value: 7 })
    const second = product('b', 'Б', { 'b-wb': 10 }, { publish: false, mode: 'percent', value: 90 })
    expect(initialDrafts([wb], [first, second])).toEqual({ 'b-wb': { publish: true, byPercent: false, percent: 0, units: 7 } })
  })

  it('суммы блока складываются только по выбранным товарам на этом складе ФФ', () => {
    expect(blockTotals(wb, [fifty, thirty])).toEqual({ onHand: 84, reserved: 4, free: 80 })
    // Про эту привязку у товара записи нет — в суммы он не входит.
    expect(blockTotals(ozon, [fifty])).toEqual({ onHand: 0, reserved: 0, free: 0 })
  })
})

describe('WMS-469 R7 тело сохранения', () => {
  it('отправляет только видимые блоки, с которых принимаем заказы; режим — ровно один', () => {
    const notServed: StockBinding = { ...ozon, served: false }
    const drafts = {
      'b-wb': { publish: true, byPercent: false, percent: 0, units: 30 },
      'b-ozon': { publish: true, byPercent: true, percent: 100, units: 0 },
    }
    expect(ruleBodyFromDrafts([wb, notServed], drafts)).toEqual({
      'b-wb': { publish: true, mode: 'units', value: 30, units_configured: true },
    })
    expect(ruleBodyFromDrafts([wb, ozon], drafts)).toEqual({
      'b-wb': { publish: true, mode: 'units', value: 30, units_configured: true },
      'b-ozon': { publish: true, mode: 'percent', value: 100, units_configured: false },
    })
  })

  it('F4 / R8, R24: уходят только переданные (изменённые) блоки — нетронутый Ozon соседних товаров не задевается', () => {
    const drafts = {
      'b-wb': { publish: true, byPercent: false, percent: 0, units: 30 },
      'b-ozon': { publish: false, byPercent: true, percent: 0, units: 0 },
    }
    // Оператор менял только WB: Ozon в теле отсутствует, сервер его не трогает.
    const touched = [wb, ozon].filter((one) => one.id === 'b-wb')
    expect(ruleBodyFromDrafts(touched, drafts)).toEqual({ 'b-wb': { publish: true, mode: 'units', value: 30, units_configured: true } })
    // Ничего не менял — тело пустое, и такой набор отправлять нельзя.
    expect(ruleBodyFromDrafts([], drafts)).toEqual({})
  })

  it('WMS-483: пустой лимит и явный 0 уходят как разные состояния', () => {
    expect(ruleBodyFromDrafts([wb], { 'b-wb': { publish: true, byPercent: false, percent: 0, units: null } }))
      .toEqual({ 'b-wb': { publish: true, mode: 'units', value: 0, units_configured: false } })
    expect(ruleBodyFromDrafts([wb], { 'b-wb': { publish: true, byPercent: false, percent: 0, units: 0 } }))
      .toEqual({ 'b-wb': { publish: true, mode: 'units', value: 0, units_configured: true } })
  })

  it('R13: WB 100 % и Ozon 100 % вместе уходят без потолка на сумму', () => {
    const drafts = {
      'b-wb': { publish: true, byPercent: true, percent: 100, units: 0 },
      'b-ozon': { publish: true, byPercent: true, percent: 100, units: 0 },
    }
    expect(Object.values(ruleBodyFromDrafts([wb, ozon], drafts)).map((one) => one.value)).toEqual([100, 100])
  })
})

// Названия складов — только из живого кабинета (WMS-457); чужой склад со
// снятым приёмом заказов не показывается (WMS-468); Ozon — только товару с
// карточкой Ozon (WMS-454).
const wbCabinet: CabinetList = {
  received: true,
  rows: [
    { wb_warehouse_id: 501001, name: 'E2E Seller Warehouse', wms_warehouse_id: YARTSEVO, served: true, marketplace: 'wb' },
    { wb_warehouse_id: 501002, name: 'Второй склад WB', wms_warehouse_id: null, served: false, marketplace: 'wb' },
  ],
}
const ozonCabinet: CabinetList = {
  received: true,
  rows: [{ wb_warehouse_id: 1020005029603630, name: 'Хоругвино', wms_warehouse_id: YARTSEVO, served: true, marketplace: 'ozon' }],
}
const saved: SavedWarehouseBinding[] = [
  { id: 'b-wb', wb_warehouse_id: 501001, wms_warehouse_id: YARTSEVO, wms_warehouse_name: 'Ярцево', is_active: true, served: true, marketplace: 'wb', editable: true },
  { id: 'b-gone', wb_warehouse_id: 501999, wms_warehouse_id: YARTSEVO, is_active: true, served: false, marketplace: 'wb' },
  { id: 'b-old', wb_warehouse_id: 501998, wms_warehouse_id: YARTSEVO, is_active: false, served: false, marketplace: 'wb' },
  { id: 'b-ozon', wb_warehouse_id: 1020005029603630, external_warehouse_id: '1020005029603630', wms_warehouse_id: YARTSEVO, is_active: true, served: true, marketplace: 'ozon', editable: false },
]

describe('WMS-469 R19 связки с названиями из кабинетов', () => {
  it('называет по кабинету, номерует остальные с причиной, неактивные не показывает', () => {
    const bindings = buildStockBindings({ wb: wbCabinet, ozon: { received: false } }, saved)
    expect(bindings.map((one) => [one.id, one.name, one.nameIssue, one.served, one.editable])).toEqual([
      ['b-wb', 'E2E Seller Warehouse', undefined, true, true],
      ['b-gone', '№ 501999', 'not_in_cabinet', false, true],
      ['b-ozon', '№ 1020005029603630', 'list_unavailable', true, false],
    ])
    expect(bindings[0]).toMatchObject({ marketplace: 'wb', externalId: '501001', wmsWarehouseId: YARTSEVO, wmsWarehouseName: 'Ярцево' })
  })

  it('Ozon-склад берёт имя из справочника Ozon по строковому external_warehouse_id', () => {
    const bindings = buildStockBindings({ wb: wbCabinet, ozon: ozonCabinet }, saved)
    const ozonBinding = bindings.find((one) => one.id === 'b-ozon')
    expect(ozonBinding?.name).toBe('Хоругвино')
    expect(ozonBinding?.nameIssue).toBeUndefined()
  })

  it('без полученного списка WB все сохранённые WB-связки подписаны номером', () => {
    const bindings = buildStockBindings({ wb: { received: false }, ozon: { received: false } }, saved)
    expect(bindings.map((one) => [one.name, one.nameIssue])).toEqual([
      ['№ 501001', 'list_unavailable'], ['№ 501999', 'list_unavailable'], ['№ 1020005029603630', 'list_unavailable'],
    ])
  })

  it('C29: склада нет в кабинете и заказы с него не принимаем — блока нет и в расчёт он не входит', () => {
    const bindings = buildStockBindings({ wb: wbCabinet, ozon: { received: false } }, saved)
    const wbOnly = product('p', 'Товар', { 'b-wb': 10, 'b-gone': 99 })
    expect(visibleStockBindings(bindings, [wbOnly]).map((one) => one.id)).toEqual(['b-wb'])
  })

  it('C28: Ozon-привязка видна только при товаре с карточкой Ozon; в bulk — если применима хотя бы одному', () => {
    const bindings = buildStockBindings({ wb: wbCabinet, ozon: ozonCabinet }, saved)
    const wbOnly = product('p', 'WB-only', { 'b-wb': 10 })
    wbOnly.byBinding['b-ozon'] = { ...wbOnly.byBinding['b-wb']!, applicable: false }
    const withOzon = product('q', 'С Ozon', { 'b-wb': 10, 'b-ozon': 10 })
    expect(visibleStockBindings(bindings, [wbOnly]).map((one) => one.id)).toEqual(['b-wb'])
    expect(visibleStockBindings(bindings, [wbOnly, withOzon]).map((one) => one.id)).toEqual(['b-wb', 'b-ozon'])
    // Записи о привязке у товара нет вовсе: WB считается применимым, Ozon — нет.
    const bare = product('r', 'Без записей', {})
    expect(visibleStockBindings(bindings, [bare]).map((one) => one.id)).toEqual(['b-wb'])
  })
})

describe('WMS-469 R5 список для «Добавить склад»', () => {
  it('C4: предлагает только ещё не связанные склады полученных кабинетов', () => {
    const bindings = buildStockBindings({ wb: wbCabinet, ozon: ozonCabinet }, saved)
    expect(addableWarehouses({ wb: wbCabinet, ozon: ozonCabinet }, bindings)).toEqual([
      { marketplace: 'wb', externalId: '501002', name: 'Второй склад WB' },
    ])
  })

  it('C5: когда все склады добавлены, список пуст', () => {
    const onlyOne: CabinetList = { received: true, rows: [wbCabinet.rows[0]!] }
    const bindings = buildStockBindings({ wb: onlyOne, ozon: { received: false } }, saved)
    expect(addableWarehouses({ wb: onlyOne, ozon: { received: false } }, bindings)).toEqual([])
  })

  it('C30: из неполученного справочника новые склады не предлагаются', () => {
    const bindings = buildStockBindings({ wb: { received: false }, ozon: ozonCabinet }, saved)
    expect(addableWarehouses({ wb: { received: false }, ozon: ozonCabinet }, bindings)).toEqual([])
  })
})
