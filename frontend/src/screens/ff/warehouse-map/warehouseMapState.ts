import {
  UNASSIGNED_ID,
  UNASSIGNED_LABEL,
  type MapNode,
  type MovementEntry,
  type WarehouseMapData,
} from './WarehouseMapTypes'

// Чистое локальное обновление карты. Его используют и превью, и боевая
// связка: оператор сразу видит перенос, а сеть подтверждает его отдельно.

function sellersOf(node: MapNode, into: Set<string>) {
  if (node.kind === 'product') {
    if (node.seller_name) into.add(node.seller_name)
    return
  }
  node.children.forEach((child) => sellersOf(child, into))
}

function normalizeNode(node: MapNode): MapNode {
  if (node.kind === 'product') return node
  const children = node.children.map(normalizeNode)
  const sellers = new Set<string>()
  children.forEach((child) => sellersOf(child, sellers))
  return {
    ...node,
    children,
    qty: children.reduce((sum, child) => sum + child.qty, 0),
    // Подпись селлера честна только когда внутри один селлер: смешанный короб
    // с чьим-то одним именем врал бы прямо в строке.
    seller_name: sellers.size === 1 ? [...sellers][0]! : null,
  }
}

export function normalizeWarehouseMap(data: WarehouseMapData): WarehouseMapData {
  return {
    ...data,
    cells: data.cells.map((cell) => {
      const children = cell.children.map(normalizeNode)
      return { ...cell, children, qty: children.reduce((sum, child) => sum + child.qty, 0) }
    }),
    unassigned: data.unassigned.map(normalizeNode),
  }
}

/** Ключ строки — это путь: корень (ячейка или «Без ячеек») и дальше вложения. */
function splitKey(key: string): { rootId: string; path: string[] } {
  const parts = key.split('/')
  return { rootId: parts[0]!, path: parts.slice(1) }
}

function mapRoot(
  data: WarehouseMapData,
  rootId: string,
  updater: (children: MapNode[]) => MapNode[],
): WarehouseMapData {
  if (rootId === UNASSIGNED_ID) {
    return { ...data, unassigned: updater(data.unassigned) }
  }
  return {
    ...data,
    cells: data.cells.map((cell) =>
      cell.id === rootId ? { ...cell, children: updater(cell.children) } : cell,
    ),
  }
}

type Taken = { children: MapNode[]; taken: MapNode | null }

function takeFrom(children: MapNode[], path: string[], qty: number): Taken {
  const [head, ...rest] = path
  if (head === undefined) {
    return { children, taken: null }
  }
  if (rest.length > 0) {
    let taken: MapNode | null = null
    const next = children.map((child) => {
      if (child.id !== head || child.kind === 'product') return child
      const result = takeFrom(child.children, rest, qty)
      taken = result.taken
      return { ...child, children: result.children }
    })
    return { children: next, taken }
  }

  const target = children.find((child) => child.id === head) ?? null
  if (!target) {
    return { children, taken: null }
  }
  // Частичное снятие бывает только у товара: короб и палета переезжают целиком.
  if (target.kind === 'product' && qty > 0 && qty < target.qty) {
    return {
      children: children.map((child) =>
        child.id === head && child.kind === 'product' ? { ...child, qty: child.qty - qty } : child,
      ),
      taken: { ...target, id: `${target.id}-part-${Date.now()}`, qty },
    }
  }
  return { children: children.filter((child) => child.id !== head), taken: target }
}

function putInto(children: MapNode[], path: string[], node: MapNode): MapNode[] {
  const [head, ...rest] = path
  if (head === undefined) {
    // Такой же товар на том же месте складывается в одну строку: две строки
    // одного SKU в одной ячейке оператор читает как ошибку системы.
    if (node.kind === 'product') {
      const twin = children.find(
        (child) => child.kind === 'product' && child.product_id === node.product_id,
      )
      if (twin && twin.kind === 'product') {
        return children.map((child) =>
          child === twin ? { ...twin, qty: twin.qty + node.qty } : child,
        )
      }
    }
    return [...children, node]
  }
  return children.map((child) => {
    if (child.id !== head || child.kind === 'product') return child
    return { ...child, children: putInto(child.children, rest, node) }
  })
}

function journalEntry(
  subject: string,
  qty: number | null,
  fromLabel: string,
  toLabel: string,
  actor: string,
): MovementEntry {
  return {
    id: `mv-${Date.now()}-${Math.round(Math.random() * 1000)}`,
    at: new Date().toISOString(),
    actor_name: actor,
    subject,
    qty,
    from_label: fromLabel,
    to_label: toLabel,
  }
}

export type WarehouseMapIntent = {
  reason: 'move' | 'takeOff' | 'disband'
  rowKey: string
  rowTitle: string
  fromLabel: string
  toKey: string
  toLabel: string
}

export function applyWarehouseMapIntent(
  data: WarehouseMapData,
  intent: WarehouseMapIntent,
  qty: number,
  actor?: string,
): WarehouseMapData {
  const source = splitKey(intent.rowKey)

  if (intent.reason === 'disband') {
    let contents: MapNode[] = []
    let next = mapRoot(data, source.rootId, (children) => {
      const result = takeFrom(children, source.path, 0)
      if (result.taken && result.taken.kind !== 'product') {
        contents = result.taken.children
      }
      return result.children
    })
    next = { ...next, unassigned: [...next.unassigned, ...contents] }
    return normalizeWarehouseMap({
      ...next,
      journal: actor
        ? [
            journalEntry(intent.rowTitle, null, intent.fromLabel, UNASSIGNED_LABEL, actor),
            ...next.journal,
          ]
        : next.journal,
    })
  }

  let moved: MapNode | null = null
  let next = mapRoot(data, source.rootId, (children) => {
    const result = takeFrom(children, source.path, qty)
    moved = result.taken
    return result.children
  })
  const takenNode = moved as MapNode | null
  if (!takenNode) {
    return data
  }

  const destination = splitKey(intent.toKey)
  next = mapRoot(next, destination.rootId, (children) =>
    putInto(children, destination.path, takenNode),
  )

  return normalizeWarehouseMap({
    ...next,
    journal: actor
      ? [
          journalEntry(intent.rowTitle, takenNode.qty, intent.fromLabel, intent.toLabel, actor),
          ...next.journal,
        ]
      : next.journal,
  })
}
