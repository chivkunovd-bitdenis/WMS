import { useEffect, useLayoutEffect, useState } from 'react'
import type { ReactNode } from 'react'

import { FfProductsCatalogScreen } from '../../../v2/FfProductsCatalogScreen'
import { PRODUCTS, SELLERS } from './data'
import type { DemoProduct } from './data'
import { SceneShell } from './SceneShell'
import { installStubFetch } from './stubFetch'
import type { StubRoute } from './stubFetch'

/**
 * Живые макеты каталога фулфилмента — списка карточек товаров, которыми склад
 * пользуется каждый день, и окна ручного создания карточки.
 *
 * Экран настоящий (`FfProductsCatalogScreen`), выдуманы только данные: их
 * отдаёт подставной fetch вместо сервера. Так картинка в инструкции не зависит
 * от того, что сейчас в базе, и не показывает чужие артикулы и остатки.
 */

/* ─────────────────────────── выдуманные данные ─────────────────────────── */

/**
 * Товары сверх общего набора `data.ts`. Каталог на пять строк выглядит как
 * склад, который ещё не начал работать, — восемь читаются как рабочий список.
 * Артикулы и штрихкоды продолжают ту же линейку, что и в `PRODUCTS`, и те же
 * позиции показывает макет «Честного знака».
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

/**
 * Всё, чего нет в общем наборе, но что показывает каталог: карточка
 * маркетплейса, остаток на складе и настройка передачи остатка в FBS.
 *
 * `stock` — сколько всего лежит на фулфилменте, `inStorage` — сколько из этого
 * уже разложено по ячейкам (остальное ещё в сортировке), `reserved` — сколько
 * отложено под направления. Свободный остаток экран считает сам, поэтому
 * держим числа согласованными между собой.
 */
type CatalogMeta = {
  category: string
  vendorCode: string
  size: string
  color: string
  brand: string
  nmId: number
  honestSign: boolean
  /** Свободные коды маркировки — тот же запас, что в макете «Честного знака». */
  markingCodes: number
  packaging: string | null
  stock: number
  inStorage: number
  reserved: number
  /** Доля свободного остатка, которую склад отдаёт в FBS; null — не передаём. */
  fbsPercent: number | null
}

const CATALOG_META: Record<string, CatalogMeta> = {
  'p-1': {
    category: 'Футболки',
    vendorCode: 'GOR-TS-WHT',
    size: 'M',
    color: 'белый',
    brand: 'Basic Cotton',
    nmId: 178452301,
    honestSign: true,
    markingCodes: 420,
    packaging: 'Сложить пополам, пакет 30×40, этикетка на лицевую сторону.',
    stock: 1240,
    inStorage: 1100,
    reserved: 260,
    fbsPercent: 30,
  },
  'p-2': {
    category: 'Футболки',
    vendorCode: 'GOR-TS-WHT',
    size: 'L',
    color: 'белый',
    brand: 'Basic Cotton',
    nmId: 178452302,
    honestSign: true,
    markingCodes: 6,
    packaging: 'Сложить пополам, пакет 30×40, этикетка на лицевую сторону.',
    stock: 860,
    inStorage: 860,
    reserved: 0,
    fbsPercent: 30,
  },
  'p-3': {
    category: 'Худи',
    vendorCode: 'GOR-HD-GRY',
    size: 'L',
    color: 'серый',
    brand: 'Basic Cotton',
    nmId: 178452310,
    honestSign: true,
    markingCodes: 0,
    packaging: null,
    stock: 320,
    inStorage: 300,
    reserved: 60,
    fbsPercent: null,
  },
  'p-4': {
    category: 'Кроссовки',
    vendorCode: 'CTP-SN-RUN',
    size: '42',
    color: 'чёрный',
    brand: 'Cityline',
    nmId: 204118907,
    honestSign: true,
    markingCodes: 260,
    packaging: 'Обувная коробка в пакет 40×60, этикетка на торец коробки.',
    stock: 145,
    inStorage: 145,
    reserved: 0,
    fbsPercent: 50,
  },
  'p-5': {
    category: 'Носки',
    vendorCode: 'CTP-SK-SPT',
    size: '41-44',
    color: 'серый меланж',
    brand: 'Cityline',
    nmId: 204118915,
    honestSign: true,
    markingCodes: 90,
    packaging: null,
    stock: 2400,
    inStorage: 2200,
    reserved: 400,
    fbsPercent: 20,
  },
  'p-6': {
    category: 'Худи',
    vendorCode: 'GOR-HD-GRY',
    size: 'M',
    color: 'серый',
    brand: 'Basic Cotton',
    nmId: 178452311,
    honestSign: true,
    markingCodes: 0,
    packaging: null,
    stock: 280,
    inStorage: 280,
    reserved: 0,
    fbsPercent: null,
  },
  'p-7': {
    category: 'Свитшоты',
    vendorCode: 'GOR-SW-BEG',
    size: 'S',
    color: 'бежевый',
    brand: 'Basic Cotton',
    nmId: 178452320,
    honestSign: true,
    markingCodes: 180,
    packaging: 'Сложить пополам, пакет 30×40, этикетка на лицевую сторону.',
    stock: 96,
    inStorage: 90,
    reserved: 0,
    fbsPercent: null,
  },
  'p-8': {
    category: 'Головные уборы',
    vendorCode: 'CTP-CP-BLK',
    size: 'one size',
    color: 'чёрный',
    brand: 'Cityline',
    nmId: 204118930,
    honestSign: false,
    markingCodes: 0,
    packaging: null,
    stock: 540,
    inStorage: 540,
    reserved: 0,
    fbsPercent: 35,
  },
}

