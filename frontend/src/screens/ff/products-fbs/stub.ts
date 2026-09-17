// Заглушка каталога товаров и настроек остатка для FBS.
//
// Ключевое, что здесь смоделировано честно: процент считается от СВОБОДНОГО
// остатка, а не от общего. Свободный — это остаток минус резерв: то, что уже
// разложено под другие пулы, и то, что добавлено в текущую отгрузку. Поэтому у
// товара три числа, а не одно, и на экране видно все три.

/** Площадка, на которой живёт склад продавца. */
export type MarketplaceCode = 'wb' | 'ozon'

export const MARKETPLACE_NAMES: Record<MarketplaceCode, string> = {
  wb: 'Wildberries',
  ozon: 'Ozon',
}

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
  /**
   * Площадка склада. Не задана — Wildberries: так было до появления Ozon, и
   * все прежние источники данных этого поля не присылают (WMS-350).
   */
  marketplace?: MarketplaceCode
  /**
   * Почему у строки нет названия из кабинета (WMS-457). Не задано — название
   * пришло из кабинета. `not_in_cabinet` — список кабинета получен, но такого
   * склада в нём нет: он удалён или принадлежит другому продавцу.
   * `list_unavailable` — список кабинета не получен (ключ, права, сеть), и
   * имени взять неоткуда. В обоих случаях `name` — это «№ <номер>».
   */
  nameIssue?: WarehouseNameIssue
}

export type WarehouseNameIssue = 'not_in_cabinet' | 'list_unavailable'

/** Площадка склада с умолчанием. Отсутствие поля означает Wildberries. */
export function warehouseMarketplace(warehouse: SellerWarehouse): MarketplaceCode {
  return warehouse.marketplace ?? 'wb'
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
  /**
   * Площадки самого товара: `wb`, `ozon` либо оба у объединённой карточки.
   * Пусто — источник данных этого не знает, тогда считаем товар только
   * вайлдберрисовским, как было до Ozon (WMS-348, WMS-350).
   */
  marketplaces?: string[]
}

/** Настройка публикации остатка в FBS по товару. */
export type FbsRule = {
  changedPublication?: MarketplaceCode[]
  productId: string
  publish: boolean
  publishOzon?: boolean
  /** Один процент на все склады, либо свой процент по каждому. */
  sameEverywhere: boolean
  percent: number
  byWarehouse: Record<string, number>
  /**
   * Режим «остаток по штукам»: доля не применяется, числа задаются руками по
   * каждому складу WB. Нужен там, где у продавца согласована разбивка по
   * направлениям в конкретных числах, а в сетку кратных десяти процентов она
   * не ложится.
   */
  unitsMode: boolean
  /**
   * Штуки по складам WB. При чтении сюда кладётся ОСТАТОК квоты (сколько ещё
   * можно отдать), при сохранении это становится новым выделением.
   */
  unitsByWarehouse: Record<string, number>
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
      // Продавец на двух площадках: те же штуки делятся между Wildberries и
      // Ozon, а не удваиваются (WMS-350).
      {
        id: 'w-gor-oz',
        name: 'Ozon Хоругвино',
        boundTo: 'wb-koledino',
        fbsEnabled: true,
        marketplace: 'ozon',
      },
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
  { id: 'p1', name: 'Футболка хлопок белая', sku: 'TS-WHT-M', size: 'M', barcode: '4680123456789', sellerId: 's-gor', category: 'Футболки', stock: { 'w-gor-1': { onHand: 280, reserved: 76 }, 'w-gor-2': { onHand: 140, reserved: 20 } }, marketplaces: ['wb', 'ozon'] },
  { id: 'p2', name: 'Футболка хлопок белая', sku: 'TS-WHT-L', size: 'L', barcode: '4680123456772', sellerId: 's-gor', category: 'Футболки', stock: { 'w-gor-1': { onHand: 180, reserved: 20 }, 'w-gor-2': { onHand: 80, reserved: 0 } } },
  { id: 'p3', name: 'Худи оверсайз серое', sku: 'HD-GRY-L', size: 'L', barcode: '4680123456796', sellerId: 's-gor', category: 'Худи и свитшоты', stock: { 'w-gor-1': { onHand: 120, reserved: 0 }, 'w-gor-2': { onHand: 60, reserved: 0 } } },
  { id: 'p4', name: 'Кроссовки беговые', sku: 'SN-RUN-42', size: '42', barcode: '4600987654321', sellerId: 's-city', category: 'Кроссовки', stock: { 'w-city-1': { onHand: 96, reserved: 36 } } },
  { id: 'p5', name: 'Носки спортивные, 3 пары', sku: 'SK-SPT-3', size: null, barcode: '4600987654338', sellerId: 's-city', category: 'Носки', stock: { 'w-city-1': { onHand: 640, reserved: 120 } } },
  { id: 'p6', name: 'Термокружка 450 мл', sku: 'MG-450', size: null, barcode: '4601122334455', sellerId: 's-larin', category: 'Посуда', stock: { 'w-lar-1': { onHand: 50, reserved: 0 }, 'w-lar-2': { onHand: 24, reserved: 0 } } },
  { id: 'p7', name: 'Ремень кожаный', sku: 'BL-110', size: '110', barcode: '4601122334462', sellerId: 's-larin', category: 'Ремни', stock: { 'w-lar-1': { onHand: 92, reserved: 12 }, 'w-lar-2': { onHand: 40, reserved: 0 } } },
]

