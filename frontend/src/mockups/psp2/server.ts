// Макет PSP-2: подставной сервер. Отвечает на запросы настоящих экранов
// фикстурами из fixtures.ts и меняет их в памяти, когда экран что-то сохраняет.
//
// Кабинет (фулфилмент или селлер) определяется по токену в заголовке
// Authorization — так же, как настоящий сервер различает пользователей.

import {
  DAY,
  FF_PROFILE,
  HERO_PRODUCT_ID,
  NOW,
  ORG_NAME,
  RATES,
  SELLER_KR,
  SERVICE_TITLES,
  WAREHOUSE,
  addCardToFulfillment,
  cardOnFulfillment,
  countIncludes,
  OBJECT_COUNT_CELL,
  fbsPublished,
  fbsSupplies,
  intakeDocs,
  inventoryCounts,
  invoiceTotal,
  invoices,
  moscowDateKey,
  nextInvoiceNumber,
  productAvailable,
  productById,
  productMarketplaces,
  productMovements,
  productPlacements,
  productVolumeLiters,
  products,
  sellerById,
  sellerCabinet,
  sellerCards,
  sellers,
  unloadDocs,
  type InventoryCountFx,
  type InvoiceFx,
  type ProductFx,
  type Profile,
  type SellerCardFx,
} from './fixtures'

export const FF_TOKEN = 'psp2-mockup-ff'
export const SELLER_TOKEN = 'psp2-mockup-seller'

type Cabinet = 'ff' | 'seller'

type Ctx = {
  method: string
  path: string
  query: URLSearchParams
  body: unknown
  cabinet: Cabinet
  match: RegExpMatchArray
}

type Handler = (ctx: Ctx) => unknown

type Route = { method: string; path: RegExp; handler: Handler }

class HttpReply {
  status: number
  body: unknown
  constructor(status: number, body: unknown) {
    this.status = status
    this.body = body
  }
}

const reply = (status: number, body: unknown) => new HttpReply(status, body)

// ── Пользователи ────────────────────────────────────────────────────────────
function ffMe() {
  return {
    id: 'user-ff-olga',
    email: 'olga.smirnova@sklad24.ru',
    full_name: 'Ольга Смирнова',
    job_title: 'Руководитель склада',
    display_name: 'Ольга Смирнова',
    organization_name: ORG_NAME,
    organization_slug: 'sklad24',
    role: 'fulfillment_admin',
    permissions: null,
    address_storage_enabled: true,
    separate_marking_print_enabled: false,
    fbs_shipment_cutoff_time: '14:00',
  }
}

function sellerMe() {
  const seller = sellerById(SELLER_KR)!
  return {
    id: 'user-seller-anna',
    email: 'anna@kravtsova-home.ru',
    full_name: 'Анна Кравцова',
    job_title: 'Владелец',
    display_name: 'Анна Кравцова',
    organization_name: ORG_NAME,
    organization_slug: 'sklad24',
    role: 'fulfillment_seller',
    seller_id: seller.id,
    seller_name: seller.name,
    home_seller_id: seller.id,
    home_seller_name: seller.name,
    active_seller_id: seller.id,
    active_seller_name: seller.name,
    can_manage_seller_shops: false,
    switchable_shops: [],
    delegatable_shops: [],
    permissions: null,
    seller_permissions: { documents: true, products: true, honest_sign: true, settings: true, staff: true },
  }
}

// ── Строки каталога ─────────────────────────────────────────────────────────
function catalogRow(p: ProductFx) {
  const seller = sellerById(p.seller_id)
  const primary = p.wb_barcodes[0] ?? null
  return {
    id: p.id,
    seller_id: p.seller_id,
    seller_name: seller?.name ?? null,
    name: p.name,
    sku_code: p.sku_code,
    wb_nm_id: p.wb_nm_id,
    wb_vendor_code: p.wb_vendor_code,
    ozon_sku: p.ozon_sku,
    ozon_offer_id: p.ozon_offer_id,
    marketplaces: productMarketplaces(p),
    wb_subject_name: p.wb_subject_name,
    wb_primary_image_url: p.photo,
    wb_barcodes: p.wb_barcodes,
    wb_primary_barcode: primary,
    wb_size: p.wb_size,
    wb_color: p.wb_color,
    wb_brand: p.wb_brand,
    wb_composition: p.wb_composition,
    packaging_instructions: p.packaging_instructions,
    country_of_origin_iso_code: p.country,
    requires_honest_sign: p.requires_honest_sign,
    has_packaging_instructions: Boolean(p.packaging_instructions),
    marking_available_count: p.requires_honest_sign ? Math.max(0, p.quantity - 4) : 0,
    fbs_stock_sync_enabled: p.fbs.enabled,
    fbs_stock_limit: p.fbs.mode === 'units' ? p.fbs.value : null,
    fbs_published_amount: p.fbs.enabled ? fbsPublished(p) : null,
    fbs_percent: p.fbs.enabled && p.fbs.mode === 'percent' && p.fbs.value !== 100 ? p.fbs.value : null,
    fbs_same_everywhere: true,
    fbs_sync_status: p.fbs.enabled ? 'synced' : null,
    marketplace_bindings: ozonBindings(p),
    wb_connected: p.wb_nm_id != null,
    ozon_connected: Boolean(p.ozon_offer_id),
  }
}

function ozonBindings(p: ProductFx) {
  if (!p.ozon_offer_id) return []
  return [
    {
      marketplace: 'ozon',
      external_product_id: p.ozon_product_id,
      external_offer_id: p.ozon_offer_id,
      external_sku: p.ozon_sku,
      external_barcodes: p.ozon_barcodes,
    },
  ]
}

function matchesSearch(p: ProductFx, search: string): boolean {
  const q = search.trim().toLowerCase()
  if (!q) return true
  const hay = [p.name, p.sku_code, p.wb_vendor_code, p.ozon_offer_id, p.ozon_sku, p.wb_nm_id != null ? String(p.wb_nm_id) : null, ...p.wb_barcodes, ...p.ozon_barcodes]
  return hay.some((v) => v != null && v.toLowerCase().includes(q))
}

function ffCatalogPage(ctx: Ctx) {
  const q = ctx.query
  const limit = Number(q.get('limit') ?? 100)
  const offset = Number(q.get('offset') ?? 0)
  const sellerId = q.get('seller_id')
  const search = q.get('search') ?? ''
  const category = q.get('category')
  const marketplace = q.get('marketplace')
  const publication = q.get('stock_publication')
  const scope = products.filter((p) => !sellerId || p.seller_id === sellerId)
  const filtered = scope.filter((p) => {
    if (!matchesSearch(p, search)) return false
    if (category && p.wb_subject_name !== category) return false
    if (marketplace === 'wildberries' && p.wb_nm_id == null) return false
    if (marketplace === 'ozon' && !p.ozon_offer_id) return false
    if (publication === 'enabled' && !p.fbs.enabled) return false
    if (publication === 'disabled' && p.fbs.enabled) return false
    return true
  })
  return {
    items: filtered.slice(offset, offset + limit).map(catalogRow),
    total: filtered.length,
    scope_total: scope.length,
    limit,
    offset,
    categories: [...new Set(scope.map((p) => p.wb_subject_name).filter((v): v is string => Boolean(v)))].sort((a, b) => a.localeCompare(b, 'ru')),
  }
}

