import type { StubRoute } from '../../screens/ff/knowledge/scenes/stubFetch'
import { PRODUCTS, productById, type DemoProduct } from './products'
import { bodyOf } from './routes'

/**
 * WMS-649 · «Честный знак»: запас кодов по трём товарам и печать из пула.
 *
 * Здесь товарам нужна маркировка (в других формах макета — нет): окно печати из
 * Честного знака всегда открывается как «ЧЗ + ШК». Коды — выдуманные, формата
 * GS1 DataMatrix, чтобы лента строилась как на настоящем складе.
 */

const PERSONAL = 120

export function inventoryPayload() {
  return {
    rows: PRODUCTS.map((product) => ({
      product_id: product.id,
      sku_code: product.sku,
      product_name: product.name,
      requires_honest_sign: true,
      available_count: PERSONAL,
      printed_count: 0,
      personal_available: PERSONAL,
      shared_baskets: [],
    })),
    unlinked_available_count: 0,
    defective_count: 0,
  }
}

function gtinOf(product: DemoProduct): string {
  const digits = (product.wbCodes[0] ?? '2037000000000').replace(/\D/g, '')
  return digits.padEnd(14, '0').slice(0, 14)
}

let serial = 1

export function fakeCis(product: DemoProduct): string {
  const number = String(serial++).padStart(13, '0')
  return `01${gtinOf(product)}21${number}\u001d91EE06\u001d92${'dGVzdC1zaWduYXR1cmUtd21zLTY0OS1tb2NrdXA'.padEnd(44, 'A')}`
}

export const honestSignRoutes: StubRoute[] = [
  { path: /^\/operations\/marking-codes\/inventory/, handler: () => inventoryPayload() },
  { path: /^\/operations\/marking-codes\/pools/, handler: () => [] },
  {
    method: 'POST',
    path: /^\/operations\/marking-codes\/products\/([^/?]+)\/print/,
    handler: (match, init) => {
      const product = productById(match[1]) ?? PRODUCTS[0]!
      const body = bodyOf(init) as { quantity?: number; layout_json?: unknown }
      const quantity = Math.max(1, Number(body.quantity) || 1)
      const codes = Array.from({ length: quantity }, () => fakeCis(product))
      return {
        codes,
        duplicate_copies: 0,
        quantity,
        shortage: null,
        layout: body.layout_json ?? { units: [{ block: 'cz', copies: 1 }, { block: 'label', copies: 1 }] },
        printed_codes: codes.map((cis, index) => ({
          id: `code-${product.id}-${serial}-${index}`,
          cis_code: cis,
          has_label_artifact: false,
        })),
      }
    },
  },
]
