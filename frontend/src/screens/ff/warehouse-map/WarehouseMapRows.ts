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
  category: string | null
  sellerArticle: string | null
  barcode: string | null
  qty: number
  /**
   * Идентификатор товара у строки товара.
   *
   * У строки товара `id` — это ключ остатка «товар на месте», а не сам товар.
   * Пересчёт по объекту ждёт именно товар, и без этого поля он отвечал
   * «объект уже переместили или удалили».
   */
  productId?: string | null
  photoUrl: string | null
  expandable: boolean
  expanded: boolean
  /** Внутри ничего нет: пустая ячейка, пустой короб. Такую строку не прячем. */
  empty: boolean
  /** Ключ строки, внутри которой эта лежит. */
  parentKey: string | null
  /** Ключи всех вышестоящих строк — чтобы палету нельзя было положить внутрь себя. */
  ancestorKeys: string[]
  /** Как эта строка называется, когда она становится местом: «Ячейка А 1.1». */
  placeLabel: string
}

export type MapFilters = {
  /** Одно значение или пачка: «4680123456789 4600987654321», можно вставить столбцом. */
  query: string
  /** Пустая строка — фильтр не применён. */
  seller: string
  category: string
}

export const EMPTY_FILTERS: MapFilters = { query: '', seller: '', category: '' }

const CONTAINER_KINDS: ContainerKind[] = ['pallet', 'box', 'cargo_place']

function isContainerKind(kind: MapRowKind): kind is ContainerKind {
  return (CONTAINER_KINDS as MapRowKind[]).includes(kind)
}

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

export function nodeTitle(node: MapNode): string {
  return node.kind === 'product' ? node.name : `${KIND_TITLE[node.kind]} ${node.code}`
}

/** Поиск понимает пачку: значения разделяются пробелом, запятой, точкой с запятой или переводом строки. */
export function searchTokens(query: string): string[] {
  return [
    ...new Set(
      query
        .split(/[\s,;]+/)
        .map((token) => token.trim().toLowerCase())
        .filter(Boolean),
    ),
  ]
}

function haystack(node: MapNode): string[] {
  return node.kind === 'product'
    ? [node.name, node.seller_name, node.category, node.seller_article, node.barcode]
        .filter(Boolean)
        .map((value) => (value as string).toLowerCase())
    : // Номер приёмки ищем тем же полем, что и код тары (§Б-04): короб из
      // незавершённой приёмки находится по номеру документа, из которого он
      // ещё не выехал в постоянное место.
      [node.code, node.seller_name, node.barcode, node.source_document_number]
        .filter(Boolean)
        .map((value) => (value as string).toLowerCase())
}

function matchesTokens(node: MapNode, tokens: string[]): boolean {
  if (tokens.length === 0) return true
  const values = haystack(node)
  return tokens.some((token) => values.some((value) => value.includes(token)))
}

function matchesFacets(node: MapNode, filters: MapFilters): boolean {
  if (node.kind !== 'product') return true
  if (filters.seller && node.seller_name !== filters.seller) return false
  if (filters.category && node.category !== filters.category) return false
  return true
}

/** Узел остаётся в выдаче, если подошёл сам или подошло что-то внутри него. */
function keepNode(node: MapNode, filters: MapFilters, tokens: string[]): MapNode | null {
  if (node.kind === 'product') {
    return matchesFacets(node, filters) && matchesTokens(node, tokens) ? node : null
  }
  const children = node.children
    .map((child) => keepNode(child, filters, tokens))
    .filter(Boolean) as MapNode[]
  if (children.length > 0) {
    return { ...node, children }
  }
  // Контейнер, который подошёл сам, остаётся даже пустым: оператор ищет короб,
  // а не его содержимое, и должен увидеть, что короб пуст.
  const selfMatch =
    matchesTokens(node, tokens) && !filters.seller && !filters.category && tokens.length > 0
  return selfMatch ? { ...node, children: [] } : null
}

function filterCell(cell: CellNode, filters: MapFilters, tokens: string[]): CellNode | null {
  const children = cell.children
    .map((child) => keepNode(child, filters, tokens))
    .filter(Boolean) as CellNode['children']
  if (children.length > 0) {
    return { ...cell, children }
  }
  const selfMatch =
    tokens.length > 0 &&
    !filters.seller &&
    !filters.category &&
    tokens.some(
      (token) =>
        cell.code.toLowerCase().includes(token) ||
        (cell.barcode ?? '').toLowerCase().includes(token),
    )
  return selfMatch ? { ...cell, children: [] } : null
}

