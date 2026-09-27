// Макет PSP-2: выдуманные, но согласованные данные.
//
// Все экраны макета смотрят в одно состояние в памяти: каталог ФФ, карточка
// товара, каталог селлера, «Расчёты», инвентаризация. Действие в одном месте
// (добавить к фулфилменту, сохранить реквизиты, задать остаток, выставить счёт)
// видно в другом. Ни одной настоящей записи здесь нет.

import { productPhoto, type PhotoKind } from './photos'

// ── Детерминированный генератор: макет каждый раз открывается одинаковым ──
function mulberry32(seed: number) {
  let a = seed >>> 0
  return () => {
    a = (a + 0x6d2b79f5) >>> 0
    let t = a
    t = Math.imul(t ^ (t >>> 15), t | 1)
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61)
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296
  }
}

const rnd = mulberry32(270926)
const randInt = (min: number, max: number) => min + Math.floor(rnd() * (max - min + 1))
function pick<T>(items: T[]): T {
  return items[Math.floor(rnd() * items.length)]!
}

export function ean13(base12: string): string {
  let sum = 0
  for (let i = 0; i < 12; i += 1) {
    const digit = Number(base12[i])
    sum += i % 2 === 0 ? digit : digit * 3
  }
  return `${base12}${(10 - (sum % 10)) % 10}`
}

let eanSeq = 0
function nextEan(prefix = '4607188'): string {
  eanSeq += 1
  const body = `${prefix}${String(31740 + eanSeq * 37).padStart(12 - prefix.length, '0')}`.slice(0, 12)
  return ean13(body)
}

const uid = (() => {
  let n = 0
  return (prefix: string) => {
    n += 1
    return `${prefix}-${(0x3a91c + n * 7919).toString(16)}-${n.toString(16).padStart(4, '0')}`
  }
})()

export const NOW = new Date()
export const DAY = 24 * 60 * 60 * 1000

/** Дата N дней назад в заданный час по Москве (UTC+3). */
export function daysAgo(days: number, hour = 11, minute = 0): Date {
  const d = new Date(NOW.getTime() - days * DAY)
  d.setUTCHours(hour - 3, minute, randInt(0, 59), 0)
  if (d.getTime() > NOW.getTime()) return new Date(NOW.getTime() - randInt(5, 90) * 60 * 1000)
  return d
}

export function moscowDateKey(d: Date): string {
  const msk = new Date(d.getTime() + 3 * 60 * 60 * 1000)
  return msk.toISOString().slice(0, 10)
}

// ── Склад и организация ─────────────────────────────────────────────────────
export const WAREHOUSE = { id: 'wh-podolsk', name: 'Подольск', code: 'POD', is_operational: true }
export const ORG_NAME = 'Склад-24'

// ── Селлеры ────────────────────────────────────────────────────────────────
export type Profile = {
  legal_name: string
  inn: string
  kpp: string | null
  bank_name: string | null
  bik: string | null
  settlement_account: string | null
  correspondent_account: string | null
}

export type SellerFx = {
  id: string
  name: string
  wb_has_key: boolean
  wb_marketplace_scope_ok: boolean | null
  wb_marketplace_scope_checked_at: string | null
  ozon_connected: boolean
  profile: Profile | null
  /** Что площадки отдают на «Заполнить из WB / из Ozon». */
  marketplaceRequisites: { wb?: { inn: string; legal_name: string; kpp: string | null }; ozon?: { inn: string; legal_name: string; kpp: string | null } }
}

export const SELLER_TH = 'seller-textile-home'
export const SELLER_KR = 'seller-kravtsova'
export const SELLER_NK = 'seller-nord-knit'

export const FF_PROFILE: Profile = {
  legal_name: 'ООО «Склад-24»',
  inn: '5036172941',
  kpp: '503601001',
  bank_name: 'АО «Альфа-Банк»',
  bik: '044525593',
  settlement_account: '40702810702450018342',
  correspondent_account: '30101810200000000593',
}

export const sellers: SellerFx[] = [
  {
    id: SELLER_TH,
    name: 'ООО «Текстиль Хоум»',
    wb_has_key: true,
    wb_marketplace_scope_ok: true,
    wb_marketplace_scope_checked_at: daysAgo(0, 9, 12).toISOString(),
    ozon_connected: true,
    profile: {
      legal_name: 'ООО «Текстиль Хоум»',
      inn: '3702184456',
      kpp: '370201001',
      bank_name: 'ПАО Сбербанк',
      bik: '044525225',
      settlement_account: '40702810938000123456',
      correspondent_account: '30101810400000000225',
    },
    marketplaceRequisites: {
      wb: { inn: '3702184456', legal_name: 'ООО «Текстиль Хоум»', kpp: '370201001' },
      ozon: { inn: '3702184456', legal_name: 'ООО «Текстиль Хоум»', kpp: '370201001' },
    },
  },
  {
    id: SELLER_NK,
    name: 'ООО «Северный Трикотаж»',
    wb_has_key: true,
    wb_marketplace_scope_ok: false,
    wb_marketplace_scope_checked_at: daysAgo(1, 18, 40).toISOString(),
    ozon_connected: false,
    // Реквизиты ещё не заполнены — на этом селлере видно «Заполнить из WB».
    profile: null,
    marketplaceRequisites: {
      wb: { inn: '7814652093', legal_name: 'ООО «Северный Трикотаж»', kpp: '781401001' },
    },
  },
  {
    id: SELLER_KR,
    name: 'ИП Кравцова А. В.',
    // Ключ WB селлер ещё не вводил: введёт в своём кабинете, и откроется окно выбора товаров.
    wb_has_key: false,
    wb_marketplace_scope_ok: null,
    wb_marketplace_scope_checked_at: null,
    ozon_connected: true,
    profile: {
      legal_name: 'ИП Кравцова Анна Викторовна',
      inn: '503214789652',
      kpp: null,
      bank_name: 'АО «Тинькофф Банк»',
      bik: '044525974',
      settlement_account: '40802810100001234567',
      correspondent_account: '30101810145250000974',
    },
    marketplaceRequisites: {
      ozon: { inn: '503214789652', legal_name: 'ИП Кравцова Анна Викторовна', kpp: null },
    },
  },
]

export function sellerById(id: string | null | undefined): SellerFx | undefined {
  return sellers.find((s) => s.id === id)
}

