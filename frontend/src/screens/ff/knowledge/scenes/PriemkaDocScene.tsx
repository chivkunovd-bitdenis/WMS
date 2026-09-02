import { useCallback, useEffect, useLayoutEffect, useState } from 'react'

import { FfInboundRequestView } from '../../FfInboundRequestView'
import type { WbProductCatalogRow } from '../../../../types/wbProductCatalog'
import { PRODUCTS, SELLERS, type DemoProduct } from './data'
import { SceneShell } from './SceneShell'
import { installStubFetch, type StubRoute } from './stubFetch'

/**
 * Живые макеты статьи «Приёмка»: один и тот же документ №000043 на четырёх
 * шагах процесса — черновик, короба и грузоместа, наполнение короба, сверка
 * перед завершением. Тот же документ виден в очереди (`PriemkaQueueScene`),
 * поэтому сотрудник по картинкам проходит один сквозной путь, а не четыре
 * разных документа.
 *
 * Экран документа (`FfInboundRequestView`) ходит на бэкенд обычным `fetch`
 * через `apiUrl()`. Сервера и входа в макетах нет, поэтому под каждой сценой
 * стоит подставной сервер: он отдаёт заранее собранный документ и те
 * справочники, за которыми экран идёт при загрузке.
 *
 * Про состав: в документе пять строк — на меньшем составе не показать сразу и
 * сошедшиеся строки, и недостачу, и излишек. Все пять демо-товаров из `data.ts`
 * показаны здесь под одним селлером: в жизни каталог приходит уже
 * отфильтрованным по селлеру документа (`/products/linked-wb-catalog?seller_id=`),
 * а построчно селлер на этом экране нигде не выводится.
 */

const SELLER = SELLERS[2] // ООО Ситипак — тот же селлер, что у документа №000043 в очереди
const WAREHOUSE = { id: 'wh-1', name: 'Основной склад', code: 'MSK-1' }

// Идентификатор документа нигде на экране не виден, но из него бэкенд собирает
// штрихкоды грузомест (`ICG-<первые 8 символов id>-0001`), поэтому он тут
// настоящего вида, а не «in-43».
const REQUEST_ID = '7f3ac91d-4e52-4a6b-9d81-2c6f0b5ae310'
const CARGO_BARCODE_PREFIX = 'ICG-7F3AC91D'

type LineSpec = {
  product: DemoProduct
  expectedQty: number
  lengthMm: number
  widthMm: number
  heightMm: number
  weightG: number
  size: string
  color: string
  subject: string
}

// Габариты и вес заданы у каждой строки не для красоты: без них в шапке
// документа литраж считается нулём, а вес показывается как «не указан», и на
// картинке в статье негде показать, откуда берётся оплата за хранение.
const LINE_SPECS: LineSpec[] = [
  {
    product: PRODUCTS[0],
    expectedQty: 30,
    lengthMm: 250,
    widthMm: 200,
    heightMm: 30,
    weightG: 180,
    size: 'M',
    color: 'белый',
    subject: 'Футболки',
  },
  {
    product: PRODUCTS[1],
    expectedQty: 24,
    lengthMm: 260,
    widthMm: 210,
    heightMm: 32,
    weightG: 195,
    size: 'L',
    color: 'белый',
    subject: 'Футболки',
  },
  {
    product: PRODUCTS[2],
    expectedQty: 16,
    lengthMm: 320,
    widthMm: 260,
    heightMm: 70,
    weightG: 620,
    size: 'L',
    color: 'серый',
    subject: 'Худи',
  },
  {
    product: PRODUCTS[3],
    expectedQty: 20,
    lengthMm: 340,
    widthMm: 220,
    heightMm: 130,
    weightG: 900,
    size: '42',
    color: 'чёрный',
    subject: 'Кроссовки',
  },
  {
    product: PRODUCTS[4],
    expectedQty: 20,
    lengthMm: 180,
    widthMm: 120,
    heightMm: 40,
    weightG: 150,
    size: '39-42',
    color: 'синий',
    subject: 'Носки',
  },
]

