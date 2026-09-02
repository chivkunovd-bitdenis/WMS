import { useLayoutEffect, useState } from 'react'
import type { ReactNode } from 'react'

import { MarkingPrintDialog } from '../../../../components/MarkingPrintDialog'
import type { MarkingPrintContext } from '../../../../components/MarkingPrintDialog'
import { FfHonestSignPage } from '../../FfHonestSignPage'
import { PRODUCTS, SELLERS } from './data'
import type { DemoProduct } from './data'
import { SceneShell } from './SceneShell'
import { installStubFetch } from './stubFetch'
import type { StubRoute } from './stubFetch'

/**
 * Живые макеты раздела «Честный знак» — того места, где склад видит запас кодов
 * маркировки и печатает их на этикетки.
 *
 * Экран настоящий (`FfHonestSignPage`), выдуманы только данные: их отдаёт
 * подставной fetch. Так картинка в инструкции не зависит от того, что сейчас
 * лежит в базе стенда, и не светит чужими артикулами и остатками.
 */

/* ─────────────────────────── выдуманные данные ─────────────────────────── */

/**
 * Товары сверх общего набора `data.ts`.
 *
 * В `PRODUCTS` у «ИП Горячкина» всего три позиции, а таблица на три строки
 * читается как полупустой склад — в статье это сбивает с толку. Артикулы и
 * штрихкоды продолжают ту же линейку, что и в общем наборе, поэтому каталог и
 * «Честный знак» показывают один и тот же товар.
 */
const EXTRA_PRODUCTS: DemoProduct[] = [
  {
    id: 'p-6',
    sku: 'HD-GRY-M',
    name: 'Худи оверсайз серое, M',
    barcode: '4680123456802',
    wbBarcode: '2037123456802',
    seller: 'ИП Горячкина',
  },
  {
    id: 'p-7',
    sku: 'SW-BEG-S',
    name: 'Свитшот бежевый, S',
    barcode: '4680123456819',
    wbBarcode: '2037123456819',
    seller: 'ИП Горячкина',
  },
  {
    id: 'p-8',
    sku: 'CP-BLK-U',
    name: 'Кепка чёрная, one size',
    barcode: '4600987654345',
    wbBarcode: '2037987654345',
    seller: 'ООО Ситипак',
  },
]

const ALL_PRODUCTS: DemoProduct[] = [...PRODUCTS, ...EXTRA_PRODUCTS]

const SELLER_ID_BY_NAME: Record<string, string> = Object.fromEntries(
  SELLERS.map((seller) => [seller.name, seller.id]),
)

/** Селлер, у которого в макете заведены коды маркировки. */
const CODES_SELLER_ID = 's-2'

/**
 * Порядок списка селлеров важен: `FfHonestSignPage` сам подставляет в фильтр
 * первого из них, а подставной сервер честно отдаёт коды только по выбранному
 * селлеру. Поставь первым того, у кого кодов нет, — и на картинке в статье
 * будет пустая таблица вместо запаса кодов.
 */
const SCENE_SELLERS = [
  ...SELLERS.filter((seller) => seller.id === CODES_SELLER_ID),
  ...SELLERS.filter((seller) => seller.id !== CODES_SELLER_ID),
]

/** Карточка товара так, как её показывает маркетплейс: размер, цвет, бренд. */
type ProductMeta = {
  size: string
  vendorCode: string
  color: string
  brand: string
}

const PRODUCT_META: Record<string, ProductMeta> = {
  'p-1': { size: 'M', vendorCode: 'GOR-TS-WHT', color: 'белый', brand: 'Basic Cotton' },
  'p-2': { size: 'L', vendorCode: 'GOR-TS-WHT', color: 'белый', brand: 'Basic Cotton' },
  'p-3': { size: 'L', vendorCode: 'GOR-HD-GRY', color: 'серый', brand: 'Basic Cotton' },
  'p-4': { size: '42', vendorCode: 'CTP-SN-RUN', color: 'чёрный', brand: 'Cityline' },
  'p-5': { size: '41-44', vendorCode: 'CTP-SK-SPT', color: 'серый меланж', brand: 'Cityline' },
  'p-6': { size: 'M', vendorCode: 'GOR-HD-GRY', color: 'серый', brand: 'Basic Cotton' },
  'p-7': { size: 'S', vendorCode: 'GOR-SW-BEG', color: 'бежевый', brand: 'Basic Cotton' },
  'p-8': { size: 'one size', vendorCode: 'CTP-CP-BLK', color: 'чёрный', brand: 'Cityline' },
}

/**
 * Запас кодов по товару.
 *
 * `personal` — свободные коды, привязанные к самому товару; `printed` — уже
 * израсходованные, то есть напечатанные на этикетки. `basket` — общая корзина:
 * один пул кодов на несколько размеров одной модели, из него берут те товары,
 * у кого личный запас кончился.
 */
type MarkingRow = {
  productId: string
  personal: number
  printed: number
  basket?: { available: number; products: number }
}