// ── Товары на фулфилменте ────────────────────────────────────────────────────
export type ProductFx = {
  id: string
  seller_id: string
  name: string
  sku_code: string
  wb_nm_id: number | null
  wb_vendor_code: string | null
  ozon_sku: string | null
  ozon_offer_id: string | null
  ozon_product_id: string | null
  ozon_barcodes: string[]
  wb_subject_name: string | null
  photo: string
  wb_barcodes: string[]
  wb_size: string | null
  wb_color: string | null
  wb_brand: string | null
  wb_composition: string | null
  packaging_instructions: string | null
  country: string | null
  requires_honest_sign: boolean
  length_mm: number | null
  width_mm: number | null
  height_mm: number | null
  weight_g: number | null
  quantity: number
  reserved: number
  fbs: { enabled: boolean; mode: 'percent' | 'units'; value: number }
  /** Правила по отдельным складам площадок (окно «Остаток для FBS»); без записи — общее правило. */
  fbsByBinding: Record<string, { enabled: boolean; mode: 'percent' | 'units'; value: number }>
  /** Сколько раз двигался товар: у «главного» товара больше 200 (догрузка «Загрузить ещё»). */
  movementCount: number
}

type Variant = { size: string; code: string; qty?: number; reserved?: number }

type ProductGroup = {
  seller: string
  name: string
  nm: number | null
  vendor: string
  category: string
  color: string
  colorName: string
  brand: string
  composition: string
  photo: PhotoKind
  variants: Variant[]
  dims: [number, number, number, number]
  honestSign?: boolean
  instructions?: string
  ozon?: Record<string, { offer: string; sku: string; productId: string }>
  ozonOnly?: { offer: string; sku: string; productId: string }
  fbsPercent?: number
  movements?: Record<string, number>
}

const GROUPS: ProductGroup[] = [
  {
    seller: SELLER_TH,
    name: 'Комплект постельного белья «Лаванда», сатин',
    nm: 214563871,
    vendor: 'TH-LAV-SAT',
    category: 'Комплекты постельного белья',
    color: '#B7A6D6',
    colorName: 'лавандовый',
    brand: 'Textile Home',
    composition: 'Сатин, 100% хлопок',
    photo: 'bedding',
    dims: [400, 300, 90, 1850],
    instructions: 'Упаковать в фирменный пакет с ручкой. Вложить открытку «Спасибо за покупку». Стикер WB — на пакет, не на коробку.',
    variants: [
      { size: '1,5-спальный', code: '15', qty: 88, reserved: 4 },
      { size: '2-спальный', code: '2SP', qty: 64, reserved: 6 },
      { size: 'Евро', code: 'EVRO', qty: 146, reserved: 12 },
      { size: 'Семейный', code: 'FAM', qty: 23, reserved: 0 },
    ],
    ozon: {
      EVRO: { offer: 'TH-LAV-SAT-EVRO', sku: '1587342190', productId: '872145331' },
      '2SP': { offer: 'TH-LAV-SAT-2SP', sku: '1587342214', productId: '872145368' },
    },
    fbsPercent: 100,
    movements: { EVRO: 236 },
  },
  {
    seller: SELLER_TH,
    name: 'Комплект постельного белья «Графит», поплин',
    nm: 214563902,
    vendor: 'TH-GRF-POP',
    category: 'Комплекты постельного белья',
    color: '#5B5F66',
    colorName: 'графит',
    brand: 'Textile Home',
    composition: 'Поплин, 100% хлопок',
    photo: 'bedding',
    dims: [390, 290, 85, 1700],
    variants: [
      { size: '1,5-спальный', code: '15', qty: 41, reserved: 2 },
      { size: '2-спальный', code: '2SP', qty: 57, reserved: 0 },
      { size: 'Евро', code: 'EVRO', qty: 0, reserved: 0 },
    ],
    fbsPercent: 80,
  },
  {
    seller: SELLER_TH,
    name: 'Комплект постельного белья детский «Облака», бязь',
    nm: 214564017,
    vendor: 'TH-OBL-BZ',
    category: 'Комплекты постельного белья',
    color: '#A9CCE3',
    colorName: 'голубой',
    brand: 'Textile Home',
    composition: 'Бязь, 100% хлопок',
    photo: 'bedding',
    dims: [350, 270, 70, 1250],
    variants: [{ size: '1,5-спальный', code: '15', qty: 34, reserved: 3 }],
    fbsPercent: 100,
  },
  {
    seller: SELLER_TH,
    name: 'Простыня на резинке, сатин, белая',
    nm: 214564155,
    vendor: 'TH-PRS-REZ',
    category: 'Простыни',
    color: '#E9E4DC',
    colorName: 'белый',
    brand: 'Textile Home',
    composition: 'Сатин, 100% хлопок',
    photo: 'sheet',
    dims: [300, 220, 60, 720],
    variants: [
      { size: '160×200', code: '160', qty: 72, reserved: 0 },
      { size: '180×200', code: '180', qty: 49, reserved: 5 },
    ],
    fbsPercent: 50,
  },
  {
    seller: SELLER_TH,
    name: 'Наволочки сатин 70×70, 2 шт., молочные',
    nm: 214564203,
    vendor: 'TH-NAV-7070-ML',
    category: 'Наволочки',
    color: '#EFE3CF',
    colorName: 'молочный',
    brand: 'Textile Home',
    composition: 'Сатин, 100% хлопок',
    photo: 'pillowcase',
    dims: [250, 200, 40, 380],
    variants: [{ size: '70×70', code: '', qty: 118, reserved: 8 }],
    fbsPercent: 100,
  },
  {
    seller: SELLER_TH,
    name: 'Наволочки поплин 50×70, 2 шт., графит',
    nm: 214564288,
    vendor: 'TH-NAV-5070-GR',
    category: 'Наволочки',
    color: '#5B5F66',
    colorName: 'графит',
    brand: 'Textile Home',
    composition: 'Поплин, 100% хлопок',
    photo: 'pillowcase',
    dims: [250, 200, 40, 340],
    variants: [{ size: '50×70', code: '', qty: 93, reserved: 0 }],
    fbsPercent: 100,
  },
  {
    seller: SELLER_TH,
    name: 'Пододеяльник сатин 200×220, серый',
    nm: 214564310,
    vendor: 'TH-POD-200-GR',
    category: 'Пододеяльники',
    color: '#9EA3A8',
    colorName: 'серый',
    brand: 'Textile Home',
    composition: 'Сатин, 100% хлопок',
    photo: 'duvet',
    dims: [320, 260, 60, 980],
    variants: [{ size: '200×220', code: '', qty: 12, reserved: 0 }],
    fbsPercent: 100,
  },
  {
    seller: SELLER_NK,
    name: 'Футболка женская оверсайз, хлопок, чёрная',
    nm: 198342017,
    vendor: 'NK-TW-OVS-BLK',
    category: 'Футболки',
    color: '#2B2B2E',
    colorName: 'чёрный',
    brand: 'Nord Knit',
    composition: 'Хлопок 100%',
    photo: 'tshirt',
    dims: [300, 250, 30, 220],
    honestSign: true,
    instructions: 'Каждую футболку — в отдельный зип-пакет. КИЗ Честного знака клеить на пакет рядом со стикером WB.',
    variants: [
      { size: 'S', code: 'S', qty: 64, reserved: 3 },
      { size: 'M', code: 'M', qty: 132, reserved: 9 },
      { size: 'L', code: 'L', qty: 97, reserved: 4 },
      { size: 'XL', code: 'XL', qty: 38, reserved: 0 },
    ],
    fbsPercent: 100,
  },
  {
    seller: SELLER_NK,
    name: 'Футболка мужская базовая, хлопок, белая',
    nm: 198342154,
    vendor: 'NK-TM-BAS-WHT',
    category: 'Футболки',
    color: '#F7F7F4',
    colorName: 'белый',
    brand: 'Nord Knit',
    composition: 'Хлопок 100%',
    photo: 'tshirt',
    dims: [300, 250, 30, 210],
    honestSign: true,
    variants: [
      { size: 'M', code: 'M', qty: 77, reserved: 2 },
      { size: 'L', code: 'L', qty: 104, reserved: 6 },
      { size: 'XL', code: 'XL', qty: 55, reserved: 0 },
      { size: 'XXL', code: 'XXL', qty: 19, reserved: 0 },
    ],
    fbsPercent: 70,
  },
  {
    seller: SELLER_NK,
    name: 'Лонгслив унисекс, хлопок, серый меланж',
    nm: 198342233,
    vendor: 'NK-LS-UNI-MEL',
    category: 'Лонгсливы',
    color: '#A7A9AC',
    colorName: 'серый меланж',
    brand: 'Nord Knit',
    composition: 'Хлопок 95%, эластан 5%',
    photo: 'longsleeve',
    dims: [310, 260, 35, 290],
    honestSign: true,
    variants: [
      { size: 'M', code: 'M', qty: 46, reserved: 1 },
      { size: 'L', code: 'L', qty: 29, reserved: 0 },
    ],
    fbsPercent: 100,
  },
  {
    seller: SELLER_KR,
    name: 'Плед флисовый 150×200, графит',
    nm: null,
    vendor: 'KR-FL-150-GRF',
    category: 'Пледы',
    color: '#55595F',
    colorName: 'графит',
    brand: 'Kravtsova Home',
    composition: 'Флис, 100% полиэстер',
    photo: 'plaid',
    dims: [380, 300, 80, 820],
    variants: [{ size: '150×200', code: '', qty: 58, reserved: 2 }],
    ozonOnly: { offer: 'KR-FL-150-GRF', sku: '1602231178', productId: '884310552' },
  },
  {
    seller: SELLER_KR,
    name: 'Плед велсофт 200×220, пудровый',
    nm: null,
    vendor: 'KR-VS-200-PDR',
    category: 'Пледы',
    color: '#D9B8B2',
    colorName: 'пудровый',
    brand: 'Kravtsova Home',
    composition: 'Велсофт, 100% полиэстер',
    photo: 'plaid',
    dims: [400, 320, 90, 1100],
    variants: [{ size: '200×220', code: '', qty: 36, reserved: 0 }],
    ozonOnly: { offer: 'KR-VS-200-PDR', sku: '1602231266', productId: '884310617' },
  },
  {
    seller: SELLER_KR,
    name: 'Покрывало стёганое 220×240, бежевое',
    nm: null,
    vendor: 'KR-PK-220-BEG',
    category: 'Покрывала',
    color: '#D8C7A8',
    colorName: 'бежевый',
    brand: 'Kravtsova Home',
    composition: 'Микрофибра, наполнитель — синтепон',
    photo: 'bedspread',
    dims: [450, 350, 120, 2300],
    variants: [{ size: '220×240', code: '', qty: 21, reserved: 1 }],
    ozonOnly: { offer: 'KR-PK-220-BEG', sku: '1602231345', productId: '884310703' },
  },
]

