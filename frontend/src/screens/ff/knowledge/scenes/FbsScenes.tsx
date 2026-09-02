import { useEffect, useLayoutEffect, useState, type ReactNode } from 'react'

import { FfFbsOrdersScreen } from '../../../v2/FfFbsOrdersScreen'
import { FfFbsSupplyWorkspace } from '../../../v2/FfFbsSupplyWorkspace'
import type { FbsPrintAsset, FbsWorklistOrder, FbsWorkspace } from '../../../v2/fbsApi'
import { SceneShell } from './SceneShell'
import { PRODUCTS, SELLERS } from './data'
import { installStubFetch, type StubRoute } from './stubFetch'

/**
 * Живые макеты флоу «ФБС Wildberries»: заказы → подбор → упаковка и короба.
 *
 * Здесь нет ни одной копии экрана: рендерятся настоящие `FfFbsOrdersScreen` и
 * `FfFbsSupplyWorkspace` из портала. Единственное, чего им не хватает, — сервер,
 * поэтому под каждую сцену подкладывается таблица подставных ответов. Так
 * картинка в статье не может разъехаться с тем, что сотрудник видит на работе:
 * поменяется экран — поменяется и макет, без правок здесь.
 */

// ── Общая обвязка ────────────────────────────────────────────────────────────

const authHeaders = (token: string) => ({ Authorization: `Bearer ${token}` })

/**
 * Подмена `fetch` обязана встать РАНЬШЕ первого рендера экрана.
 *
 * Экраны стреляют запросами прямо из `useEffect` при монтировании: поставь
 * подмену обычным эффектом — первый запрос уже улетит настоящим `fetch`, упрётся
 * в отсутствующий сервер, и макет покажет красную плашку ошибки вместо данных.
 * Поэтому ставим её в `useLayoutEffect` и до готовности не рендерим детей вовсе.
 * Откат в размонтировании тоже обязателен: макет живёт внутри портала, и
 * оставленная подмена сломала бы настоящие экраны, открытые после него.
 */
function StubbedScene({
  routes,
  route,
  children,
}: {
  routes: StubRoute[]
  route: string
  children: ReactNode
}) {
  const [ready, setReady] = useState(false)

  useLayoutEffect(() => {
    const restore = installStubFetch(routes)
    setReady(true)
    return restore
  }, [routes])

  if (!ready) return null
  return <SceneShell route={route}>{children}</SceneShell>
}

// ── Выдуманные данные ────────────────────────────────────────────────────────

/**
 * Фото товара рисуем прямо в макете.
 *
 * Настоящие карточки WB — чужие картинки на чужом CDN: они протухают, требуют
 * сети и тащат в инструкцию чужой бренд. Серый прямоугольник с инициалами
 * держит строку той же высоты, что и на бою, и не зависит ни от чего.
 */
function photo(letters: string): string {
  const svg = `<svg xmlns="http://www.w3.org/2000/svg" width="240" height="240">
    <rect width="240" height="240" fill="#eef1f6"/>
    <rect x="48" y="60" width="144" height="120" rx="10" fill="#c7cedb"/>
    <text x="120" y="141" font-family="Inter, sans-serif" font-size="46" font-weight="700"
      fill="#5a6478" text-anchor="middle">${letters}</text>
  </svg>`
  return `data:image/svg+xml;utf8,${encodeURIComponent(svg.replace(/\s+/g, ' '))}`
}

/** Время считаем от «сейчас», а не фиксированной датой: иначе через сутки после
 *  съёмки все сроки на макете становятся просроченными и плашки краснеют. */
function inHours(hours: number): string {
  return new Date(Date.now() + hours * 3_600_000).toISOString()
}

function sellerByName(name: string) {
  return SELLERS.find((one) => one.name === name) ?? SELLERS[0]
}

