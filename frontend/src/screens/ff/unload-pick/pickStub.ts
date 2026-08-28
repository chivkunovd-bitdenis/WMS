import { CELLS, KIND_TITLE, cellRef, objRef } from '../sorting-objects/objectsStub'
import type { Cell, GoodsLine, Holder, ObjKind, WarehouseObject } from '../sorting-objects/objectsStub'

// Подбор на отгрузку: товар снимается не только с ячейки, но и с палеты, короба
// и грузоместа.
//
// Модель мест — ровно та же, что на раскладке, и взята оттуда импортом, а не
// переписана заново: две правды о том, где лежит товар, разъезжаются на первой
// же правке. Правило простое и другого в модели нет: у палеты, короба и
// грузоместа либо есть ячейка, либо её нет. Есть — всё, что внутри, лежит в
// этой ячейке. Нет — объект висит без ячейки, и товар с него снимается точно
// так же.

export { KIND_TITLE, cellRef, objRef }
export type { Cell, GoodsLine, Holder, ObjKind, WarehouseObject }

export type PickProduct = {
  id: string
  name: string
  sku: string
  barcode: string
  photo: string
  /** Размер с карточки маркетплейса. Есть не у всякого товара. */
  size: string | null
}

/** Строка плана отгрузки: сколько штук маркетплейс ждёт от нас. */
export type PlanLine = { id: string; productId: string; plan: number }

function photo(letters: string): string {
  const svg = `<svg xmlns="http://www.w3.org/2000/svg" width="240" height="240">
    <rect width="240" height="240" fill="#eef1f6"/>
    <rect x="48" y="60" width="144" height="120" rx="10" fill="#c7cedb"/>
    <text x="120" y="141" font-family="Inter, sans-serif" font-size="46" font-weight="700"
      fill="#5a6478" text-anchor="middle">${letters}</text>
  </svg>`
  return `data:image/svg+xml;utf8,${encodeURIComponent(svg.replace(/\s+/g, ' '))}`
}

// Одна отгрузка — один продавец: маркетплейс принимает поставку от конкретного
// продавца, и мешать в одном документе чужие товары нечем.
export const SELLER = 'ИП Горячкина'
export const DOCUMENT = 'Отгрузка №4471 в Wildberries от 28.08.2026'

export const PRODUCTS: PickProduct[] = [
  { id: 'p-tshirt', name: 'Футболка хлопок белая, M', sku: 'TS-WHT-M', barcode: '4680123456789', photo: photo('ФБ'), size: 'M' },
  { id: 'p-hoodie', name: 'Худи оверсайз серое, L', sku: 'HD-GRY-L', barcode: '4680123456796', photo: photo('ХД'), size: 'L' },
  { id: 'p-jeans', name: 'Джинсы прямые синие, 32', sku: 'JN-BLU-32', barcode: '4680123456802', photo: photo('ДЖ'), size: '32' },
  { id: 'p-socks', name: 'Носки спортивные, 3 пары', sku: 'SK-SPT-3', barcode: '4680123456819', photo: photo('НС'), size: null },
  { id: 'p-cap', name: 'Кепка бейсболка чёрная', sku: 'CP-BLK', barcode: '4680123456826', photo: photo('КП'), size: null },
  { id: 'p-belt', name: 'Ремень кожаный, 110 см', sku: 'BL-110', barcode: '4680123456833', photo: photo('РМ'), size: '110' },
]

export function productById(id: string): PickProduct {
  return PRODUCTS.find((one) => one.id === id)!
}

export const PICK_CELLS: Cell[] = CELLS

// Что стоит на складе к моменту подбора. Часть объектов на ячейках, часть —
// без ячеек: короб КР-000480 и палета П-000140 стоят в проходе, товар с них
// снимается так же, как с полки.
export const OBJECTS: WarehouseObject[] = [
  { id: 'plt-131', kind: 'pallet', code: 'П-000131', barcode: '2100000001311', holder: cellRef('c-a11') },
  { id: 'box-472', kind: 'box', code: 'КР-000472', barcode: '2200000004723', holder: objRef('plt-131') },
  { id: 'box-480', kind: 'box', code: 'КР-000480', barcode: '2200000004807', holder: null },
  { id: 'plt-140', kind: 'pallet', code: 'П-000140', barcode: '2100000001403', holder: null },
  { id: 'cp-318', kind: 'cargo_place', code: 'ГМ-000318', barcode: '2300000003185', holder: cellRef('c-a12') },
]

// Где физически лежит товар. Держатель у строки один — тот самый нижний объект
// или ячейка, где товар реально руками берут. Ячейку по цепочке вычисляем, а не
// храним второй раз.
export const STOCK: GoodsLine[] = [
  // Футболка лежит тремя местами сразу — и в коробе на палете, и россыпью на
  // той же палете, и в коробе без ячейки. Ради этого случая и затевался экран.
  { id: 's-1', productId: 'p-tshirt', qty: 24, holder: objRef('box-472') },
  { id: 's-2', productId: 'p-tshirt', qty: 10, holder: objRef('plt-131') },
  { id: 's-3', productId: 'p-tshirt', qty: 6, holder: objRef('box-480') },
  // Худи — одно место, выбирать не из чего: снимается сразу по пику.
  { id: 's-4', productId: 'p-hoodie', qty: 16, holder: objRef('box-472') },
  // Джинсы — россыпью прямо в ячейке и на палете, которая стоит без ячейки.
  { id: 's-5', productId: 'p-jeans', qty: 30, holder: cellRef('c-b11') },
  { id: 's-6', productId: 'p-jeans', qty: 12, holder: objRef('plt-140') },
  // Носки — только в коробе без ячейки.
  { id: 's-7', productId: 'p-socks', qty: 90, holder: objRef('box-480') },
  // Ремень — в грузоместе, которое стоит на ячейке А 1.2.
  { id: 's-8', productId: 'p-belt', qty: 14, holder: objRef('cp-318') },
  // Кепки на складе нет вовсе — строка плана останется несобранной.
]

export const PLAN: PlanLine[] = [
  { id: 'pl-1', productId: 'p-tshirt', plan: 30 },
  { id: 'pl-2', productId: 'p-hoodie', plan: 16 },
  { id: 'pl-3', productId: 'p-jeans', plan: 12 },
  { id: 'pl-4', productId: 'p-socks', plan: 50 },
  { id: 'pl-5', productId: 'p-cap', plan: 6 },
  { id: 'pl-6', productId: 'p-belt', plan: 8 },
]
