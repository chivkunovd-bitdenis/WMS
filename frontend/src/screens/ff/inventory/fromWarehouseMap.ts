import type {
  CellNode as MapCell,
  MapNode,
  WarehouseMapData,
} from '../warehouse-map/WarehouseMapTypes'
import { UNASSIGNED_ID, UNASSIGNED_LABEL } from '../warehouse-map/WarehouseMapTypes'
import type { CellNode, InventoryCount, InventoryNode } from './InventoryTypes'

// Пересчёт со строки карты склада.
//
// Документ рождается наполненным составом ровно того объекта, на котором нажали:
// нажал на короб — в документе только его товары. Ничего лишнего рядом: человек
// стоит у конкретной полки и не должен видеть весь склад.

function toInventoryNode(node: MapNode): InventoryNode {
  if (node.kind === 'product') {
    return {
      kind: 'product',
      id: node.id,
      productId: node.product_id,
      name: node.name,
      sku: node.product_id,
      seller: node.seller_name ?? '—',
      category: node.category ?? '—',
      barcode: node.barcode ?? '',
      photoUrl: node.photo_url,
      // Числится ровно столько, сколько показывает карта. Факт пока не введён.
      expected: node.qty,
      actual: null,
    }
  }
  return {
    kind: node.kind,
    id: node.id,
    code: node.code,
    barcode: node.barcode,
    children: node.children.map(toInventoryNode),
  }
}

type Found = { node: MapNode; cellLabel: string | null }

function findNode(data: WarehouseMapData, id: string): Found | null {
  function walk(nodes: MapNode[], cellLabel: string | null): Found | null {
    for (const node of nodes) {
      if (node.id === id) return { node, cellLabel }
      if (node.kind !== 'product') {
        const inner = walk(node.children, cellLabel)
        if (inner) return inner
      }
    }
    return null
  }
  for (const cell of data.cells) {
    const found = walk(cell.children, cell.code)
    if (found) return found
  }
  return walk(data.unassigned, UNASSIGNED_LABEL)
}

function cellById(data: WarehouseMapData, id: string): MapCell | undefined {
  return data.cells.find((cell) => cell.id === id)
}

export type MapInventoryTarget = {
  kind: 'cell' | 'unassigned' | 'pallet' | 'box' | 'cargo_place' | 'product'
  id: string
  title: string
}

/** Где лежит объект: показываем в шапке диалога, а не отдельным уровнем дерева. */
export function placeOf(data: WarehouseMapData, target: MapInventoryTarget): string | null {
  if (target.kind === 'cell' || target.kind === 'unassigned') return null
  const found = findNode(data, target.id)
  return found?.cellLabel ?? null
}

/**
 * Собрать документ пересчёта по одной строке карты.
 *
 * Возвращает `null`, если строку не нашли: молча показать пустой документ хуже,
 * чем не открыть его вовсе — человек решит, что на месте действительно пусто.
 */
export function countFromMapRow(
  data: WarehouseMapData,
  target: MapInventoryTarget,
  warehouseName: string,
  addressStorage: boolean,
): InventoryCount | null {
  let cells: CellNode[]
  if (target.kind === 'cell') {
    const cell = cellById(data, target.id)
    if (!cell) return null
    cells = [{ id: cell.id, label: cell.code, children: cell.children.map(toInventoryNode) }]
  } else if (target.kind === 'unassigned' || target.id === UNASSIGNED_ID) {
    cells = [
      { id: UNASSIGNED_ID, label: UNASSIGNED_LABEL, children: data.unassigned.map(toInventoryNode) },
    ]
  } else {
    const found = findNode(data, target.id)
    if (!found) return null
    cells = [
      {
        id: `scope-${target.id}`,
        label: found.cellLabel ?? UNASSIGNED_LABEL,
        children: [toInventoryNode(found.node)],
      },
    ]
  }

  return {
    id: `map-${target.id}`,
    // Номер выдаёт сервер при сохранении. До этого документа в базе нет, и
    // выдумывать ему номер на клиенте нельзя: он разойдётся с настоящим.
    number: 'новый',
    status: 'draft',
    warehouseName,
    fill: { mode: 'object', objectLabel: target.title },
    createdAt: '',
    createdBy: '',
    postedAt: null,
    postedBy: null,
    comment: '',
    addressStorage,
    scoped: target.kind !== 'cell' && target.kind !== 'unassigned',
    cells,
  }
}

/**
 * Как назвать то, что пересчитываем.
 *
 * У тары и товара строка карты уже называет себя целиком («Короб КР-000471»),
 * поэтому добавлять слово «Короб» второй раз нельзя. Ячейка называет себя одним
 * кодом, ей название нужно.
 */
export function targetTitle(kind: MapInventoryTarget['kind'], rowTitle: string): string {
  if (kind === 'cell') return `Ячейка ${rowTitle}`
  return rowTitle
}