/** Витрина товара для FBS: то же, что каталог отдал бы про карточку WB. */
type DemoCard = {
  productId: string
  name: string
  sku: string
  barcode: string
  sellerArticle: string
  wbArticle: number
  chrtId: number
  size: string | null
  color: string
  category: string
  image: string
  sellerId: string
  sellerName: string
}

function card(
  productSku: string,
  extra: {
    sellerArticle: string
    wbArticle: number
    chrtId: number
    size: string | null
    color: string
    category: string
    letters: string
  },
): DemoCard {
  // Названия, штрихкоды и продавцов берём из общего справочника макетов: во всех
  // статьях базы знаний должен встречаться один и тот же выдуманный склад.
  const product = PRODUCTS.find((one) => one.sku === productSku)!
  const seller = sellerByName(product.seller)
  return {
    productId: product.id,
    name: product.name,
    sku: product.wbBarcode,
    barcode: product.barcode,
    sellerArticle: extra.sellerArticle,
    wbArticle: extra.wbArticle,
    chrtId: extra.chrtId,
    size: extra.size,
    color: extra.color,
    category: extra.category,
    image: photo(extra.letters),
    sellerId: seller.id,
    sellerName: seller.name,
  }
}

const TSHIRT_M = card('TS-WHT-M', {
  sellerArticle: 'TSHIRT-WHITE',
  wbArticle: 178452301,
  chrtId: 421700111,
  size: 'M',
  color: 'Белый',
  category: 'Футболки',
  letters: 'ФБ',
})
const TSHIRT_L = card('TS-WHT-L', {
  sellerArticle: 'TSHIRT-WHITE',
  wbArticle: 178452301,
  chrtId: 421700112,
  size: 'L',
  color: 'Белый',
  category: 'Футболки',
  letters: 'ФБ',
})
const HOODIE_L = card('HD-GRY-L', {
  sellerArticle: 'HOODIE-GREY',
  wbArticle: 191203744,
  chrtId: 438110255,
  size: 'L',
  color: 'Серый',
  category: 'Худи',
  letters: 'ХД',
})
const SNEAKERS = card('SN-RUN-42', {
  sellerArticle: 'SNEAKERS-RUN',
  wbArticle: 204338910,
  chrtId: 455901042,
  size: '42',
  color: 'Чёрный',
  category: 'Кроссовки',
  letters: 'КР',
})
const SOCKS = card('SK-SPT-3', {
  sellerArticle: 'SOCKS-SPORT',
  wbArticle: 204338977,
  chrtId: 455901077,
  size: null,
  color: 'Белый',
  category: 'Носки',
  letters: 'НС',
})

/** Склады селлера в кабинете WB — куда физически сдаётся поставка. */
const WB_KOLEDINO = { id: 507, name: 'Коледино' }
const WB_ELEKTROSTAL = { id: 686, name: 'Электросталь' }
const WMS_WAREHOUSE = { id: 'wh-1', name: 'Основной склад' }

type OrderSeed = {
  id: string
  wbOrderId: number
  card: DemoCard
  wbWarehouse: { id: number; name: string }
  deadlineInHours: number
  canPvz: boolean
  legal?: boolean
  cellCode: string
}

