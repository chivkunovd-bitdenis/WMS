import { cellRef, objRef, type ObjKind } from './pickStub'

/** The server already subtracts assignments/reservations in source.available. */
type ScanLocation = {
  storage_location_id: string
  available: number
  sources?: {
    available?: number
    container_path: { id: string; kind: ObjKind }[]
  }[]
}

export type ScanSource = {
  locationId: string
  containerKind: ObjKind | null
  containerId: string | null
}

/** Existing row disclosure needs the product identity even for an alternate barcode. */
export class PickScanSourceError extends Error {
  readonly productId: string
  /** Only this case may make a group scan try the next supply. */
  readonly reason: 'ambiguous' | 'no_stock'

  constructor(productId: string, message: string, reason: 'ambiguous' | 'no_stock' = 'ambiguous') {
    super(message)
    this.name = 'PickScanSourceError'
    this.productId = productId
    this.reason = reason
  }
}

export function resolveProductScanSource(
  product: { id: string; sku: string },
  locations: ScanLocation[],
  selected: ScanSource | null,
): ScanSource {
  // Preserve every explicit source: cell + NULL means loose stock, not any
  // container at that cell. The server validates its current availability.
  if (selected) return selected
  const candidates: ScanSource[] = []
  for (const location of locations) {
    const sources = location.sources?.length
      ? location.sources
      : [{ available: location.available, container_path: [] }]
    for (const source of sources) {
      if ((source.available ?? 0) < 1) continue
      const leaf = source.container_path.at(-1)
      candidates.push({
        locationId: location.storage_location_id,
        containerKind: leaf?.kind ?? null,
        containerId: leaf?.id ?? null,
      })
    }
  }
  if (candidates.length === 1) return candidates[0]
  throw new PickScanSourceError(
    product.id,
    candidates.length > 1
      ? `${product.sku} лежит в ${candidates.length} местах — уточните место или укажите число руками`
      : `${product.sku} — в выбранном месте нет доступного товара`,
    candidates.length > 1 ? 'ambiguous' : 'no_stock',
  )
}

export function scanSourceKey(source: ScanSource): string {
  return source.containerId ? objRef(source.containerId) : cellRef(source.locationId)
}
