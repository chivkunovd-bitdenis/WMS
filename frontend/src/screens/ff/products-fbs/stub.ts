// Заглушка каталога товаров и настроек остатка для FBS.
//
// Ключевое, что здесь смоделировано честно: процент считается от СВОБОДНОГО
// остатка, а не от общего. Свободный — это остаток минус резерв: то, что уже
// разложено под другие пулы, и то, что добавлено в текущую отгрузку. Поэтому у
// товара три числа, а не одно, и на экране видно все три.

export type SellerWarehouse = {
  id: string
  name: string
  /** Склад продавца в кабинете WB, с которым сопоставлен наш. */
  boundTo: string | null
  /**
   * Обслуживаем ли мы этот склад по FBS.
   *
   * У селлера складов может быть много, а фулфилмент обычно обслуживает один.
   * Галочка ставится один раз в настройках селлера и решает сразу две вещи:
   * какие заказы вообще наши и по каким складам раздаётся остаток.
   */
  fbsEnabled: boolean
}

export type Seller = {
  id: string
  name: string
  warehouses: SellerWarehouse[]
  /** Склады в кабинете WB — выбор для сопоставления. */
  wbWarehouses: Array<{ id: string; name: string }>
}

/** Остаток лежит на конкретном складе, а не «вообще». */
export type StockAt = { onHand: number; reserved: number }

export type Product = {
  id: string
  name: string
  sku: string
  size: string | null
  barcode: string
  sellerId: string
  category: string
  /**
   * Остаток по складам. Общего числа у товара нет намеренно: доля склада
   * считается от того, что лежит на этом складе, а не от суммы по всем. Иначе
   * 100% на одном складе и 70% на другом дают в сумме больше, чем есть.
   */
  stock: Record<string, StockAt>
}

/** Настройка публикации остатка в FBS по товару. */
export type FbsRule = {
  productId: string
  publish: boolean
  /** Один процент на все склады, либо свой процент по каждому. */
  sameEverywhere: boolean
  percent: number
  byWarehouse: Record<string, number>
}

export const SELLERS: Seller[] = [
  // ИП Чжоу — настоящий продавец с боевой базы: по нему снята метрика времени
  // сборки. Остальные продавцы в списке выдуманы, они здесь ради вида списка.
  {
    id: 's-zhou',
    name: 'ИП Чжоу',
    warehouses: [
      { id: 'w-zhou-1', name: 'Ярцево', boundTo: 'wb-1', fbsEnabled: true },
    ],
    wbWarehouses: [{ id: 'wb-1', name: 'Склад WB' }],
  },
  {
    id: 's-gor',
    name: 'ИП Горячкина',
    warehouses: [
      { id: 'w-gor-1', name: 'Ярцево', boundTo: 'wb-koledino', fbsEnabled: true },
      { id: 'w-gor-2', name: 'Химки', boundTo: null, fbsEnabled: true },
    ],
    wbWarehouses: [
      { id: 'wb-koledino', name: 'Коледино' },
      { id: 'wb-elektrostal', name: 'Электросталь' },
      { id: 'wb-podolsk', name: 'Подольск' },
    ],
  },
  {
    id: 's-city',
    name: 'ООО Ситипак',
    warehouses: [{ id: 'w-city-1', name: 'Ярцево', boundTo: 'wb-kazan', fbsEnabled: true }],
    wbWarehouses: [
      { id: 'wb-kazan', name: 'Казань' },
      { id: 'wb-tula', name: 'Тула' },
    ],
  },
  {
    id: 's-larin',
    name: 'ИП Ларин',
    warehouses: [
      { id: 'w-lar-1', name: 'Ярцево', boundTo: null, fbsEnabled: true },
      { id: 'w-lar-2', name: 'Подольск', boundTo: null, fbsEnabled: false },
    ],
    wbWarehouses: [{ id: 'wb-nevinnomyssk', name: 'Невинномысск' }],
  },
]