function order(seed: OrderSeed): FbsWorklistOrder {
  return {
    id: seed.id,
    marketplace: 'wb',
    external_order_id: null,
    wb_order_id: seed.wbOrderId,
    status: 'new',
    wb_status: 'new',
    supplier_status: 'new',
    seller: { id: seed.card.sellerId, name: seed.card.sellerName },
    wb_warehouse: seed.wbWarehouse,
    wms_warehouse: WMS_WAREHOUSE,
    product: {
      id: seed.card.productId,
      name: seed.card.name,
      image_url: seed.card.image,
      seller_article: seed.card.sellerArticle,
      wb_article: seed.card.wbArticle,
      barcode: seed.card.barcode,
      sku: seed.card.sku,
      chrt_id: seed.card.chrtId,
      category: seed.card.category,
      color: seed.card.color,
      size: seed.card.size,
    },
    positions: [],
    inventory: {
      available_unpacked: 12,
      locations: [{ id: `loc-${seed.cellCode}`, code: seed.cellCode, available_unpacked: 12 }],
    },
    buyer_type: seed.legal ? 'legal' : 'individual',
    cargo_type: 'mgt',
    can_pvz: seed.canPvz,
    // Честный знак этим товарам не нужен — иначе в макете пришлось бы объяснять
    // ещё и маркировку, а это отдельный шаг и отдельная статья.
    metadata: {
      required: [],
      optional: [],
      states: [],
      delivery_allowed: true,
      last_checked_at: null,
    },
    sticker: { code: null, status: 'not_requested', asset_url: null, applied_at: null },
    pick: { status: 'pending', location_code: seed.cellCode, picked_at: null },
    pack: { status: 'pending', packed_at: null },
    created_at_wb: inHours(-14),
    deadline_at: inHours(seed.deadlineInHours),
    supply_id: null,
    selection_blockers: [],
  }
}

/** Новые заказы: шесть штук по двум селлерам и двум складам WB. */
function newOrders(): FbsWorklistOrder[] {
  return [
    order({ id: 'o-1', wbOrderId: 3941200011, card: TSHIRT_M, wbWarehouse: WB_KOLEDINO, deadlineInHours: 9, canPvz: false, cellCode: 'А-01-11' }),
    order({ id: 'o-2', wbOrderId: 3941200018, card: TSHIRT_M, wbWarehouse: WB_KOLEDINO, deadlineInHours: 31, canPvz: false, cellCode: 'А-01-11' }),
    order({ id: 'o-3', wbOrderId: 3941200024, card: TSHIRT_L, wbWarehouse: WB_KOLEDINO, deadlineInHours: 33, canPvz: false, cellCode: 'А-01-12' }),
    order({ id: 'o-4', wbOrderId: 3941200037, card: HOODIE_L, wbWarehouse: WB_KOLEDINO, deadlineInHours: 54, canPvz: false, cellCode: 'Б-02-04' }),
    order({ id: 'o-5', wbOrderId: 3941200052, card: SNEAKERS, wbWarehouse: WB_ELEKTROSTAL, deadlineInHours: 76, canPvz: true, cellCode: 'В-03-07' }),
    order({ id: 'o-6', wbOrderId: 3941200061, card: SOCKS, wbWarehouse: WB_ELEKTROSTAL, deadlineInHours: 92, canPvz: true, legal: true, cellCode: 'В-03-08' }),
  ]
}

const WAREHOUSE_OPTIONS = [
  { id: '507', name: 'Коледино', wb_warehouse: WB_KOLEDINO },
  { id: '686', name: 'Электросталь', wb_warehouse: WB_ELEKTROSTAL },
]

// ── Сцена 1. Первый экран раздела: список новых заказов ──────────────────────

const ORDERS_ROUTES: StubRoute[] = [
  {
    path: /^\/operations\/fbs-orders\/worklist/,
    handler: () => ({
      items: newOrders(),
      next_cursor: null,
      server_now: new Date().toISOString(),
      warehouse_options: WAREHOUSE_OPTIONS,
    }),
  },
  {
    // Сводка среднего времени сборки над таблицей. Без неё блок честно пишет
    // «—» вместо цифр, и в статье это выглядит поломкой, а не пустотой.
    path: /^\/fbs\/assembly-time/,
    handler: () => ({
      hours: 6.4,
      orders: 128,
      within_12_hours_percent: 92,
      within_24_hours_percent: 99,
    }),
  },
]

export function FbsOrdersScene() {
  return (
    <StubbedScene routes={ORDERS_ROUTES} route="/app/ff/fbs">
      <FfFbsOrdersScreen
        token="demo"
        authHeaders={authHeaders}
        sellers={SELLERS}
        // Кнопку «Синхронизировать заказы» видит администратор — именно про неё
        // говорит статья, когда объясняет, откуда в списке берутся заказы.
        isAdmin
      />
    </StubbedScene>
  )
}

