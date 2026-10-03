import { hasMarketplace, type DemoProduct, type Marketplace } from './products'

export function platformLabel(marketplace: Marketplace): string {
  return marketplace === 'wb' ? 'WB' : 'Ozon'
}

/** Площадки товара, у которых есть код. */
export function platformsOf(product: DemoProduct): Marketplace[] {
  return (['wb', 'ozon'] as const).filter((marketplace) => hasMarketplace(product, marketplace))
}

/** Какую площадку фиксирует контекст; null — оператору предстоит выбор («микс»). */
export function fixedPlatform(product: DemoProduct, docPlatform: Marketplace | null): Marketplace | null {
  const available = platformsOf(product)
  if (docPlatform && available.includes(docPlatform)) return docPlatform
  if (available.length === 1) return available[0]!
  return null
}
