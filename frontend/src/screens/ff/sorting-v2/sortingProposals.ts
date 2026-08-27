import type { Placement, SortCell, SortProduct } from './sortingStub'
import { remainingFor } from './sortingStub'

// Расчёт предложений вынесен из файла компонента: рядом с ним он ломает горячую
// перезагрузку, а сам по себе это чистая функция и её удобно проверять отдельно.

export type Proposal = {
  product: SortProduct
  cell: SortCell | null
  qty: number
  reason: string
  included: boolean
}

export function buildProposals(
  products: SortProduct[],
  placements: Placement[],
  cells: SortCell[],
  warehouseId: string,
): Proposal[] {
  const byId = new Map(cells.map((cell) => [cell.id, cell]))
  return products
    .map((product) => {
      const qty = remainingFor(product, placements)
      if (qty <= 0) return null
      const hint = product.alreadyAt.find(
        (place) => !place.warehouseId || place.warehouseId === warehouseId,
      )
      const cell = hint ? (byId.get(hint.cellId) ?? null) : null
      const elsewhere = !hint && product.alreadyAt.length > 0
      return {
        product,
        cell,
        qty,
        reason: cell
          ? `уже лежит ${hint!.qty} шт`
          : elsewhere
            ? 'лежит на другом складе'
            : 'новый на складе',
        included: Boolean(cell),
      } as Proposal
    })
    .filter(Boolean) as Proposal[]
}