// ── Поставка, которую собираем в сценах 2 и 3 ────────────────────────────────

const SUPPLY_ID = 'sup-318'
const SUPPLY_CARDS = [TSHIRT_M, TSHIRT_L, HOODIE_L]

/** Сколько единиц каждого товара в поставке и где они лежат на складе. */
const SUPPLY_LINES = [
  { card: TSHIRT_M, cellId: 'loc-a11', cellCode: 'А-01-11', planned: 4, picked: 2, onHand: 24 },
  { card: TSHIRT_L, cellId: 'loc-a12', cellCode: 'А-01-12', planned: 3, picked: 1, onHand: 15 },
  { card: HOODIE_L, cellId: 'loc-b24', cellCode: 'Б-02-04', planned: 2, picked: 0, onHand: 8 },
]

const SUPPLY_TOTAL = SUPPLY_LINES.reduce((sum, line) => sum + line.planned, 0)

/**
 * Сколько единиц уже снято с полки — единственное живое состояние макета.
 *
 * Макет открывают не только ради снимка: в проигрывателе сценария сотрудник
 * может пикнуть штрихкод сам. Держать снятое неизменной константой значит либо
 * ничего не менять на экране в ответ на скан, либо уронить его — экран ждёт от
 * сервера настоящий результат снятия. Поэтому счётчики живут здесь и правятся
 * теми же ручками, что и на бою; при перезагрузке страницы всё возвращается к
 * исходному состоянию.
 */
const pickedUnits = new Map<string, number>(
  SUPPLY_LINES.map((line) => [line.card.productId, line.picked]),
)

function pickedOf(productId: string): number {
  return pickedUnits.get(productId) ?? 0
}

function totalPicked(): number {
  return SUPPLY_LINES.reduce((sum, line) => sum + pickedOf(line.card.productId), 0)
}

/** Тело запроса подставного сервера: экран всегда шлёт JSON-строку. */
function requestBody(init: RequestInit | undefined): Record<string, unknown> {
  try {
    return typeof init?.body === 'string' ? JSON.parse(init.body) : {}
  } catch {
    return {}
  }
}

/**
 * Хвост кода маркировки — последние символы КИЗ, по которым оператор сверяет
 * строку с этикеткой. Берём буквы и цифры, а не последние цифры номера заказа:
 * иначе на картинке в инструкции хвост кода не отличить от номера заказа,
 * который стоит в той же строке.
 */
function kizTailFor(wbOrderId: number): string {
  const alphabet = 'ACDEFGHJKLMNPQRTUVWXY3479'
  let value = wbOrderId
  let tail = ''
  for (let position = 0; position < 4; position += 1) {
    tail += alphabet[value % alphabet.length]
    value = Math.floor(value / alphabet.length) + 17
  }
  return tail
}

/**
 * Шаг, на котором застали поставку. Стадию выбирает не макет, а ответ сервера:
 * рабочее пространство само открывает вкладку по `workspace.stage`.
 */
type SupplyStage = 'picking' | 'packing' | 'handoff_prep'

/**
 * Сколько заказов на шаге упаковки уже прошли стол: стикер напечатан и наклеен,
 * Честный знак со стикера внесён. Ровно из-за них в статье видно, чем зелёная
 * строка с хвостом кода отличается от белой, где сканировать ещё нечего.
 */
const MARKED_ORDERS = 4

