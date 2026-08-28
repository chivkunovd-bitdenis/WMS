import type {
  ContainerNode,
  InventoryCount,
  InventoryNode,
  NodeKind,
  ProductNode,
} from './InventoryTypes'
import { KIND_TITLE } from './InventoryTypes'

// Дерево разворачивается в плоский список строк: таблица на экране остаётся
// одной таблицей с одной шапкой, а вложенность видна отступом. Вторая таблица
// внутри строки читалась бы как второй отчёт.

export type RowKind = 'cell' | NodeKind

export type InvRow = {
  key: string
  id: string
  kind: RowKind
  depth: number
  title: string
  seller: string | null
  category: string | null
  barcode: string | null
  photoUrl: string | null
  /** Числится: у листа своё, у тары — сумма по её листам. */
  expected: number
  /** Факт: у листа введённое число, у тары — сумма введённых. */
  actual: number | null
  /**
   * Расхождение. У тары считается ТОЛЬКО по посчитанным строкам.
   *
   * Иначе непосчитанная строка молча засчитывается как ноль, и ячейка, где
   * человек прошёл половину, показывает недостачу, которой нет. Кладовщик идёт
   * искать пропажу, а искать нечего — он просто не дошёл до конца полки.
   */
  delta: number | null
  /**
   * У тары — излишек и недостача по отдельности, а не одним числом.
   *
   * Сложенные вместе они врут: три лишних ремня и три недостающих платья дают
   * ноль, и ячейка выглядит благополучной. На складе это два разных товара и две
   * разные причины, и обе надо разобрать.
   */
  surplus: number
  shortage: number
  /** Сколько строк внутри не сошлось. */
  mismatchLeaves: number
  /** Сколько листов внутри и сколько из них посчитано. У листа обе нули. */
  leaves: number
  countedLeaves: number
  expandable: boolean
  expanded: boolean
  empty: boolean
  parentKey: string | null
  /** Остаток изменился с момента наполнения документа. */
  stale: boolean
}

export type InvFilters = {
  /** Название, артикул или штрихкод. Можно вставить пачкой через пробел. */
  query: string
  seller: string
  category: string
  /** Показывать только то, где ещё не считали или где расхождение. */
  onlyPending: boolean
}

export const EMPTY_FILTERS: InvFilters = {
  query: '',
  seller: '',
  category: '',
  onlyPending: false,
}

function isProduct(node: InventoryNode): node is ProductNode {
  return node.kind === 'product'
}

/** Порядок внутри места: сначала палеты, потом короба и грузоместа, товар последним. */
const KIND_ORDER: Record<NodeKind, number> = {
  pallet: 0,
  box: 1,
  cargo_place: 1,
  product: 2,
}

function inOrder(nodes: InventoryNode[]): InventoryNode[] {
  return [...nodes].sort((a, b) => KIND_ORDER[a.kind] - KIND_ORDER[b.kind])
}

export function nodeTitle(node: InventoryNode): string {
  return isProduct(node) ? node.name : `${KIND_TITLE[node.kind]} ${node.code}`
}

/** Что реально числится сейчас: если остаток уехал, берём новое число. */
export function expectedNow(product: ProductNode): number {
  return product.expectedNow ?? product.expected
}

export function isStale(product: ProductNode): boolean {
  return product.expectedNow !== undefined && product.expectedNow !== product.expected
}

export function collectProducts(nodes: InventoryNode[]): ProductNode[] {
  const out: ProductNode[] = []
  for (const node of nodes) {
    if (isProduct(node)) out.push(node)
    else out.push(...collectProducts(node.children))
  }
  return out
}

export function allProducts(count: InventoryCount): ProductNode[] {
  return count.cells.flatMap((cell) => collectProducts(cell.children))
}

function matchesFilters(product: ProductNode, filters: InvFilters): boolean {
  if (filters.seller && product.seller !== filters.seller) return false
  if (filters.category && product.category !== filters.category) return false
  if (filters.onlyPending) {
    const counted = product.actual !== null
    const matches = counted && product.actual === expectedNow(product)
    if (matches) return false
  }
  const needle = filters.query.trim().toLowerCase()
  if (!needle) return true
  // Пачка кодов, вставленная столбцом: достаточно совпадения по любому.
  const parts = needle.split(/\s+/)
  const haystack = `${product.name} ${product.sku} ${product.barcode}`.toLowerCase()
  return parts.some((part) => haystack.includes(part))
}

type Agg = {
  expected: number
  actual: number | null
  /** Числящееся только по тем строкам, которые уже посчитали. */
  expectedCounted: number
  delta: number | null
  surplus: number
  shortage: number
  mismatch: number
  leaves: number
  counted: number
}

function aggregate(products: ProductNode[]): Agg {
  let expected = 0
  let expectedCounted = 0
  let actualSum = 0
  let counted = 0
  let surplus = 0
  let shortage = 0
  let mismatch = 0
  for (const product of products) {
    expected += expectedNow(product)
    if (product.actual === null) continue
    expectedCounted += expectedNow(product)
    actualSum += product.actual
    counted += 1
    const d = product.actual - expectedNow(product)
    if (d === 0) continue
    mismatch += 1
    if (d > 0) surplus += d
    else shortage += -d
  }
  return {
    expected,
    actual: counted === 0 ? null : actualSum,
    expectedCounted,
    delta: counted === 0 ? null : actualSum - expectedCounted,
    surplus,
    shortage,
    mismatch,
    leaves: products.length,
    counted,
  }
}

type BuildCtx = {
  filters: InvFilters
  collapsed: Set<string>
  rows: InvRow[]
}