const CATEGORIES = [...new Set(Object.values(CATALOG_META).map((meta) => meta.category))].sort()

/** Склады фулфилмента: экран берёт их только для настройки остатка FBS. */
const WAREHOUSES = [
  { id: 'wh-1', name: 'Основной склад', code: 'main', is_operational: true },
  { id: 'wh-2', name: 'Склад возвратов', code: 'returns', is_operational: true },
]

function freeStock(meta: CatalogMeta): number {
  return meta.stock - meta.reserved
}

function catalogRow(product: DemoProduct) {
  const meta = CATALOG_META[product.id]
  const free = freeStock(meta)
  return {
    id: product.id,
    seller_id: SELLER_ID_BY_NAME[product.seller] ?? null,
    seller_name: product.seller,
    name: product.name,
    sku_code: product.sku,
    wb_nm_id: meta.nmId,
    wb_vendor_code: meta.vendorCode,
    ozon_sku: null,
    ozon_offer_id: null,
    wb_subject_name: meta.category,
    // Фото нет: ссылка вела бы на картинку маркетплейса, а макет должен
    // рисоваться без сети. Экран покажет заглушку вместо фотографии.
    wb_primary_image_url: null,
    wb_barcodes: [product.wbBarcode],
    wb_primary_barcode: product.wbBarcode,
    wb_size: meta.size,
    wb_color: meta.color,
    wb_brand: meta.brand,
    wb_composition: 'хлопок 92%, эластан 8%',
    packaging_instructions: meta.packaging,
    country_of_origin_iso_code: null,
    requires_honest_sign: meta.honestSign,
    has_packaging_instructions: meta.packaging != null,
    marking_available_count: meta.markingCodes,
    fbs_stock_sync_enabled: meta.fbsPercent != null,
    fbs_stock_limit: null,
    fbs_published_amount:
      meta.fbsPercent == null ? null : Math.floor((free * meta.fbsPercent) / 100),
    fbs_percent: meta.fbsPercent,
    fbs_same_everywhere: true,
    fbs_sync_status: null,
  }
}

