// Данные и расчёты «пульта перемещений». Это макет-эксперимент: он показывает,
// как мог бы выглядеть склад, если бы система не ждала указаний оператора, а
// сама говорила, что стоит переложить и почему. Ничего из этого пока не
// согласовано и в работу не берётся — сделано, чтобы посмотреть глазами.

export type LabItem = {
  sku: string
  name: string
  qty: number
}

export type LabCell = {
  id: string
  code: string
  /** Номер ряда стеллажей: по нему считается место плитки на плане. */
  row: number
  column: number
  /** Сколько штук физически влезает. Из этого считается заполненность. */
  capacity: number
  /** Сколько шагов от зоны упаковки. Дальняя ячейка дороже в сборке. */
  distance: number
  /** Движений за последние семь дней — «горячая» ячейка или «мёртвая». */
  turnover: number
  items: LabItem[]
}

export type LabMove = {
  fromId: string
  toId: string
  sku: string
  qty: number
}

export type LabAdvice = {
  id: string
  /** Что предлагаем сделать — одной строкой, языком склада. */
  title: string
  /** Почему: то, ради чего оператор нажмёт кнопку. */
  reason: string
  gain: string
  tone: 'stop' | 'warn' | 'ok'
  moves: LabMove[]
}

const NAMES: Record<string, string> = {
  'TS-WHT-M': 'Футболка хлопок белая, M',
  'HD-GRY-L': 'Худи оверсайз серое, L',
  'SN-RUN-42': 'Кроссовки беговые, 42',
  'SK-SPT-3': 'Носки спортивные, 3 пары',
  'MG-450': 'Термокружка 450 мл',
  'BL-110': 'Ремень кожаный, 110 см',
}

export function itemName(sku: string): string {
  return NAMES[sku] ?? sku
}

function item(sku: string, qty: number): LabItem {
  return { sku, name: itemName(sku), qty }
}

const RACKS = ['А', 'Б', 'В']

export function initialCells(): LabCell[] {
  const raw: Array<[number, number, number, number, number, LabItem[]]> = [
    [0, 0, 120, 4, 31, [item('TS-WHT-M', 74), item('MG-450', 18)]],
    [0, 1, 120, 5, 24, [item('SK-SPT-3', 96)]],
    [0, 2, 120, 6, 3, [item('BL-110', 12)]],
    [0, 3, 120, 7, 0, []],
    [0, 4, 120, 8, 17, [item('TS-WHT-M', 22)]],
    [0, 5, 120, 9, 2, [item('HD-GRY-L', 9)]],
    [1, 0, 200, 12, 28, [item('SN-RUN-42', 188)]],
    [1, 1, 200, 13, 11, [item('HD-GRY-L', 64), item('BL-110', 40)]],
    [1, 2, 200, 14, 1, [item('MG-450', 6)]],
    [1, 3, 200, 15, 0, []],
    [1, 4, 200, 16, 9, [item('TS-WHT-M', 31)]],
    [1, 5, 200, 17, 0, []],
    [2, 0, 320, 22, 1, [item('SK-SPT-3', 40)]],
    [2, 1, 320, 23, 0, []],
    [2, 2, 320, 24, 6, [item('SN-RUN-42', 96), item('HD-GRY-L', 120)]],
    [2, 3, 320, 25, 0, []],
    [2, 4, 320, 26, 0, [item('MG-450', 4)]],
    [2, 5, 320, 27, 0, []],
  ]
  return raw.map(([row, column, capacity, distance, turnover, items]) => ({
    id: `c-${row}-${column}`,
    code: `${RACKS[row]} 1.${column + 1}`,
    row,
    column,
    capacity,
    distance,
    turnover,
    items,
  }))
}

export function cellQty(cell: LabCell): number {
  return cell.items.reduce((sum, entry) => sum + entry.qty, 0)
}

export function fillRatio(cell: LabCell): number {
  return cell.capacity === 0 ? 0 : cellQty(cell) / cell.capacity
}

export type LabMetric = 'fill' | 'turnover' | 'distance'

export const METRICS: Array<{ value: LabMetric; label: string; legend: string }> = [
  { value: 'fill', label: 'Заполненность', legend: 'Темнее — ячейка ближе к переполнению' },
  { value: 'turnover', label: 'Оборачиваемость', legend: 'Темнее — чаще берут за последнюю неделю' },
  { value: 'distance', label: 'Дальность', legend: 'Темнее — дальше идти от зоны упаковки' },
]

/** Значение метрики, приведённое к 0..1 — из него берётся насыщенность плитки. */
export function metricValue(cell: LabCell, metric: LabMetric, cells: LabCell[]): number {
  if (metric === 'fill') return Math.min(1, fillRatio(cell))
  if (metric === 'turnover') {
    const max = Math.max(1, ...cells.map((one) => one.turnover))
    return cell.turnover / max
  }
  const max = Math.max(1, ...cells.map((one) => one.distance))
  return cell.distance / max
}

export function metricCaption(cell: LabCell, metric: LabMetric): string {
  if (metric === 'fill') return `${Math.round(fillRatio(cell) * 100)}%`
  if (metric === 'turnover') return `${cell.turnover} движ.`
  return `${cell.distance} шагов`
}

// --- подсказки -------------------------------------------------------------