export const PRODUCTS: Product[] = [
  { id: 'p1', name: 'Футболка хлопок белая', sku: 'TS-WHT-M', size: 'M', barcode: '4680123456789', sellerId: 's-gor', category: 'Футболки', stock: { 'w-gor-1': { onHand: 280, reserved: 76 }, 'w-gor-2': { onHand: 140, reserved: 20 } } },
  { id: 'p2', name: 'Футболка хлопок белая', sku: 'TS-WHT-L', size: 'L', barcode: '4680123456772', sellerId: 's-gor', category: 'Футболки', stock: { 'w-gor-1': { onHand: 180, reserved: 20 }, 'w-gor-2': { onHand: 80, reserved: 0 } } },
  { id: 'p3', name: 'Худи оверсайз серое', sku: 'HD-GRY-L', size: 'L', barcode: '4680123456796', sellerId: 's-gor', category: 'Худи и свитшоты', stock: { 'w-gor-1': { onHand: 120, reserved: 0 }, 'w-gor-2': { onHand: 60, reserved: 0 } } },
  { id: 'p4', name: 'Кроссовки беговые', sku: 'SN-RUN-42', size: '42', barcode: '4600987654321', sellerId: 's-city', category: 'Кроссовки', stock: { 'w-city-1': { onHand: 96, reserved: 36 } } },
  { id: 'p5', name: 'Носки спортивные, 3 пары', sku: 'SK-SPT-3', size: null, barcode: '4600987654338', sellerId: 's-city', category: 'Носки', stock: { 'w-city-1': { onHand: 640, reserved: 120 } } },
  { id: 'p6', name: 'Термокружка 450 мл', sku: 'MG-450', size: null, barcode: '4601122334455', sellerId: 's-larin', category: 'Посуда', stock: { 'w-lar-1': { onHand: 50, reserved: 0 }, 'w-lar-2': { onHand: 24, reserved: 0 } } },
  { id: 'p7', name: 'Ремень кожаный', sku: 'BL-110', size: '110', barcode: '4601122334462', sellerId: 's-larin', category: 'Ремни', stock: { 'w-lar-1': { onHand: 92, reserved: 12 }, 'w-lar-2': { onHand: 40, reserved: 0 } } },
]

export const INITIAL_RULES: FbsRule[] = [
  { productId: 'p1', publish: true, sameEverywhere: true, percent: 50, byWarehouse: {} },
  { productId: 'p4', publish: true, sameEverywhere: false, percent: 0, byWarehouse: { 'w-city-1': 30 } },
  { productId: 'p5', publish: false, sameEverywhere: true, percent: 20, byWarehouse: {} },
]

/** Свободный остаток на конкретном складе: из него и считается доля этого склада. */
export function freeStockAt(product: Product, warehouseId: string): number {
  const at = product.stock[warehouseId]
  if (!at) return 0
  return Math.max(0, at.onHand - at.reserved)
}

/** Свободный остаток по всем складам продавца — сумма, а не отдельное число. */
export function freeStock(product: Product): number {
  return Object.keys(product.stock).reduce(
    (sum, warehouseId) => sum + freeStockAt(product, warehouseId),
    0,
  )
}

export function onHandTotal(product: Product): number {
  return Object.values(product.stock).reduce((sum, at) => sum + at.onHand, 0)
}

export function reservedTotal(product: Product): number {
  return Object.values(product.stock).reduce((sum, at) => sum + at.reserved, 0)
}

/** Склады, которые мы обслуживаем по FBS. Только они участвуют в раздаче остатка. */
export function servedWarehouses(seller: Seller): SellerWarehouse[] {
  return seller.warehouses.filter((one) => one.fbsEnabled)
}

export function sellerById(id: string): Seller {
  return SELLERS.find((one) => one.id === id)!
}

export function ruleFor(rules: FbsRule[], productId: string): FbsRule {
  return (
    rules.find((one) => one.productId === productId) ?? {
      productId,
      publish: false,
      sameEverywhere: true,
      percent: 0,
      byWarehouse: {},
    }
  )
}

/** Сколько уйдёт в Wildberries по этому правилу прямо сейчас. */
export function publishedQty(product: Product, rule: FbsRule, seller: Seller): number {
  if (!rule.publish) return 0
  const base = freeStock(product)
  if (rule.sameEverywhere) return Math.floor((base * rule.percent) / 100)
  // Доли складов делят один и тот же свободный остаток, поэтому суммируются
  // проценты, а не посчитанные по отдельности количества.
  const percent = Math.min(
    100,
    seller.warehouses.reduce((sum, warehouse) => sum + (rule.byWarehouse[warehouse.id] ?? 0), 0),
  )
  return Math.floor((base * percent) / 100)
}