/** Заказы поставки: по одной единице на заказ — так их и отдаёт WB. */
function supplyOrders(stage: SupplyStage): Array<FbsWorkspace['orders'][number]> {
  const done = stage === 'handoff_prep'
  const marking = stage === 'packing'
  const rows: Array<FbsWorkspace['orders'][number]> = []
  let index = 0
  let wbOrderId = 3941200011
  for (const line of SUPPLY_LINES) {
    for (let unit = 0; unit < line.planned; unit += 1) {
      wbOrderId += 7
      const picked = done || marking || unit < pickedOf(line.card.productId)
      // На шаге упаковки часть заказов уже готова, остальные ждут своей очереди.
      const ready = done || (marking && index < MARKED_ORDERS)
      const tail = kizTailFor(wbOrderId)
      rows.push({
        ...order({
          id: `so-${index + 1}`,
          wbOrderId,
          card: line.card,
          wbWarehouse: WB_KOLEDINO,
          deadlineInHours: 30,
          canPvz: false,
          cellCode: line.cellCode,
        }),
        status: ready ? 'packed' : 'assembling',
        supply_id: SUPPLY_ID,
        pick: {
          status: picked ? 'picked' : 'pending',
          location_code: line.cellCode,
          picked_at: picked ? inHours(-1) : null,
        },
        pack: { status: ready ? 'packed' : 'pending', packed_at: ready ? inHours(-0.5) : null },
        sticker: ready
          ? { code: `WB-${wbOrderId}`, status: 'applied', asset_url: null, applied_at: inHours(-0.4) }
          : { code: null, status: 'not_requested', asset_url: null, applied_at: null },
        // Одежда маркируется Честным знаком — на шаге упаковки это и есть работа
        // оператора. На остальных шагах маркировку не показываем: у неё своя
        // статья, и мешать её в кадр про подбор или короба незачем.
        metadata: marking
          ? {
              required: ['sgtin'],
              optional: [],
              states: [
                ready
                  ? {
                      kind: 'sgtin',
                      status: 'accepted' as const,
                      reason: null,
                      source: 'operator' as const,
                      value_tail: tail,
                    }
                  : { kind: 'sgtin', status: 'missing' as const, reason: null, value_tail: null },
              ],
              delivery_allowed: false,
              last_checked_at: inHours(-0.3),
            }
          : { required: [], optional: [], states: [], delivery_allowed: true, last_checked_at: null },
        tape_order_index: index,
      })
      index += 1
    }
  }
  return rows
}

function boxQrAsset(id: string): FbsPrintAsset {
  return {
    id,
    kind: 'box_qr',
    status: 'ready',
    content_type: 'image/svg+xml',
    width_mm: 58,
    height_mm: 40,
    preview_url: photo('QR'),
    download_url: null,
    checksum: null,
    applied_at: null,
    error: null,
  }
}

/**
 * Одна и та же поставка на трёх шагах.
 *
 * Вкладку внутри рабочего пространства выбирает не макет, а сервер: экран
 * ставит её из `workspace.stage`. Поэтому «подбор», «упаковка и маркировка» и
 * «короба» — это не три разных экрана, а один и тот же с разным этапом в
 * ответе.
 */