function pushContainer(
  node: ContainerNode,
  ctx: BuildCtx,
  depth: number,
  parentKey: string,
): ProductNode[] {
  const key = `${node.kind}:${node.id}`
  const kept = collectProducts(node.children).filter((p) => matchesFilters(p, ctx.filters))
  // Тара, из которой фильтр вымел всё, не показывается: иначе экран усыпан
  // пустыми коробами, к которым человеку идти незачем.
  if (kept.length === 0 && !isEmptyContainer(node)) return []
  const agg = aggregate(kept)
  const expanded = !ctx.collapsed.has(key)
  ctx.rows.push({
    key,
    id: node.id,
    kind: node.kind,
    depth,
    title: nodeTitle(node),
    seller: null,
    category: null,
    barcode: node.barcode,
    photoUrl: null,
    expected: agg.expected,
    actual: agg.actual,
    delta: agg.delta,
    surplus: agg.surplus,
    shortage: agg.shortage,
    mismatchLeaves: agg.mismatch,
    leaves: agg.leaves,
    countedLeaves: agg.counted,
    expandable: node.children.length > 0,
    expanded,
    empty: isEmptyContainer(node),
    parentKey,
    stale: kept.some(isStale),
  })
  if (expanded) walk(node.children, ctx, depth + 1, key)
  return kept
}

function isEmptyContainer(node: ContainerNode): boolean {
  return collectProducts(node.children).length === 0
}

function walk(nodes: InventoryNode[], ctx: BuildCtx, depth: number, parentKey: string) {
  for (const node of inOrder(nodes)) {
    if (isProduct(node)) {
      if (!matchesFilters(node, ctx.filters)) continue
      ctx.rows.push({
        key: `product:${node.id}`,
        id: node.id,
        kind: 'product',
        depth,
        title: node.name,
        seller: node.seller,
        category: node.category,
        barcode: node.barcode,
        photoUrl: node.photoUrl,
        expected: expectedNow(node),
        actual: node.actual,
        delta: node.actual === null ? null : node.actual - expectedNow(node),
        surplus: 0,
        shortage: 0,
        mismatchLeaves: 0,
        leaves: 0,
        countedLeaves: 0,
        expandable: false,
        expanded: false,
        empty: false,
        parentKey,
        stale: isStale(node),
      })
      continue
    }
    pushContainer(node, ctx, depth, parentKey)
  }
}

export function buildRows(
  count: InventoryCount,
  filters: InvFilters,
  collapsed: Set<string>,
): InvRow[] {
  const ctx: BuildCtx = { filters, collapsed, rows: [] }
  for (const cell of count.cells) {
    const kept = collectProducts(cell.children).filter((p) => matchesFilters(p, filters))
    if (kept.length === 0) continue
    const key = `cell:${cell.id}`
    const agg = aggregate(kept)
    const expanded = !collapsed.has(key)
    ctx.rows.push({
      key,
      id: cell.id,
      kind: 'cell',
      depth: 0,
      title: cell.label,
      seller: null,
      category: null,
      barcode: null,
      photoUrl: null,
      expected: agg.expected,
      actual: agg.actual,
      delta: agg.delta,
      surplus: agg.surplus,
      shortage: agg.shortage,
      mismatchLeaves: agg.mismatch,
      leaves: agg.leaves,
      countedLeaves: agg.counted,
      expandable: cell.children.length > 0,
      expanded,
      empty: false,
      parentKey: null,
      stale: kept.some(isStale),
    })
    if (expanded) walk(cell.children, ctx, 1, key)
  }
  return ctx.rows
}

export type CountTotals = {
  lines: number
  counted: number
  discrepancies: number
  surplus: number
  shortage: number
  stale: number
}

export function totals(count: InventoryCount): CountTotals {
  let counted = 0
  let discrepancies = 0
  let surplus = 0
  let shortage = 0
  let stale = 0
  const products = allProducts(count)
  for (const product of products) {
    if (isStale(product)) stale += 1
    if (product.actual === null) continue
    counted += 1
    const delta = product.actual - expectedNow(product)
    if (delta === 0) continue
    discrepancies += 1
    if (delta > 0) surplus += delta
    else shortage += -delta
  }
  return { lines: products.length, counted, discrepancies, surplus, shortage, stale }
}

/** Все значения выбора для фильтров — берутся из самого документа. */
export function facets(count: InventoryCount): { sellers: string[]; categories: string[] } {
  const sellers = new Set<string>()
  const categories = new Set<string>()
  for (const product of allProducts(count)) {
    sellers.add(product.seller)
    categories.add(product.category)
  }
  return {
    sellers: [...sellers].sort((a, b) => a.localeCompare(b, 'ru')),
    categories: [...categories].sort((a, b) => a.localeCompare(b, 'ru')),
  }
}

export function setActual(
  count: InventoryCount,
  productId: string,
  actual: number | null,
): InventoryCount {
  function mapNodes(nodes: InventoryNode[]): InventoryNode[] {
    return nodes.map((node) => {
      if (node.kind === 'product') {
        return node.id === productId ? { ...node, actual } : node
      }
      return { ...node, children: mapNodes(node.children) }
    })
  }
  return { ...count, cells: count.cells.map((c) => ({ ...c, children: mapNodes(c.children) })) }
}

export function collapseAllKeys(count: InventoryCount): Set<string> {
  const keys = new Set<string>()
  function walkNodes(nodes: InventoryNode[]) {
    for (const node of nodes) {
      if (node.kind === 'product') continue
      keys.add(`${node.kind}:${node.id}`)
      walkNodes(node.children)
    }
  }
  for (const cell of count.cells) {
    keys.add(`cell:${cell.id}`)
    walkNodes(cell.children)
  }
  return keys
}
