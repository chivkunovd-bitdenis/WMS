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

/**
 * Что сейчас открыто у сканера.
 *
 * Тара и ячейка — два уровня одного и того же: «куда я сейчас складываю пики».
 * Открыт короб — пики идут в короб. Короб закрыли — остаётся его ячейка, и пики
 * идут в неё россыпью. Именно поэтому закрытие короба не сбрасывает место
 * целиком: оператор пикнул короб второй раз, чтобы считать россыпь ЗДЕСЬ, а не
 * чтобы система забыла, где он стоит.
 */
export type ScanOpenPlace = {
  containerId: string | null
  cellId: string | null
}

export const NOTHING_OPEN: ScanOpenPlace = { containerId: null, cellId: null }

/**
 * Строка дерева «Без ячеек» — не ячейка.
 *
 * Под ней сервер собирает две вещи: товар, лежащий россыпью без адреса, и тару,
 * которая стоит не в ячейке. Идентификатор у неё — слово, а не ссылка на место,
 * поэтому наружу его отдавать нельзя: сервер такую «ячейку» не найдёт.
 */
export const UNASSIGNED_CELL_ID = 'unassigned'

function realCellId(cellId: string | null): string | null {
  return cellId && cellId !== UNASSIGNED_CELL_ID ? cellId : null
}

export type ScanResult = {
  count: InventoryCount
  /** Что осталось открытым после этого скана. */
  open: ScanOpenPlace
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
    /** Все прочтения кода: как пришло со сканера и как в латинской раскладке. */
    barcodes: string[]
    /** Ячейка, если она открыта. null — россыпь без ячейки или адрес берётся у тары. */
    cellId: string | null
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
  kind: ContainerKind
  code: string
  cellId: string
  pathKeys: string[]
}

/** Найденная ячейка: её тоже можно открыть сканом, как и тару. */
type FoundCell = { id: string; label: string; pathKeys: string[] }

/** Тара, ячейка и товары ищутся одним обходом; на 1000 строках второго прохода нет. */
function findScanTargets(
  count: InventoryCount,
  normalizedCodes: Set<string>,
): {
  container: FoundContainer | null
  /** Тара, найденная только по видимому номеру, когда таких нашлось несколько. */
  ambiguousContainers: FoundContainer[]
  cell: FoundCell | null
  products: Located[]
} {
  let container: FoundContainer | null = null
  // Штрихкод уникален, видимый номер — нет. Номер короба уникален внутри
  // приёмки, а не склада: на бою есть восемь пар коробов с одним номером в
  // одном складе, у номера «1» — одиннадцать носителей. Открыть «первый
  // попавшийся» нельзя: находка ляжет в чужую тару, и на бумаге товар окажется
  // не там, где он лежит. Поэтому совпадения по номеру собираем все.
  const byVisibleCode: FoundContainer[] = []
  let cell: FoundCell | null = null
  const products: Located[] = []
  function walk(nodes: InventoryNode[], cellId: string, containerId: string | null, pathKeys: string[]) {
    for (const node of nodes) {
      const key = `${node.kind}:${node.id}`
      const nextPath = [...pathKeys, key]
      if (node.kind === 'product') {
        if (productMatches(node, normalizedCodes)) {
          products.push({ product: node, containerId, pathKeys: nextPath })
        }
        continue
      }
      const found = { id: node.id, kind: node.kind, code: node.code, cellId, pathKeys: nextPath }
      if (!container && matchesPlace(normalizedCodes, node.barcode)) {
        // Штрихкод — точный адрес, он всегда важнее номера на ярлыке.
        container = found
      } else if (matchesPlace(normalizedCodes, node.code)) {
        byVisibleCode.push(found)
      }
      walk(node.children, cellId, node.id, nextPath)
    }
  }
  for (const item of count.cells) {
    const cellKey = `cell:${item.id}`
    if (!cell && matchesPlace(normalizedCodes, item.barcode, item.label)) {
      cell = { id: item.id, label: item.label, pathKeys: [cellKey] }
    }
    walk(item.children, item.id, null, [cellKey])
  }
  if (!container) {
    // Тара, пустая по документу, в дерево не попадает — иначе пересчёт по
    // складу превращается в стену строк «0 из 0». Но пикнуть её оператор
    // должен: он подошёл к коробу, а в нём лежит то, чего по учёту тут нет.
    for (const item of count.scannableContainers) {
      const found = {
        id: item.id,
        kind: item.kind,
        code: item.code,
        cellId: item.cellId ?? UNASSIGNED_CELL_ID,
        // Строки в дереве у такой тары нет, подсвечивать нечего.
        pathKeys: [`cell:${item.cellId ?? UNASSIGNED_CELL_ID}`],
      }
      if (!container && matchesPlace(normalizedCodes, item.barcode)) container = found
      else if (matchesPlace(normalizedCodes, item.code)) byVisibleCode.push(found)
    }
  }
  if (!container && byVisibleCode.length === 1) {
    container = byVisibleCode[0]
  }
  if (!cell) {
    // Ячейки, пустые по учёту, в дерево не попадают, но сканер обязан их знать:
    // именно в такой чаще всего и находят то, чего по учёту тут нет.
    const empty = count.scannableCells.find(
      (item) => matchesPlace(normalizedCodes, item.barcode, item.label),
    )
    if (empty) cell = { id: empty.id, label: empty.label, pathKeys: [`cell:${empty.id}`] }
  }
  return {
    container,
    ambiguousContainers: container ? [] : byVisibleCode,
    cell,
    products,
  }
}

