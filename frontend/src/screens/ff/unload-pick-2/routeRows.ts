import { isCellRef } from '../sorting-objects/objectsStub'
import type { Cell, GoodsLine, Holder, WarehouseObject } from '../sorting-objects/objectsStub'
import { KIND_TITLE, PLAN, PRODUCTS, STOCK, cellRef, objRef } from '../unload-pick/pickStub'
import type { PlanLine } from '../unload-pick/pickStub'
import { chainOf } from '../unload-pick/pickRows'

// Вариант Б подбора на отгрузку: экран собран от МЕСТА ОБХОДА, а не от товара.
//
// Кладовщик ходит по складу, а не по строкам документа. Он подходит к палете
// один раз и снимает с неё всё, что нужно по отгрузке, — а не возвращается к
// ней трижды, потому что в документе три строки. Поэтому единица экрана здесь
// не товар, а остановка: адрес, к которому надо подойти.
//
// Модель мест взята импортом из раскладки (`sorting-objects/objectsStub`) и из
// варианта А, а не переписана: две правды о том, где лежит товар, разъезжаются
// на первой же правке. Правило то же и другого в модели нет: у палеты, короба и
// грузоместа либо есть ячейка, либо её нет. Есть — всё, что внутри, лежит в
// этой ячейке. Нет — объект стоит без ячейки, и товар с него снимается так же.

/** Сколько снято по каждой строке остатка: ключ — идентификатор строки. */
export type PickedMap = Record<string, number>

/** Товар в том виде, в каком его показывает этот экран. */
export type RouteProduct = {
  id: string
  name: string
  sku: string
  barcode: string
  photo: string
}

function photo(letters: string): string {
  const svg = `<svg xmlns="http://www.w3.org/2000/svg" width="240" height="240">
    <rect width="240" height="240" fill="#eef1f6"/>
    <rect x="48" y="60" width="144" height="120" rx="10" fill="#c7cedb"/>
    <text x="120" y="141" font-family="Inter, sans-serif" font-size="46" font-weight="700"
      fill="#5a6478" text-anchor="middle">${letters}</text>
  </svg>`
  return `data:image/svg+xml;utf8,${encodeURIComponent(svg.replace(/\s+/g, ' '))}`
}

/**
 * Товары того же продавца, которых в этой отгрузке нет.
 *
 * Они здесь не для красоты. Кладовщик открывает короб и видит в нём не только
 * то, что просит документ: если экран показывает лишь плановые строки, человек
 * решает, что взял не тот короб, и идёт искать другой. Чёрная футболка рядом с
 * белой — самый частый способ ошибиться рукой, и она должна быть видна.
 */
const EXTRA_PRODUCTS: RouteProduct[] = [
  {
    id: 'p-tshirt-black',
    name: 'Футболка хлопок чёрная, M',
    sku: 'TS-BLK-M',
    barcode: '4680123456840',
    photo: photo('ФЧ'),
  },
  {
    id: 'p-shorts',
    name: 'Шорты джинсовые синие, 32',
    sku: 'SH-BLU-32',
    barcode: '4680123456857',
    photo: photo('ШР'),
  },
]

export const CATALOG: RouteProduct[] = [...PRODUCTS, ...EXTRA_PRODUCTS]

export function routeProduct(id: string): RouteProduct {
  return CATALOG.find((one) => one.id === id)!
}

/** Что ещё лежит в тех же местах помимо плана отгрузки. */
const EXTRA_STOCK: GoodsLine[] = [
  { id: 'x-1', productId: 'p-tshirt-black', qty: 40, holder: objRef('plt-131') },
  { id: 'x-2', productId: 'p-shorts', qty: 22, holder: objRef('box-472') },
]

export const ROUTE_STOCK: GoodsLine[] = [...STOCK, ...EXTRA_STOCK]

export type RouteItem = {
  /** Ключ строки остатка — по нему же считается снятое. */
  key: string
  product: RouteProduct
  /** В чём лежит внутри места: «Короб КР-000472», «Палета П-000131», «На полке». */
  inside: string
  holder: Holder
  /** Сколько физически лежит. */
  qty: number
  /** Сколько уже снято отсюда в этом подборе. */
  picked: number
  /** Сколько ещё снять именно отсюда по документу. */
  need: number
  /** Есть ли товар в плане отгрузки. */
  inPlan: boolean
}

