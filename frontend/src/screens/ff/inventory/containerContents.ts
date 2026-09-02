import type {
  ContainerKind,
  ContainerNode,
  InventoryCount,
  InventoryNode,
  ProductNode,
} from './InventoryTypes'
import { KIND_TITLE } from './InventoryTypes'
import { expectedNow } from './InventoryRows'

/** Строка описи: одна позиция внутри тары. */
export type ContentsRow = {
  photoUrl: string | null
  name: string
  size: string | null
  barcode: string | null
  vendorCode: string | null
  quantity: number
  /** Число взято из учёта, а не с пересчёта: до этой строки ещё не дошли. */
  fromLedger: boolean
}

export type ContainerContents = {
  kind: ContainerKind
  /**
   * Что наклеено на самой таре: `INB-…` у короба приёмки, `FBS-…` у короба
   * склада, свой код у палеты. Опознание идёт по нему — это единственный
   * идентификатор, который и уникален, и физически присутствует на коробе.
   */
  label: string
  /** Как ту же тару называет дерево документа: «КР-000007». Печатаем мелко. */
  treeCode: string
  cellLabel: string | null
  /** Один селлер — его имя. Несколько — так и пишем, выдумывать нельзя. */
  seller: string
  rows: ContentsRow[]
  totalPieces: number
}

function isProduct(node: InventoryNode): node is ProductNode {
  return node.kind === 'product'
}

type Found = { node: ContainerNode; cellLabel: string | null }

function findContainer(count: InventoryCount, containerId: string): Found | null {
  function walk(nodes: InventoryNode[], cellLabel: string | null): Found | null {
    for (const node of nodes) {
      if (isProduct(node)) continue
      if (node.id === containerId) return { node, cellLabel }
      const nested = walk(node.children, cellLabel)
      if (nested) return nested
    }
    return null
  }
  for (const cell of count.cells) {
    const found = walk(cell.children, cell.label || null)
    if (found) return found
  }
  return null
}

/**
 * Всё, что лежит внутри тары, включая вложенную.
 *
 * У палеты собственных товаров нет — товар лежит в её коробах. Опись палеты,
 * которая показывает пустоту, бесполезна, поэтому спускаемся до конца.
 */
function collectProducts(node: ContainerNode): ProductNode[] {
  const out: ProductNode[] = []
  function walk(nodes: InventoryNode[]) {
    for (const child of nodes) {
      if (isProduct(child)) out.push(child)
      else walk(child.children)
    }
  }
  walk(node.children)
  return out
}

/**
 * Содержимое тары для печатной описи.
 *
 * Печатаем факт пересчёта: опись клеится на короб после того, как его посчитали,
 * и на ней должно стоять то, что реально лежит внутри. До строк, которых ещё не
 * коснулись, факта нет — там берём учётное число и помечаем его, чтобы никто не
 * принял непосчитанное за посчитанное.
 *
 * Позиции с нулём в опись не идут: строка «этого товара здесь ноль» на ярлыке
 * короба не значит ничего, а место занимает.
 */
export function containerContents(
  count: InventoryCount,
  containerId: string,
): ContainerContents | null {
  const found = findContainer(count, containerId)
  if (!found) return null

  const rows: ContentsRow[] = []
  for (const product of collectProducts(found.node)) {
    const counted = product.actual !== null
    const quantity = counted ? (product.actual as number) : expectedNow(product)
    if (quantity <= 0) continue
    rows.push({
      photoUrl: product.photoUrl,
      name: product.name,
      size: product.wbSize ?? null,
      barcode: product.wbBarcode ?? product.barcode ?? null,
      vendorCode: product.wbVendorCode ?? null,
      quantity,
      fromLedger: !counted,
    })
  }

  rows.sort((a, b) => {
    const byName = a.name.localeCompare(b.name, 'ru')
    if (byName !== 0) return byName
    return (a.size ?? '').localeCompare(b.size ?? '', 'ru', { numeric: true })
  })

  const sellers = new Set(collectProducts(found.node).map((product) => product.seller))
  const seller =
    sellers.size === 1 ? ([...sellers][0] as string) : `Несколько селлеров: ${sellers.size}`

  return {
    kind: found.node.kind,
    label: found.node.barcode ?? found.node.code,
    treeCode: `${KIND_TITLE[found.node.kind]} ${found.node.code}`,
    cellLabel: found.cellLabel,
    seller,
    rows,
    totalPieces: rows.reduce((sum, row) => sum + row.quantity, 0),
  }
}