export const products: ProductFx[] = []

function buildProducts() {
  for (const group of GROUPS) {
    for (const variant of group.variants) {
      // Как на сервере (wb_card_enrichment.sku_code_for_wb_variant): у многоразмерной карточки SKU — «артикул/размер».
      const skuCode = group.variants.length > 1 ? `${group.vendor}/${variant.size.replace('/', '-')}` : group.vendor
      const ozonLink = group.ozon?.[variant.code] ?? group.ozonOnly
      const wbBarcode = nextEan()
      const barcodes = group.nm != null ? [wbBarcode] : []
      // Часть карточек WB держит второй ШК размера (перемаркировка) — видно, что ШК «все».
      if (group.nm != null && rnd() < 0.3) barcodes.push(nextEan('2040'))
      const ozonBarcodes = ozonLink ? [group.nm != null ? nextEan('4630') : wbBarcode, `OZN${ozonLink.sku}`] : []
      products.push({
        id: uid('prod'),
        seller_id: group.seller,
        name: group.name,
        sku_code: skuCode,
        wb_nm_id: group.nm,
        wb_vendor_code: group.nm != null ? group.vendor : null,
        ozon_sku: ozonLink?.sku ?? null,
        ozon_offer_id: ozonLink?.offer ?? null,
        ozon_product_id: ozonLink?.productId ?? null,
        ozon_barcodes: ozonBarcodes,
        wb_subject_name: group.category,
        photo: productPhoto(group.photo, group.color),
        wb_barcodes: group.nm != null ? barcodes : [ozonBarcodes[0]!],
        wb_size: variant.size,
        wb_color: group.colorName,
        wb_brand: group.brand,
        wb_composition: group.composition,
        packaging_instructions: group.instructions ?? null,
        country: 'RU',
        requires_honest_sign: Boolean(group.honestSign),
        length_mm: group.dims[0],
        width_mm: group.dims[1],
        height_mm: group.dims[2],
        weight_g: group.dims[3],
        quantity: variant.qty ?? randInt(10, 120),
        reserved: variant.reserved ?? 0,
        fbs: { enabled: group.fbsPercent != null, mode: 'percent', value: group.fbsPercent ?? 100 },
        fbsByBinding: {},
        movementCount: group.movements?.[variant.code] ?? randInt(14, 42),
      })
    }
  }
}
buildProducts()