function stockSummary(ctx: Ctx) {
  const ids = ctx.query.getAll('product_id')
  const scope = ctx.cabinet === 'seller' ? products.filter((p) => p.seller_id === SELLER_KR) : products
  const chosen = ids.length > 0 ? scope.filter((p) => ids.includes(p.id)) : scope
  return chosen.map((p) => ({
    product_id: p.id,
    sku_code: p.sku_code,
    product_name: p.name,
    quantity: p.quantity,
    reserved: p.reserved,
    available: productAvailable(p),
  }))
}

function productCard(ctx: Ctx) {
  const p = productById(ctx.match[1]!)
  if (!p) return reply(404, { detail: 'product_not_found' })
  const row = catalogRow(p)
  return {
    ...row,
    marketplace_bindings: ozonBindings(p),
    length_mm: p.length_mm,
    width_mm: p.width_mm,
    height_mm: p.height_mm,
    weight_g: p.weight_g,
    location_warehouses: p.quantity > 0 ? [{ id: WAREHOUSE.id, name: WAREHOUSE.name }] : [],
  }
}

function productMovementsPage(ctx: Ctx) {
  const p = productById(ctx.query.get('product_id') ?? '')
  if (!p) return reply(404, { detail: 'product_not_found' })
  const page = Math.max(1, Number(ctx.query.get('page') ?? 1))
  const limit = 200
  const rows = productMovements(p)
  const slice = rows.slice((page - 1) * limit, page * limit)
  return { rows: slice, truncated: (page - 1) * limit + slice.length < rows.length, total: rows.length, page, limit }
}

// ── Окно «Остаток для FBS» ──────────────────────────────────────────────────
const WB_WAREHOUSE_ID = 1402871
const OZON_WAREHOUSE_ID = 1020001987654000

function sellerBindings(sellerId: string) {
  const seller = sellerById(sellerId)
  const result: Array<Record<string, unknown>> = []
  if (seller?.wb_has_key) {
    result.push({
      id: `bind-wb-${sellerId}`,
      wb_warehouse_id: WB_WAREHOUSE_ID,
      wms_warehouse_id: WAREHOUSE.id,
      wms_warehouse_name: WAREHOUSE.name,
      is_active: true,
      served: true,
      marketplace: 'wb',
      external_warehouse_id: String(WB_WAREHOUSE_ID),
      editable: true,
    })
  }
  if (seller?.ozon_connected) {
    result.push({
      id: `bind-ozon-${sellerId}`,
      wb_warehouse_id: OZON_WAREHOUSE_ID,
      wms_warehouse_id: WAREHOUSE.id,
      wms_warehouse_name: WAREHOUSE.name,
      is_active: true,
      served: true,
      marketplace: 'ozon',
      external_warehouse_id: String(OZON_WAREHOUSE_ID),
      editable: true,
    })
  }
  return result
}

/** Правило товара по привязке: своё у склада, если его задавали, иначе общее правило товара. */
function bindingRule(p: ProductFx, binding: Record<string, unknown>) {
  const free = Math.max(0, productAvailable(p))
  const marketplace = String(binding.marketplace)
  const applicable = marketplace === 'ozon' ? Boolean(p.ozon_offer_id) : p.wb_nm_id != null
  const rule = p.fbsByBinding[String(binding.id)] ?? p.fbs
  return {
    publish: rule.enabled,
    mode: rule.mode,
    value: rule.value,
    units_configured: rule.mode === 'units',
    marketplace,
    external_warehouse_id: String(binding.external_warehouse_id),
    wms_warehouse_id: String(binding.wms_warehouse_id),
    served: true,
    applicable,
    on_hand: p.quantity,
    reserved: p.reserved,
    free_stock: free,
    published_now: applicable ? fbsPublished(p, rule) : 0,
  }
}

function bulkRules(ctx: Ctx) {
  const body = ctx.body as { product_ids?: string[] } | null
  const ids = body?.product_ids ?? []
  return {
    items: ids
      .map((id) => productById(id))
      .filter((p): p is ProductFx => Boolean(p))
      .map((p) => ({
        product_id: p.id,
        by_binding: Object.fromEntries(sellerBindings(p.seller_id).map((b) => [String(b.id), bindingRule(p, b)])),
      })),
  }
}

function saveRule(ctx: Ctx) {
  const body = ctx.body as { product_ids?: string[]; rule?: { by_binding?: Record<string, { publish: boolean; mode: 'percent' | 'units'; value: number }> } } | null
  const ids = body?.product_ids ?? []
  const byBinding = body?.rule?.by_binding ?? {}
  for (const id of ids) {
    const p = productById(id)
    if (!p) continue
    for (const [bindingId, one] of Object.entries(byBinding)) {
      const rule = { enabled: one.publish, mode: one.mode, value: one.value }
      p.fbsByBinding[bindingId] = rule
      // Колонка каталога «В Wildberries» показывает правило склада WB.
      if (bindingId.startsWith('bind-wb-')) p.fbs = rule
    }
  }
  return {
    items: ids
      .map((id) => productById(id))
      .filter((p): p is ProductFx => Boolean(p))
      .map((p) => ({ product_id: p.id, by_binding: Object.fromEntries(sellerBindings(p.seller_id).map((b) => [String(b.id), bindingRule(p, b)])) })),
    clamps: {},
  }
}

// ── Реквизиты ───────────────────────────────────────────────────────────────
function saveProfile(target: 'ff' | string, body: unknown): unknown {
  const data = body as Profile
  const profile: Profile = {
    legal_name: data.legal_name,
    inn: data.inn,
    kpp: data.kpp ?? null,
    bank_name: data.bank_name ?? null,
    bik: data.bik ?? null,
    settlement_account: data.settlement_account ?? null,
    correspondent_account: data.correspondent_account ?? null,
  }
  if (target === 'ff') {
    Object.assign(FF_PROFILE, profile)
    return FF_PROFILE
  }
  const seller = sellerById(target)
  if (!seller) return reply(404, { detail: 'seller_not_found' })
  seller.profile = profile
  return profile
}

const DADATA: Record<string, { legal_name: string; kpp: string | null; address: string; manager: string }> = {
  '3702184456': { legal_name: 'ООО «Текстиль Хоум»', kpp: '370201001', address: 'г. Иваново, ул. Станкостроителей, д. 12', manager: 'Белов Сергей Игоревич' },
  '7814652093': { legal_name: 'ООО «Северный Трикотаж»', kpp: '781401001', address: 'г. Санкт-Петербург, Коломяжский пр-кт, д. 27', manager: 'Ковалёва Ирина Павловна' },
  '503214789652': { legal_name: 'ИП Кравцова Анна Викторовна', kpp: null, address: 'Московская обл., г. Подольск', manager: 'Кравцова Анна Викторовна' },
  '5036172941': { legal_name: 'ООО «Склад-24»', kpp: '503601001', address: 'Московская обл., г. Подольск, ул. Индустриальная, д. 4', manager: 'Смирнова Ольга Николаевна' },
}

// ── Расчёты ────────────────────────────────────────────────────────────────
type EntryFx = {
  id: string
  seller_id: string
  kind: 'operation_fact'
  occurred_at: string
  service_code: string
  item_quantity: number
  source_type: string
  source_id: string
  supply: { id: string; number: string } | null
  source_target: { kind: 'inbound'; source_id: string } | { kind: 'fbs_order'; source_id: string } | { kind: 'route'; to: string } | null
  document_number: string
  product_name: string | null
  sku: string | null
  rate_kopecks: number
  amount_kopecks: number
  unit: string
  fbs_status_label: string | null
  invoiced: boolean
}