/**
 * Узнаём место и по штрихкоду, и по видимому номеру.
 *
 * У приёмочного короба штрихкод внутренний — вида INB-1B7EE88D369F, — а на
 * ярлыке человек читает «КР-000108». Если системный ярлык на короб не наклеен
 * (пришёл чужой короб, ярлык отвалился, распечатать не успели), открыть его
 * было нечем: сканер знал только внутренний код, а видимый номер не понимал.
 * Посчитать содержимое такого короба становилось невозможно вовсе.
 */
function matchesPlace(
  normalizedCodes: Set<string>,
  ...identifiers: Array<string | null | undefined>
): boolean {
  return identifiers.some((identifier) => {
    const normalized = identifier?.trim().toLowerCase()
    return Boolean(normalized && normalizedCodes.has(normalized))
  })
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

/**
 * Куда записать находку.
 *
 * Открыта тара — в неё. Открыта ячейка — в неё россыпью. Ничего не открыто, но
 * в документе одна ячейка — в неё. Иначе места нет, и выдумывать его нельзя:
 * записанная не туда находка испортит остаток чужой ячейки.
 */
function foundPlace(
  count: InventoryCount,
  open: ScanOpenPlace,
): { cellId: string | null; containerKind: ContainerKind | null; containerId: string | null } | null {
  if (open.containerId) {
    const kind = containerKindOf(count, open.containerId)
    if (!kind) return null
    // Ячейку тары сервер возьмёт из её карточки: палета или грузоместо могут
    // стоять без ячейки, и знать об этом должна карточка, а не экран.
    return { cellId: null, containerKind: kind, containerId: open.containerId }
  }
  return { cellId: realCellId(open.cellId), containerKind: null, containerId: null }
}

function containerKindOf(count: InventoryCount, containerId: string): ContainerKind | null {
  let kind: ContainerKind | null = null
  function walk(nodes: InventoryNode[]) {
    for (const node of nodes) {
      if (node.kind === 'product') continue
      if (node.id === containerId) {
        kind = node.kind
        return
      }
      walk(node.children)
    }
  }
  for (const cell of count.cells) walk(cell.children)
  if (kind) return kind
  // Открытая тара может не иметь строки в дереве — её выбросили как пустую.
  // Без этой ветки находка в такой короб молча не записалась бы.
  return count.scannableContainers.find((item) => item.id === containerId)?.kind ?? null
}

const CLOSED: Record<ContainerKind, string> = {
  pallet: 'закрыта',
  box: 'закрыт',
  cargo_place: 'закрыто',
}

export function applyScan(
  count: InventoryCount,
  rawCode: string,
  open: ScanOpenPlace,
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
    return { count, open, message: '', tone: 'ok' }
  }

  const normalizedCodes = new Set(codes.map((candidate) => candidate.toLowerCase()))
  const targets = findScanTargets(count, normalizedCodes)

  // Номер на ярлыке оказался не адресом, а совпадением: под ним в этом
  // документе стоит несколько коробов. Открыть наугад — значит записать
  // находку в чужую тару, и товар на бумаге окажется не там, где лежит.
  // Честнее остановиться и попросить штрихкод: он один на всю систему.
  if (targets.ambiguousContainers.length > 1) {
    const codes = targets.ambiguousContainers
      .map((item) => KIND_TITLE[item.kind])
      .filter((title, index, all) => all.indexOf(title) === index)
      .join(' и ')
    return {
      count,
      open,
      message:
        `Номер ${code} носит ${targets.ambiguousContainers.length} шт. тары (${codes}) — `
        + 'какую именно открыть, по номеру не понять. Отсканируйте штрихкод с ярлыка.',
      tone: 'error',
    }
  }

  const container = targets.container
  if (container) {
    if (container.id === open.containerId) {
      // Повторный скан той же тары закрывает её, но ячейку под ней оставляет
      // открытой: оператор пикнул короб второй раз именно затем, чтобы считать
      // россыпь ЗДЕСЬ, а не чтобы система забыла, где он стоит.
      return {
        count,
        open: { containerId: null, cellId: container.cellId },
        focusRowKey: `cell:${container.cellId}`,
        message: `${KIND_TITLE[container.kind]} ${container.code} ${CLOSED[container.kind]}. Пики идут россыпью в эту ячейку.`,
        tone: 'ok',
      }
    }
    return {
      count,
      open: { containerId: container.id, cellId: container.cellId },
      focusRowKey: `${container.kind}:${container.id}`,
      focusPathKeys: container.pathKeys,
      message: `${KIND_TITLE[container.kind]} ${container.code} ${OPENED[container.kind]}. Пикайте товар — каждый пик добавит штуку.`,
      tone: 'ok',
    }
  }

  const cell = targets.cell
  if (cell) {
    if (cell.id === open.cellId && !open.containerId) {
      return {
        count,
        open: NOTHING_OPEN,
        message: `Ячейка ${cell.label} закрыта.`,
        tone: 'ok',
      }
    }
    return {
      count,
      open: { containerId: null, cellId: cell.id },
      focusRowKey: `cell:${cell.id}`,
      focusPathKeys: cell.pathKeys,
      message: `Ячейка ${cell.label} открыта. Пики идут россыпью в неё; чтобы считать тару, отсканируйте её.`,
      tone: 'ok',
    }
  }

  const byBarcode = targets.products
  const place = allowFound ? foundPlace(count, open) : null

  if (byBarcode.length === 0) {
    if (!place) {
      return {
        count,
        open,
        message: `Код ${code} в этом документе не числится. Находку вносят в полном документе инвентаризации.`,
        tone: 'warn',
      }
    }
    return {
      count,
      open,
      message: `Код ${code} — записываем находку сюда.`,
      tone: 'ok',
      found: { barcodes: codes, ...place },
    }
  }

  if (open.containerId) {
    const inside = byBarcode.find((item) => item.containerId === open.containerId)
    if (inside) {
      return {
        count: bump(count, inside.product),
        open,
        focusRowKey: `product:${inside.product.id}`,
        focusPathKeys: inside.pathKeys,
        message: scannedMessage(inside.product),
        tone: 'ok',
      }
    }
    const openName = containerName(count, open.containerId)
    if (!place) {
      return {
        count,
        open,
        message: `${byBarcode[0].product.name} — числится не здесь. Находку вносят в полном документе инвентаризации.`,
        tone: 'warn',
      }
    }
    return {
      count,
      open,
      message: `${byBarcode[0].product.name} — записываем находку в ${openName}.`,
      tone: 'ok',
      found: { barcodes: codes, ...place },
    }
  }

  // Тара не открыта: считаем россыпь. Строка россыпи в открытой ячейке — самый
  // частый случай, поэтому ищем сначала её.
  // Россыпь ищем ровно в открытом месте: открыта ячейка — в ней, не открыто
  // ничего — в «Без ячеек». Иначе пик засчитался бы в чужую ячейку.
  const looseCell = open.cellId ?? UNASSIGNED_CELL_ID
  const loose = byBarcode.find(
    (item) => item.containerId === null && looseCellOf(count, item) === looseCell,
  )
  if (loose) {
    return {
      count: bump(count, loose.product),
      open,
      focusRowKey: `product:${loose.product.id}`,
      focusPathKeys: loose.pathKeys,
      message: scannedMessage(loose.product),
      tone: 'ok',
    }
  }

  // Товар по учёту лежит в таре, а оператор считает его россыпью. Это законная
  // находка — но молчать о ней нельзя: если он просто забыл пикнуть короб,
  // строка короба останется непосчитанной, и один товар посчитается дважды.
  if (!place) {
    return {
      count,
      open,
      message: `${byBarcode[0].product.name} — числится в другом месте. Находку вносят в полном документе инвентаризации.`,
      tone: 'warn',
    }
  }
  return {
    count,
    open,
    message:
      `${byBarcode[0].product.name} числится в другом месте — записываем находку сюда. `
      + 'Если он лежит в таре, отсканируйте её и посчитайте там.',
    tone: 'warn',
    found: { barcodes: codes, ...place },
  }
}

/** Ячейка, в которой лежит найденная россыпью строка: первый ключ её пути. */
function looseCellOf(count: InventoryCount, located: Located): string | null {
  const first = located.pathKeys[0]
  if (!first || !first.startsWith('cell:')) return null
  const id = first.slice('cell:'.length)
  return count.cells.some((cell) => cell.id === id) ? id : null
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
  if (name !== 'таре') return name
  // Тара, выброшенная из дерева как пустая: имя у неё есть, строки нет.
  const outside = count.scannableContainers.find((item) => item.id === containerId)
  return outside ? `${IN_CONTAINER[outside.kind]} ${outside.code}` : name
}


/** Подпись ячейки для строки сканера: «А-01», а не сырой идентификатор. */
export function cellLabel(count: InventoryCount, cellId: string): string {
  return count.cells.find((cell) => cell.id === cellId)?.label ?? 'ячейке'
}
