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
}

export type Seller = {
  id: string
  name: string
  warehouses: SellerWarehouse[]
  /** Склады в кабинете WB — выбор для сопоставления. */
  wbWarehouses: Array<{ id: string; name: string }>
}

export type Product = {
  id: string
  name: string
  sku: string
  size: string | null
  barcode: string
  sellerId: string
  category: string
  /** Всего на складе. */
  onHand: number
  /** Занято: другие пулы и то, что уже в отгрузке. */
  reserved: number
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
  {
    id: 's-gor',
    name: 'ИП Горячкина',
    warehouses: [
      { id: 'w-gor-1', name: 'Ярцево', boundTo: 'wb-koledino' },
      { id: 'w-gor-2', name: 'Химки', boundTo: null },
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
    warehouses: [{ id: 'w-city-1', name: 'Ярцево', boundTo: 'wb-kazan' }],
    wbWarehouses: [
      { id: 'wb-kazan', name: 'Казань' },
      { id: 'wb-tula', name: 'Тула' },
    ],
  },
  {
    id: 's-larin',
    name: 'ИП Ларин',
    warehouses: [
      { id: 'w-lar-1', name: 'Ярцево', boundTo: null },
      { id: 'w-lar-2', name: 'Подольск', boundTo: null },
    ],
    wbWarehouses: [{ id: 'wb-nevinnomyssk', name: 'Невинномысск' }],
  },
]

export const PRODUCTS: Product[] = [
  { id: 'p1', name: 'Футболка хлопок белая', sku: 'TS-WHT-M', size: 'M', barcode: '4680123456789', sellerId: 's-gor', category: 'Футболки', onHand: 420, reserved: 96 },
  { id: 'p2', name: 'Футболка хлопок белая', sku: 'TS-WHT-L', size: 'L', barcode: '4680123456772', sellerId: 's-gor', category: 'Футболки', onHand: 260, reserved: 20 },
  { id: 'p3', name: 'Худи оверсайз серое', sku: 'HD-GRY-L', size: 'L', barcode: '4680123456796', sellerId: 's-gor', category: 'Худи и свитшоты', onHand: 180, reserved: 0 },
  { id: 'p4', name: 'Кроссовки беговые', sku: 'SN-RUN-42', size: '42', barcode: '4600987654321', sellerId: 's-city', category: 'Кроссовки', onHand: 96, reserved: 36 },
  { id: 'p5', name: 'Носки спортивные, 3 пары', sku: 'SK-SPT-3', size: null, barcode: '4600987654338', sellerId: 's-city', category: 'Носки', onHand: 640, reserved: 120 },
  { id: 'p6', name: 'Термокружка 450 мл', sku: 'MG-450', size: null, barcode: '4601122334455', sellerId: 's-larin', category: 'Посуда', onHand: 74, reserved: 0 },
  { id: 'p7', name: 'Ремень кожаный', sku: 'BL-110', size: '110', barcode: '4601122334462', sellerId: 's-larin', category: 'Ремни', onHand: 132, reserved: 12 },
]

export const INITIAL_RULES: FbsRule[] = [
  { productId: 'p1', publish: true, sameEverywhere: true, percent: 50, byWarehouse: {} },
  { productId: 'p4', publish: true, sameEverywhere: false, percent: 0, byWarehouse: { 'w-city-1': 30 } },
  { productId: 'p5', publish: false, sameEverywhere: true, percent: 20, byWarehouse: {} },
]

/** Свободный остаток: из него и считается процент. Пересчитывается всегда. */
export function freeStock(product: Product): number {
  return Math.max(0, product.onHand - product.reserved)
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
  const base = freeStock(product)
  if (!rule.publish) return 0
  if (rule.sameEverywhere) return Math.floor((base * rule.percent) / 100)
  return seller.warehouses.reduce(
    (sum, warehouse) => sum + Math.floor((base * (rule.byWarehouse[warehouse.id] ?? 0)) / 100),
    0,
  )
}