let entriesCache: EntryFx[] | null = null

/** Начисления строятся из тех же движений, что видит карточка товара. */
function billingEntries(): EntryFx[] {
  if (entriesCache) return entriesCache
  const since = NOW.getTime() - 75 * DAY
  const entries: EntryFx[] = []
  const byDoc = new Map<string, EntryFx>()
  for (const p of products) {
    for (const move of productMovements(p)) {
      const at = new Date(move.at).getTime()
      if (at < since || !move.document) continue
      const doc = move.document
      if (move.operation === 'Приёмка' && doc.kind === 'inbound') {
        const key = `${p.seller_id}:inbound:${doc.id}`
        const existing = byDoc.get(key)
        if (existing) {
          existing.item_quantity += move.quantity
          existing.amount_kopecks = existing.item_quantity * RATES.inbound.rate
          existing.product_name = null
          existing.sku = null
          continue
        }
        const entry: EntryFx = {
          id: `led-${key}`,
          seller_id: p.seller_id,
          kind: 'operation_fact',
          occurred_at: move.at,
          service_code: 'inbound',
          item_quantity: move.quantity,
          source_type: 'inbound_intake',
          source_id: doc.id,
          supply: null,
          source_target: { kind: 'inbound', source_id: doc.id },
          document_number: `Приёмка ${doc.number}`,
          product_name: p.name,
          sku: p.sku_code,
          rate_kopecks: RATES.inbound.rate,
          amount_kopecks: move.quantity * RATES.inbound.rate,
          unit: RATES.inbound.unit,
          fbs_status_label: null,
          invoiced: at < NOW.getTime() - 22 * DAY,
        }
        byDoc.set(key, entry)
        entries.push(entry)
      } else if (move.operation === 'Отгрузка на МП' && doc.kind === 'marketplace_unload') {
        for (const service of ['packing', 'marketplace_outbound'] as const) {
          const key = `${p.seller_id}:${service}:${doc.id}`
          const qty = -move.quantity
          const existing = byDoc.get(key)
          if (existing) {
            existing.item_quantity += qty
            existing.amount_kopecks = existing.item_quantity * RATES[service].rate
            existing.product_name = null
            existing.sku = null
            continue
          }
          const entry: EntryFx = {
            id: `led-${key}`,
            seller_id: p.seller_id,
            kind: 'operation_fact',
            occurred_at: move.at,
            service_code: service,
            item_quantity: qty,
            source_type: 'marketplace_unload',
            source_id: doc.id,
            supply: null,
            source_target: null,
            document_number: `Отгрузка ${doc.number}`,
            product_name: p.name,
            sku: p.sku_code,
            rate_kopecks: RATES[service].rate,
            amount_kopecks: qty * RATES[service].rate,
            unit: RATES[service].unit,
            fbs_status_label: null,
            invoiced: at < NOW.getTime() - 22 * DAY,
          }
          byDoc.set(key, entry)
          entries.push(entry)
        }
      } else if (move.operation === 'FBS' && doc.kind === 'fbs_supply') {
        // Как на сервере: заказ FBS — документ с двумя услугами, FBS и упаковка.
        const supply = fbsSupplies.find((s) => s.id === doc.id) ?? null
        for (const service of ['fbs_order', 'packing'] as const) {
          entries.push({
            id: `fbs_order:${move.id}:${service}`,
            seller_id: p.seller_id,
            kind: 'operation_fact',
            occurred_at: move.at,
            service_code: service,
            item_quantity: 1,
            source_type: 'fbs_order',
            source_id: move.id,
            supply,
            source_target: { kind: 'fbs_order', source_id: move.id },
            document_number: doc.number,
            product_name: p.name,
            sku: p.sku_code,
            rate_kopecks: RATES[service].rate,
            amount_kopecks: RATES[service].rate,
            unit: service === 'fbs_order' ? RATES.fbs_order.unit : RATES.packing.unit,
            fbs_status_label: at > NOW.getTime() - 2 * DAY ? 'Передан ВБ' : 'ВБ получил',
            invoiced: at < NOW.getTime() - 22 * DAY,
          })
        }
      }
    }
  }
  entriesCache = entries.sort((a, b) => b.occurred_at.localeCompare(a.occurred_at))
  return entriesCache
}

function rangeOf(ctx: Ctx): { from: string; to: string } {
  const today = moscowDateKey(NOW)
  return { from: ctx.query.get('date_from') ?? today, to: ctx.query.get('date_to') ?? today }
}

function entriesFor(sellerId: string | null, range: { from: string; to: string }): EntryFx[] {
  return billingEntries().filter((e) => {
    if (sellerId && e.seller_id !== sellerId) return false
    const day = moscowDateKey(new Date(e.occurred_at))
    return day >= range.from && day <= range.to
  })
}

function daysInRange(range: { from: string; to: string }): number {
  return Math.max(1, Math.round((Date.parse(range.to) - Date.parse(range.from)) / DAY) + 1)
}

function storageLiterDays(sellerId: string | null, range: { from: string; to: string }): number {
  const perDay = products.filter((p) => !sellerId || p.seller_id === sellerId).reduce((sum, p) => sum + p.quantity * productVolumeLiters(p), 0)
  return Math.round(perDay * daysInRange(range) * 100) / 100
}

function sellerSummaryRow(sellerId: string, range: { from: string; to: string }) {
  const seller = sellerById(sellerId)!
  const list = entriesFor(sellerId, range)
  const storage = Math.round(storageLiterDays(sellerId, range) * RATES.storage.rate)
  return {
    seller_id: sellerId,
    seller_name: seller.name,
    operation_count: list.length,
    item_quantity: list.reduce((s, e) => s + e.item_quantity, 0),
    not_billable_count: 0,
    details_target: 'seller_details',
    unpriced_count: 0,
    net_total_kopecks: list.reduce((s, e) => s + e.amount_kopecks, 0) + storage,
  }
}

function summaryTotals(rows: ReturnType<typeof sellerSummaryRow>[], sellerIds: string[], range: { from: string; to: string }) {
  const list = sellerIds.flatMap((id) => entriesFor(id, range))
  const sumBy = (service: string) => list.filter((e) => e.service_code === service).reduce((s, e) => s + e.item_quantity, 0)
  return {
    seller_count: rows.length,
    operation_count: rows.reduce((s, r) => s + r.operation_count, 0),
    item_quantity: rows.reduce((s, r) => s + r.item_quantity, 0),
    not_billable_count: 0,
    net_total_kopecks: rows.reduce((s, r) => s + r.net_total_kopecks, 0),
    inbound_items: sumBy('inbound'),
    packing_items: sumBy('packing'),
    outbound_items: sumBy('marketplace_outbound'),
    fbs_items: sumBy('fbs_order'),
  }
}

function ffSummary(ctx: Ctx) {
  const range = rangeOf(ctx)
  const sellerId = ctx.query.get('seller_id')
  const ids = sellers.map((s) => s.id).filter((id) => !sellerId || id === sellerId)
  const rows = ids.map((id) => sellerSummaryRow(id, range)).filter((r) => r.operation_count > 0 || sellerId)
  return { rows, totals: summaryTotals(rows, rows.map((r) => r.seller_id), range) }
}