export type RouteStop = {
  key: string
  /** «А 1.1» или «Без ячейки». */
  address: string
  cellCode: string | null
  /** Что стоит по этому адресу: «Палета П-000131», «Россыпью, без тары». */
  standing: string
  items: RouteItem[]
  /** Сколько строк документа закрывается здесь. */
  lines: number
  /** Сколько штук снять здесь. */
  need: number
  /** Сколько здесь уже снято. */
  picked: number
  /** Сколько лежит того, чего в этой отгрузке нет. */
  foreign: number
  skipped: boolean
}

export type Shortfall = { product: RouteProduct; qty: number }

export type RoutePlan = {
  stops: RouteStop[]
  /** Чего не хватит: остаток плана, который не закрылся ни одним местом. */
  shortfall: Shortfall[]
  planQty: number
  pickedQty: number
  linesTotal: number
  linesDone: number
  /** Сколько мест ещё надо обойти. */
  stopsLeft: number
  stopsTotal: number
}

function objectTitle(object: WarehouseObject): string {
  return `${KIND_TITLE[object.kind]} ${object.code}`
}

/**
 * Что стоит по адресу.
 *
 * Для ячейки это объекты, которые стоят прямо на ней: короб внутри палеты сюда
 * не попадает, он часть содержимого палеты, а не отдельная вещь на полке.
 */
function standingAt(key: string, objects: WarehouseObject[]): string {
  if (isCellRef(key)) {
    const onCell = objects.filter((one) => one.holder === key)
    if (onCell.length === 0) return 'Россыпью, без тары'
    return onCell.map(objectTitle).join(' · ')
  }
  const object = objects.find((one) => objRef(one.id) === key)
  return object ? objectTitle(object) : 'Без тары'
}

/** В чём лежит строка остатка: ближайший держатель, а не вся цепочка. */
function insideTitle(holder: Holder, objects: WarehouseObject[]): string {
  if (!holder) return 'Без тары'
  if (isCellRef(holder)) return 'На полке'
  const object = objects.find((one) => objRef(one.id) === holder)
  return object ? objectTitle(object) : 'Без тары'
}

/**
 * Адрес, к которому подходит кладовщик.
 *
 * Ячейка, если она есть у цепочки; иначе самый внешний объект — он и есть
 * место, потому что стоит сам по себе. Это ровно то же правило, что и в
 * раскладке: палета присвоена ячейке — значит всё, что на ней, лежит там же.
 */
export function stopKeyOf(
  holder: Holder,
  objects: WarehouseObject[],
  cells: Cell[],
): string | null {
  const { cell, chain } = chainOf(holder, objects, cells)
  if (cell) return cellRef(cell.id)
  if (chain.length > 0) return objRef(chain[0].id)
  return null
}

/**
 * Раздача плана по местам.
 *
 * Плановое количество раздаётся местам в том порядке, в каком кладовщик их
 * обходит: первое место забирает столько, сколько может дать, остаток уходит
 * дальше. Из-за этого место, без которого план закрывается, честно помечается
 * «не нужно» — и человек к нему не идёт. Вариант А этого сказать не мог: он
 * перечислял все места товара, а решать, к какому идти, оставлял человеку.
 *
 * Пропущенные места из раздачи выпадают, и их количество тут же переезжает на
 * следующие. Поэтому «пропустить» — это не пометка на память, а пересчёт.
 */