/**
 * Подсказки считаются из тех же данных, что видит оператор, а не берутся из
 * головы. Каждая обязана назвать выгоду: без неё это не совет, а мнение.
 */
export function advise(cells: LabCell[]): LabAdvice[] {
  const advice: LabAdvice[] = []
  const byId = new Map(cells.map((cell) => [cell.id, cell]))

  // 1. Один товар размазан по нескольким ячейкам — собрать в самую ближнюю.
  const places = new Map<string, LabCell[]>()
  cells.forEach((cell) => {
    cell.items.forEach((entry) => {
      places.set(entry.sku, [...(places.get(entry.sku) ?? []), cell])
    })
  })
  places.forEach((list, sku) => {
    if (list.length < 3) return
    // Целью становится не просто ближняя ячейка, а ближняя из тех, куда всё
    // сведённое физически влезет. Без этой проверки совет набивал ячейку на
    // 121% и следом сам же советовал её разгрузить — то есть гонял товар по кругу.
    const totalOfSku = list.reduce(
      (sum, cell) => sum + (cell.items.find((entry) => entry.sku === sku)?.qty ?? 0),
      0,
    )
    const target = [...list]
      .sort((a, b) => a.distance - b.distance)
      .find((cell) => {
        const own = cell.items.find((entry) => entry.sku === sku)?.qty ?? 0
        const free = cell.capacity - (cellQty(cell) - own)
        return free >= totalOfSku
      })
    if (!target) return
    const sources = list.filter((cell) => cell.id !== target.id)
    const total = sources.reduce(
      (sum, cell) => sum + (cell.items.find((entry) => entry.sku === sku)?.qty ?? 0),
      0,
    )
    advice.push({
      id: `merge-${sku}`,
      title: `Свести «${itemName(sku)}» в ${target.code}`,
      reason: `Один товар лежит в ${list.length} ячейках — сборщик обходит все три вместо одной.`,
      gain: `Минус ${sources.length} подхода, ${total} шт переедет`,
      tone: 'warn',
      moves: sources.map((cell) => ({
        fromId: cell.id,
        toId: target.id,
        sku,
        qty: cell.items.find((entry) => entry.sku === sku)?.qty ?? 0,
      })),
    })
  })

  // 2. Ячейка вот-вот лопнет, а рядом стоит пустая.
  cells
    .filter((cell) => fillRatio(cell) > 0.85)
    .forEach((full) => {
      const free = cells
        .filter((cell) => cellQty(cell) === 0 && cell.row === full.row)
        .sort((a, b) => Math.abs(a.column - full.column) - Math.abs(b.column - full.column))[0]
      if (!free) return
      const biggest = [...full.items].sort((a, b) => b.qty - a.qty)[0]
      if (!biggest) return
      const moved = Math.min(Math.round(biggest.qty / 2), free.capacity)
      advice.push({
        id: `spill-${full.id}`,
        title: `Разгрузить ${full.code} в ${free.code}`,
        reason: `Ячейка занята на ${Math.round(fillRatio(full) * 100)}% — следующая приёмка в неё не влезет.`,
        gain: `Освободится место под ${moved} шт`,
        tone: 'stop',
        moves: [
          { fromId: full.id, toId: free.id, sku: biggest.sku, qty: moved },
        ],
      })
    })

  // 3. Ходовой товар лежит далеко, а близкая ячейка простаивает.
  const hot = [...cells].sort((a, b) => b.turnover - a.turnover)[0]
  if (hot && hot.distance > 10) {
    const biggest = [...hot.items].sort((a, b) => b.qty - a.qty)[0]
    const near = cells
      .filter(
        (cell) =>
          cellQty(cell) === 0 && cell.distance < hot.distance && cell.capacity >= (biggest?.qty ?? 0),
      )
      .sort((a, b) => a.distance - b.distance)[0]
    if (near && biggest) {
      advice.push({
        id: `hot-${hot.id}`,
        title: `Переставить «${itemName(biggest.sku)}» ближе, в ${near.code}`,
        reason: `Это самый ходовой товар недели, а лежит он в ${hot.distance} шагах от упаковки.`,
        gain: `Каждая сборка короче на ${hot.distance - near.distance} шагов`,
        tone: 'ok',
        moves: [{ fromId: hot.id, toId: near.id, sku: biggest.sku, qty: biggest.qty }],
      })
    }
  }

  return advice.filter((one) => one.moves.every((move) => byId.has(move.fromId) && byId.has(move.toId)))
}

export function applyMoves(cells: LabCell[], moves: LabMove[]): LabCell[] {
  let next = cells.map((cell) => ({ ...cell, items: cell.items.map((entry) => ({ ...entry })) }))
  for (const move of moves) {
    next = next.map((cell) => {
      if (cell.id === move.fromId) {
        const items = cell.items
          .map((entry) =>
            entry.sku === move.sku ? { ...entry, qty: entry.qty - move.qty } : entry,
          )
          .filter((entry) => entry.qty > 0)
        return { ...cell, items }
      }
      if (cell.id === move.toId) {
        const twin = cell.items.find((entry) => entry.sku === move.sku)
        const items = twin
          ? cell.items.map((entry) =>
              entry.sku === move.sku ? { ...entry, qty: entry.qty + move.qty } : entry,
            )
          : [...cell.items, item(move.sku, move.qty)]
        return { ...cell, items }
      }
      return cell
    })
  }
  return next
}
