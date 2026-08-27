// Заглушка раскладки по ячейкам. Числа выдуманные, но устроены как настоящая
// приёмка: часть товара приехала россыпью, часть в коробах, и часть SKU уже
// лежит на складе с прошлых поставок — именно эта подсказка и меняет работу.

export type SortSource = { kind: 'loose' | 'box'; label: string }

export type AlreadyAt = { cellId: string; code: string; qty: number; warehouseId?: string; warehouseName?: string }

export type SortProduct = {
  id: string
  name: string
  sku: string
  seller: string
  barcode: string
  photo: string | null
  source: SortSource
  /** Сколько приняли по этой строке приёмки. */
  accepted: number
  /** Где этот же товар уже лежит на складе — из карты склада. */
  alreadyAt: AlreadyAt[]
}

export type SortCell = {
  id: string
  code: string
  barcode: string
  /** Что лежит в ячейке до нашей раскладки. */
  occupied: Array<{ name: string; qty: number }>
}

/** Одно положенное: товар, ячейка, сколько. */
export type Placement = { productId: string; cellId: string; qty: number }

function photo(background: string, accent: string, letters: string): string {
  const svg = `<svg xmlns="http://www.w3.org/2000/svg" width="240" height="240">
    <rect width="240" height="240" fill="${background}"/>
    <circle cx="120" cy="96" r="54" fill="${accent}" opacity="0.85"/>
    <rect x="42" y="162" width="156" height="42" rx="12" fill="${accent}" opacity="0.55"/>
    <text x="120" y="116" font-family="Inter, sans-serif" font-size="52" font-weight="700"
      fill="${background}" text-anchor="middle">${letters}</text>
  </svg>`
  return `data:image/svg+xml;utf8,${encodeURIComponent(svg.replace(/\s+/g, ' '))}`
}

export const CELLS: SortCell[] = [
  { id: 'c-a11', code: 'А 1.1', barcode: '2000000000114', occupied: [{ name: 'Футболка хлопок белая, M', qty: 24 }] },
  { id: 'c-a12', code: 'А 1.2', barcode: '2000000000121', occupied: [{ name: 'Носки спортивные, 3 пары', qty: 60 }] },
  { id: 'c-a13', code: 'А 1.3', barcode: '2000000000138', occupied: [] },
  { id: 'c-a21', code: 'А 2.1', barcode: '2000000000213', occupied: [] },
  { id: 'c-b11', code: 'Б 1.1', barcode: '2000000000411', occupied: [{ name: 'Кроссовки беговые, 42', qty: 36 }] },
  { id: 'c-b12', code: 'Б 1.2', barcode: '2000000000428', occupied: [] },
]

export const PRODUCTS: SortProduct[] = [
  {
    id: 'p-tshirt',
    name: 'Футболка хлопок белая, M',
    sku: 'TS-WHT-M',
    seller: 'ИП Горячкина',
    barcode: '4680123456789',
    photo: photo('#e2e8f0', '#5b21b6', 'ФБ'),
    source: { kind: 'loose', label: 'Россыпь' },
    accepted: 48,
    alreadyAt: [{ cellId: 'c-a11', code: 'А 1.1', qty: 24 }],
  },
  {
    id: 'p-hoodie',
    name: 'Худи оверсайз серое, L',
    sku: 'HD-GRY-L',
    seller: 'ИП Горячкина',
    barcode: '4680123456796',
    photo: photo('#ede9fe', '#4c1d95', 'ХД'),
    source: { kind: 'box', label: 'Короб №3' },
    accepted: 30,
    alreadyAt: [],
  },
  {
    id: 'p-sneakers',
    name: 'Кроссовки беговые, 42',
    sku: 'SN-RUN-42',
    seller: 'ООО Ситипак',
    barcode: '4600987654321',
    photo: photo('#e0f2fe', '#0369a1', 'КР'),
    source: { kind: 'loose', label: 'Россыпь' },
    accepted: 24,
    alreadyAt: [{ cellId: 'c-b11', code: 'Б 1.1', qty: 36 }],
  },
  {
    id: 'p-socks',
    name: 'Носки спортивные, 3 пары',
    sku: 'SK-SPT-3',
    seller: 'ООО Ситипак',
    barcode: '4600987654338',
    photo: photo('#dcfce7', '#15803d', 'НС'),
    source: { kind: 'box', label: 'Короб №5' },
    accepted: 90,
    alreadyAt: [{ cellId: 'c-a12', code: 'А 1.2', qty: 60 }],
  },
  {
    id: 'p-mug',
    name: 'Термокружка 450 мл',
    sku: 'MG-450',
    seller: 'ИП Ларин',
    barcode: '4601122334455',
    photo: photo('#fef3c7', '#a16207', 'ТК'),
    source: { kind: 'loose', label: 'Россыпь' },
    accepted: 12,
    alreadyAt: [],
  },
]

