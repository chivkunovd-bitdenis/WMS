// WMS-536 · Единый клиентский поиск товара по коду.
//
// Отвечает ровно на один вопрос: «какой единственный товар из уже загруженного
// экраном набора соответствует этому коду?». Что делать с найденным товаром,
// что классифицировать раньше товара (ячейку, тару, короб, стикер, КИЗ) и как
// реагировать на «не найдено» — решает сам экран. КИЗ, DataMatrix и стикеры
// заказов сюда не передаются: у них свои нормализаторы, а этот слой не должен
// их видеть (R8, R9).
//
// Правила:
// - Индекс `код → набор карточек` строится один раз на набор товаров; каждый
//   скан — это поиск в Map, а не обход тысячи строк (R13).
// - Одновременно участвуют основной WB-код, все WB-коды размера (WMS-535),
//   sku_code и Ozon external_barcodes. external_sku и external_offer_id в индекс
//   не попадают (R3, R4).
// - Результат — found / not_found / ambiguous. Код, ведущий к двум разным
//   карточкам, никогда не разрешается выбором первой или последней (R2).
// - С краёв снимаются только пробел, TAB, CR и LF. Внутренние символы, GS,
//   AIM-префиксы и ведущие нули сохраняются, 13 и 14 знаков — разные коды.
//   Регистр не учитывается ни для латиницы, ни для кириллицы (R6).
// - Раскладка не исправляется сама. Вызывающий экран, который уже умел это
//   делать, может передать второй кандидат; он проверяется только после того,
//   как исходная строка дала not_found (R7).

/** Коды одной карточки, из которых строится индекс (R3). */
export type ProductScanSource = {
  productId: string
  /** `Product.sku_code`. */
  skuCode?: string | null
  /** Основной WB-штрихкод (`wb_primary_barcode` каталога, `wb_barcode` строки). */
  wbPrimaryBarcode?: string | null
  /** Все WB-штрихкоды размера — `wb_barcodes` каталога после WMS-535. */
  wbBarcodes?: readonly (string | null | undefined)[] | null
  /**
   * `external_barcodes` активной Ozon-привязки.
   *
   * Поля для `external_sku` и `external_offer_id` здесь нет намеренно: на
   * клиенте они не становятся штрихкодом товара (R4).
   */
  externalBarcodes?: readonly (string | null | undefined)[] | null
}

/** Строка каталога товаров в том виде, в каком её отдаёт сервер. */
export type ProductScanCatalogRow = {
  id: string
  sku_code?: string | null
  wb_primary_barcode?: string | null
  wb_barcodes?: readonly (string | null | undefined)[] | null
  marketplace_bindings?:
    | readonly {
        marketplace?: string | null
        external_barcodes?: readonly (string | null | undefined)[] | null
      }[]
    | null
}

/** Построенный индекс. Строится через `buildProductScanIndex` или `catalogProductScanIndex`. */
export type ProductScanIndex = {
  /** Нормализованный код → карточки, у которых он есть. */
  readonly productIdsByCode: ReadonlyMap<string, ReadonlySet<string>>
}

export type ProductScanOptions = {
  /**
   * Тот же ввод в латинской раскладке по физическим клавишам (R7).
   *
   * Передаёт только экран, который исправлял раскладку до WMS-536: подписчик
   * клавиатурного сканера (`useBarcodeScanner` отдаёт `scan.layout`) и
   * инвентаризация. Проверяется, только если исходная строка дала not_found;
   * при found или ambiguous по исходной строке не смотрится вовсе.
   */
  layoutCandidate?: string | null
}

export type ProductScanResult =
  | {
      status: 'found'
      productId: string
      /** Исходный код без краевых пробелов — для сообщений оператору. */
      code: string
      /** Кандидат, по которому нашлось: исходный код либо layout-кандидат. */
      matchedCode: string
      viaLayout: boolean
    }
  | {
      status: 'ambiguous'
      /** Все карточки из переданного набора, у которых есть этот код. */
      productIds: string[]
      code: string
      matchedCode: string
      viaLayout: boolean
    }
  | {
      status: 'not_found'
      code: string
    }

/** Текст для оператора при неоднозначном коде (R2). */
export const PRODUCT_SCAN_AMBIGUOUS_MESSAGE =
  'Код относится к нескольким товарам. Проверьте штрихкоды карточек.'

const EDGE_FRAMING = /^[ \t\r\n]+|[ \t\r\n]+$/g

/**
 * Снимает с краёв только пробел, TAB, CR и LF (R6).
 *
 * `String.trim()` здесь не подходит: он снимает и другие символы, а правило
 * сознательно консервативное. Внутренняя строка не меняется.
 */