const MARKING_ROWS: MarkingRow[] = [
  { productId: 'p-1', personal: 420, printed: 138 },
  // Шесть штук — это «на исходе»: экран красит остаток красным и считает такие
  // товары в плитке «На исходе». Ради этой плитки строка и заведена.
  { productId: 'p-2', personal: 6, printed: 96 },
  { productId: 'p-3', personal: 0, printed: 54, basket: { available: 300, products: 2 } },
  { productId: 'p-6', personal: 0, printed: 41, basket: { available: 300, products: 2 } },
  // По свитшоту коды загрузили, но ещё ни разу не печатали — именно его берёт
  // макет окна печати: у товара с историей печати окно показывает
  // предупреждение «ЧЗ уже печатался ранее», и картинка в статье получается
  // про перепечатку, а не про обычную печать.
  { productId: 'p-7', personal: 180, printed: 0 },
  { productId: 'p-4', personal: 260, printed: 75 },
  { productId: 'p-5', personal: 90, printed: 30 },
  { productId: 'p-8', personal: 40, printed: 8 },
]

/** Бракованные коды — плитка «Брак» на экране. */
const DEFECTIVE_BY_SELLER: Record<string, number> = {
  's-2': 12,
  's-3': 3,
}

function productById(productId: string): DemoProduct | undefined {
  return ALL_PRODUCTS.find((product) => product.id === productId)
}

function sellerIdOfRow(row: MarkingRow): string {
  const product = productById(row.productId)
  return product ? SELLER_ID_BY_NAME[product.seller] : ''
}

/** Селлер из строки запроса: экран всегда шлёт `?seller_id=…`. */
function sellerIdFromPath(match: RegExpMatchArray): string {
  const query = (match.input ?? '').split('?')[1] ?? ''
  return new URLSearchParams(query).get('seller_id') ?? ''
}

function rowsForSeller(sellerId: string): MarkingRow[] {
  if (!sellerId) {
    return MARKING_ROWS
  }
  return MARKING_ROWS.filter((row) => sellerIdOfRow(row) === sellerId)
}

/** Общая корзина: один пул на несколько размеров одной модели. */
function basketPoolId(row: MarkingRow): string {
  const product = productById(row.productId)
  const meta = product ? PRODUCT_META[product.id] : undefined
  return `pool-${meta?.vendorCode ?? row.productId}`
}

function inventoryPayload(sellerId: string) {
  const rows = rowsForSeller(sellerId)
  return {
    rows: rows.map((row) => {
      const product = productById(row.productId)
      return {
        product_id: row.productId,
        sku_code: product?.sku ?? row.productId,
        product_name: product?.name ?? '',
        requires_honest_sign: true,
        available_count: row.personal + (row.basket?.available ?? 0),
        printed_count: row.printed,
        personal_available: row.personal,
        shared_baskets: row.basket
          ? [
              {
                pool_id: basketPoolId(row),
                gtin: product?.wbBarcode ?? '',
                title: `Общая корзина · ${product?.name ?? ''}`,
                available: row.basket.available,
                products_count: row.basket.products,
              },
            ]
          : [],
      }
    }),
    // Кодов без привязки к товару в макете нет: такой остаток поднимает на
    // экране отдельное предупреждение и таблицу «Пул без привязки», а статья
    // рассказывает про обычную работу, а не про разбор залежей.
    unlinked_available_count: 0,
    defective_count: DEFECTIVE_BY_SELLER[sellerId] ?? 0,
  }
}

/**
 * Пулы кодов. Экран берёт из них только пулы без привязки к товарам, поэтому у
 * каждого пула здесь есть свои товары — лишних блоков на картинке не появится.
 */
function poolsPayload(sellerId: string) {
  return rowsForSeller(sellerId).map((row) => {
    const product = productById(row.productId)
    const linked = [{ id: row.productId, sku_code: product?.sku ?? '', name: product?.name ?? '' }]
    return {
      id: row.basket ? basketPoolId(row) : `pool-${row.productId}`,
      title: row.basket ? `Общая корзина · ${product?.name ?? ''}` : `Пул · ${product?.sku ?? ''}`,
      gtin: product?.wbBarcode ?? '',
      products: linked,
      available: row.personal + (row.basket?.available ?? 0),
      linked_products_count: row.basket?.products ?? 1,
    }
  })
}

/** Карточки товаров маркетплейса: из них экран берёт размер и фото. */
function catalogPayload(sellerId: string) {
  return rowsForSeller(sellerId).map((row) => {
    const product = productById(row.productId)
    const meta = PRODUCT_META[row.productId]
    return {
      id: row.productId,
      name: product?.name ?? '',
      sku_code: product?.sku ?? '',
      seller_name: product?.seller ?? null,
      wb_nm_id: null,
      wb_vendor_code: meta?.vendorCode ?? null,
      wb_subject_name: null,
      // Фото нет: ссылка на картинку маркетплейса тянула бы внешний адрес,
      // а макет должен рисоваться без сети. Экран покажет заглушку.
      wb_primary_image_url: null,
      wb_barcodes: product ? [product.wbBarcode] : [],
      wb_primary_barcode: product?.wbBarcode ?? null,
      wb_size: meta?.size ?? null,
      wb_color: meta?.color ?? null,
      wb_brand: meta?.brand ?? null,
      wb_composition: 'хлопок 92%, эластан 8%',
      marketplace_bindings: [],
    }
  })
}

