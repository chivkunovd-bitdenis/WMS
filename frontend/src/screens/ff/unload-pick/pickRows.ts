import { isCellRef, refId } from '../sorting-objects/objectsStub'
import {
  KIND_TITLE,
  productById,
  type Cell,
  type GoodsLine,
  type Holder,
  type PickProduct,
  type PlanLine,
  type WarehouseObject,
} from './pickStub'

// Строки экрана подбора. Одна строка — один товар из плана отгрузки, внутри
// строки списком идут места, откуда его можно снять.
//
// Списка ячеек здесь нет намеренно: ячейка — только верхнее слово в адресе
// места. Товар лежит в коробе, короб на палете, палета в ячейке — и снимать его
// надо с того объекта, где он реально лежит, а не «с ячейки вообще».

/** Сколько снято по каждому месту: ключ — товар + место. */
export type PickedMap = Record<string, number>

export const pickKey = (productId: string, placeKey: string) => `${productId}|${placeKey}`

export type PickPlace = {
  /** Ссылка на держатель: она же ключ строки места. */
  key: string
  holder: Holder
  /** «А 1.1 · палета П-000131 · короб КР-000472» — адрес одной строкой. */
  label: string
  /** Ячейка есть или объект стоит без ячейки. Нужно для порядка сортировки. */
  cellCode: string | null
  /** Сколько физически лежит. */
  qty: number
  /** Сколько уже снято в этом подборе. */
  picked: number
  /** Сколько ещё можно снять отсюда. */
  left: number
}

export type PickRow = {
  key: string
  product: PickProduct
  plan: number
  picked: number
  left: number
  places: PickPlace[]
}

/**
 * Цепочка держателей снизу вверх: где лежит и в чём.
 *
 * Ячейка в цепочке всегда последняя ступень и всегда одна. Если её нет — объект
 * стоит без ячейки; это не ошибка данных, а обычное состояние склада: палета
 * приехала и стоит в проходе, товар с неё снимают точно так же.
 */
export function chainOf(
  holder: Holder,
  objects: WarehouseObject[],
  cells: Cell[],
): { cell: Cell | null; chain: WarehouseObject[] } {
  const chain: WarehouseObject[] = []
  let cursor = holder
  while (cursor) {
    if (isCellRef(cursor)) {
      return { cell: cells.find((one) => one.id === refId(cursor!)) ?? null, chain }
    }
    const object = objects.find((one) => one.id === refId(cursor!))
    if (!object) break
    chain.unshift(object)
    cursor = object.holder
  }
  return { cell: null, chain }
}

/**
 * Адрес места одной строкой: ячейка, потом объекты снаружи внутрь.
 *
 * «Без ячейки» пишется у самого внешнего объекта, а не отдельным словом впереди:
 * кладовщику важно, что искать надо палету П-000140, а не то, что у неё нет
 * адреса на полке.
 */
export function placeLabel(holder: Holder, objects: WarehouseObject[], cells: Cell[]): string {
  const { cell, chain } = chainOf(holder, objects, cells)
  const parts = chain.map((one, index) => {
    const name = `${KIND_TITLE[one.kind].toLowerCase()} ${one.code}`
    return !cell && index === 0 ? `${name} (без ячейки)` : name
  })
  if (cell) parts.unshift(cell.code)
  if (parts.length === 0) return 'Без ячейки'
  return parts.join(' · ')
}

/**
 * Места, откуда можно снять этот товар.
 *
 * Место — всегда самый нижний объект, в котором товар лежит: если он в коробе
 * на палете, то место — короб, а палета остаётся частью адреса. Порядок такой
 * же, как оператор ходит: сначала то, что стоит на ячейках, потом то, что без
 * ячеек.
 */
export function placesOf(
  productId: string,
  stock: GoodsLine[],
  objects: WarehouseObject[],
  cells: Cell[],
  picked: PickedMap,
): PickPlace[] {
  const byHolder = new Map<string, number>()
  for (const line of stock) {
    if (line.productId !== productId) continue
    const key = line.holder ?? 'none'
    byHolder.set(key, (byHolder.get(key) ?? 0) + line.qty)
  }
  const places: PickPlace[] = []
  for (const [key, qty] of byHolder) {
    const holder: Holder = key === 'none' ? null : key
    const { cell } = chainOf(holder, objects, cells)
    const taken = picked[pickKey(productId, key)] ?? 0
    places.push({
      key,
      holder,
      label: placeLabel(holder, objects, cells),
      cellCode: cell?.code ?? null,
      qty,
      picked: taken,
      left: Math.max(0, qty - taken),
    })
  }
  return places.sort((a, b) => {
    if (Boolean(a.cellCode) !== Boolean(b.cellCode)) return a.cellCode ? -1 : 1
    return (a.cellCode ?? a.label).localeCompare(b.cellCode ?? b.label, 'ru')
  })
}

export function rowsOf(
  plan: PlanLine[],
  stock: GoodsLine[],
  objects: WarehouseObject[],
  cells: Cell[],
  picked: PickedMap,
): PickRow[] {
  return plan.map((line) => {
    const places = placesOf(line.productId, stock, objects, cells, picked)
    const taken = places.reduce((sum, place) => sum + place.picked, 0)
    return {
      key: line.id,
      product: productById(line.productId),
      plan: line.plan,
      picked: taken,
      left: Math.max(0, line.plan - taken),
      places,
    }
  })
}

/** Лежит ли место внутри отсканированного источника (или это он сам). */
export function isInside(holder: Holder, source: string, objects: WarehouseObject[]): boolean {
  let cursor = holder
  while (cursor) {
    if (cursor === source) return true
    if (isCellRef(cursor)) return false
    const object = objects.find((one) => one.id === refId(cursor!))
    if (!object) return false
    cursor = object.holder
  }
  return false
}

/**
 * Что из этого товара лежит внутри отсканированного места.
 *
 * Пикнули палету — сюда попадёт и то, что лежит на ней россыпью, и то, что
 * лежит в коробе на этой палете. Разбираться, из чего именно брать, экран будет
 * только если таких мест окажется больше одного.
 */
export function placesUnder(
  places: PickPlace[],
  source: string | null,
  objects: WarehouseObject[],
): PickPlace[] {
  const available = places.filter((place) => place.left > 0)
  if (!source) return available
  return available.filter((place) => isInside(place.holder, source, objects))
}