export function routePlan(
  plan: PlanLine[],
  stock: GoodsLine[],
  objects: WarehouseObject[],
  cells: Cell[],
  picked: PickedMap,
  skipped: string[],
): RoutePlan {
  const planned = new Map(plan.map((line) => [line.productId, line.plan]))
  const stops = new Map<string, RouteStop>()

  for (const line of stock) {
    const key = stopKeyOf(line.holder, objects, cells) ?? 'none'
    let stop = stops.get(key)
    if (!stop) {
      const { cell } = chainOf(line.holder, objects, cells)
      stop = {
        key,
        address: cell ? cell.code : 'Без ячейки',
        cellCode: cell?.code ?? null,
        standing: standingAt(key, objects),
        items: [],
        lines: 0,
        need: 0,
        picked: 0,
        foreign: 0,
        skipped: skipped.includes(key),
      }
      stops.set(key, stop)
    }
    stop.items.push({
      key: line.id,
      product: routeProduct(line.productId),
      inside: insideTitle(line.holder, objects),
      holder: line.holder,
      qty: line.qty,
      picked: picked[line.id] ?? 0,
      need: 0,
      inPlan: planned.has(line.productId),
    })
  }

  // Порядок обхода: сначала то, что стоит на ячейках, по адресу; потом то, что
  // стоит без ячейки. Ровно так человек и ходит — по стеллажам, а потом по тому,
  // что брошено в проходе.
  const ordered = [...stops.values()].sort((a, b) => {
    if (Boolean(a.cellCode) !== Boolean(b.cellCode)) return a.cellCode ? -1 : 1
    return (a.cellCode ?? a.standing).localeCompare(b.cellCode ?? b.standing, 'ru')
  })

  for (const stop of ordered) {
    stop.items.sort(
      (a, b) =>
        a.inside.localeCompare(b.inside, 'ru') || a.product.name.localeCompare(b.product.name, 'ru'),
    )
  }

  // Сколько ещё нужно по каждому товару: план минус уже снятое по всему складу.
  const left = new Map<string, number>()
  for (const line of plan) {
    const takenTotal = stock
      .filter((one) => one.productId === line.productId)
      .reduce((sum, one) => sum + (picked[one.id] ?? 0), 0)
    left.set(line.productId, Math.max(0, line.plan - takenTotal))
  }

  for (const stop of ordered) {
    for (const item of stop.items) {
      if (!item.inPlan || stop.skipped) continue
      const remaining = left.get(item.product.id) ?? 0
      const available = Math.max(0, item.qty - item.picked)
      const take = Math.min(remaining, available)
      item.need = take
      left.set(item.product.id, remaining - take)
    }
    stop.need = stop.items.reduce((sum, item) => sum + item.need, 0)
    stop.picked = stop.items.reduce((sum, item) => sum + item.picked, 0)
    stop.foreign = stop.items
      .filter((item) => !item.inPlan)
      .reduce((sum, item) => sum + item.qty, 0)
    stop.lines = new Set(
      stop.items.filter((item) => item.need > 0).map((item) => item.product.id),
    ).size
  }

  const shortfall: Shortfall[] = []
  for (const [productId, qty] of left) {
    if (qty > 0) shortfall.push({ product: routeProduct(productId), qty })
  }

  const planQty = plan.reduce((sum, line) => sum + line.plan, 0)
  const pickedQty = plan.reduce((sum, line) => {
    const taken = stock
      .filter((one) => one.productId === line.productId)
      .reduce((inner, one) => inner + (picked[one.id] ?? 0), 0)
    return sum + Math.min(taken, line.plan)
  }, 0)
  const linesDone = plan.filter((line) => {
    const taken = stock
      .filter((one) => one.productId === line.productId)
      .reduce((inner, one) => inner + (picked[one.id] ?? 0), 0)
    return taken >= line.plan
  }).length

  return {
    stops: ordered,
    shortfall,
    planQty,
    pickedQty,
    linesTotal: plan.length,
    linesDone,
    stopsLeft: ordered.filter((stop) => stop.need > 0).length,
    stopsTotal: ordered.length,
  }
}

/**
 * Состояние места одним словом.
 *
 * «Не нужно» — не ошибка и не пустое место: там лежит товар отгрузки, но его
 * количество целиком закрывается местами, к которым человек подойдёт раньше.
 */
export function stopStatus(stop: RouteStop): {
  label: string
  tone: 'neutral' | 'ok' | 'warn' | 'stop'
  hint: string
} {
  if (stop.skipped) {
    return {
      label: 'Пропущено',
      tone: 'warn',
      hint: 'Место пропущено — его количество перешло на следующие места маршрута',
    }
  }
  if (stop.need === 0 && stop.picked > 0) {
    return { label: 'Снято', tone: 'ok', hint: 'Отсюда взято всё, что требовалось' }
  }
  if (stop.need === 0) {
    return {
      label: 'Не нужно',
      tone: 'neutral',
      hint: 'Плановое количество закрывается местами, к которым вы подойдёте раньше',
    }
  }
  if (stop.picked > 0) {
    return { label: 'Начато', tone: 'warn', hint: 'Здесь снято не всё — вернитесь и доснимите' }
  }
  return { label: 'Не начато', tone: 'neutral', hint: 'К этому месту ещё не подходили' }
}

export const DEFAULT_PLAN = PLAN
