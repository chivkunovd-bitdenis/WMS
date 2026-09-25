// Блоки окна «Остаток для FBS» (WMS-469).
//
// Один блок — одна сохранённая привязка склада продавца (WB или Ozon) к
// физическому складу ФФ. Внутри блока — правило выбранных товаров именно для
// этой привязки: включена ли передача, процент либо ручной потолок. Всё, что
// здесь считается, — чистые функции без сети и без React: их проверяют
// юнит-тесты, а окно только рисует результат.

import { type MarketplaceCode, type WarehouseNameIssue } from './stub'
import { warehouseNumberLabel, type CabinetList, type SavedWarehouseBinding } from './fbsSellerWarehouseRows'

/** Правило товара по одной привязке — как отдаёт `by_binding` сервера. */
export type ApiBindingRule = {
  publish: boolean
  mode: 'percent' | 'units'
  value: number
  /** WMS-483: false distinguishes an unset units limit from an explicit zero. */
  units_configured?: boolean
  marketplace: string
  external_warehouse_id: string
  wms_warehouse_id: string
  served: boolean
  applicable: boolean
  on_hand: number
  reserved: number
  free_stock: number
  published_now: number
}

/** Состояние товара по привязке, которым живёт окно. */
export type ProductBindingState = {
  publish: boolean
  mode: 'percent' | 'units'
  value: number
  /** In units mode, whether the operator actually set the limit (zero included). */
  unitsConfigured: boolean
  /** Ozon-привязка применима только к товару с активной карточкой Ozon. */
  applicable: boolean
  onHand: number
  reserved: number
  freeStock: number
}

export type StockDialogProduct = {
  id: string
  name: string
  sku: string
  size: string | null
  /** Ключ — id привязки (`binding_id`). */
  byBinding: Record<string, ProductBindingState>
}

/** Сохранённая привязка продавца с человеческим названием из кабинета. */
export type StockBinding = {
  /** `binding_id` — им ключуется правило товара. */
  id: string
  marketplace: MarketplaceCode
  /** Внешний номер склада строкой: у WB — `wb_warehouse_id`, у Ozon — `external_warehouse_id`. */
  externalId: string
  /** Название из живого справочника либо «№ <номер>», если имени нет. */
  name: string
  nameIssue?: WarehouseNameIssue
  wmsWarehouseId: string
  /** Название склада ФФ из ответа привязки — на случай, если его нет в списке выбора. */
  wmsWarehouseName: string | null
  served: boolean
  /** Может ли текущий пользователь менять связку и приём заказов. */
  editable: boolean
}

/** Склад из живого кабинета площадки — кандидат в «Добавить склад». */
export type CabinetWarehouse = {
  marketplace: MarketplaceCode
  externalId: string
  name: string
}

/** Черновик одного блока. Ровно один источник: процент либо число. */
export type BlockDraft = {
  publish: boolean
  byPercent: boolean
  percent: number
  /** null is an empty field; 0 is an explicit operator limit (WMS-483). */
  units: number | null
}

export const PERCENT_STEP = 5

export function toProductBindingState(rule: ApiBindingRule): ProductBindingState {
  return {
    publish: rule.publish,
    mode: rule.mode,
    value: rule.value,
    unitsConfigured: rule.units_configured ?? rule.mode === 'units',
    applicable: rule.applicable,
    onHand: rule.on_hand,
    reserved: rule.reserved,
    freeStock: rule.free_stock,
  }
}

/**
 * Привязки продавца с названиями из кабинетов.
 *
 * Имя берётся только из живого справочника соответствующей площадки (WMS-457):
 * для WB по `wb_warehouse_id`, для Ozon по строковому `external_warehouse_id`.
 * Нет имени — строка подписывается номером и получает причину: справочник
 * получен, но склада в нём нет (удалён или чужой), либо справочник не получен.
 * Неактивные привязки не показываются вовсе.
 */
export function buildStockBindings(
  cabinets: Record<MarketplaceCode, CabinetList>,
  bindings: SavedWarehouseBinding[],
): StockBinding[] {
  const result: StockBinding[] = []
  for (const binding of bindings) {
    if (!binding.is_active || !binding.id || !binding.wms_warehouse_id) continue
    const marketplace = binding.marketplace ?? 'wb'
    const externalId = String(binding.external_warehouse_id ?? binding.wb_warehouse_id)
    const list = cabinets[marketplace]
    const row = list.received
      ? list.rows.find((one) => String(one.wb_warehouse_id) === externalId)
      : undefined
    result.push({
      id: binding.id,
      marketplace,
      externalId,
      name: row?.name ?? warehouseNumberLabel(externalId),
      ...(row?.name ? {} : { nameIssue: list.received ? 'not_in_cabinet' : 'list_unavailable' }),
      wmsWarehouseId: binding.wms_warehouse_id,
      wmsWarehouseName: binding.wms_warehouse_name ?? null,
      served: binding.served,
      editable: binding.editable ?? true,
    })
  }
  return result
}