const CATALOG: WbProductCatalogRow[] = LINE_SPECS.map((spec, index) => ({
  id: spec.product.id,
  name: spec.product.name,
  sku_code: spec.product.sku,
  seller_name: SELLER.name,
  wb_nm_id: 191240500 + index,
  wb_vendor_code: spec.product.sku,
  wb_subject_name: spec.subject,
  // Фото намеренно нет: макет должен открываться без сети, а битая ссылка на
  // картинку WB выглядела бы на иллюстрации как поломка экрана.
  wb_primary_image_url: null,
  wb_barcodes: [spec.product.wbBarcode],
  wb_primary_barcode: spec.product.wbBarcode,
  wb_size: spec.size,
  wb_color: spec.color,
  wb_brand: 'CITYPACK',
}))

const LOCATIONS = [
  { id: 'loc-1', code: 'A-01', warehouse_id: WAREHOUSE.id, barcode: 'LOC-A-01' },
  { id: 'loc-2', code: 'A-02', warehouse_id: WAREHOUSE.id, barcode: 'LOC-A-02' },
  { id: 'loc-3', code: 'B-01', warehouse_id: WAREHOUSE.id, barcode: 'LOC-B-01' },
]

/** Факт по строке: «россыпью» (не в коробе) и итог, который считает бэкенд. */
type LineFact = { looseQty: number | null; effectiveQty: number | null }

function buildLines(facts: LineFact[]) {
  return LINE_SPECS.map((spec, index) => ({
    id: `ln-${index + 1}`,
    product_id: spec.product.id,
    sku_code: spec.product.sku,
    product_name: spec.product.name,
    wb_barcode: spec.product.wbBarcode,
    requires_honest_sign: false,
    length_mm: spec.lengthMm,
    width_mm: spec.widthMm,
    height_mm: spec.heightMm,
    weight_g: spec.weightG,
    volume_liters:
      Math.round((spec.lengthMm * spec.widthMm * spec.heightMm) / 1000) / 1000,
    added_by_fulfillment: false,
    expected_qty: spec.expectedQty,
    actual_qty: facts[index].looseQty,
    effective_actual_qty: facts[index].effectiveQty,
    defective_qty: 0,
    posted_qty: 0,
    storage_location_id: null,
    storage_location_code: null,
  }))
}

// Штрихкоды коробов — в том же виде, в каком их выдаёт бэкенд: префикс INB и
// четырнадцать символов Crockford Base32.
const BOX_BARCODES = ['INB-7QK4M2X9DPHR5N', 'INB-3TB8VC6WY2GJQ0', 'INB-9NZ5FDS1XKR7MV']

/** Содержимое короба: пары «номер товара в составе документа → количество». */
type BoxFill = [productIndex: number, quantity: number]

function buildBox(boxNumber: number, fills: BoxFill[]) {
  const filled = fills.length > 0
  return {
    id: `box-${boxNumber}`,
    box_number: boxNumber,
    internal_barcode: BOX_BARCODES[boxNumber - 1],
    label_printed_at: '2026-09-03T08:12:00Z',
    intake_opened_at: '2026-09-03T08:10:00Z',
    intake_closed_at: filled ? '2026-09-03T08:41:00Z' : null,
    is_open: !filled,
    remaining_qty: 0,
    lines: fills.map(([productIndex, quantity], lineIndex) => ({
      id: `box-${boxNumber}-ln-${lineIndex + 1}`,
      product_id: LINE_SPECS[productIndex].product.id,
      sku_code: LINE_SPECS[productIndex].product.sku,
      product_name: LINE_SPECS[productIndex].product.name,
      quantity,
      posted_qty: 0,
      remaining_qty: quantity,
    })),
  }
}

function buildCargoPlace(placeNumber: number) {
  return {
    id: `cargo-${placeNumber}`,
    place_number: placeNumber,
    internal_barcode: `${CARGO_BARCODE_PREFIX}-${String(placeNumber).padStart(4, '0')}`,
    label_printed_at: placeNumber === 1 ? '2026-09-03T08:15:00Z' : null,
    created_at: '2026-09-03T08:14:00Z',
    lines: [],
  }
}

type DetailPatch = {
  status: string
  lines: ReturnType<typeof buildLines>
  boxes: ReturnType<typeof buildBox>[]
  cargoPlaces: ReturnType<typeof buildCargoPlace>[]
}