/* ───────────────────────── подставные адреса ───────────────────────── */

const HONEST_SIGN_ROUTES: StubRoute[] = [
  {
    path: /^\/operations\/marking-codes\/inventory/,
    handler: (match) => inventoryPayload(sellerIdFromPath(match)),
  },
  {
    path: /^\/operations\/marking-codes\/pools/,
    handler: (match) => poolsPayload(sellerIdFromPath(match)),
  },
  {
    path: /^\/products\/linked-wb-catalog/,
    handler: (match) => catalogPayload(sellerIdFromPath(match)),
  },
]

/**
 * Окно печати спрашивает у сервера две вещи: настройку тенанта «раздельная
 * печать» и шаблон ленты для товара. Без них оно показало бы «Проверяем
 * настройку…» и пустую ленту — то есть ровно не тот кадр, который нужен статье.
 */
const PRINT_ROUTES: StubRoute[] = [
  ...HONEST_SIGN_ROUTES,
  {
    path: /^\/auth\/me/,
    handler: () => ({ separate_marking_print_enabled: false }),
  },
  {
    path: /^\/operations\/marking-codes\/print-templates\/resolve/,
    handler: () => ({
      id: 'tpl-demo',
      seller_id: null,
      product_id: null,
      user_id: null,
      name: 'ШК ВБ + ЧЗ',
      layout: {
        units: [
          { block: 'label', copies: 1 },
          { block: 'cz', copies: 1 },
        ],
      },
      is_default: true,
      is_system: true,
    }),
  },
]

/**
 * Что печатаем. `source: 'catalog'` — печать из карточки товара, без строки
 * упаковки: именно так открывается это окно из раздела «Честный знак».
 */
const PRINT_CTX: MarkingPrintContext = {
  token: 'demo',
  source: 'catalog',
  productId: 'p-7',
  documentNumber: null,
  qtyNeedPack: 1,
  markingAvailable: 180,
  qtyMarkingPrinted: 0,
  requiresHonestSign: true,
  skuCode: 'SW-BEG-S',
  productName: 'Свитшот бежевый, S',
  productLabel: {
    product_name: 'Свитшот бежевый, S',
    sku_code: 'SW-BEG-S',
    wb_vendor_code: 'GOR-SW-BEG',
    wb_size: 'S',
    wb_color: 'бежевый',
    wb_brand: 'Basic Cotton',
    wb_composition: 'хлопок 92%, эластан 8%',
    seller_name: 'ИП Горячкина',
    barcode: '2037123456819',
  },
  onPrinted: () => {},
}

/* ───────────────────────────── сцены ───────────────────────────── */

/**
 * Подмена fetch должна встать раньше первого запроса экрана, иначе он успеет
 * сходить на настоящий адрес и показать ошибку. Поэтому ставим её в
 * `useLayoutEffect` и до готовности не рендерим детей вовсе: React не запускает
 * эффекты того, что ещё не смонтировано. Откат обязателен — макет живёт внутри
 * портала, и оставленная подмена сломала бы обычные экраны.
 */
function StubbedScene({ routes, children }: { routes: StubRoute[]; children: ReactNode }) {
  const [ready, setReady] = useState(false)

  useLayoutEffect(() => {
    const restore = installStubFetch(routes)
    setReady(true)
    return restore
  }, [routes])

  return ready ? <>{children}</> : null
}

/** Основной экран раздела: запас кодов маркировки по товарам. */
export function HonestSignScene() {
  return (
    <StubbedScene routes={HONEST_SIGN_ROUTES}>
      <SceneShell route="/app/ff/honest-sign">
        <FfHonestSignPage token="demo" sellers={SCENE_SELLERS} />
      </SceneShell>
    </StubbedScene>
  )
}

/**
 * Тот же экран с открытым окном печати кодов.
 *
 * Окном управляет проп `open` самого `MarkingPrintDialog` (на боевом экране его
 * поднимает хук `useMarkingCodePrint` из кнопки печати в строке товара).
 * Поэтому диалог здесь просто отрисован поверх экрана с `open` — нажимать
 * кнопку в макете незачем, состояние и так то самое.
 */
export function HonestSignPrintScene() {
  return (
    <StubbedScene routes={PRINT_ROUTES}>
      <SceneShell route="/app/ff/honest-sign">
        <FfHonestSignPage token="demo" sellers={SCENE_SELLERS} />
        <MarkingPrintDialog
          open
          reprint={false}
          ctx={PRINT_CTX}
          busy={false}
          onBusyChange={() => {}}
          onClose={() => {}}
        />
      </SceneShell>
    </StubbedScene>
  )
}