/** «Главный» товар макета: объединён с Ozon, больше 200 движений. */
export const HERO_PRODUCT_ID = products.find((p) => p.wb_vendor_code === 'TH-LAV-SAT' && p.wb_size === 'Евро')!.id

export function productById(id: string): ProductFx | undefined {
  return products.find((p) => p.id === id)
}

export function productAvailable(p: ProductFx): number {
  return p.quantity - p.reserved
}

export function productMarketplaces(p: ProductFx): string[] {
  const result: string[] = []
  if (p.wb_nm_id != null) result.push('wb')
  if (p.ozon_sku || p.ozon_offer_id) result.push('ozon')
  return result
}

/** Публикуемый остаток FBS: min(лимит оператора, свободный остаток). */
export function fbsPublished(p: ProductFx, rule: ProductFx['fbs'] = p.fbs): number {
  const free = Math.max(0, productAvailable(p))
  if (!rule.enabled) return 0
  if (rule.mode === 'units') return Math.min(rule.value, free)
  return Math.floor((free * rule.value) / 100)
}

// ── Документы, из которых складываются движения ───────────────────────────
type DocRef = { id: string; number: string; at: Date }

function docPool(count: number, prefix: string, startNumber: number, spanDays: number): DocRef[] {
  const docs: DocRef[] = []
  for (let i = 0; i < count; i += 1) {
    const age = Math.round((spanDays * (count - i)) / count)
    docs.push({ id: uid(prefix), number: `№${String(startNumber + i).padStart(6, '0')}`, at: daysAgo(age, randInt(9, 17), randInt(0, 59)) })
  }
  return docs
}

export const intakeDocs = docPool(34, 'inb', 118, 200)
export const returnDocs = docPool(8, 'ret', 160, 150)
export const unloadDocs = docPool(26, 'mpu', 412, 180)
export const fbsSupplies = Array.from({ length: 30 }, (_, i) => ({
  id: uid('sup'),
  number: `WB-GI-${String(18724311 + i * 137)}`,
}))

export type InventoryCountFx = {
  id: string
  number: string
  status: 'draft' | 'posted' | 'cancelled'
  created_at: string
  created_by: string
  posted_at: string | null
  posted_by: string | null
  fill: { mode: 'all' | 'filters' | 'object'; seller_id: string | null; category: string | null; object_label: string | null }
  comment: string
  /** Факт по строкам (id строки = id товара в ячейке). */
  actual: Record<string, number | null>
}

function invNumber(id: string): string {
  return `ИНВ-${id.replace(/[^0-9a-f]/gi, '').slice(0, 8).toUpperCase()}`
}

export const OBJECT_COUNT_CELL = 'Б 2.1'

const invDraftId = '7c2e91a4-5d1f-4b8e-9a0c-2f6d3e1b7a55'
const invPostedId = '51b0d3f2-9e4a-4c7d-8b21-6a0e9f3c2d18'
const invObjectId = 'a94e0c17-3b6d-4f28-9c55-1d7e8a2b4f60'

export const inventoryCounts: InventoryCountFx[] = [
  {
    id: invDraftId,
    number: invNumber(invDraftId),
    status: 'draft',
    created_at: daysAgo(0, 9, 5).toISOString(),
    created_by: 'Ольга Смирнова',
    posted_at: null,
    posted_by: null,
    fill: { mode: 'filters', seller_id: SELLER_TH, category: 'Комплекты постельного белья', object_label: null },
    comment: '',
    actual: {},
  },
  {
    id: invPostedId,
    number: invNumber(invPostedId),
    status: 'posted',
    created_at: daysAgo(12, 10, 20).toISOString(),
    created_by: 'Дмитрий Орлов',
    posted_at: daysAgo(12, 16, 45).toISOString(),
    posted_by: 'Дмитрий Орлов',
    fill: { mode: 'filters', seller_id: SELLER_NK, category: null, object_label: null },
    comment: 'Плановый пересчёт трикотажа',
    actual: {},
  },
  {
    id: invObjectId,
    number: invNumber(invObjectId),
    status: 'posted',
    created_at: daysAgo(31, 14, 2).toISOString(),
    created_by: 'Ольга Смирнова',
    posted_at: daysAgo(31, 15, 30).toISOString(),
    posted_by: 'Ольга Смирнова',
    fill: { mode: 'object', seller_id: null, category: null, object_label: `Ячейка ${OBJECT_COUNT_CELL}` },
    comment: '',
    actual: {},
  },
]

// ── Движения ────────────────────────────────────────────────────────────────
export type MovementDocument = { kind: string; id: string; number: string } | null
export type MovementRowFx = {
  id: string
  at: string
  operation: string
  quantity: number
  product_id: string
  product_name: string
  sku_code: string
  document: MovementDocument
}

const movementCache = new Map<string, MovementRowFx[]>()

function fbsOrderNumber(p: ProductFx): string {
  if (!p.wb_nm_id && p.ozon_sku) return `Заказ Ozon №${randInt(10000000, 99999999)}-${String(randInt(1, 9999)).padStart(4, '0')}-1`
  return `Заказ WB №${randInt(4100000000, 4499999999)}`
}

/**
 * История движений товара, сходящаяся к его текущему остатку.
 * Перемещения между ячейками сюда не попадают: они меняют расположение, а не
 * остаток (сервер их тоже не отдаёт).
 */