function buildDetail(patch: DetailPatch) {
  return {
    id: REQUEST_ID,
    document_number: 'ПРИЕМ-26-09-02-43',
    display_number: '№000043',
    public_number: null,
    human_number: null,
    waybill_number: 'ТТН-4517',
    warehouse_id: WAREHOUSE.id,
    status: patch.status,
    operation_type: 'inbound',
    marketplace: 'wildberries',
    marketplace_warning: null,
    planned_delivery_date: '2026-09-02',
    planned_box_count: 3,
    actual_box_count: patch.boxes.length,
    boxes_discrepancy: false,
    has_discrepancy: false,
    seller_id: SELLER.id,
    seller_name: SELLER.name,
    // Черновик завели на складе, а не в кабинете селлера: у документа селлера
    // кнопка «Начать приёмку» намеренно спрятана, и шаг 1 статьи было бы нечем
    // проиллюстрировать.
    created_by_seller_id: null,
    created_at: '2026-09-02T15:20:00Z',
    distribution_completed_at: null,
    boxes: patch.boxes,
    cargo_places: patch.cargoPlaces,
    lines: patch.lines,
  }
}

/**
 * Таблица адресов, которые экран документа дёргает при загрузке. Всё
 * остальное `installStubFetch` отдаёт пустым успешным ответом — этого хватает,
 * потому что остальные ручки экрана срабатывают только на действия оператора.
 */
function buildRoutes(detail: unknown): StubRoute[] {
  return [
    {
      path: /^\/operations\/inbound-intake-requests\/[^/?]+$/,
      handler: () => detail,
    },
    {
      path: /^\/operations\/inbound-intake-requests\/[^/?]+\/distribution-lines$/,
      handler: () => [],
    },
    { path: /^\/operations\/discrepancy-acts$/, handler: () => [] },
    { path: /^\/products\/linked-wb-catalog/, handler: () => CATALOG },
    { path: /^\/warehouses$/, handler: () => [WAREHOUSE] },
    { path: /^\/warehouses\/[^/?]+\/locations/, handler: () => LOCATIONS },
  ]
}

/**
 * Доигровка сцены после первого рендера.
 *
 * Возвращает `true`, когда экран пришёл в нужное состояние и дальше дёргать
 * его не надо. Блок коробов и окно наполнения живут во внутреннем состоянии
 * `FfInboundRequestView`, снаружи их не выставить — поэтому макет доводит экран
 * до нужного шага ровно так же, как оператор: нажимает настоящие кнопки, как
 * только они появились в разметке.
 */
type Autoplay = () => boolean

/** Раскрывает блок «Короба и грузоместа». */
function expandPackages(): boolean {
  const toggle = document.querySelector<HTMLElement>('[data-testid="ff-inbound-packages-toggle"]')
  if (!toggle) {
    return false
  }
  if (toggle.getAttribute('aria-expanded') === 'true') {
    return true
  }
  toggle.click()
  return false
}

/** Раскрывает блок коробов и открывает окно «Наполнить короб» у первого короба. */
function openFirstBoxFillDialog(): boolean {
  const table = document.querySelector<HTMLElement>('[data-testid="ff-inbound-box-add-table"]')
  if (table) {
    // Окно наполнения упирается в свои 960 px, а таблица товаров просит около
    // 1006 px, поэтому колонка «В коробе» уезжает за правый край на любом
    // мониторе — её доскручивают руками. Макет доскручивает сам: иначе на
    // картинке в статье не видно того самого поля, куда вписывают количество.
    const scroller = table.parentElement
    if (!scroller || scroller.scrollWidth <= scroller.clientWidth) {
      return true
    }
    scroller.scrollLeft = scroller.scrollWidth
    return scroller.scrollLeft > 0
  }
  if (!expandPackages()) {
    return false
  }
  const fillButton = document.querySelector<HTMLButtonElement>(
    '[data-testid^="ff-inbound-box-fill-"]',
  )
  if (!fillButton || fillButton.disabled) {
    return false
  }
  fillButton.click()
  return false
}

type SceneProps = {
  detail: unknown
  autoplay?: Autoplay
}