function workspace(stage: SupplyStage): FbsWorkspace {
  const packed = stage === 'handoff_prep'
  const orders = supplyOrders(stage)
  // На шаге упаковки готова часть заказов: столько же строк зелёные, столько же
  // посчитано в «напечатано» и «упаковано» над списком.
  const readyOrders = packed ? SUPPLY_TOTAL : stage === 'packing' ? MARKED_ORDERS : 0
  return {
    supply: {
      id: SUPPLY_ID,
      marketplace: 'wb',
      wb_supply_id: 'WB-GI-1284471',
      name: 'Поставка 000318',
      status: packed ? 'packed' : 'assembling',
      delivery_type: 'warehouse_sc',
      seller: { id: TSHIRT_M.sellerId, name: TSHIRT_M.sellerName },
      wb_warehouse: WB_KOLEDINO,
      wms_warehouse: WMS_WAREHOUSE,
      planned_destination: null,
      planned_shipment_date: new Date(Date.now() + 86_400_000).toISOString().slice(0, 10),
      nearest_deadline_at: inHours(30),
      packaging_task_id: 'pt-318',
      barcode_asset: null,
    },
    stage,
    progress: {
      picked: stage === 'picking' ? totalPicked() : SUPPLY_TOTAL,
      packed: readyOrders,
      metadata_ready: readyOrders,
      stickers_ready: readyOrders,
      total: SUPPLY_TOTAL,
    },
    blockers: [],
    orders,
    cargo_places: [],
    boxes: packed
      ? [
          {
            id: 'pbx-1',
            box_number: 1,
            barcode: '2200000004723',
            // В первый короб уехали футболки, во второй — худи: в статье видно,
            // что короб — это не «весь заказ», а конкретные единицы товара.
            assigned_order_ids: orders.slice(0, 7).map((one) => one.id),
            trbx_id: 'trbx-1',
            wb_trbx_id: 'WB-TRBX-880141',
            qr_asset: boxQrAsset('asset-box-1'),
            without_distribution: false,
          },
          {
            id: 'pbx-2',
            box_number: 2,
            barcode: '2200000004730',
            assigned_order_ids: orders.slice(7).map((one) => one.id),
            trbx_id: 'trbx-2',
            wb_trbx_id: 'WB-TRBX-880142',
            qr_asset: boxQrAsset('asset-box-2'),
            without_distribution: false,
          },
        ]
      : [],
    delivery_preflight: null,
    last_wb_sync_at: inHours(-0.2),
    server_now: new Date().toISOString(),
  }
}

// ── Сцена 2. Подбор ──────────────────────────────────────────────────────────

/** Карточка поставки для экрана подбора: он читает её отдельной ручкой. */
const SUPPLY_DETAIL = {
  id: SUPPLY_ID,
  name: 'Поставка 000318',
  wb_supply_id: 'WB-GI-1284471',
  document_number: '000318',
  display_number: '000318',
  warehouse_name: WMS_WAREHOUSE.name,
  status: 'assembling',
  seller_id: TSHIRT_M.sellerId,
  seller_name: TSHIRT_M.sellerName,
  planned_shipment_date: new Date(Date.now() + 86_400_000).toISOString().slice(0, 10),
}

/**
 * Места подбора: что снять, сколько и из какой ячейки.
 *
 * У поставки ФБС состава в документе нет вовсе — товары приезжают вместе с
 * местами, и экран подбора собирает список именно отсюда.
 */
function pickOptions() {
  return SUPPLY_LINES.map((line) => {
    const picked = pickedOf(line.card.productId)
    return {
      product_id: line.card.productId,
      sku_code: line.card.sku,
      product_name: line.card.name,
      planned_qty: line.planned,
      picked_qty: picked,
      locations: [
        {
          storage_location_id: line.cellId,
          location_code: line.cellCode,
          quantity: line.onHand,
          reserved: line.planned,
          available: line.onHand - picked,
          picked,
          // Разбивку по таре сервер отдаёт всегда. Без неё экран считает
          // вместимость места по старой совместимой формуле и показывает уже
          // снятое дважды — «внутри 26 шт» там, где на полке лежит 24.
          sources: [
            {
              quantity: line.onHand - picked,
              is_loose: true,
              source_label: 'Россыпью',
              container_path: [],
              picked,
            },
          ],
        },
      ],
    }
  })
}

/** Скан в подборе: сначала ячейка, потом товар — как на настоящем сервере. */
function pickScan(init: RequestInit | undefined) {
  const body = requestBody(init)
  const barcode = String(body.barcode ?? '').trim()
  const empty = {
    storage_location_id: null,
    location_code: null,
    product_id: null,
    sku_code: null,
    product_name: null,
    picked_qty: null,
    allocation_quantity: null,
    container_kind: null,
    container_id: null,
    container_code: null,
  }

  const cell = SUPPLY_LINES.find((line) => line.cellCode === barcode)
  if (cell) {
    return {
      ...empty,
      kind: 'location',
      storage_location_id: cell.cellId,
      location_code: cell.cellCode,
    }
  }

  const line = SUPPLY_LINES.find(
    (one) => one.card.barcode === barcode || one.card.sku === barcode,
  )
  if (!line) {
    // Незнакомый штрихкод — не молчаливый успех: экран покажет ту же ошибку,
    // что и на бою, и сотрудник поймёт, что пикнул не то.
    throw new Error(`Штрихкод ${barcode} — ни место, ни товар этой поставки`)
  }
  // Больше плана не снимаем: это то же ограничение, что держит сервер.
  const next = Math.min(line.planned, pickedOf(line.card.productId) + 1)
  pickedUnits.set(line.card.productId, next)
  return {
    ...empty,
    kind: 'product',
    storage_location_id: line.cellId,
    location_code: line.cellCode,
    product_id: line.card.productId,
    sku_code: line.card.sku,
    product_name: line.card.name,
    picked_qty: next,
    allocation_quantity: next,
  }
}