function isFiltered(filters: MapFilters, tokens: string[]): boolean {
  return tokens.length > 0 || Boolean(filters.seller) || Boolean(filters.category)
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
    productId: node.kind === 'product' ? node.product_id : null,
    kind: node.kind,
    depth,
    title: nodeTitle(node),
    seller: node.seller_name,
    category: node.kind === 'product' ? node.category : null,
    sellerArticle: node.kind === 'product' ? node.seller_article : null,
    barcode: node.barcode,
    qty: node.qty,
    photoUrl: node.kind === 'product' ? node.photo_url : null,
    expandable: children.length > 0,
    expanded: children.length > 0 && expanded,
    // Пусто — значит внутри физически ничего нет, и это решает qty, а не длина
    // списка детей. При поиске контейнер, совпавший по собственному коду,
    // остаётся без детей — и раньше получал чип «Пустая», имея внутри товар.
    empty: node.kind !== 'product' && node.qty === 0,
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
  options: { expandedKeys: Set<string>; filters: MapFilters },
): MapRow[] {
  const { filters } = options
  const tokens = searchTokens(filters.query)
  const filtered = isFiltered(filters, tokens)
  const context: WalkContext = {
    rows: [],
    expandedKeys: options.expandedKeys,
    forceExpanded: filtered,
  }

  const unassigned = filtered
    ? (data.unassigned.map((node) => keepNode(node, filters, tokens)).filter(Boolean) as MapNode[])
    : data.unassigned
  const cells = filtered
    ? (data.cells.map((cell) => filterCell(cell, filters, tokens)).filter(Boolean) as CellNode[])
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
    category: null,
    sellerArticle: null,
    barcode: null,
    qty: unassignedQty,
    photoUrl: null,
    expandable: unassigned.length > 0,
    expanded: unassigned.length > 0 && unassignedExpanded,
    empty: unassignedQty === 0 && unassigned.length === 0,
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
      category: null,
      sellerArticle: null,
      barcode: cell.barcode,
      qty: cell.qty,
      photoUrl: null,
      expandable: cell.children.length > 0,
      expanded: cell.children.length > 0 && expanded,
      empty: cell.qty === 0 && cell.children.length === 0,
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

/**
 * Значения пачки, по которым на складе ничего не нашлось.
 *
 * Оператор вставляет столбец штрихкодов и должен сразу видеть не только то, что
 * нашлось, но и чего нет: молчаливый короткий список он прочитает как «всё тут».
 */
export function missingTokens(data: WarehouseMapData, query: string): string[] {
  const tokens = searchTokens(query)
  if (tokens.length === 0) return []
  const found = new Set<string>()
  const visit = (node: MapNode) => {
    const values = haystack(node)
    tokens.forEach((token) => {
      if (values.some((value) => value.includes(token))) found.add(token)
    })
    if (node.kind !== 'product') node.children.forEach(visit)
  }
  data.unassigned.forEach(visit)
  data.cells.forEach((cell) => {
    const values = [cell.code.toLowerCase(), (cell.barcode ?? '').toLowerCase()]
    tokens.forEach((token) => {
      if (values.some((value) => value.includes(token))) found.add(token)
    })
    cell.children.forEach(visit)
  })
  return tokens.filter((token) => !found.has(token))
}

/**
 * Найти по штрихкороду короб, палету, грузоместо, ячейку или товар.
 *
 * Это перенос уже существующего поведения из блока коробов в каталоге: пикнул
 * короб — он раскрылся и подсветился. Здесь то же самое, только цель ещё и
 * показывает, на какой ячейке лежит, потому что дерево видно целиком.
 */
export function findByBarcode(
  data: WarehouseMapData,
  barcode: string,
): { key: string; ancestorKeys: string[]; title: string; placeLabel: string } | null {
  const needle = barcode.trim().toLowerCase()
  if (!needle) return null

  const walk = (
    node: MapNode,
    parentKey: string,
    ancestors: string[],
    placeLabel: string,
  ): { key: string; ancestorKeys: string[]; title: string; placeLabel: string } | null => {
    const key = `${parentKey}/${node.id}`
    if ((node.barcode ?? '').toLowerCase() === needle) {
      return { key, ancestorKeys: ancestors, title: nodeTitle(node), placeLabel }
    }
    if (node.kind === 'product') return null
    for (const child of node.children) {
      const hit = walk(child, key, [...ancestors, key], nodeTitle(node))
      if (hit) return hit
    }
    return null
  }

  for (const node of data.unassigned) {
    const hit = walk(node, UNASSIGNED_ID, [UNASSIGNED_ID], UNASSIGNED_LABEL)
    if (hit) return hit
  }
  for (const cell of data.cells) {
    if ((cell.barcode ?? '').toLowerCase() === needle) {
      return { key: cell.id, ancestorKeys: [], title: cell.code, placeLabel: `Ячейка ${cell.code}` }
    }
    for (const node of cell.children) {
      const hit = walk(node, cell.id, [cell.id], `Ячейка ${cell.code}`)
      if (hit) return hit
    }
  }
  return null
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
