import {
  KIND_TITLE,
  cellRef,
  whereIs,
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
      /** Сколько строк внутри — для подписи под названием. */
      inside: number
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
      size: string | null
      qty: number
      alreadyAt: Array<{ cellId: string; code: string; qty: number }>
      inside: number
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
      inside: children,
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
      size: product.size,
      qty: line.qty,
      alreadyAt: product.alreadyAt,
      inside: 0,
    })
  }
}

/**
 * Всё, что ещё не поставлено на полку, одним списком: товар россыпью и
 * собранные короба, палеты и грузоместа со своим содержимым внутри.
 * Поставленное отсюда уходит — список тает по мере работы.
 */
export function unplacedRows(
  objects: WarehouseObject[],
  lines: GoodsLine[],
  collapsed: Set<string>,
): ObjectRow[] {
  const out: ObjectRow[] = []
  walk(null, 0, objects, lines, collapsed, out)
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


/**
 * Единый список: сначала то, что ещё не поставлено на полку, потом то, что уже
 * стоит, по ячейкам. Две таблицы с двумя шапками оператор читает как два разных
 * отчёта — здесь одна таблица и одна шапка, а разница видна колонкой «Где».
 */
export function allRows(
  objects: WarehouseObject[],
  lines: GoodsLine[],
  cells: Cell[],
  collapsed: Set<string>,
): ObjectRow[] {
  const out: ObjectRow[] = []
  walk(null, 0, objects, lines, collapsed, out)
  for (const cell of cells) {
    walk(cellRef(cell.id), 0, objects, lines, collapsed, out)
  }
  return out
}

/** Ячейка, в которой физически стоит эта строка, или null — ещё не поставлено. */
export function rowCell(
  row: ObjectRow,
  objects: WarehouseObject[],
  cells: Cell[],
): Cell | null {
  const holder = row.kind === 'object' ? row.object.holder : row.line.holder
  return whereIs(holder, objects, cells).cell
}

/** Куда вообще можно положить это — готовый список мест для выбора. */
export function destinationsFor(
  carried: Carried,
  objects: WarehouseObject[],
  cells: Cell[],
): Array<{ value: string; label: string }> {
  const options: Array<{ value: string; label: string }> = []
  if (canPut(carried, null, objects)) {
    options.push({ value: 'none', label: 'Россыпь — вынуть наружу' })
  }
  for (const cell of cells) {
    if (canPut(carried, cellRef(cell.id), objects)) {
      options.push({ value: cellRef(cell.id), label: `Ячейка ${cell.code}` })
    }
  }
  for (const object of objects) {
    if (canPut(carried, objRef(object.id), objects)) {
      options.push({ value: objRef(object.id), label: objectTitle(object) })
    }
  }
  return options
}