function sellerScopeSummary(ctx: Ctx) {
  const range = rangeOf(ctx)
  const row = sellerSummaryRow(SELLER_KR, range)
  const rows = row.operation_count > 0 ? [row] : []
  return { rows, totals: summaryTotals(rows, [SELLER_KR], range) }
}

function details(sellerId: string, ctx: Ctx) {
  const range = rangeOf(ctx)
  const seller = sellerById(sellerId)!
  const list = entriesFor(sellerId, range)
  const liters = storageLiterDays(sellerId, range)
  return {
    seller_id: sellerId,
    seller_name: seller.name,
    entries: list.map((e) => ({
      id: e.id,
      kind: e.kind,
      occurred_at: e.occurred_at,
      service_code: e.service_code,
      item_quantity: e.item_quantity,
      source_type: e.source_type,
      source_id: e.source_id,
      supply: e.supply,
      source_target: e.source_target,
      document_number: e.document_number,
      product_name: e.product_name,
      sku: e.sku,
      result: 'completed',
      unit: e.unit,
      rate_kopecks: e.rate_kopecks,
      amount_kopecks: e.amount_kopecks,
      billing_ledger_entry_id: e.id,
      fbs_status_label: e.fbs_status_label,
      priced_live: false,
      invoice_history: { state: 'known', count: e.invoiced ? 1 : 0 },
    })),
    storage_row: liters > 0 ? { kind: 'storage', date_from: range.from, date_to: range.to, liter_days: liters, status: 'calculated', amount_kopecks: Math.round(liters * RATES.storage.rate) } : null,
    next_cursor: null,
  }
}

function invoiceRow(inv: InvoiceFx) {
  return {
    id: inv.id,
    origin: inv.origin,
    number: inv.number,
    seller_id: inv.seller_id,
    seller_name: sellerById(inv.seller_id)?.name ?? '—',
    issued_at: inv.issued_at,
    period_start: inv.period_start,
    period_end: inv.period_end,
    creation_mode: inv.creation_mode,
    status: inv.status,
    total_amount_kopecks: invoiceTotal(inv),
  }
}

function invoiceList(ctx: Ctx, sellerScope: boolean) {
  const status = ctx.query.get('status') ?? 'all'
  const sellerId = sellerScope ? SELLER_KR : ctx.query.get('seller_id') ?? 'all'
  const number = (ctx.query.get('number') ?? '').trim().toLowerCase()
  const list = invoices
    .filter((inv) => sellerId === 'all' || inv.seller_id === sellerId)
    .filter((inv) => status === 'all' || inv.status === status)
    .filter((inv) => !number || inv.number.toLowerCase().includes(number))
    .sort((a, b) => b.issued_at.localeCompare(a.issued_at))
  return { invoices: list.map(invoiceRow), next_cursor: null }
}

function v2Invoice(inv: InvoiceFx) {
  return {
    id: inv.id,
    number: inv.number,
    status: inv.status,
    issued_at: inv.issued_at,
    period_start: inv.period_start,
    period_end: inv.period_end,
    creation_mode: inv.creation_mode,
    total_amount_kopecks: invoiceTotal(inv),
    ff_profile: FF_PROFILE,
    seller_profile: inv.seller_profile ?? undefined,
    lines: inv.lines,
  }
}

function legacyInvoice(inv: InvoiceFx) {
  const codes: Record<string, string> = { 'Приёмка': 'inbound', 'Отгрузка': 'marketplace_outbound', 'Хранение': 'storage_liter_day' }
  return {
    id: inv.id,
    number: inv.number,
    period: (inv.period_start ?? '').slice(0, 7),
    status: inv.status,
    issued_at: inv.issued_at,
    seller_name: sellerById(inv.seller_id)?.name ?? '—',
    total_amount: invoiceTotal(inv),
    ff_profile: FF_PROFILE,
    seller_profile: inv.seller_profile ?? undefined,
    lines: inv.lines.map((l) => ({ id: l.id, service_code: codes[l.description] ?? l.description, amount: l.total_amount_kopecks ?? 0 })),
  }
}

function findInvoice(id: string, sellerScope: boolean): InvoiceFx | undefined {
  const inv = invoices.find((i) => i.id === id)
  if (!inv) return undefined
  if (sellerScope && inv.seller_id !== SELLER_KR) return undefined
  return inv
}

type PreviewBody = {
  creation_mode: 'manual' | 'selected_operations'
  seller_id: string
  date_from?: string
  date_to?: string
  selected_root_ids?: string[]
  include_storage?: boolean
  manual_lines?: Array<{ description: string; amount: string }>
  lines?: Array<{ description: string; amount: string }>
  final_amount?: string
}

function rubToKopecks(value: string): number {
  return Math.round(Number(value.replace(/\s/g, '').replace(',', '.')) * 100)
}

function buildPreviewLines(body: PreviewBody) {
  const lines: Array<{ id: string; description: string; unit_price_kopecks: number | null; total_amount_kopecks: number | null; sort_order: number }> = []
  if (body.creation_mode === 'manual') {
    for (const line of body.lines ?? []) {
      lines.push({ id: `pl-${lines.length}`, description: line.description, unit_price_kopecks: null, total_amount_kopecks: rubToKopecks(line.amount), sort_order: lines.length })
    }
    return lines
  }
  const selected = new Set(body.selected_root_ids ?? [])
  const chosen = billingEntries().filter((e) => selected.has(e.id))
  for (const service of ['inbound', 'packing', 'fbs_order', 'marketplace_outbound']) {
    const group = chosen.filter((e) => e.service_code === service)
    if (group.length === 0) continue
    const qty = group.reduce((s, e) => s + e.item_quantity, 0)
    const unitLabel = service === 'fbs_order' ? 'заказов' : 'шт.'
    lines.push({
      id: `pl-${lines.length}`,
      description: `${SERVICE_TITLES[service]} — ${qty} ${unitLabel}`,
      unit_price_kopecks: RATES[service as keyof typeof RATES].rate,
      total_amount_kopecks: group.reduce((s, e) => s + e.amount_kopecks, 0),
      sort_order: lines.length,
    })
  }
  if (body.include_storage && body.date_from && body.date_to) {
    const liters = storageLiterDays(body.seller_id, { from: body.date_from, to: body.date_to })
    lines.push({ id: `pl-${lines.length}`, description: 'Хранение', unit_price_kopecks: RATES.storage.rate, total_amount_kopecks: Math.round(liters * RATES.storage.rate), sort_order: lines.length })
  }
  for (const line of body.manual_lines ?? []) {
    lines.push({ id: `pl-${lines.length}`, description: line.description, unit_price_kopecks: null, total_amount_kopecks: rubToKopecks(line.amount), sort_order: lines.length })
  }
  return lines
}

function previewInvoice(ctx: Ctx) {
  const body = ctx.body as PreviewBody
  const seller = sellerById(body.seller_id)
  if (!seller) return reply(422, { detail: 'seller_not_found' })
  const lines = buildPreviewLines(body)
  const calculated = lines.reduce((s, l) => s + (l.total_amount_kopecks ?? 0), 0)
  const total = body.final_amount ? rubToKopecks(body.final_amount) : calculated
  return {
    id: 'preview',
    seller_id: seller.id,
    number: 'Будет присвоен при сохранении',
    creation_mode: body.creation_mode,
    period_start: body.date_from ?? null,
    period_end: body.date_to ?? null,
    status: 'issued',
    issued_at: null,
    total_amount_kopecks: total,
    calculated_amount_kopecks: calculated,
    ff_profile: FF_PROFILE,
    seller_profile: seller.profile ?? undefined,
    lines,
  }
}