export const INITIAL_RULES: FbsRule[] = [
  { productId: 'p1', publish: true, sameEverywhere: true, percent: 50, byWarehouse: {}, unitsMode: false, unitsByWarehouse: {} },
  { productId: 'p4', publish: true, sameEverywhere: false, percent: 0, byWarehouse: { 'w-city-1': 30 }, unitsMode: false, unitsByWarehouse: {} },
  { productId: 'p5', publish: false, sameEverywhere: true, percent: 20, byWarehouse: {}, unitsMode: false, unitsByWarehouse: {} },
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

/** Склады, которые мы обслуживаем по FBS. Только они участвуют в раздаче остатка.
 *
 * Порядок — по возрастанию номера склада WB, ровно как на сервере
 * (`_seller_bindings` сортирует по `wb_warehouse_id`). От порядка зависит, кому
 * не хватит остатка при переборе, поэтому окно должно перебирать так же.
 */
export function servedWarehouses(seller: Seller): SellerWarehouse[] {
  return seller.warehouses
    .filter((one) => one.fbsEnabled)
    .slice()
    .sort((a, b) => (Number(a.id) || 0) - (Number(b.id) || 0))
}

/**
 * Показывать ли в окне остатка Ozon: галку передачи, заголовки площадок и
 * склады Ozon. Решает карточка товара, а не склады продавца: у товара без
 * карточки Ozon передавать туда нечего, и его окно совпадает с окном того же
 * товара у продавца без Ozon-складов (WMS-454). Признак тот же, что у значка
 * площадки в строке каталога. Пустой список площадок — источник данных этого
 * не знает; тогда, как и до Ozon, товар считается вайлдберрисовским.
 */
export function dialogShowsOzon(products: Array<Pick<Product, 'marketplaces'>>): boolean {
  return products.some((one) => (one.marketplaces ?? []).includes('ozon'))
}

/** Склады продавца, которые видны в окне: без Ozon, если Ozon в окне нет. */
export function visibleWarehouses(seller: Seller, ozonShown: boolean): SellerWarehouse[] {
  return ozonShown
    ? seller.warehouses
    : seller.warehouses.filter((one) => warehouseMarketplace(one) === 'wb')
}

/**
 * Черновик, с которого окно начинает. `warehouses` — склады, видимые в окне.
 *
 * Единственный обслуживаемый склад — особый случай: галку «одинаково по всем
 * складам» в этом режиме не показывают (делить не с кем), поэтому черновик
 * всегда считается по общему проценту — что оператор видит на ползунке, то и
 * уезжает. Если сохранённое правило задавало доли по складам, действующая доля
 * этого единственного склада лежит в byWarehouse, а общий процент — старый и
 * к ней не относится; на ползунок идёт именно доля склада. Иначе окно показало
 * бы чужое число (обычно 0), и сохранение без правок затёрло бы долю: у
 * WB-товара с прежним правилом «WB 60 / Ozon 40» после скрытия Ozon
 * обслуживаемый склад остаётся один, и WB-доля 60 должна остаться 60.
 * Когда обслуживаемых нет, а видимый склад один, берётся его доля: она
 * заработает, как только склад включат.
 *
 * У товара без карточки Ozon флаг Ozon в окне не показывается и при каждом
 * сохранении уходит выключенным: иначе унаследованное «как у Wildberries»
 * держит Ozon-привязку продавца в общих ста процентах (WMS-454). «ozon» в
 * списке тронутых флагов и есть команда сохранению отправить поле, а не
 * оставить прежнее значение.
 */
export function initialDraft(
  rule: FbsRule,
  warehouses: SellerWarehouse[],
  ozonShown: boolean,
): FbsRule {
  const served = warehouses.filter((one) => one.fbsEnabled)
  const single = served.length <= 1
  const only = served[0] ?? (warehouses.length === 1 ? warehouses[0] : undefined)
  const percent =
    single && !rule.sameEverywhere && only ? (rule.byWarehouse[only.id] ?? 0) : rule.percent
  return {
    ...rule,
    ...(single ? { sameEverywhere: true, percent } : {}),
    ...(ozonShown
      ? { changedPublication: [] }
      : { publishOzon: false, changedPublication: ['ozon' as const] }),
  }
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
      unitsMode: false,
      unitsByWarehouse: {},
    }
  )
}