function stockRow(product: DemoProduct) {
  const meta = CATALOG_META[product.id]
  const free = freeStock(meta)
  return {
    product_id: product.id,
    sku_code: product.sku,
    product_name: product.name,
    quantity: meta.stock,
    quantity_in_sorting: meta.stock - meta.inStorage,
    quantity_in_storage: meta.inStorage,
    reserved: meta.reserved,
    available: free,
    quantity_fbs: meta.reserved,
    quantity_reserved_directions: meta.reserved,
    quantity_free_fbo: free,
  }
}

function queryOf(match: RegExpMatchArray): URLSearchParams {
  return new URLSearchParams((match.input ?? '').split('?')[1] ?? '')
}

/**
 * Страница каталога. Фильтры по селлеру и поиску отрабатываем честно: в
 * проигрывателе сценария по макету можно щёлкать, и фильтр, который ничего не
 * меняет, выглядел бы сломанным.
 */
function catalogPagePayload(match: RegExpMatchArray) {
  const query = queryOf(match)
  const sellerId = query.get('seller_id') ?? ''
  const search = (query.get('search') ?? '').trim().toLowerCase()
  const category = query.get('category') ?? ''
  const items = ALL_PRODUCTS.filter((product) => {
    if (sellerId && SELLER_ID_BY_NAME[product.seller] !== sellerId) {
      return false
    }
    if (category && CATALOG_META[product.id].category !== category) {
      return false
    }
    if (!search) {
      return true
    }
    return (
      product.name.toLowerCase().includes(search) ||
      product.sku.toLowerCase().includes(search) ||
      product.wbBarcode.includes(search)
    )
  })
  return {
    items: items.map(catalogRow),
    total: items.length,
    scope_total: ALL_PRODUCTS.length,
    limit: Number(query.get('limit') ?? 100),
    offset: Number(query.get('offset') ?? 0),
    categories: CATEGORIES,
  }
}

/** Остатки запрашиваются ровно по тем товарам, что попали на страницу. */
function stockSummaryPayload(match: RegExpMatchArray) {
  const ids = queryOf(match).getAll('product_id')
  return ALL_PRODUCTS.filter((product) => ids.includes(product.id)).map(stockRow)
}

/* ───────────────────────── подставные адреса ───────────────────────── */

const CATALOG_ROUTES: StubRoute[] = [
  {
    path: /^\/products\/ff-catalog-page/,
    handler: (match) => catalogPagePayload(match),
  },
  {
    path: /^\/operations\/inventory-balances\/summary/,
    handler: (match) => stockSummaryPayload(match),
  },
  {
    // Экран перезапрашивает селлеров для выпадающего списка в окне создания.
    path: /^\/sellers/,
    handler: () => SELLERS,
  },
]

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

function CatalogScreen() {
  return (
    <FfProductsCatalogScreen
      token="demo"
      authHeaders={(t) => ({ Authorization: `Bearer ${t}` })}
      sellers={SELLERS}
      warehouses={WAREHOUSES}
      canManageCatalog
      addressStorageEnabled
    />
  )
}

/** Каталог товаров фулфилмента: список карточек, поиск и фильтры. */
export function CatalogScene() {
  return (
    <StubbedScene routes={CATALOG_ROUTES}>
      <SceneShell route="/app/ff/products">
        <CatalogScreen />
      </SceneShell>
    </StubbedScene>
  )
}

/** Значения, которыми макет заполняет форму нового товара. */
const NEW_PRODUCT = {
  seller: 'ИП Горячкина',
  name: 'Свитшот бежевый, M',
  sku: 'SW-BEG-M',
  vendor: 'GOR-SW-BEG',
  size: 'M',
  barcode: '2037123456826',
  length: '320',
  width: '240',
  height: '60',
  tz: 'Сложить пополам, пакет 30×40, этикетка на лицевую сторону.',
}

/**
 * React держит значение поля в своём состоянии и слушает событие `input`, а не
 * присваивание `value`. Поэтому пишем через нативный сеттер и сами шлём
 * событие — иначе поле в кадре останется пустым, хотя в DOM текст уже стоит.
 */