function InboundDocScene({ detail, autoplay }: SceneProps) {
  const [ready, setReady] = useState(false)

  useLayoutEffect(() => {
    // Подмена обязана встать до первого рендера экрана. Иначе он успевает уйти
    // на настоящий бэкенд, получить 401 и показать «Не удалось загрузить
    // заявку» вместо документа.
    const restore = installStubFetch(buildRoutes(detail))
    setReady(true)
    return restore
  }, [detail])

  useEffect(() => {
    if (!ready || !autoplay) {
      return
    }
    if (autoplay()) {
      return
    }
    const timer = window.setInterval(() => {
      if (autoplay()) {
        window.clearInterval(timer)
      }
    }, 60)
    return () => window.clearInterval(timer)
  }, [ready, autoplay])

  if (!ready) {
    return null
  }

  return (
    <SceneShell route="/app/ff/reception">
      <FfInboundRequestView
        token="demo"
        requestId={REQUEST_ID}
        isFulfillmentAdmin
        workspace="reception"
        onClose={() => {}}
      />
    </SceneShell>
  )
}

// ——— Шаг 1: черновик с набранным составом ———————————————————————————————

const DRAFT_DETAIL = buildDetail({
  status: 'draft',
  // У черновика факта ещё нет: бэкенд отдаёт `effective_actual_qty` только на
  // приёмке, поэтому в колонке «Принято» честно стоят нули и подписи недостачи.
  lines: buildLines(LINE_SPECS.map(() => ({ looseQty: null, effectiveQty: null }))),
  boxes: [],
  cargoPlaces: [],
})

export function PriemkaDraftScene() {
  return <InboundDocScene detail={DRAFT_DETAIL} />
}

// ——— Шаг 2: короба и грузоместа, товар принят частично ————————————————————

const RECEIVING_BOXES = [
  buildBox(1, [
    [0, 30],
    [1, 10],
  ]),
  buildBox(2, [
    [1, 14],
    [2, 6],
  ]),
  // Третий короб только что создали и ещё не наполнили — на картинке видно, как
  // выглядит пустой короб и что кнопка «Удалить» у него доступна.
  buildBox(3, []),
]

const RECEIVING_CARGO_PLACES = [buildCargoPlace(1), buildCargoPlace(2)]

// Итог по строке = россыпь + то, что уже разложено по коробам. Кроссовки
// пересчитали руками (8 шт. россыпью), носки ещё не трогали.
const RECEIVING_DETAIL = buildDetail({
  status: 'receiving',
  lines: buildLines([
    { looseQty: 0, effectiveQty: 30 },
    { looseQty: 0, effectiveQty: 24 },
    { looseQty: 0, effectiveQty: 6 },
    { looseQty: 8, effectiveQty: 8 },
    { looseQty: null, effectiveQty: 0 },
  ]),
  boxes: RECEIVING_BOXES,
  cargoPlaces: RECEIVING_CARGO_PLACES,
})

export function PriemkaBoxesScene() {
  const autoplay = useCallback<Autoplay>(() => expandPackages(), [])
  return <InboundDocScene detail={RECEIVING_DETAIL} autoplay={autoplay} />
}

// ——— Шаг 3: то же состояние, но открыто окно «Наполнить короб» ——————————————

export function PriemkaBoxFillScene() {
  const autoplay = useCallback<Autoplay>(() => openFirstBoxFillDialog(), [])
  return <InboundDocScene detail={RECEIVING_DETAIL} autoplay={autoplay} />
}

// ——— Шаг 4: весь товар посчитан, видны расхождения по строкам ————————————

const DONE_BOXES = [
  buildBox(1, [
    [0, 30],
    [1, 10],
  ]),
  buildBox(2, [
    [1, 14],
    [2, 13],
  ]),
  buildBox(3, [
    [3, 22],
    [4, 20],
  ]),
]

// Весь товар уложен по коробам, россыпи не осталось. По двум строкам факт не
// сошёлся с планом: худи недосчитались, кроссовок пришло больше — ровно тот
// случай, ради которого перед завершением просят сверить документ.
const FINISHED_DETAIL = buildDetail({
  status: 'receiving',
  lines: buildLines([
    { looseQty: 0, effectiveQty: 30 },
    { looseQty: 0, effectiveQty: 24 },
    { looseQty: 0, effectiveQty: 13 },
    { looseQty: 0, effectiveQty: 22 },
    { looseQty: 0, effectiveQty: 20 },
  ]),
  boxes: DONE_BOXES,
  cargoPlaces: RECEIVING_CARGO_PLACES,
})

export function PriemkaDoneScene() {
  return <InboundDocScene detail={FINISHED_DETAIL} />
}