/** Сколько уйдёт на один склад WB — та же формула, что на сервере. */
export function amountFromPercent(freeStockQty: number, percent: number): number {
  if (freeStockQty <= 0 || percent <= 0) return 0
  return Math.floor((freeStockQty * percent) / 100)
}

/** Раскладка свободного остатка по обслуживаемым складам: id склада WB -> штуки.
 *
 * Повторяет `split_amounts` из `fbs_stock_rule_service.py` шаг в шаг: доля
 * считается КАЖДОМУ складу отдельно и округляется вниз у каждого, а не один раз
 * у суммы; переполнение отрезается у последнего склада по порядку.
 *
 * Раньше окно считало иначе, и числа расходились с тем, что реально уезжало в
 * Wildberries: при двух складах и галке «одинаково» с долей 50% окно обещало
 * половину остатка, а уезжал весь (50% + 50%); при долях 50/20/30 на 201
 * свободной штуке окно писало 201, а уезжало 200.
 */
export function publishesTo(rule: FbsRule, marketplace: MarketplaceCode): boolean {
  return marketplace === 'ozon' ? (rule.publishOzon ?? rule.publish) : rule.publish
}

export function splitAmounts(
  rule: FbsRule,
  freeStockQty: number,
  served: SellerWarehouse[],
): Record<string, number> {
  const amounts: Record<string, number> = {}
  let remaining = Math.max(freeStockQty, 0)
  for (const warehouse of served) {
    if (!publishesTo(rule, warehouseMarketplace(warehouse))) {
      amounts[warehouse.id] = 0
      continue
    }
    // В режиме штук доля не участвует вовсе: берётся заданное число, но обрезка
    // по свободному остатку остаётся — столько товара может просто не быть.
    const share = rule.unitsMode
      ? Math.max(0, rule.unitsByWarehouse[warehouse.id] ?? 0)
      : amountFromPercent(
          freeStockQty,
          rule.sameEverywhere ? rule.percent : (rule.byWarehouse[warehouse.id] ?? 0),
        )
    const amount = Math.min(share, remaining)
    amounts[warehouse.id] = amount
    remaining -= amount
  }
  return amounts
}

/** Сколько уйдёт в Wildberries по этому правилу прямо сейчас. */
export function publishedQty(product: Product, rule: FbsRule, seller: Seller): number {
  // Остаток уходит только на обслуживаемые склады. Если не выбран ни один,
  // отправлять некуда, и показывать посчитанное по проценту число нельзя:
  // оператор решит, что товар выставлен, а в кабинет не уйдёт ничего.
  const served = servedWarehouses(seller)
  if (served.length === 0) return 0
  const amounts = splitAmounts(rule, freeStock(product), served)
  return Object.values(amounts).reduce((sum, one) => sum + one, 0)
}

/** Сумма долей так, как её проверяет сервер (`validate_rule`).
 *
 * При галке «одинаково» доля применяется к КАЖДОМУ складу, поэтому в сумме она
 * умножается на их количество: 50% на четырёх складах Фэшн — это 200%, и сервер
 * такое правило не примет.
 */
/** Сколько штук распределено по обслуживаемым складам. */
export function totalUnits(rule: FbsRule, served: SellerWarehouse[]): number {
  return served.reduce((sum, one) => sum + (rule.unitsByWarehouse[one.id] ?? 0), 0)
}

export function totalPercent(rule: FbsRule, servedCount: number): number {
  if (rule.sameEverywhere) return rule.percent * Math.max(servedCount, 1)
  return Object.values(rule.byWarehouse).reduce((sum, one) => sum + one, 0)
}