function typeInto(testId: string, value: string): void {
  const field = document.querySelector<HTMLInputElement | HTMLTextAreaElement>(
    `[data-testid="${testId}"]`,
  )
  if (!field) {
    return
  }
  const prototype =
    field instanceof HTMLTextAreaElement ? HTMLTextAreaElement.prototype : HTMLInputElement.prototype
  Object.getOwnPropertyDescriptor(prototype, 'value')?.set?.call(field, value)
  field.dispatchEvent(new Event('input', { bubbles: true }))
}

/**
 * Открывает окно ручного создания товара и заполняет его.
 *
 * Окно живёт во внутреннем состоянии экрана, пропа «открыть снаружи» у него
 * нет. Значит, единственный честный способ показать его — нажать ту же кнопку,
 * что нажимает оператор. Кнопка сначала догружает список селлеров, поэтому поля
 * ждём опросом, а не одним таймером наугад.
 */
function CreateDialogScript() {
  useEffect(() => {
    let cancelled = false
    const timers: number[] = []
    const sleep = (ms: number) =>
      new Promise<void>((resolve) => {
        timers.push(window.setTimeout(resolve, ms))
      })
    const waitFor = async <T extends Element>(selector: string): Promise<T | null> => {
      for (let attempt = 0; attempt < 60; attempt += 1) {
        const found = document.querySelector<T>(selector)
        if (found) {
          return found
        }
        await sleep(50)
        if (cancelled) {
          return null
        }
      }
      return null
    }

    void (async () => {
      const openButton = await waitFor<HTMLButtonElement>('[data-testid="ff-products-create"]')
      openButton?.click()
      const nameField = await waitFor<HTMLInputElement>('[data-testid="ff-manual-product-name"]')
      if (!nameField || cancelled) {
        return
      }

      // Селлер — выпадающий список MUI: значение выбирается кликом по пункту
      // меню, присваивание в поле здесь не работает. Само меню открывается по
      // `mousedown`, а не по `click` (так устроен MUI Select), поэтому шлём
      // именно это событие — от `element.click()` список не раскрывается.
      const sellerSelect = document.querySelector<HTMLElement>(
        '[data-testid="ff-manual-product-seller"] [role="combobox"]',
      )
      sellerSelect?.dispatchEvent(new MouseEvent('mousedown', { bubbles: true, button: 0 }))
      await waitFor<HTMLElement>('li[role="option"]')
      const option = Array.from(document.querySelectorAll<HTMLElement>('li[role="option"]')).find(
        (item) => item.textContent?.trim() === NEW_PRODUCT.seller,
      )
      option?.click()

      if (cancelled) {
        return
      }
      typeInto('ff-manual-product-name', NEW_PRODUCT.name)
      typeInto('ff-manual-product-sku', NEW_PRODUCT.sku)
      typeInto('ff-manual-product-vendor', NEW_PRODUCT.vendor)
      typeInto('ff-manual-product-size', NEW_PRODUCT.size)
      typeInto('ff-manual-product-barcode', NEW_PRODUCT.barcode)
      typeInto('ff-manual-product-length', NEW_PRODUCT.length)
      typeInto('ff-manual-product-width', NEW_PRODUCT.width)
      typeInto('ff-manual-product-height', NEW_PRODUCT.height)
      typeInto('ff-manual-product-tz', NEW_PRODUCT.tz)
    })()

    return () => {
      cancelled = true
      timers.forEach((timer) => window.clearTimeout(timer))
    }
  }, [])

  return null
}

/**
 * Каталог с открытым окном «Создать товар».
 *
 * Ручное создание карточки — основной путь: Excel грузят пачкой и редко, а
 * поштучно товар заводят руками, поэтому в статье нужен именно этот кадр.
 */
export function CatalogCreateScene() {
  return (
    <StubbedScene routes={CATALOG_ROUTES}>
      <SceneShell route="/app/ff/products">
        <CatalogScreen />
        <CreateDialogScript />
      </SceneShell>
    </StubbedScene>
  )
}
