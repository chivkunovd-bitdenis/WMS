// Раскладка объектами: товар лежит в коробе, короб на палете, палета в ячейке.
//
// Ключевое отличие от «раскладки по товарам»: место товара нигде не хранится —
// оно вычисляется по цепочке держателей. Поэтому нельзя рассинхронизировать
// «что в коробе» и «где короб»: это одно и то же знание, записанное один раз.

export type ObjKind = 'pallet' | 'box' | 'cargo_place'

/** Кто держит: объект, ячейка или никто (собрано, но ещё не поставлено). */
export type Holder = string | null

export const KIND_TITLE: Record<ObjKind, string> = {
  pallet: 'Палета',
  box: 'Короб',
  cargo_place: 'Грузоместо',
}

export type WarehouseObject = {
  id: string
  kind: ObjKind
  code: string
  barcode: string
  holder: Holder
}

export type GoodsLine = {
  id: string
  productId: string
  qty: number
  holder: Holder
}

export type Product = {
  id: string
  name: string
  sku: string
  seller: string
  barcode: string
  photo: string
}

export type Cell = { id: string; code: string; barcode: string }

export const objRef = (id: string) => `obj:${id}`
export const cellRef = (id: string) => `cell:${id}`
export const isCellRef = (holder: Holder) => Boolean(holder && holder.startsWith('cell:'))
export const refId = (holder: string) => holder.slice(holder.indexOf(':') + 1)

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

export const PRODUCTS: Product[] = [
  { id: 'p-tshirt', name: 'Футболка хлопок белая, M', sku: 'TS-WHT-M', seller: 'ИП Горячкина', barcode: '4680123456789', photo: photo('#e2e8f0', '#5b21b6', 'ФБ') },
  { id: 'p-hoodie', name: 'Худи оверсайз серое, L', sku: 'HD-GRY-L', seller: 'ИП Горячкина', barcode: '4680123456796', photo: photo('#ede9fe', '#4c1d95', 'ХД') },
  { id: 'p-sneakers', name: 'Кроссовки беговые, 42', sku: 'SN-RUN-42', seller: 'ООО Ситипак', barcode: '4600987654321', photo: photo('#e0f2fe', '#0369a1', 'КР') },
  { id: 'p-socks', name: 'Носки спортивные, 3 пары', sku: 'SK-SPT-3', seller: 'ООО Ситипак', barcode: '4600987654338', photo: photo('#dcfce7', '#15803d', 'НС') },
  { id: 'p-mug', name: 'Термокружка 450 мл', sku: 'MG-450', seller: 'ИП Ларин', barcode: '4601122334455', photo: photo('#fef3c7', '#a16207', 'ТК') },
  { id: 'p-belt', name: 'Ремень кожаный, 110 см', sku: 'BL-110', seller: 'ИП Ларин', barcode: '4601122334462', photo: photo('#fee2e2', '#9f1239', 'РМ') },
]

export const CELLS: Cell[] = [
  { id: 'c-a11', code: 'А 1.1', barcode: '2000000000114' },
  { id: 'c-a12', code: 'А 1.2', barcode: '2000000000121' },
  { id: 'c-a13', code: 'А 1.3', barcode: '2000000000138' },
  { id: 'c-a21', code: 'А 2.1', barcode: '2000000000213' },
  { id: 'c-b11', code: 'Б 1.1', barcode: '2000000000411' },
  { id: 'c-b12', code: 'Б 1.2', barcode: '2000000000428' },
]

// Что пришло с шага упаковки: палета с двумя коробами уже собрана, один короб и
// одно грузоместо стоят отдельно, часть товара приехала россыпью.
export const INITIAL_OBJECTS: WarehouseObject[] = [
  { id: 'plt-131', kind: 'pallet', code: 'П-000131', barcode: '2100000001311', holder: null },
  { id: 'box-472', kind: 'box', code: 'КР-000472', barcode: '2200000004723', holder: objRef('plt-131') },
  { id: 'box-473', kind: 'box', code: 'КР-000473', barcode: '2200000004730', holder: objRef('plt-131') },
  { id: 'box-480', kind: 'box', code: 'КР-000480', barcode: '2200000004807', holder: null },
  { id: 'cp-318', kind: 'cargo_place', code: 'ГМ-000318', barcode: '2300000003185', holder: null },
]

export const INITIAL_LINES: GoodsLine[] = [
  { id: 'l-1', productId: 'p-tshirt', qty: 24, holder: objRef('box-472') },
  { id: 'l-2', productId: 'p-hoodie', qty: 16, holder: objRef('box-472') },
  { id: 'l-3', productId: 'p-sneakers', qty: 30, holder: objRef('box-473') },
  { id: 'l-4', productId: 'p-socks', qty: 90, holder: objRef('box-480') },
  { id: 'l-5', productId: 'p-belt', qty: 14, holder: objRef('cp-318') },
  { id: 'l-6', productId: 'p-mug', qty: 12, holder: null },
  { id: 'l-7', productId: 'p-tshirt', qty: 18, holder: null },
  { id: 'l-8', productId: 'p-socks', qty: 40, holder: null },
]

export function productById(id: string): Product {
  return PRODUCTS.find((one) => one.id === id)!
}

/** Сколько штук внутри объекта — вместе со всем вложенным. */
export function objectQty(
  objectId: string,
  objects: WarehouseObject[],
  lines: GoodsLine[],
): number {
  const own = lines
    .filter((line) => line.holder === objRef(objectId))
    .reduce((sum, line) => sum + line.qty, 0)
  const inner = objects
    .filter((one) => one.holder === objRef(objectId))
    .reduce((sum, one) => sum + objectQty(one.id, objects, lines), 0)
  return own + inner
}

/** Сколько штук стоит на ячейке — считается по составу, а не хранится. */
export function cellQty(cellId: string, objects: WarehouseObject[], lines: GoodsLine[]): number {
  const loose = lines
    .filter((line) => line.holder === cellRef(cellId))
    .reduce((sum, line) => sum + line.qty, 0)
  const inside = objects
    .filter((one) => one.holder === cellRef(cellId))
    .reduce((sum, one) => sum + objectQty(one.id, objects, lines), 0)
  return loose + inside
}

/** Цепочка держателей до ячейки: где физически лежит эта строка товара. */
export function whereIs(
  holder: Holder,
  objects: WarehouseObject[],
  cells: Cell[],
): { cell: Cell | null; path: string[] } {
  const path: string[] = []
  let cursor = holder
  while (cursor) {
    if (isCellRef(cursor)) {
      const cell = cells.find((one) => one.id === refId(cursor!)) ?? null
      return { cell, path }
    }
    const object = objects.find((one) => one.id === refId(cursor!))
    if (!object) return { cell: null, path }
    path.unshift(`${KIND_TITLE[object.kind]} ${object.code}`)
    cursor = object.holder
  }
  return { cell: null, path }
}