export function productMovements(p: ProductFx): MovementRowFx[] {
  const cached = movementCache.get(p.id)
  if (cached) return cached
  const index = products.indexOf(p)
  const local = mulberry32(9173 + index * 7919)
  const lr = (min: number, max: number) => min + Math.floor(local() * (max - min + 1))
  const lpick = <T,>(items: T[]) => items[Math.floor(local() * items.length)]!
  type Draft = { at: Date; operation: string; quantity: number; document: MovementDocument }
  const drafts: Draft[] = []
  const total = p.movementCount
  const target = p.quantity
  const span = p.id === HERO_PRODUCT_ID ? 190 : 150
  const nowMs = NOW.getTime()
  const clampNow = (d: Date) => new Date(Math.min(d.getTime(), nowMs - 60 * 1000))
  // Приёмки и отгрузки встают на время своего документа: у товаров одной
  // приёмки одна и та же дата и один и тот же номер.
  const nearest = (pool: DocRef[], at: Date) =>
    pool.reduce((best, doc) => (Math.abs(doc.at.getTime() - at.getTime()) < Math.abs(best.at.getTime() - at.getTime()) ? doc : best), pool[0]!)
  const onDoc = (doc: DocRef) => clampNow(new Date(doc.at.getTime() + lr(10, 240) * 60 * 1000))
  const inventoryFor = inventoryCounts.filter((c) => c.status === 'posted' && countIncludes(c, p))
  const plannedInventory = inventoryFor.length
  let balance = 0
  // Первая приёмка — в начале истории.
  const firstIntake = nearest(intakeDocs, new Date(nowMs - span * DAY))
  const firstQty = Math.max(target + lr(20, 60), 30)
  drafts.push({ at: onDoc(firstIntake), operation: 'Приёмка', quantity: firstQty, document: { kind: 'inbound', id: firstIntake.id, number: firstIntake.number } })
  balance += firstQty
  const steps = Math.max(0, total - 2 - plannedInventory)
  for (let i = 1; i <= steps; i += 1) {
    const at = daysAgo(Math.max(0, Math.round(span - (span * i) / (steps + 1))), lr(9, 20), lr(0, 59))
    const excess = balance - target
    const roll = local()
    if (balance < Math.max(12, target * 0.4) || (excess < -25 && roll < 0.3)) {
      const doc = nearest(intakeDocs, at)
      const q = lr(25, 70)
      drafts.push({ at: onDoc(doc), operation: 'Приёмка', quantity: q, document: { kind: 'inbound', id: doc.id, number: doc.number } })
      balance += q
    } else if (excess > 30 && roll < 0.35) {
      const doc = nearest(unloadDocs, at)
      const q = Math.min(40, Math.max(6, excess - lr(0, 15)), balance - 2)
      drafts.push({ at: onDoc(doc), operation: 'Отгрузка на МП', quantity: -q, document: { kind: 'marketplace_unload', id: doc.id, number: doc.number } })
      balance -= q
    } else if (roll < 0.72) {
      drafts.push({ at, operation: 'FBS', quantity: -1, document: { kind: 'fbs_supply', id: lpick(fbsSupplies).id, number: fbsOrderNumber(p) } })
      balance -= 1
    } else if (roll < 0.8 && balance > 14) {
      const doc = nearest(unloadDocs, at)
      const q = lr(4, Math.min(24, balance - 6))
      drafts.push({ at: onDoc(doc), operation: 'Отгрузка на МП', quantity: -q, document: { kind: 'marketplace_unload', id: doc.id, number: doc.number } })
      balance -= q
    } else if (roll < 0.88) {
      const doc = nearest(intakeDocs, at)
      const q = lr(10, 40)
      drafts.push({ at: onDoc(doc), operation: 'Приёмка', quantity: q, document: { kind: 'inbound', id: doc.id, number: doc.number } })
      balance += q
    } else if (roll < 0.94) {
      const doc = nearest(returnDocs, at)
      drafts.push({ at: onDoc(doc), operation: 'Возврат', quantity: 1, document: { kind: 'inbound', id: doc.id, number: doc.number } })
      balance += 1
    } else if (roll < 0.97) {
      const doc = nearest(intakeDocs, at)
      const delta = balance > 2 ? lpick([-1, 1]) : 1
      drafts.push({ at: onDoc(doc), operation: 'Корректировка по акту расхождений', quantity: delta, document: { kind: 'inbound', id: doc.id, number: doc.number } })
      balance += delta
    } else if (balance > 3) {
      const q = lr(1, 3)
      drafts.push({ at, operation: 'Отгрузка', quantity: -q, document: { kind: 'outbound_shipment', id: uid('out'), number: 'без номера' } })
      balance -= q
    } else {
      drafts.push({ at, operation: 'FBS, сторно', quantity: 1, document: { kind: 'fbs_supply', id: lpick(fbsSupplies).id, number: fbsOrderNumber(p) } })
      balance += 1
    }
  }
  // Проведённые инвентаризации — ровно в момент проведения документа.
  for (const count of inventoryFor) {
    const delta = lpick([-1, 1, 2])
    drafts.push({ at: new Date(count.posted_at!), operation: 'Инвентаризация', quantity: delta, document: { kind: 'inventory_count', id: count.id, number: count.number } })
    balance += delta
  }
  // Сегодняшние заказы FBS: «Расчёты» по умолчанию открываются на «Сегодня».
  if (target > 5 && index % 3 !== 2) {
    const todayOrders = lr(1, 3)
    for (let k = 0; k < todayOrders; k += 1) {
      drafts.push({ at: new Date(nowMs - lr(20, 420) * 60 * 1000), operation: 'FBS', quantity: -1, document: { kind: 'fbs_supply', id: lpick(fbsSupplies).id, number: fbsOrderNumber(p) } })
      balance -= 1
    }
  }
  // Последнее движение сводит историю к текущему остатку.
  const diff = target - balance
  if (diff > 0) {
    const doc = intakeDocs[intakeDocs.length - 1]!
    drafts.push({ at: onDoc(doc), operation: 'Приёмка', quantity: diff, document: { kind: 'inbound', id: doc.id, number: doc.number } })
  } else if (diff < 0) {
    const doc = unloadDocs[unloadDocs.length - 1]!
    drafts.push({ at: onDoc(doc), operation: 'Отгрузка на МП', quantity: diff, document: { kind: 'marketplace_unload', id: doc.id, number: doc.number } })
  } else {
    drafts.push({ at: daysAgo(0, 10, lr(0, 50)), operation: 'FBS', quantity: -1, document: { kind: 'fbs_supply', id: fbsSupplies[0]!.id, number: fbsOrderNumber(p) } })
    const ret = returnDocs[returnDocs.length - 1]!
    drafts.push({ at: onDoc(ret), operation: 'Возврат', quantity: 1, document: { kind: 'inbound', id: ret.id, number: ret.number } })
  }
  // Даты привязаны к документам, поэтому порядок мог перемешаться: остаток не
  // должен уходить в минус ни в одной точке истории.
  drafts.sort((a, b) => a.at.getTime() - b.at.getTime())
  let running = 0
  let lowest = 0
  for (const d of drafts) {
    running += d.quantity
    lowest = Math.min(lowest, running)
  }
  if (lowest < 0) {
    const first = drafts.find((d) => d.operation === 'Приёмка')!
    first.quantity += -lowest
    for (let k = 0; k < -lowest; k += 1) {
      drafts.push({ at: new Date(nowMs - (k + 1) * lr(20, 45) * 60 * 1000), operation: 'FBS', quantity: -1, document: { kind: 'fbs_supply', id: fbsSupplies[k % fbsSupplies.length]!.id, number: fbsOrderNumber(p) } })
    }
  }
  const rows = drafts
    .sort((a, b) => b.at.getTime() - a.at.getTime())
    .map((d, n) => ({
      id: `${p.id}-mv-${n}`,
      at: d.at.toISOString(),
      operation: d.operation,
      quantity: d.quantity,
      product_id: p.id,
      product_name: p.name,
      sku_code: p.sku_code,
      document: d.document,
    }))
  movementCache.set(p.id, rows)
  return rows
}