/** Применима ли привязка к товару. Без записи в правиле WB считается применимым, Ozon — нет. */
export function bindingApplies(binding: StockBinding, product: StockDialogProduct): boolean {
  const state = product.byBinding[binding.id]
  if (state) return state.applicable
  return binding.marketplace !== 'ozon'
}

/**
 * Блоки, которые окно показывает для выбранных товаров.
 *
 * Скрываются: склад, которого нет в полученном кабинете и с которого заказы не
 * принимаем (WMS-468, он не должен участвовать в расчёте); Ozon-привязка, если
 * ни у одного из выбранных товаров нет активной карточки Ozon (WMS-454).
 */
export function visibleStockBindings(
  bindings: StockBinding[],
  products: StockDialogProduct[],
): StockBinding[] {
  return bindings.filter((binding) => {
    if (binding.nameIssue === 'not_in_cabinet' && !binding.served) return false
    return products.some((product) => bindingApplies(binding, product))
  })
}

/** Склады кабинетов, у которых ещё нет активной привязки, — список для «Добавить склад». */
export function addableWarehouses(
  cabinets: Record<MarketplaceCode, CabinetList>,
  bindings: StockBinding[],
): CabinetWarehouse[] {
  const bound = new Set(bindings.map((one) => `${one.marketplace}:${one.externalId}`))
  const result: CabinetWarehouse[] = []
  for (const marketplace of ['wb', 'ozon'] as const) {
    const list = cabinets[marketplace]
    if (!list.received) continue
    for (const row of list.rows) {
      const externalId = String(row.wb_warehouse_id)
      if (bound.has(`${marketplace}:${externalId}`)) continue
      result.push({ marketplace, externalId, name: row.name ?? warehouseNumberLabel(externalId) })
    }
  }
  return result
}

export function emptyDraft(): BlockDraft {
  return { publish: false, byPercent: true, percent: 0, units: null }
}

/** Черновик блока из сохранённого состояния товара. */
export function draftFromState(state: ProductBindingState | undefined): BlockDraft {
  if (!state) return emptyDraft()
  return {
    publish: state.publish,
    byPercent: state.mode === 'percent',
    percent: state.mode === 'percent' ? state.value : 0,
    units: state.mode === 'units' && state.unitsConfigured ? state.value : null,
  }
}

/**
 * Черновики всех блоков на открытие окна. При нескольких товарах окно
 * начинает с правила первого выбранного; ко всем выбранным применяются
 * только те блоки, которые оператор в этом открытии менял.
 */
export function initialDrafts(
  bindings: StockBinding[],
  products: StockDialogProduct[],
): Record<string, BlockDraft> {
  const first = products[0]
  return Object.fromEntries(
    bindings.map((binding) => [binding.id, draftFromState(first?.byBinding[binding.id])]),
  )
}

function freeAt(product: StockDialogProduct, bindingId: string): number {
  return product.byBinding[bindingId]?.freeStock ?? 0
}

/**
 * Строка чисел блока — Остаток, Резерв и Доступно организации суммой по
 * выбранным товарам (WMS-530 R6). Доступно показывается как есть, в том числе
 * меньше нуля, как в каталоге (R3, D3): это разность остатка и резерва, а не
 * `free_stock`, который сервер для расчётов обрезает нулём.
 */
export function blockTotals(
  binding: StockBinding,
  products: StockDialogProduct[],
): { onHand: number; reserved: number; available: number } {
  let onHand = 0
  let reserved = 0
  for (const product of products) {
    const state = product.byBinding[binding.id]
    if (!state) continue
    onHand += state.onHand
    reserved += state.reserved
  }
  return { onHand, reserved, available: onHand - reserved }
}

/**
 * Потолок ручного числа: свободный остаток самого малого из выбранных товаров
 * на этом складе ФФ (ответ владельца: «одного товара 50, второго 30 — общий
 * остаток 30»). При равенстве называется первый товар в порядке выбранных
 * строк (решение D3).
 */
export function unitsCap(
  binding: StockBinding,
  products: StockDialogProduct[],
): { free: number; product: StockDialogProduct } {
  let best: { free: number; product: StockDialogProduct } | null = null
  for (const product of products) {
    const free = freeAt(product, binding.id)
    if (best === null || free < best.free) best = { free, product }
  }
  return best ?? { free: 0, product: products[0]! }
}

