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
  /** Строка тары или товара, которую экран должен раскрыть, показать и подсветить. */
  focusRowKey?: string
  /** Уже найденный при скане путь: повторно обходить всё дерево экрану не нужно. */
  focusPathKeys?: string[]
  /** Сервер должен создать отсутствующую строку в уже открытой таре. */
  ensureProductLine?: {
    containerKind: 'pallet' | 'box' | 'cargo_place'
    containerId: string
    barcodeCandidates: string[]
    productId?: string
  }
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

function findContainerById(
  count: InventoryCount,
  containerId: string,
): { kind: 'pallet' | 'box' | 'cargo_place'; id: string } | null {
  let found: { kind: 'pallet' | 'box' | 'cargo_place'; id: string } | null = null
  function walk(nodes: InventoryNode[]) {
    for (const node of nodes) {
      if (node.kind === 'product') continue
      if (node.id === containerId) {
        found = { kind: node.kind, id: node.id }
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

function ensureLineRequest(
  count: InventoryCount,
  activeContainerId: string,
  barcodeCandidates: string[],
  productId?: string,
): ScanResult['ensureProductLine'] | undefined {
  const container = findContainerById(count, activeContainerId)
  if (!container) return undefined
  return {
    containerKind: container.kind,
    containerId: container.id,
    barcodeCandidates,
    ...(productId ? { productId } : {}),
  }
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
    const ensureProductLine = activeContainerId
      ? ensureLineRequest(count, activeContainerId, codes)
      : undefined
    return {
      count,
      activeContainerId,
      ...(ensureProductLine ? { ensureProductLine } : {}),
      message: ensureProductLine
        ? `Добавляем найденный товар в ${containerName(count, activeContainerId as string)}.`
        : `Код ${code} в этом документе не числится. Сначала отсканируйте тару, в которой нашли товар.`,
      tone: ensureProductLine ? 'ok' : 'error',
    }
  }

  if (activeContainerId) {
    const inside = byBarcode.find((item) => item.containerId === activeContainerId)
    if (!inside) {
      const where = byBarcode[0]
      const openName = containerName(count, activeContainerId)
      const ensureProductLine = ensureLineRequest(
        count,
        activeContainerId,
        codes,
        where.product.productId,
      )
      return {
        count,
        activeContainerId,
        ...(ensureProductLine ? { ensureProductLine } : {}),
        message: ensureProductLine
          ? `${where.product.name} найден в ${openName} — добавляем отдельную строку.`
          : `Не удалось определить открытую тару для ${where.product.name}. Отсканируйте тару ещё раз.`,
        tone: ensureProductLine ? 'ok' : 'error',
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
    focusRowKey: `product:${loose.product.id}`,
    focusPathKeys: loose.pathKeys,
    message: scannedMessage(loose.product),
    tone: 'ok',
  }
}

/** Результат уже записанного сервером первого пика новой строки. */
export function confirmedProductScan(
  count: InventoryCount,
  lineId: string,
  activeContainerId: string,
): ScanResult {
  let located: Located | null = null
  function walk(nodes: InventoryNode[], containerId: string | null, pathKeys: string[]) {
    for (const node of nodes) {
      const key = `${node.kind}:${node.id}`
      const nextPath = [...pathKeys, key]
      if (node.kind === 'product') {
        if (node.id === lineId) located = { product: node, containerId, pathKeys: nextPath }
        continue
      }
      walk(node.children, node.id, nextPath)
    }
  }
  for (const cell of count.cells) walk(cell.children, null, [`cell:${cell.id}`])
  if (!located) {
    return {
      count,
      activeContainerId,
      message: 'Товар добавлен, но строка не вернулась с сервера. Обновите документ.',
      tone: 'error',
    }
  }
  const item = located as Located
  return {
    count,
    activeContainerId,
    focusRowKey: `product:${item.product.id}`,
    focusPathKeys: item.pathKeys,
    message: scannedMessageAt(item.product, item.product.actual ?? 0),
    tone: 'ok',
  }
}

function scannedMessage(product: ProductNode): string {
  const now = (product.actual ?? 0) + 1
  return scannedMessageAt(product, now)
}

function scannedMessageAt(product: ProductNode, now: number): string {
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