/** Входит ли товар в документ инвентаризации (по отбору или по объекту). */
export function countIncludes(count: InventoryCountFx, p: ProductFx): boolean {
  if (count.fill.mode === 'object') return productPlacements(p).some((pl) => pl.cell === OBJECT_COUNT_CELL)
  if (count.fill.seller_id && p.seller_id !== count.fill.seller_id) return false
  if (count.fill.category && p.wb_subject_name !== count.fill.category) return false
  return p.quantity > 0
}

export function recordMovement(p: ProductFx, operation: string, quantity: number, document: MovementDocument) {
  const rows = productMovements(p)
  rows.unshift({
    id: `${p.id}-mv-live-${rows.length}`,
    at: new Date().toISOString(),
    operation,
    quantity,
    product_id: p.id,
    product_name: p.name,
    sku_code: p.sku_code,
    document,
  })
}

// ── Ячейки: где лежит товар (та же структура, что в «Ячейках») ────────────
export type PlacementFx = { cell: string; container: { kind: 'pallet' | 'box'; code: string } | null; qty: number }

const CELLS = ['А 1.1', 'А 1.2', 'А 1.3', 'А 2.1', 'А 2.2', 'Б 1.1', 'Б 1.2', 'Б 2.1', 'Б 2.2', 'В 1.1', 'В 1.2', 'В 3.1']
const placementCache = new Map<string, PlacementFx[]>()

export function productPlacements(p: ProductFx): PlacementFx[] {
  const cached = placementCache.get(p.id)
  if (cached) return cached
  const parts: PlacementFx[] = []
  let left = p.quantity
  const index = products.indexOf(p)
  let slot = 0
  while (left > 0) {
    const qty = slot >= 2 ? left : Math.min(left, Math.max(1, Math.round(left * (slot === 0 ? 0.6 : 0.7))))
    const cell = CELLS[(index * 3 + slot * 5) % CELLS.length]!
    const container =
      slot === 0 && qty > 40
        ? { kind: 'pallet' as const, code: `П-${String(2310 + index).padStart(5, '0')}` }
        : slot === 1
          ? { kind: 'box' as const, code: `WHB-${String(88120 + index * 3 + slot)}` }
          : null
    parts.push({ cell, container, qty })
    left -= qty
    slot += 1
  }
  placementCache.set(p.id, parts)
  return parts
}

// ── Каталог селлера: карточки площадок, ещё не на фулфилменте ─────────────
export type SellerCardFx = {
  marketplace: 'wildberries' | 'ozon'
  nm_id: number | null
  ozon_product_id: string | null
  vendor_code: string
  name: string
  photo_url: string
  barcodes: string[]
  sizes: string[]
  category: string
  color: string
  colorName: string
  photoKind: PhotoKind
  brand: string
  composition: string
  dims: [number, number, number, number]
}

function wbCard(nm: number, vendor: string, name: string, category: string, photoKind: PhotoKind, color: string, colorName: string, size: string, composition: string, dims: [number, number, number, number]): SellerCardFx {
  return {
    marketplace: 'wildberries',
    nm_id: nm,
    ozon_product_id: null,
    vendor_code: vendor,
    name,
    photo_url: productPhoto(photoKind, color),
    barcodes: [nextEan('4640')],
    sizes: [size],
    category,
    color,
    colorName,
    photoKind,
    brand: 'Kravtsova Home',
    composition,
    dims,
  }
}

function ozonCard(productId: string, vendor: string, name: string, category: string, photoKind: PhotoKind, color: string, colorName: string, size: string, composition: string, dims: [number, number, number, number]): SellerCardFx {
  return {
    marketplace: 'ozon',
    nm_id: null,
    ozon_product_id: productId,
    vendor_code: vendor,
    name,
    photo_url: productPhoto(photoKind, color),
    barcodes: [nextEan('4630')],
    sizes: [size],
    category,
    color,
    colorName,
    photoKind,
    brand: 'Kravtsova Home',
    composition,
    dims,
  }
}

const PLAID_COLORS: Array<[string, string, string]> = [
  ['#55595F', 'графит', 'GRF'],
  ['#2F6B5B', 'изумрудный', 'EMR'],
  ['#C9A27E', 'карамельный', 'CRM'],
  ['#8C4A5A', 'бордовый', 'BRD'],
  ['#3F5A7A', 'синий', 'BLU'],
  ['#D9B8B2', 'пудровый', 'PDR'],
]

export const sellerCards: SellerCardFx[] = []