export function placedFor(placements: Placement[], productId: string): number {
  return placements
    .filter((one) => one.productId === productId)
    .reduce((sum, one) => sum + one.qty, 0)
}

export function placementsInCell(placements: Placement[], cellId: string): Placement[] {
  return placements.filter((one) => one.cellId === cellId)
}

export function remainingFor(product: SortProduct, placements: Placement[]): number {
  return product.accepted - placedFor(placements, product.id)
}

export function totalRemaining(products: SortProduct[], placements: Placement[]): number {
  return products.reduce((sum, product) => sum + remainingFor(product, placements), 0)
}

export function totalAccepted(products: SortProduct[]): number {
  return products.reduce((sum, product) => sum + product.accepted, 0)
}

export function findByBarcode(code: string): { kind: 'cell' | 'product'; id: string } | null {
  const needle = code.trim().toLowerCase()
  const cell = CELLS.find((one) => one.barcode.toLowerCase() === needle)
  if (cell) return { kind: 'cell', id: cell.id }
  const product = PRODUCTS.find(
    (one) => one.barcode.toLowerCase() === needle || one.sku.toLowerCase() === needle,
  )
  if (product) return { kind: 'product', id: product.id }
  return null
}

// --- палеты и короба -------------------------------------------------------

export type ContainerKind = 'pallet' | 'box'

/** Палета или короб, созданные при раскладке. Родитель — ячейка или палета. */
export type Container = {
  id: string
  kind: ContainerKind
  code: string
  parentId: string
}

/** Место, куда можно положить: ячейка, палета или короб. */
export type PlaceRef = { id: string; code: string; kind: 'cell' | ContainerKind }

/** Что сейчас несут рукой. */
export type Carried =
  | { kind: 'product'; product: SortProduct }
  | { kind: 'container'; container: Container }

export const CONTAINER_TITLE: Record<ContainerKind, string> = {
  pallet: 'Палета',
  box: 'Короб',
}

export const INITIAL_CONTAINERS: Container[] = [
  { id: 'plt-1', kind: 'pallet', code: 'П-000131', parentId: 'c-a11' },
  { id: 'box-1', kind: 'box', code: 'КР-000472', parentId: 'plt-1' },
  { id: 'box-2', kind: 'box', code: 'КР-000473', parentId: 'c-a12' },
]

/**
 * Что можно положить в это место.
 *
 * Правила складские: товар ложится куда угодно, короб — на ячейку или на
 * палету, палета — только на ячейку. Внутрь самой себя не кладётся ничего.
 */
export function canDropInto(carried: Carried, place: PlaceRef, containers: Container[]): boolean {
  if (carried.kind === 'product') return true
  const moving = carried.container
  if (moving.id === place.id) return false
  if (moving.parentId === place.id) return false
  // Нельзя положить палету внутрь короба, который лежит на ней самой.
  let cursor: string | undefined = place.id
  const byId = new Map(containers.map((one) => [one.id, one]))
  while (cursor) {
    if (cursor === moving.id) return false
    cursor = byId.get(cursor)?.parentId
  }
  if (moving.kind === 'pallet') return place.kind === 'cell'
  return place.kind === 'cell' || place.kind === 'pallet'
}

/** Где можно создать что: в коробе не создают ничего, на палете — только короб. */
export function creatableIn(place: PlaceRef): ContainerKind[] {
  if (place.kind === 'cell') return ['pallet', 'box']
  if (place.kind === 'pallet') return ['box']
  return []
}

/** Суммарное количество в контейнере вместе со вложенными. */
export function containerQty(
  containerId: string,
  placements: Placement[],
  containers: Container[],
): number {
  const own = placements
    .filter((one) => one.cellId === containerId)
    .reduce((sum, one) => sum + one.qty, 0)
  const inner = containers
    .filter((one) => one.parentId === containerId)
    .reduce((sum, one) => sum + containerQty(one.id, placements, containers), 0)
  return own + inner
}
