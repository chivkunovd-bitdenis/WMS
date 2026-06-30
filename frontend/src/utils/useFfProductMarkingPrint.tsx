import { useCallback } from 'react'
import { apiUrl } from '../api'
import type { ProductLineDisplayMeta } from '../types/wbProductCatalog'
import { displayMetaToProductLabel } from './productBarcodePrint'
import { readApiErrorMessage } from './readApiErrorMessage'
import { useMarkingCodePrint } from './useMarkingCodePrint'

type MarkingOverviewResponse = {
  product: { requires_honest_sign: boolean }
  personal_pools: { available: number; printed: number }[]
}

export type OpenFfProductPrintOpts = {
  productId: string
  meta: ProductLineDisplayMeta
  documentNumber?: string | null
  qtyNeedPack?: number
  requiresHonestSign?: boolean
  markingAvailable?: number
  qtyMarkingPrinted?: number
  onPrinted?: () => void
}

function sumPersonalAvailable(pools: { available: number }[]): number {
  return pools.reduce((sum, pool) => sum + (pool.available ?? 0), 0)
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
          markingAvailable = sumPersonalAvailable(overview.personal_pools)
        }
        if (qtyMarkingPrinted === undefined) {
          qtyMarkingPrinted = sumPersonalPrinted(overview.personal_pools)
        }
      }

      openPrint({
        token,
        source: 'catalog',
        productId: opts.productId,
        documentNumber: opts.documentNumber ?? null,
        qtyNeedPack: opts.qtyNeedPack ?? 1,
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
