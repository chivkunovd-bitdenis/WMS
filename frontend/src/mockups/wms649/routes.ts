import type { StubRoute } from '../../screens/ff/knowledge/scenes/stubFetch'
import {
  catalogFields,
  catalogRow,
  DEMO_SELLER,
  PRODUCTS,
  productById,
  stockRow,
} from './products'

/**
 * WMS-649 · подставной сервер макета.
 *
 * Тот же приём, что у «живых макетов» базы знаний: настоящие экраны ходят на
 * бэкенд обычным fetch, а здесь вместо бэкенда — таблица «адрес → ответ». Всё,
 * чего в таблице нет, получает пустой успешный ответ. Данные — три выдуманных
 * товара из products.ts; порядок кодов в ответах зависит от выбранного
 * «ШК по умолчанию».
 */

export function queryOf(match: RegExpMatchArray): URLSearchParams {
  return new URLSearchParams((match.input ?? '').split('?')[1] ?? '')
}

export function bodyOf(init: RequestInit | undefined): Record<string, unknown> {
  try {
    return typeof init?.body === 'string' ? JSON.parse(init.body) : {}
  } catch {
    return {}
  }
}

export const WAREHOUSE = { id: 'wh-649', name: 'Основной склад', code: 'MSK-1', is_operational: true }

/* ─────────────────────────── общие для печати ─────────────────────────── */

const commonRoutes: StubRoute[] = [
  { path: /^\/auth\/me/, handler: () => ({ separate_marking_print_enabled: false }) },
  {
    path: /^\/operations\/marking-codes\/print-templates\/resolve/,
    handler: () => ({
      id: 'tpl-649',
      seller_id: null,
      product_id: null,
      user_id: null,
      name: 'ШК товара',
      layout: { units: [{ block: 'label', copies: 1 }] },
      is_default: true,
      is_system: true,
    }),
  },
  {
    path: /^\/operations\/marking-codes\/products\/([^/?]+)\/marking-overview/,
    handler: (match) => {
      const product = productById(match[1])
      return {
        product: { requires_honest_sign: product?.honestSign ?? false },
        personal_pools: product?.honestSign
          ? [{ available: product.markingCodes, printed: 0 }]
          : [],
        shared_baskets: [],
      }
    },
  },
  { path: /^\/warehouses$/, handler: () => [WAREHOUSE] },
  { path: /^\/sellers/, handler: () => [DEMO_SELLER] },
  {
    // Каталог продавца, из которого экраны берут ШК, размеры и привязки площадок.
    path: /^\/products\/linked-wb-catalog/,
    handler: () => PRODUCTS.map((product) => catalogFields(product)),
  },
]

/* ───────────────────────── каталог и карточка товара ───────────────────────── */

const catalogRoutes: StubRoute[] = [
  {
    path: /^\/products\/ff-catalog-page/,
    handler: (match) => {
      const query = queryOf(match)
      const search = (query.get('search') ?? '').trim().toLowerCase()
      const items = PRODUCTS.filter((product) => {
        if (!search) return true
        return (
          product.name.toLowerCase().includes(search) ||
          product.sku.toLowerCase().includes(search) ||
          [...product.wbCodes, ...product.ozonCodes].some((code) => code.toLowerCase().includes(search))
        )
      })
      return {
        items: items.map(catalogRow),
        total: items.length,
        scope_total: PRODUCTS.length,
        limit: Number(query.get('limit') ?? 100),
        offset: Number(query.get('offset') ?? 0),
        categories: [...new Set(PRODUCTS.map((product) => product.subject))].sort(),
      }
    },
  },
  {
    path: /^\/operations\/inventory-balances\/summary/,
    handler: (match) => {
      const ids = queryOf(match).getAll('product_id')
      return PRODUCTS.filter((product) => ids.includes(product.id)).map(stockRow)
    },
  },
  {
    path: /^\/products\/([^/?]+)\/card/,
    handler: (match) => {
      const product = productById(match[1])
      if (!product) return null
      return {
        ...catalogFields(product),
        length_mm: 250,
        width_mm: 200,
        height_mm: 40,
        weight_g: 300,
        location_warehouses: [],
      }
    },
  },
]

export function buildRoutes(extra: StubRoute[]): StubRoute[] {
  return [...extra, ...catalogRoutes, ...commonRoutes]
}
