/**
 * WMS-686: верх вкладки «Упаковка» отгрузки FBO.
 *
 * Типы описывают только то, что нужно этому блоку. Ответ отгрузки экрана
 * (MarketplaceUnloadDetail в FfSuppliesShipmentsPage) подходит под FboPackingDetail
 * по структуре: лишние поля ему не мешают.
 */

export type FboPackingLine = {
  id: string
  product_id: string
  sku_code: string
  product_name: string
  /** План (P). */
  quantity: number
  /** Подобрано по товару (S). */
  picked_qty?: number
  /** Если сервер отдаёт признак на строке — он главнее признака из каталога. */
  requires_honest_sign?: boolean
  /** K, посчитанное сервером; до загрузки списка кодов показывается оно. */
  kiz_count?: number
  /** ТЗ на упаковку товара (иконка «ТЗ»). */
  packaging_instructions?: string | null
}

export type FboPackingBoxLine = {
  id: string
  product_id: string
  sku_code: string
  product_name: string
  quantity: number
}

export type FboPackingBox = {
  id: string
  /** ШК складского короба (WHB-) или короба приёмки (INB-). */
  internal_barcode: string | null
  closed_at?: string | null
  lines: FboPackingBoxLine[]
}

export type FboPackingAllocation = {
  product_id: string
  quantity: number
}

export type FboPackingDetail = {
  id: string
  document_number?: string | null
  display_number?: string | null
  public_number?: string | null
  human_number?: string | null
  warehouse_name: string
  seller_name: string | null
  /** 'wb' | 'ozon' */
  marketplace: string
  status: string
  created_at: string | null
  lines: FboPackingLine[]
  boxes: FboPackingBox[]
  pick_allocations?: FboPackingAllocation[]
}

/** Код ЧЗ, привязанный к строке отгрузки (GET .../marking-codes). */
export type FboMarkingCode = {
  marking_code_id: string
  cis_code: string
  product_id: string
  line_id?: string | null
  status?: string | null
  intake_document_number?: string | null
  linked_at?: string | null
  has_label_artifact?: boolean
}

export type FboMarkingScanResult = {
  marking_code_id?: string
  cis_code?: string
  product_id?: string
  line_id?: string | null
  kiz_count?: number
  picked_qty?: number
  /** Повтор того же кода на ту же строку: ничего не изменилось. */
  already_linked?: boolean
}

export type FboMarkingIssueResult = {
  items: FboMarkingCode[]
  /** Сколько кодов не хватило в пуле. */
  shortage?: number
}

export type FboBoxScanResult = {
  kind: string
  product_id?: string | null
  picked_qty?: number | null
  quantity?: number | null
}

/** Строка общей таблицы товаров. Все числа вычисляются, независимых счётчиков нет. */
export type FboProductRow = {
  productId: string
  lineIds: string[]
  skuCode: string
  productName: string
  /** Нужно (P). */
  need: number
  /** Подобрано (S). */
  picked: number
  /** В коробах (B). */
  inBoxes: number
  /** Признак ЧЗ из строк отгрузки; undefined — сервер его не прислал. */
  requiresHonestSign: boolean | undefined
  /** K по данным отгрузки; пока список кодов не загружен, показывается оно. */
  kizCount: number
  /** ТЗ на упаковку из строки отгрузки. */
  packagingInstructions: string | null
}