export function trimProductScanCode(raw: string): string {
  return raw.replace(EDGE_FRAMING, '')
}

/** Ключ индекса: краевая очистка и сравнение без учёта регистра. */
function productScanKey(raw: string): string {
  return trimProductScanCode(raw).toLowerCase()
}

function addCode(
  target: Map<string, Set<string>>,
  value: string | null | undefined,
  productId: string,
): void {
  if (typeof value !== 'string') return
  const key = productScanKey(value)
  if (!key) return
  const ids = target.get(key)
  if (ids) {
    ids.add(productId)
  } else {
    target.set(key, new Set([productId]))
  }
}

/**
 * Строит индекс по уже загруженным товарам экрана.
 *
 * Набор, переданный сюда, и есть область поиска (R5): товар вне него не будет
 * найден. Одна и та же карточка может прийти несколько раз (строка документа и
 * строка каталога) — её коды просто сольются, неоднозначности это не создаёт.
 *
 * Вызывать один раз на набор (например, в `useMemo`), не на каждый скан.
 */
export function buildProductScanIndex(sources: Iterable<ProductScanSource>): ProductScanIndex {
  const productIdsByCode = new Map<string, Set<string>>()
  for (const source of sources) {
    const productId = source.productId
    if (!productId) continue
    addCode(productIdsByCode, source.skuCode, productId)
    addCode(productIdsByCode, source.wbPrimaryBarcode, productId)
    for (const barcode of source.wbBarcodes ?? []) addCode(productIdsByCode, barcode, productId)
    for (const barcode of source.externalBarcodes ?? []) {
      addCode(productIdsByCode, barcode, productId)
    }
  }
  return { productIdsByCode }
}

/** Коды строки каталога: sku_code, основной и все WB-коды, Ozon external_barcodes. */
export function productScanSourceFromCatalogRow(row: ProductScanCatalogRow): ProductScanSource {
  const externalBarcodes: (string | null | undefined)[] = []
  for (const binding of row.marketplace_bindings ?? []) {
    if (binding.marketplace !== 'ozon') continue
    externalBarcodes.push(...(binding.external_barcodes ?? []))
  }
  return {
    productId: row.id,
    skuCode: row.sku_code,
    wbPrimaryBarcode: row.wb_primary_barcode,
    wbBarcodes: row.wb_barcodes,
    externalBarcodes,
  }
}

const catalogIndexCache = new WeakMap<readonly ProductScanCatalogRow[], ProductScanIndex>()

/**
 * Индекс по массиву строк каталога; строится один раз на массив.
 *
 * Кэш привязан к самому массиву: пока экран держит тот же массив, каждый скан
 * берёт готовый индекс. Новый массив (перезагрузка каталога) — новый индекс.
 * Массив после передачи сюда не должен меняться на месте.
 */
export function catalogProductScanIndex(rows: readonly ProductScanCatalogRow[]): ProductScanIndex {
  const cached = catalogIndexCache.get(rows)
  if (cached) return cached
  const index = buildProductScanIndex(rows.map(productScanSourceFromCatalogRow))
  catalogIndexCache.set(rows, index)
  return index
}

function lookup(index: ProductScanIndex, candidate: string): ReadonlySet<string> | undefined {
  const ids = index.productIdsByCode.get(productScanKey(candidate))
  return ids && ids.size > 0 ? ids : undefined
}

function matchResult(
  ids: ReadonlySet<string>,
  code: string,
  matchedCode: string,
  viaLayout: boolean,
): ProductScanResult {
  if (ids.size === 1) {
    const [productId] = ids
    return { status: 'found', productId, code, matchedCode, viaLayout }
  }
  return { status: 'ambiguous', productIds: [...ids], code, matchedCode, viaLayout }
}

/**
 * Ищет товар по отсканированному коду в переданном индексе.
 *
 * Сначала — исходная строка. Layout-кандидат (если передан) проверяется только
 * после not_found по исходной строке. Пустой ввод — not_found с пустым `code`.
 */
export function resolveProductScan(
  index: ProductScanIndex,
  raw: string,
  options: ProductScanOptions = {},
): ProductScanResult {
  const code = trimProductScanCode(raw)
  if (!code) return { status: 'not_found', code }

  const direct = lookup(index, code)
  if (direct) return matchResult(direct, code, code, false)

  const layout = trimProductScanCode(options.layoutCandidate ?? '')
  if (layout && productScanKey(layout) !== productScanKey(code)) {
    const viaLayout = lookup(index, layout)
    if (viaLayout) return matchResult(viaLayout, code, layout, true)
  }
  return { status: 'not_found', code }
}