function issueInvoice(ctx: Ctx) {
  const body = ctx.body as PreviewBody
  const seller = sellerById(body.seller_id)
  if (!seller) return reply(422, { detail: 'seller_not_found' })
  const lines = buildPreviewLines(body)
  const at = new Date()
  const inv: InvoiceFx = {
    id: `inv-live-${invoices.length}`,
    origin: 'v2',
    number: nextInvoiceNumber(at),
    seller_id: seller.id,
    issued_at: at.toISOString(),
    period_start: body.date_from ?? null,
    period_end: body.date_to ?? null,
    creation_mode: body.creation_mode,
    status: 'issued',
    lines: lines.map((l) => ({ id: l.id, description: l.description, total_amount_kopecks: l.total_amount_kopecks })),
    seller_profile: seller.profile,
  }
  if (body.final_amount) {
    const diff = rubToKopecks(body.final_amount) - invoiceTotal(inv)
    if (diff !== 0) inv.lines.push({ id: `pl-adj-${inv.lines.length}`, description: 'Корректировка итоговой суммы', total_amount_kopecks: diff })
  }
  invoices.push(inv)
  const selected = new Set(body.selected_root_ids ?? [])
  for (const e of billingEntries()) if (selected.has(e.id)) e.invoiced = true
  return { ...v2Invoice(inv), seller_id: seller.id, calculated_amount_kopecks: invoiceTotal(inv), lines: lines }
}

// ── Инвентаризация ─────────────────────────────────────────────────────────
function countProducts(count: InventoryCountFx): ProductFx[] {
  return products.filter((p) => countIncludes(count, p))
}

function fillLabel(count: InventoryCountFx): string {
  if (count.fill.mode === 'object') return count.fill.object_label ?? 'По объекту'
  if (count.fill.mode === 'all') return 'Товары документа'
  const parts = [count.fill.seller_id ? sellerById(count.fill.seller_id)?.name : null, count.fill.category].filter(Boolean)
  return parts.join(' · ') || 'Товары документа'
}

function countLines(count: InventoryCountFx) {
  const lines: Array<{ lineId: string; product: ProductFx; cell: string; container: { kind: 'pallet' | 'box'; code: string } | null; expected: number }> = []
  for (const p of countProducts(count)) {
    for (const pl of productPlacements(p)) {
      if (count.fill.mode === 'object' && pl.cell !== OBJECT_COUNT_CELL) continue
      lines.push({ lineId: `${count.id.slice(0, 8)}-${p.id}-${pl.cell}-${pl.container?.code ?? 'loose'}`, product: p, cell: pl.cell, container: pl.container, expected: pl.qty })
    }
  }
  return lines
}

function countActual(count: InventoryCountFx, lineId: string, expected: number, index: number): number | null {
  if (lineId in count.actual) return count.actual[lineId] ?? null
  if (count.status === 'posted') return index % 7 === 3 ? expected - 1 : index % 11 === 5 ? expected + 1 : expected
  // Черновик: первые строки уже посчитаны, остальные ждут пересчёта.
  return index < 4 ? (index === 2 ? expected - 1 : expected) : null
}

function countSummary(count: InventoryCountFx) {
  const lines = countLines(count)
  let counted = 0
  let surplus = 0
  let shortage = 0
  lines.forEach((l, i) => {
    const actual = countActual(count, l.lineId, l.expected, i)
    if (actual == null) return
    counted += 1
    if (actual > l.expected) surplus += actual - l.expected
    if (actual < l.expected) shortage += l.expected - actual
  })
  return {
    id: count.id,
    number: count.number,
    status: count.status,
    warehouse_name: WAREHOUSE.name,
    fill_label: fillLabel(count),
    created_at: count.created_at,
    created_by: count.created_by,
    lines: lines.length,
    counted,
    discrepancies: lines.filter((l, i) => {
      const a = countActual(count, l.lineId, l.expected, i)
      return a != null && a !== l.expected
    }).length,
    surplus,
    shortage,
  }
}

function countDetail(count: InventoryCountFx) {
  const lines = countLines(count)
  type ApiNodeOut = Record<string, unknown> & { children?: ApiNodeOut[] }
  const cells = new Map<string, { id: string; label: string; barcode: string; children: ApiNodeOut[]; containers: Map<string, ApiNodeOut> }>()
  lines.forEach((l, i) => {
    let cell = cells.get(l.cell)
    if (!cell) {
      cell = { id: `cell-${l.cell.replace(/\s|\./g, '')}`, label: l.cell, barcode: `LOC-${l.cell.replace(/\s|\./g, '')}`, children: [], containers: new Map() }
      cells.set(l.cell, cell)
    }
    const productNode: ApiNodeOut = {
      kind: 'product',
      id: l.lineId,
      name: l.product.name,
      sku: l.product.sku_code,
      seller: sellerById(l.product.seller_id)?.name ?? '—',
      category: l.product.wb_subject_name,
      barcode: l.product.wb_barcodes[0] ?? null,
      wb_vendor_code: l.product.wb_vendor_code,
      wb_barcode: l.product.wb_barcodes[0] ?? null,
      wb_size: l.product.wb_size,
      photo_url: l.product.photo,
      expected: l.expected,
      actual: countActual(count, l.lineId, l.expected, i),
      expected_now: l.expected,
    }
    if (l.container) {
      let container = cell.containers.get(l.container.code)
      if (!container) {
        container = { kind: l.container.kind, id: `cont-${l.container.code}`, code: l.container.code, barcode: l.container.code, children: [] }
        cell.containers.set(l.container.code, container)
        cell.children.push(container)
      }
      container.children!.push(productNode)
    } else {
      cell.children.push(productNode)
    }
  })
  const cellList = [...cells.values()].sort((a, b) => a.label.localeCompare(b.label, 'ru'))
  return {
    id: count.id,
    number: count.number,
    status: count.status,
    warehouse_id: WAREHOUSE.id,
    warehouse_name: WAREHOUSE.name,
    fill: count.fill,
    created_at: count.created_at,
    created_by: count.created_by,
    posted_at: count.posted_at,
    posted_by: count.posted_by,
    comment: count.comment,
    empty_places: [],
    address_storage: true,
    cells: cellList.map((c) => ({ id: c.id, label: c.label, barcode: c.barcode, children: c.children })),
    scannable_cells: cellList.map((c) => ({ id: c.id, label: c.label, barcode: c.barcode })),
    scannable_containers: cellList.flatMap((c) => [...c.containers.values()].map((k) => ({ kind: k.kind, id: k.id, code: k.code, barcode: k.barcode, cell_id: c.id }))),
  }
}

