import type { InventoryCount, InventoryNode, ProductNode } from './InventoryTypes'
import { KIND_TITLE } from './InventoryTypes'
import { expectedNow, setActual } from './InventoryRows'

// Сканер на пересчёте.
//
// Правило владельца дословно: «сканирую либо тару, и тогда следующие пики в неё
// и они пишут факт просто поочерёдно, либо сам товар — тогда тот, что вне тары.
// Если вне тары нет, пишет отсканируйте тару».
//
// То есть у сканера есть память на одну вещь: какую тару открыли. Пока она
// открыта, каждый пик товара — это плюс одна штука внутри неё. Открытой тары
// нет — считаем то, что лежит в ячейке россыпью.

export type ScanTone = 'ok' | 'warn' | 'error'

export type ScanResult = {
  count: InventoryCount
  /** Идентификатор открытой тары. null — считаем россыпь. */
  activeContainerId: string | null
  /** Есть только при скане самой тары: экран должен найти и показать её строку. */
  focusContainerKey?: string
  message: string
  tone: ScanTone
}

// «Короб открыт», но «палета открыта» и «грузоместо открыто». Род у слов разный,
// и одна форма на всех выдаёт машинный перевод.
const OPENED: Record<'pallet' | 'box' | 'cargo_place', string> = {
  pallet: 'открыта',
  box: 'открыт',
  cargo_place: 'открыто',
}

function normalize(code: string): string {
  return code.trim()
}

type Located = { product: ProductNode; containerId: string | null }

/** Все товары документа с указанием тары, в которой каждый лежит. */
function locateProducts(count: InventoryCount): Located[] {
  const out: Located[] = []
  function walk(nodes: InventoryNode[], containerId: string | null) {
    for (const node of nodes) {
      if (node.kind === 'product') out.push({ product: node, containerId })
      else walk(node.children, node.id)
    }
  }
  for (const cell of count.cells) walk(cell.children, null)
  return out
}

type FoundContainer = { id: string; kind: 'pallet' | 'box' | 'cargo_place'; code: string }

function findContainer(count: InventoryCount, code: string): FoundContainer | null {
  let found: FoundContainer | null = null
  function walk(nodes: InventoryNode[]) {
    for (const node of nodes) {
      if (node.kind === 'product') continue
      if (node.barcode && node.barcode === code) {
        found = { id: node.id, kind: node.kind, code: node.code }
        return
      }
      walk(node.children)
      if (found) return
    }
  }
  for (const cell of count.cells) {
    walk(cell.children)
    if (found) break
  }
  return found
}

/** Пик увеличивает факт на единицу: человек считает штуками, а не вводит итог. */
function bump(count: InventoryCount, product: ProductNode): InventoryCount {
  return setActual(count, product.id, (product.actual ?? 0) + 1)
}

export function applyScan(
  count: InventoryCount,
  rawCode: string,
  activeContainerId: string | null,
): ScanResult {
  const code = normalize(rawCode)
  if (!code) {
    return { count, activeContainerId, message: '', tone: 'ok' }
  }

  const container = findContainer(count, code)
  if (container) {
    return {
      count,
      activeContainerId: container.id,
      focusContainerKey: `${container.kind}:${container.id}`,
      message: `${KIND_TITLE[container.kind]} ${container.code} ${OPENED[container.kind]}. Пикайте товар — каждый пик добавит штуку.`,
      tone: 'ok',
    }
  }

  const located = locateProducts(count)
  const byBarcode = located.filter((item) => item.product.barcode === code)

  if (byBarcode.length === 0) {
    return {
      count,
      activeContainerId,
      message: `Код ${code} в этом документе не числится. Если товар лежит здесь — это находка, её вносим отдельно.`,
      tone: 'error',
    }
  }

  if (activeContainerId) {
    const inside = byBarcode.find((item) => item.containerId === activeContainerId)
    if (!inside) {
      const where = byBarcode[0]
      const openName = containerName(count, activeContainerId)
      return {
        count,
        activeContainerId,
        message: where.containerId
          ? `${where.product.name} — числится не здесь, а в другой таре. В ${openName} его нет.`
          : `${where.product.name} — числится россыпью, а не в ${openName}. Закройте тару, чтобы считать россыпь.`,
        tone: 'warn',
      }
    }
    const next = bump(count, inside.product)
    return {
      count: next,
      activeContainerId,
      message: scannedMessage(inside.product),
      tone: 'ok',
    }
  }

  const loose = byBarcode.find((item) => item.containerId === null)
  if (!loose) {
    return {
      count,
      activeContainerId,
      // Ровно тот случай, который назвал владелец: товар есть, но он в таре.
      message: `${byBarcode[0].product.name} — лежит в таре. Отсканируйте тару.`,
      tone: 'warn',
    }
  }
  return {
    count: bump(count, loose.product),
    activeContainerId,
    message: scannedMessage(loose.product),
    tone: 'ok',
  }
}

function scannedMessage(product: ProductNode): string {
  const now = (product.actual ?? 0) + 1
  const expected = expectedNow(product)
  const tail =
    now === expected
      ? 'сходится'
      : now > expected
        ? `на ${now - expected} больше, чем числится`
        : `осталось ${expected - now}`
  return `${product.name} — ${now} из ${expected}, ${tail}.`
}

// Предложный падеж: экран пишет «товар в коробе», а не «товар в короб».
// Русский интерфейс, который не склоняет, читается как машинный перевод.
const IN_CONTAINER: Record<'pallet' | 'box' | 'cargo_place', string> = {
  pallet: 'палете',
  box: 'коробе',
  cargo_place: 'грузоместе',
}

export function containerName(count: InventoryCount, containerId: string): string {
  let name = 'таре'
  function walk(nodes: InventoryNode[]) {
    for (const node of nodes) {
      if (node.kind === 'product') continue
      if (node.id === containerId) {
        name = `${IN_CONTAINER[node.kind]} ${node.code}`
        return
      }
      walk(node.children)
    }
  }
  for (const cell of count.cells) walk(cell.children)
  return name
}
