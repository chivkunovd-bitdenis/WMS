// Общие типы карточки товара (WMS-490). Контракт данных — из документа
// требований, раздел «План реализации», кусок D1 (`GET /products/{id}/card`):
// тот же сборщик, что отдаёт каталог (`_ff_catalog_out_rows`), плюс габариты,
// вес и список складов, где лежит товар. Ни одно поле здесь не считается
// заново — сервер отдаёт его напрямую (AGENTS.md, R17).

/** Привязка товара к площадке (сейчас — только Ozon, см. R6). */
export type ProductCardMarketplaceBinding = {
  marketplace: string
  external_product_id: string | null
  external_offer_id: string | null
  external_sku: string | null
  external_barcodes: string[]
}

/** Склад, на котором у товара есть остаток или незавершённая приёмка (для вкладки «Расположение», D5). */
export type ProductCardLocationWarehouse = {
  id: string
  name: string
}

/** Ответ `GET /products/{id}/card` (кусок D1). */
export type ProductCardData = {
  id: string
  seller_id: string | null
  seller_name: string | null
  name: string
  sku_code: string
  wb_nm_id: number | null
  wb_vendor_code: string | null
  ozon_sku: string | null
  ozon_offer_id: string | null
  wb_subject_name: string | null
  wb_primary_image_url: string | null
  marketplace_bindings: ProductCardMarketplaceBinding[]
  wb_barcodes: string[]
  wb_primary_barcode: string | null
  wb_size: string | null
  wb_color: string | null
  wb_brand: string | null
  wb_composition: string | null
  packaging_instructions: string | null
  country_of_origin_iso_code: string | null
  requires_honest_sign: boolean
  // Площадки товара — то же правило, что значок в каталоге (R5–R7).
  marketplaces: string[]
  length_mm: number | null
  width_mm: number | null
  height_mm: number | null
  weight_g: number | null
  location_warehouses: ProductCardLocationWarehouse[]
}

/** Три числа шапки — из `/operations/inventory-balances/summary` (R2). */
export type ProductCardStockTotals = {
  quantity: number
  reserved: number
  available: number
}

/**
 * Минимум, который уже есть у строки каталога в момент клика — этого хватает,
 * чтобы сразу нарисовать заголовок (фото и название, R2), решить, показывать
 * ли вкладку «Задать остаток» (R3), и открыть саму вкладку без ожидания
 * `/products/{id}/card` (D1): окно «Остаток для FBS» испокон века строится из
 * тех же полей строки каталога (`FbsStockDialogRow`), не из карточки (D6).
 */
export type ProductCardTriggerRow = {
  id: string
  name: string
  sku_code: string
  wb_size: string | null
  wb_primary_image_url: string | null
  seller_id: string | null
  seller_name: string | null
}