function printSheet(count: InventoryCountFx) {
  const seen = new Set<string>()
  const rows = countProducts(count)
    .filter((p) => (seen.has(p.id) ? false : (seen.add(p.id), true)))
    .map((p) => ({
      product_id: p.id,
      barcode: p.wb_barcodes[0] ?? null,
      article: p.wb_vendor_code ?? p.ozon_offer_id ?? p.sku_code,
      name: p.name,
      total: p.quantity,
      reserved: p.reserved,
    }))
  return {
    number: count.number,
    created_at: count.created_at,
    created_by: count.created_by,
    filters: {
      object: count.fill.mode === 'object',
      warehouse_name: WAREHOUSE.name,
      seller_name: count.fill.seller_id ? sellerById(count.fill.seller_id)?.name ?? null : null,
      category: count.fill.category,
      product_articles: [],
    },
    rows,
  }
}

// ── Каталог селлера ────────────────────────────────────────────────────────
function visibleSellerCards(): SellerCardFx[] {
  return sellerCards.filter((c) => c.marketplace === 'ozon' || sellerCabinet.wbKeyConnected)
}

function sellerCatalogItems(): Array<Record<string, unknown>> {
  const items: Array<Record<string, unknown>> = []
  const own = products.filter((p) => p.seller_id === SELLER_KR)
  for (const p of own) {
    items.push({ key: `product:${p.id}`, on_fulfillment: true, marketplace: p.wb_nm_id != null ? 'wildberries' : 'ozon', ...catalogRow(p), nm_id: null, ozon_product_id: null, vendor_code: null, photo_url: null, barcodes: [], sizes: [], category: null })
  }
  for (const card of visibleSellerCards()) {
    if (cardOnFulfillment(card)) continue
    items.push({
      key: card.marketplace === 'wildberries' ? `wb:${card.nm_id}` : `ozon:${card.ozon_product_id}`,
      on_fulfillment: false,
      marketplace: card.marketplace,
      id: null,
      name: card.name,
      nm_id: card.nm_id,
      ozon_product_id: card.ozon_product_id,
      vendor_code: card.vendor_code,
      photo_url: card.photo_url,
      barcodes: card.barcodes,
      sizes: card.sizes,
      category: card.category,
      wb_barcodes: [],
      marketplace_bindings: [],
    })
  }
  return items
}

function itemCategory(item: Record<string, unknown>): string | null {
  return (item.on_fulfillment ? item.wb_subject_name : item.category) as string | null
}

function sellerCatalogFiltered(ctx: Ctx) {
  const q = ctx.query
  const onFf = q.get('on_fulfillment') ?? 'all'
  const marketplace = q.get('marketplace')
  const search = (q.get('search') ?? '').trim().toLowerCase()
  const category = q.get('category')
  const scope = sellerCatalogItems().filter((item) => !marketplace || item.marketplace === marketplace)
  const filtered = scope.filter((item) => {
    if (onFf === 'yes' && !item.on_fulfillment) return false
    if (onFf === 'no' && item.on_fulfillment) return false
    if (category && itemCategory(item) !== category) return false
    if (search) {
      const hay = [item.name, item.sku_code, item.wb_vendor_code, item.vendor_code, item.nm_id, item.wb_nm_id, item.ozon_product_id, item.ozon_offer_id, ...((item.barcodes as string[]) ?? []), ...((item.wb_barcodes as string[]) ?? [])]
      if (!hay.some((v) => v != null && String(v).toLowerCase().includes(search))) return false
    }
    return true
  })
  return { scope, filtered }
}

function sellerCatalogPage(ctx: Ctx) {
  const limit = Number(ctx.query.get('limit') ?? 100)
  const offset = Number(ctx.query.get('offset') ?? 0)
  const { scope, filtered } = sellerCatalogFiltered(ctx)
  return {
    items: filtered.slice(offset, offset + limit),
    total: filtered.length,
    scope_total: scope.length,
    limit,
    offset,
    categories: [...new Set(scope.map(itemCategory).filter((v): v is string => Boolean(v)))].sort((a, b) => a.localeCompare(b, 'ru')),
  }
}

function addToFulfillment(ctx: Ctx) {
  const body = ctx.body as { wb_nm_ids?: number[]; ozon_product_ids?: string[] } | null
  const added: Array<{ marketplace: string; id: string; vendor_code: string; products_added: number }> = []
  for (const nm of body?.wb_nm_ids ?? []) {
    const card = sellerCards.find((c) => c.marketplace === 'wildberries' && c.nm_id === nm)
    if (!card) continue
    addCardToFulfillment(card)
    added.push({ marketplace: 'wildberries', id: String(nm), vendor_code: card.vendor_code, products_added: 1 })
  }
  for (const id of body?.ozon_product_ids ?? []) {
    const card = sellerCards.find((c) => c.marketplace === 'ozon' && c.ozon_product_id === id)
    if (!card) continue
    addCardToFulfillment(card)
    added.push({ marketplace: 'ozon', id, vendor_code: card.vendor_code, products_added: 1 })
  }
  return { added, skipped: [] }
}

function ozonAccount() {
  return {
    marketplace: 'ozon',
    connected: true,
    live_exchange_enabled: true,
    validation_status: 'valid',
    last_validated_at: new Date(NOW.getTime() - 3 * 60 * 60 * 1000).toISOString(),
    last_validation_error: null,
    credentials_updated_at: new Date(NOW.getTime() - 20 * DAY).toISOString(),
    last_synced_at: new Date(NOW.getTime() - 40 * 60 * 1000).toISOString(),
    last_sync_error: null,
  }
}

type SellerRateOut = {
  service_code: string
  unit: string
  rate_kopecks: number
  valid_from_at: string
  product_id: string | null
  product_sku: string | null
  product_name: string | null
}

function sellerRates() {
  const since = new Date(NOW.getTime() - 120 * DAY).toISOString()
  const rows: SellerRateOut[] = (['inbound', 'packing', 'fbs_order', 'marketplace_outbound', 'storage'] as const).map((code) => ({
    service_code: code,
    unit: RATES[code].unit,
    rate_kopecks: RATES[code].rate,
    valid_from_at: since,
    product_id: null,
    product_sku: null,
    product_name: null,
  }))
  // Отдельная ставка на один товар: стёганое покрывало упаковывать дольше.
  const special = products.find((p) => p.seller_id === SELLER_KR && p.sku_code === 'KR-PK-220-BEG')
  if (special) {
    rows.push({ service_code: 'packing', unit: 'item', rate_kopecks: 2500, valid_from_at: new Date(NOW.getTime() - 45 * DAY).toISOString(), product_id: special.id, product_sku: special.sku_code, product_name: special.name })
  }
  return { rates: rows }
}

// ── Таблица маршрутов ──────────────────────────────────────────────────────
const sellerList = () =>
  sellers.map((s) => ({
    id: s.id,
    name: s.name,
    wb_has_key: s.wb_has_key,
    wb_marketplace_scope_ok: s.wb_marketplace_scope_ok,
    wb_marketplace_scope_checked_at: s.wb_marketplace_scope_checked_at,
    ozon_connected: s.ozon_connected,
  }))

