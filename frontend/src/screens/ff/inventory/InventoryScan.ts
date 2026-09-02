import type { ContainerKind, InventoryCount, InventoryNode, ProductNode } from './InventoryTypes'
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
  /** Строка тары или товара, которую экран должен раскрыть, показать и подсветить. */
  focusRowKey?: string
  /** Уже найденный при скане путь: повторно обходить всё дерево экрану не нужно. */
  focusPathKeys?: string[]
  message: string
  tone: ScanTone
  /**
   * Находка: товар лежит там, где по учёту его нет.
   *
   * Скан сам строку не создаёт — её заводит сервер, потому что документ и его
   * строки живут на сервере. Экран, получив это поле, дёргает ручку находки и
   * перезагружает документ.
   */
  found?: {
    barcode: string
    storageLocationId: string
    containerKind: ContainerKind | null
    containerId: string | null
  }
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

// Сканер — обычная клавиатура. Если в системе выбрана русская раскладка, он
// печатает кириллицу: вместо Chin-56005 приезжает Сршт-56005, и поиск ничего
// не находит. Оператор при этом видит «код не числится» и думает, что товара
// в документе нет. Переводим раскладку и ищем по обоим вариантам.
const RU_TO_LAT: Record<string, string> = {
  й: 'q', ц: 'w', у: 'e', к: 'r', е: 't', н: 'y', г: 'u', ш: 'i', щ: 'o', з: 'p',
  х: '[', ъ: ']', ф: 'a', ы: 's', в: 'd', а: 'f', п: 'g', р: 'h', о: 'j', л: 'k',
  д: 'l', ж: ';', э: "'", я: 'z', ч: 'x', с: 'c', м: 'v', и: 'b', т: 'n', ь: 'm',
  б: ',', ю: '.', ё: '`',
}

function hasCyrillic(value: string): boolean {
  return /[\u0400-\u04FF]/.test(value)
}

/** Коды-кандидаты: как пришло и как было бы в латинской раскладке. */
export function scanCandidates(rawCode: string): string[] {
  const code = normalize(rawCode)
  if (!code || !hasCyrillic(code)) return code ? [code] : []
  const converted = Array.from(code)
    .map((ch) => {
      const lower = ch.toLowerCase()
      const mapped = RU_TO_LAT[lower]
      if (mapped === undefined) return ch
      return ch === lower ? mapped : mapped.toUpperCase()
    })
    .join('')
  return converted && converted !== code ? [code, converted] : [code]
}

type Located = { product: ProductNode; containerId: string | null; pathKeys: string[] }

/**
 * Полный путь к строке в дереве: ячейка, родительская тара и сама строка.
 *
 * Перед подсветкой путь раскрывается целиком. Иначе факт уже увеличился, но
 * строка товара остаётся внутри свёрнутого короба и оператор видит тот же
 * эффект, что при неработающем скане.
 */
export function inventoryRowPathKeys(count: InventoryCount, targetKey: string): string[] {
  function find(nodes: InventoryNode[]): string[] | null {
    for (const node of nodes) {
      const key = `${node.kind}:${node.id}`
      if (key === targetKey) return [key]
      if (node.kind === 'product') continue
      const nested = find(node.children)
      if (nested) return [key, ...nested]
    }
    return null
  }

  for (const cell of count.cells) {
    const cellKey = `cell:${cell.id}`
    if (cellKey === targetKey) return [cellKey]
    const nested = find(cell.children)
    if (nested) return [cellKey, ...nested]
  }
  return []
}

/** Найденная тара и её уже вычисленный путь в дереве. */
type FoundContainer = {
  id: string
  kind: 'pallet' | 'box' | 'cargo_place'
  code: string
  pathKeys: string[]
}

/** Тара и товары ищутся одним обходом; на 1000 строках второго прохода нет. */
function findScanTargets(
  count: InventoryCount,
  normalizedCodes: Set<string>,
): { container: FoundContainer | null; products: Located[] } {
  let container: FoundContainer | null = null
  const products: Located[] = []
  function walk(nodes: InventoryNode[], containerId: string | null, pathKeys: string[]) {
    for (const node of nodes) {
      const key = `${node.kind}:${node.id}`
      const nextPath = [...pathKeys, key]
      if (node.kind === 'product') {
        if (productMatches(node, normalizedCodes)) {
          products.push({ product: node, containerId, pathKeys: nextPath })
        }
        continue
      }
      if (!container && node.barcode && normalizedCodes.has(node.barcode.trim().toLowerCase())) {
        container = { id: node.id, kind: node.kind, code: node.code, pathKeys: nextPath }
      }
      walk(node.children, node.id, nextPath)
    }
  }
  for (const cell of count.cells) {
    walk(cell.children, null, [`cell:${cell.id}`])
  }
  return { container, products }
}

/** Ячейка и вид открытой тары: находке нужно точное место, а не просто «где-то». */
function locateContainer(
  count: InventoryCount,
  containerId: string,
): { cellId: string; kind: ContainerKind } | null {
  for (const cell of count.cells) {
    let found: ContainerKind | null = null
    const walk = (nodes: InventoryNode[]) => {
      for (const node of nodes) {
        if (node.kind === 'product') continue
        if (node.id === containerId) {
          found = node.kind
          return
        }
        walk(node.children)
      }
    }
    walk(cell.children)
    if (found) return { cellId: cell.id, kind: found }
  }
  return null
}

/** Единственная ячейка документа: только тогда россыпь можно записать без вопросов. */
function soleCellId(count: InventoryCount): string | null {
  return count.cells.length === 1 ? count.cells[0].id : null
}

