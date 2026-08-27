import {
  KIND_TITLE,
  UNASSIGNED_ID,
  UNASSIGNED_LABEL,
  type CellNode,
  type ContainerKind,
  type MapNode,
  type WarehouseMapData,
} from './WarehouseMapTypes'

// Дерево склада разворачивается в один плоский список строк, и таблица на экране
// остаётся одной таблицей с одной шапкой. Вторая таблица под строкой читалась бы
// как второй отчёт — оператору нужен один список, где вложенность видна отступом.

export type MapRowKind = 'cell' | 'unassigned' | ContainerKind | 'product'

export type MapRow = {
  key: string
  id: string
  kind: MapRowKind
  depth: number
  title: string
  seller: string | null
  barcode: string | null
  qty: number
  photoUrl: string | null
  expandable: boolean
  expanded: boolean
  /** Внутри ничего нет: пустая ячейка, пустой короб. Такую строку не прячем. */
  empty: boolean
  /** Ключ строки, внутри которой эта лежит. */
  parentKey: string | null
  /** Ключи всех вышестоящих строк — чтобы палету нельзя было положить внутрь себя. */
  ancestorKeys: string[]
  /** Как эта строка называется, когда она становится местом: «Ячейка А-01-02». */
  placeLabel: string
}

const CONTAINER_KINDS: ContainerKind[] = ['pallet', 'box', 'cargo_place']

// Порядок внутри места продиктован владельцем и не зависит от того, в каком
// порядке строки пришли с сервера: сначала палеты, потом короба и грузоместа,
// в конце товар, лежащий россыпью.
const KIND_ORDER: Record<MapNode['kind'], number> = {
  pallet: 0,
  box: 1,
  cargo_place: 1,
  product: 2,
}

function inOrder(nodes: MapNode[]): MapNode[] {
  return [...nodes].sort((left, right) => KIND_ORDER[left.kind] - KIND_ORDER[right.kind])
}

function isContainerKind(kind: MapRowKind): kind is ContainerKind {
  return (CONTAINER_KINDS as MapRowKind[]).includes(kind)
}

export function nodeTitle(node: MapNode): string {
  return node.kind === 'product' ? node.name : `${KIND_TITLE[node.kind]} ${node.code}`
}

function matchesQuery(node: MapNode, query: string): boolean {
  const haystack =
    node.kind === 'product'
      ? [node.name, node.seller_name, node.barcode]
      : [node.code, node.seller_name, node.barcode]
  return haystack.some((value) => (value ?? '').toLowerCase().includes(query))
}

/** Узел остаётся в выдаче, если совпал сам или совпало что-то внутри него. */
function keepNode(node: MapNode, query: string): MapNode | null {
  if (node.kind === 'product') {
    return matchesQuery(node, query) ? node : null
  }
  if (matchesQuery(node, query)) {
    return node
  }
  const children = node.children.map((child) => keepNode(child, query)).filter(Boolean) as MapNode[]
  return children.length > 0 ? { ...node, children } : null
}

function filterCell(cell: CellNode, query: string): CellNode | null {
  if (cell.code.toLowerCase().includes(query)) {
    return cell
  }
  const children = cell.children.map((child) => keepNode(child, query)).filter(Boolean) as MapNode[]
  return children.length > 0 ? { ...cell, children } : null
}

type WalkContext = {
  rows: MapRow[]
  expandedKeys: Set<string>
  /** При поиске всё раскрыто: иначе найденное прячется под свёрнутым родителем. */
  forceExpanded: boolean
}

function pushNode(
  context: WalkContext,
  node: MapNode,
  depth: number,
  parentKey: string,
  ancestorKeys: string[],
) {
  const key = `${parentKey}/${node.id}`
  const children = node.kind === 'product' ? [] : inOrder(node.children)
  const expanded = context.forceExpanded || context.expandedKeys.has(key)
  context.rows.push({
    key,
    id: node.id,
    kind: node.kind,
    depth,
    title: nodeTitle(node),
    seller: node.seller_name,
    barcode: node.barcode,
    qty: node.qty,
    photoUrl: node.kind === 'product' ? node.photo_url : null,
    expandable: children.length > 0,
    expanded: children.length > 0 && expanded,
    empty: node.kind !== 'product' && children.length === 0,
    parentKey,
    ancestorKeys,
    placeLabel: nodeTitle(node),
  })
  if (children.length === 0 || !expanded) {
    return
  }
  const nextAncestors = [...ancestorKeys, key]
  for (const child of children) {
    pushNode(context, child, depth + 1, key, nextAncestors)
  }
}

