import {
  KIND_TITLE,
  cellRef,
  isCellRef,
  objRef,
  objectQty,
  productById,
  refId,
  type Cell,
  type GoodsLine,
  type Holder,
  type ObjKind,
  type WarehouseObject,
} from './objectsStub'

// Плоские строки для дерева объектов. Одна таблица с одной шапкой: вложенность
// видна отступом, а не второй таблицей внутри строки.

export type ObjectRow =
  | {
      key: string
      depth: number
      kind: 'object'
      object: WarehouseObject
      qty: number
      expandable: boolean
      expanded: boolean
      empty: boolean
    }
  | {
      key: string
      depth: number
      kind: 'goods'
      line: GoodsLine
      name: string
      sku: string
      seller: string
      barcode: string
      photo: string
      qty: number
    }

export type Carried =
  | { kind: 'object'; object: WarehouseObject }
  | { kind: 'goods'; line: GoodsLine }

/**
 * Куда можно положить то, что несут.
 *
 * Правила складские: товар ложится в любой объект и на любую ячейку; короб и
 * грузоместо — на палету или на ячейку; палета — только на ячейку. Внутрь себя
 * ничего не кладётся, и туда, где вещь и так лежит, — тоже: такой перенос
 * ничего не менял бы, а в журнале появилась бы работа, которой не было.
 */
export function canPut(
  carried: Carried,
  target: Holder,
  objects: WarehouseObject[],
): boolean {
  if (!target) return true // «вынуть наружу» разрешено всему
  if (carried.kind === 'goods') return carried.line.holder !== target
  const moving = carried.object
  if (moving.holder === target) return false
  if (target === objRef(moving.id)) return false
  if (isCellRef(target)) return true
  const byId = new Map(objects.map((one) => [one.id, one]))
  // Цикл: нельзя положить палету в короб, который стоит на ней самой.
  let cursor: Holder = target
  while (cursor && !isCellRef(cursor)) {
    const id = refId(cursor)
    if (id === moving.id) return false
    cursor = byId.get(id)?.holder ?? null
  }
  const host = byId.get(refId(target))
  if (!host) return false
  if (moving.kind === 'pallet') return false
  return host.kind === 'pallet'
}

/** Что можно создать внутри этого держателя. */
export function creatableIn(target: Holder, objects: WarehouseObject[]): ObjKind[] {
  if (!target) return ['pallet', 'box', 'cargo_place']
  if (isCellRef(target)) return ['pallet', 'box', 'cargo_place']
  const host = objects.find((one) => one.id === refId(target))
  if (!host) return []
  return host.kind === 'pallet' ? ['box', 'cargo_place'] : []
}

export function objectTitle(object: WarehouseObject): string {
  return `${KIND_TITLE[object.kind]} ${object.code}`
}

function walk(
  holder: Holder,
  depth: number,
  objects: WarehouseObject[],
  lines: GoodsLine[],
  collapsed: Set<string>,
  out: ObjectRow[],
) {
  for (const object of objects.filter((one) => one.holder === holder)) {
    const qty = objectQty(object.id, objects, lines)
    const children =
      objects.filter((one) => one.holder === objRef(object.id)).length +
      lines.filter((one) => one.holder === objRef(object.id)).length
    const expanded = !collapsed.has(object.id)
    out.push({
      key: `o-${object.id}`,
      depth,
      kind: 'object',
      object,
      qty,
      expandable: children > 0,
      expanded: children > 0 && expanded,
      empty: children === 0,
    })
    if (children > 0 && expanded) {
      walk(objRef(object.id), depth + 1, objects, lines, collapsed, out)
    }
  }
  for (const line of lines.filter((one) => one.holder === holder)) {
    const product = productById(line.productId)
    out.push({
      key: `l-${line.id}`,
      depth,
      kind: 'goods',
      line,
      name: product.name,
      sku: product.sku,
      seller: product.seller,
      barcode: product.barcode,
      photo: product.photo,
      qty: line.qty,
    })
  }
}

/** Дерево «собрано, но ещё не поставлено на полку». */
export function assembledRows(
  objects: WarehouseObject[],
  lines: GoodsLine[],
  collapsed: Set<string>,
): ObjectRow[] {
  const out: ObjectRow[] = []
  walk(null, 0, objects, lines, collapsed, out)
  return out.filter((row) => row.kind === 'object' || row.depth > 0)
}

/** Товар, который приехал россыпью и ещё никуда не убран. */
export function looseRows(lines: GoodsLine[]): ObjectRow[] {
  const out: ObjectRow[] = []
  walk(null, 0, [], lines, new Set(), out)
  return out
}

/** Что стоит на ячейке — считается по составу, а не хранится отдельно. */
export function cellRows(
  cell: Cell,
  objects: WarehouseObject[],
  lines: GoodsLine[],
  collapsed: Set<string>,
): ObjectRow[] {
  const out: ObjectRow[] = []
  walk(cellRef(cell.id), 0, objects, lines, collapsed, out)
  return out
}
