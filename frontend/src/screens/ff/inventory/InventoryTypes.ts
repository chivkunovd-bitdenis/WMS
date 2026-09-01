// Документ инвентаризации: что числится и что реально лежит.
//
// Дерево повторяет карту склада — ячейка, палета, короб, грузоместо, товар, —
// потому что человек считает по местам, а не по списку артикулов. Отличие одно:
// у листа появляется введённое руками число.

export type ContainerKind = 'pallet' | 'box' | 'cargo_place'
export type NodeKind = ContainerKind | 'product'

export const KIND_TITLE: Record<NodeKind, string> = {
  pallet: 'Палета',
  box: 'Короб',
  cargo_place: 'Грузоместо',
  product: 'Товар',
}

export type ProductNode = {
  kind: 'product'
  id: string
  name: string
  sku: string
  seller: string
  category: string
  barcode: string
  /** Поля карточки продавца показываются отдельными прямыми колонками. */
  wbVendorCode?: string | null
  wbBarcode?: string | null
  wbSize?: string | null
  photoUrl: string | null
  /** Что числится в системе на момент наполнения документа. */
  expected: number
  /** Что насчитал человек. null — до этой строки ещё не дошли. */
  actual: number | null
  /**
   * Остаток успел измениться после наполнения документа: товар отгрузили,
   * пока шёл пересчёт. Строка не ломается, но при проведении о ней предупредим.
   */
  expectedNow?: number
}

export type ContainerNode = {
  kind: ContainerKind
  id: string
  code: string
  barcode: string | null
  children: InventoryNode[]
}

export type InventoryNode = ContainerNode | ProductNode

export type CellNode = {
  id: string
  /** «А 1.1». Виртуальная зона «Без ячеек» приходит с этим же типом. */
  label: string
  /** У виртуальной зоны «Без ячеек» штрихкода нет. */
  barcode?: string | null
  children: InventoryNode[]
}

export type CountStatus = 'draft' | 'posted' | 'cancelled'

export type CountFill =
  | { mode: 'object'; objectLabel: string }
  | { mode: 'all' }
  | { mode: 'filters'; seller: string | null; category: string | null }

export type InventoryCount = {
  id: string
  number: string
  status: CountStatus
  warehouseId?: string | null
  warehouseName: string
  fill: CountFill
  createdAt: string
  createdBy: string
  postedAt: string | null
  postedBy: string | null
  comment: string
  /**
   * Адресное хранение включено у арендатора.
   *
   * Выключено — ячеек в системе нет вообще, и показывать их нельзя нигде:
   * ни заголовком, ни в подсказке, ни как «Без ячеек». Остаётся тара и товар.
   */
  addressStorage: boolean
  /**
   * Документ сужен до одного объекта — открыт со строки карты склада.
   *
   * Тогда уровень ячейки в дереве не рисуем: где лежит этот короб, написано в
   * шапке, а лишний заголовок над одной строкой читается как второй список.
   */
  scoped?: boolean
  cells: CellNode[]
}

/** Строка списка документов. */
export type CountListItem = {
  id: string
  number: string
  status: CountStatus
  warehouseName: string
  fillLabel: string
  createdAt: string
  createdBy: string
  lines: number
  counted: number
  discrepancies: number
  /** Суммарная дельта в штуках: сколько нашли сверх и сколько недосчитались. */
  surplus: number
  shortage: number
}
