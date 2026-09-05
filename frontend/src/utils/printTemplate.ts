import { apiUrl } from '../api'
import { readApiErrorMessage } from './readApiErrorMessage'

export type PrintLayoutUnit = {
  block: 'label' | 'cz'
  copies: number
}

/**
 * Что печатать на этикетке ШК. Порядок строк единый для всех и не
 * настраивается: размер, цвет, бренд, состав — решение владельца 03.09.2026.
 */
export type PrintLabelOptions = {
  include_size: boolean
  include_color: boolean
  include_brand: boolean
  include_composition: boolean
}

export const DEFAULT_PRINT_LABEL_OPTIONS: PrintLabelOptions = {
  include_size: true,
  include_color: true,
  include_brand: true,
  include_composition: true,
}

export type PrintLayout = {
  units: PrintLayoutUnit[]
  /** Может не прийти со старого шаблона — тогда печатаем всё, что есть. */
  label_options?: PrintLabelOptions
}

export type PrintTemplate = {
  id: string | null
  seller_id: string | null
  product_id: string | null
  user_id: string | null
  name: string
  layout: PrintLayout
  is_default: boolean
  is_system: boolean
}

export function czCopiesFromLayout(layout: PrintLayout): number {
  const total = layout.units
    .filter((unit) => unit.block === 'cz')
    .reduce((sum, unit) => sum + unit.copies, 0)
  return total > 0 ? total : 1
}

export async function resolvePrintTemplate(
  token: string,
  params: { productId?: string; sellerId?: string },
): Promise<PrintTemplate> {
  const qs = new URLSearchParams()
  if (params.productId) {
    qs.set('product_id', params.productId)
  }
  if (params.sellerId) {
    qs.set('seller_id', params.sellerId)
  }
  const suffix = qs.toString()
  const res = await fetch(
    apiUrl(`/operations/marking-codes/print-templates/resolve${suffix ? `?${suffix}` : ''}`),
    { headers: { Authorization: `Bearer ${token}` } },
  )
  if (!res.ok) {
    throw new Error(await readApiErrorMessage(res))
  }
  return (await res.json()) as PrintTemplate
}

export async function createPrintTemplate(
  token: string,
  body: {
    name: string
    layout: PrintLayout
    seller_id?: string
    product_id?: string
    is_default?: boolean
  },
): Promise<PrintTemplate> {
  const res = await fetch(apiUrl('/operations/marking-codes/print-templates'), {
    method: 'POST',
    headers: {
      Authorization: `Bearer ${token}`,
      'Content-Type': 'application/json',
    },
    body: JSON.stringify(body),
  })
  if (!res.ok) {
    throw new Error(await readApiErrorMessage(res))
  }
  return (await res.json()) as PrintTemplate
}