function buildSellerCards() {
  let nm = 231907114
  const fleece = PLAID_COLORS.map(([hex, name, code]) =>
    wbCard(nm++, `KR-FL-150-${code}`, `Плед флисовый 150×200, ${name}`, 'Пледы', 'plaid', hex, name, '150×200', 'Флис, 100% полиэстер', [380, 300, 80, 820]),
  )
  const velsoft = PLAID_COLORS.slice(0, 5).map(([hex, name, code]) =>
    wbCard(nm++, `KR-VS-200-${code}`, `Плед велсофт 200×220, ${name}`, 'Пледы', 'plaid', hex, name, '200×220', 'Велсофт, 100% полиэстер', [400, 320, 90, 1100]),
  )
  const knitted = ([['#EFE6D8', 'молочный', 'MLK'], ['#B9B2A6', 'серо-бежевый', 'GBG'], ['#6E7B6A', 'оливковый', 'OLV'], ['#C98F7A', 'терракотовый', 'TER']] as Array<[string, string, string]>).map(([hex, name, code]) =>
    wbCard(nm++, `KR-VZ-130-${code}`, `Плед вязаный 130×170, ${name}`, 'Пледы', 'plaid', hex, name, '130×170', 'Акрил 70%, хлопок 30%', [350, 280, 90, 950]),
  )
  const kids = ([['#BFE3D0', 'мятный', 'MNT'], ['#F4D6A0', 'жёлтый', 'YLW'], ['#C8D8F0', 'голубой', 'BLU'], ['#F2C4CE', 'розовый', 'PNK']] as Array<[string, string, string]>).map(([hex, name, code]) =>
    wbCard(nm++, `KR-KD-100-${code}`, `Плед детский 100×140, ${name}`, 'Пледы', 'plaid', hex, name, '100×140', 'Велсофт, 100% полиэстер', [300, 250, 60, 480]),
  )
  const spreads = ([['#D8C7A8', 'бежевое', 'BEG'], ['#8E9AA6', 'серое', 'GRY'], ['#7A4E3A', 'шоколадное', 'CHC'], ['#EDE7DD', 'белое', 'WHT']] as Array<[string, string, string]>).map(([hex, name, code]) =>
    wbCard(nm++, `KR-PK-220-${code}`, `Покрывало стёганое 220×240, ${name}`, 'Покрывала', 'bedspread', hex, name, '220×240', 'Микрофибра, наполнитель — синтепон', [450, 350, 120, 2300]),
  )
  const cushions = PLAID_COLORS.map(([hex, name, code]) =>
    wbCard(nm++, `KR-PD-45-${code}`, `Подушка декоративная 45×45, бархат, ${name}`, 'Подушки декоративные', 'cushion', hex, name, '45×45', 'Велюр, наполнитель — холлофайбер', [460, 460, 150, 520]),
  )
  const cases = PLAID_COLORS.slice(0, 5).map(([hex, name, code]) =>
    wbCard(nm++, `KR-ND-45-${code}`, `Наволочка декоративная 45×45, бархат, ${name}`, 'Наволочки декоративные', 'pillowcase', hex, name, '45×45', 'Велюр, 100% полиэстер', [250, 200, 20, 140]),
  )
  const sleeves = ([['#8E9AA6', 'серый', 'GRY'], ['#3F5A7A', 'синий', 'BLU'], ['#C9A27E', 'карамельный', 'CRM']] as Array<[string, string, string]>).map(([hex, name, code]) =>
    wbCard(nm++, `KR-RK-${code}`, `Плед-накидка с рукавами, ${name}`, 'Пледы', 'plaid', hex, name, '150×180', 'Флис, 100% полиэстер', [380, 300, 80, 900]),
  )
  sellerCards.push(...fleece, ...velsoft, ...knitted, ...kids, ...spreads, ...cushions, ...cases, ...sleeves)
  let oz = 884311020
  sellerCards.push(
    ozonCard(String(oz++), 'KR-VZ-130-MLK', 'Плед вязаный 130×170, молочный', 'Пледы', 'plaid', '#EFE6D8', 'молочный', '130×170', 'Акрил 70%, хлопок 30%', [350, 280, 90, 950]),
    ozonCard(String(oz++), 'KR-FL-150-EMR', 'Плед флисовый 150×200, изумрудный', 'Пледы', 'plaid', '#2F6B5B', 'изумрудный', '150×200', 'Флис, 100% полиэстер', [380, 300, 80, 820]),
    ozonCard(String(oz++), 'KR-PK-240-GRY', 'Покрывало жаккард 240×260, серое', 'Покрывала', 'bedspread', '#8E9AA6', 'серое', '240×260', 'Жаккард, 100% хлопок', [460, 360, 130, 2600]),
    ozonCard(String(oz++), 'KR-RK-GRY', 'Плед-накидка с рукавами, серый', 'Пледы', 'plaid', '#8E9AA6', 'серый', '150×180', 'Флис, 100% полиэстер', [380, 300, 80, 900]),
    ozonCard(String(oz++), 'KR-KD-100-MNT', 'Плед детский 100×140, мятный', 'Пледы', 'plaid', '#BFE3D0', 'мятный', '100×140', 'Велсофт, 100% полиэстер', [300, 250, 60, 480]),
  )
}
buildSellerCards()

/** Ключ WB у селлера кабинета — снимок карточек WB появляется только после ввода ключа. */
export const sellerCabinet = {
  sellerId: SELLER_KR,
  wbKeyConnected: false,
}

export function cardOnFulfillment(card: SellerCardFx): ProductFx | undefined {
  if (card.marketplace === 'wildberries') return products.find((p) => p.seller_id === SELLER_KR && p.wb_nm_id === card.nm_id)
  return products.find((p) => p.seller_id === SELLER_KR && p.ozon_product_id === card.ozon_product_id)
}

/** Добавить карточку к фулфилменту: становится товаром ФФ без остатка. */
export function addCardToFulfillment(card: SellerCardFx): ProductFx {
  const existing = cardOnFulfillment(card)
  if (existing) return existing
  const isWb = card.marketplace === 'wildberries'
  const product: ProductFx = {
    id: uid('prod'),
    seller_id: SELLER_KR,
    name: card.name,
    sku_code: card.vendor_code,
    wb_nm_id: isWb ? card.nm_id : null,
    wb_vendor_code: isWb ? card.vendor_code : null,
    ozon_sku: isWb ? null : String(1602231400 + products.length),
    ozon_offer_id: isWb ? null : card.vendor_code,
    ozon_product_id: isWb ? null : card.ozon_product_id,
    ozon_barcodes: isWb ? [] : [card.barcodes[0]!],
    wb_subject_name: card.category,
    photo: card.photo_url,
    wb_barcodes: [...card.barcodes],
    wb_size: card.sizes[0] ?? null,
    wb_color: card.colorName,
    wb_brand: card.brand,
    wb_composition: card.composition,
    packaging_instructions: null,
    country: 'RU',
    requires_honest_sign: false,
    length_mm: card.dims[0],
    width_mm: card.dims[1],
    height_mm: card.dims[2],
    weight_g: card.dims[3],
    quantity: 0,
    reserved: 0,
    fbs: { enabled: false, mode: 'percent', value: 100 },
    fbsByBinding: {},
    movementCount: 0,
  }
  products.push(product)
  movementCache.set(product.id, [])
  placementCache.set(product.id, [])
  return product
}

