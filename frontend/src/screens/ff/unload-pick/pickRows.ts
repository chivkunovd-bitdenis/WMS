import { isCellRef, refId } from '../sorting-objects/objectsStub'
import {
  KIND_TITLE,
  cellRef,
  objRef,
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

/** Строки плана, у которых есть хоть одно место внутри отсканированного объекта. */
export function rowsWithin(rows: PickRow[], source: string, objects: WarehouseObject[]): PickRow[] {
  return rows.filter((row) => row.places.some((place) => isInside(place.holder, source, objects)))
}

/**
 * Строка дерева мест: ячейка или объект на своей ступеньке отступа.
 *
 * Раскрывашка товара показывает не список ячеек, а структуру: ячейка → палета
 * → короб. `place` заполнен только там, где товар физически лежит и берётся
 * рукой — это те же ключи, что и в `PickPlace` (§3, §4 контракта). Узел без
 * `place` — чистая структура: он отвечает на вопрос «куда идти», снять с него
 * нечего.
 */
export type PlaceTreeRow = {
  key: string
  label: string
  depth: number
  place: PickPlace | null
}

type TreeNode = { key: string; label: string; place: PickPlace | null; children: TreeNode[] }

/**
 * Дерево мест одного товара, разложенное в плоский список для `DataTable`.
 *
 * Ключ узла всегда совпадает с ключом места (`cell:c-a11`, `obj:plt-131`,
 * `none`), когда узел — место: это ссылка на держатель, а не второй
 * идентификатор экрана (контракт, §12). Поэтому подсветку сканера можно
 * передавать в `DataTable.highlightedKey` напрямую — тем же значением, что
 * лежит в `source`.
 */
export function placeTreeOf(
  places: PickPlace[],
  objects: WarehouseObject[],
  cells: Cell[],
): PlaceTreeRow[] {
  const roots = new Map<string, TreeNode>()

  function rootFor(cell: Cell | null): TreeNode {
    const key = cell ? cellRef(cell.id) : 'none'
    const existing = roots.get(key)
    if (existing) return existing
    const node: TreeNode = { key, label: cell ? cell.code : 'Без ячейки', place: null, children: [] }
    roots.set(key, node)
    return node
  }

  for (const place of places) {
    const { cell, chain } = chainOf(place.holder, objects, cells)
    let current = rootFor(cell)
    if (chain.length === 0) {
      current.place = place
      continue
    }
    chain.forEach((object, index) => {
      const key = objRef(object.id)
      let child = current.children.find((one) => one.key === key)
      if (!child) {
        child = { key, label: `${KIND_TITLE[object.kind]} ${object.code}`, place: null, children: [] }
        current.children.push(child)
      }
      current = child
      if (index === chain.length - 1) current.place = place
    })
  }

  const flat: PlaceTreeRow[] = []
  function visit(node: TreeNode, depth: number) {
    flat.push({ key: node.key, label: node.label, depth, place: node.place })
    node.children.forEach((child) => visit(child, depth + 1))
  }
  roots.forEach((node) => visit(node, 0))
  return flat
}