const routes: Route[] = [
  // Вход, подписка, уведомления.
  { method: 'GET', path: /^\/auth\/me$/, handler: (c) => (c.cabinet === 'seller' ? sellerMe() : ffMe()) },
  { method: 'GET', path: /^\/subscription$/, handler: () => ({ enabled: false, paid_until: null, days_left: null, blocked: false, price_rub: 0, payment_available: false }) },
  { method: 'GET', path: /^\/operations\/notifications/, handler: () => ({ items: [], unread_count: 0 }) },
  { method: 'POST', path: /^\/operations\/notifications/, handler: () => ({ ok: true }) },
  { method: 'POST', path: /^\/client-errors/, handler: () => ({ ok: true }) },

  // Справочники ФФ.
  { method: 'GET', path: /^\/warehouses$/, handler: () => [WAREHOUSE] },
  { method: 'GET', path: /^\/warehouses\/[^/]+\/locations/, handler: () => [] },
  { method: 'GET', path: /^\/sellers$/, handler: (c) => (c.cabinet === 'seller' ? [sellerList().find((s) => s.id === SELLER_KR)] : sellerList()) },
  { method: 'GET', path: /^\/operations\/(inbound-intake-requests|outbound-shipment-requests|marketplace-unload-requests|discrepancy-acts|background-jobs|stock-transfers)$/, handler: () => [] },
  { method: 'GET', path: /^\/operations\/inventory-movements/, handler: () => [] },
  { method: 'GET', path: /^\/operations\/wb-mp-warehouses/, handler: () => [] },
  { method: 'GET', path: /^\/integrations\/wildberries\/sellers\/([^/]+)\/tokens$/, handler: (c) => {
      const seller = sellerById(c.match[1])
      const has = Boolean(seller?.wb_has_key)
      return { has_content_token: has, has_supplies_token: has, has_marketplace_token: has, marketplace_scope_ok: seller?.wb_marketplace_scope_ok ?? null, updated_at: has ? seller?.wb_marketplace_scope_checked_at ?? null : null }
    } },
  { method: 'GET', path: /^\/integrations\/wildberries\/sellers\/[^/]+\/(imported-cards|imported-supplies)$/, handler: () => [] },

  // Каталог и карточка товара.
  { method: 'GET', path: /^\/products\/ff-catalog-page$/, handler: ffCatalogPage },
  { method: 'GET', path: /^\/products\/ff-catalog$/, handler: () => products.map(catalogRow) },
  { method: 'GET', path: /^\/products\/categories$/, handler: () => [...new Set(products.map((p) => p.wb_subject_name).filter(Boolean))].sort() },
  { method: 'GET', path: /^\/products\/wb-catalog$/, handler: (c) => products.filter((p) => c.cabinet !== 'seller' || p.seller_id === SELLER_KR).map(catalogRow) },
  { method: 'GET', path: /^\/products$/, handler: () => products.map(catalogRow) },
  { method: 'GET', path: /^\/operations\/inventory-balances\/summary$/, handler: stockSummary },
  { method: 'GET', path: /^\/products\/([^/]+)\/card$/, handler: productCard },
  { method: 'GET', path: /^\/reports\/inventory\/product-movements$/, handler: productMovementsPage },
  { method: 'GET', path: /^\/products\/([^/]+)\/stock-directions$/, handler: () => [] },
  { method: 'POST', path: /^\/products\/fbs-rule\/bulk$/, handler: bulkRules },
  { method: 'PUT', path: /^\/products\/fbs-rule$/, handler: saveRule },
  { method: 'GET', path: /^\/operations\/fbs-sellers\/([^/]+)\/warehouses$/, handler: (c) => (sellerById(c.match[1])?.wb_has_key ? [{ wb_warehouse_id: WB_WAREHOUSE_ID, name: 'Склад-24 Подольск (FBS)', wms_warehouse_id: WAREHOUSE.id, served: true }] : reply(409, { detail: { code: 'wb_token_missing', message: 'Ключ WB не подключён' } })) },
  { method: 'GET', path: /^\/operations\/fbs-sellers\/([^/]+)\/warehouse-bindings$/, handler: (c) => sellerBindings(c.match[1]!) },
  { method: 'GET', path: /^\/operations\/fbs-sellers\/([^/]+)\/ozon-warehouses$/, handler: (c) => (sellerById(c.match[1])?.ozon_connected ? [{ warehouse_id: OZON_WAREHOUSE_ID, name: 'Склад-24 Подольск (rFBS)', served: true, wms_warehouse_id: WAREHOUSE.id }] : reply(409, { detail: 'Ozon не подключён у селлера' })) },
  { method: 'PUT', path: /^\/fbs-sellers\/([^/]+)\/warehouses\/([^/]+)$/, handler: () => ({ ok: true }) },
  { method: 'PUT', path: /^\/products\/([^/]+)\/packaging-instructions$/, handler: (c) => {
      const p = productById(c.match[1]!)
      const body = c.body as { packaging_instructions?: string | null; requires_honest_sign?: boolean } | null
      if (p && body) {
        if ('packaging_instructions' in body) p.packaging_instructions = body.packaging_instructions || null
        if (typeof body.requires_honest_sign === 'boolean') p.requires_honest_sign = body.requires_honest_sign
      }
      return p ? catalogRow(p) : reply(404, { detail: 'product_not_found' })
    } },

  // Селлеры и реквизиты.
  { method: 'GET', path: /^\/billing\/profiles\/ff$/, handler: () => FF_PROFILE },
  { method: 'PUT', path: /^\/billing\/profiles\/ff$/, handler: (c) => saveProfile('ff', c.body) },
  { method: 'GET', path: /^\/billing\/profiles\/sellers\/([^/]+)\/marketplace-requisites$/, handler: (c) => {
      const seller = sellerById(c.match[1])
      const marketplace = c.query.get('marketplace') === 'ozon' ? 'ozon' : 'wb'
      const data = seller?.marketplaceRequisites[marketplace]
      return data ?? reply(409, { detail: 'key_not_connected' })
    } },
  { method: 'GET', path: /^\/billing\/profiles\/sellers\/([^/]+)$/, handler: (c) => sellerById(c.match[1])?.profile ?? null },
  { method: 'PUT', path: /^\/billing\/profiles\/sellers\/([^/]+)$/, handler: (c) => saveProfile(c.match[1]!, c.body) },
  { method: 'GET', path: /^\/billing\/profiles\/lookup-inn$/, handler: (c) => {
      const inn = (c.query.get('inn') ?? '').trim()
      const found = DADATA[inn]
      return found ? { inn, ...found } : reply(404, { detail: 'party_not_found' })
    } },

  // Расчёты ФФ.
  { method: 'GET', path: /^\/billing\/seller-report\/summary$/, handler: ffSummary },
  { method: 'GET', path: /^\/billing\/seller-report\/storage-total$/, handler: (c) => ({ liter_days: storageLiterDays(c.query.get('seller_id'), rangeOf(c)) }) },
  { method: 'GET', path: /^\/billing\/seller-report\/sellers\/([^/]+)\/details$/, handler: (c) => details(c.match[1]!, c) },
  { method: 'GET', path: /^\/billing\/invoices-v2$/, handler: (c) => invoiceList(c, false) },
  { method: 'POST', path: /^\/billing\/invoices-v2\/preview$/, handler: previewInvoice },
  { method: 'POST', path: /^\/billing\/invoices-v2$/, handler: issueInvoice },
  { method: 'GET', path: /^\/billing\/invoices-v2\/([^/]+)$/, handler: (c) => {
      const inv = findInvoice(c.match[1]!, false)
      return inv ? v2Invoice(inv) : reply(404, { detail: 'invoice_not_found' })
    } },
  { method: 'GET', path: /^\/billing\/invoices\/([^/]+)$/, handler: (c) => {
      const inv = findInvoice(c.match[1]!, false)
      return inv ? legacyInvoice(inv) : reply(404, { detail: 'invoice_not_found' })
    } },
  { method: 'POST', path: /^\/billing\/(invoices-v2|invoices)\/([^/]+)\/cancel$/, handler: (c) => {
      const inv = findInvoice(c.match[2]!, false)
      if (!inv) return reply(404, { detail: 'invoice_not_found' })
      inv.status = 'cancelled'
      return { ok: true }
    } },
  { method: 'GET', path: /^\/billing\/tariff-matrix/, handler: () => ({ rows: [] }) },

  // Расчёты селлера — только его данные.
  { method: 'GET', path: /^\/seller-billing\/summary$/, handler: sellerScopeSummary },
  { method: 'GET', path: /^\/seller-billing\/storage-total$/, handler: (c) => ({ liter_days: storageLiterDays(SELLER_KR, rangeOf(c)) }) },
  { method: 'GET', path: /^\/seller-billing\/details$/, handler: (c) => details(SELLER_KR, c) },
  { method: 'GET', path: /^\/seller-billing\/invoices$/, handler: (c) => invoiceList(c, true) },
  { method: 'GET', path: /^\/seller-billing\/invoices\/v2\/([^/]+)$/, handler: (c) => {
      const inv = findInvoice(c.match[1]!, true)
      return inv ? v2Invoice(inv) : reply(404, { detail: 'invoice_not_found' })
    } },
  { method: 'GET', path: /^\/seller-billing\/invoices\/legacy\/([^/]+)$/, handler: (c) => {
      const inv = findInvoice(c.match[1]!, true)
      return inv ? legacyInvoice(inv) : reply(404, { detail: 'invoice_not_found' })
    } },
  { method: 'GET', path: /^\/seller-billing\/rates$/, handler: sellerRates },

  // Инвентаризация.
  { method: 'GET', path: /^\/operations\/inventory-counts$/, handler: () => inventoryCounts.map(countSummary) },
  { method: 'GET', path: /^\/operations\/inventory-counts\/([^/]+)\/print-sheet$/, handler: (c) => {
      const count = inventoryCounts.find((x) => x.id === c.match[1])
      return count ? printSheet(count) : reply(404, { detail: 'not_found' })
    } },
  { method: 'GET', path: /^\/operations\/inventory-counts\/([^/]+)$/, handler: (c) => {
      const count = inventoryCounts.find((x) => x.id === c.match[1])
      return count ? countDetail(count) : reply(404, { detail: 'not_found' })
    } },
  { method: 'PUT', path: /^\/operations\/inventory-counts\/([^/]+)\/lines$/, handler: (c) => {
      const count = inventoryCounts.find((x) => x.id === c.match[1])
      if (!count) return reply(404, { detail: 'not_found' })
      const body = c.body as { lines?: Array<{ line_id: string; actual_quantity: number | null }>; comment?: string | null; update_comment?: boolean } | null
      for (const line of body?.lines ?? []) count.actual[line.line_id] = line.actual_quantity
      if (body?.update_comment) count.comment = body.comment ?? ''
      return countDetail(count)
    } },

  // Кабинет селлера: каталог, ключи площадок, настройки.
  { method: 'GET', path: /^\/seller-catalog\/page$/, handler: sellerCatalogPage },
  { method: 'GET', path: /^\/seller-catalog\/keys$/, handler: (c) => sellerCatalogFiltered(c).filtered.filter((i) => !i.on_fulfillment).map((i) => String(i.key)) },
  { method: 'POST', path: /^\/seller-catalog\/add-to-fulfillment$/, handler: addToFulfillment },
  { method: 'GET', path: /^\/integrations\/wildberries\/self\/tokens$/, handler: () => ({ has_content_token: sellerCabinet.wbKeyConnected, has_marketplace_token: sellerCabinet.wbKeyConnected }) },
  { method: 'POST', path: /^\/integrations\/wildberries\/self\/content-token$/, handler: () => {
      const firstTime = !sellerCabinet.wbKeyConnected
      sellerCabinet.wbKeyConnected = true
      const seller = sellerById(SELLER_KR)!
      seller.wb_has_key = true
      seller.wb_marketplace_scope_ok = true
      seller.wb_marketplace_scope_checked_at = new Date().toISOString()
      seller.marketplaceRequisites.wb = { inn: '503214789652', legal_name: 'ИП Кравцова Анна Викторовна', kpp: null }
      const count = sellerCards.filter((c) => c.marketplace === 'wildberries').length
      return { validation_ok: true, validation_error: null, cards_received: count, cards_saved: firstTime ? count : 0 }
    } },
  { method: 'POST', path: /^\/integrations\/wildberries\/self\/sync-products$/, handler: () => ({ cards_received: sellerCabinet.wbKeyConnected ? sellerCards.filter((c) => c.marketplace === 'wildberries').length : 0, cards_saved: 0, products_created: 0, products_updated: 0 }) },
  { method: 'GET', path: /^\/integrations\/ozon\/self\/account$/, handler: ozonAccount },
  { method: 'POST', path: /^\/integrations\/ozon\/self\/sync-products$/, handler: () => ({ ok: true }) },
  { method: 'GET', path: /^\/operations\/marking-codes\/self\/credentials$/, handler: () => ({ has_cz_token: false, has_suz_oms_token: false, has_mp_api_key: false, marketplace: 'wildberries', mchd_id: null, mchd_valid_until: null, signing_method: 'none', edo_route: 'none', auto_introduce: false, auto_emit_limit: null }) },
  { method: 'GET', path: /^\/auth\/seller-staff-accounts$/, handler: () => [
      { id: 'staff-anna', email: 'anna@kravtsova-home.ru', full_name: 'Анна Кравцова', job_title: 'Владелец', display_name: 'Анна Кравцова', role: 'fulfillment_seller', seller_id: SELLER_KR, must_set_password: false, is_owner: true, permissions: { documents: true, products: true, honest_sign: true, settings: true, staff: true } },
      { id: 'staff-igor', email: 'igor@kravtsova-home.ru', full_name: 'Игорь Лебедев', job_title: 'Менеджер маркетплейсов', display_name: 'Игорь Лебедев', role: 'fulfillment_seller', seller_id: SELLER_KR, must_set_password: false, is_owner: false, permissions: { documents: true, products: true, honest_sign: false, settings: false, staff: false } },
    ] },
]

// Для отчёта прогона: какие запросы экран сделал, а макет не знает.
export const unmocked: string[] = []

export function handleRequest(method: string, rawPath: string, body: unknown, authorization: string | null): { status: number; body: unknown } {
  const [pathOnly, search = ''] = rawPath.split('?')
  const cabinet: Cabinet = authorization?.includes(SELLER_TOKEN) ? 'seller' : 'ff'
  for (const route of routes) {
    if (route.method !== method) continue
    const match = pathOnly!.match(route.path)
    if (!match) continue
    const result = route.handler({ method, path: pathOnly!, query: new URLSearchParams(search), body, cabinet, match })
    if (result instanceof HttpReply) return { status: result.status, body: result.body }
    return { status: 200, body: result }
  }
  unmocked.push(`${method} ${rawPath}`)
  // Незнакомый запрос: пустой ответ. GET — пустой список, остальное — «принято».
  return { status: 200, body: method === 'GET' ? [] : { ok: true } }
}

// Используется точкой входа: документы, которые упоминаются в движениях.
export const mockupDocs = { intakeDocs, unloadDocs, HERO_PRODUCT_ID }