/** Ручная правка числа в строке места. */
function pickSet(init: RequestInit | undefined) {
  const body = requestBody(init)
  const productId = String(body.product_id ?? '')
  const line = SUPPLY_LINES.find((one) => one.card.productId === productId)
  const quantity = Math.max(0, Math.min(line?.planned ?? 0, Number(body.quantity) || 0))
  if (line) pickedUnits.set(productId, quantity)
  return {
    product_id: productId,
    storage_location_id: line?.cellId ?? null,
    quantity,
  }
}

/** Каталог WB: из него экран подбора берёт фото, артикул продавца, ШК и размер. */
const WB_CATALOG = SUPPLY_CARDS.map((one) => ({
  id: one.productId,
  name: one.name,
  sku_code: one.sku,
  seller_name: one.sellerName,
  wb_nm_id: one.wbArticle,
  wb_vendor_code: one.sellerArticle,
  wb_subject_name: one.category,
  wb_primary_image_url: one.image,
  wb_barcodes: [one.barcode],
  wb_primary_barcode: one.barcode,
  wb_size: one.size,
  wb_color: one.color,
}))

const PICK_ROUTES: StubRoute[] = [
  // Порядок важен: «голая» карточка поставки стоит последней, иначе её регулярка
  // перехватила бы и /workspace, и /pick-options.
  { path: /^\/operations\/fbs-supplies\/[^/?]+\/workspace/, handler: () => workspace('picking') },
  { path: /^\/operations\/fbs-supplies\/[^/?]+\/pick-options/, handler: () => pickOptions() },
  {
    method: 'POST',
    path: /^\/operations\/fbs-supplies\/[^/?]+\/pick\/scan/,
    handler: (_match, init) => pickScan(init),
  },
  {
    method: 'POST',
    path: /^\/operations\/fbs-supplies\/[^/?]+\/pick\/set/,
    handler: (_match, init) => pickSet(init),
  },
  { path: /^\/operations\/fbs-supplies\/[^/?]+(?:\?|$)/, handler: () => SUPPLY_DETAIL },
  { path: /^\/products\/linked-wb-catalog/, handler: () => WB_CATALOG },
]

/**
 * Раскрывает строки подбора один раз после загрузки.
 *
 * На бою кладовщик сам открывает строку и видит ячейку, из которой снимать
 * товар. На неподвижной картинке в инструкции строку никто не откроет, а без
 * неё шаг «подбор» теряет главное — адрес товара на складе. Поэтому макет
 * нажимает ровно те же стрелки, что нажал бы человек: экран не переписан, он
 * просто стартует в раскрытом виде. Не нашли стрелок за шесть секунд — тихо
 * сдаёмся, картинка останется со свёрнутыми строками.
 */
function useOpenedPickRows() {
  useEffect(() => {
    let attempts = 0
    const timer = window.setInterval(() => {
      attempts += 1
      const toggles = document.querySelectorAll<HTMLButtonElement>(
        '[data-testid^="pick-table-expand-"]',
      )
      if (toggles.length > 0) {
        toggles.forEach((toggle) => toggle.click())
        window.clearInterval(timer)
        return
      }
      if (attempts > 60) window.clearInterval(timer)
    }, 100)
    return () => window.clearInterval(timer)
  }, [])
}