/** Пик увеличивает факт на единицу: человек считает штуками, а не вводит итог. */
function bump(count: InventoryCount, product: ProductNode): InventoryCount {
  return setActual(count, product.id, (product.actual ?? 0) + 1)
}

/** ШК WB — основной код, SKU — код на внутренней этикетке при отсутствии ШК WB. */
function productMatches(product: ProductNode, normalizedCodes: Set<string>): boolean {
  return [product.barcode, product.wbBarcode, product.sku].some((identifier) => {
    const normalized = identifier?.trim().toLowerCase()
    return Boolean(normalized && normalizedCodes.has(normalized))
  })
}

export function applyScan(
  count: InventoryCount,
  rawCode: string,
  activeContainerId: string | null,
  /**
   * Разрешено ли записывать находки.
   *
   * Строку находки заводит сервер, поэтому экран, у которого нет доступа к нему
   * (компактный диалог с карты склада), находку записать не может. Обещать
   * оператору «записываем» и ничего не записать — хуже, чем честно сказать, что
   * находку вносят в полном документе.
   */
  allowFound = true,
): ScanResult {
  const codes = scanCandidates(rawCode)
  const code = codes[0] ?? ''
  if (!code) {
    return { count, activeContainerId, message: '', tone: 'ok' }
  }

  const normalizedCodes = new Set(codes.map((candidate) => candidate.toLowerCase()))
  const targets = findScanTargets(count, normalizedCodes)
  const container = targets.container
  if (container) {
    if (container.id === activeContainerId) {
      // Повторный скан той же тары закрывает её. До 02.09.2026 система советовала
      // «закройте тару, чтобы считать россыпь», а способа закрыть не было ни
      // сканом, ни кнопкой — оператор выходил из документа и заходил заново.
      return {
        count,
        activeContainerId: null,
        focusRowKey: `${container.kind}:${container.id}`,
        focusPathKeys: container.pathKeys,
        message: `${KIND_TITLE[container.kind]} ${container.code} закрыт${container.kind === 'pallet' ? 'а' : container.kind === 'cargo_place' ? 'о' : ''}. Следующие пики считают россыпь.`,
        tone: 'ok',
      }
    }
    return {
      count,
      activeContainerId: container.id,
      focusRowKey: `${container.kind}:${container.id}`,
      focusPathKeys: container.pathKeys,
      message: `${KIND_TITLE[container.kind]} ${container.code} ${OPENED[container.kind]}. Пикайте товар — каждый пик добавит штуку.`,
      tone: 'ok',
    }
  }

  const byBarcode = targets.products

  if (byBarcode.length === 0) {
    const place = allowFound ? foundPlace(count, activeContainerId) : null
    if (!place) {
      return {
        count,
        activeContainerId,
        message: allowFound
          ? `Код ${code} в этом документе не числится. Отсканируйте тару или ячейку, куда его записать.`
          : `Код ${code} в этом документе не числится. Находку вносят в полном документе инвентаризации.`,
        tone: 'warn',
      }
    }
    return {
      count,
      activeContainerId,
      message: `Код ${code} по учёту здесь не числится — записываем как находку.`,
      tone: 'ok',
      found: { barcode: code, ...place },
    }
  }

  if (activeContainerId) {
    const inside = byBarcode.find((item) => item.containerId === activeContainerId)
    if (!inside) {
      const where = byBarcode[0]
      const openName = containerName(count, activeContainerId)
      const place = allowFound ? foundPlace(count, activeContainerId) : null
      return {
        count,
        activeContainerId,
        message: place
          ? `${where.product.name} по учёту в ${openName} не числится — записываем как находку.`
          : `${where.product.name} — числится не здесь. Отсканируйте тару, куда его записать.`,
        tone: place ? 'ok' : 'warn',
        ...(place ? { found: { barcode: code, ...place } } : {}),
      }
    }
    const next = bump(count, inside.product)
    return {
      count: next,
      activeContainerId,
      focusRowKey: `product:${inside.product.id}`,
      focusPathKeys: inside.pathKeys,
      message: scannedMessage(inside.product),
      tone: 'ok',
    }
  }

  const loose = byBarcode.find((item) => item.containerId === null)
  if (!loose) {
    const place = allowFound ? foundPlace(count, null) : null
    if (!place) {
      // Ровно тот случай, который назвал владелец: товар есть, но он в таре.
      return {
        count,
        activeContainerId,
        message: `${byBarcode[0].product.name} — лежит в таре. Отсканируйте тару.`,
        tone: 'warn',
      }
    }
    return {
      count,
      activeContainerId,
      message: `${byBarcode[0].product.name} по учёту лежит в таре — записываем находку россыпью.`,
      tone: 'ok',
      found: { barcode: code, ...place },
    }
  }
  return {
    count: bump(count, loose.product),
    activeContainerId,
    focusRowKey: `product:${loose.product.id}`,
    focusPathKeys: loose.pathKeys,
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


/**
 * Куда записать находку.
 *
 * Открыта тара — в неё. Тары нет, но в документе одна ячейка — в эту ячейку.
 * Ячеек несколько и тара не открыта — места нет, и выдумывать его нельзя:
 * записанная не туда находка испортит остаток чужой ячейки.
 */
function foundPlace(
  count: InventoryCount,
  activeContainerId: string | null,
): { storageLocationId: string; containerKind: ContainerKind | null; containerId: string | null } | null {
  if (activeContainerId) {
    const placed = locateContainer(count, activeContainerId)
    if (!placed) return null
    return {
      storageLocationId: placed.cellId,
      containerKind: placed.kind,
      containerId: activeContainerId,
    }
  }
  const cellId = soleCellId(count)
  if (!cellId) return null
  return { storageLocationId: cellId, containerKind: null, containerId: null }
}
