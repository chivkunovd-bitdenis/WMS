// Что экран показывает и чем он оперирует. Форма нарочно повторяет складскую
// правду, а не устройство базы: ячейка держит палеты, короба и товар россыпью,
// палета держит короба и товар, короб держит товар. Глубже вложений не бывает.

export type ContainerKind = 'pallet' | 'box' | 'cargo_place'

export type ProductNode = {
  kind: 'product'
  /** Ключ строки остатка: один товар на одном месте хранения. */
  id: string
  product_id: string
  name: string
  seller_name: string | null
  /** Предмет с карточки маркетплейса: «Футболки», «Кроссовки». */
  category: string | null
  /** Артикул продавца из карточки WB, не внутренний SKU склада. */
  seller_article: string | null
  barcode: string | null
  photo_url: string | null
  qty: number
}

export type ContainerNode = {
  kind: ContainerKind
  id: string
  /** Человеческий номер: «П-000123», «КР-000451». Сырых идентификаторов на экране нет. */
  code: string
  barcode: string | null
  /** Селлер контейнера — только когда внутри товар одного селлера. */
  seller_name: string | null
  /** Всего штук внутри, вместе с вложенными коробами. */
  qty: number
  /**
   * Номер приёмки, из которой родилась эта тара — если она ещё не завершена
   * (§Б-04). Необязательное: короб из завершённой приёмки его не несёт, а
   * заглушки предпросмотра (stub.ts) — не источник правды об этом поле.
   */
  source_document_number?: string | null
  children: MapNode[]
}

export type MapNode = ProductNode | ContainerNode

export type CellNode = {
  id: string
  /** Код ячейки как на её этикетке: «А-01-02». */
  code: string
  barcode: string | null
  qty: number
  children: MapNode[]
}

export type WarehouseOption = {
  id: string
  name: string
}

export type MovementEntry = {
  id: string
  /** UTC ISO — время экран показывает в московском поясе, как везде в системе. */
  at: string
  actor_name: string
  /** Что переехало: «Футболка хлопок белая, M» или «Короб КР-000451». */
  subject: string
  qty: number | null
  from_label: string
  to_label: string
}

export type WarehouseMapData = {
  warehouses: WarehouseOption[]
  /** Списки для фильтров приходят с сервера: экран их из строк не собирает. */
  sellers: string[]
  categories: string[]
  cells: CellNode[]
  /** Принято, но никуда не положено, плюс всё, что сняли с ячеек. */
  unassigned: MapNode[]
  journal: MovementEntry[]
}

export const UNASSIGNED_ID = 'unassigned'
export const UNASSIGNED_LABEL = 'Без ячеек'

export const KIND_TITLE: Record<ContainerKind, string> = {
  pallet: 'Палета',
  box: 'Короб',
  cargo_place: 'Грузоместо',
}