export function buildRows(
  data: WarehouseMapData,
  options: { expandedKeys: Set<string>; query: string },
): MapRow[] {
  const query = options.query.trim().toLowerCase()
  const context: WalkContext = {
    rows: [],
    expandedKeys: options.expandedKeys,
    forceExpanded: query.length > 0,
  }

  const unassigned = query
    ? (data.unassigned.map((node) => keepNode(node, query)).filter(Boolean) as MapNode[])
    : data.unassigned
  const cells = query
    ? (data.cells.map((cell) => filterCell(cell, query)).filter(Boolean) as CellNode[])
    : data.cells

  // Совсем пустой склад показывает не строку «Без ячеек» с нулём, а пустое
  // состояние таблицы: оператору нужно сказать, что делать, а не показать ноль.
  if (cells.length === 0 && unassigned.length === 0) {
    return []
  }

  // «Без ячеек» стоит первым и намеренно: это очередь работы, а не архив.
  // Всё, что там лежит, ждёт, когда его разложат.
  const unassignedExpanded = context.forceExpanded || context.expandedKeys.has(UNASSIGNED_ID)
  const unassignedQty = unassigned.reduce((sum, node) => sum + node.qty, 0)
  context.rows.push({
    key: UNASSIGNED_ID,
    id: UNASSIGNED_ID,
    kind: 'unassigned',
    depth: 0,
    title: UNASSIGNED_LABEL,
    seller: null,
    barcode: null,
    qty: unassignedQty,
    photoUrl: null,
    expandable: unassigned.length > 0,
    expanded: unassigned.length > 0 && unassignedExpanded,
    empty: unassigned.length === 0,
    parentKey: null,
    ancestorKeys: [],
    placeLabel: UNASSIGNED_LABEL,
  })
  if (unassigned.length > 0 && unassignedExpanded) {
    for (const node of inOrder(unassigned)) {
      pushNode(context, node, 1, UNASSIGNED_ID, [UNASSIGNED_ID])
    }
  }

  for (const cell of cells) {
    const expanded = context.forceExpanded || context.expandedKeys.has(cell.id)
    context.rows.push({
      key: cell.id,
      id: cell.id,
      kind: 'cell',
      depth: 0,
      title: cell.code,
      seller: null,
      barcode: cell.barcode,
      qty: cell.qty,
      photoUrl: null,
      expandable: cell.children.length > 0,
      expanded: cell.children.length > 0 && expanded,
      empty: cell.children.length === 0,
      parentKey: null,
      ancestorKeys: [],
      placeLabel: `Ячейка ${cell.code}`,
    })
    if (cell.children.length === 0 || !expanded) {
      continue
    }
    for (const node of inOrder(cell.children)) {
      pushNode(context, node, 1, cell.id, [cell.id])
    }
  }

  return context.rows
}

/** Ключи всех строк, которые вообще можно раскрыть — для «развернуть всё». */
export function allExpandableKeys(data: WarehouseMapData): Set<string> {
  const keys = new Set<string>()
  const walk = (node: MapNode, parentKey: string) => {
    if (node.kind === 'product') return
    const key = `${parentKey}/${node.id}`
    if (node.children.length > 0) {
      keys.add(key)
      node.children.forEach((child) => walk(child, key))
    }
  }
  if (data.unassigned.length > 0) {
    keys.add(UNASSIGNED_ID)
    data.unassigned.forEach((node) => walk(node, UNASSIGNED_ID))
  }
  for (const cell of data.cells) {
    if (cell.children.length === 0) continue
    keys.add(cell.id)
    cell.children.forEach((node) => walk(node, cell.id))
  }
  return keys
}

/**
 * Куда можно положить взятое.
 *
 * Правила складские, а не программистские: товар ложится куда угодно, короб —
 * на ячейку, на палету или в «Без ячеек», палета — только на ячейку или в
 * «Без ячеек». Внутрь самой себя не кладётся ничего, и в то место, где строка
 * и так лежит, тоже: такой «перенос» ничего не менял бы, а в журнале появилась
 * бы запись о работе, которой не было.
 */
export function canDropOn(carried: MapRow, target: MapRow): boolean {
  if (target.key === carried.key) return false
  if (target.key === carried.parentKey) return false
  if (target.ancestorKeys.includes(carried.key)) return false

  if (carried.kind === 'product') {
    return target.kind !== 'product'
  }
  if (carried.kind === 'pallet') {
    return target.kind === 'cell' || target.kind === 'unassigned'
  }
  if (isContainerKind(carried.kind)) {
    return target.kind === 'cell' || target.kind === 'unassigned' || target.kind === 'pallet'
  }
  return false
}

/** Строку-место (ячейку и «Без ячеек») рукой не носят: место остаётся на месте. */
export function canDragRow(row: MapRow): boolean {
  return row.kind !== 'cell' && row.kind !== 'unassigned'
}
