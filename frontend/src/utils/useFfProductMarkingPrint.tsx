import { useCallback } from 'react'
import { apiUrl } from '../api'
import type { ProductLineDisplayMeta } from '../types/wbProductCatalog'
import { displayMetaToProductLabel } from './productBarcodePrint'
import { readApiErrorMessage } from './readApiErrorMessage'
import { useMarkingCodePrint } from './useMarkingCodePrint'

type MarkingOverviewResponse = {
  product: { requires_honest_sign: boolean }
  personal_pools: { available: number; printed: number }[]
  shared_baskets: { available: number }[]
}

export function sumPersonalAvailable(pools: { available: number }[]): number {
  return pools.reduce((sum, pool) => sum + (pool.available ?? 0), 0)
}

export function sumSharedBasketAvailable(baskets: { available: number }[]): number {
  return baskets.reduce((sum, basket) => sum + (basket.available ?? 0), 0)
}

export function computeMarkingAvailable(
  personalPools: { available: number }[],
  sharedBaskets: { available: number }[],
): number {
  return sumPersonalAvailable(personalPools) + sumSharedBasketAvailable(sharedBaskets)
}

export function computeMarkingAvailableFromInventory(
  personalAvailable: number,
  sharedBaskets: { available: number }[],
): number {
  return personalAvailable + sumSharedBasketAvailable(sharedBaskets)
}

export type OpenFfProductPrintOpts = {
  productId: string
  meta: ProductLineDisplayMeta
  documentNumber?: string | null
  /** База для печати (как qty_need_pack в упаковке). В каталоге не задаётся. */
  qtyNeedPack?: number
  /** catalog — своё поле «кол-во товаров»; packaging — база = qtyNeedPack, ЧЗ/ШК = множители на ед. */
  source?: 'catalog' | 'packaging'
  requiresHonestSign?: boolean
  markingAvailable?: number
  qtyMarkingPrinted?: number
  onPrinted?: () => void
}

function sumPersonalPrinted(pools: { printed: number }[]): number {
  return pools.reduce((sum, pool) => sum + (pool.printed ?? 0), 0)
}

async function fetchMarkingOverview(
  token: string,
  productId: string,
): Promise<MarkingOverviewResponse> {
  const res = await fetch(apiUrl(`/operations/marking-codes/products/${productId}/marking-overview`), {
    headers: { Authorization: `Bearer ${token}` },
  })
  if (!res.ok) {
    throw new Error(await readApiErrorMessage(res))
  }
  return (await res.json()) as MarkingOverviewResponse
}

/** Единая печать товара (как в отгрузке/упаковке): MarkingPrintDialog + конструктор ЧЗ. */
export function useFfProductMarkingPrint(token: string) {
  const { openPrint, dialog } = useMarkingCodePrint()

  const openCatalogProductPrint = useCallback(
    async (opts: OpenFfProductPrintOpts) => {
      let requiresHonestSign = opts.requiresHonestSign
      let markingAvailable = opts.markingAvailable
      let qtyMarkingPrinted = opts.qtyMarkingPrinted

      if (
        requiresHonestSign === undefined ||
        markingAvailable === undefined ||
        qtyMarkingPrinted === undefined
      ) {
        const overview = await fetchMarkingOverview(token, opts.productId)
        if (requiresHonestSign === undefined) {
          requiresHonestSign = overview.product.requires_honest_sign
        }
        if (markingAvailable === undefined) {
          markingAvailable = computeMarkingAvailable(
            overview.personal_pools,
            overview.shared_baskets ?? [],
          )
        }
        if (qtyMarkingPrinted === undefined) {
          qtyMarkingPrinted = sumPersonalPrinted(overview.personal_pools)
        }
      }

      const source =
        opts.source ?? (opts.qtyNeedPack != null && opts.qtyNeedPack > 0 ? 'packaging' : 'catalog')

      openPrint({
        token,
        source,
        productId: opts.productId,
        documentNumber: opts.documentNumber ?? null,
        qtyNeedPack: source === 'packaging' ? Math.max(1, opts.qtyNeedPack ?? 1) : 1,
        markingAvailable: markingAvailable ?? 0,
        qtyMarkingPrinted: qtyMarkingPrinted ?? 0,
        requiresHonestSign: requiresHonestSign ?? false,
        skuCode: opts.meta.sku_code,
        productName: opts.meta.product_name,
        productLabel: displayMetaToProductLabel(opts.meta),
        packagingInstructions: opts.meta.packaging_instructions,
        unitsInPack: opts.meta.units_in_pack,
        onPrinted: opts.onPrinted ?? (() => {}),
      })
    },
    [openPrint, token],
  )

  return { openCatalogProductPrint, dialog }
}