export function FbsPickScene() {
  useOpenedPickRows()
  return (
    <StubbedScene routes={PICK_ROUTES} route="/app/ff/fbs">
      <FfFbsSupplyWorkspace
        token="demo"
        authHeaders={authHeaders}
        supplyId={SUPPLY_ID}
        open
        onClose={() => {}}
      />
    </StubbedScene>
  )
}

// ── Сцена 3. Упаковка и короба ───────────────────────────────────────────────

const PACK_ROUTES: StubRoute[] = [
  {
    path: /^\/operations\/fbs-supplies\/[^/?]+\/workspace/,
    handler: () => workspace('handoff_prep'),
  },
]

export function FbsPackScene() {
  return (
    <StubbedScene routes={PACK_ROUTES} route="/app/ff/fbs">
      <FfFbsSupplyWorkspace
        token="demo"
        authHeaders={authHeaders}
        supplyId={SUPPLY_ID}
        open
        onClose={() => {}}
      />
    </StubbedScene>
  )
}

// ── Сцена 4. Упаковка и маркировка ───────────────────────────────────────────

/**
 * Задание упаковки поставки.
 *
 * Вкладка «Упаковка и маркировка» рисует список заказов только вместе с ним:
 * без задания на её месте висит плашка «Загружаем существующее задание
 * упаковки…». Из строк задания берутся ТЗ на упаковку и печать ЧЗ со ШК,
 * поэтому у каждого товара поставки здесь своя строка.
 */
const PACKAGING_TASK = {
  id: 'pt-318',
  document_number: '000318',
  display_number: '000318',
  warehouse_id: WMS_WAREHOUSE.id,
  warehouse_name: WMS_WAREHOUSE.name,
  seller_id: TSHIRT_M.sellerId,
  seller_name: TSHIRT_M.sellerName,
  status: 'in_progress',
  marketplace_unload_request_id: null,
  inbound_intake_request_id: null,
  is_complete: false,
  created_at: inHours(-2),
  updated_at: inHours(-0.3),
  lines: SUPPLY_LINES.map((line, index) => {
    const packed = Math.min(line.planned, Math.max(0, MARKED_ORDERS - SUPPLY_LINES
      .slice(0, index)
      .reduce((sum, one) => sum + one.planned, 0)))
    return {
      id: `ptl-${index + 1}`,
      product_id: line.card.productId,
      seller_id: line.card.sellerId,
      seller_name: line.card.sellerName,
      sku_code: line.card.sku,
      product_name: line.card.name,
      storage_location_id: line.cellId,
      storage_location_code: line.cellCode,
      packaging_instructions:
        'Сложить втрое, вложить в курьерский пакет 24×32, стикер заказа — на лицевую сторону.',
      requires_honest_sign: true,
      qty_total: line.planned,
      qty_suggested_packed: line.planned,
      qty_confirmed_packed: packed,
      qty_need_pack: line.planned - packed,
      qty_packed_in_task: packed,
      qty_done: packed,
      qty_marking_printed: packed,
      qty_marking_external: 0,
      qty_product_label_printed: packed,
      marking_available_count: line.planned,
      is_complete: packed === line.planned,
    }
  }),
}

const MARKING_ROUTES: StubRoute[] = [
  { path: /^\/operations\/fbs-supplies\/[^/?]+\/workspace/, handler: () => workspace('packing') },
  { path: /^\/operations\/packaging-tasks\/[^/?]+/, handler: () => PACKAGING_TASK },
]

export function FbsMarkingScene() {
  return (
    <StubbedScene routes={MARKING_ROUTES} route="/app/ff/fbs">
      <FfFbsSupplyWorkspace
        token="demo"
        authHeaders={authHeaders}
        supplyId={SUPPLY_ID}
        open
        onClose={() => {}}
      />
    </StubbedScene>
  )
}