/**
 * Что показать в строке площадки: число в поле и процент на ползунке.
 *
 * В процентном режиме лимит считается каждому товару отдельно с округлением
 * вниз и складывается — как на сервере; умножать один раз суммарный остаток
 * нельзя (R10). В ручном режиме число — одинаковый потолок каждому товару, а
 * процент — только индикатор: отношение суммы `min(N, свободно)` к сумме
 * свободных остатков, округлённое до целого (R11).
 */
export function rowCalc(
  binding: StockBinding,
  draft: BlockDraft,
  products: StockDialogProduct[],
): { free: number; ship: number; pct: number; fieldValue: number | null } {
  let free = 0
  let ship = 0
  for (const product of products) {
    const f = freeAt(product, binding.id)
    free += f
    if (draft.byPercent) ship += Math.floor((f * draft.percent) / 100)
    else ship += Math.min(draft.units ?? 0, f)
  }
  const pct = draft.byPercent ? draft.percent : free > 0 ? Math.round((ship / free) * 100) : 0
  return { free, ship, pct, fieldValue: draft.byPercent ? ship : draft.units }
}

export function snapPercent(value: number): number {
  return Math.max(0, Math.min(100, Math.round(value / PERCENT_STEP) * PERCENT_STEP))
}

/**
 * Ручной ввод числа с обрезкой без блокировки (R12): больше, чем есть у самого
 * малого из товаров, не даём — поле встаёт на максимум, а подпись называет
 * товар и его остаток. Возвращает принятое число и товар-ограничитель, если
 * обрезка была.
 */
export function clampUnits(
  binding: StockBinding,
  requested: number,
  products: StockDialogProduct[],
): { units: number; limitedBy: { free: number; product: StockDialogProduct } | null } {
  const cap = unitsCap(binding, products)
  const units = Math.max(0, Math.min(999999, Math.floor(requested)))
  if (units > cap.free) return { units: cap.free, limitedBy: cap }
  return { units, limitedBy: null }
}

/** Переключение «процентом» → «числом» и обратно: одно значение в двух представлениях. */
export function toggleByPercent(
  binding: StockBinding,
  draft: BlockDraft,
  byPercent: boolean,
  products: StockDialogProduct[],
): BlockDraft {
  const calc = rowCalc(binding, draft, products)
  if (byPercent) return { ...draft, byPercent: true, percent: snapPercent(calc.pct) }
  // WMS-483: если поштучный лимит не был задан, простое переключение режима
  // оставляет поле пустым. Иначе пустое и явный операторский 0 схлопнулись бы.
  return { ...draft, byPercent: false }
}

export const NUMBER_FORMAT = (n: number) => n.toLocaleString('ru-RU')

export function pluralRu(n: number, one: string, few: string, many: string): string {
  const a = Math.abs(n) % 100
  const b = a % 10
  if (a > 10 && a < 20) return many
  if (b > 1 && b < 5) return few
  if (b === 1) return one
  return many
}

/** Подпись под полем: `товара «…» всего N штук`. */
export function capNoteText(limit: { free: number; product: { name: string } }): string {
  return `товара «${limit.product.name}» всего ${NUMBER_FORMAT(limit.free)} ${pluralRu(limit.free, 'штука', 'штуки', 'штук')}`
}

/**
 * Тело `rule.by_binding` для PUT /products/fbs-rule из переданных блоков —
 * вызывающий отдает только изменённые оператором. Не переданный блок сервер
 * не трогает, поэтому правки WB не задевают Ozon соседних товаров (R8, R24).
 * Пустой результат означает «нечего сохранять»: отправлять его нельзя —
 * пустой by_binding сервер читает как старую форму правила.
 */
export function ruleBodyFromDrafts(
  bindings: StockBinding[],
  drafts: Record<string, BlockDraft>,
): Record<string, { publish: boolean; mode: 'percent' | 'units'; value: number; units_configured: boolean }> {
  const body: Record<string, { publish: boolean; mode: 'percent' | 'units'; value: number; units_configured: boolean }> = {}
  for (const binding of bindings) {
    // Снятая галка приёма заказов прячет строку и не трогает сохранённое правило (R7).
    if (!binding.served) continue
    const draft = drafts[binding.id]
    if (!draft) continue
    body[binding.id] = draft.byPercent
      ? { publish: draft.publish, mode: 'percent', value: draft.percent, units_configured: false }
      : {
          publish: draft.publish,
          mode: 'units',
          value: draft.units ?? 0,
          units_configured: draft.units !== null,
        }
  }
  return body
}