// Селлер уже раньше добавил к фулфилменту три карточки Ozon.
for (const product of products.filter((p) => p.seller_id === SELLER_KR)) {
  sellerCards.push({
    marketplace: 'ozon',
    nm_id: null,
    ozon_product_id: product.ozon_product_id,
    vendor_code: product.sku_code,
    name: product.name,
    photo_url: product.photo,
    barcodes: [...product.wb_barcodes],
    sizes: product.wb_size ? [product.wb_size] : [],
    category: product.wb_subject_name ?? '',
    color: '#999999',
    colorName: product.wb_color ?? '',
    photoKind: 'plaid',
    brand: product.wb_brand ?? '',
    composition: product.wb_composition ?? '',
    dims: [product.length_mm ?? 0, product.width_mm ?? 0, product.height_mm ?? 0, product.weight_g ?? 0],
  })
}

// ── Счета ───────────────────────────────────────────────────────────────────
export type InvoiceLineFx = { id: string; description: string; total_amount_kopecks: number | null }
export type InvoiceFx = {
  id: string
  origin: 'legacy' | 'v2'
  number: string
  seller_id: string
  issued_at: string
  period_start: string | null
  period_end: string | null
  creation_mode: 'monthly' | 'manual' | 'selected_operations'
  status: 'issued' | 'cancelled'
  lines: InvoiceLineFx[]
  seller_profile: Profile | null
}

function invoiceNumber(at: Date, counter: number): string {
  const msk = new Date(at.getTime() + 3 * 60 * 60 * 1000)
  const yy = String(msk.getUTCFullYear() % 100).padStart(2, '0')
  const mm = String(msk.getUTCMonth() + 1).padStart(2, '0')
  const dd = String(msk.getUTCDate()).padStart(2, '0')
  return `СЧЕТ-${yy}-${mm}-${dd}-${counter}`
}

export let invoiceCounter = 17
export function nextInvoiceNumber(at: Date): string {
  invoiceCounter += 1
  return invoiceNumber(at, invoiceCounter)
}

function periodOf(startAgo: number, endAgo: number): { start: string; end: string } {
  return { start: moscowDateKey(daysAgo(startAgo)), end: moscowDateKey(daysAgo(endAgo)) }
}

export const invoices: InvoiceFx[] = []

function buildInvoices() {
  const th = sellerById(SELLER_TH)!
  const nk = sellerById(SELLER_NK)!
  const kr = sellerById(SELLER_KR)!
  const prevMonth = new Date(Date.UTC(NOW.getUTCFullYear(), NOW.getUTCMonth() - 1, 1))
  const prevMonthEnd = new Date(Date.UTC(NOW.getUTCFullYear(), NOW.getUTCMonth(), 0))
  const add = (seller: SellerFx, issuedAgo: number, period: { start: string; end: string } | null, mode: InvoiceFx['creation_mode'], lines: Array<[string, number]>, status: InvoiceFx['status'] = 'issued', origin: InvoiceFx['origin'] = 'v2') => {
    const at = daysAgo(issuedAgo, 12, randInt(0, 59))
    invoices.push({
      id: uid('inv'),
      origin,
      number: invoiceNumber(at, 3 + invoices.length),
      seller_id: seller.id,
      issued_at: at.toISOString(),
      period_start: period?.start ?? null,
      period_end: period?.end ?? null,
      creation_mode: mode,
      status,
      lines: lines.map(([description, amount]) => ({ id: uid('line'), description, total_amount_kopecks: amount })),
      seller_profile: seller.profile,
    })
  }
  add(th, 38, { start: prevMonth.toISOString().slice(0, 10), end: prevMonthEnd.toISOString().slice(0, 10) }, 'monthly', [['Приёмка', 1860000], ['Отгрузка', 942000], ['Хранение', 318450]], 'issued', 'legacy')
  add(th, 21, periodOf(35, 22), 'selected_operations', [['Приёмка — 412 шт.', 618000], ['Упаковка — 380 шт.', 456000], ['FBS — 214 заказов', 963000], ['Хранение', 204330]])
  add(th, 9, periodOf(21, 10), 'selected_operations', [['Приёмка — 265 шт.', 397500], ['FBS — 188 заказов', 846000], ['Отгрузка — 140 шт.', 280000]])
  add(th, 4, null, 'manual', [['Переупаковка возвратов', 450000]], 'cancelled')
  add(nk, 17, periodOf(30, 18), 'selected_operations', [['Приёмка — 520 шт.', 780000], ['Упаковка — 498 шт.', 597600], ['FBS — 305 заказов', 1372500]])
  add(nk, 6, periodOf(17, 7), 'selected_operations', [['FBS — 146 заказов', 657000], ['Хранение', 96420]])
  add(kr, 11, periodOf(40, 12), 'selected_operations', [['Приёмка — 140 шт.', 210000], ['FBS — 36 заказов', 162000], ['Хранение', 58100]])
}
buildInvoices()

export function invoiceTotal(inv: InvoiceFx): number {
  return inv.lines.reduce((sum, line) => sum + (line.total_amount_kopecks ?? 0), 0)
}

// ── Ставки (единые для всех селлеров ФФ, копейки) ───────────────────────────
export const RATES = {
  inbound: { rate: 1500, unit: 'item' },
  packing: { rate: 1200, unit: 'item' },
  fbs_order: { rate: 4500, unit: 'document' },
  marketplace_outbound: { rate: 2000, unit: 'item' },
  storage: { rate: 30, unit: 'liter_day' },
} as const

export const SERVICE_TITLES: Record<string, string> = {
  inbound: 'Приёмка',
  packing: 'Упаковка',
  fbs_order: 'FBS',
  marketplace_outbound: 'Отгрузка',
  storage: 'Хранение',
}

export function productVolumeLiters(p: ProductFx): number {
  if (!p.length_mm || !p.width_mm || !p.height_mm) return 0
  return (p.length_mm * p.width_mm * p.height_mm) / 1_000_000
}

export { pick, randInt }
